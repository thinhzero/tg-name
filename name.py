"""
name.py - Điểm khởi chạy chính của hệ thống Telegram Profile Updater & Helper Bot.

- Nếu có BOT_TOKEN: Khởi chạy Helper Bot tương tác (đồng thời tự động khởi chạy Profile Updater).
- Nếu không có BOT_TOKEN: Khởi chạy trực tiếp Profile Updater dưới nền.
"""

import asyncio
from bot_updater import run_with_restart
from updater_state import state
from profile_engine import engine
from helper_bot import run_standalone_bot

async def main():
    state.reload_config()
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

if __name__ == "__main__":
    try:
        run_with_restart(main)
    except (KeyboardInterrupt, SystemExit):
        print("\n[👋] Đã dừng chương trình.")
