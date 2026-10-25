import asyncio
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import shell_commands
from shell_commands import ShellError, ShellResult, ShellRunner, clipped_html, format_shell_result


@unittest.skipUnless(sys.platform.startswith(("linux", "android")), "Linux/Termux shell execution")
class ShellRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-shell-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = ShellRunner(self.root, timeout=2)

    async def test_ls_runs_in_project_directory(self):
        (self.root / "entry.txt").write_text("sample")
        result = await self.runner.run("ls -1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("entry.txt", result.output)

    async def test_commands_are_not_restricted_to_uptime(self):
        tool = self.root / "fastfetch"
        tool.write_text(f"#!{shutil.which('sh')}\nprintf 'test fastfetch\\n'\n")
        tool.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(self.root) + os.pathsep + os.environ.get("PATH", "")}):
            result = await self.runner.run("fastfetch")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output, "test fastfetch")

    async def test_termux_shell_is_found_in_prefix_path(self):
        real_shell = shutil.which("sh")
        prefix = self.root / "termux" / "usr"
        binary_dir = prefix / "bin"
        binary_dir.mkdir(parents=True)
        shell = binary_dir / "bash"
        shell.write_text(f"#!{real_shell}\nprintf 'used prefix shell' > shell-marker\nexec {shlex.quote(real_shell)} \"$@\"\n")
        shell.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(binary_dir), "PREFIX": str(prefix)}):
            result = await self.runner.run("printf termux-ok")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output, "termux-ok")
        self.assertEqual((self.root / "shell-marker").read_text(), "used prefix shell")

    async def test_android_platform_accepts_termux_commands(self):
        with patch.object(shell_commands.sys, "platform", "android"):
            result = await self.runner.run("printf android-ok")
        self.assertEqual(result.output, "android-ok")
        self.assertEqual(result.returncode, 0)

    async def test_sh_is_used_when_bash_is_unavailable(self):
        real_shell = shutil.which("sh")
        with patch.object(shell_commands.shutil, "which", side_effect=[None, real_shell]) as which:
            result = await self.runner.run("printf sh-ok")
        self.assertEqual(result.output, "sh-ok")
        self.assertEqual([call.args[0] for call in which.call_args_list], ["bash", "sh"])

    async def test_arguments_pipelines_and_shell_syntax_are_supported(self):
        result = await self.runner.run("printf '%s\\n' 'hello world' | tr 'a-z' 'A-Z'")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.output, "HELLO WORLD")

    async def test_stderr_and_exit_status_are_returned(self):
        result = await self.runner.run("printf 'error detail' >&2; exit 7")
        self.assertEqual(result.returncode, 7)
        self.assertIn("error detail", result.output)

    async def test_missing_commands_return_shell_error_output(self):
        result = await self.runner.run("tg_name_nonexistent_command_for_test")
        self.assertEqual(result.returncode, 127)
        self.assertIn("tg_name_nonexistent_command_for_test", result.output)

    async def test_stdin_is_closed_for_noninteractive_commands(self):
        result = await self.runner.run("read value; printf 'read status: %s' \"$?\"")
        self.assertEqual(result.output, "read status: 1")
        self.assertFalse(result.timed_out)

    @unittest.skipUnless(shutil.which("uptime"), "uptime installed")
    async def test_literal_braced_uptime_example_runs(self):
        result = await self.runner.run("{uptime}")
        self.assertEqual(result.command, "uptime")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.output)

    async def test_sensitive_environment_variables_are_removed(self):
        with patch.dict(os.environ, {"BOT_TOKEN": "private-bot-token", "CUSTOM_SECRET": "private-secret"}):
            result = await self.runner.run("printf '%s:%s' \"$BOT_TOKEN\" \"$CUSTOM_SECRET\"")
        self.assertEqual(result.output, ":")

    async def test_known_secrets_in_files_are_redacted(self):
        (self.root / ".env").write_text("BOT_TOKEN=private-bot-token\n")
        result = await self.runner.run("cat .env", secret_values=["private-bot-token"])
        self.assertNotIn("private-bot-token", result.output)
        self.assertIn("[REDACTED]", result.output)

    async def test_secrets_are_also_redacted_in_command_display(self):
        secret = "private-api-value"
        result = await self.runner.run(f"printf %s {shlex.quote(secret)}", secret_values=[secret])
        self.assertNotIn(secret, result.command + result.output)

    async def test_timeout_kills_the_command_and_releases_lock(self):
        self.runner.timeout = 0.05
        result = await self.runner.run(f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(30)'")
        self.assertTrue(result.timed_out)
        self.assertLess(result.returncode, 0)
        self.assertFalse(self.runner._lock.locked())

    async def test_timeout_kills_children_as_well_as_the_shell(self):
        self.runner.timeout = 0.2
        script = "import time; from pathlib import Path; time.sleep(0.5); Path('child-survived').touch()"
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)} & wait"
        result = await self.runner.run(command)
        self.assertTrue(result.timed_out)
        await asyncio.sleep(0.6)
        self.assertFalse((self.root / "child-survived").exists())

    @unittest.skipUnless(shutil.which("yes"), "yes installed")
    async def test_output_limit_stops_unbounded_output(self):
        self.runner.max_output = 256
        result = await self.runner.run("yes output")
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.output.encode()), 256)

    async def test_cancellation_cleans_up_and_allows_the_next_command(self):
        started = asyncio.Event()
        create_process = asyncio.create_subprocess_exec
        processes = []

        async def create(*args, **kwargs):
            process = await create_process(*args, **kwargs)
            processes.append(process)
            started.set()
            return process

        with patch.object(shell_commands.asyncio, "create_subprocess_exec", side_effect=create):
            task = asyncio.create_task(self.runner.run(f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(30)'"))
            await started.wait()
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertLess(processes[0].returncode, 0)
        self.assertFalse(self.runner._lock.locked())
        self.assertEqual((await self.runner.run("printf ok")).output, "ok")

    async def test_second_command_is_rejected_while_busy(self):
        async with self.runner._lock:
            with self.assertRaises(ShellError) as error:
                await self.runner.run("uptime")
        self.assertEqual(error.exception.key, "shell_busy")

    async def test_terminal_color_escape_sequences_are_removed(self):
        result = await self.runner.run("printf '\\033[31mred\\033[0m'")
        self.assertEqual(result.output, "red")


class ShellFormattingTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_linux_never_spawns_a_process(self):
        runner = ShellRunner()
        with patch.object(shell_commands.sys, "platform", "win32"):
            with patch.object(shell_commands.asyncio, "create_subprocess_exec", new=AsyncMock()) as create:
                with self.assertRaises(ShellError) as error:
                    await runner.run("uptime")
        self.assertEqual(error.exception.key, "shell_linux_only")
        create.assert_not_awaited()

    async def test_missing_shell_is_reported_without_spawning(self):
        runner = ShellRunner()
        with patch.object(shell_commands.sys, "platform", "android"):
            with patch.object(shell_commands.shutil, "which", return_value=None):
                with patch.object(shell_commands.asyncio, "create_subprocess_exec", new=AsyncMock()) as create:
                    with self.assertRaises(ShellError) as error:
                        await runner.run("ls")
        self.assertEqual(error.exception.key, "shell_missing_shell")
        self.assertFalse(runner._lock.locked())
        create.assert_not_awaited()

    async def test_invalid_or_empty_commands_are_rejected(self):
        for value in ("", " ", "{}", "a" * 4097, "echo\0x"):
            with self.assertRaises(ShellError):
                ShellRunner.normalize(value)

    async def test_html_and_non_bmp_output_fit_in_telegram(self):
        result = ShellResult("echo <tag> & test", "🎲<&>" * 10000, 0, timed_out=True, truncated=True)
        text = format_shell_result(result)
        self.assertLess(len(text.encode("utf-16-le")) // 2, 3500)
        self.assertIn("&lt;tag&gt;", text)
        self.assertNotIn("<tag>", text)
        self.assertIn("30 giây", text)

    async def test_html_clipping_does_not_split_entities(self):
        text, clipped = clipped_html("<" * 100, 5)
        self.assertTrue(clipped)
        self.assertEqual(text, "&lt;…")

    async def test_common_token_and_private_key_patterns_are_redacted(self):
        github = "gh" + "p_" + "a" * 36
        telegram = "123456789:" + "b" * 35
        private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nprivate data\n-----END OPENSSH PRIVATE KEY-----"
        redacted = shell_commands.redact(github + "\n" + telegram + "\n" + private_key, [])
        for value in (github, telegram, "private data"):
            self.assertNotIn(value, redacted)

    async def test_empty_output_has_a_readable_placeholder(self):
        self.assertIn("không có output", format_shell_result(ShellResult("true", "", 0)))


if __name__ == "__main__":
    unittest.main()
