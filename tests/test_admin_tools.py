import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot_updater import UpdateResult, UpdatePlan, update_requests
from shell_commands import ShellError, ShellResult


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử công cụ admin")
class AdminToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        import bot_setup
        self.helper = helper_bot
        self.bootstrap = bot_setup
        self.updater = SimpleNamespace(check=AsyncMock(return_value=UpdatePlan("abcdef123", "abcdef123")), update=AsyncMock(return_value=UpdateResult("abcdef123", "abcdef123")), request_restart=Mock())
        self.runner = SimpleNamespace(run=AsyncMock(return_value=ShellResult("uptime", "up 1 day", 0)))
        for patcher in (
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "LANGUAGE": "vi", "BOT_TOKEN": "private-bot-token"}),
            patch.object(helper_bot.state, "is_resetting", False),
            patch.object(helper_bot, "bot_updater", self.updater),
            patch.object(bot_setup, "bot_updater", self.updater),
            patch.object(helper_bot, "shell_runner", self.runner),
            patch.object(bot_setup, "shell_runner", self.runner),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.dict(update_requests.pending, {}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = HandlerClient()
        helper_bot.register_bot_handlers(self.client)
        self.message = SimpleNamespace(edit=AsyncMock())

    def event(self, text="", data=None, sender=42, private=True):
        return SimpleNamespace(
            sender_id=sender, is_private=private, raw_text=text, data=data.encode() if data else None,
            reply=AsyncMock(return_value=self.message), respond=AsyncMock(return_value=self.message), answer=AsyncMock(),
            edit=self.message.edit,
        )

    async def test_update_button_is_present_in_both_menus(self):
        for keyboard in (self.helper.get_main_keyboard(), self.helper.get_settings_keyboard()):
            data = [(getattr(button, "data", None) or button.type.data).decode() for row in keyboard for button in row]
            self.assertIn("updatecheck", data)
            self.assertTrue(self.helper.TelegramClient.build_reply_markup(keyboard).rows)

    async def test_update_button_uses_existing_update_flow(self):
        handler, _ = self.client.handlers["callback_handler"]
        await handler(self.event(data="updatecheck"))
        self.updater.check.assert_awaited_once()
        self.updater.update.assert_not_awaited()
        self.assertIn("mới nhất", self.message.edit.call_args.args[0])
        self.updater.request_restart.assert_not_called()

    async def test_update_button_restarts_if_update_was_applied(self):
        self.updater.check.return_value = UpdatePlan("old", "new", ahead=2)
        self.updater.update.return_value = UpdateResult("old", "new", updated=True)
        handler, _ = self.client.handlers["callback_handler"]
        await handler(self.event(data="updatecheck"))
        self.updater.update.assert_not_awaited()
        self.updater.request_restart.assert_not_called()
        token = update_requests.pending[(42, False)][0]
        await handler(self.event(data=f"update_confirm:{token}"))
        self.updater.request_restart.assert_called_once()

    async def test_update_button_does_not_accept_non_admin_or_group_clicks(self):
        handler, _ = self.client.handlers["callback_handler"]
        await handler(self.event(data="updatecheck", sender=99))
        await handler(self.event(data="updatecheck", private=False))
        self.updater.update.assert_not_awaited()

    async def test_update_no_button_does_not_apply_or_restart(self):
        self.updater.check.return_value = UpdatePlan("old", "new", ahead=2)
        handler, _ = self.client.handlers["callback_handler"]
        await handler(self.event(data="updatecheck"))
        token = update_requests.pending[(42, False)][0]
        await handler(self.event(data=f"update_cancel:{token}"))
        self.updater.update.assert_not_awaited()
        self.updater.request_restart.assert_not_called()
        self.assertIn("không cập nhật", self.message.edit.call_args.args[0])

    async def test_non_admin_or_group_cannot_consume_update_confirmation(self):
        token = update_requests.create(42, UpdatePlan("old", "new", ahead=1))
        handler, _ = self.client.handlers["callback_handler"]
        await handler(self.event(data=f"update_confirm:{token}", sender=99))
        await handler(self.event(data=f"update_confirm:{token}", private=False))
        self.updater.update.assert_not_awaited()
        self.assertIn((42, False), update_requests.pending)

    async def test_shell_command_supports_bot_username_and_arbitrary_arguments(self):
        handler, builder = self.client.handlers["shell_cmd"]
        event = self.event("/shell@MyBot ls -la | head")
        event.pattern_match = builder.pattern(event.raw_text)
        await handler(event)
        self.assertEqual(self.runner.run.call_args.args[0], "ls -la | head")
        self.assertIn("private-bot-token", self.runner.run.call_args.kwargs["secret_values"])
        self.assertIn("up 1 day", event.reply.call_args.args[0])
        event.reply.assert_awaited_once()
        self.message.edit.assert_not_awaited()

    async def test_shell_command_is_admin_private_only(self):
        handler, builder = self.client.handlers["shell_cmd"]
        for event in (self.event("/shell uptime", sender=99), self.event("/shell uptime", private=False)):
            event.pattern_match = builder.pattern(event.raw_text)
            await handler(event)
            event.reply.assert_not_awaited()
        self.runner.run.assert_not_awaited()

    async def test_shell_command_is_disabled_during_reset(self):
        handler, builder = self.client.handlers["shell_cmd"]
        event = self.event("/shell ls")
        event.pattern_match = builder.pattern(event.raw_text)
        with patch.object(self.helper.state, "is_resetting", True):
            await handler(event)
        event.reply.assert_not_awaited()
        self.runner.run.assert_not_awaited()

    async def test_shell_error_is_shown_without_echoing_exception(self):
        self.runner.run.side_effect = ShellError("shell_linux_only")
        handler, builder = self.client.handlers["shell_cmd"]
        event = self.event("/shell uptime")
        event.pattern_match = builder.pattern(event.raw_text)
        await handler(event)
        self.assertIn("chỉ hoạt động trên Linux", event.reply.call_args.args[0])
        self.message.edit.assert_not_awaited()

    async def test_shell_is_not_mistaken_for_pending_name_input(self):
        self.helper.user_sessions[42] = {"action": "input_name"}
        handler, _ = self.client.handlers["user_input_handler"]
        with patch.object(self.helper.state, "update_config") as save:
            await handler(self.event("/shell uptime"))
        save.assert_not_called()

    def setup_bot(self):
        setup = self.bootstrap.BotAPISetup(Mock(), "private-bot-token", "42")
        setup.call = AsyncMock(return_value={"message_id": 77})
        return setup

    async def test_bootstrap_menu_includes_update_button(self):
        setup = self.setup_bot()
        await setup.show_menu()
        keyboard = setup.call.call_args.kwargs["reply_markup"]["inline_keyboard"]
        self.assertIn("updatecheck", [button.get("callback_data") for row in keyboard for button in row])

    async def test_bootstrap_update_button_is_admin_only(self):
        setup = self.setup_bot()
        def callback(sender, kind="private"):
            return {"callback_query": {"id": "cb", "data": "updatecheck", "from": {"id": sender}, "message": {"chat": {"id": 42, "type": kind}}}}
        await setup.handle(callback(99))
        await setup.handle(callback(42, "group"))
        self.updater.update.assert_not_awaited()
        await setup.handle(callback(42))
        self.updater.check.assert_awaited_once()

    async def test_bootstrap_update_command_preserves_api_input(self):
        setup = self.setup_bot()
        setup.action = "api_hash"
        await setup.handle({"message": {
            "date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/updatecheck",
        }})
        self.updater.check.assert_awaited_once()
        self.assertEqual(setup.action, "api_hash")

    async def test_bootstrap_yes_and_no_use_the_same_confirmation_flow(self):
        self.updater.check.return_value = UpdatePlan("old", "new", ahead=3)
        setup = self.setup_bot()
        def callback(data):
            return {"callback_query": {"id": "cb", "data": data, "from": {"id": 42}, "message": {"message_id": 77, "chat": {"id": 42, "type": "private"}}}}
        await setup.handle(callback("updatecheck"))
        self.updater.update.assert_not_awaited()
        token = update_requests.pending[(42, False)][0]
        await setup.handle(callback(f"update_cancel:{token}"))
        self.updater.update.assert_not_awaited()
        await setup.handle(callback("updatecheck"))
        token = update_requests.pending[(42, False)][0]
        self.updater.update.return_value = UpdateResult("old", "new", updated=True, snapshot="snapshots/example")
        await setup.handle(callback(f"update_confirm:{token}"))
        self.updater.update.assert_awaited_once()
        self.updater.request_restart.assert_called_once()
        self.assertTrue(any("snapshots/example" in call.kwargs.get("text", "") for call in setup.call.call_args_list))

    async def test_bootstrap_shell_runs_before_api_configuration(self):
        setup = self.setup_bot()
        setup.action = "api_hash"
        setup.api_id = "123"
        setup.panel_message_id = 55
        await setup.handle({"message": {
            "date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/shell fastfetch",
        }})
        self.assertEqual(self.runner.run.call_args.args[0], "fastfetch")
        self.assertEqual(setup.action, "api_hash")
        self.assertEqual([call.args[0] for call in setup.call.call_args_list], ["sendMessage"])
        self.assertEqual(setup.panel_message_id, 55)
        self.assertIn("up 1 day", setup.call.call_args.kwargs["text"])

    async def test_bootstrap_shell_rejects_non_admin_and_groups(self):
        setup = self.setup_bot()
        for sender, kind in ((99, "private"), (42, "group")):
            await setup.handle({"message": {
                "date": setup.started_at, "from": {"id": sender}, "chat": {"id": 42, "type": kind}, "text": "/shell ls",
            }})
        self.runner.run.assert_not_awaited()

    async def test_bootstrap_shell_results_keep_history_and_reply_to_their_command(self):
        setup = self.setup_bot()
        setup.panel_message_id = 55
        for message_id in (101, 102):
            await setup.handle({"message": {
                "message_id": message_id, "date": setup.started_at, "from": {"id": 42},
                "chat": {"id": 42, "type": "private"}, "text": "/shell pwd",
            }})
        calls = setup.call.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["sendMessage", "sendMessage"])
        self.assertEqual([call.kwargs["reply_parameters"]["message_id"] for call in calls], [101, 102])
        self.assertTrue(all(call.kwargs["disable_notification"] for call in calls))
        self.assertEqual(setup.panel_message_id, 55)


if __name__ == "__main__":
    unittest.main()
