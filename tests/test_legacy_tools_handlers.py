import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}
        self.send_file = AsyncMock()

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử tiện ích từ source cũ")
class LegacyToolsHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import bot_setup
        import helper_bot
        self.helper, self.bootstrap = helper_bot, bot_setup
        self.lookup = AsyncMock()
        self.transfers = SimpleNamespace(run=AsyncMock(), cancel=Mock(return_value=True), close=AsyncMock())
        self.speeds = SimpleNamespace(run=AsyncMock(), cancel=Mock(return_value=False), close=AsyncMock())
        self.logs = SimpleNamespace(emit=Mock(return_value=False), command=AsyncMock(), button=AsyncMock(), inline=AsyncMock())
        for patcher in (
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "LANGUAGE": "vi"}),
            patch.object(helper_bot.state, "is_resetting", False),
            patch.object(helper_bot, "lookup_message", self.lookup),
            patch.object(bot_setup, "lookup_message", self.lookup),
            patch.object(helper_bot, "file_transfers", self.transfers),
            patch.object(helper_bot, "speed_tests", self.speeds),
            patch.object(helper_bot, "chat_log", self.logs),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.object(helper_bot, "notify_update_completed", new=AsyncMock(return_value=False)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client, self.user = HandlerClient(), HandlerClient()
        helper_bot.register_bot_handlers(self.client)
        helper_bot.register_userbot_handlers(self.user)
        self.message = SimpleNamespace(edit=AsyncMock())

    def event(self, text, sender=42, private=True):
        return SimpleNamespace(
            id=100, sender_id=sender, chat_id=42, is_private=private, raw_text=text, data=None,
            is_reply=False, reply_to_msg_id=None,
            reply=AsyncMock(return_value=self.message), respond=AsyncMock(return_value=self.message),
            edit=AsyncMock(), answer=AsyncMock(), delete=AsyncMock(), get_reply_message=AsyncMock(),
        )

    async def helper_command(self, name, event):
        handler, builder = self.client.handlers[name]
        event.pattern_match = builder.pattern(event.raw_text)
        self.assertIsNotNone(event.pattern_match)
        await handler(event)

    async def user_command(self, text):
        event = self.event(text)
        handler, builder = self.user.handlers["userbot_command_handler"]
        self.assertTrue(builder.outgoing)
        event.pattern_match = builder.pattern(text)
        await handler(event)
        return event

    async def test_userbot_and_full_helper_lookup_commands_route_consistently(self):
        for command, argument in (("whois", "example.com"),):
            event = await self.user_command(f".{command} {argument}")
            self.lookup.assert_awaited_with(command, argument, event.edit, "vi")
            event = self.event(f"/{command}@MyBot {argument}")
            await self.helper_command("lookup_cmd", event)
            self.assertEqual(self.lookup.call_args.args[:2], (command, argument))

    async def test_helper_tools_are_admin_private_only_and_blocked_during_reset(self):
        for name, text in (("lookup_cmd", "/whois example.com"), ("link_transfer_cmd", "/l https://example.com/file")):
            for event in (self.event(text, sender=99), self.event(text, private=False)):
                await self.helper_command(name, event)
            with patch.object(self.helper.state, "is_resetting", True):
                await self.helper_command(name, self.event(text))
        self.lookup.assert_not_awaited()
        self.transfers.run.assert_not_awaited()

    async def test_transfer_preserves_original_l_command_and_uploads_as_document(self):
        async def run(url, edit, upload, **kwargs):
            await upload(Path("/temporary/file.zip"), "<file>.zip", AsyncMock())
        self.transfers.run.side_effect = run
        for text, client, userbot in ((".l https://example.com/file", self.user, True), ("/l@MyBot https://example.com/file", self.client, False)):
            if userbot:
                event = await self.user_command(text)
            else:
                event = self.event(text)
                await self.helper_command("link_transfer_cmd", event)
            self.assertEqual(self.transfers.run.call_args.args[0], "https://example.com/file")
            self.assertEqual(self.transfers.run.call_args.kwargs["userbot"], userbot)
            self.assertEqual(self.transfers.run.call_args.kwargs["owner_id"], 42)
            client.send_file.assert_awaited_once()
            call = client.send_file.call_args
            self.assertEqual(call.args[:2], (42, "/temporary/file.zip"))
            self.assertEqual(call.kwargs["caption"], "&lt;file&gt;.zip")
            self.assertTrue(call.kwargs["force_document"])
            self.assertTrue(call.kwargs["silent"])
            event.delete.assert_not_awaited()

    async def test_userbot_cancel_is_bound_to_owner_chat_and_transport(self):
        await self.user_command(".cancel")
        self.transfers.cancel.assert_called_once_with(42, 42, userbot=True)
        self.transfers.cancel.reset_mock()
        await self.helper_command("cancel_cmd", self.event("/cancel@MyBot"))
        self.transfers.cancel.assert_called_once_with(42, 42)
        self.speeds.cancel.assert_any_call(42, 42, userbot=True)
        self.speeds.cancel.assert_any_call(42, 42)

    async def test_speedtest_aliases_route_to_the_same_job_for_both_transports(self):
        for alias in ("speedtest", "speetest", "speed", "sp"):
            await self.user_command("." + alias)
            self.assertTrue(self.speeds.run.call_args.kwargs["userbot"])
            await self.helper_command("speedtest_cmd", self.event("/" + alias + "@MyBot"))
            self.assertEqual(self.speeds.run.call_args.kwargs["chat_id"], 42)
        self.assertEqual(self.speeds.run.await_count, 8)

    async def test_speedtest_is_admin_private_only_and_blocked_during_reset(self):
        for event in (self.event("/sp", sender=99), self.event("/sp", private=False)):
            await self.helper_command("speedtest_cmd", event)
        with patch.object(self.helper.state, "is_resetting", True):
            await self.helper_command("speedtest_cmd", self.event("/sp"))
        self.speeds.run.assert_not_awaited()

    async def test_log_commands_are_owner_outgoing_commands_and_preserve_current_chat(self):
        for text in (".loghere", ".unloghere", ".logconfig", ".logtypes error,update"):
            await self.user_command(text)
        self.assertEqual(self.logs.command.await_count, 4)
        self.assertEqual(self.logs.command.call_args.args[1:3], ("logtypes", "error,update"))

    async def test_only_log_settings_callbacks_can_pass_the_group_guard(self):
        event = self.event("", private=False)
        event.message_id = 800
        event.data = b"logcfg:nonce:cat_profile"
        await self.client.handlers["private_chat_only"][0](event)
        with self.assertRaises(self.helper.events.StopPropagation):
            await self.client.handlers["log_settings_callback"][0](event)
        self.logs.button.assert_awaited_once_with(event, self.helper.state)
        event.data = b"main_menu"
        with self.assertRaises(self.helper.events.StopPropagation):
            await self.client.handlers["private_chat_only"][0](event)

    async def test_command_logs_never_include_arguments(self):
        await self.user_command(".whois example.com?private-api-key")
        self.logs.emit.assert_called_with("command", {"command": ".whois"})
        self.assertNotIn("private-api-key", str(self.logs.emit.call_args_list))

    async def test_full_helper_commands_do_not_get_saved_as_dialog_input(self):
        session = {"action": "input_name"}
        self.helper.user_sessions[42] = session
        for text in ("/ip 1.1.1.1", "/whois example.com", "/l https://example.com/file", "/cancel@MyBot"):
            event = self.event(text)
            await self.client.handlers["user_input_handler"][0](event)
            self.assertEqual(self.helper.user_sessions[42], session)
            event.delete.assert_not_awaited()

    async def test_old_progress_does_not_overwrite_home(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def run(url, edit, upload, **kwargs):
            await edit("transfer starting", parse_mode="html")
            started.set()
            await finish.wait()
            await edit("stale transfer result", parse_mode="html")
        self.transfers.run.side_effect = run
        event = self.event("/l https://example.com/file")
        task = asyncio.create_task(self.helper_command("link_transfer_cmd", event))
        try:
            await started.wait()
            home = self.event("")
            home.data = b"main_menu"
            await self.client.handlers["callback_handler"][0](home)
        finally:
            finish.set()
            await task
        self.assertNotIn("stale transfer result", str(self.message.edit.call_args_list))

    async def test_bootstrap_lookups_work_before_api_and_leave_pending_api_input_intact(self):
        setup = self.bootstrap.BotAPISetup(Mock(), "fake-token", "42")
        setup.call = AsyncMock()
        setup.action = "api_id"
        for command in ("/whois example.com", "/whois@MyBot example.com"):
            await setup.handle({"message": {"date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": command}})
            self.assertEqual(setup.action, "api_id")
        self.assertEqual(self.lookup.await_count, 2)
        self.assertEqual(self.lookup.call_args.args[:2], ("whois", "example.com"))
        setup.call.assert_not_awaited()

    async def test_new_commands_are_anchored_and_do_not_intercept_login_or_music(self):
        for name, text in (("link_transfer_cmd", "/login"), ("lookup_cmd", "/ipanything 1.1.1.1")):
            self.assertIsNone(self.client.handlers[name][1].pattern(text))
        from bot_commands import command_menu
        names = {item["command"] for item in command_menu()}
        self.assertTrue({"whois", "l", "speedtest", "sp"} <= names)
        self.assertNotIn("ip", names)
        self.assertNotIn("up", names)
        self.assertIsNone(self.user.handlers["userbot_command_handler"][1].pattern(".ip 1.1.1.1"))
        self.assertIsNone(self.user.handlers["userbot_command_handler"][1].pattern(".up https://example.com/file"))
        self.assertNotIn("l", {item["command"] for item in command_menu(bootstrap=True)})


if __name__ == "__main__":
    unittest.main()
