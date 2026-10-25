import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = handler
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử reset")
class ResetStorageTests(unittest.TestCase):
    def setUp(self):
        import updater_state
        import reset_control
        self.module = updater_state
        self.reset = reset_control
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-reset-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = self.root / ".env"
        self.env.write_text('BOT_TOKEN="fake-bot-token"\nADMIN_ID="42"\nAPI_ID="123"\nAPI_HASH="old-private-hash"\nSESSION_STRING="old-session"\nOLD_TOKEN="old-token"\nTIMEZONE="UTC"\n')
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(updater_state, "ENV_FILE", str(self.env)),
            patch.object(reset_control, "pending_session_cleanup", set()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.state = updater_state.UpdaterState()

    def test_reset_keeps_exactly_two_keys_and_clears_cached_secrets(self):
        self.assertIn("OLD_TOKEN", os.environ)
        self.state.reset_config()
        values = self.module.dotenv_values(self.env)
        self.assertEqual(values, {"BOT_TOKEN": "fake-bot-token", "ADMIN_ID": "42"})
        for key in ("API_ID", "API_HASH", "SESSION_STRING", "OLD_TOKEN"):
            self.assertNotIn(key, os.environ)
        self.assertEqual(self.state.config["API_HASH"], "")
        self.assertEqual(self.state.config["TIMEZONE"], "Asia/Ho_Chi_Minh")
        self.assertNotIn("old-", self.env.read_text())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_keys_previously_loaded_from_env_are_also_cleared(self):
        self.env.write_text('BOT_TOKEN="fake-bot-token"\nADMIN_ID="42"\n')
        self.state.reload_config()
        self.assertIn("OLD_TOKEN", os.environ)
        self.state.reset_config()
        self.assertNotIn("OLD_TOKEN", os.environ)

    def test_failed_atomic_replace_keeps_old_config_and_removes_temp_file(self):
        old = self.env.read_bytes()
        with patch.object(self.module.os, "replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.state.reset_config()
        self.assertEqual(self.env.read_bytes(), old)
        self.assertEqual(os.environ["API_HASH"], "old-private-hash")
        self.assertEqual(list(self.root.glob(".env.reset-*")), [])

    def test_reset_without_valid_bot_identity_is_rejected(self):
        self.state.config["ADMIN_ID"] = ""
        old = self.env.read_bytes()
        with self.assertRaises(ValueError):
            self.state.reset_config()
        self.assertEqual(self.env.read_bytes(), old)

    def test_in_flight_configuration_writes_are_blocked_during_reset(self):
        self.state.is_resetting = True
        with self.assertRaises(RuntimeError):
            self.state.update_config({"API_HASH": "new-private-hash"})

    def test_confirmation_is_bound_to_user_single_use_and_expires(self):
        requests = self.reset.ResetRequests()
        with patch.object(self.reset.time, "monotonic", return_value=100):
            token = requests.create(42)
            self.assertFalse(requests.consume(99, token))
            self.assertFalse(requests.consume(42, "wrong"))
            self.assertTrue(requests.consume(42, token))
            self.assertFalse(requests.consume(42, token))
            expired = requests.create(42)
        with patch.object(self.reset.time, "monotonic", return_value=401):
            self.assertFalse(requests.consume(42, expired))

    def test_only_recognized_in_repo_session_files_are_removed(self):
        for name in ("bot.session", "helper_bot_session.session", "custom.session", "custom.session-wal", "other.session", "name.txt"):
            (self.root / name).write_text("local data")
        self.reset.pending_session_cleanup.update(self.reset.session_files("custom", self.root))
        self.assertEqual(self.reset.cleanup_reset_sessions(), [])
        for name in ("bot.session", "helper_bot_session.session", "custom.session", "custom.session-wal"):
            self.assertFalse((self.root / name).exists())
        self.assertTrue((self.root / "other.session").exists())
        self.assertTrue((self.root / "name.txt").exists())

    def test_outside_and_symlink_sessions_are_not_deleted(self):
        outside = self.root / "outside"
        outside.mkdir()
        repo = self.root / "repo"
        repo.mkdir()
        target = outside / "private.session"
        target.write_text("private data")
        link = repo / "bot.session"
        link.symlink_to(target)
        paths = self.reset.session_files(str(target), repo)
        self.assertNotIn(target, paths)
        self.assertNotIn(link, paths)
        self.reset.pending_session_cleanup.update(paths)
        self.reset.cleanup_reset_sessions()
        self.assertEqual(target.read_text(), "private data")
        self.assertTrue(link.is_symlink())


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử nút settings/reset")
class ResetAndSettingsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        import updater_state
        import reset_control
        from random_names import RandomNames
        self.helper = helper_bot
        self.reset = reset_control
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-reset-handler-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = self.root / ".env"
        self.env.write_text('BOT_TOKEN="fake-bot-token"\nADMIN_ID="42"\nAPI_ID="123"\nAPI_HASH="private-hash"\nSESSION_STRING="private-session"\n')
        for patcher in (patch.dict(os.environ, {}, clear=True), patch.object(updater_state, "ENV_FILE", str(self.env))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.state = updater_state.UpdaterState()
        self.engine = SimpleNamespace(is_running=True, start=AsyncMock(return_value=(True, "started")), stop=AsyncMock())
        self.updater = SimpleNamespace(is_busy=False, request_restart=Mock())
        self.names = RandomNames(self.root / "name.txt")
        session_files = reset_control.session_files
        for patcher in (
            patch.object(helper_bot, "state", self.state),
            patch.object(reset_control, "state", self.state),
            patch.object(helper_bot, "engine", self.engine),
            patch.object(helper_bot, "bot_updater", self.updater),
            patch.object(helper_bot, "random_names", self.names),
            patch.object(helper_bot, "generate_preview", return_value=("Preview", "Bio")),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.dict(reset_control.reset_requests.pending, {}, clear=True),
            patch.object(reset_control, "pending_session_cleanup", set()),
            patch.object(reset_control, "session_files", side_effect=lambda name: session_files(name, self.root)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = HandlerClient()
        helper_bot.register_bot_handlers(self.client)

    def event(self, data=None, sender_id=42, private=True, text=""):
        return SimpleNamespace(
            sender_id=sender_id, is_private=private, data=data.encode() if data else None, raw_text=text,
            reply=AsyncMock(), respond=AsyncMock(), edit=AsyncMock(), answer=AsyncMock(), delete=AsyncMock(),
        )

    async def request(self):
        event = self.event(text="/reset")
        await self.client.handlers["reset_cmd"](event)
        return self.reset.reset_requests.pending[42][0]

    async def test_reset_request_only_shows_confirmation(self):
        old = self.env.read_bytes()
        token = await self.request()
        self.assertTrue(token)
        self.assertEqual(self.env.read_bytes(), old)
        self.engine.stop.assert_not_awaited()
        self.updater.request_restart.assert_not_called()

    async def test_non_admin_and_group_reset_requests_are_rejected(self):
        for event in (self.event(sender_id=99), self.event(private=False)):
            await self.client.handlers["reset_cmd"](event)
            event.respond.assert_not_awaited()
        self.assertEqual(self.reset.reset_requests.pending, {})

    async def test_confirm_clears_config_after_stopping_engine_and_requests_restart(self):
        token = await self.request()
        self.names.add("keep this random")
        temp_client = SimpleNamespace(disconnect=AsyncMock())
        self.helper.user_sessions[42] = {"temp_client": temp_client}
        async def stop_runtime():
            with self.assertRaises(RuntimeError):
                self.state.update_config({"API_HASH": "late-write"})
        self.engine.stop.side_effect = stop_runtime
        event = self.event(f"reset_confirm:{token}")
        await self.client.handlers["callback_handler"](event)
        self.assertEqual(set(self.helper.state.config) >= {"BOT_TOKEN", "ADMIN_ID"}, True)
        self.assertEqual(self.env.read_text().count("\n"), 2)
        self.assertNotIn("API_HASH", self.env.read_text())
        temp_client.disconnect.assert_awaited_once()
        self.engine.stop.assert_awaited_once()
        self.updater.request_restart.assert_called_once()
        self.assertTrue(self.state.is_resetting)
        self.assertEqual(self.names.choose(), "keep this random")
        self.assertTrue(self.reset.pending_session_cleanup)

    async def test_reset_cancel_preserves_config(self):
        token = await self.request()
        old = self.env.read_bytes()
        await self.client.handlers["callback_handler"](self.event(f"reset_cancel:{token}"))
        self.assertEqual(self.env.read_bytes(), old)
        self.updater.request_restart.assert_not_called()

    async def test_forged_and_nonprivate_confirmation_cannot_reset(self):
        token = await self.request()
        old = self.env.read_bytes()
        await self.client.handlers["callback_handler"](self.event(f"reset_confirm:{token}", sender_id=99))
        await self.client.handlers["callback_handler"](self.event(f"reset_confirm:{token}", private=False))
        self.assertEqual(self.env.read_bytes(), old)
        self.updater.request_restart.assert_not_called()
        self.assertIn(42, self.reset.reset_requests.pending)

    async def test_stale_confirmation_and_update_in_progress_do_not_reset(self):
        old = self.env.read_bytes()
        await self.client.handlers["callback_handler"](self.event("reset_confirm:unknown"))
        self.updater.is_busy = True
        token = await self.request()
        await self.client.handlers["callback_handler"](self.event(f"reset_confirm:{token}"))
        self.assertEqual(self.env.read_bytes(), old)
        self.engine.stop.assert_not_awaited()

    async def test_failed_reset_does_not_restart_or_leave_reset_lock_enabled(self):
        token = await self.request()
        with patch.object(self.state, "reset_config", side_effect=PermissionError("denied")):
            await self.client.handlers["callback_handler"](self.event(f"reset_confirm:{token}"))
        self.assertFalse(self.state.is_resetting)
        self.updater.request_restart.assert_not_called()

    async def test_success_still_restarts_if_telegram_notification_fails(self):
        token = await self.request()
        event = self.event(f"reset_confirm:{token}")
        event.edit.side_effect = RuntimeError("disconnected")
        await self.client.handlers["callback_handler"](event)
        self.updater.request_restart.assert_called_once()

    async def test_settings_menu_buttons_open_their_inputs(self):
        data_values = {
            (getattr(button, "data", None) or button.type.data).decode()
            for row in self.helper.get_settings_keyboard() for button in row
        }
        self.assertTrue({"reset_request", "menu_random", "setup_lastfm_key", "setup_api_creds"} <= data_values)
        for data in ("menu_settings", "setup_name", "setup_city", "setup_weather", "setup_api_creds", "setup_timezone", "setup_format", "setup_lastfm", "setup_lastfm_key", "menu_random", "setup_random_add"):
            event = self.event(data)
            await self.client.handlers["callback_handler"](event)
            self.assertTrue(event.edit.await_count or event.respond.await_count, data)

    async def test_telethon_can_build_all_settings_and_confirmation_keyboards(self):
        for keyboard in (
            self.helper.get_settings_keyboard(), self.helper.get_setup_keyboard(),
            self.helper.get_reset_keyboard("test-confirmation"), self.helper.random_settings_panel()[1],
        ):
            markup = self.helper.TelegramClient.build_reply_markup(keyboard)
            self.assertTrue(markup.rows)

    async def test_random_add_and_delete_work_through_buttons(self):
        await self.client.handlers["callback_handler"](self.event("setup_random_add"))
        await self.client.handlers["user_input_handler"](self.event(text="eat29\nsleep"))
        entry = self.names.entries()[0]
        await self.client.handlers["callback_handler"](self.event(f"random_remove:{entry.uid}"))
        self.assertEqual(len(self.names.entries()), 2)
        await self.client.handlers["callback_handler"](self.event(f"random_confirm_remove:{entry.uid}"))
        self.assertEqual([entry.text for entry in self.names.entries()], ["sleep"])

    async def test_lastfm_key_input_is_saved_hidden_and_deleted(self):
        await self.client.handlers["callback_handler"](self.event("setup_lastfm_key"))
        event = self.event(text="a" * 32)
        await self.client.handlers["user_input_handler"](event)
        self.assertEqual(self.state.config["LASTFM_API_KEY"], "a" * 32)
        self.assertNotIn("a" * 32, str(event.reply.call_args_list))
        event.delete.assert_awaited_once()

    async def test_bootstrap_reset_uses_same_identity_and_confirmation(self):
        import bot_setup
        setup = bot_setup.BotAPISetup(Mock(), "fake-bot-token", "42")
        setup.call = AsyncMock(return_value={})
        with patch.object(bot_setup, "state", self.state):
            with patch.object(bot_setup, "bot_updater", self.updater):
                await setup.handle({"message": {"message_id": 1, "date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/reset"}})
                token = self.reset.reset_requests.pending[42][0]
                await setup.handle({"callback_query": {"id": "cb", "data": f"reset_confirm:{token}", "from": {"id": 42}, "message": {"chat": {"id": 42, "type": "private"}}}})
        self.assertEqual(self.env.read_text().count("\n"), 2)
        self.updater.request_restart.assert_called_once()

    async def test_session_files_are_removed_only_after_helper_disconnects(self):
        session_file = self.root / "helper_bot_session.session"
        session_file.write_text("old local session")
        token = self.reset.reset_requests.create(42)

        async def reset_during_runtime():
            await self.helper.confirm_reset(self.event(), token)

        async def disconnect():
            self.assertTrue(session_file.exists())

        client = SimpleNamespace(
            on=HandlerClient().on, start=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(username="TestBot", id=100)),
            send_message=AsyncMock(), run_until_disconnected=AsyncMock(side_effect=reset_during_runtime),
            disconnect=AsyncMock(side_effect=disconnect),
        )
        with patch.object(self.helper, "TelegramClient", return_value=client):
            await self.helper.run_standalone_bot()
        client.disconnect.assert_awaited_once()
        self.assertFalse(session_file.exists())
        self.assertEqual(self.env.read_text().count("\n"), 2)


if __name__ == "__main__":
    unittest.main()
