"""Danh sách gợi ý khi gõ /, chỉ đăng ký trong chat riêng của admin."""

import asyncio


COMMANDS = (
    ("start", "Mở bảng điều khiển", "Open the dashboard"),
    ("home", "Về Home, hủy bước nhập đang chờ", "Go Home and cancel pending input"),
    ("help", "Hướng dẫn dùng các lệnh", "Show command help"),
    ("setup", "Cài đặt từng bước qua nút bấm", "Open the setup wizard"),
    ("settings", "Cài đặt tên, múi giờ, API, nhạc...", "Open profile and API settings"),
    ("login", "Đăng nhập tài khoản Telegram", "Log in to your Telegram account"),
    ("status", "Xem trạng thái Userbot", "Show Userbot status"),
    ("update", "Cập nhật tên và bio ngay", "Update your name and bio now"),
    ("updatecheck", "Đếm commit GitHub, hỏi trước khi cập nhật", "Check GitHub commits; ask before updating"),
    ("shell", "Chạy lệnh Linux/Termux, VD: /shell ls -la", "Run Linux/Termux commands, e.g. /shell ls -la"),
    ("ping", "Độ trễ Telegram, uptime; có thể thêm host", "Telegram latency and uptime; optional host"),
    ("ip", "Tra IP công khai: /ip 1.1.1.1", "Look up a public IP: /ip 1.1.1.1"),
    ("whois", "Tra tên miền: /whois example.com", "Look up a domain: /whois example.com"),
    ("l", "Tải link trực tiếp lên Telegram; tối đa 100 MiB", "Send a direct download to Telegram; max 100 MiB"),
    ("afk", "Bật AFK: /afk [10s] [lý do]; tự xóa trả lời", "Enable AFK: /afk [10s] [reason]; auto-delete replies"),
    ("on", "Tắt AFK", "Disable AFK"),
    ("preview", "Xem trước tên và bio", "Preview name and bio"),
    ("previewbio", "Xem bio và giới hạn ký tự", "Preview bio and character limits"),
    ("weather", "Xem thời tiết", "Show weather"),
    ("pause", "Tạm dừng cập nhật profile", "Pause profile updates"),
    ("resume", "Tiếp tục cập nhật profile", "Resume profile updates"),
    ("setname", "Đổi tên cố định", "Change your base name"),
    ("nameformat", "Đổi mẫu tên", "Change the name format"),
    ("bioformat", "Đổi mẫu bio", "Change the bio format"),
    ("setcity", "Đổi thành phố", "Change the city"),
    ("lastfm", "Đặt username Last.fm", "Set your Last.fm username"),
    ("music", "Xem nhạc đang nghe", "Show current music"),
    ("updaterandom", "Thêm nội dung random", "Add random entries"),
    ("lsrandom", "Xem random và UID", "List random entries and UIDs"),
    ("rmrandom", "Xóa random bằng UID", "Remove a random entry by UID"),
    ("lang", "Đổi ngôn ngữ: /lang vi hoặc /lang en", "Change language: /lang vi or /lang en"),
    ("reset", "Đặt lại cấu hình, cần xác nhận", "Reset settings, with confirmation"),
    ("cancel", "Hủy bước nhập hoặc tác vụ tải file", "Cancel input or the current file transfer"),
)
SETUP_COMMANDS = {"start", "home", "setup", "updatecheck", "shell", "ping", "ip", "whois", "reset", "cancel"}


def command_menu(lang="vi", bootstrap=False):
    return [
        {"command": command, "description": en if lang == "en" else vi}
        for command, vi, en in COMMANDS
        if not bootstrap or command in SETUP_COMMANDS
    ]


async def register_helper_commands(client, admin_id, lang="vi"):
    # Menu chỉ là gợi ý, không thay thế kiểm tra admin/private chat trong handler.
    try:
        from telethon.tl import functions, types

        async def register():
            peer = await client.get_input_entity(int(admin_id))
            await client(functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopePeer(peer=peer), lang_code="",
                commands=[types.BotCommand(**item) for item in command_menu(lang)],
            ))
        await asyncio.wait_for(register(), timeout=10)
        return True
    except Exception as exc:
        # Không in lỗi thô: request/URL có thể chứa thông tin riêng.
        print(f"[ℹ️] Chưa đồng bộ gợi ý lệnh ({type(exc).__name__}); gửi /start để thử lại.")
        return False
