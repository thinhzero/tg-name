"""Kiểm tra handler bằng mock; không kết nối hoặc đăng nhập Telegram."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot_updater import UpdateError, UpdateResult
from random_names import RandomNames


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử handler Telegram")
class UpdatecheckHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        self.helper = helper_bot
        self.updater = SimpleNamespace(update=AsyncMock(), request_restart=Mock())
        updater_patch = patch.object(helper_bot, "bot_updater", self.updater)
        updater_patch.start()
        self.addCleanup(updater_patch.stop)
        config_patch = patch.dict(helper_bot.state.config, {"LANGUAGE": "vi", "ADMIN_ID": "42"})
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.message = SimpleNamespace(edit=AsyncMock())

    async def test_latest_version_does_not_restart(self):
        self.updater.update.return_value = UpdateResult("abcdef123", "abcdef123")
        await self.helper.handle_updatecheck(self.message)
        self.assertIn("mới nhất", self.message.edit.call_args.args[0])
        self.updater.request_restart.assert_not_called()

    async def test_success_notifies_then_restarts(self):
        self.updater.update.return_value = UpdateResult("abcdef123", "123456789", updated=True)
        self.updater.request_restart.side_effect = lambda: self.message.edit.assert_awaited_once()
        await self.helper.handle_updatecheck(self.message)
        self.assertIn("abcdef1", self.message.edit.call_args.args[0])
        self.assertIn("1234567", self.message.edit.call_args.args[0])
        self.updater.request_restart.assert_called_once()

    async def test_success_still_restarts_if_notification_fails(self):
        self.updater.update.return_value = UpdateResult("old", "new", updated=True)
        self.message.edit.side_effect = RuntimeError("Telegram disconnected")
        with self.assertRaises(RuntimeError):
            await self.helper.handle_updatecheck(self.message)
        self.updater.request_restart.assert_called_once()

    async def test_update_error_is_escaped_and_does_not_restart(self):
        self.updater.update.side_effect = UpdateError("self_update_command_failed", details="<failure>&")
        await self.helper.handle_updatecheck(self.message)
        self.assertIn("&lt;failure&gt;&amp;", self.message.edit.call_args.args[0])
        self.updater.request_restart.assert_not_called()

    async def test_progress_uses_selected_language(self):
        async def update(progress):
            await progress("self_update_downloading")
            return UpdateResult("old", "new", updated=True)

        self.helper.state.config["LANGUAGE"] = "en"
        self.updater.update.side_effect = update
        await self.helper.handle_updatecheck(self.message)
        self.assertIn("Cloning", self.message.edit.call_args_list[0].args[0])
        self.assertIn("Restarting", self.message.edit.call_args_list[1].args[0])

    async def test_userbot_command_is_outgoing_only(self):
        client = HandlerClient()
        self.helper.register_userbot_handlers(client)
        handler, builder = client.handlers["userbot_command_handler"]
        self.assertTrue(builder.outgoing)
        match = builder.pattern(".updatecheck")
        self.assertIsNotNone(match)
        event = SimpleNamespace(pattern_match=match, edit=AsyncMock())
        self.updater.update.return_value = UpdateResult("old", "old")
        await handler(event)
        self.updater.update.assert_awaited_once()

    async def test_profile_update_keeps_its_original_behavior(self):
        client = HandlerClient()
        self.helper.register_userbot_handlers(client)
        handler, builder = client.handlers["userbot_command_handler"]
        event = SimpleNamespace(pattern_match=builder.pattern(".update"), edit=AsyncMock())
        with patch.object(self.helper.state, "trigger_update") as trigger:
            await handler(event)
        trigger.assert_called_once()
        self.updater.update.assert_not_awaited()

    async def test_helper_command_rejects_non_admin(self):
        client = HandlerClient()
        self.helper.register_bot_handlers(client)
        handler, _ = client.handlers["updatecheck_cmd"]
        event = SimpleNamespace(sender_id=99, reply=AsyncMock())
        await handler(event)
        self.updater.update.assert_not_awaited()
        event.reply.assert_not_awaited()

    async def test_helper_command_allows_admin_and_bot_username(self):
        client = HandlerClient()
        self.helper.register_bot_handlers(client)
        handler, builder = client.handlers["updatecheck_cmd"]
        self.assertIsNotNone(builder.pattern("/updatecheck@MyHelperBot"))
        event = SimpleNamespace(sender_id=42, reply=AsyncMock(return_value=self.message))
        self.updater.update.return_value = UpdateResult("old", "old")
        await handler(event)
        self.updater.update.assert_awaited_once()


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử handler Telegram")
class RandomCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        self.helper = helper_bot
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-random-handler-")
        self.addCleanup(self.temp.cleanup)
        self.store = RandomNames(Path(self.temp.name) / "name.txt")
        self.trigger = Mock()
        for patcher in (
            patch.object(helper_bot, "random_names", self.store),
            patch.object(helper_bot.state, "trigger_update", self.trigger),
            patch.dict(helper_bot.state.config, {"LANGUAGE": "vi", "ADMIN_ID": "42"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = HandlerClient()
        helper_bot.register_userbot_handlers(self.client)
        helper_bot.register_bot_handlers(self.client)

    async def userbot(self, text):
        handler, builder = self.client.handlers["userbot_command_handler"]
        match = builder.pattern(text)
        self.assertIsNotNone(match)
        event = SimpleNamespace(pattern_match=match, edit=AsyncMock(), reply=AsyncMock())
        await handler(event)
        return event

    async def test_add_multiline_and_report_uids(self):
        event = await self.userbot(".updaterandom eat29\nsleep\neat29")
        self.assertEqual([entry.text for entry in self.store.entries()], ["eat29", "sleep"])
        for entry in self.store.entries():
            self.assertIn(entry.uid, event.edit.call_args.args[0])
        self.trigger.assert_called_once()

    async def test_list_includes_uid_and_escapes_content(self):
        entry, = self.store.add("<eat29> & sleep")
        event = await self.userbot(".lsrandom")
        message = event.edit.call_args.args[0]
        self.assertIn(entry.uid, message)
        self.assertIn("&lt;eat29&gt; &amp; sleep", message)
        self.trigger.assert_not_called()

    async def test_remove_uid_only_removes_the_matching_entry(self):
        first, second = self.store.add("eat29\nsleep")
        await self.userbot(f".rmrandom {{{first.uid}}}")
        self.assertEqual(self.store.entries(), [second])
        self.trigger.assert_called_once()

    async def test_unknown_uid_does_not_change_list(self):
        self.store.add("eat29")
        event = await self.userbot(".rmrandom unknown")
        self.assertIn("Không tìm thấy", event.edit.call_args.args[0])
        self.assertEqual(len(self.store.entries()), 1)
        self.trigger.assert_not_called()

    async def test_empty_arguments_show_usage(self):
        for cmd in ("updaterandom", "rmrandom"):
            event = await self.userbot(f".{cmd}")
            self.assertIn(cmd, event.edit.call_args.args[0])
        self.assertEqual(self.store.entries(), [])
        self.trigger.assert_not_called()

    async def test_duplicate_does_not_trigger_an_update(self):
        self.store.add("eat29")
        event = await self.userbot(".updaterandom eat29")
        self.assertIn("đã có", event.edit.call_args.args[0])
        self.trigger.assert_not_called()

    async def test_empty_list(self):
        event = await self.userbot(".lsrandom")
        self.assertIn("đang trống", event.edit.call_args.args[0])

    async def test_long_list_is_paginated_and_does_not_lose_uids(self):
        entries = self.store.add("\n".join(f"{index} " + "🎲<&>" * 50 for index in range(80)))
        event = await self.userbot(".lsrandom")
        pages = [event.edit.call_args.args[0], *(call.args[0] for call in event.reply.call_args_list)]
        self.assertGreater(len(pages), 1)
        for page in pages:
            self.assertLessEqual(len(page.encode("utf-16-le")) // 2, 3500)
        for entry in entries:
            self.assertEqual("\n".join(pages).count(entry.uid), 1)

    async def test_file_error_is_reported(self):
        with patch.object(self.store, "add", side_effect=PermissionError("<denied>")):
            event = await self.userbot(".updaterandom eat29")
        self.assertIn("&lt;denied&gt;", event.edit.call_args.args[0])
        self.trigger.assert_not_called()

    async def test_helper_random_commands_are_admin_only(self):
        handler, builder = self.client.handlers["random_cmd"]
        event = SimpleNamespace(sender_id=99, pattern_match=builder.pattern("/updaterandom eat29"), reply=AsyncMock())
        await handler(event)
        self.assertEqual(self.store.entries(), [])
        event.reply.assert_not_awaited()
        event.sender_id = 42
        event.pattern_match = builder.pattern("/updaterandom@MyHelperBot eat29")
        await handler(event)
        self.assertEqual(self.store.choose(), "eat29")
        event.reply.assert_awaited_once()

    async def test_random_command_is_not_mistaken_for_pending_name_input(self):
        handler, _ = self.client.handlers["user_input_handler"]
        event = SimpleNamespace(sender_id=42, raw_text="/lsrandom", reply=AsyncMock())
        with patch.dict(self.helper.user_sessions, {42: {"action": "input_name"}}):
            with patch.object(self.helper.state, "update_config") as update_config:
                await handler(event)
            update_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
