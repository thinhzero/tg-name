"""Khởi tạo qua Bot API khi máy mới chỉ có BOT_TOKEN và ADMIN_ID."""

import asyncio
import re
import time

import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession

from updater_state import state
from bot_updater import bot_updater, run_update_check, run_update_action, update_requests, notify_update_completed
from reset_control import reset_requests, reset_notice, reset_buttons, apply_config_reset, cleanup_reset_sessions
from i18n import get_text
from shell_commands import shell_runner, run_shell_message, config_secrets
from presence import ping_message
from bot_commands import command_menu
from network_tools import lookup_message


API_ERROR_HINTS = {
    "query_expired": "Nút bấm đã hết hạn; hãy bấm lại trong Telegram.",
    "chat_not_found": "Kiểm tra ADMIN_ID và nhấn Start bằng đúng tài khoản admin.",
    "bot_not_started": "Admin cần nhấn Start trong chat riêng với bot.",
    "bot_blocked": "Admin cần bỏ chặn bot rồi nhấn Start.",
    "invalid_html": "Tin nhắn của bot có định dạng HTML không hợp lệ.",
    "message_not_modified": "Nội dung tin nhắn không thay đổi.",
    "message_uneditable": "Tin giao diện đã bị xóa hoặc không còn sửa được.",
}


class BotSetupError(Exception):
    def __init__(self, code, retry_after=0, *, method="", description=""):
        # Chỉ giữ phương thức nội bộ và lý do được nhận diện; không lưu/in mô tả
        # thô, URL (chứa token), request, nội dung chat hay API hash vào lỗi/log.
        self.code = code
        self.retry_after = retry_after
        self.method = method
        self.reason = ""
        description = description.lower() if isinstance(description, str) else ""
        for reason, phrases in (
            ("query_expired", ("query is too old", "query id is invalid", "response timeout expired")),
            ("chat_not_found", ("chat not found",)),
            ("bot_not_started", ("bot can't initiate conversation",)),
            ("bot_blocked", ("bot was blocked",)),
            ("invalid_html", ("can't parse entities", "unsupported start tag",)),
            ("message_not_modified", ("message is not modified",)),
            ("message_uneditable", ("message to edit not found", "message can't be edited", "message_id_invalid")),
        ):
            if any(phrase in description for phrase in phrases):
                self.reason = reason
                break
        super().__init__(self.diagnostic())

    def diagnostic(self):
        detail = f"{self.method or 'request'}: mã {self.code}"
        if self.reason:
            detail += f" — {API_ERROR_HINTS[self.reason]}"
        return detail


class BotAPISetup:
    def __init__(self, session, token, admin_id):
        self.session = session
        self.token = token
        self.admin_id = int(admin_id)
        self.action = None
        self.api_id = ""
        self.started_at = int(time.time())
        self.panel_message_id = None
        self.input_panel_message_id = None
        self._input_response = False

    def text(self, vi, en):
        return en if state.config.get("LANGUAGE") == "en" else vi

    async def register_commands(self):
        try:
            await self.call(
                "setMyCommands", commands=command_menu(state.config.get("LANGUAGE", "vi"), bootstrap=True),
                scope={"type": "chat", "chat_id": self.admin_id}, language_code="",
            )
            return True
        except Exception as exc:
            print(f"[ℹ️] Chưa đồng bộ gợi ý lệnh ({type(exc).__name__}); gửi /start để thử lại.")
            return False

    async def notify_completed(self):
        async def send_completed(text, parse_mode="html"):
            await self.call("sendMessage", chat_id=self.admin_id, text=text, parse_mode="HTML")
        return await notify_update_completed(send_completed, self.admin_id, state.config.get("LANGUAGE", "vi"))

    async def call(self, method, **payload):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        async with self.session.post(url, json=payload) as response:
            try:
                data = await response.json(content_type=None)
            except ValueError as exc:
                raise BotSetupError(response.status, method=method) from exc
        if not isinstance(data, dict):
            raise BotSetupError(response.status, method=method)
        if not data.get("ok"):
            raise BotSetupError(
                data.get("error_code", response.status), data.get("parameters", {}).get("retry_after", 0),
                method=method, description=data.get("description", ""),
            )
        return data.get("result")

    async def send(self, text, keyboard=None):
        rows = [list(row) for row in (keyboard or [])]
        if not any(button.get("callback_data") == "main_menu" for row in rows for button in row):
            rows.append([{"text": "🏠 Home", "callback_data": "main_menu"}])
        payload = {"chat_id": self.admin_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": rows}}
        if self.panel_message_id is not None:
            try:
                result = await self.call("editMessageText", message_id=self.panel_message_id, **payload)
                return result if isinstance(result, dict) and "message_id" in result else {"message_id": self.panel_message_id}
            except BotSetupError as exc:
                if exc.reason == "message_not_modified":
                    return {"message_id": self.panel_message_id}
                if exc.reason != "message_uneditable":
                    raise
                self.panel_message_id = None
        result = await self.call("sendMessage", disable_notification=True, **payload)
        if isinstance(result, dict) and isinstance(result.get("message_id"), int):
            self.panel_message_id = result["message_id"]
        return result

    def cancel_keyboard(self):
        return [[{"text": self.text("❌ Hủy / Nhập lại", "❌ Cancel / Start over"), "callback_data": "bootstrap_cancel"}]]

    async def show_menu(self):
        await self.send(self.text(
            "🛠 <b>CÀI ĐẶT QUA TELEGRAM</b>\n\n"
            "Bot đã nhận ADMIN_ID từ .env; chỉ tài khoản này được cấu hình.\n"
            "Bước 1: bấm nút bên dưới để nhập <b>API_ID</b> và <b>API_HASH riêng</b> từ my.telegram.org/apps.\n"
            "Sau đó bot sẽ mở các nút đăng nhập Telegram, đổi tên, múi giờ và định dạng.\n\n"
            "Không gửi lại BOT_TOKEN, OTP hoặc mật khẩu vào bước nhập API.",
            "🛠 <b>TELEGRAM SETUP</b>\n\n"
            "ADMIN_ID was read from .env; only this account can configure the bot.\n"
            "Step 1: use the button below to enter your own <b>API_ID</b> and <b>API_HASH</b> from my.telegram.org/apps.\n"
            "The bot will then offer Telegram login, name, timezone and format settings.\n\n"
            "Do not send BOT_TOKEN, OTP or passwords in the API step."
        ), [
            [{"text": self.text("1️⃣ Nhập API_ID / API_HASH", "1️⃣ Enter API_ID / API_HASH"), "callback_data": "bootstrap_api"}],
            [{"text": "🌐 my.telegram.org/apps", "url": "https://my.telegram.org/apps"}],
            [{"text": "🇻🇳 Tiếng Việt", "callback_data": "bootstrap_vi"}, {"text": "🇬🇧 English", "callback_data": "bootstrap_en"}],
            [{"text": get_text("btn_check_updates", state.config.get("LANGUAGE", "vi")), "callback_data": "updatecheck"}],
            [{"text": self.text("🧹 Đặt lại cấu hình", "🧹 Reset settings"), "callback_data": "reset_request"}],
        ])

    def authorized(self, message, sender):
        chat = message.get("chat", {})
        return chat.get("type") == "private" and chat.get("id") == self.admin_id and sender.get("id") == self.admin_id

    async def validate_api(self, api_hash):
        # Kiểm tra cặp API bằng phiên bot trong RAM; không dùng API key chung,
        # không tạo file session và không đăng nhập tài khoản người dùng ở đây.
        client = TelegramClient(StringSession(), int(self.api_id), api_hash)
        try:
            await asyncio.wait_for(client.start(bot_token=self.token), timeout=30)
        finally:
            await asyncio.wait_for(client.disconnect(), timeout=10)

    async def handle(self, update):
        self._input_response = False
        try:
            return await self._handle(update)
        finally:
            if self.action is None:
                self.input_panel_message_id = None
            elif self._input_response:
                self.input_panel_message_id = self.panel_message_id

    async def _handle(self, update):
        if state.is_resetting:
            return False
        callback = update.get("callback_query")
        if callback:
            if not self.authorized(callback.get("message", {}), callback.get("from", {})):
                return False
            message_id = callback.get("message", {}).get("message_id")
            if isinstance(message_id, int):
                self.panel_message_id = message_id
            try:
                await self.call("answerCallbackQuery", callback_query_id=callback["id"])
            except BotSetupError as exc:
                if exc.code != 400 or exc.reason != "query_expired":
                    raise
                print(f"[ℹ️] Bot API {exc.diagnostic()}")
                return False
            data = callback.get("data", "")
            if data.startswith(("update_confirm:", "update_cancel:")):
                action, token = data.split(":", 1)
                await run_update_action(
                    self.update_edit, self.admin_id, token, state.config.get("LANGUAGE", "vi"), updater=bot_updater,
                    confirm=action == "update_confirm", secret_values=[*config_secrets(state.config), state.config.get("API_ID", "")],
                )
            elif data == "updatecheck":
                await self.check_update()
            elif data == "reset_request":
                await self.offer_reset()
            elif data.startswith("reset_cancel:"):
                reset_requests.consume(self.admin_id, data.split(":", 1)[1])
                await self.show_menu()
            elif data.startswith("reset_confirm:"):
                if not reset_requests.consume(self.admin_id, data.split(":", 1)[1]):
                    await self.send(self.text("⚠️ Xác nhận đã hết hạn/đã dùng. Gửi /reset để mở lại.", "⚠️ Reset expired. Send /reset again."))
                    return False
                state.is_resetting = True
                try:
                    apply_config_reset()
                    cleanup_reset_sessions()
                except Exception as exc:
                    state.is_resetting = False
                    await self.send(self.text(f"❌ Reset chưa hoàn tất ({type(exc).__name__}).", f"❌ Reset failed ({type(exc).__name__})."))
                    return False
                self.action = None
                self.api_id = ""
                try:
                    await self.send(self.text("✅ Chỉ giữ BOT_TOKEN + ADMIN_ID. Đang khởi động lại...", "✅ Kept BOT_TOKEN + ADMIN_ID only. Restarting..."))
                finally:
                    bot_updater.request_restart()
            elif data == "bootstrap_api":
                self._input_response = True
                self.action = "api_id"
                self.api_id = ""
                await self.send(self.text("🆔 Gửi <b>API_ID</b> của bạn (số dương):", "🆔 Send your <b>API_ID</b> (a positive number):"), self.cancel_keyboard())
            elif data in ("main_menu", "bootstrap_cancel", "bootstrap_vi", "bootstrap_en"):
                update_requests.cancel(self.admin_id)
                self.action = None
                self.api_id = ""
                if data in ("bootstrap_vi", "bootstrap_en"):
                    state.update_config({"LANGUAGE": data.rsplit("_", 1)[1]})
                    await self.register_commands()
                await self.show_menu()
            return False

        message = update.get("message", {})
        if not self.authorized(message, message.get("from", {})):
            return False
        # Không diễn giải lại API/OTP cũ còn trong hàng đợi sau khi khởi động.
        if message.get("date", 0) < self.started_at:
            return False
        text = message.get("text", "").strip()
        if not text:
            return False
        command = text.split()[0].split("@", 1)[0]
        if text.startswith("/") and command != "/shell":
            # Chỉ lần gọi lệnh mới mở tin mới; các bước progress sau vẫn sửa tin đó.
            self.panel_message_id = None
        if command in ("/ip", "/whois"):
            parts = text.split(maxsplit=1)
            await lookup_message(command[1:], parts[1] if len(parts) > 1 else "", self.update_edit, state.config.get("LANGUAGE", "vi"))
            return False
        if command == "/ping":
            parts = text.split(maxsplit=1)
            async def edit_ping(text, parse_mode="html"):
                await self.send(text)
            await ping_message(parts[1] if len(parts) > 1 else "", edit_ping, state.config.get("LANGUAGE", "vi"))
            return False
        if command == "/updatecheck":
            await self.check_update()
            return False
        if command == "/shell":
            parts = text.split(maxsplit=1)
            lang = state.config.get("LANGUAGE", "vi")
            async def reply_shell(text, parse_mode="html"):
                payload = {"chat_id": self.admin_id, "text": text, "parse_mode": "HTML", "disable_notification": True}
                if isinstance(message.get("message_id"), int):
                    payload["reply_parameters"] = {"message_id": message["message_id"], "allow_sending_without_reply": True}
                await self.call("sendMessage", **payload)
            await run_shell_message(parts[1] if len(parts) > 1 else "", reply_shell, lang, runner=shell_runner, secret_values=config_secrets(state.config))
            return False
        if command == "/reset":
            await self.offer_reset()
            return False
        if command in ("/start", "/home", "/setup", "/cancel"):
            if command == "/start":
                await self.register_commands()
            update_requests.cancel(self.admin_id)
            self.action = None
            self.api_id = ""
            await self.show_menu()
            if command == "/start":
                await self.notify_completed()
            return False
        if text.startswith("/") or self.action is None:
            await self.show_menu()
            return False

        self._input_response = True
        if self.input_panel_message_id is not None:
            self.panel_message_id = self.input_panel_message_id
        try:
            await self.call("deleteMessage", chat_id=self.admin_id, message_id=message["message_id"])
        except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError):
            pass

        if self.action == "api_id":
            if not re.fullmatch(r"[1-9][0-9]{0,9}", text) or int(text) > 2147483647:
                await self.send(self.text("⚠️ API_ID phải là số dương từ my.telegram.org/apps. Hãy nhập lại.", "⚠️ API_ID must be a positive number from my.telegram.org/apps. Try again."))
                return False
            self.api_id = text
            self.action = "api_hash"
            await self.send(self.text("🔑 Gửi <b>API_HASH</b> riêng (32 ký tự hex). Bot sẽ cố xóa tin nhắn chứa hash sau khi nhận.", "🔑 Send your own <b>API_HASH</b> (32 hexadecimal characters). The bot will try to delete the message after receiving it."), self.cancel_keyboard())
            return False

        if not re.fullmatch(r"[0-9a-fA-F]{32}", text):
            await self.send(self.text("⚠️ API_HASH cần đúng 32 ký tự hex. Nhập lại hoặc bấm Hủy.", "⚠️ API_HASH must contain exactly 32 hexadecimal characters. Retry or cancel."), self.cancel_keyboard())
            return False
        await self.send(self.text("⏳ Đang kiểm tra API Telegram...", "⏳ Checking Telegram API credentials..."))
        try:
            await self.validate_api(text)
        except Exception as exc:
            self.action = None
            self.api_id = ""
            await self.send(self.text(
                f"❌ Chưa xác thực được API ({type(exc).__name__}). Chưa lưu key. Kiểm tra API/mạng rồi nhập lại.",
                f"❌ API validation failed ({type(exc).__name__}). Keys were not saved. Check your API/network and retry."
            ))
            await self.show_menu()
            return False
        try:
            state.update_config({"API_ID": self.api_id, "API_HASH": text})
        except OSError:
            await self.send(self.text("❌ Không ghi được .env. Kiểm tra quyền thư mục rồi gửi lại API_HASH.", "❌ Could not write .env. Check directory permissions and resend API_HASH."))
            return False
        self.action = None
        self.api_id = ""
        try:
            await self.send(self.text("✅ Đã lưu API vào .env. Chờ vài giây để bot mở nút <b>Đăng nhập Telegram</b>; không cần chạy lại trên máy.", "✅ API credentials saved in .env. Wait a few seconds for the <b>Telegram login</b> button; no terminal restart is needed."))
        except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError):
            pass
        return True

    async def offer_reset(self):
        self.action = None
        self.api_id = ""
        lang = state.config.get("LANGUAGE", "vi")
        token = reset_requests.create(self.admin_id)
        await self.send(reset_notice(lang), reset_buttons(token, lang))

    async def check_update(self):
        lang = state.config.get("LANGUAGE", "vi")
        await self.send(get_text("self_update_checking", lang))
        await run_update_check(self.update_edit, lang, updater=bot_updater, owner_id=self.admin_id)

    async def update_edit(self, text, parse_mode="html", buttons=None):
        await self.send(text, keyboard=buttons)


async def run_api_setup(token, admin_id):
    """Long polling chỉ ở bước thiếu API; đóng hoàn toàn trước khi chạy Helper đầy đủ."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
        setup = BotAPISetup(session, token, admin_id)
        try:
            me = await setup.call("getMe")
            webhook = await setup.call("getWebhookInfo")
            if webhook.get("url"):
                print("[❌] Bot đang có webhook. Tắt webhook ở dịch vụ cũ trước khi chạy chế độ cài đặt này.")
                return False
            await setup.register_commands()
            await setup.notify_completed()
            print(f"[🛠] Mở https://t.me/{me['username']} và /start bằng tài khoản ADMIN_ID={admin_id}.")
            try:
                await setup.show_menu()
            except BotSetupError as exc:
                if exc.code != 403 and not (exc.code == 400 and exc.reason in ("chat_not_found", "bot_not_started")):
                    raise
                print(f"[ℹ️] Bot API {exc.diagnostic()} Admin cần nhấn Start trước để bot được phép gửi hướng dẫn.")
            offset = 0
            while True:
                try:
                    updates = await setup.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
                    for update in updates:
                        try:
                            configured = await setup.handle(update)
                        except BotSetupError as exc:
                            if exc.code != 400:
                                raise
                            # Lỗi request cố định (VD callback hết hạn) không thể
                            # hết bằng cách đọc lại. Bỏ qua đúng update lỗi, vẫn
                            # xử lý các update mới trong cùng batch.
                            offset = update["update_id"] + 1
                            print(f"[⚠️] Bot API {exc.diagnostic()} Đã bỏ qua sự kiện lỗi; gửi /start hoặc bấm lại nút.")
                            continue
                        offset = update["update_id"] + 1
                        if configured:
                            # Xác nhận update chứa hash trước khi chuyển transport.
                            try:
                                await setup.call("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"])
                            except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError):
                                pass
                            return True
                except BotSetupError as exc:
                    if exc.code in (400, 401, 403, 404, 409):
                        raise
                    print(f"[⚠️] Bot API {exc.diagnostic()} Đang thử lại.")
                    await asyncio.sleep(max(2, exc.retry_after))
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    print("[⚠️] Mạng Bot API gián đoạn; đang thử lại.")
                    await asyncio.sleep(2)
        except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            detail = exc.diagnostic() if isinstance(exc, BotSetupError) else type(exc).__name__
            print(f"[❌] Không chạy được bước cài đặt Bot API ({detail}). Kiểm tra token/mạng và bảo đảm chỉ chạy một bản bot.")
            return False
