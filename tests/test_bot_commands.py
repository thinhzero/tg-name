import asyncio
import importlib.util
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot_commands import SETUP_COMMANDS, command_menu, register_helper_commands


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


class CommandMenuTests(unittest.TestCase):
    def test_catalog_has_valid_unique_commands_and_descriptions(self):
        menu = command_menu()
        names = [item["command"] for item in menu]
        self.assertEqual(len(names), len(set(names)))
        self.assertLessEqual(len(menu), 100)
        self.assertTrue({"shell", "afk", "on", "ping", "home", "updatecheck", "reset"} <= set(names))
        for item in menu:
            self.assertRegex(item["command"], re.compile(r"^[a-z0-9_]{1,32}$"))
            self.assertTrue(1 <= len(item["description"]) <= 256)

    def test_bootstrap_only_suggests_supported_commands(self):
        names = {item["command"] for item in command_menu(bootstrap=True)}
        self.assertEqual(names, SETUP_COMMANDS)
        self.assertNotIn("login", names)
        self.assertNotIn("settings", names)

    def test_language_and_returned_items_are_independent(self):
        vi, en = command_menu("vi"), command_menu("en")
        self.assertNotEqual(vi[0]["description"], en[0]["description"])
        self.assertEqual(vi, command_menu("unknown"))
        vi[0]["description"] = "modified"
        self.assertNotEqual(vi, command_menu("vi"))


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử đăng ký menu")
class CommandRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import bot_setup
        import helper_bot
        for module in (bot_setup, helper_bot):
            patcher = patch.object(module, "notify_update_completed", new=AsyncMock(return_value=False))
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_telethon_registers_commands_for_admin_peer_only(self):
        from telethon.tl import functions, types
        client = AsyncMock(return_value=True)
        client.get_input_entity = AsyncMock(return_value=types.InputPeerUser(42, 7))
        self.assertTrue(await register_helper_commands(client, "42", "en"))
        request = client.call_args.args[0]
        self.assertIsInstance(request, functions.bots.SetBotCommandsRequest)
        self.assertIsInstance(request.scope, types.BotCommandScopePeer)
        self.assertEqual(request.scope.peer.user_id, 42)
        self.assertEqual(request.lang_code, "")
        self.assertIn("shell", [command.command for command in request.commands])
        self.assertEqual(request.commands[0].description, command_menu("en")[0]["description"])

    async def test_failure_is_nonfatal_and_does_not_echo_private_errors(self):
        client = AsyncMock()
        client.get_input_entity.side_effect = ValueError("private-token-from-request")
        with patch("builtins.print") as output:
            self.assertFalse(await register_helper_commands(client, 42))
        client.assert_not_awaited()
        self.assertNotIn("private-token-from-request", str(output.call_args_list))

    async def test_helper_startup_registers_menu(self):
        import helper_bot
        client = SimpleNamespace(
            on=HandlerClient().on, start=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(username="TestBot", id=100)),
            send_message=AsyncMock(), run_until_disconnected=AsyncMock(), disconnect=AsyncMock(),
        )
        with patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "BOT_TOKEN": "fake-bot-token", "API_ID": "123", "API_HASH": "private-hash", "SESSION_STRING": "", "LANGUAGE": "en"}):
            with patch.object(helper_bot.state, "reload_config"):
                with patch.object(helper_bot, "engine", SimpleNamespace(is_running=False, stop=AsyncMock())):
                    with patch.object(helper_bot, "TelegramClient", return_value=client):
                        with patch.object(helper_bot, "register_helper_commands", new=AsyncMock(return_value=True)) as register:
                            await helper_bot.run_standalone_bot()
        register.assert_awaited_once_with(client, 42, "en")
        client.disconnect.assert_awaited_once()

    async def test_start_and_language_change_refresh_helper_menu(self):
        import helper_bot
        client = HandlerClient()
        helper_bot.register_bot_handlers(client)
        event = SimpleNamespace(sender_id=42, chat_id=42, is_private=True, data=None, raw_text="/start", reply=AsyncMock())
        with patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "LANGUAGE": "vi"}):
            with patch.object(helper_bot.state, "update_config", side_effect=helper_bot.state.config.update):
                with patch.object(helper_bot, "register_helper_commands", new=AsyncMock(return_value=True)) as register:
                    await client.handlers["start_cmd"][0](event)
                    register.assert_awaited_with(client, 42, "vi")
                    handler, builder = client.handlers["lang_cmd"]
                    event.pattern_match = builder.pattern("/lang en")
                    await handler(event)
                    register.assert_awaited_with(client, 42, "en")
                    event.data = b"set_lang_vi"
                    event.answer = AsyncMock()
                    await client.handlers["callback_handler"][0](event)
                    register.assert_awaited_with(client, 42, "vi")

    async def test_bootstrap_menu_registration_uses_admin_chat_scope(self):
        import bot_setup
        setup = bot_setup.BotAPISetup(Mock(), "fake-bot-token", "42")
        setup.call = AsyncMock(return_value=True)
        with patch.dict(bot_setup.state.config, {"LANGUAGE": "en"}):
            self.assertTrue(await setup.register_commands())
        self.assertEqual(setup.call.call_args.args[0], "setMyCommands")
        self.assertEqual(setup.call.call_args.kwargs["scope"], {"type": "chat", "chat_id": 42})
        self.assertEqual(setup.call.call_args.kwargs["commands"], command_menu("en", bootstrap=True))

    async def test_bootstrap_failed_registration_does_not_stop_polling(self):
        import bot_setup
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        calls = []
        async def call(instance, method, **payload):
            calls.append(method)
            if method == "getMe": return {"username": "TestBot"}
            if method == "getWebhookInfo": return {"url": ""}
            if method == "setMyCommands": raise bot_setup.BotSetupError(400, method=method)
            if method == "getUpdates": raise asyncio.CancelledError()
            return {"message_id": 7}
        with patch.object(bot_setup.aiohttp, "ClientSession", return_value=session):
            with patch.object(bot_setup.BotAPISetup, "call", call):
                with self.assertRaises(asyncio.CancelledError):
                    await bot_setup.run_api_setup("fake-bot-token", "42")
        self.assertEqual(calls, ["getMe", "getWebhookInfo", "setMyCommands", "sendMessage", "getUpdates"])

    async def test_bootstrap_start_and_language_refresh_menu(self):
        import bot_setup
        setup = bot_setup.BotAPISetup(Mock(), "fake-bot-token", "42")
        setup.call = AsyncMock(return_value={"message_id": 7})
        with patch.dict(bot_setup.state.config, {"LANGUAGE": "vi"}):
            with patch.object(bot_setup.state, "update_config", side_effect=bot_setup.state.config.update):
                await setup.handle({"message": {"date": setup.started_at, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "/start"}})
                self.assertTrue(any(call.args[0] == "setMyCommands" for call in setup.call.call_args_list))
                setup.call.reset_mock()
                await setup.handle({"callback_query": {"id": "cb", "data": "bootstrap_en", "from": {"id": 42}, "message": {"message_id": 7, "chat": {"id": 42, "type": "private"}}}})
                menu_calls = [call for call in setup.call.call_args_list if call.args[0] == "setMyCommands"]
                self.assertEqual(len(menu_calls), 1)
                self.assertEqual(menu_calls[0].kwargs["commands"], command_menu("en", bootstrap=True))


if __name__ == "__main__":
    unittest.main()
