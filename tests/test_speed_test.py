import asyncio
import importlib.util
import json
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
        self.assertEqual(self.runner.run.call_args.kwargs["secret_values"], ["private-token"])
        self.assertEqual(self.edit.await_count, 2)
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
