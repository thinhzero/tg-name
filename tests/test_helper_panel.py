import asyncio
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử panel")
class HelperPanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from helper_panel import HelperPanels
        from telethon import Button
        self.panels = HelperPanels(lambda: [[Button.inline("🏠 Home", data="main_menu")]])
        self.message = SimpleNamespace(edit=AsyncMock(), delete=AsyncMock())

    def event(self, *, callback=False, sender=42):
        return SimpleNamespace(
            sender_id=sender, chat_id=sender, data=b"test" if callback else None,
            reply=AsyncMock(return_value=self.message), respond=AsyncMock(return_value=self.message),
            edit=AsyncMock(), delete=AsyncMock(),
        )

    def callback_data(self, kwargs):
        return [getattr(button, "data", None) or button.type.data for row in kwargs["buttons"] for button in row]

    async def test_first_message_is_silent_and_future_commands_edit_it(self):
        first = self.event()
        await self.panels.wrap(first).reply("Home")
        first.reply.assert_awaited_once()
        self.assertTrue(first.reply.call_args.kwargs["silent"])
        self.assertIn(b"main_menu", self.callback_data(first.reply.call_args.kwargs))
        second = self.event()
        await self.panels.wrap(second).reply("Settings")
        second.reply.assert_not_awaited()
        self.message.edit.assert_awaited_once()
        self.assertEqual(self.message.edit.call_args.args[0], "Settings")
        first.edit.assert_not_awaited()
        second.edit.assert_not_awaited()

    async def test_callback_edits_clicked_message_without_sending(self):
        event = self.event(callback=True)
        await self.panels.wrap(event).respond("Prompt")
        event.edit.assert_awaited_once()
        event.respond.assert_not_awaited()
        event.reply.assert_not_awaited()

    async def test_progress_updates_use_same_panel_and_do_not_delete_it(self):
        event = self.event()
        status = await self.panels.wrap(event).reply("Checking")
        await status.edit("Done")
        await status.delete()
        event.reply.assert_awaited_once()
        self.message.edit.assert_awaited_once()
        self.message.delete.assert_not_awaited()

    async def test_deleting_sensitive_input_still_deletes_user_message(self):
        event = self.event()
        await self.panels.wrap(event).delete()
        event.delete.assert_awaited_once()
        self.message.delete.assert_not_awaited()

    async def test_deleted_panel_has_one_silent_replacement(self):
        from telethon.errors import MessageIdInvalidError
        await self.panels.wrap(self.event()).reply("First")
        self.message.edit.side_effect = MessageIdInvalidError(request=None)
        replacement = SimpleNamespace(edit=AsyncMock())
        event = self.event()
        event.reply.return_value = replacement
        await self.panels.wrap(event).reply("Replacement")
        event.reply.assert_awaited_once()
        self.assertTrue(event.reply.call_args.kwargs["silent"])
        await self.panels.wrap(self.event()).reply("Next")
        replacement.edit.assert_awaited_once()

    async def test_network_errors_do_not_fall_back_to_duplicate_sends(self):
        await self.panels.wrap(self.event()).reply("First")
        self.message.edit.side_effect = ConnectionError("offline")
        event = self.event()
        with self.assertRaises(ConnectionError):
            await self.panels.wrap(event).reply("Next")
        event.reply.assert_not_awaited()

    async def test_unchanged_message_is_a_noop(self):
        from telethon.errors import MessageNotModifiedError
        await self.panels.wrap(self.event()).reply("First")
        self.message.edit.side_effect = MessageNotModifiedError(request=None)
        event = self.event()
        await self.panels.wrap(event).reply("First")
        event.reply.assert_not_awaited()

    async def test_background_result_cannot_overwrite_new_home_view(self):
        old = self.panels.wrap(self.event())
        message = await old.reply("Running")
        await self.panels.wrap(self.event(callback=True)).edit("Home")
        self.message.edit.reset_mock()
        await message.edit("Old result")
        await old.show_pages(["Old list"])
        self.message.edit.assert_not_awaited()
        self.assertNotIn("pages", old.panel)

    async def test_late_first_response_cannot_overwrite_newer_view(self):
        old = self.panels.wrap(self.event(callback=True))
        home = self.event(callback=True)
        await self.panels.wrap(home).edit("Home")
        await old.respond("Slow callback finished")
        home.edit.assert_awaited_once()
        old.event.respond.assert_not_awaited()

    async def test_pages_are_navigable_without_losing_content(self):
        event = self.event()
        await self.panels.wrap(event).show_pages(["Page 1", "Page 2"])
        self.assertIn(b"panel_page:1", self.callback_data(event.reply.call_args.kwargs))
        await self.panels.wrap(self.event(callback=True)).show_pages(["Page 1", "Page 2"], 1)
        self.assertEqual(self.message.edit.call_args.args[0], "Page 2")
        self.assertIn(b"main_menu", self.callback_data(self.message.edit.call_args.kwargs))

    async def test_distinct_chats_do_not_share_a_panel(self):
        first = self.event(sender=42)
        second = self.event(sender=99)
        await self.panels.wrap(first).reply("A")
        await self.panels.wrap(second).reply("B")
        first.reply.assert_awaited_once()
        second.reply.assert_awaited_once()
        self.message.edit.assert_not_awaited()


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử luồng Helper")
class HelperPanelHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        self.helper = helper_bot
        for patcher in (
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "LANGUAGE": "vi", "SESSION_STRING": "session"}),
            patch.object(helper_bot.state, "is_resetting", False),
            patch.object(helper_bot.state, "update_config"),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.object(helper_bot, "generate_preview", return_value=("Preview", "Bio")),
            patch.object(helper_bot, "notify_update_completed", new=AsyncMock(return_value=False)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = HandlerClient()
        self.panels = helper_bot.register_bot_handlers(self.client)
        self.message = SimpleNamespace(edit=AsyncMock(), delete=AsyncMock())

    def event(self, text="", data=None):
        return SimpleNamespace(
            sender_id=42, chat_id=42, is_private=True, raw_text=text,
            data=data.encode() if data else None, reply=AsyncMock(return_value=self.message),
            respond=AsyncMock(return_value=self.message), edit=AsyncMock(), delete=AsyncMock(), answer=AsyncMock(),
        )

    async def run_handler(self, name, event):
        handler, builder = self.client.handlers[name]
        if getattr(builder, "pattern", None) and event.raw_text:
            event.pattern_match = builder.pattern(event.raw_text)
        await handler(event)

    async def test_settings_input_and_home_reuse_one_message(self):
        start = self.event("/start")
        await self.run_handler("start_cmd", start)
        callback = self.event(data="setup_name")
        await self.run_handler("callback_handler", callback)
        await self.run_handler("user_input_handler", self.event("new name"))
        self.helper.state.update_config.assert_called_once_with({"BASE_NAME": "new name"})
        self.assertEqual(self.message.edit.await_count, 2)
        data = [getattr(button, "data", None) or button.type.data for row in self.message.edit.call_args.kwargs["buttons"] for button in row]
        self.assertIn(b"main_menu", data)
        await self.run_handler("callback_handler", self.event(data="main_menu"))
        self.assertEqual(self.message.edit.await_count, 3)
        callback.respond.assert_not_awaited()
        start.reply.assert_awaited_once()

    async def test_home_cancels_pending_login_connection(self):
        temp = SimpleNamespace(disconnect=AsyncMock())
        self.helper.user_sessions[42] = {"action": "login_wait_code", "temp_client": temp}
        event = self.event(data="main_menu")
        await self.run_handler("callback_handler", event)
        temp.disconnect.assert_awaited_once()
        self.assertNotIn(42, self.helper.user_sessions)
        event.respond.assert_not_awaited()
        event.edit.assert_awaited_once()

    async def test_home_command_is_not_saved_as_a_pending_name(self):
        self.helper.user_sessions[42] = {"action": "input_name"}
        await self.run_handler("user_input_handler", self.event("/home"))
        self.helper.state.update_config.assert_not_called()

    async def test_secret_input_is_deleted_even_when_the_response_edits_panel(self):
        await self.run_handler("callback_handler", self.event(data="setup_lastfm_key"))
        event = self.event("a" * 32)
        await self.run_handler("user_input_handler", event)
        event.reply.assert_not_awaited()
        event.delete.assert_awaited_once()
        self.helper.state.update_config.assert_called_once_with({"LASTFM_API_KEY": "a" * 32})

    async def test_preview_weather_bio_help_edit_the_panel(self):
        first = self.event(data="preview")
        with patch.object(self.helper, "format_weather_card", return_value="Weather"):
            with patch.object(self.helper, "format_bio_preview_card", return_value="Bio"):
                await self.run_handler("callback_handler", first)
                for data in ("preview_bio", "weather_card", "help"):
                    event = self.event(data=data)
                    await self.run_handler("callback_handler", event)
                    event.respond.assert_not_awaited()
        self.assertEqual(first.edit.await_count, 4)

    async def test_non_admin_events_cannot_change_the_panel(self):
        event = self.event("/settings")
        event.sender_id = 99
        await self.run_handler("settings_cmd", event)
        event.reply.assert_not_awaited()
        self.assertEqual(self.panels.chats, {})

    async def test_group_guard_runs_before_any_panel_is_created(self):
        event = self.event("/settings")
        event.is_private = False
        with self.assertRaises(self.helper.events.StopPropagation):
            await self.run_handler("private_chat_only", event)
        self.assertEqual(self.panels.chats, {})

    async def test_random_result_pages_are_readable_in_the_same_panel(self):
        first = self.event("/lsrandom")
        with patch.object(self.helper, "format_random_entries", return_value=["First page", "Second page"]):
            with patch.object(self.helper, "random_names", SimpleNamespace(entries=Mock(return_value=[object()]))):
                await self.run_handler("random_cmd", first)
        first.reply.assert_awaited_once()
        self.assertEqual(first.reply.call_args.args[0], "First page")
        callback = self.event(data="panel_page:1")
        await self.run_handler("callback_handler", callback)
        self.assertEqual(self.message.edit.call_args.args[0], "Second page")
        callback.respond.assert_not_awaited()

    async def test_shell_results_are_separate_and_never_replace_or_join_the_panel(self):
        from shell_commands import ShellResult
        await self.run_handler("start_cmd", self.event("/start"))
        generation = self.panels.chats[42]["generation"]
        runner = SimpleNamespace(run=AsyncMock(return_value=ShellResult("pwd", "/termux/tg-name", 0)))
        shell_message = SimpleNamespace(edit=AsyncMock())
        with patch.object(self.helper, "shell_runner", runner):
            first = self.event("/shell pwd")
            first.reply.return_value = shell_message
            await self.run_handler("shell_cmd", first)
            first.reply.assert_awaited_once()
            self.assertIn("/termux/tg-name", first.reply.call_args.args[0])
            self.assertTrue(first.reply.call_args.kwargs["silent"])
            self.assertEqual(self.panels.chats[42]["generation"], generation)
            self.message.edit.assert_not_awaited()
            await self.run_handler("callback_handler", self.event(data="main_menu"))
            self.message.edit.assert_awaited_once()
            second = self.event("/shell pwd")
            await self.run_handler("shell_cmd", second)
            second.reply.assert_awaited_once()
            self.message.edit.assert_awaited_once()
            shell_message.edit.assert_not_awaited()

    async def test_long_shell_still_delivers_a_new_result_after_returning_home(self):
        from shell_commands import ShellResult
        started, finish = asyncio.Event(), asyncio.Event()
        async def run(*args, **kwargs):
            started.set()
            await finish.wait()
            return ShellResult("pwd", "late output", 0)
        await self.run_handler("start_cmd", self.event("/start"))
        shell_event = self.event("/shell pwd")
        with patch.object(self.helper, "shell_runner", SimpleNamespace(run=AsyncMock(side_effect=run))):
            task = asyncio.create_task(self.run_handler("shell_cmd", shell_event))
            try:
                await started.wait()
                await self.run_handler("callback_handler", self.event(data="main_menu"))
            finally:
                finish.set()
                await task
        self.assertIn("late output", shell_event.reply.call_args.args[0])
        shell_event.reply.assert_awaited_once()
        self.message.edit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
