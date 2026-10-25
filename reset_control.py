"""Xác nhận reset và dọn đúng các file session cục bộ được bot sử dụng."""

import secrets
import time
from pathlib import Path

from updater_state import state


PROJECT_DIR = Path(__file__).resolve().parent


class ResetRequests:
    def __init__(self):
        self.pending = {}

    def create(self, user_id):
        token = secrets.token_urlsafe(12)
        self.pending[user_id] = (token, time.monotonic() + 300)
        return token

    def consume(self, user_id, token):
        request = self.pending.get(user_id)
        if not request or request[0] != token:
            return False
        self.pending.pop(user_id)
        return request[1] >= time.monotonic()


reset_requests = ResetRequests()
pending_session_cleanup = set()


def reset_notice(lang="vi"):
    if lang == "en":
        return (
            "⚠️ <b>RESET CONFIGURATION?</b>\n\n"
            "Keep exactly <b>BOT_TOKEN</b> and <b>ADMIN_ID</b> in .env.\n"
            "Remove API credentials, other keys, saved Telegram login and profile settings. "
            "Local bot/userbot session files will be removed after disconnecting.\n"
            "<b>name.txt is kept.</b> The bot restarts into button-based setup; enter your API and log in again.\n\n"
            "This only clears local data, not messages/history or keys issued by Telegram/other services. Confirm within 5 minutes."
        )
    return (
        "⚠️ <b>ĐẶT LẠI CẤU HÌNH?</b>\n\n"
        "Giữ đúng <b>BOT_TOKEN</b> và <b>ADMIN_ID</b> trong .env.\n"
        "Xóa API, các key khác, đăng nhập Telegram đã lưu và cấu hình tên/bio. "
        "File session của bot/userbot sẽ được dọn sau khi ngắt kết nối.\n"
        "<b>Giữ nguyên name.txt.</b> Bot tự khởi động lại vào màn hình nút bấm; bạn nhập API và đăng nhập lại.\n\n"
        "Chỉ xóa dữ liệu cục bộ, không xóa lịch sử chat hay thu hồi key ở dịch vụ cấp key. Xác nhận trong 5 phút."
    )


def reset_buttons(token, lang="vi"):
    return [[
        {"text": "✅ Confirm reset" if lang == "en" else "✅ Xác nhận reset", "callback_data": f"reset_confirm:{token}"},
        {"text": "❌ Cancel" if lang == "en" else "❌ Hủy", "callback_data": f"reset_cancel:{token}"},
    ]]


def session_files(session_name, project_dir=PROJECT_DIR):
    root = Path(project_dir).resolve()
    names = {"bot", "helper_bot_session", session_name or "bot"}
    paths = set()
    for name in names:
        base = root / (name if str(name).endswith(".session") else f"{name}.session")
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(str(base) + suffix)
            # Không đụng tới session ngoài repo hoặc file symlink của người dùng.
            if root in path.resolve().parents and not path.is_symlink():
                paths.add(path)
    return paths


def apply_config_reset():
    paths = session_files(state.config.get("SESSION_NAME", "bot"))
    state.reset_config()
    pending_session_cleanup.update(paths)
    reset_requests.pending.clear()


def cleanup_reset_sessions():
    """Chỉ gọi sau khi tất cả client Telegram đã disconnect."""
    failed = []
    for path in list(pending_session_cleanup):
        try:
            if not path.is_symlink():
                path.unlink(missing_ok=True)
            pending_session_cleanup.discard(path)
        except OSError:
            failed.append(path.name)
    if failed:
        print("[⚠️] Chưa xóa được một số session cục bộ; kiểm tra quyền file trước khi dùng lại session.")
    return failed
