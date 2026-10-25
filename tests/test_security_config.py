import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parent.parent
HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class RepositoryHygieneTests(unittest.TestCase):
    def test_every_example_env_value_is_empty(self):
        assignments = [line for line in (ROOT / ".env.example").read_text().splitlines() if line and not line.startswith("#")]
        self.assertGreater(len(assignments), 10)
        for line in assignments:
            key, value = line.split("=", 1)
            self.assertEqual(value.strip(), "", key)

    def test_runtime_files_and_env_backups_are_ignored(self):
        paths = [".env", ".env.backup", ".env.production", "name.txt", "bot.session", "bot.session-wal", ".venv/pyvenv.cfg", "__pycache__/cache.pyc"]
        result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT, input="\n".join(paths), text=True, capture_output=True)
        self.assertEqual(set(result.stdout.splitlines()), set(paths))
        result = subprocess.run(["git", "check-ignore", "--no-index", ".env.example"], cwd=ROOT, capture_output=True)
        self.assertNotEqual(result.returncode, 0)


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử cấu hình/bảo mật")
class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        import updater_state
        import setup
        self.module = updater_state
        self.setup_module = setup
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-security-test-")
        self.addCleanup(self.temp.cleanup)
        self.env = Path(self.temp.name) / ".env"
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(updater_state, "ENV_FILE", str(self.env)),
            patch.object(setup, "ENV_FILE", str(self.env)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_empty_env_uses_only_non_secret_defaults(self):
        self.env.write_text((ROOT / ".env.example").read_text())
        state = self.module.UpdaterState()
        for key in ("API_ID", "API_HASH", "BOT_TOKEN", "SESSION_STRING", "ADMIN_ID", "LASTFM_API_KEY", "WEATHER_API"):
            self.assertEqual(state.config[key], "", key)
        self.assertEqual(state.config["TIMEZONE"], "Asia/Ho_Chi_Minh")
        self.assertEqual(state.config["NAME_FORMAT"], self.module.DEFAULT_NAME_FORMAT)
        self.assertEqual(state.config["SESSION_NAME"], "bot")

    def test_setup_and_runtime_agree_on_blank_optional_values(self):
        self.env.write_text((ROOT / ".env.example").read_text())
        config = self.setup_module.load_env()
        state = self.module.UpdaterState()
        for key, value in self.setup_module.DEFAULT_CONFIG.items():
            self.assertEqual(config[key], value, key)
            self.assertEqual(config[key], state.config[key], key)

    def test_user_values_override_defaults_and_multiline_survives(self):
        state = self.module.UpdaterState()
        state.update_config({"API_ID": "123", "API_HASH": "private-api-hash", "BIO_FORMAT": "line1\nline2 # text", "TIMEZONE": "UTC"})
        self.assertEqual(state.config["API_HASH"], "private-api-hash")
        self.assertEqual(state.config["BIO_FORMAT"], "line1\nline2 # text")
        self.assertEqual(state.config["TIMEZONE"], "UTC")

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions")
    def test_runtime_and_setup_make_env_private(self):
        state = self.module.UpdaterState()
        state.update_config({"API_HASH": "private-api-hash"})
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        self.env.chmod(0o644)
        self.setup_module.save_env({"API_HASH": "another-private-hash"})
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử bảo mật Telegram")
class HelperSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        import profile_engine
        self.helper = helper_bot
        self.profile = profile_engine
        patcher = patch.dict(helper_bot.state.config, {"API_ID": "123", "API_HASH": "private-api-hash", "ADMIN_ID": "42", "BOT_TOKEN": "fake-bot-token"})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_unconfigured_admin_never_claims_the_bot(self):
        self.helper.state.config["ADMIN_ID"] = ""
        with patch.object(self.helper.state, "update_config") as update:
            self.assertFalse(self.helper.is_admin(99))
        update.assert_not_called()

    async def test_helper_will_not_connect_without_explicit_admin(self):
        self.helper.state.config["ADMIN_ID"] = ""
        with patch.object(self.helper.state, "reload_config"):
            with patch.object(self.helper, "TelegramClient") as client:
                await self.helper.run_standalone_bot()
        client.assert_not_called()

    async def test_no_shared_api_fallback_for_helper_or_engine(self):
        self.helper.state.config.update({"API_ID": "", "API_HASH": ""})
        with patch.object(self.helper.state, "reload_config"):
            with patch.object(self.helper, "TelegramClient") as client:
                with patch.object(self.helper, "run_api_setup", new=AsyncMock(return_value=False)) as setup:
                    await self.helper.run_standalone_bot()
                setup.assert_awaited_once_with("fake-bot-token", "42")
            ok, message = await self.profile.ProfileEngine().start()
        client.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("API_ID/API_HASH", message)

    async def test_settings_never_echo_api_hash(self):
        for lang in ("vi", "en"):
            message = self.helper.format_settings_text(lang)
            self.assertNotIn("private-api-hash", message)
            self.assertNotIn("private-", message)

    async def test_private_chat_guard_blocks_groups(self):
        class Client:
            def __init__(self):
                self.handlers = {}

            def on(self, builder):
                def register(handler):
                    self.handlers[handler.__name__] = handler
                    return handler
                return register

        client = Client()
        self.helper.register_bot_handlers(client)
        guard = client.handlers["private_chat_only"]
        with self.assertRaises(self.helper.events.StopPropagation):
            await guard(SimpleNamespace(is_private=False))
        await guard(SimpleNamespace(is_private=True))

    async def test_lastfm_without_key_does_not_use_a_shared_one(self):
        with patch.object(self.helper.urllib.request, "urlopen") as urlopen:
            ok, message = self.helper.test_lastfm_user_sync("username")
        self.assertFalse(ok)
        self.assertIn("LASTFM_API_KEY", message)
        urlopen.assert_not_called()
        with patch.object(self.profile.aiohttp, "ClientSession") as session:
            track = await self.profile.get_lastfm_track("username")
        session.assert_not_called()
        self.assertEqual(track["formatted"], "")

    async def test_openweather_key_is_only_sent_over_https(self):
        response = Mock(status=200)
        response.read.return_value = b'{"main": {"temp": 20}, "weather": [{"description": "clear"}]}'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(self.helper.urllib.request, "urlopen", return_value=context) as urlopen:
            self.helper.test_weather_api_sync("private-weather-key", "Hanoi")
        self.assertTrue(urlopen.call_args.args[0].full_url.startswith("https://"))

    async def test_help_is_short_and_explains_the_new_commands(self):
        for lang in ("vi", "en"):
            for helper in (False, True):
                message = self.helper.format_help(lang, helper)
                self.assertLess(len(message.encode("utf-16-le")) // 2, 3500)
                prefix = "/" if helper else "."
                for cmd in ("updaterandom", "lsrandom", "rmrandom", "updatecheck", "nameformat"):
                    self.assertIn(prefix + cmd, message)
                self.assertIn(self.helper.DEFAULT_NAME_FORMAT, message)


if __name__ == "__main__":
    unittest.main()
