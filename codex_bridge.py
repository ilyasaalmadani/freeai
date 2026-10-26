#!/usr/bin/env python3
"""Jembatan Responses API (Codex) → Chat Completions (FreeLLMAPI).

Codex 0.164+ hanya berbicara OpenAI Responses API untuk custom provider,
sedangkan FreeLLMAPI hanya menyediakan Chat Completions. Server kecil ini
menerjemahkan kedua arah secara streaming sehingga Codex asli bisa memakai
model gratis FreeAI. Python standard library only.

Jalankan: python3 codex_bridge.py [--port 3002] [--target http://127.0.0.1:3001/v1]
"""
import argparse
import json
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://127.0.0.1:3001/v1"
TIMEOUT = 180


def now_ts():
    return int(time.time())


def rid(kind):
    return kind + "_" + secrets.token_hex(10)


def responses_to_chat(body):
    """Map a Responses API request body to a Chat Completions body."""
    if not isinstance(body, dict):
        raise ValueError("body harus objek JSON")
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("model wajib diisi")
    messages = []
    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})
    for item in body.get("input") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "message":
            role = item.get("role", "user")
            parts = item.get("content") or []
            text = ""
            for part in parts:
                if isinstance(part, str):
                    text += part
                elif isinstance(part, dict) and part.get("type") in ("input_text", "output_text", "text"):
                    text += part.get("text") or ""
            tool_calls = []
            for part in parts:
                if isinstance(part, dict) and part.get("type") == "function_call":
                    tool_calls.append({"id": part.get("call_id") or rid("call"),
                                       "type": "function",
                                       "function": {"name": part.get("name") or "",
                                                    "arguments": part.get("arguments") or "{}"}})
            message = {"role": role, "content": text or None}
            if tool_calls:
                message["tool_calls"] = tool_calls
            messages.append(message)
        elif kind == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item.get("call_id") or "call",
                             "content": item.get("output") or ""})
    chat = {"model": model, "messages": messages, "stream": bool(body.get("stream"))}
    if body.get("max_output_tokens"):
        chat["max_tokens"] = int(body["max_output_tokens"])
    for field in ("temperature", "top_p"):
        if body.get(field) is not None:
            chat[field] = body[field]
    tools = []
    for tool in body.get("tools") or []:
        if isinstance(tool, dict) and tool.get("type") == "function":
            function = dict(tool.get("function") if isinstance(tool.get("function"), dict) else {})
            spec = {"type": "function", "function": {
                "name": function.get("name") or tool.get("name") or "",
                "description": function.get("description") or tool.get("description") or "",
                "parameters": function.get("parameters") or tool.get("parameters") or {"type": "object", "properties": {}},
            }}
            tools.append(spec)
    if tools:
        chat["tools"] = tools
    choice = body.get("tool_choice")
    if choice == "required":
        chat["tool_choice"] = "auto"
    elif choice == "none":
        chat["tool_choice"] = "none"
    elif isinstance(choice, dict) and choice.get("type") == "function":
        chat["tool_choice"] = {"type": "function", "function": {"name": choice.get("name") or ""}}
    elif choice == "auto" or (tools and choice is None):
        chat["tool_choice"] = "auto"
    return chat


def responses_usage(usage):
    """Normalize Chat Completions usage into Responses API usage fields."""
    usage = usage or {}
    prompt = usage.get("input_tokens", usage.get("prompt_tokens"))
    completion = usage.get("output_tokens", usage.get("completion_tokens"))
    total = usage.get("total_tokens")
    try:
        prompt = int(prompt or 0)
        completion = int(completion or 0)
        total = int(total or prompt + completion)
    except (TypeError, ValueError):
        prompt, completion, total = 0, 0, 0
    return {"input_tokens": prompt, "output_tokens": completion, "total_tokens": total,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0}}


def function_call_item(call_id, name, arguments=""):
    return {"type": "function_call", "id": rid("fc"), "call_id": call_id,
            "name": name, "arguments": arguments, "status": "in_progress"}


class ResponseTranslator:
    """Chat Completions SSE → Responses API events."""

    def __init__(self, model):
        self.model = model
        self.response_id = rid("resp")
        self.message_id = rid("msg")
        self.sequence = 0
        self.content = []
        self.tools = {}
        self.tool_order = []
        self.text_open = False
        self.tool_open = {}
        self.output = []
        self.started = False

    def event(self, kind, **fields):
        payload = {"type": kind, "sequence_number": self.sequence}
        payload.update(fields)
        self.sequence += 1
        return payload

    def start(self):
        if self.started:
            return []
        self.started = True
        return [("response.created", self.event("response.created", response={
            "id": self.response_id, "object": "response", "created_at": now_ts(),
            "status": "in_progress", "model": self.model, "output": []}))]

    def message_start(self):
        item = {"type": "message", "id": self.message_id, "status": "in_progress",
                "role": "assistant", "content": []}
        return [("response.output_item.added", self.event("response.output_item.added", output_index=0, item=item)),
                ("response.content_part.added", self.event("response.content_part.added", item_id=self.message_id,
                                                          output_index=0, content_index=0,
                                                          part={"type": "output_text", "text": "", "annotations": []}))]

    def content_delta(self, piece):
        self.content.append(piece)
        if not self.text_open:
            self.text_open = True
            return self.message_start() + [("response.output_text.delta", self.event(
                "response.output_text.delta", item_id=self.message_id, output_index=0, content_index=0, delta=piece))]
        return [("response.output_text.delta", self.event(
            "response.output_text.delta", item_id=self.message_id, output_index=0, content_index=0, delta=piece))]

    def tool_delta(self, index, call_id, name, arguments_piece):
        if index not in self.tool_open:
            self.tool_open[index] = True
            self.tool_order.append(index)
            output_index = len(self.tool_order) - 1 if not (self.text_open or self.content) else len(self.tool_order)
            slot = {"call_id": call_id or rid("call"), "name": name or "",
                    "arguments": [], "output_index": output_index}
            item = function_call_item(slot["call_id"], name or "", "")
            slot["item_id"] = item["id"]
            self.tools[index] = slot
            events = [("response.output_item.added", self.event("response.output_item.added",
                                                                output_index=output_index, item=item))]
            if arguments_piece:
                slot["arguments"].append(arguments_piece)
                events.append(("response.function_call_arguments.delta", self.event(
                    "response.function_call_arguments.delta", item_id=item["id"],
                    output_index=output_index, delta=arguments_piece)))
            return events
        slot = self.tools[index]
        slot["name"] = slot["name"] or name or ""
        if arguments_piece:
            slot["arguments"].append(arguments_piece)
            return [("response.function_call_arguments.delta", self.event(
                "response.function_call_arguments.delta", item_id=slot["item_id"],
                output_index=slot["output_index"], delta=arguments_piece))]
        return []

    def finish_text(self):
        if not self.text_open:
            return []
        self.text_open = False
        text = "".join(self.content)
        part = {"type": "output_text", "text": text, "annotations": []}
        item = {"type": "message", "id": self.message_id, "status": "completed",
                "role": "assistant", "content": [part]}
        self.output.append(item)
        return [("response.output_text.done", self.event("response.output_text.done", item_id=self.message_id,
                                                         output_index=0, content_index=0, text=text)),
                ("response.content_part.done", self.event("response.content_part.done", item_id=self.message_id,
                                                          output_index=0, content_index=0, part=part)),
                ("response.output_item.done", self.event("response.output_item.done", output_index=0, item=item))]

    def finish_tools(self):
        events = []
        for index in self.tool_order:
            slot = self.tools[index]
            arguments = "".join(slot["arguments"])
            item = function_call_item(slot["call_id"], slot["name"], arguments)
            item["id"] = slot["item_id"]
            item["status"] = "completed"
            item_id = item["id"]
            self.output.append(item)
            output_index = slot["output_index"]
            events.append(("response.function_call_arguments.done", self.event(
                "response.function_call_arguments.done", item_id=item_id, output_index=output_index, arguments=arguments)))
            events.append(("response.output_item.done", self.event("response.output_item.done",
                                                                   output_index=output_index, item=item)))
        self.tool_open = {}
        return events

    def complete(self, usage):
        events = self.finish_text() + self.finish_tools()
        response = {"id": self.response_id, "object": "response", "created_at": now_ts(),
                    "status": "completed", "model": self.model, "output": self.output,
                    "usage": responses_usage(usage)}
        events.append(("response.completed", self.event("response.completed", response=response)))
        return events

    def error(self, message):
        return [("error", {"type": "error", "message": message})]


def chat_delta_to_events(translator, delta, model=None):
    """Translate one Chat Completions stream delta into Responses events."""
    events = translator.start()
    if model:
        translator.model = model
    if not delta:
        return events
    piece = delta.get("content")
    if isinstance(piece, str) and piece:
        events += translator.content_delta(piece)
    for call in delta.get("tool_calls") or []:
        function = call.get("function") or {}
        events += translator.tool_delta(call.get("index", 0), call.get("id"),
                                        function.get("name"), function.get("arguments"))
    return events


def sse_write(wfile, event, data):
    payload = json.dumps(data, ensure_ascii=False)
    wfile.write(("event: " + event + "\ndata: " + payload + "\n\n").encode("utf-8"))
    wfile.flush()


def proxy_models(path, headers, body=None):
    url = UPSTREAM + path
    return http_request(url, headers, body)


def http_request(url, headers, body=None, timeout=TIMEOUT):
    wanted = {key: value for key, value in headers.items() if key.lower() in {"authorization", "content-type", "accept", "user-agent"}}
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8") if body is not None else None, headers=wanted)
    return urllib.request.urlopen(request, timeout=timeout)


def exported_models():
    """Model yang diekspor FreeAI ke FreeLLMAPI (lulus tes gratis)."""
    try:
        path = pathlib.Path(__file__).resolve().parent / "data" / "freellmapi.config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        return {model["model"] for provider in config.get("customProviders", [])
                for model in provider.get("models", []) if model.get("model")}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        sys.stderr.write("[bridge] " + (format % args) + "\n")

    def _send(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            upstream_path = self.path[3:] if self.path.startswith("/v1/") else self.path
            try:
                with http_request(UPSTREAM + upstream_path, dict(self.headers)) as upstream:
                    data = json.loads(upstream.read().decode("utf-8"))
                allowed = exported_models()
                rows = []
                for row in data.get("data", []):
                    if not isinstance(row, dict) or not row.get("id"):
                        continue
                    if allowed:
                        name = row.get("name") or row["id"]
                        compact = name.replace("/", "").replace("-", "").replace(".", "")
                        if name not in allowed and row["id"] not in allowed and compact not in allowed:
                            continue
                    item = dict(row)
                    item.setdefault("name", row["id"])
                    item.setdefault("display_name", row.get("name") or row["id"])
                    if "available" not in item:
                        item["available"] = True
                    if not item.get("execution_status"):
                        item["execution_status"] = "ready"
                    if not isinstance(item.get("context_window"), int) or not item["context_window"]:
                        item["context_window"] = 131072
                    if not item.get("max_output_tokens"):
                        item["max_output_tokens"] = 16384
                    rows.append(item)
                payload = json.dumps({"object": "list", "data": rows}).encode("utf-8")
                self._send(200, "application/json", payload)
            except Exception as exc:
                self._send(502, "application/json", json.dumps({"error": str(exc)}).encode("utf-8"))
        else:
            self._send(404, "application/json", b'{"error":"not found"}')

    def do_POST(self):
        if not self.path.startswith("/v1/responses"):
            self._send(404, "application/json", b'{"error":"not found"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            chat = responses_to_chat(body)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            self._send(400, "application/json", json.dumps({"error": str(exc)}).encode("utf-8"))
            return
        try:
            if not chat.get("stream"):
                try:
                    with http_request(UPSTREAM + "/chat/completions", dict(self.headers), chat) as upstream:
                        result = json.loads(upstream.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    self._send(exc.code, "application/json",
                               json.dumps({"error": f"upstream HTTP {exc.code}"}).encode("utf-8"))
                    return
                message = result["choices"][0]["message"]
                output = []
                if message.get("content"):
                    output.append({"type": "message", "id": rid("msg"), "status": "completed",
                                   "role": "assistant", "content": [{"type": "output_text", "text": message["content"]}]})
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    output.append({"type": "function_call", "id": rid("fc"), "call_id": call.get("id") or rid("call"),
                                   "name": function.get("name") or "", "arguments": function.get("arguments") or "{}",
                                   "status": "completed"})
                usage = result.get("usage") or {}
                response = {"id": rid("resp"), "object": "response", "created_at": now_ts(), "status": "completed",
                            "model": result.get("model") or chat["model"], "output": output,
                            "usage": responses_usage(usage)}
                self._send(200, "application/json", json.dumps(response, ensure_ascii=False).encode("utf-8"))
                return
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            translator = ResponseTranslator(chat["model"])
            usage = {}
            with http_request(UPSTREAM + "/chat/completions", dict(self.headers), chat) as upstream:
                buffer = b""
                while True:
                    chunk = upstream.read(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line or line.startswith(b":"):
                            continue
                        if line.startswith(b"data:"):
                            line = line[5:].lstrip()
                        if line == b"[DONE]":
                            continue
                        try:
                            event = json.loads(line.decode("utf-8"))
                        except (UnicodeError, json.JSONDecodeError):
                            continue
                        if event.get("model"):
                            translator.model = event["model"]
                        if isinstance(event.get("usage"), dict) and event["usage"]:
                            usage = event["usage"]
                        for choice in event.get("choices", []):
                            for name, data in chat_delta_to_events(translator, choice.get("delta") or {}, event.get("model")):
                                sse_write(self.wfile, name, data)
            for name, data in translator.complete(usage):
                sse_write(self.wfile, name, data)
        except urllib.error.HTTPError as exc:
            self.wfile.write(("event: error\ndata: " + json.dumps(
                {"type": "error", "message": f"upstream HTTP {exc.code}"}) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        except Exception as exc:
            try:
                for name, data in translator.error(str(exc)):
                    sse_write(self.wfile, name, data)
            except Exception:
                pass


def main():
    global UPSTREAM
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--target", default=UPSTREAM)
    args = parser.parse_args()
    UPSTREAM = args.target.rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Codex bridge: {UPSTREAM} -> http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
