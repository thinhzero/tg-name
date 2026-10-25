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
            self.handlers[handler.__name__] = handler
            return handler
        return register


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử cài đặt qua bot")
class BotAPISetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import bot_setup
        self.module = bot_setup
        self.setup = bot_setup.BotAPISetup(Mock(), "fake-bot-token", "42")
        self.setup.call = AsyncMock(return_value={})
        self.setup.validate_api = AsyncMock()
        self.hash = "a" * 32
        config_patch = patch.dict(bot_setup.state.config, {
            "ADMIN_ID": "42", "BOT_TOKEN": "fake-bot-token", "API_ID": "", "API_HASH": "", "LANGUAGE": "vi",
        })
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.save = Mock(side_effect=bot_setup.state.config.update)
        save_patch = patch.object(bot_setup.state, "update_config", self.save)
        save_patch.start()
        self.addCleanup(save_patch.stop)

    def message(self, text, sender=42, chat_type="private", date=None):
        return {"update_id": 3, "message": {
            "message_id": 99, "date": self.setup.started_at if date is None else date,
            "from": {"id": sender}, "chat": {"id": 42, "type": chat_type}, "text": text,
        }}

    def callback(self, data="bootstrap_api", sender=42):
        return {"update_id": 1, "callback_query": {
            "id": "callback", "from": {"id": sender}, "data": data,
            "message": {"chat": {"id": 42, "type": "private"}},
        }}

    async def enter_id(self):
        await self.setup.handle(self.callback())
        await self.setup.handle(self.message("123"))

    async def test_start_shows_buttons_without_granting_admin(self):
        await self.setup.handle(self.message("/start"))
        call = self.setup.call.call_args
        self.assertEqual(call.args[0], "sendMessage")
        self.assertEqual(call.kwargs["chat_id"], 42)
        self.assertIn("inline_keyboard", call.kwargs["reply_markup"])
        self.save.assert_not_called()

    async def test_non_admin_and_group_updates_are_ignored(self):
        await self.setup.handle(self.message("/start", sender=99))
        await self.setup.handle(self.message("/start", chat_type="group"))
        await self.setup.handle(self.callback(sender=99))
        self.setup.call.assert_not_awaited()
        self.save.assert_not_called()

    async def test_old_pending_messages_are_not_replayed(self):
        await self.setup.handle(self.message("/start", date=self.setup.started_at - 30))
        self.setup.call.assert_not_awaited()

    async def test_click_and_api_id_advance_without_saving_credentials(self):
        await self.enter_id()
        self.assertEqual(self.setup.action, "api_hash")
        self.assertEqual(self.setup.api_id, "123")
        self.save.assert_not_called()

    async def test_invalid_api_id_is_rejected(self):
        await self.setup.handle(self.callback())
        for value in ("0", "-12", "abc", "2147483648", "9" * 100):
            await self.setup.handle(self.message(value))
            self.assertEqual(self.setup.action, "api_id")
        self.save.assert_not_called()

    async def test_invalid_hash_is_deleted_and_retried(self):
        await self.enter_id()
        result = await self.setup.handle(self.message("not a hash"))
        self.assertFalse(result)
        self.assertEqual(self.setup.action, "api_hash")
        self.setup.call.assert_any_await("deleteMessage", chat_id=42, message_id=99)
        self.setup.validate_api.assert_not_awaited()
        self.save.assert_not_called()

    async def test_valid_credentials_are_saved_without_token_or_admin_changes(self):
        await self.enter_id()
        self.assertTrue(await self.setup.handle(self.message(self.hash)))
        self.setup.validate_api.assert_awaited_once_with(self.hash)
        self.save.assert_called_once_with({"API_ID": "123", "API_HASH": self.hash})
        self.assertEqual(self.module.state.config["ADMIN_ID"], "42")
        for call in self.setup.call.call_args_list:
            self.assertNotIn(self.hash, str(call.kwargs))
            self.assertNotIn("fake-bot-token", str(call.kwargs))

    async def test_api_failure_does_not_save_or_echo_secret_exception(self):
        await self.enter_id()
        self.setup.validate_api.side_effect = ValueError(self.hash + " fake-bot-token")
        self.assertFalse(await self.setup.handle(self.message(self.hash)))
        self.save.assert_not_called()
        self.assertIsNone(self.setup.action)
        for call in self.setup.call.call_args_list:
            self.assertNotIn(self.hash, str(call.kwargs))
            self.assertNotIn("fake-bot-token", str(call.kwargs))

    async def test_cancel_forgets_partial_credentials(self):
        await self.enter_id()
        await self.setup.handle(self.callback("bootstrap_cancel"))
        self.assertIsNone(self.setup.action)
        self.assertEqual(self.setup.api_id, "")
        self.save.assert_not_called()

    async def test_expired_callback_is_ignored_without_running_its_action(self):
        self.setup.call.side_effect = self.module.BotSetupError(
            400, method="answerCallbackQuery",
            description="Bad Request: query is too old and response timeout expired or query ID is invalid",
        )
        self.setup.offer_reset = AsyncMock()
        self.assertFalse(await self.setup.handle(self.callback("reset_request")))
        self.setup.call.assert_awaited_once_with("answerCallbackQuery", callback_query_id="callback")
        self.setup.offer_reset.assert_not_awaited()
        self.save.assert_not_called()

    async def test_other_callback_errors_are_not_silently_ignored(self):
        self.setup.call.side_effect = self.module.BotSetupError(429, 3, method="answerCallbackQuery")
        with self.assertRaises(self.module.BotSetupError):
            await self.setup.handle(self.callback())

    async def test_write_failure_keeps_hash_step_for_retry(self):
        await self.enter_id()
        self.save.side_effect = PermissionError("denied")
        self.assertFalse(await self.setup.handle(self.message(self.hash)))
        self.assertEqual(self.setup.action, "api_hash")

    async def test_credential_validation_disconnects_its_memory_session_on_error(self):
        self.setup.api_id = "123"
        client = SimpleNamespace(start=AsyncMock(side_effect=ValueError("invalid")), disconnect=AsyncMock())
        with patch.object(self.module, "TelegramClient", return_value=client):
            with self.assertRaises(ValueError):
                await self.module.BotAPISetup.validate_api(self.setup, self.hash)
        client.disconnect.assert_awaited_once()

    async def test_polling_hands_off_and_acknowledges_last_update(self):
        updates = [self.callback(), self.message("123"), self.message(self.hash)]
        for index, update in enumerate(updates, start=1):
            update["update_id"] = index
        calls = []

        async def call(instance, method, **payload):
            calls.append((method, payload))
            if method == "getMe":
                return {"username": "TestHelper"}
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "getUpdates":
                return updates if payload["offset"] == 0 else []
            return {}

        session = Mock()
        session.__aenter__ = AsyncMock(return_value=Mock())
        session.__aexit__ = AsyncMock(return_value=False)
        with patch.object(self.module.time, "time", return_value=self.setup.started_at):
            with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
                with patch.object(self.module.BotAPISetup, "call", call):
                    with patch.object(self.module.BotAPISetup, "validate_api", new=AsyncMock()):
                        self.assertTrue(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual([payload["offset"] for method, payload in calls if method == "getUpdates"], [0, 4])
        self.save.assert_called_once_with({"API_ID": "123", "API_HASH": self.hash})
        session.__aexit__.assert_awaited_once()

    async def test_bad_callback_does_not_poison_pending_update_queue(self):
        updates = [self.callback(), self.callback(), self.message("123"), self.message(self.hash)]
        updates[0]["callback_query"]["id"] = "expired-callback"
        for index, update in enumerate(updates, start=1):
            update["update_id"] = index
        offsets = []
        rejected = []

        async def call(instance, method, **payload):
            if method == "getMe":
                return {"username": "TestHelper"}
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "getUpdates":
                offsets.append(payload["offset"])
                if len(offsets) == 1:
                    return updates
                self.assertEqual(payload["offset"], 5, "Failed updates must be acknowledged, not replayed forever")
                return []
            if method == "answerCallbackQuery" and payload["callback_query_id"] == "expired-callback":
                rejected.append(payload["callback_query_id"])
                raise self.module.BotSetupError(400)
            return {}

        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        with patch.object(self.module.time, "time", return_value=self.setup.started_at):
            with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
                with patch.object(self.module.BotAPISetup, "call", call):
                    with patch.object(self.module.BotAPISetup, "validate_api", new=AsyncMock()):
                        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()):
                            self.assertTrue(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual(offsets, [0, 5])
        self.assertEqual(rejected, ["expired-callback"])
        self.save.assert_called_once_with({"API_ID": "123", "API_HASH": self.hash})

    async def test_rate_limited_update_is_retried_without_skipping_it(self):
        updates = [self.callback(), self.message("123"), self.message(self.hash)]
        for index, update in enumerate(updates, start=1):
            update["update_id"] = index
        offsets = []
        attempts = []

        async def call(instance, method, **payload):
            if method == "getMe":
                return {"username": "TestHelper"}
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "getUpdates":
                offsets.append(payload["offset"])
                self.assertLessEqual(len(offsets), 3)
                return updates if payload["offset"] == 0 else []
            if method == "answerCallbackQuery":
                attempts.append(method)
                if len(attempts) == 1:
                    raise self.module.BotSetupError(429, 3, method=method)
            return {}

        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        with patch.object(self.module.time, "time", return_value=self.setup.started_at):
            with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
                with patch.object(self.module.BotAPISetup, "call", call):
                    with patch.object(self.module.BotAPISetup, "validate_api", new=AsyncMock()):
                        with patch.object(self.module.asyncio, "sleep", new=AsyncMock()) as sleep:
                            self.assertTrue(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual(offsets, [0, 0, 4])
        sleep.assert_awaited_once_with(3)
        self.save.assert_called_once_with({"API_ID": "123", "API_HASH": self.hash})

    async def test_get_updates_bad_request_stops_instead_of_retrying_forever(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        call = AsyncMock(side_effect=[
            {"username": "TestHelper"}, {"url": ""}, {},
            self.module.BotSetupError(400, method="getUpdates", description="secret: fake-bot-token " + self.hash),
        ])
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", call):
                with patch.object(self.module.asyncio, "sleep", new=AsyncMock()) as sleep:
                    with patch("builtins.print") as output:
                        self.assertFalse(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual(call.await_count, 4)
        sleep.assert_not_awaited()
        self.assertIn("getUpdates: mã 400", str(output.call_args_list))
        self.assertNotIn("fake-bot-token", str(output.call_args_list))
        self.assertNotIn(self.hash, str(output.call_args_list))

    async def test_invalid_menu_html_is_not_misreported_as_admin_needing_start(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        call = AsyncMock(side_effect=[
            {"username": "TestHelper"}, {"url": ""},
            self.module.BotSetupError(400, method="sendMessage", description="Bad Request: can't parse entities"),
        ])
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", call):
                with patch("builtins.print") as output:
                    self.assertFalse(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual(call.await_count, 3)
        self.assertIn("sendMessage: mã 400", str(output.call_args_list))
        self.assertIn("HTML", str(output.call_args_list))
        self.assertNotIn("Admin cần nhấn Start", str(output.call_args_list))

    async def test_chat_not_found_does_not_stop_polling_for_admin_start(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        call = AsyncMock(side_effect=[
            {"username": "TestHelper"}, {"url": ""},
            self.module.BotSetupError(400, method="sendMessage", description="Bad Request: chat not found"),
            asyncio.CancelledError(),
        ])
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", call):
                with self.assertRaises(asyncio.CancelledError):
                    await self.module.run_api_setup("fake-bot-token", "42")
        self.assertEqual(call.call_args.args[0], "getUpdates")

    async def test_existing_webhook_is_not_removed(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        call = AsyncMock(side_effect=[{"username": "TestHelper"}, {"url": "https://example.com/hook"}])
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", call):
                self.assertFalse(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertEqual([entry.args[0] for entry in call.call_args_list], ["getMe", "getWebhookInfo"])

    async def test_invalid_bot_token_is_reported_without_echoing_it(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", new=AsyncMock(side_effect=self.module.BotSetupError(401))):
                with patch("builtins.print") as output:
                    self.assertFalse(await self.module.run_api_setup("fake-bot-token", "42"))
        self.assertNotIn("fake-bot-token", str(output.call_args_list))

    async def test_admin_not_started_yet_does_not_stop_polling(self):
        session = Mock(__aenter__=AsyncMock(return_value=Mock()), __aexit__=AsyncMock(return_value=False))
        call = AsyncMock(side_effect=[
            {"username": "TestHelper"}, {"url": ""}, self.module.BotSetupError(403), asyncio.CancelledError(),
        ])
        with patch.object(self.module.aiohttp, "ClientSession", return_value=session):
            with patch.object(self.module.BotAPISetup, "call", call):
                with self.assertRaises(asyncio.CancelledError):
                    await self.module.run_api_setup("fake-bot-token", "42")
        self.assertEqual(call.call_args.args[0], "getUpdates")
        session.__aexit__.assert_awaited_once()


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử Bot API")
class BotAPICallTests(unittest.IsolatedAsyncioTestCase):
    def setup_response(self, data, status=400):
        import bot_setup
        self.module = bot_setup
        response = SimpleNamespace(status=status, json=AsyncMock(return_value=data))
        request = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock(return_value=False))
        session = Mock(post=Mock(return_value=request))
        return bot_setup.BotAPISetup(session, "fake-bot-token", "42"), response

    async def test_success_returns_result_without_changing_large_admin_ids(self):
        setup, _ = self.setup_response({"ok": True, "result": {"message_id": 7}}, status=200)
        admin_id = 2 ** 33 + 42
        setup.admin_id = admin_id
        self.assertEqual(await setup.send("test"), {"message_id": 7})
        self.assertEqual(setup.session.post.call_args.kwargs["json"]["chat_id"], admin_id)

    async def test_error_keeps_method_and_safe_reason_not_raw_description(self):
        secret_hash = "a" * 32
        setup, _ = self.setup_response({
            "ok": False, "error_code": 400,
            "description": "Bad Request: query is too old; secret fake-bot-token " + secret_hash,
        })
        with self.assertRaises(self.module.BotSetupError) as caught:
            await setup.call("answerCallbackQuery", callback_query_id="old-query")
        error = caught.exception
        self.assertEqual(error.method, "answerCallbackQuery")
        self.assertEqual(error.reason, "query_expired")
        self.assertIn("answerCallbackQuery: mã 400", str(error))
        for secret in ("fake-bot-token", secret_hash, "old-query"):
            self.assertNotIn(secret, str(error))
            self.assertNotIn(secret, repr(vars(error)))

    async def test_rate_limit_preserves_retry_after(self):
        setup, _ = self.setup_response({"ok": False, "error_code": 429, "parameters": {"retry_after": 5}}, status=429)
        with self.assertRaises(self.module.BotSetupError) as caught:
            await setup.call("getUpdates")
        self.assertEqual(caught.exception.retry_after, 5)
        self.assertEqual(caught.exception.method, "getUpdates")

    async def test_malformed_json_keeps_method_without_logging_response_body(self):
        setup, response = self.setup_response(None, status=502)
        response.json.side_effect = ValueError("fake-bot-token private response")
        with self.assertRaises(self.module.BotSetupError) as caught:
            await setup.call("getUpdates")
        self.assertEqual(caught.exception.method, "getUpdates")
        self.assertEqual(caught.exception.code, 502)
        self.assertNotIn("fake-bot-token", str(caught.exception))

    async def test_non_object_json_is_reported_without_echoing_it(self):
        setup, _ = self.setup_response(["fake-bot-token"], status=502)
        with self.assertRaises(self.module.BotSetupError) as caught:
            await setup.call("getUpdates")
        self.assertEqual(caught.exception.method, "getUpdates")
        self.assertNotIn("fake-bot-token", str(caught.exception))


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử đăng nhập qua bot")
class HelperOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        self.helper = helper_bot
        self.engine = SimpleNamespace(is_running=False, start=AsyncMock(return_value=(True, "started")), stop=AsyncMock())
        self.save = Mock(side_effect=helper_bot.state.config.update)
        for patcher in (
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "BOT_TOKEN": "fake-bot-token", "API_ID": "123", "API_HASH": "a" * 32, "SESSION_STRING": "", "LANGUAGE": "vi"}),
            patch.dict(helper_bot.user_sessions, {}, clear=True),
            patch.object(helper_bot, "engine", self.engine),
            patch.object(helper_bot.state, "update_config", self.save),
            patch.object(helper_bot.state, "reload_config"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = HandlerClient()
        helper_bot.register_bot_handlers(self.client)

    def event(self, text=""):
        return SimpleNamespace(sender_id=42, raw_text=text, reply=AsyncMock(), edit=AsyncMock(), answer=AsyncMock(), delete=AsyncMock())

    async def test_start_opens_setup_for_new_account(self):
        event = self.event("/start")
        await self.client.handlers["start_cmd"](event)
        self.assertIn("CÀI ĐẶT USERBOT", event.reply.call_args.args[0])
        labels = [button.text for row in event.reply.call_args.kwargs["buttons"] for button in row]
        self.assertTrue(any("Đăng nhập Telegram" in label for label in labels))
        self.save.assert_not_called()

    async def test_setup_cancels_pending_login_connection(self):
        temp = SimpleNamespace(disconnect=AsyncMock())
        self.helper.user_sessions[42] = {"action": "login_wait_code", "temp_client": temp}
        await self.client.handlers["setup_cmd"](self.event("/setup"))
        temp.disconnect.assert_awaited_once()
        self.assertNotIn(42, self.helper.user_sessions)

    async def test_setup_callback_uses_the_same_guide(self):
        event = self.event()
        event.data = b"menu_setup"
        await self.client.handlers["callback_handler"](event)
        self.assertIn("CÀI ĐẶT USERBOT", event.edit.call_args.args[0])

    async def test_old_bootstrap_button_opens_current_setup(self):
        event = self.event()
        event.data = b"bootstrap_api"
        await self.client.handlers["callback_handler"](event)
        self.assertIn("CÀI ĐẶT USERBOT", event.edit.call_args.args[0])

    def login_client(self):
        return SimpleNamespace(
            sign_in=AsyncMock(), get_me=AsyncMock(return_value=SimpleNamespace(id=777, first_name="Test", last_name="User", username="test")),
            session=SimpleNamespace(save=Mock(return_value="private-session")), disconnect=AsyncMock(), is_connected=Mock(return_value=True),
        )

    async def test_otp_login_preserves_configured_admin_and_deletes_code(self):
        temp = self.login_client()
        self.helper.user_sessions[42] = {"action": "login_wait_code", "temp_client": temp, "phone": "+123", "phone_code_hash": "hash"}
        event = self.event("1 2 3 4 5")
        await self.client.handlers["user_input_handler"](event)
        temp.sign_in.assert_awaited_once_with(phone="+123", code="12345", phone_code_hash="hash")
        self.save.assert_called_once_with({"SESSION_STRING": "private-session"})
        self.assertEqual(self.helper.state.config["ADMIN_ID"], "42")
        self.engine.start.assert_awaited_once()
        event.delete.assert_awaited_once()

    async def test_2fa_prompt_and_password_keep_the_original_admin(self):
        temp = self.login_client()
        temp.sign_in.side_effect = [self.helper.SessionPasswordNeededError(None), None]
        sess = {"action": "login_wait_code", "temp_client": temp, "phone": "+123", "phone_code_hash": "hash"}
        self.helper.user_sessions[42] = sess
        code_event = self.event("1 2 3 4 5")
        await self.client.handlers["user_input_handler"](code_event)
        self.assertEqual(sess["action"], "login_wait_password")
        self.save.assert_not_called()
        password_event = self.event("private-password")
        await self.client.handlers["user_input_handler"](password_event)
        self.save.assert_called_once_with({"SESSION_STRING": "private-session"})
        self.assertEqual(self.helper.state.config["ADMIN_ID"], "42")
        code_event.delete.assert_awaited_once()
        password_event.delete.assert_awaited_once()

    async def test_invalid_otp_can_be_retried_and_is_deleted(self):
        temp = self.login_client()
        temp.sign_in.side_effect = self.helper.PhoneCodeInvalidError(None)
        sess = {"action": "login_wait_code", "temp_client": temp}
        self.helper.user_sessions[42] = sess
        event = self.event("12345")
        await self.client.handlers["user_input_handler"](event)
        self.assertEqual(sess["action"], "login_wait_code")
        self.save.assert_not_called()
        event.delete.assert_awaited_once()

    async def test_non_admin_cannot_set_up_or_submit_login_credentials(self):
        for handler in ("setup_cmd", "login_cmd", "user_input_handler"):
            event = self.event("12345")
            event.sender_id = 99
            await self.client.handlers[handler](event)
            event.reply.assert_not_awaited()
        self.save.assert_not_called()

    async def test_failed_phone_request_disconnects_the_temporary_client(self):
        temp = SimpleNamespace(connect=AsyncMock(), send_code_request=AsyncMock(side_effect=ValueError("private phone")), disconnect=AsyncMock())
        self.helper.user_sessions[42] = {"action": "login_wait_phone"}
        event = self.event("+123456789")
        with patch.object(self.helper, "TelegramClient", return_value=temp):
            await self.client.handlers["user_input_handler"](event)
        temp.disconnect.assert_awaited_once()
        event.delete.assert_awaited_once()
        self.assertNotIn(42, self.helper.user_sessions)
        self.assertNotIn("private phone", str(event.reply.call_args_list))

    async def test_token_only_startup_hands_off_to_full_helper_without_restart(self):
        self.helper.state.config.update({"API_ID": "", "API_HASH": ""})

        async def bootstrap(token, admin_id):
            self.helper.state.config.update({"API_ID": "123", "API_HASH": "a" * 32})
            return True

        client = SimpleNamespace(
            on=HandlerClient().on,
            start=AsyncMock(), get_me=AsyncMock(return_value=SimpleNamespace(username="TestBot", id=100)),
            send_message=AsyncMock(), run_until_disconnected=AsyncMock(), disconnect=AsyncMock(),
        )
        with patch.object(self.helper, "run_api_setup", new=AsyncMock(side_effect=bootstrap)) as setup:
            with patch.object(self.helper, "TelegramClient", return_value=client) as factory:
                await self.helper.run_standalone_bot()
        setup.assert_awaited_once_with("fake-bot-token", "42")
        factory.assert_called_once_with("helper_bot_session", 123, "a" * 32)
        client.send_message.assert_awaited_once()
        client.disconnect.assert_awaited_once()

    async def test_missing_admin_blocks_bootstrap_and_full_helper(self):
        self.helper.state.config.update({"ADMIN_ID": "", "API_ID": "", "API_HASH": ""})
        with patch.object(self.helper, "run_api_setup", new=AsyncMock()) as setup:
            with patch.object(self.helper, "TelegramClient") as client:
                await self.helper.run_standalone_bot()
        setup.assert_not_awaited()
        client.assert_not_called()

    async def test_terminal_alternative_only_saves_token_and_admin(self):
        import setup
        with patch.object(setup, "getpass", return_value="fake-bot-token"):
            with patch("builtins.input", return_value="42"):
                with patch.object(setup, "save_env") as save:
                    with patch.object(setup.subprocess, "call") as run:
                        setup.run_bot_first_setup({})
        save.assert_called_once_with({"BOT_TOKEN": "fake-bot-token", "ADMIN_ID": "42"})
        self.assertTrue(run.call_args.args[0][-1].endswith("name.py"))


if __name__ == "__main__":
    unittest.main()
