import asyncio
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot_updater import BotUpdater, UpdateResult, notify_update_completed
from update_completion import NOTICE_ENV, STATUS_DIR, UpdateCompletion


class UpdateCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-completion-")
        self.addCleanup(self.temp.cleanup)
        patcher = patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = Path(self.temp.name)
        self.completion = UpdateCompletion(self.root)
        self.result = UpdateResult("a" * 40, "b" * 40, updated=True, snapshot="snapshots/test")
        self.destination = {"owner_id": 42, "lang": "vi", "userbot": False}
        self.current = AsyncMock(return_value=self.result.latest)
        self.send = AsyncMock()

    def record(self, **destination):
        self.completion.record(self.result, {**self.destination, **destination})

    async def deliver(self, completion=None, **kwargs):
        return await (completion or self.completion).deliver(self.send, self.current, **{"owner_id": 42, **kwargs})

    def manifest(self, *, created=None, latest=None, name="test"):
        path = self.root / "snapshots" / name / "snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "from_commit": self.result.current, "to_commit": latest or self.result.latest,
            "created_at": (created or datetime.now(timezone.utc)).isoformat(),
            "files": [], "BOT_TOKEN": "must-not-copy-from-manifest",
        }))
        return path

    async def test_record_is_credential_free_and_does_not_send_before_restart(self):
        self.record(API_HASH="private-hash", BOT_TOKEN="private-token", SESSION_STRING="private-session")
        pending = self.root / STATUS_DIR / "pending.json"
        data = json.loads(pending.read_text())
        self.assertEqual(set(data), {"id", "current", "latest", "snapshot", "owner_id", "userbot", "lang"})
        self.assertNotIn("private-", pending.read_text() + os.environ[NOTICE_ENV])
        self.send.assert_not_awaited()
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(pending.stat().st_mode), 0o600)

    async def test_new_process_delivers_once_and_repeated_start_does_not_repeat(self):
        self.record()
        os.environ.pop(NOTICE_ENV)
        self.assertTrue(await self.deliver(UpdateCompletion(self.root)))
        self.assertIn("Đã cập nhật xong", self.send.call_args.args[0])
        self.assertIn("bbbbbbb", self.send.call_args.args[0])
        self.assertIn("snapshots/test", self.send.call_args.args[0])
        self.assertFalse((self.root / STATUS_DIR / "pending.json").exists())
        self.assertTrue((self.root / STATUS_DIR / "delivered.json").exists())
        self.assertFalse(await self.deliver(UpdateCompletion(self.root)))
        self.send.assert_awaited_once()

    async def test_environment_fallback_when_pending_write_fails(self):
        with patch.object(self.completion, "write", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.record()
        self.assertTrue(await self.deliver(UpdateCompletion(self.root)))
        self.assertNotIn(NOTICE_ENV, os.environ)

    async def test_wrong_commit_never_reports_success_and_keeps_receipt(self):
        self.record()
        self.current.return_value = self.result.current
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()
        self.assertTrue((self.root / STATUS_DIR / "pending.json").exists())
        self.current.return_value = self.result.latest
        self.assertTrue(await self.deliver())

    async def test_owner_and_transport_must_match(self):
        self.record()
        self.assertFalse(await self.deliver(owner_id=99))
        self.assertFalse(await self.deliver(userbot=True))
        self.current.assert_not_awaited()
        self.send.assert_not_awaited()
        self.assertTrue(await self.deliver())

    async def test_failed_send_is_retryable_without_logging_credentials(self):
        self.record()
        self.send.side_effect = ConnectionError("private-hash private-token")
        with patch("builtins.print") as output:
            self.assertFalse(await self.deliver())
        self.assertNotIn("private-", str(output.call_args_list))
        self.assertTrue((self.root / STATUS_DIR / "pending.json").exists())
        self.send.side_effect = None
        self.assertTrue(await self.deliver(UpdateCompletion(self.root)))
        self.assertEqual(self.send.await_count, 2)

    async def test_git_failure_does_not_acknowledge_receipt(self):
        self.record()
        self.current.side_effect = OSError("git unavailable")
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()
        self.current.side_effect = None
        self.assertTrue(await self.deliver())

    async def test_concurrent_start_and_startup_do_not_send_twice(self):
        self.record()
        results = await asyncio.gather(self.deliver(), self.deliver())
        self.assertEqual(results, [True, False])
        self.send.assert_awaited_once()

    async def test_english_and_userbot_routing(self):
        self.record(lang="en", userbot=True)
        self.assertTrue(await self.deliver(userbot=True))
        self.assertIn("Update completed", self.send.call_args.args[0])

    async def test_normal_start_without_update_has_no_notice_or_git_call(self):
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()
        self.current.assert_not_awaited()

    async def test_first_upgrade_from_legacy_updater_recovers_recent_snapshot(self):
        self.manifest()
        self.assertTrue(await self.deliver())
        self.assertFalse(await self.deliver(UpdateCompletion(self.root)))
        self.send.assert_awaited_once()
        self.assertNotIn("must-not-copy", self.send.call_args.args[0])

    async def test_failed_legacy_notification_is_persisted_for_later_retries(self):
        manifest = self.manifest()
        self.send.side_effect = ConnectionError("offline")
        self.assertFalse(await self.deliver())
        self.assertTrue((self.completion.directory / "pending.json").exists())
        os.environ.pop(NOTICE_ENV)
        manifest.unlink()  # recovery no longer depends on rediscovering the snapshot
        self.send.side_effect = None
        self.assertTrue(await self.deliver(UpdateCompletion(self.root)))

    async def test_stale_future_or_wrong_commit_legacy_snapshots_are_ignored(self):
        now = datetime.now(timezone.utc)
        self.manifest(created=now - timedelta(days=2), name="old")
        self.manifest(created=now + timedelta(hours=1), name="future")
        self.manifest(latest="c" * 40, name="different")
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()

    async def test_legacy_userbot_fallback_can_be_disabled_when_helper_is_configured(self):
        self.manifest()
        self.assertFalse(await self.deliver(userbot=True, legacy=False))
        self.send.assert_not_awaited()
        self.record(userbot=True)
        self.assertTrue(await self.deliver(userbot=True, legacy=False))

    async def test_corrupt_status_is_ignored_without_affecting_startup(self):
        self.completion.directory.mkdir()
        (self.completion.directory / "pending.json").write_text("{broken json")
        os.environ[NOTICE_ENV] = "invalid json"
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()

    async def test_invalid_metadata_and_unsafe_paths_are_rejected(self):
        for snapshot in ("../secret", "/absolute", "snapshots/../secret", "other/test"):
            self.result.snapshot = snapshot
            with self.assertRaises(ValueError):
                self.record()
        self.result.snapshot = "snapshots/test"
        for owner in (0, -1, "42", True):
            with self.assertRaises(ValueError):
                self.record(owner_id=owner)

    async def test_symlink_status_directory_is_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.completion.directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.record()
        self.assertFalse(await self.deliver())
        self.send.assert_not_awaited()
        self.assertEqual(list(outside.iterdir()), [])

    async def test_replayed_receipt_is_not_sent_again_after_a_restart(self):
        self.record()
        receipt = os.environ[NOTICE_ENV]
        self.assertTrue(await self.deliver())
        os.environ[NOTICE_ENV] = receipt
        self.assertFalse(await self.deliver(UpdateCompletion(self.root)))
        self.send.assert_awaited_once()

    async def test_notifier_checks_head_in_the_updaters_repository(self):
        self.record()
        updater = BotUpdater(self.root)
        updater._git = AsyncMock(return_value=SimpleNamespace(stdout=self.result.latest))
        self.assertTrue(await notify_update_completed(self.send, 42, updater=updater))
        updater._git.assert_awaited_once_with("rev-parse", "HEAD")

    async def test_old_runtime_cannot_report_completion_before_actual_restart(self):
        self.record()
        updater = BotUpdater(self.root)
        updater._restart_pending = True
        updater._git = AsyncMock(return_value=SimpleNamespace(stdout=self.result.latest))
        self.assertFalse(await notify_update_completed(self.send, 42, updater=updater))
        self.send.assert_not_awaited()
        updater._git.assert_not_awaited()


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = handler
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử thông báo sau kết nối")
class CompletionStartupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import bot_setup
        import helper_bot
        import profile_engine
        self.setup_module, self.helper, self.profile = bot_setup, helper_bot, profile_engine
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-ready-notice-")
        self.addCleanup(self.temp.cleanup)
        self.updater = BotUpdater(self.temp.name)
        self.result = UpdateResult("a" * 40, "b" * 40, updated=True, snapshot="snapshots/test")
        self.updater._git = AsyncMock(return_value=SimpleNamespace(stdout=self.result.latest))

        async def notify(*args, **kwargs):
            return await notify_update_completed(*args, **kwargs, updater=self.updater)
        self.notice = AsyncMock(side_effect=notify)
        self.engine = SimpleNamespace(is_running=False, start=AsyncMock(return_value=(True, "started")), stop=AsyncMock())
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "API_ID": "123", "API_HASH": "a" * 32, "SESSION_STRING": "", "BOT_TOKEN": "fake-token", "LANGUAGE": "vi"}),
            patch.object(helper_bot.state, "reload_config"),
            patch.object(helper_bot.state, "is_running", False),
            patch.object(helper_bot.state, "account_name", ""),
            patch.object(helper_bot.state, "account_id", ""),
            patch.object(helper_bot, "engine", self.engine),
            patch.object(helper_bot, "register_helper_commands", new=AsyncMock()),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.object(helper_bot, "notify_update_completed", self.notice),
            patch.object(bot_setup, "notify_update_completed", self.notice),
            patch.object(profile_engine, "notify_update_completed", self.notice),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = SimpleNamespace(
            on=HandlerClient().on, start=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(username="TestBot", id=100)),
            send_message=AsyncMock(), run_until_disconnected=AsyncMock(), disconnect=AsyncMock(),
        )

    def record(self, userbot=False):
        self.updater.completion.record(self.result, {"owner_id": 42, "lang": "vi", "userbot": userbot})

    async def test_full_helper_sends_new_completion_message_only_after_connecting(self):
        self.record()
        async def send(chat, text, **kwargs):
            self.client.start.assert_awaited_once()
            self.client.get_me.assert_awaited_once()
            return SimpleNamespace(edit=AsyncMock())
        self.client.send_message.side_effect = send
        with patch.object(self.helper, "TelegramClient", return_value=self.client):
            await self.helper.run_standalone_bot()
        calls = self.client.send_message.call_args_list
        self.assertEqual(len(calls), 2)  # setup panel, then independent completion notice
        self.assertEqual(calls[-1].args[0], 42)
        self.assertIn("Đã cập nhật xong", calls[-1].args[1])
        self.client.disconnect.assert_awaited_once()

    async def test_failed_helper_connection_never_acknowledges_completion(self):
        self.record()
        self.client.start.side_effect = ConnectionError("offline")
        with patch.object(self.helper, "TelegramClient", return_value=self.client):
            with self.assertRaises(ConnectionError):
                await self.helper.run_standalone_bot()
        self.notice.assert_not_awaited()
        self.assertTrue((self.updater.completion.directory / "pending.json").exists())

    async def test_start_retries_failed_delivery_without_using_or_replacing_panel(self):
        self.record()
        client = HandlerClient()
        client.send_message = AsyncMock(side_effect=[ConnectionError("offline"), None])
        self.helper.register_bot_handlers(client)
        event = SimpleNamespace(sender_id=42, chat_id=42, is_private=True, data=None, raw_text="/start", reply=AsyncMock())
        for _ in range(3):
            await client.handlers["start_cmd"](event)
        self.assertEqual(client.send_message.await_count, 2)  # failure + successful retry, no third send
        self.assertIn("Đã cập nhật xong", client.send_message.call_args.args[1])
        self.assertFalse((self.updater.completion.directory / "pending.json").exists())

    async def test_bootstrap_start_retries_with_separate_send_message(self):
        self.record()
        setup = self.setup_module.BotAPISetup(Mock(), "fake-token", "42")
        setup.call = AsyncMock(return_value={"message_id": 7})
        setup.panel_message_id = 55
        setup.register_commands = AsyncMock()
        message = {"message": {"date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/start"}}
        await setup.handle(message)
        self.assertEqual([call.args[0] for call in setup.call.call_args_list], ["editMessageText", "sendMessage"])
        self.assertEqual(setup.panel_message_id, 55)
        self.assertIn("Đã cập nhật xong", setup.call.call_args.kwargs["text"])
        setup.call.reset_mock()
        await setup.handle(message)
        self.assertEqual([call.args[0] for call in setup.call.call_args_list], ["editMessageText"])

    async def test_bootstrap_startup_notifies_after_authenticated_getme(self):
        self.record()
        calls = []
        async def call(instance, method, **payload):
            calls.append((method, payload))
            if method == "getMe": return {"username": "TestBot"}
            if method == "getWebhookInfo": return {"url": ""}
            if method == "getUpdates": raise asyncio.CancelledError()
            return {"message_id": 7}
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        with patch.object(self.setup_module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.setup_module.BotAPISetup, "call", call):
                with self.assertRaises(asyncio.CancelledError):
                    await self.setup_module.run_api_setup("fake-token", "42")
        self.assertEqual(calls[0][0], "getMe")
        completed = [payload for method, payload in calls if method == "sendMessage" and "Đã cập nhật xong" in payload["text"]]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["chat_id"], 42)

    async def start_userbot(self, authorized=True):
        client = SimpleNamespace(
            on=HandlerClient().on, connect=AsyncMock(), disconnect=AsyncMock(),
            is_connected=Mock(return_value=True),
            is_user_authorized=AsyncMock(return_value=authorized),
            get_me=AsyncMock(return_value=SimpleNamespace(id=42, first_name="Test", last_name="User")),
            send_message=AsyncMock(),
        )
        engine = self.profile.ProfileEngine()
        self.addAsyncCleanup(engine.stop)
        self.helper.state.config["SESSION_STRING"] = "private-session"
        with patch.object(self.profile, "StringSession", return_value=Mock()):
            with patch.object(self.profile, "TelegramClient", return_value=client):
                with patch.object(engine, "_loop", new=AsyncMock()):
                    ok, _ = await engine.start()
        return ok, client

    async def test_userbot_sends_completion_to_saved_messages_after_authentication(self):
        self.record(userbot=True)
        ok, client = await self.start_userbot()
        self.assertTrue(ok)
        client.connect.assert_awaited_once()
        client.is_user_authorized.assert_awaited_once()
        client.send_message.assert_awaited_once()
        self.assertEqual(client.send_message.call_args.args[0], "me")
        self.assertIn("Đã cập nhật xong", client.send_message.call_args.args[1])
        self.assertFalse(self.notice.call_args.kwargs["legacy"])

    async def test_failed_userbot_authentication_does_not_notify(self):
        self.record(userbot=True)
        ok, client = await self.start_userbot(authorized=False)
        self.assertFalse(ok)
        self.notice.assert_not_awaited()
        client.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
