"""
name.py - Điểm khởi chạy chính của hệ thống Telegram Profile Updater & Helper Bot.

- Nếu có BOT_TOKEN: Khởi chạy Helper Bot tương tác (đồng thời tự động khởi chạy Profile Updater).
- Nếu không có BOT_TOKEN: Khởi chạy trực tiếp Profile Updater dưới nền.
- Lần đầu chưa cấu hình: chỉ hỏi BOT_TOKEN + ADMIN_ID, phần đăng nhập làm trong chat.
- Tự chuẩn bị virtualenv/thư viện còn thiếu trước khi import các module Telegram.
"""

import asyncio
import sys
from getpass import getpass
from startup import ensure_dependencies


def prepare_bot_config(state):
    """Lần chạy đầu chỉ hỏi token/admin, không yêu cầu đăng nhập Telegram trên VPS."""
    config = state.config
    if not config.get("BOT_TOKEN") and any(config.get(key) for key in ("API_ID", "API_HASH", "SESSION_STRING")):
        return True  # Giữ chế độ Userbot không dùng Helper Bot.
    if config.get("BOT_TOKEN") and config.get("ADMIN_ID", "").isdigit() and int(config["ADMIN_ID"]) > 0:
        return True
    if not sys.stdin.isatty():
        print("[❌] Cần BOT_TOKEN + ADMIN_ID trong .env, hoặc chạy python name.py ở terminal để nhập lần đầu.")
        return False
    token = config.get("BOT_TOKEN", "")
    while not token:
        token = getpass("BOT_TOKEN từ @BotFather (ẩn): ").strip()
    admin = config.get("ADMIN_ID", "")
    while not admin.isdigit() or int(admin) <= 0:
        admin = input("ADMIN_ID của chính bạn (ID số): ").strip()
    state.update_config({"BOT_TOKEN": token, "ADMIN_ID": admin})
    return True

async def main():
    from updater_state import state
    from profile_engine import engine
    from helper_bot import run_standalone_bot

    state.reload_config()
    if not prepare_bot_config(state):
        return
    bot_token = state.config.get("BOT_TOKEN", "").strip()

    if bot_token:
        # Có Bot Token -> Chạy Helper Bot (Helper Bot sẽ tự động kích hoạt Profile Engine)
        await run_standalone_bot()
    else:
        # Không có Bot Token -> Chạy Profile Updater trực tiếp
        print("=" * 60)
        print("🚀 KHỞI ĐỘNG TELEGRAM PROFILE UPDATER (CHẾ ĐỘ USERBOT)")
        print("=" * 60)
        ok, msg = await engine.start()
        if not ok:
            print(f"[❌] {msg}")
            print("\n💡 Gợi ý:")
            print("  1. Chạy 'python3 setup.py' để cài đặt API hoặc đăng nhập Telegram.")
            print("  2. Hoặc thêm BOT_TOKEN vào .env để cài đặt và đăng nhập trực tiếp qua Telegram.")
            return

        print(f"[✅] {msg}")
        print("[ℹ️] Bạn có thể gõ các lệnh .status, .name, .update trong tin nhắn Telegram.")
        print("Nhấn Ctrl+C để dừng bot.\n")

        try:
            # Chờ cho đến khi engine dừng hoặc có yêu cầu khởi động lại
            while engine.is_running:
                await asyncio.sleep(1)
        finally:
            await engine.stop()

def launch():
    try:
        if not ensure_dependencies():
            return 1
        from bot_updater import run_with_restart
        run_with_restart(main)
    except (KeyboardInterrupt, SystemExit):
        print("\n[👋] Đã dừng chương trình.")
    return 0


if __name__ == "__main__":
    sys.exit(launch())
