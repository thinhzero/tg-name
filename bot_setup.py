"""Khởi tạo qua Bot API khi máy mới chỉ có BOT_TOKEN và ADMIN_ID."""

import asyncio
import re
import time

import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession

from updater_state import state


class BotSetupError(Exception):
    def __init__(self, code, retry_after=0):
        # Không đưa URL (chứa token), request hay API hash vào lỗi/log.
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"Telegram Bot API error {code}")


class BotAPISetup:
    def __init__(self, session, token, admin_id):
        self.session = session
        self.token = token
        self.admin_id = int(admin_id)
        self.action = None
        self.api_id = ""
        self.started_at = int(time.time())

    def text(self, vi, en):
        return en if state.config.get("LANGUAGE") == "en" else vi

    async def call(self, method, **payload):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        async with self.session.post(url, json=payload) as response:
            try:
                data = await response.json(content_type=None)
            except ValueError as exc:
                raise BotSetupError(response.status) from exc
        if not isinstance(data, dict):
            raise BotSetupError(response.status)
        if not data.get("ok"):
            raise BotSetupError(data.get("error_code", response.status), data.get("parameters", {}).get("retry_after", 0))
        return data.get("result")

    async def send(self, text, keyboard=None):
        payload = {"chat_id": self.admin_id, "text": text, "parse_mode": "HTML"}
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return await self.call("sendMessage", **payload)

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
        callback = update.get("callback_query")
        if callback:
            if not self.authorized(callback.get("message", {}), callback.get("from", {})):
                return False
            await self.call("answerCallbackQuery", callback_query_id=callback["id"])
            data = callback.get("data")
            if data == "bootstrap_api":
                self.action = "api_id"
                self.api_id = ""
                await self.send(self.text("🆔 Gửi <b>API_ID</b> của bạn (số dương):", "🆔 Send your <b>API_ID</b> (a positive number):"), self.cancel_keyboard())
            elif data in ("bootstrap_cancel", "bootstrap_vi", "bootstrap_en"):
                self.action = None
                self.api_id = ""
                if data != "bootstrap_cancel":
                    state.update_config({"LANGUAGE": data.rsplit("_", 1)[1]})
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
        if command in ("/start", "/setup", "/cancel"):
            self.action = None
            self.api_id = ""
            await self.show_menu()
            return False
        if text.startswith("/") or self.action is None:
            await self.show_menu()
            return False

        if self.action == "api_id":
            if not re.fullmatch(r"[1-9][0-9]{0,9}", text) or int(text) > 2147483647:
                await self.send(self.text("⚠️ API_ID phải là số dương từ my.telegram.org/apps. Hãy nhập lại.", "⚠️ API_ID must be a positive number from my.telegram.org/apps. Try again."))
                return False
            self.api_id = text
            self.action = "api_hash"
            await self.send(self.text("🔑 Gửi <b>API_HASH</b> riêng (32 ký tự hex). Bot sẽ cố xóa tin nhắn chứa hash sau khi nhận.", "🔑 Send your own <b>API_HASH</b> (32 hexadecimal characters). The bot will try to delete the message after receiving it."), self.cancel_keyboard())
            return False

        try:
            await self.call("deleteMessage", chat_id=self.admin_id, message_id=message["message_id"])
        except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError):
            pass
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
            print(f"[🛠] Mở https://t.me/{me['username']} và /start bằng tài khoản ADMIN_ID={admin_id}.")
            try:
                await setup.show_menu()
            except BotSetupError as exc:
                if exc.code not in (400, 403):
                    raise
                print("[ℹ️] Admin cần nhấn Start trước để bot được phép gửi hướng dẫn.")
            offset = 0
            while True:
                try:
                    updates = await setup.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
                    for update in updates:
                        configured = await setup.handle(update)
                        offset = update["update_id"] + 1
                        if configured:
                            # Xác nhận update chứa hash trước khi chuyển transport.
                            try:
                                await setup.call("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"])
                            except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError):
                                pass
                            return True
                except BotSetupError as exc:
                    if exc.code in (401, 403, 409):
                        raise
                    print(f"[⚠️] Bot API mã {exc.code}; đang thử lại.")
                    await asyncio.sleep(max(2, exc.retry_after))
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    print("[⚠️] Mạng Bot API gián đoạn; đang thử lại.")
                    await asyncio.sleep(2)
        except (BotSetupError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            code = exc.code if isinstance(exc, BotSetupError) else type(exc).__name__
            print(f"[❌] Không chạy được bước cài đặt Bot API ({code}). Kiểm tra token/mạng và bảo đảm chỉ chạy một bản bot.")
            return False
