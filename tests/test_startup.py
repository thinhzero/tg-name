import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import name
import startup


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-startup-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "requirements.txt").write_text("telethon>=1.36.0\n")
        for patcher in (
            patch.object(startup, "PROJECT_DIR", self.root),
            patch.object(startup.sys, "prefix", str(self.root / "active-env")),
            patch.object(startup.sys, "base_prefix", str(self.root / "system-python")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_ready_environment_does_not_run_pip(self):
        with patch.object(startup, "missing_dependencies", return_value=[]):
            with patch.object(startup.subprocess, "run") as run:
                self.assertTrue(startup.ensure_dependencies())
        run.assert_not_called()

    def test_missing_libraries_are_installed_in_current_virtualenv(self):
        with patch.object(startup, "missing_dependencies", side_effect=[["Telethon"], []]):
            with patch.object(startup.importlib.util, "find_spec", return_value=object()):
                with patch.object(startup.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                    self.assertTrue(startup.ensure_dependencies())
        self.assertEqual(run.call_args.args[0][:4], [sys.executable, "-m", "pip", "install"])
        self.assertEqual(run.call_args.args[0][-1], str(self.root / "requirements.txt"))
        self.assertNotIn("--break-system-packages", run.call_args.args[0])

    def test_missing_pip_is_bootstrapped_first(self):
        with patch.object(startup, "missing_dependencies", side_effect=[["Telethon"], []]):
            with patch.object(startup.importlib.util, "find_spec", return_value=None):
                with patch.object(startup.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                    self.assertTrue(startup.ensure_dependencies())
        self.assertEqual(run.call_args_list[0].args[0], [sys.executable, "-m", "ensurepip", "--upgrade"])
        self.assertEqual(len(run.call_args_list), 2)

    def test_pip_failure_stops_startup(self):
        with patch.object(startup, "missing_dependencies", return_value=["Telethon"]):
            with patch.object(startup.importlib.util, "find_spec", return_value=object()):
                with patch.object(startup.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
                    self.assertFalse(startup.ensure_dependencies())

    def test_system_python_creates_venv_then_execs_without_installing_globally(self):
        with patch.object(startup.sys, "prefix", startup.sys.base_prefix):
            with patch.object(startup.sys, "orig_argv", ["python", "-u", "name.py"], create=True):
                with patch.object(startup, "missing_dependencies", return_value=["Telethon"]):
                    with patch.object(startup.venv, "EnvBuilder") as builder:
                        with patch.object(startup.os, "execv") as execute:
                            with patch.object(startup.subprocess, "run") as run:
                                startup.ensure_dependencies()
        builder.assert_called_once_with(with_pip=True)
        builder.return_value.create.assert_called_once_with(self.root / ".venv")
        python = str(self.root / ".venv" / "bin" / "python")
        execute.assert_called_once_with(python, [python, "-u", "name.py"])
        run.assert_not_called()

    def test_existing_non_venv_directory_is_not_overwritten(self):
        environment = self.root / ".venv"
        environment.mkdir()
        (environment / "notes.txt").write_text("user work")
        with patch.object(startup.sys, "prefix", startup.sys.base_prefix):
            with patch.object(startup, "missing_dependencies", return_value=["Telethon"]):
                with patch.object(startup.venv, "EnvBuilder") as builder:
                    self.assertFalse(startup.ensure_dependencies())
        builder.assert_not_called()
        self.assertEqual((environment / "notes.txt").read_text(), "user work")

    def test_pip_timeout_is_reported_without_running_the_app(self):
        with patch.object(startup, "missing_dependencies", return_value=["Telethon"]):
            with patch.object(startup.importlib.util, "find_spec", return_value=object()):
                with patch.object(startup.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 600)):
                    self.assertFalse(startup.ensure_dependencies())

    def test_missing_requirements_does_not_guess_install_commands(self):
        (self.root / "requirements.txt").unlink()
        with patch.object(startup, "missing_dependencies", return_value=["Telethon"]):
            with patch.object(startup.subprocess, "run") as run:
                self.assertFalse(startup.ensure_dependencies())
        run.assert_not_called()

    def test_name_module_can_be_imported_with_site_packages_disabled(self):
        result = subprocess.run([
            sys.executable, "-S", "-c",
            "import name, sys; assert 'telethon' not in sys.modules; assert 'dotenv' not in sys.modules; print('stdlib only')",
        ], cwd=Path(__file__).resolve().parent.parent, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stdlib only", result.stdout)


class OneCommandEntryTests(unittest.TestCase):
    def test_configured_bot_never_prompts(self):
        state = SimpleNamespace(config={"BOT_TOKEN": "fake-bot-token", "ADMIN_ID": "42"}, update_config=Mock())
        with patch.object(name, "getpass") as getpass:
            self.assertTrue(name.prepare_bot_config(state))
        getpass.assert_not_called()
        state.update_config.assert_not_called()

    def test_first_run_only_prompts_for_token_and_admin(self):
        state = SimpleNamespace(config={}, update_config=Mock())
        with patch.object(name.sys.stdin, "isatty", return_value=True):
            with patch.object(name, "getpass", return_value="fake-bot-token"):
                with patch("builtins.input", return_value="42"):
                    self.assertTrue(name.prepare_bot_config(state))
        state.update_config.assert_called_once_with({"BOT_TOKEN": "fake-bot-token", "ADMIN_ID": "42"})

    def test_noninteractive_launch_requires_preconfigured_values(self):
        state = SimpleNamespace(config={}, update_config=Mock())
        with patch.object(name.sys.stdin, "isatty", return_value=False):
            self.assertFalse(name.prepare_bot_config(state))
        state.update_config.assert_not_called()

    def test_userbot_without_bot_token_remains_supported(self):
        state = SimpleNamespace(config={"API_ID": "123", "SESSION_STRING": "private-session"}, update_config=Mock())
        self.assertTrue(name.prepare_bot_config(state))
        state.update_config.assert_not_called()

    def test_dependencies_are_checked_before_starting_runtime(self):
        import bot_updater
        order = []
        with patch.object(name, "ensure_dependencies", side_effect=lambda: order.append("deps") or True):
            with patch.object(bot_updater, "run_with_restart", side_effect=lambda main: order.append("run")):
                self.assertEqual(name.launch(), 0)
        self.assertEqual(order, ["deps", "run"])

    def test_failed_dependency_setup_does_not_launch(self):
        import bot_updater
        with patch.object(name, "ensure_dependencies", return_value=False):
            with patch.object(bot_updater, "run_with_restart") as run:
                self.assertEqual(name.launch(), 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
