import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot_updater
from bot_updater import BotUpdater, UpdateError


class BotUpdaterTests(unittest.IsolatedAsyncioTestCase):
    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git(self.remote, "add", ".")
        self.git(self.remote, "commit", "-qm", message)
        return self.git(self.remote, "rev-parse", "HEAD")

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-test-")
        self.addCleanup(self.temp.cleanup)
        self.remote = Path(self.temp.name) / "remote"
        self.local = Path(self.temp.name) / "local"
        self.remote.mkdir()
        self.git(self.remote, "init", "-q", "-b", "main")
        self.git(self.remote, "config", "user.name", "Test")
        self.git(self.remote, "config", "user.email", "test@example.com")
        (self.remote / "name.py").write_text("VERSION = 1\n")
        (self.remote / ".gitignore").write_text(".env\n*.session\n.venv/\nname.txt\n")
        self.initial = self.commit("Initial")
        self.git(self.remote, "clone", "-q", str(self.remote), str(self.local))
        self.updater = BotUpdater(self.local)
        self.progress = AsyncMock()
        patcher = patch.object(bot_updater, "REPO_URL", str(self.remote))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_no_update_does_not_clone_or_restart(self):
        result = await self.updater.update(self.progress)
        self.assertFalse(result.updated)
        self.assertEqual(result.current, self.initial)
        self.progress.assert_not_awaited()
        self.assertFalse(self.updater.restart_event.is_set())

    async def test_update_preserves_config_sessions_and_origin(self):
        (self.local / ".env").write_text("BOT_TOKEN=secret\n")
        (self.local / "helper_bot.session").write_bytes(b"session")
        (self.local / "name.txt").write_text("eat29\nsleep\n")
        (self.local / "notes.txt").write_text("local notes")
        (self.remote / "name.py").write_text("VERSION = 2\n")
        latest = self.commit("Update")

        result = await self.updater.update(self.progress)

        self.assertTrue(result.updated)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), latest)
        self.assertEqual((self.local / ".env").read_text(), "BOT_TOKEN=secret\n")
        self.assertEqual((self.local / "helper_bot.session").read_bytes(), b"session")
        self.assertEqual((self.local / "name.txt").read_text(), "eat29\nsleep\n")
        self.assertEqual((self.local / "notes.txt").read_text(), "local notes")
        self.assertEqual(self.git(self.local, "remote", "get-url", "origin"), str(self.remote))
        self.assertFalse(self.updater.restart_event.is_set())
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_busy")
        self.updater.request_restart()
        self.assertTrue(self.updater.restart_event.is_set())

    async def test_dirty_source_is_not_overwritten(self):
        (self.remote / "name.py").write_text("VERSION = 2\n")
        self.commit("Update")
        (self.local / "name.py").write_text("LOCAL = True\n")
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_dirty")
        self.assertEqual((self.local / "name.py").read_text(), "LOCAL = True\n")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)

    async def test_local_commits_are_not_discarded(self):
        self.git(self.local, "config", "user.name", "Test")
        self.git(self.local, "config", "user.email", "test@example.com")
        (self.local / "local.py").write_text("LOCAL = True\n")
        self.git(self.local, "add", ".")
        self.git(self.local, "commit", "-qm", "Local commit")
        current = self.git(self.local, "rev-parse", "HEAD")
        (self.remote / "name.py").write_text("VERSION = 2\n")
        self.commit("Upstream update")
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_diverged")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), current)

    async def test_invalid_python_leaves_running_code_untouched(self):
        (self.remote / "name.py").write_text("def broken(:\n")
        self.commit("Broken update")
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_invalid_source")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)
        self.assertFalse(self.updater.restart_event.is_set())

    async def test_untracked_collision_is_not_overwritten(self):
        (self.local / "new.py").write_text("LOCAL = True\n")
        (self.remote / "new.py").write_text("UPSTREAM = True\n")
        self.commit("New file")
        with self.assertRaises(UpdateError):
            await self.updater.update(self.progress)
        self.assertEqual((self.local / "new.py").read_text(), "LOCAL = True\n")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)

    async def test_ignored_collision_is_not_overwritten(self):
        (self.local / ".venv").mkdir()
        (self.local / ".venv" / "config.txt").write_text("local environment")
        (self.remote / ".venv").mkdir()
        (self.remote / ".venv" / "config.txt").write_text("upstream")
        self.git(self.remote, "add", "-f", ".venv/config.txt")
        self.commit("Ignored collision")
        with self.assertRaises(UpdateError):
            await self.updater.update(self.progress)
        self.assertEqual((self.local / ".venv" / "config.txt").read_text(), "local environment")

    async def test_upstream_cannot_replace_credentials(self):
        (self.remote / ".env").write_text("BOT_TOKEN=upstream\n")
        self.git(self.remote, "add", "-f", ".env")
        self.commit("Unsafe update")
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_unsafe_file")
        self.assertFalse((self.local / ".env").exists())

    async def test_dependencies_are_installed_before_merge(self):
        (self.remote / "requirements.txt").write_text("example-package==1.0\n")
        latest = self.commit("Dependencies")
        original_run = self.updater._run
        pip_calls = []

        async def run(*command, **kwargs):
            if command[0] != "git":
                pip_calls.append(command)
                self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)
                return subprocess.CompletedProcess(command, 0, stdout="Installed")
            return await original_run(*command, **kwargs)

        with patch.object(self.updater, "_run", side_effect=run):
            await self.updater.update(self.progress)
        self.assertEqual(len(pip_calls), 1)
        self.assertEqual(pip_calls[0][:4], (bot_updater.sys.executable, "-m", "pip", "install"))
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), latest)

    async def test_upstream_cannot_replace_personal_random_names(self):
        (self.remote / "name.txt").write_text("upstream data\n")
        self.git(self.remote, "add", "-f", "name.txt")
        self.commit("Unsafe random names")
        with self.assertRaises(UpdateError) as error:
            await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_unsafe_file")
        self.assertFalse((self.local / "name.txt").exists())

    async def test_failed_dependency_install_does_not_merge(self):
        (self.remote / "requirements.txt").write_text("example-package==1.0\n")
        self.commit("Dependencies")
        original_run = self.updater._run

        async def run(*command, **kwargs):
            if command[0] != "git":
                raise UpdateError("self_update_command_failed", details="pip failed")
            return await original_run(*command, **kwargs)

        with patch.object(self.updater, "_run", side_effect=run):
            with self.assertRaises(UpdateError):
                await self.updater.update(self.progress)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)
        self.assertFalse(self.updater._restart_pending)

    async def test_not_git_checkout_is_rejected(self):
        updater = BotUpdater(self.temp.name)
        with self.assertRaises(UpdateError) as error:
            await updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_not_git")
        self.assertEqual(error.exception.details["directory"], str(Path(self.temp.name).resolve()))

    async def test_inherited_git_directory_cannot_redirect_the_updater(self):
        (self.remote / "name.py").write_text("VERSION = 2\n")
        latest = self.commit("Update")
        environment = {
            "GIT_DIR": str(self.remote / ".git"), "GIT_WORK_TREE": str(self.remote),
            "GIT_INDEX_FILE": str(self.remote / ".git" / "index"),
            "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true",
            "GIT_TRACE": "1",
        }
        with patch.dict(os.environ, environment):
            result = await self.updater.update(self.progress)
        self.assertTrue(result.updated)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), latest)
        self.assertEqual((self.local / "name.py").read_text(), "VERSION = 2\n")
        self.assertEqual(self.git(self.remote, "rev-parse", "HEAD"), latest)

    async def test_git_warnings_do_not_become_part_of_repository_paths(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(str(self.local).encode(), b"warning: optional Git warning\n")),
        )
        with patch.object(bot_updater.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)):
            await self.updater._check_checkout()

    async def test_git_preserves_termux_runtime_environment(self):
        process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"ok", b"")))
        environment = {
            "PREFIX": "/data/data/com.termux/files/usr",
            "LD_PRELOAD": "/data/data/com.termux/files/usr/lib/libtermux-exec.so",
            "GIT_EXEC_PATH": "/data/data/com.termux/files/usr/libexec/git-core",
            "GIT_DIR": "/wrong/repository/.git",
        }
        with patch.dict(os.environ, environment):
            with patch.object(bot_updater.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)) as create:
                await self.updater._git("rev-parse", "HEAD")
        env = create.call_args.kwargs["env"]
        for key in ("PREFIX", "LD_PRELOAD", "GIT_EXEC_PATH"):
            self.assertEqual(env[key], environment[key])
        self.assertNotIn("GIT_DIR", env)
        self.assertEqual(env["LC_ALL"], "C")

    async def test_dubious_ownership_is_not_reported_as_a_missing_clone(self):
        result = subprocess.CompletedProcess(
            ("git",), 128, stdout="", stderr="fatal: detected dubious ownership in repository",
        )
        with patch.object(self.updater, "_git", new=AsyncMock(return_value=result)) as git:
            with self.assertRaises(UpdateError) as error:
                await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_git_ownership")
        self.assertEqual(error.exception.details["directory"], str(self.local.resolve()))
        git.assert_awaited_once_with("rev-parse", "--show-toplevel", allowed_codes=(0, 128))

    async def test_other_git_errors_are_not_reported_as_a_missing_clone(self):
        result = subprocess.CompletedProcess(("git",), 128, stdout="", stderr="fatal: permission denied")
        with patch.object(self.updater, "_git", new=AsyncMock(return_value=result)):
            with self.assertRaises(UpdateError) as error:
                await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_command_failed")
        self.assertIn("permission denied", error.exception.details["details"])

    async def test_parent_repository_is_not_updated_by_mistake(self):
        nested = self.local / "nested-bot"
        nested.mkdir()
        updater = BotUpdater(nested)
        with self.assertRaises(UpdateError) as error:
            await updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_wrong_directory")
        self.assertEqual(error.exception.details["root"], str(self.local.resolve()))
        self.assertEqual(error.exception.details["directory"], str(nested.resolve()))
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)

    async def test_linked_git_worktree_is_supported(self):
        linked = Path(self.temp.name) / "linked"
        self.git(self.local, "worktree", "add", "--detach", str(linked), self.initial)
        self.assertTrue((linked / ".git").is_file())
        (self.remote / "name.py").write_text("VERSION = 2\n")
        latest = self.commit("Worktree update")
        result = await BotUpdater(linked).update(self.progress)
        self.assertTrue(result.updated)
        self.assertEqual(self.git(linked, "rev-parse", "HEAD"), latest)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)

    async def test_symlinked_checkout_is_supported(self):
        linked = Path(self.temp.name) / "linked-bot"
        linked.symlink_to(self.local, target_is_directory=True)
        result = await BotUpdater(linked).update(self.progress)
        self.assertFalse(result.updated)

    async def test_successful_subprocess_keeps_stdout_and_stderr_separate(self):
        result = await self.updater._run(
            bot_updater.sys.executable, "-c", "import sys; print('result'); print('warning', file=sys.stderr)",
        )
        self.assertEqual(result.stdout, "result")
        self.assertEqual(result.stderr, "warning")

    async def test_missing_git_is_reported(self):
        with patch("bot_updater.shutil.which", return_value=None):
            with self.assertRaises(UpdateError) as error:
                await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_missing_git")

    async def test_concurrent_update_is_rejected(self):
        async with self.updater._lock:
            with self.assertRaises(UpdateError) as error:
                await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_busy")

    async def test_source_changed_during_download_is_not_overwritten(self):
        (self.remote / "name.py").write_text("VERSION = 2\n")
        self.commit("Update")

        async def progress(key):
            if key == "self_update_validating":
                (self.local / "name.py").write_text("LOCAL = True\n")

        with self.assertRaises(UpdateError) as error:
            await self.updater.update(progress)
        self.assertEqual(error.exception.key, "self_update_dirty")
        self.assertEqual((self.local / "name.py").read_text(), "LOCAL = True\n")

    async def test_failed_network_does_not_restart(self):
        with patch.object(bot_updater, "REPO_URL", str(self.remote / "missing")):
            with self.assertRaises(UpdateError) as error:
                await self.updater.update(self.progress)
        self.assertEqual(error.exception.key, "self_update_command_failed")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), self.initial)
        self.assertFalse(self.updater.restart_event.is_set())
        # Khóa được nhả để có thể thử lại sau lỗi.
        self.assertFalse((await self.updater.update(self.progress)).updated)

    async def test_subprocess_timeout_is_reported(self):
        with self.assertRaises(UpdateError) as error:
            await self.updater._run(bot_updater.sys.executable, "-c", "import time; time.sleep(10)", timeout=0.05)
        self.assertEqual(error.exception.key, "self_update_timeout")


class RestartTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_waits_for_cleanup(self):
        updater = BotUpdater()
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def main():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        with patch.object(bot_updater, "bot_updater", updater):
            task = asyncio.create_task(bot_updater._run_until_restart(main))
            await started.wait()
            updater.request_restart()
            self.assertTrue(await task)
        self.assertTrue(cleaned.is_set())

    async def test_normal_exit_does_not_restart(self):
        with patch.object(bot_updater, "bot_updater", BotUpdater()):
            self.assertFalse(await bot_updater._run_until_restart(AsyncMock()))

    async def test_main_failure_is_not_hidden(self):
        with patch.object(bot_updater, "bot_updater", BotUpdater()):
            with self.assertRaisesRegex(RuntimeError, "failure"):
                await bot_updater._run_until_restart(AsyncMock(side_effect=RuntimeError("failure")))


class RestartEntrypointTests(unittest.TestCase):
    def test_exec_uses_same_python_and_preserves_interpreter_flags(self):
        original = ["python3", "-u", "name.py"]
        with patch.object(bot_updater.sys, "orig_argv", original, create=True):
            with patch.object(bot_updater, "_run_until_restart", new=AsyncMock(return_value=True)):
                with patch.object(bot_updater.os, "execv") as execv:
                    bot_updater.run_with_restart(AsyncMock())
        execv.assert_called_once_with(bot_updater.sys.executable, [bot_updater.sys.executable, "-u", "name.py"])


if __name__ == "__main__":
    unittest.main()
