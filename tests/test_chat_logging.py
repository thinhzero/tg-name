import asyncio
import html
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from chat_logging import AFK_FIELDS, ChatLogger, message_link, selections


class ChatLogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = {"ADMIN_ID": "42", "LANGUAGE": "vi", "LOG_CHAT_ID": "-1000000000123", "LOG_TYPES": "afk,error,update", "LOG_AFK_FIELDS": ",".join(sorted(AFK_FIELDS)), "API_HASH": "private-api-hash", "API_ID": "12345678"}
        self.client = SimpleNamespace(send_message=AsyncMock())
        self.logger = ChatLogger(interval=0)
        self.logger.bind(self.client, lambda: self.config)
        self.addAsyncCleanup(self.logger.close, drain=False)

    async def flush(self):
        await self.logger.queue.join()

    def event(self, chat=99):
        return SimpleNamespace(chat_id=chat, id=456, sender_id=99, chat=SimpleNamespace(title="<private chat>"), message=SimpleNamespace(id=456, raw_text="PRIVATE MESSAGE BODY"))

    async def test_message_links_cover_channels_private_groups_dms_and_basic_groups(self):
        self.assertEqual(message_link(self.event(-1000000000123)), "https://t.me/c/123/456")
        self.assertEqual(message_link(self.event(99)), "tg://openmessage?user_id=99&message_id=456")
        self.assertEqual(message_link(self.event(-99)), "tg://openmessage?chat_id=99&message_id=456")
        event = self.event()
        event.id = None
        event.message.id = None
        self.assertIsNone(message_link(event))

    async def test_afk_is_mandatory_but_optional_types_can_be_disabled(self):
        self.config["LOG_TYPES"] = "profile"
        self.assertTrue(self.logger.afk(self.event(), SimpleNamespace(first_name="<Alice>"), "away", "1m"))
        self.assertFalse(self.logger.emit("command", {"command": ".ping"}))
        await self.flush()
        self.client.send_message.assert_awaited_once()
        text = self.client.send_message.call_args.args[1]
        self.assertIn("user_id=99&message_id=456", html.unescape(text))
        self.assertIn("&lt;Alice&gt;", text)
        self.assertNotIn("PRIVATE MESSAGE BODY", text)
        self.assertTrue(self.client.send_message.call_args.kwargs["silent"])
        self.assertFalse(self.client.send_message.call_args.kwargs["link_preview"])

    async def test_all_afk_details_can_be_hidden_but_the_original_link_remains(self):
        self.config["LOG_AFK_FIELDS"] = "-"
        self.logger.afk(self.event(), SimpleNamespace(first_name="Alice"), "secret reason", "5m")
        await self.flush()
        text = self.client.send_message.call_args.args[1]
        self.assertIn("message_id=456", text)
        for value in ("Alice", "secret reason", "5m", "private chat"):
            self.assertNotIn(value, text)

    async def test_no_afk_log_without_original_message_link(self):
        self.assertFalse(self.logger.emit("afk", {"reason": "away"}))
        self.client.send_message.assert_not_awaited()

    async def test_known_credentials_and_html_are_redacted_before_delivery(self):
        self.logger.emit("error", {"error": "private-api-hash 12345678 <bad>"})
        await self.flush()
        text = self.client.send_message.call_args.args[1]
        self.assertNotIn("private-api-hash", text)
        self.assertNotIn("12345678", text)
        self.assertIn("&lt;bad&gt;", text)

    async def test_disabling_or_reconfiguring_logging_discards_queued_old_messages(self):
        self.logger.emit("error", {"error": "old event"})
        self.config["LOG_CHAT_ID"] = ""
        await self.flush()
        self.client.send_message.assert_not_awaited()
        self.config["LOG_CHAT_ID"] = "42"
        self.logger.emit("error", {"error": "new event"})
        await self.flush()
        self.assertEqual(self.client.send_message.call_args.args[0], 42)

    async def test_delivery_failure_is_nonfatal_and_never_logs_the_raw_exception(self):
        self.client.send_message.side_effect = RuntimeError("private-api-hash private-url")
        with patch("builtins.print") as output:
            self.logger.emit("error", {"error": "an error"})
            await self.flush()
        self.assertEqual(self.logger.last_error, "RuntimeError")
        self.assertNotIn("private-", str(output.call_args_list))
        self.assertEqual(self.logger.queue.qsize(), 0)

    async def test_queue_is_bounded_and_afk_can_displace_an_older_event(self):
        for _ in range(100):
            self.assertTrue(self.logger.emit("error", {"error": "event"}))
        self.assertFalse(self.logger.emit("error", {"error": "extra"}))
        self.assertTrue(self.logger.afk(self.event(), SimpleNamespace(first_name="Alice"), "away", "1m"))
        self.assertEqual(self.logger.queue.qsize(), 100)
        self.assertEqual(self.logger.dropped, 2)
        await self.flush()
        self.assertIn("message_id=456", self.client.send_message.call_args.args[1])

    async def test_shutdown_can_discard_a_blocked_delivery_and_wait_for_worker(self):
        started = asyncio.Event()
        async def send(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        self.client.send_message.side_effect = send
        self.logger.emit("error", {"error": "event"})
        await started.wait()
        worker = self.logger.worker
        await self.logger.close(drain=False)
        self.assertTrue(worker.done())
        self.assertIsNone(self.logger.client)

    async def test_log_destination_is_resolved_again_after_string_session_restart(self):
        self.client.get_input_entity = AsyncMock(side_effect=ValueError("entity cache empty"))
        async def dialogs():
            yield SimpleNamespace(id=99, input_entity="wrong peer")
            yield SimpleNamespace(id=-1000000000123, input_entity="restored peer")
        self.client.iter_dialogs = dialogs
        self.logger.emit("error", {"error": "first"})
        self.logger.emit("error", {"error": "second"})
        await self.flush()
        self.client.get_input_entity.assert_awaited_once()
        self.assertEqual(self.client.send_message.call_args.args[0], "restored peer")


@unittest.skipUnless(importlib.util.find_spec("telethon"), "Cài Telethon để kiểm thử bảng inline")
class LogInlineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await ChatLogTests.asyncSetUp(self)
        self.controls = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(id=800)))
        self.logger.bind_controls(self.controls, lambda: self.config)
        self.state = SimpleNamespace(config=self.config, account_id="42", is_resetting=False, update_config=Mock(side_effect=self.config.update))

    async def panel(self):
        self.assertTrue(await self.logger.show_controls(-1000000000123, self.state))
        return next(reversed(self.logger.cards))

    def callback(self, nonce, action, sender=42, chat=-1000000000123, message=800):
        return SimpleNamespace(data=f"logcfg:{nonce}:{action}".encode(), sender_id=sender, chat_id=chat, message_id=message, edit=AsyncMock(), answer=AsyncMock())

    async def test_control_panel_uses_helper_bot_and_falls_back_to_admin_private_chat(self):
        self.controls.send_message.side_effect = [RuntimeError("no permission"), SimpleNamespace(id=801)]
        self.assertTrue(await self.logger.show_controls(-1000000000123, self.state))
        calls = self.controls.send_message.call_args_list
        self.assertEqual([call.args[0] for call in calls], [-1000000000123, 42])
        self.client.send_message.assert_not_awaited()
        card = next(iter(self.logger.cards.values()))
        self.assertEqual((card["chat"], card["message"]), (42, 801))
        labels = [button.text for row in calls[-1].kwargs["buttons"] for button in row]
        self.assertTrue(any("✅ AFK" in label for label in labels))
        self.assertTrue(any("❌" in label for label in labels))

    async def test_inline_mode_is_preferred_and_does_not_require_bot_membership(self):
        result = SimpleNamespace(click=AsyncMock(return_value=SimpleNamespace(id=900)))
        self.client.inline_query = AsyncMock(return_value=[result])
        self.logger.control_username = "MyHelperBot"
        self.assertTrue(await self.logger.show_controls(-1000000000123, self.state))
        self.client.inline_query.assert_awaited_once()
        self.assertEqual(self.client.inline_query.call_args.args[0], "MyHelperBot")
        self.assertTrue(self.client.inline_query.call_args.args[1].startswith("tgname_log "))
        result.click.assert_awaited_once_with(-1000000000123, silent=True)
        self.controls.send_message.assert_not_awaited()
        self.assertTrue(next(iter(self.logger.cards.values()))["inline"])

    async def test_real_telethon_builder_can_serialize_the_inline_settings_without_connecting(self):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.custom.inlinebuilder import InlineBuilder
        client = TelegramClient(StringSession(), 123, "a" * 32)
        try:
            text, buttons = self.logger.panel("a" * 12, -1000000000123, self.config)
            result = await InlineBuilder(client).article("Log settings", id="log_test", text=text, parse_mode="html", buttons=buttons, link_preview=False)
            self.assertTrue(bytes(result))
            self.assertFalse(client.is_connected())
        finally:
            await client.disconnect()

    async def test_disabled_inline_mode_falls_back_to_a_direct_helper_message(self):
        self.client.inline_query = AsyncMock(side_effect=RuntimeError("inline mode disabled"))
        self.logger.control_username = "MyHelperBot"
        self.assertTrue(await self.logger.show_controls(-1000000000123, self.state))
        self.controls.send_message.assert_awaited_once()
        self.assertFalse(next(iter(self.logger.cards.values()))["inline"])

    async def test_inline_query_requires_owner_and_valid_nonce_and_is_never_globally_cached(self):
        nonce = await self.panel()
        self.logger.cards[nonce]["inline"] = True
        event = SimpleNamespace(text=f"tgname_log {nonce}", sender_id=42, builder=SimpleNamespace(article=AsyncMock(return_value="article")), answer=AsyncMock())
        await self.logger.inline(event, self.state)
        event.answer.assert_awaited_once_with(["article"], cache_time=0, private=True)
        event.sender_id = 99
        event.answer.reset_mock()
        await self.logger.inline(event, self.state)
        event.answer.assert_awaited_once_with([], cache_time=0, private=True)

    async def test_inline_callbacks_use_native_message_identity_instead_of_a_fake_chat_id(self):
        from telethon.tl import types
        result = SimpleNamespace(click=AsyncMock(return_value=SimpleNamespace(id=900)))
        self.client.inline_query = AsyncMock(return_value=[result])
        self.logger.control_username = "MyHelperBot"
        self.assertTrue(await self.logger.show_controls(-1000000000123, self.state))
        nonce = next(iter(self.logger.cards))
        event = self.callback(nonce, "cat_profile", chat=0, message=0)
        event.query = SimpleNamespace(msg_id=types.InputBotInlineMessageID64(dc_id=2, owner_id=42, id=900, access_hash=1234))
        await self.logger.button(event, self.state)
        event.edit.assert_awaited_once()
        self.assertIn("profile", selections(self.config)[0])
        copied = self.callback(nonce, "cat_error", chat=0, message=0)
        copied.query = SimpleNamespace(msg_id=types.InputBotInlineMessageID64(dc_id=2, owner_id=42, id=901, access_hash=1235))
        await self.logger.button(copied, self.state)
        copied.edit.assert_not_awaited()
        self.assertTrue(copied.answer.call_args.kwargs["alert"])

    async def test_inline_toggle_updates_the_same_message_not_a_new_message(self):
        nonce = await self.panel()
        event = self.callback(nonce, "cat_profile")
        await self.logger.button(event, self.state)
        self.assertIn("profile", selections(self.config)[0])
        event.edit.assert_awaited_once()
        self.controls.send_message.assert_awaited_once()
        self.assertTrue(any("✅ Tên / bio" in button.text for row in event.edit.call_args.kwargs["buttons"] for button in row))
        await self.logger.button(self.callback(nonce, "field_reason"), self.state)
        self.assertNotIn("reason", selections(self.config)[1])

    async def test_afk_button_is_locked_and_never_updates_config(self):
        nonce = await self.panel()
        event = self.callback(nonce, "cat_afk")
        await self.logger.button(event, self.state)
        self.state.update_config.assert_not_called()
        event.edit.assert_not_awaited()
        self.assertTrue(event.answer.call_args.kwargs["alert"])

    async def test_other_users_wrong_message_and_stale_cards_are_rejected(self):
        nonce = await self.panel()
        for event in (self.callback(nonce, "cat_profile", sender=99), self.callback(nonce, "cat_profile", chat=99), self.callback(nonce, "cat_profile", message=801)):
            await self.logger.button(event, self.state)
            event.edit.assert_not_awaited()
            self.assertTrue(event.answer.call_args.kwargs["alert"])
        self.config["LOG_TYPES"] = "afk"
        await self.logger.button(self.callback(nonce, "cat_profile"), self.state)
        self.state.update_config.assert_not_called()

    async def test_master_toggle_disables_and_reenables_without_disabling_afk_selection(self):
        nonce = await self.panel()
        await self.logger.button(self.callback(nonce, "enabled"), self.state)
        self.assertFalse(self.logger.target())
        self.assertIn("afk", selections(self.config)[0])
        await self.logger.button(self.callback(nonce, "enabled"), self.state)
        self.assertEqual(self.logger.target(), -1000000000123)

    async def test_inline_privacy_change_discards_pending_old_afk_fields(self):
        nonce = await self.panel()
        self.logger.afk(SimpleNamespace(chat_id=99, id=456, sender_id=99, chat=None), SimpleNamespace(first_name="Alice"), "private reason", "1m")
        await self.logger.button(self.callback(nonce, "field_reason"), self.state)
        await self.logger.queue.join()
        self.client.send_message.assert_not_awaited()

    async def test_saved_config_is_not_reported_as_unsaved_when_panel_edit_fails(self):
        nonce = await self.panel()
        event = self.callback(nonce, "cat_profile")
        event.edit.side_effect = RuntimeError("connection lost")
        await self.logger.button(event, self.state)
        self.assertIn("profile", selections(self.config)[0])
        self.assertIn("Đã lưu", event.answer.call_args.args[0])
        self.assertNotIn(nonce, self.logger.cards)

    async def test_write_failure_does_not_change_inline_ticks_or_configuration(self):
        nonce = await self.panel()
        self.state.update_config.side_effect = PermissionError("denied")
        event = self.callback(nonce, "cat_profile")
        await self.logger.button(event, self.state)
        self.assertNotIn("profile", selections(self.config)[0])
        event.edit.assert_not_awaited()
        self.assertIn("Chưa lưu", event.answer.call_args.args[0])

    async def test_loghere_persists_target_and_unloghere_only_applies_to_that_chat(self):
        event = SimpleNamespace(chat_id=-1000000000123, sender_id=42, edit=AsyncMock())
        await self.logger.command(event, "loghere", "profile", self.client, self.state)
        self.assertEqual(self.config["LOG_TYPES"], "afk,profile")
        other = SimpleNamespace(chat_id=99, sender_id=42, edit=AsyncMock())
        await self.logger.command(other, "unloghere", "", self.client, self.state)
        self.assertEqual(self.logger.target(), -1000000000123)
        await self.logger.command(event, "unloghere", "", self.client, self.state)
        self.assertFalse(self.logger.target())

    async def test_bad_log_types_do_not_save_config(self):
        event = SimpleNamespace(chat_id=99, sender_id=42, edit=AsyncMock())
        await self.logger.command(event, "logconfig", "passwords", self.client, self.state)
        self.state.update_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
