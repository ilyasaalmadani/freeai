import datetime as dt
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

import freeai as app


def entry(provider="first", access="keyless"):
    return {
        "id": provider + "/test", "provider": provider, "name": provider,
        "model": "test", "base_url": "https://example.com/v1", "access": access,
        "auth_env": "FREEAI_TEST_KEY", "check": {
            "status": "working", "checked_at": app.now(), "placeholder_auth": True,
            "latency_seconds": 1, "tools": "untested"
        }
    }


class FreeAI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous = app.DATA
        app.DATA = Path(self.directory.name)
        private = app.DATA / "private"
        self.paths = patch.multiple(app, USER_DATA=private, USER_SETTINGS=private / "settings.json",
                                    USER_CREDENTIALS=private / "credentials.json")
        self.paths.start()
        self.env = patch.dict(os.environ, {"FREEAI_STREAM": "0"})
        self.env.start()
        app.SEARCH_CACHE.clear()
        app.PAGE_CACHE.clear()

    def tearDown(self):
        self.env.stop()
        self.paths.stop()
        app.DATA = self.previous
        self.directory.cleanup()

    def catalog(self, entries):
        app.save_json(app.DATA / "catalog.json", {"entries": entries})

    def test_paid_models_and_hidden_costs_rejected(self):
        for model in [
            {"id": "paid", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "x:free", "pricing": {"prompt": "0", "completion": "0.01"}},
            {"id": "x:free", "pricing": {"prompt": "0", "completion": "0", "request": "0.5"}},
            {"id": "x:free", "pricing": {"prompt": "0"}},
            {"id": "x:free", "pricing": {"prompt": "NaN", "completion": "0"}},
        ]:
            self.assertFalse(app.is_free_model(model))
        self.assertTrue(app.is_free_model({"id": "x:free", "pricing": {"prompt": "0.0", "completion": "0", "request": "0"}}))

    def test_blockrun_live_catalog_requires_free_available_and_zero_prices(self):
        model = {"id": "nvidia/example", "billing_mode": "free", "available": True, "pricing": {"input": 0, "output": 0}}
        self.assertTrue(app.is_free_model(model, "blockrun"))
        self.assertFalse(app.is_free_model(dict(model, available=False), "blockrun"))
        self.assertFalse(app.is_free_model(dict(model, billing_mode="paid"), "blockrun"))
        self.assertFalse(app.is_free_model(dict(model, pricing={"input": 0, "output": 1}), "blockrun"))

    def test_crawler_discards_query_credentials(self):
        links = app.links_in('https://example.com/v1?key=SECRET https://user:pass@example.com/ https://example.com/v1#SECRET')
        self.assertEqual(links, ["https://example.com/v1"])

    def test_malformed_crawled_url_does_not_abort_discovery(self):
        links = app.links_in('https://[invalid https://example.com/v1')
        self.assertEqual(links, ["https://example.com/v1"])

    def test_irrelevant_search_results_not_counted_as_ai_providers(self):
        self.assertFalse(app.relevant_search_hit("Compress PDF for free", "Online free compressor API"))
        self.assertFalse(app.relevant_search_hit("OpenAI GitHub", "OpenAI repositories"))
        self.assertTrue(app.relevant_search_hit("Free LLM API", "Community inference endpoint"))

    def test_local_endpoints_not_probed(self):
        for ip in ["127.0.0.1", "192.168.1.2", "169.254.169.254", "::1"]:
            result = [(2, 1, 6, "", (ip, 443))]
            with patch.object(app.socket, "getaddrinfo", return_value=result):
                with self.assertRaises(app.Failure):
                    app.public_url("https://example.com/v1")

    def test_credential_urls_rejected(self):
        for url in ["http://example.com", "https://key@example.com", "https://example.com?key=secret"]:
            with self.assertRaises(app.Failure):
                app.public_url(url)

    def test_auth_redirect_not_followed(self):
        req = urllib.request.Request("https://example.com/v1", headers={"Authorization": "Bearer SECRET"})
        with patch.object(app, "public_url"):
            with self.assertRaises(app.Failure):
                app.Redirects().redirect_request(req, None, 302, "", {}, "https://other.example/v1")

    def test_no_key_no_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(app, "fetch") as fetch:
            result = app.probe_entry(entry(access="free_account"))
        self.assertEqual(result["status"], "needs_key")
        fetch.assert_not_called()

    def test_fake_200_or_empty_response_not_healthy(self):
        for response in [{"ok": True}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}]:
            with patch.object(app, "fetch", return_value=response):
                self.assertEqual(app.probe_entry(entry())["status"], "failed")

    def test_canned_response_fails_random_challenge(self):
        with patch.object(app, "fetch", return_value={"choices": [{"message": {"content": "hello world"}}]}):
            self.assertEqual(app.probe_entry(entry())["status"], "failed")

    def test_probe_passes_with_placeholder_used_for_export(self):
        def response(url, **kwargs):
            self.assertEqual(kwargs["key"], "no-key")
            challenge = kwargs["body"]["messages"][0]["content"].split()[-1]
            return {"model": "test", "choices": [{"message": {"content": challenge}}]}
        with patch.object(app, "fetch", side_effect=response):
            result = app.probe_entry(entry())
        self.assertEqual(result["status"], "working")
        self.assertEqual(result["tools"], "untested")

    def test_false_tool_calls_not_claimed_supported(self):
        def complete(row, messages, **kwargs):
            challenge = messages[0]["content"].split()[-1]
            if kwargs.get("tools"):
                return {"content": "I called echo", "tool_calls": []}, "test", {}
            return {"content": challenge}, "test", {}
        with patch.object(app, "complete", side_effect=complete):
            result = app.probe_entry(entry(), with_tools=True)
        self.assertEqual(result["status"], "working")
        self.assertEqual(result["tools"], "failed")

    def test_stale_or_future_success_not_active(self):
        for hours in [-1, 25]:
            row = entry()
            row["check"]["checked_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
            self.assertFalse(app.fresh(row))

    def test_export_only_fresh_keyless_and_no_secrets(self):
        old = entry("old")
        old["check"]["checked_at"] = "2020-01-01T00:00:00+00:00"
        self.catalog([entry(), entry("secret-provider", "free_account"), old])
        output = app.DATA / "export.json"
        with patch.dict(os.environ, {"FREEAI_TEST_KEY": "SECRET"}):
            app.export_config(output)
        text = output.read_text()
        self.assertNotIn("SECRET", text)
        self.assertNotIn("secret-provider", text)
        models = json.loads(text)["customProviders"][0]["models"]
        self.assertEqual(len(models), 1)
        self.assertFalse(models[0]["supportsTools"])

    def test_failed_routes_disable_previous_export(self):
        self.catalog([entry()])
        output = app.DATA / "export.json"
        app.export_config(output)
        self.catalog([])
        for _ in range(2):
            with self.assertRaises(app.Failure):
                app.export_config(output)
            config = app.load_json(output)
            self.assertEqual(config["customProviders"], [])
            self.assertEqual(config["models"][0]["enabled"], False)

    def test_failover_and_failed_route_demoted(self):
        first, second = entry(), entry("second")
        second["base_url"] = "https://second.example/v1"
        second["check"]["latency_seconds"] = 2
        self.catalog([first, second])
        with patch.object(app, "complete", side_effect=[app.Failure("HTTP 429", 429, "60"), ({"content": "answer"}, "test", {})]):
            self.assertEqual(app.ask([{"role": "user", "content": "hello"}]), "answer")
        saved = app.catalog()["entries"]
        self.assertEqual(saved[0]["check"]["status"], "rate_limited")
        self.assertEqual(saved[0]["check"]["retry_after"], "60")

    def test_probe_limit_counts_network_attempts_only(self):
        second = entry("second")
        second["check"] = {"status": "unverified"}
        self.catalog([entry("needs-key", "free_account"), entry("first"), second])
        with patch.dict(os.environ, {}, clear=True), patch.object(app, "probe_entry", return_value={"status": "working"}) as mock:
            app.probe(limit=1)
        self.assertEqual(mock.call_count, 2)  # one skipped key and one actual probe
        self.assertEqual(app.catalog()["entries"][2]["check"]["status"], "unverified")

    def test_failed_catalog_fetch_does_not_reuse_old_routes(self):
        self.catalog([entry("openrouter")])
        provider = {"id": "openrouter", "models": [], "catalog_url": "https://example.com/models"}
        with patch.object(app, "providers", return_value=[provider]), patch.object(app, "fetch", side_effect=app.Failure("offline")), patch.object(app, "DOCS", []):
            app.discover()
        self.assertEqual(app.catalog()["entries"], [])

    def test_exact_route_does_not_also_select_a_model_with_a_longer_name(self):
        short, extended = entry(), entry("first")
        extended.update(id="first/test-plus", model="test-plus")
        self.catalog([short, extended])
        _, routes = app.available_routes(model="first/test")
        self.assertEqual([route["id"] for route in routes], ["first/test"])

    def test_local_picker_uses_actual_api_ids_and_only_exported_ready_models(self):
        app.save_json(app.USER_CREDENTIALS, {"api_key": "freellmapi-private"})
        app.save_json(app.DATA / "freellmapi.config.json", {"customProviders": [{"models": [
            {"model": "nvidia/gpt-oss-20b", "supportsTools": True}]}]})
        response = {"data": [
            {"id": "nvidiagpt-oss-20b", "name": "nvidia/gpt-oss-20b", "available": True, "execution_status": "ready"},
            {"id": "unapproved", "name": "paid-model", "available": True, "execution_status": "ready"},
            {"id": "needs-key", "name": "nvidia/gpt-oss-20b", "available": False, "execution_status": "needsKey"}]}
        with patch.object(app, "fetch", return_value=response):
            routes = app.freellm_model_entries(refresh=True)
        self.assertEqual([route["model"] for route in routes], ["nvidiagpt-oss-20b"])
        self.assertEqual(routes[0]["check"]["tools"], "passed")
        self.assertNotIn("freellmapi-private", (app.USER_DATA / "models.json").read_text())

    def test_numbered_picker_selects_model_and_enter_cancels(self):
        row = entry()
        self.catalog([row])
        with patch.object(app, "tui_enabled", return_value=False), patch("builtins.input", return_value="2"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.choose_model("", None), row["id"])
        with patch.object(app, "tui_enabled", return_value=False), patch("builtins.input", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.choose_model("", row["id"]), row["id"])
        self.assertIsNone(app.choose_model("auto", row["id"]))

    def test_offline_router_does_not_block_every_prompt_with_repeated_catalog_requests(self):
        app.save_json(app.USER_CREDENTIALS, {"api_key": "freellmapi-private"})
        with patch.object(app, "fetch", side_effect=app.Failure("offline")) as fetch:
            self.assertEqual(app.freellm_model_entries(), [])
            self.assertEqual(app.freellm_model_entries(), [])
        self.assertEqual(fetch.call_count, 1)

    def test_reconnecting_preserves_selected_model(self):
        app.save_json(app.USER_CREDENTIALS, {"api_key": "freellmapi-private"})
        app.save_json(app.USER_SETTINGS, {"preferred_model": "first/test"})
        with patch.object(app, "fetch", side_effect=[{"needsSetup": False}, {"data": []}]), patch.object(app, "sync_local_route"), contextlib.redirect_stdout(io.StringIO()):
            app.connect_freellmapi()
        self.assertEqual(app.load_json(app.USER_SETTINGS)["preferred_model"], "first/test")

    def test_bad_model_name_keeps_cli_open_and_selected_model_is_used(self):
        row = entry()
        row["check"]["tools"] = "passed"
        self.catalog([row])
        def reply(pending, *args, **kwargs):
            return "OK", pending
        inputs = ["/model 2", "/model tidak-ada", "Halo", "/status", "/quit"]
        with patch.object(app, "read_prompt", side_effect=inputs), patch.object(app, "agent_reply", side_effect=reply) as call, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            app.coding_cli()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[4], row["id"])
        self.assertEqual(app.load_json(app.USER_SETTINGS)["preferred_model"], row["id"])

    def test_search_html_decodes_links_and_keeps_snippets(self):
        from web_support import SearchHTML
        parser = SearchHTML()
        parser.feed('<a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fpathlib.html&amp;x=1">Python <b>pathlib</b></a><td class="result-snippet">Filesystem paths</td>')
        self.assertEqual(parser.results[0]["url"], "https://docs.python.org/3/library/pathlib.html")
        self.assertEqual(parser.results[0]["summary"], "Filesystem paths")

    def test_unrelated_search_hits_are_not_returned_as_success(self):
        rows = [{"title": "Dokumentasi Adalah", "url": "https://example.com/dokumentasi", "summary": "Pengertian dokumentasi"},
                {"title": "Python pathlib", "url": "https://docs.python.org/3/library/pathlib.html", "summary": "Python filesystem paths"}]
        self.assertEqual(len(app.rank_results(rows, "dokumentasi Python pathlib resmi")), 1)

    def test_search_switches_engine_when_primary_requests_verification(self):
        rss = '<rss><channel><item><title>Python pathlib</title><link>https://docs.python.org/3/library/pathlib.html</link><description>Python paths</description></item></channel></rss>'
        with patch.object(app, "fetch", side_effect=['<div class="anomaly-modal">captcha</div>', rss]) as fetch:
            payload = json.loads(app.web_search("Python pathlib"))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(payload["source"], "Bing RSS")
        self.assertEqual(payload["results"][0]["url"], "https://docs.python.org/3/library/pathlib.html")

    def test_explicit_search_forces_tool_and_adds_sources(self):
        row = entry(); row["check"]["tools"] = "passed"; self.catalog([row])
        call = {"id": "s1", "type": "function", "function": {"name": "web_search", "arguments": '{"query":"Python pathlib"}'}}
        evidence = json.dumps({"source": "test", "results": [{"url": "https://docs.python.org/3/library/pathlib.html", "title": "Python pathlib"}]})
        responses = [({"content": None, "tool_calls": [call]}, "test", {}), ({"content": "Pathlib mengelola path."}, "test", {})]
        with patch.object(app, "complete", side_effect=responses) as complete, patch.object(app, "web_search", return_value=evidence) as search, contextlib.redirect_stderr(io.StringIO()):
            answer, _ = app.chat_reply([{"role": "user", "content": "Cari dokumentasi Python pathlib"}])
        self.assertEqual(complete.call_args_list[0].kwargs["tool_choice"]["function"]["name"], "web_search")
        search.assert_called_once_with("Python pathlib")
        self.assertIn("https://docs.python.org/3/library/pathlib.html", answer)

    def test_model_claiming_no_web_access_recovers_with_search(self):
        row = entry(); row["check"]["tools"] = "passed"; self.catalog([row])
        evidence = json.dumps({"source": "test", "results": [{"url": "https://example.com/python", "title": "Python"}]})
        responses = [({"content": "Saya tidak dapat mengakses internet."}, "test", {}), ({"content": "Jawaban bersumber."}, "test", {})]
        with patch.object(app, "complete", side_effect=responses), patch.object(app, "web_search", return_value=evidence) as search, contextlib.redirect_stderr(io.StringIO()):
            answer, _ = app.chat_reply([{"role": "user", "content": "Apa fungsi pathlib?"}])
        search.assert_called_once()
        self.assertIn("https://example.com/python", answer)

    def test_stable_question_does_not_force_a_search_and_off_disables_it(self):
        row = entry(); row["check"]["tools"] = "passed"; self.catalog([row])
        with patch.object(app, "complete", return_value=({"content": "Rekursi memanggil fungsi sendiri."}, "test", {})) as complete, patch.object(app, "web_search") as search:
            app.chat_reply([{"role": "user", "content": "Jelaskan rekursi"}])
        search.assert_not_called()
        self.assertIsNone(complete.call_args.kwargs["tool_choice"])
        app.save_json(app.USER_SETTINGS, {"web_mode": "off"})
        with patch.object(app, "complete", return_value=({"content": "Belum tahu info terkini."}, "test", {})), patch.object(app, "web_search") as search, contextlib.redirect_stderr(io.StringIO()):
            app.chat_reply([{"role": "user", "content": "Cari berita terbaru"}])
        search.assert_not_called()

    def test_page_reader_ignores_scripts_and_queries_do_not_leak_keys(self):
        from web_support import PageText, search_query
        page = PageText(); page.feed('<title>Doc</title><script>steal secrets</script><p>Useful text</p>')
        self.assertNotIn("steal secrets", page.content())
        query = search_query('Python error ```private code``` /Users/ilyas/private.txt api_key=sk-privatepassword')
        self.assertNotIn("private", query)

    def test_page_reader_starts_at_requested_section(self):
        from web_support import PageText
        page = PageText()
        page.feed('<p>irrelevant intro</p><h2 id="read_text">Read a text file</h2><p>encoding option</p>')
        self.assertNotIn("irrelevant intro", page.content("read_text"))
        self.assertIn("Read a text file", page.content("read_text"))

    def test_public_search_redirect_allows_query_without_forwarding_credentials(self):
        req = urllib.request.Request("https://example.com/search?q=python")
        with patch.object(app, "public_url") as validate:
            redirected = app.Redirects().redirect_request(req, None, 302, "", {}, "https://other.example/search?q=python")
        self.assertEqual(redirected.full_url, "https://other.example/search?q=python")
        validate.assert_called_once_with("https://other.example/search")

    def test_stream_chat_assembles_content_tool_calls_and_usage(self):
        row = entry()
        events = [
            {"choices": [{"delta": {"content": "halo dunia"}}]},
            {"choices": [{"delta": {"content": " 😀"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1",
                                                     "function": {"name": "web_search", "arguments": "{\"query\":"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"Python pathlib\"}"}}]}}]},
            {"model": "served", "usage": {"total_tokens": 9}},
        ]
        raw = "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
        byte_chunks = [raw.encode()[i:i + 7] for i in range(0, len(raw.encode()), 7)]
        collected = []
        with patch.object(app, "public_url"), patch.object(app.urllib.request, "build_opener", return_value=FakeOpener(FakeStreamResponse(byte_chunks))):
            message, served, usage = app.stream_complete(row, [{"role": "user", "content": "halo"}],
                                                         tools=[{"type": "function", "function": {"name": "web_search"}}],
                                                         on_delta=collected.append)
        self.assertEqual("".join(collected), "halo dunia 😀")
        self.assertEqual(message["content"], "halo dunia 😀")
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "web_search")
        self.assertEqual(json.loads(message["tool_calls"][0]["function"]["arguments"]), {"query": "Python pathlib"})
        self.assertEqual(served, "served")
        self.assertEqual(usage["total_tokens"], 9)

    def test_stream_falls_back_to_json_when_server_ignores_stream_flag(self):
        row = entry()
        response = FakeStreamResponse([json.dumps({"model": "served", "choices": [{"message": {"content": "jawaban"}}],
                                                   "usage": {"total_tokens": 3}})],
                                      content_type="application/json")
        with patch.object(app, "public_url"), patch.object(app.urllib.request, "build_opener", return_value=FakeOpener(response)):
            message, served, usage = app.stream_complete(row, [{"role": "user", "content": "halo"}])
        self.assertEqual(message["content"], "jawaban")
        self.assertEqual(served, "served")
        self.assertEqual(usage["total_tokens"], 3)

    def test_empty_or_broken_stream_rejected(self):
        row = entry()
        for chunks in (["data: [DONE]\n\n"], ["data: bukan-json\n\n"]):
            response = FakeStreamResponse(chunks)
            with patch.object(app, "public_url"), patch.object(app.urllib.request, "build_opener", return_value=FakeOpener(response)):
                with self.assertRaises(app.Failure):
                    app.stream_complete(row, [{"role": "user", "content": "halo"}])

    def test_stream_printer_strips_ansi_and_survives_split_escapes(self):
        printer = app.StreamPrinter(enabled=True)
        out = io.StringIO()
        with patch.object(app.sys, "stdout", out):
            printer.feed("halo \x1b[38;5;")
            printer.feed("203mmerah\x1b[0m dunia")
            printer.finish()
        self.assertIn("halo merah dunia", out.getvalue())
        self.assertNotIn("\x1b", out.getvalue())

    def test_chat_reply_streams_when_printer_enabled(self):
        row = entry()
        row["check"]["tools"] = "passed"
        self.catalog([row])
        printer = app.StreamPrinter(enabled=True)

        def fake_stream(entry, messages, max_tokens=2048, tools=None, timeout=120, tool_choice=None, task_type=None, on_delta=None):
            if on_delta:
                on_delta("jawaban stream")
            return {"content": "jawaban stream"}, "served", {}

        with patch.object(app, "stream_complete", side_effect=fake_stream) as stream, contextlib.redirect_stdout(io.StringIO()):
            answer, _ = app.chat_reply([{"role": "user", "content": "halo"}], stream=printer)
        stream.assert_called_once()
        self.assertEqual(answer, "jawaban stream")
        self.assertTrue(printer.used)

    def test_stream_failure_falls_back_to_complete_on_same_route(self):
        row = entry()
        row["check"]["tools"] = "passed"
        self.catalog([row])
        printer = app.StreamPrinter(enabled=True)
        with patch.object(app, "stream_complete", side_effect=app.Failure("stream ditolak")), \
             patch.object(app, "complete", return_value=({"content": "jawaban normal"}, "served", {})) as complete, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            answer, _ = app.chat_reply([{"role": "user", "content": "halo"}], stream=printer)
        complete.assert_called_once()
        self.assertTrue(printer.aborted)
        self.assertEqual(answer, "jawaban normal")

    def test_command_menu_numbered_fallback(self):
        with patch.object(app, "tui_enabled", return_value=False), patch("builtins.input", return_value="1"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.command_menu(), "/model")
        with patch.object(app, "tui_enabled", return_value=False), patch("builtins.input", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(app.command_menu())

    def test_markdown_next_splits_paragraphs_and_holds_open_fences(self):
        self.assertEqual(app.markdown_next("satu\n\n", None), ("satu\n\n", "", None))
        self.assertEqual(app.markdown_next("belum selesai", None), (None, "belum selesai", None))
        self.assertEqual(app.markdown_next("```py\nx = 1\n", None), (None, "```py\nx = 1\n", "```"))
        self.assertEqual(app.markdown_next("```py\nx = 1\n```\n", "```"), ("```py\nx = 1\n```\n", "", None))
        emit, rest, fence = app.markdown_next("teks\n\n```py\n", None)
        self.assertEqual((emit, rest, fence), ("teks\n\n", "```py\n", None))
        emit, rest, fence = app.markdown_next(rest, None)
        self.assertEqual((emit, fence), (None, "```"))

    def test_stream_printer_renders_paragraphs_incrementally(self):
        printer = app.StreamPrinter(enabled=True)
        out = io.StringIO()
        rendered = []
        with patch.object(app, "render_markdown", side_effect=lambda text: rendered.append(text) or ("R:" + text.replace("\n", "|") + "|\n")), \
             patch.object(app.sys, "stdout", out):
            printer.feed("paragraf satu.\n\n")
            printer.feed("paragraf dua.")
            printer.finish()
        self.assertIn("R:paragraf satu.|", out.getvalue())
        self.assertIn("R:paragraf dua.|", out.getvalue())

    def test_stream_printer_waits_for_closed_code_fence(self):
        printer = app.StreamPrinter(enabled=True)
        out = io.StringIO()
        rendered = []
        with patch.object(app, "render_markdown", side_effect=lambda text: rendered.append(text) or ("R:" + text)), \
             patch.object(app.sys, "stdout", out):
            printer.feed("```python\nx = 1\n")
            printer.feed("y = 2\n```\n")
            printer.finish()
        self.assertEqual(len(rendered), 1)
        self.assertIn("x = 1", rendered[0])
        self.assertIn("y = 2", rendered[0])

    def test_session_saved_and_resumed_for_same_workspace_and_mode(self):
        workspace = Path(self.directory.name)
        messages = [{"role": "user", "content": "halo"}, {"role": "assistant", "content": "hai"}]
        app.save_chat_session(workspace, True, messages, "first/test")
        self.assertEqual(app.load_chat_session(workspace, True), (messages, "first/test"))
        self.assertEqual(app.load_chat_session(workspace / "lain", True), (None, None))
        self.assertEqual(app.load_chat_session(workspace, False), (None, None))

    def test_resume_restores_saved_messages_in_cli(self):
        row = entry()
        row["check"]["tools"] = "passed"
        self.catalog([row])
        app.save_chat_session(Path.cwd(), True, [{"role": "user", "content": "pertanyaan lama"}], None)
        inputs = ["/status", "/quit"]
        out = io.StringIO()
        with patch.object(app, "read_prompt", side_effect=inputs), patch.object(app, "agent_reply") as reply, \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            app.coding_cli(resume=True)
        reply.assert_not_called()
        self.assertIn("Pesan dalam konteks: 1", out.getvalue())


class FakeStreamResponse:
    def __init__(self, chunks, content_type="text/event-stream"):
        self.chunks = [chunk if isinstance(chunk, bytes) else str(chunk).encode() for chunk in chunks]
        self.headers = {"Content-Type": content_type}
        self.position = 0

    def read(self, size=-1):
        if self.position >= len(self.chunks):
            return b""
        chunk = self.chunks[self.position]
        self.position += 1
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout=None):
        return self.response


if __name__ == "__main__":
    unittest.main()
