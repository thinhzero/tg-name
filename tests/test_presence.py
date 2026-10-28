import asyncio
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from presence import Presence, elapsed, ping_message, parse_afk_args


class HandlerClient:
    def __init__(self):
        self.handlers = {}

    def on(self, builder):
        def register(handler):
            self.handlers[handler.__name__] = (handler, builder)
            return handler
        return register


class PresenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.presence = Presence(delete_after=100)
        self.addAsyncCleanup(self.presence.close)
        self.presence.enable("đi ngủ <tag>")

    def event(self, *, mentioned=True, reply=False, sender=99, chat=100, bot=False):
        return SimpleNamespace(
            out=False, is_reply=reply, sender_id=sender, chat_id=chat,
            message=SimpleNamespace(mentioned=mentioned, via_bot_id=None),
            get_reply_message=AsyncMock(return_value=SimpleNamespace(sender_id=42)),
            get_sender=AsyncMock(return_value=SimpleNamespace(bot=bot)),
            reply=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())),
        )

    async def test_afk_notice_escapes_reason_and_name(self):
        text = self.presence.notice(name="<owner>")
        self.assertIn("&lt;owner&gt;", text)
        self.assertIn("&lt;tag&gt;", text)
        self.assertNotIn("<tag>", text)

    async def test_mention_replies_once_and_silently(self):
        event = self.event()
        await self.presence.incoming(event, 42, "Owner")
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_awaited_once()
        self.assertTrue(event.reply.call_args.kwargs["silent"])

    async def test_reply_to_owner_triggers_afk(self):
        event = self.event(mentioned=False, reply=True)
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_awaited_once()

    async def test_reply_to_somebody_else_does_not_trigger_afk(self):
        event = self.event(mentioned=False, reply=True)
        event.get_reply_message.return_value.sender_id = 123
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_not_awaited()

    async def test_unrelated_messages_bots_self_and_outgoing_are_ignored(self):
        for event in (self.event(mentioned=False), self.event(bot=True), self.event(sender=42)):
            await self.presence.incoming(event, 42, "Owner")
            event.reply.assert_not_awaited()
        event = self.event()
        event.out = True
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_not_awaited()

    async def test_cooldown_is_per_sender_and_chat(self):
        events = [self.event(), self.event(sender=101), self.event(chat=200)]
        for event in events:
            await self.presence.incoming(event, 42, "Owner")
            event.reply.assert_awaited_once()

    async def test_cooldown_expires(self):
        event = self.event()
        with patch("presence.time.monotonic", return_value=100):
            await self.presence.incoming(event, 42, "Owner")
        with patch("presence.time.monotonic", return_value=161):
            await self.presence.incoming(event, 42, "Owner")
        self.assertEqual(event.reply.await_count, 2)

    async def test_on_disables_afk(self):
        self.presence.disable()
        event = self.event()
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_not_awaited()
        self.assertEqual(self.presence.reason, "")

    async def test_disabling_during_sender_lookup_prevents_late_reply(self):
        event = self.event()
        async def sender():
            self.presence.disable()
            return SimpleNamespace(bot=False)
        event.get_sender.side_effect = sender
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_not_awaited()

    async def test_cleanup_deletes_auto_reply(self):
        self.presence.delete_after = 0
        event = self.event()
        await self.presence.incoming(event, 42, "Owner")
        await asyncio.gather(*self.presence.tasks)
        event.reply.return_value.delete.assert_awaited_once()

    async def test_private_messages_trigger_afk_without_mention_and_log_original_event(self):
        event = self.event(mentioned=False)
        event.is_private = True
        event.id = 456
        with patch("presence.chat_log") as logger:
            await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_awaited_once()
        logger.afk.assert_called_once()
        self.assertIs(logger.afk.call_args.args[0], event)
        self.assertEqual(logger.afk.call_args.args[0].id, 456)

    async def test_afk_logging_is_not_suppressed_by_auto_reply_cooldown(self):
        event = self.event()
        with patch("presence.chat_log") as logger:
            await self.presence.incoming(event, 42, "Owner")
            await self.presence.incoming(event, 42, "Owner")
        self.assertEqual(logger.afk.call_count, 2)
        event.reply.assert_awaited_once()

    async def test_telegram_login_service_is_never_replied_to_or_logged(self):
        event = self.event(sender=777000)
        event.is_private = True
        with patch("presence.chat_log") as logger:
            await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_not_awaited()
        logger.afk.assert_not_called()

    async def test_default_and_custom_deletion_times_are_used(self):
        self.assertEqual(Presence().delete_after, 10)
        for argument, seconds in (("ngủ", 10), ("30s ngủ", 30), ("30 ngủ", 30)):
            delay, reason = parse_afk_args(argument)
            self.presence.enable(reason, delete_after=delay)
            event = self.event()
            with patch("presence.asyncio.sleep", new=AsyncMock()) as sleep:
                await self.presence.incoming(event, 42, "Owner")
                await asyncio.gather(*self.presence.tasks)
            sleep.assert_awaited_once_with(seconds)
            event.reply.return_value.delete.assert_awaited_once()

    async def test_changing_afk_does_not_change_an_existing_reply_lifetime(self):
        self.presence.enable("first", delete_after=30)
        event = self.event()
        with patch("presence.asyncio.sleep", new=AsyncMock()) as sleep:
            await self.presence.incoming(event, 42, "Owner")
            self.presence.enable("second", delete_after=10)
            await asyncio.gather(*self.presence.tasks)
        sleep.assert_awaited_once_with(30)

    async def test_deletion_errors_are_nonfatal(self):
        event = self.event()
        event.reply.return_value.delete.side_effect = RuntimeError("no permission")
        with patch("presence.asyncio.sleep", new=AsyncMock()):
            await self.presence.incoming(event, 42, "Owner")
            await asyncio.gather(*self.presence.tasks)
        event.reply.return_value.delete.assert_awaited_once()

    async def test_on_during_send_removes_the_late_auto_reply(self):
        event = self.event()
        message = SimpleNamespace(delete=AsyncMock())
        async def send(*args, **kwargs):
            self.presence.disable()
            return message
        event.reply.side_effect = send
        await self.presence.incoming(event, 42, "Owner")
        message.delete.assert_awaited_once()
        self.assertFalse(self.presence.tasks)

    async def test_cooldown_cache_is_bounded(self):
        self.presence.replies.update({(1, sender): 1 for sender in range(1024)})
        await self.presence.incoming(self.event(), 42, "Owner")
        self.assertEqual(len(self.presence.replies), 1024)
        self.assertNotIn((1, 0), self.presence.replies)

    async def test_failed_sends_do_not_retry_on_every_message(self):
        event = self.event()
        event.reply.side_effect = RuntimeError("no permission")
        await self.presence.incoming(event, 42, "Owner")
        await self.presence.incoming(event, 42, "Owner")
        event.reply.assert_awaited_once()

    async def test_close_cancels_pending_cleanup_tasks(self):
        await self.presence.incoming(self.event(), 42, "Owner")
        tasks = list(self.presence.tasks)
        await self.presence.close()
        self.assertTrue(all(task.done() for task in tasks))
        self.assertFalse(self.presence.active)
        self.assertFalse(self.presence.tasks)

    async def test_duration_format(self):
        self.assertEqual(elapsed(90061), "1d 1h 1m 1s")
        self.assertEqual(elapsed(-1), "0d 0h 0m 0s")


class PingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_without_host_only_edits_one_message(self):
        edit = AsyncMock()
        process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"google reply", None)))
        with patch("presence.shutil.which", return_value="/ping"):
            with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as create:
                await ping_message("", edit)
        self.assertEqual(edit.await_count, 2)
        self.assertIn("Uptime", edit.call_args.args[0])
        self.assertIn("Telegram", edit.call_args.args[0])
        self.assertEqual(create.call_args.args[-1], "google.com")
        self.assertIn("google.com", edit.call_args.args[0])

    async def test_bad_hosts_urls_and_flags_never_execute(self):
        with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock()) as create:
            for target in ("-f", "example.com; id", "https://example.com", "a b", "a" * 254):
                edit = AsyncMock()
                await ping_message(target, edit)
                edit.assert_awaited_once()
        create.assert_not_awaited()

    async def test_missing_ping_binary_has_install_hint(self):
        edit = AsyncMock()
        with patch("presence.shutil.which", return_value=None):
            await ping_message("example.com", edit)
        self.assertIn("pkg install iputils", edit.call_args.args[0])

    async def test_ping_uses_argv_and_escapes_output(self):
        edit = AsyncMock()
        process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"<reply>&", None)))
        with patch("presence.shutil.which", return_value="/termux/usr/bin/ping"):
            with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as create:
                await ping_message("::1", edit)
        self.assertEqual(create.call_args.args, ("/termux/usr/bin/ping", "-c", "1", "-W", "2", "::1"))
        self.assertIn("&lt;reply&gt;&amp;", edit.call_args.args[0])

    async def test_explicit_ping_host_replaces_google_instead_of_adding_a_second_ping(self):
        process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"target reply", None)))
        edit = AsyncMock()
        with patch("presence.shutil.which", return_value="/ping"):
            with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as create:
                await ping_message("yotube.com", edit)
        create.assert_awaited_once()
        self.assertEqual(create.call_args.args[-1], "yotube.com")
        self.assertNotIn("google.com", edit.call_args.args[0])

    async def test_timeout_kills_and_reaps_ping(self):
        edit = AsyncMock()
        process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=[asyncio.TimeoutError(), (b"", None)]), kill=Mock())
        with patch("presence.shutil.which", return_value="/ping"):
            with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                await ping_message("example.com", edit)
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)
        self.assertIn("thời gian", edit.call_args.args[0])

    async def test_cancellation_kills_ping(self):
        process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=[asyncio.CancelledError(), (b"", None)]), kill=Mock())
        with patch("presence.shutil.which", return_value="/ping"):
            with patch("presence.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                with self.assertRaises(asyncio.CancelledError):
                    await ping_message("example.com", AsyncMock())
        process.kill.assert_called_once()


class AfkArgumentTests(unittest.TestCase):
    def test_optional_seconds_and_reason(self):
        for argument, result in (
            ("", (10, "")), ("đi ngủ", (10, "đi ngủ")),
            ("30s đi ngủ", (30, "đi ngủ")), ("30 đi ngủ", (30, "đi ngủ")),
            ("30", (30, "")), ("  2m  ăn cơm  ", (120, "ăn cơm")),
            ("1H ngủ", (3600, "ngủ")), ("24h", (86400, "")),
            ("hẹn 30s nữa", (10, "hẹn 30s nữa")), ("<tag> & lý do", (10, "<tag> & lý do")),
        ):
            with self.subTest(argument=argument):
                self.assertEqual(parse_afk_args(argument), result)

    def test_invalid_numeric_durations(self):
        for argument in ("0", "0s ngủ", "-1 đi ngủ", "+30 ngủ", "1.5s ngủ", "86401", "25h", "9" * 5000):
            with self.subTest(argument=argument[:30]), self.assertRaises(ValueError):
                parse_afk_args(argument)


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử lệnh Userbot")
class PresenceHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import helper_bot
        self.helper = helper_bot
        self.presence = Presence()
        for patcher in (
            patch.object(helper_bot, "presence", self.presence),
            patch.dict(helper_bot.state.config, {"ADMIN_ID": "42", "LANGUAGE": "vi"}),
            patch("presence.shutil.which", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addAsyncCleanup(self.presence.close)
        self.client = HandlerClient()
        helper_bot.register_userbot_handlers(self.client)

    async def command(self, text):
        handler, builder = self.client.handlers["userbot_command_handler"]
        event = SimpleNamespace(pattern_match=builder.pattern(text), edit=AsyncMock(), delete=AsyncMock(), respond=AsyncMock(), reply=AsyncMock())
        self.assertIsNotNone(event.pattern_match)
        self.assertTrue(builder.outgoing)
        await handler(event)
        return event

    async def test_afk_and_on_are_owner_commands_and_edit_or_delete_the_command(self):
        event = await self.command(".afk đi ngủ")
        self.assertTrue(self.presence.active)
        self.assertEqual(self.presence.reason, "đi ngủ")
        event.edit.assert_awaited_once()
        event.respond.assert_not_awaited()
        event = await self.command(".on")
        event.delete.assert_awaited_once()
        self.assertFalse(self.presence.active)

    async def test_ping_has_one_handler_and_never_sends_followup(self):
        event = await self.command(".ping")
        self.assertEqual(event.edit.await_count, 2)
        event.respond.assert_not_awaited()
        event.reply.assert_not_awaited()
        _, builder = self.client.handlers["afk_incoming_handler"]
        self.assertTrue(builder.incoming)

    async def helper_command(self, text, running=True, sender=42):
        client = HandlerClient()
        self.helper.register_bot_handlers(client)
        handler, builder = client.handlers["presence_cmd"]
        event = SimpleNamespace(
            sender_id=sender, chat_id=sender, is_private=True, raw_text=text, data=None,
            pattern_match=builder.pattern(text), reply=AsyncMock(), respond=AsyncMock(), edit=AsyncMock(),
        )
        with patch.object(self.helper, "engine", SimpleNamespace(is_running=running)):
            await handler(event)
        return event

    async def test_helper_admin_can_enable_afk_and_return_online(self):
        await self.helper_command("/afk ngủ")
        self.assertTrue(self.presence.active)
        self.assertEqual(self.presence.reason, "ngủ")
        await self.helper_command("/on")
        self.assertFalse(self.presence.active)

    async def test_both_transports_accept_duration_and_reset_to_default(self):
        for command in (self.command, self.helper_command):
            prefix = "." if command == self.command else "/"
            await command(prefix + "afk 30s đi ngủ")
            self.assertEqual(self.presence.reason, "đi ngủ")
            self.assertEqual(self.presence.delete_after, 30)
            await command(prefix + "afk 45 đi ngủ")
            self.assertEqual(self.presence.delete_after, 45)
            await command(prefix + "afk đi ngủ")
            self.assertEqual(self.presence.delete_after, 10)

    async def test_invalid_duration_does_not_change_current_afk(self):
        self.presence.enable("keep", delete_after=30)
        since = self.presence.since
        event = await self.command(".afk 0s invalid")
        self.assertIn("24h", event.edit.call_args.args[0])
        await self.helper_command("/afk -10 invalid")
        self.assertEqual(self.presence.since, since)
        self.assertEqual(self.presence.reason, "keep")
        self.assertEqual(self.presence.delete_after, 30)

    async def test_helper_afk_requires_running_userbot(self):
        event = await self.helper_command("/afk ngủ", running=False)
        self.assertFalse(self.presence.active)
        self.assertIn("Userbot", event.reply.call_args.args[0])

    async def test_helper_afk_rejects_non_admin(self):
        event = await self.helper_command("/afk ngủ", sender=99)
        self.assertFalse(self.presence.active)
        event.reply.assert_not_awaited()

    async def test_helper_ping_never_edits_the_users_command(self):
        event = await self.helper_command("/ping")
        event.edit.assert_not_awaited()
        event.respond.assert_awaited_once()
        event.respond.return_value.edit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
