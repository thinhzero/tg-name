#!/usr/bin/env python3
"""
Script hỗ trợ tạo Telethon StringSession cho tài khoản Telegram.
Chạy script:
    python3 generate_session.py
"""

import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from getpass import getpass

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_FILE)

async def main():
    print("=" * 60)
    print("🔑 TELEGRAM SESSION STRING GENERATOR")
    print("=" * 60)
    print("Lấy API_ID & API_HASH riêng tại: https://my.telegram.org/apps\n")

    default_api_id = os.getenv("API_ID", "").strip()
    default_api_hash = os.getenv("API_HASH", "").strip()

    api_id_input = input(f"Nhập API_ID [{default_api_id}]: ").strip()
    raw_api_id = api_id_input or default_api_id
    if not raw_api_id.isdigit() or int(raw_api_id) <= 0:
        print("❌ API_ID bắt buộc, phải là số dương từ my.telegram.org/apps.")
        return
    api_id = int(raw_api_id)

    api_hash_input = getpass("Nhập API_HASH (ẩn; Enter giữ giá trị trong .env): ").strip()
    api_hash = api_hash_input if api_hash_input else default_api_hash
    if not api_hash:
        print("❌ API_HASH bắt buộc. Không có API key dùng chung.")
        return

    print("\n⏳ Đang kết nối Telethon...")
    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.start()
        session_string = client.session.save()
        me = await client.get_me()

        print("\n" + "=" * 60)
        print("✅ ĐĂNG NHẬP THÀNH CÔNG!")
        print(f"👤 Tài khoản: {me.first_name} {me.last_name or ''} (@{me.username or 'None'}, ID: {me.id})")
        print("=" * 60)
        from updater_state import state
        state.update_config({
            "API_ID": str(api_id), "API_HASH": api_hash,
            "SESSION_STRING": session_string, "ADMIN_ID": str(me.id),
        })
        print("✅ Đã lưu thông tin đăng nhập vào .env; không in session ra terminal.")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[👋] Đã hủy.")
