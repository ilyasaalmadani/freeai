import json
import unittest
from unittest.mock import patch

import codex_bridge as bridge


class CodexBridge(unittest.TestCase):
    def test_responses_to_chat_maps_instructions_input_and_tools(self):
        body = {
            "model": "nvidianemotron-3-ultra-550b",
            "instructions": "Kamu asisten terminal.",
            "input": [
                {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "Baca "},
                    {"type": "input_text", "text": "file x"}]},
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "Saya cek."},
                    {"type": "function_call", "call_id": "call_1", "name": "read_file",
                     "arguments": '{"path": "x"}'}]},
                {"type": "function_call_output", "call_id": "call_1", "output": "isi file"},
            ],
            "tools": [{"type": "function", "name": "read_file", "description": "Baca file",
                       "parameters": {"type": "object", "properties": {}}, "strict": True}],
            "max_output_tokens": 4096,
            "tool_choice": "auto",
            "stream": True,
        }
        chat = bridge.responses_to_chat(body)
        self.assertEqual(chat["model"], "nvidianemotron-3-ultra-550b")
        self.assertEqual(chat["messages"][0], {"role": "system", "content": "Kamu asisten terminal."})
        self.assertEqual(chat["messages"][1], {"role": "user", "content": "Baca file x"})
        assistant = chat["messages"][2]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["content"], "Saya cek.")
        self.assertEqual(assistant["tool_calls"][0]["function"]["name"], "read_file")
        self.assertEqual(chat["messages"][3], {"role": "tool", "tool_call_id": "call_1", "content": "isi file"})
        self.assertEqual(chat["tools"][0]["function"]["name"], "read_file")
        self.assertNotIn("strict", chat["tools"][0]["function"])
        self.assertEqual(chat["max_tokens"], 4096)
        self.assertEqual(chat["tool_choice"], "auto")

    def test_responses_tool_choice_required_maps_to_auto(self):
        chat = bridge.responses_to_chat({"model": "m", "input": [], "tool_choice": "required", "stream": True})
        self.assertEqual(chat["tool_choice"], "auto")
        chat = bridge.responses_to_chat({"model": "m", "input": [], "tool_choice": {"type": "function", "name": "f"}, "stream": True})
        self.assertEqual(chat["tool_choice"], {"type": "function", "function": {"name": "f"}})

    def test_translator_streams_content_events_and_completes(self):
        translator = bridge.ResponseTranslator("model-x")
        events = []
        for piece in ["halo", " dunia"]:
            events += translator.content_delta(piece)
        self.assertEqual(events[0][0], "response.output_item.added")
        self.assertEqual(events[-1][0], "response.output_text.delta")
        done = translator.complete({"total_tokens": 5})
        names = [name for name, _ in done]
        self.assertIn("response.output_text.done", names)
        self.assertIn("response.output_item.done", names)
        self.assertIn("response.completed", names)
        completed = next(data for name, data in done if name == "response.completed")
        self.assertEqual(completed["response"]["output"][0]["content"][0]["text"], "halo dunia")
        self.assertEqual(completed["response"]["usage"]["total_tokens"], 5)
        self.assertIn("input_tokens", completed["response"]["usage"])

    def test_translator_tool_deltas_share_item_id_and_index(self):
        translator = bridge.ResponseTranslator("model-x")
        events = translator.tool_delta(0, "call_9", "web_search", '{"q":')
        added = next(data for name, data in events if name == "response.output_item.added")
        item_id = added["item"]["id"]
        more = translator.tool_delta(0, "call_9", "web_search", '"python"}')
        delta = next(data for name, data in more if name == "response.function_call_arguments.delta")
        self.assertEqual(delta["item_id"], item_id)
        self.assertEqual(delta["output_index"], 0)
        done = translator.complete({})
        done_call = next(data for name, data in done if name == "response.function_call_arguments.done")
        self.assertEqual(done_call["arguments"], '{"q":"python"}')
        self.assertEqual(done_call["item_id"], item_id)

    def test_translator_message_before_tools_reserves_index_zero(self):
        translator = bridge.ResponseTranslator("model-x")
        translator.content_delta("pakai tool")
        translator.tool_delta(0, "call_1", "f", "{}")
        done = translator.complete({})
        tool_added = [data for name, data in done if name == "response.output_item.done"
                      and data["item"]["type"] == "function_call"]
        self.assertEqual(tool_added[0]["output_index"], 1)

    def test_bridge_sse_writer_emits_named_events(self):
        import io
        class FakeWfile(io.BytesIO):
            def flush(self):
                pass
        wfile = FakeWfile()
        bridge.sse_write(wfile, "response.output_text.delta", {"type": "response.output_text.delta", "delta": "x"})
        text = wfile.getvalue().decode("utf-8")
        self.assertTrue(text.startswith("event: response.output_text.delta\ndata: "))
        self.assertIn('"delta": "x"', text)
        self.assertTrue(text.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
