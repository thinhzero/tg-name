import asyncio
import importlib.util
import json
import shlex
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


HAS_HTTP = importlib.util.find_spec("aiohttp") is not None
if HAS_HTTP:
    import speed_test
    from speed_test import SpeedTests, speed_result
    from shell_commands import ShellResult


@unittest.skipUnless(HAS_HTTP, "Cài aiohttp để kiểm thử công cụ speedtest")
class SpeedTestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"download": 120000000, "upload": 35000000, "ping": 12.5, "server": {"name": "Server 198.51.100.3", "country": "<VN>", "host": "203.0.113.5", "url": "https://private-upload.example/"}, "client": {"ip": "203.0.113.44", "isp": "ISP 2001:db8::1"}, "share": "https://speedtest.example/share?ip=203.0.113.44"}
        self.runner = SimpleNamespace(run=AsyncMock(return_value=ShellResult("internal command", json.dumps(self.data), 0)))
        self.tests = SpeedTests(self.runner)
        self.addAsyncCleanup(self.tests.close)
        self.edit = AsyncMock()
        patcher = patch.object(speed_test.importlib.util, "find_spec", return_value=object())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def run_test(self, **kwargs):
        await self.tests.run(self.edit, **{"owner_id": 42, "chat_id": 99, "userbot": True, **kwargs})

    async def test_result_whitelists_fields_and_hides_all_ip_and_share_data(self):
        for lang in ("vi", "en"):
            text = speed_result(json.dumps(self.data), lang)
            for value in ("198.51.100.3", "203.0.113.5", "203.0.113.44", "2001:db8::1", "private-upload", "share?"):
                self.assertNotIn(value, text)
            self.assertIn("120.00 Mbps", text)
            self.assertIn("35.00 Mbps", text)
            self.assertIn("12.50 ms", text)
            self.assertIn("hidden", text)
            self.assertIn("&lt;VN&gt;", text)

    async def test_speedtest_runs_fixed_secure_cli_without_share_or_user_arguments(self):
        await self.run_test(secret_values=["private-token"])
        command = self.runner.run.call_args.args[0]
        for value in ("-m speedtest", "--json", "--secure", "--no-pre-allocate"):
            self.assertIn(value, command)
        self.assertNotIn("--share", command)
        args = shlex.split(command)
        self.assertEqual(args[1:5], ["-W", "ignore::DeprecationWarning", "-m", "speedtest"])
        self.assertEqual(self.runner.run.call_args.kwargs["secret_values"], ["private-token"])
        self.assertEqual(self.edit.await_count, 2)
        self.assertIsNone(self.tests.job)

    async def test_success_sends_image_after_result_text(self):
        from io import BytesIO
        image = BytesIO(b"png")
        async def send_image(value):
            self.assertIs(value, image)
            self.assertIn("120.00 Mbps", self.edit.call_args.args[0])
        callback = AsyncMock(side_effect=send_image)
        with patch("speed_card.speed_card", return_value=image) as render:
            await self.run_test(send_image=callback)
        render.assert_called_once_with(json.dumps(self.data))
        callback.assert_awaited_once_with(image)
        self.assertTrue(image.closed)

    async def test_image_failure_preserves_successful_text_and_logs_safe_error(self):
        from io import BytesIO
        for rendering_fails in (False, True):
            self.edit.reset_mock()
            image = BytesIO(b"png")
            callback = AsyncMock(side_effect=RuntimeError("private-token 203.0.113.44"))
            with patch("speed_card.speed_card", side_effect=RuntimeError("private-token") if rendering_fails else None, return_value=image), patch.object(speed_test.chat_log, "emit") as emit:
                await self.run_test(send_image=callback)
            self.assertEqual(self.edit.await_count, 2)
            self.assertIn("120.00 Mbps", self.edit.call_args.args[0])
            emit.assert_called_once_with("error", {"action": "speedtest", "error": "Image delivery failed"})
            if not rendering_fails:
                self.assertTrue(image.closed)
            self.assertIsNone(self.tests.job)

    async def test_missing_dependency_does_not_start_a_process(self):
        with patch.object(speed_test.importlib.util, "find_spec", return_value=None):
            await self.run_test()
        self.runner.run.assert_not_awaited()
        self.assertIn("speedtest-cli", self.edit.call_args.args[0])

    async def test_failure_timeout_and_invalid_json_never_echo_raw_output(self):
        for result in (ShellResult("internal", "203.0.113.44 private-token", 1), ShellResult("internal", "203.0.113.44", -1, timed_out=True), ShellResult("internal", "203.0.113.44", 0), ShellResult("internal", json.dumps(self.data), 0, truncated=True)):
            self.runner.run.return_value = result
            self.edit.reset_mock()
            await self.run_test()
            self.assertNotIn("203.0.113.44", str(self.edit.call_args_list))
            self.assertNotIn("private-token", str(self.edit.call_args_list))
            self.assertIsNone(self.tests.job)

    async def test_known_errors_only_emit_fixed_actionable_diagnostics(self):
        cases = (
            ("ERROR: HTTP Error 403: Forbidden", "forbidden", "403"),
            ("Cannot retrieve speedtest configuration", "config", "configuration"),
            ("Unable to connect to servers to test latency.", "servers", "server"),
            ("No matched servers: 123", "servers", "server"),
            ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "tls", "CA certificates"),
            ("<urlopen error [Errno -3] Temporary failure in name resolution>", "network", "DNS"),
            ("Cannot retrieve speedtest configuration: HTTP Error 403: Forbidden", "forbidden", "403"),
            ("Cannot retrieve speedtest configuration: certificate verify failed", "tls", "CA certificates"),
        )
        for message, category, hint in cases:
            for lang in ("vi", "en"):
                with self.subTest(message=message, lang=lang):
                    raw = message + " 203.0.113.44 private-token https://private.example/ <script>"
                    self.runner.run.return_value = ShellResult("internal", raw, 1)
                    with patch.object(speed_test.chat_log, "emit") as emit:
                        await self.run_test(lang=lang)
                    text = self.edit.call_args.args[0]
                    if lang == "en":
                        self.assertIn(hint, text)
                    for secret in ("203.0.113.44", "private-token", "private.example", "<script>"):
                        self.assertNotIn(secret, text)
                        self.assertNotIn(secret, str(emit.call_args_list))
                    emit.assert_called_once_with("error", {"action": "speedtest", "error": category})

    async def test_warning_prefixed_json_fails_closed_without_echoing_warning(self):
        # Do not scrape arbitrary JSON from merged output: suppress the known
        # Python warning at its source and reject unexpected output safely.
        raw = "/private/path:1: DeprecationWarning: datetime.datetime.utcnow() is deprecated\n" + json.dumps(self.data)
        self.runner.run.return_value = ShellResult("internal", raw, 0)
        await self.run_test(lang="en")
        text = self.edit.call_args.args[0]
        self.assertEqual(text, speed_test.get_text("speed_failed", "en"))
        self.assertNotIn("private/path", text)
        self.assertIsNone(self.tests.job)

    async def test_unknown_and_truncated_errors_stay_generic(self):
        for raw, truncated in (("unknown private-token", False), ("HTTP Error 403: Forbidden", True)):
            self.runner.run.return_value = ShellResult("internal", raw, 1, truncated=truncated)
            await self.run_test(lang="en")
            self.assertEqual(self.edit.call_args.args[0], speed_test.get_text("speed_failed", "en"))

    async def test_numeric_fields_reject_nonfinite_negative_and_boolean_values(self):
        for value in (float("nan"), float("inf"), -1, True, "120"):
            self.data["download"] = value
            with self.assertRaises(ValueError):
                speed_result(json.dumps(self.data))

    async def test_only_same_owner_chat_transport_can_cancel_and_only_one_test_runs(self):
        started = asyncio.Event()
        async def run(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        self.runner.run.side_effect = run
        first = asyncio.create_task(self.run_test())
        await started.wait()
        other = AsyncMock()
        await self.tests.run(other, owner_id=42, chat_id=99, userbot=True)
        self.assertIn("Đang có", other.call_args.args[0])
        self.assertFalse(self.tests.cancel(99, 99, True))
        self.assertFalse(self.tests.cancel(42, 42, True))
        self.assertFalse(self.tests.cancel(42, 99, False))
        self.assertTrue(self.tests.cancel(42, 99, True))
        await first
        self.assertIn("Đã hủy", self.edit.call_args.args[0])
        self.assertIsNone(self.tests.job)

    async def test_shutdown_cancellation_propagates_and_clears_job(self):
        started = asyncio.Event()
        async def run(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        self.runner.run.side_effect = run
        task = asyncio.create_task(self.run_test())
        await started.wait()
        await self.tests.close(userbot=False)
        self.assertFalse(task.done())
        await self.tests.close(userbot=True)
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.tests.job)


if __name__ == "__main__":
    unittest.main()
