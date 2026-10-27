"""
i18n.py - Hỗ trợ đa ngôn ngữ (Tiếng Việt & English) cho Telegram Profile Updater & Helper Bot.
"""

from typing import Dict, Any

LANGUAGES = {
    "vi": "Tiếng Việt 🇻🇳",
    "en": "English 🇬🇧"
}

WEEKDAYS = {
    "vi": ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
}

WEEKDAYS_SHORT = {
    "vi": ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
}

MONTHS = {
    "vi": ["Tháng 1", "Tháng 2", "Tháng 3", "Tháng 4", "Tháng 5", "Tháng 6", "Tháng 7", "Tháng 8", "Tháng 9", "Tháng 10", "Tháng 11", "Tháng 12"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
}

TEXTS: Dict[str, Dict[str, str]] = {
    "lookup_ip_usage": {
        "vi": "🌐 Dùng <code>.ip 1.1.1.1</code> hoặc <code>/ip 1.1.1.1</code>. Nhận IPv4/IPv6 công khai; không tự tra IP máy chạy bot.",
        "en": "🌐 Use <code>.ip 1.1.1.1</code> or <code>/ip 1.1.1.1</code>. Accepts public IPv4/IPv6; never looks up the bot host's IP implicitly."
    },
    "lookup_whois_usage": {
        "vi": "🔎 Dùng <code>.whois example.com</code> hoặc <code>/whois example.com</code>. Chỉ nhập tên miền, không nhập URL/đường dẫn/port.",
        "en": "🔎 Use <code>.whois example.com</code> or <code>/whois example.com</code>. Enter a domain, not a URL, path or port."
    },
    "lookup_working": {"vi": "🔎 Đang tra cứu...", "en": "🔎 Looking up..."},
    "lookup_failed": {"vi": "❌ Chưa tra được. Dịch vụ có thể đang lỗi, không hỗ trợ tên miền này hoặc mạng bị gián đoạn; thử lại sau.", "en": "❌ Lookup failed. The service may be unavailable, the domain unsupported, or the connection interrupted; try again later."},
    "lookup_missing": {"vi": "⚠️ Không tìm thấy dữ liệu công khai cho địa chỉ/tên miền này.", "en": "⚠️ No public data was found for this address/domain."},
    "lookup_rate_limited": {"vi": "⏳ Dịch vụ đang giới hạn lượt tra cứu. Hãy đợi rồi thử lại.", "en": "⏳ The lookup service is rate-limiting requests. Wait before retrying."},
    "lookup_ip_result": {
        "vi": "🌐 <b>IP {ip}</b>\n🏳️ Quốc gia: {country}\n🏙️ Khu vực: {region} · {city}\n📡 ISP: {isp}\n🏢 Tổ chức: {org}\n🔗 ASN: {asn}\n\n<i>Nguồn: ipwho.is · Vị trí chỉ là ước lượng.</i>",
        "en": "🌐 <b>IP {ip}</b>\n🏳️ Country: {country}\n🏙️ Region: {region} · {city}\n📡 ISP: {isp}\n🏢 Organization: {org}\n🔗 ASN: {asn}\n\n<i>Source: ipwho.is · Location is approximate.</i>"
    },
    "lookup_whois_result": {
        "vi": "🔎 <b>Tên miền {domain}</b>\n🏢 Nhà đăng ký: {registrar}\n📅 Đăng ký: {registered}\n⌛ Hết hạn: {expires}\n🔄 Thay đổi: {changed}\n📋 Trạng thái: {status}\n🌐 Nameserver: {ns}\n\n<i>Nguồn: RDAP qua rdap.org · Không hiện thông tin liên hệ cá nhân.</i>",
        "en": "🔎 <b>Domain {domain}</b>\n🏢 Registrar: {registrar}\n📅 Registered: {registered}\n⌛ Expires: {expires}\n🔄 Changed: {changed}\n📋 Status: {status}\n🌐 Nameservers: {ns}\n\n<i>Source: RDAP via rdap.org · Personal contact details are omitted.</i>"
    },
    "transfer_usage": {
        "vi": "📥 Dùng <code>.l https://example.com/file.zip</code> hoặc <code>/l URL</code>; có thể reply tin chứa link. Chỉ tải link file trực tiếp, tối đa 100 MiB. Dùng <code>.cancel</code>/<code>/cancel</code> trong cùng chat để hủy.",
        "en": "📥 Use <code>.l https://example.com/file.zip</code> or <code>/l URL</code>; replying to a message containing a link also works. Direct file links only, max 100 MiB. Use <code>.cancel</code>/<code>/cancel</code> in the same chat to stop."
    },
    "transfer_starting": {"vi": "📥 Đang mở link tải...", "en": "📥 Opening the download..."},
    "transfer_download": {"vi": "📥 Đang tải", "en": "📥 Downloading"},
    "transfer_upload": {"vi": "📤 Đang gửi Telegram", "en": "📤 Sending to Telegram"},
    "transfer_progress": {
        "vi": "<b>{phase}</b>\n<code>{filename}</code>\n[{bar}] {percent}\n{current} / {total}\n⚡ {speed}/s · ETA: {eta}\n⏱ {elapsed}",
        "en": "<b>{phase}</b>\n<code>{filename}</code>\n[{bar}] {percent}\n{current} / {total}\n⚡ {speed}/s · ETA: {eta}\n⏱ {elapsed}"
    },
    "transfer_done": {"vi": "✅ Đã gửi <code>{filename}</code> lên Telegram và dọn file tạm.", "en": "✅ Sent <code>{filename}</code> to Telegram and removed the temporary file."},
    "transfer_cancelled": {"vi": "❌ Đã hủy tác vụ tải/gửi file.", "en": "❌ File transfer cancelled."},
    "transfer_not_running": {"vi": "ℹ️ Không có tác vụ tải/gửi file của bạn đang chạy trong chat này.", "en": "ℹ️ You have no active file transfer in this chat."},
    "transfer_busy": {"vi": "⏳ Đang có một tác vụ tải/gửi file. Chờ xong hoặc hủy tác vụ đó trước.", "en": "⏳ A file transfer is already running. Wait or cancel that transfer first."},
    "transfer_unsafe": {"vi": "⚠️ Chỉ nhận link HTTP/HTTPS công khai; không nhận file cục bộ, URL có tài khoản/mật khẩu, mạng nội bộ hay redirect không an toàn.", "en": "⚠️ Only public HTTP/HTTPS links are allowed; local files, URLs with credentials, internal networks and unsafe redirects are rejected."},
    "transfer_too_large": {"vi": "⚠️ File vượt giới hạn {limit}. Đã dừng và dọn phần tải dở.", "en": "⚠️ File exceeds the {limit} limit. Stopped and removed the partial download."},
    "transfer_timeout": {"vi": "⌛ Tác vụ quá 5 phút. Đã dừng và dọn file tạm.", "en": "⌛ Transfer exceeded 5 minutes. Stopped and removed the temporary file."},
    "transfer_empty": {"vi": "⚠️ Link trả về file rỗng; không gửi lên Telegram.", "en": "⚠️ The download is empty; nothing was sent to Telegram."},
    "transfer_failed": {"vi": "❌ Không tải/gửi được file. Kiểm tra link trực tiếp, quyền ghi bộ nhớ hoặc mạng rồi thử lại. File tạm đã được dọn.", "en": "❌ Could not transfer the file. Check the direct link, storage permissions or connection and retry. Temporary files were removed."},
    "afk_no_reason": {"vi": "Không có", "en": "Not specified"},
    "afk_enabled": {
        "vi": "😴 <b>AFK</b>\nLý do: {reason}\nTin tự trả lời xóa sau {delete_after}s.\nDùng <code>.on</code> hoặc <code>/on</code> để tắt.",
        "en": "😴 <b>AFK</b>\nReason: {reason}\nAutomatic replies delete after {delete_after}s.\nUse <code>.on</code> or <code>/on</code> to return."
    },
    "afk_usage": {
        "vi": "⚠️ Dùng <code>.afk [thời gian] [lý do]</code> hoặc <code>/afk [thời gian] [lý do]</code>. Ví dụ: <code>.afk 30s đi ngủ</code>. Mặc định 10s; nhận số giây hoặc s/m/h, từ 1s đến 24h.",
        "en": "⚠️ Use <code>.afk [time] [reason]</code> or <code>/afk [time] [reason]</code>. Example: <code>.afk 30s sleeping</code>. Default: 10s; accepts seconds or s/m/h, from 1s to 24h."
    },
    "afk_disabled": {"vi": "🟢 Đã tắt AFK.", "en": "🟢 AFK disabled."},
    "afk_login_required": {"vi": "⚠️ Cần đăng nhập và chạy Userbot trước khi bật AFK.", "en": "⚠️ Log in and start the Userbot before enabling AFK."},
    "afk_reply": {
        "vi": "😴 <b>{name} đang AFK</b>\nThời gian: {duration}\nLý do: {reason}",
        "en": "😴 <b>{name} is AFK</b>\nTime: {duration}\nReason: {reason}"
    },
    "ping_result": {
        "vi": "🏓 <b>Pong!</b>\nĐộ trễ Telegram: <code>{latency} ms</code>\nUptime: <code>{uptime}</code>",
        "en": "🏓 <b>Pong!</b>\nTelegram latency: <code>{latency} ms</code>\nUptime: <code>{uptime}</code>"
    },
    "ping_usage": {"vi": "🏓 Dùng <code>.ping</code> hoặc <code>.ping example.com</code> (Helper Bot: <code>/ping</code>). Chỉ nhập hostname/IP, không phải URL hay tùy chọn.", "en": "🏓 Use <code>.ping</code> or <code>.ping example.com</code> (Helper Bot: <code>/ping</code>). Enter a hostname/IP, not a URL or flags."},
    "ping_missing": {"vi": "Chưa có lệnh ping. Termux: pkg install iputils.", "en": "ping is not installed. Termux: pkg install iputils."},
    "ping_failed": {"vi": "Không ping được host hoặc đã hết thời gian chờ.", "en": "Host ping failed or timed out."},
    "btn_check_updates": {
        "vi": "🔎 Kiểm tra cập nhật",
        "en": "🔎 Check for updates"
    },
    "shell_usage": {
        "vi": "💻 Dùng <code>/shell &lt;lệnh&gt;</code>, VD <code>/shell ls -la</code>, <code>/shell fastfetch</code>. Chỉ admin, chat riêng, Linux/Termux.",
        "en": "💻 Use <code>/shell &lt;command&gt;</code>, e.g. <code>/shell ls -la</code> or <code>/shell fastfetch</code>. Admin only, private chat, Linux/Termux."
    },
    "shell_running": {
        "vi": "⏳ Đang chạy lệnh Linux/Termux (tối đa 30 giây)...",
        "en": "⏳ Running Linux/Termux command (up to 30 seconds)..."
    },
    "shell_linux_only": {
        "vi": "⚠️ /shell chỉ hoạt động trên Linux/Termux.",
        "en": "⚠️ /shell is only available on Linux/Termux."
    },
    "shell_missing_shell": {
        "vi": "⚠️ Không tìm thấy bash/sh trong PATH. Trên Termux, chạy <code>pkg install bash</code> rồi thử lại.",
        "en": "⚠️ No bash/sh found in PATH. On Termux, run <code>pkg install bash</code> and try again."
    },
    "shell_busy": {
        "vi": "⏳ Đang có một lệnh shell chạy. Chờ lệnh đó hoàn tất rồi thử lại.",
        "en": "⏳ A shell command is already running. Wait for it to finish."
    },
    "shell_failed": {
        "vi": "❌ Không chạy được lệnh shell. Kiểm tra quyền/thư mục chạy bot.",
        "en": "❌ Could not run the shell command. Check the bot's permissions/working directory."
    },
    "shell_empty_output": {
        "vi": "(không có output)",
        "en": "(no output)"
    },
    "shell_timeout": {
        "vi": "⏱ Lệnh quá 30 giây; đã dừng nhóm tiến trình.",
        "en": "⏱ Command exceeded 30 seconds; its process group was stopped."
    },
    "shell_truncated": {
        "vi": "✂️ Kết quả đã rút gọn; lệnh bị dừng nếu output vượt 64 KiB.",
        "en": "✂️ Output was shortened; the command is stopped if output exceeds 64 KiB."
    },

    "random_add_usage": {
        "vi": "🎲 Thêm bằng <code>.updaterandom eat29</code> (Helper Bot: <code>/updaterandom eat29</code>). Có thể gửi nhiều dòng, mỗi dòng một mục.",
        "en": "🎲 Use <code>.updaterandom eat29</code> (Helper Bot: <code>/updaterandom eat29</code>). Multiple lines are supported, one entry per line."
    },
    "random_added": {
        "vi": "✅ <b>Đã thêm {count} mục vào name.txt.</b> UID — Nội dung:",
        "en": "✅ <b>Added {count} entries to name.txt.</b> UID — Text:"
    },
    "random_duplicate": {
        "vi": "ℹ️ Các mục này đã có trong name.txt; không thêm trùng. Dùng <code>.lsrandom</code> hoặc <code>/lsrandom</code> để xem UID.",
        "en": "ℹ️ These entries already exist in name.txt; duplicates were skipped. Use <code>.lsrandom</code> or <code>/lsrandom</code> to see their UIDs."
    },
    "random_list": {
        "vi": "🎲 <b>Danh sách random ({count} mục)</b>\nUID — Nội dung:",
        "en": "🎲 <b>Random entries ({count})</b>\nUID — Text:"
    },
    "random_empty": {
        "vi": "📭 name.txt đang trống. Thêm bằng <code>.updaterandom &lt;nội dung&gt;</code> hoặc <code>/updaterandom &lt;nội dung&gt;</code>.",
        "en": "📭 name.txt is empty. Add entries using <code>.updaterandom &lt;text&gt;</code> or <code>/updaterandom &lt;text&gt;</code>."
    },
    "random_remove_usage": {
        "vi": "🗑 Dùng <code>.rmrandom &lt;uid&gt;</code> (Helper Bot: <code>/rmrandom &lt;uid&gt;</code>). Lấy UID bằng <code>.lsrandom</code> hoặc <code>/lsrandom</code>.",
        "en": "🗑 Use <code>.rmrandom &lt;uid&gt;</code> (Helper Bot: <code>/rmrandom &lt;uid&gt;</code>). Get the UID with <code>.lsrandom</code> or <code>/lsrandom</code>."
    },
    "random_removed": {
        "vi": "🗑 <b>Đã xóa mục random:</b>",
        "en": "🗑 <b>Removed random entry:</b>"
    },
    "random_not_found": {
        "vi": "⚠️ Không tìm thấy UID <code>{uid}</code>. Dùng <code>.lsrandom</code> hoặc <code>/lsrandom</code> để xem lại.",
        "en": "⚠️ UID <code>{uid}</code> was not found. Use <code>.lsrandom</code> or <code>/lsrandom</code> to check the list."
    },
    "random_file_error": {
        "vi": "❌ Không thể đọc/ghi name.txt: <code>{details}</code>",
        "en": "❌ Could not read/write name.txt: <code>{details}</code>"
    },

    # Cập nhật mã nguồn bot từ GitHub
    "self_update_checking": {
        "vi": "🔎 <b>Đang kiểm tra bản bot mới trên GitHub...</b>",
        "en": "🔎 <b>Checking GitHub for bot updates...</b>"
    },
    "self_update_offer": {
        "vi": "🔎 <b>Có {count} commit mới hơn trên GitHub.</b>\n<code>{old}</code> → <code>{new}</code>\n\nChưa clone, cài thư viện hay thay code. Chọn <b>Có</b> để tạo snapshot code (không chứa .env/token/API/session), cập nhật đúng commit này rồi restart. Chọn <b>Không</b> để giữ nguyên.\nXác nhận có hiệu lực 5 phút.",
        "en": "🔎 <b>GitHub is {count} commits ahead.</b>\n<code>{old}</code> → <code>{new}</code>\n\nNo clone, dependency installation or code change yet. Choose <b>Yes</b> to snapshot the code (excluding .env/tokens/API credentials/sessions), apply this commit and restart. Choose <b>No</b> to keep the current code.\nConfirmation expires in 5 minutes."
    },
    "self_update_text_confirm": {
        "vi": "\n\nXác nhận: <code>.updateconfirm {token}</code>\nBỏ qua: <code>.updatecancel {token}</code>",
        "en": "\n\nConfirm: <code>.updateconfirm {token}</code>\nDecline: <code>.updatecancel {token}</code>"
    },
    "self_update_compare_diverged": {
        "vi": "⚠️ GitHub có <b>{ahead}</b> commit chưa có ở máy này; máy này có <b>{local}</b> commit riêng. Chưa đổi code. Không cập nhật fast-forward được; hãy xử lý nhánh test/commit riêng thủ công.",
        "en": "⚠️ GitHub has <b>{ahead}</b> commits missing locally; this checkout has <b>{local}</b> local-only commits. Code is unchanged. Resolve the test branch/local commits before a fast-forward update."
    },
    "self_update_cancelled": {
        "vi": "✅ Đã chọn không cập nhật. Giữ nguyên code; không tạo snapshot, cài thư viện hay restart.",
        "en": "✅ Update declined. Code is unchanged; no snapshot, dependency installation or restart."
    },
    "self_update_expired": {
        "vi": "⚠️ Xác nhận đã hết hạn, đã dùng hoặc thuộc lần chạy khác. Gửi /updatecheck (Userbot: .updatecheck) để kiểm tra lại.",
        "en": "⚠️ Confirmation expired, was already used or belongs to another run. Check again with /updatecheck (Userbot: .updatecheck)."
    },
    "self_update_confirmation_required": {
        "vi": "⚠️ Cần kiểm tra và xác nhận Có trước khi cập nhật.",
        "en": "⚠️ Check and explicitly confirm Yes before updating."
    },
    "self_update_snapshot": {
        "vi": "📸 <b>Đang tạo snapshot code hiện tại, loại bỏ cấu hình/khóa/phiên đăng nhập...</b>",
        "en": "📸 <b>Snapshotting current source, excluding configuration credentials and sessions...</b>"
    },
    "self_update_snapshot_failed": {
        "vi": "❌ Không tạo được snapshot ({details}); đã dừng trước khi cài thư viện/thay code.",
        "en": "❌ Snapshot failed ({details}); stopped before installing dependencies or changing code."
    },
    "self_update_downloading": {
        "vi": "📥 <b>Có bản mới! Đang clone thinhzero/tg-name (main)...</b>",
        "en": "📥 <b>Update found! Cloning thinhzero/tg-name (main)...</b>"
    },
    "self_update_validating": {
        "vi": "🔎 <b>Đang kiểm tra mã nguồn mới...</b>",
        "en": "🔎 <b>Validating the new source code...</b>"
    },
    "self_update_dependencies": {
        "vi": "📦 <b>Đang cài thư viện từ requirements.txt mới...</b>",
        "en": "📦 <b>Installing dependencies from the new requirements.txt...</b>"
    },
    "self_update_latest": {
        "vi": "✅ <b>Bot đã ở bản mới nhất.</b> Commit: <code>{commit}</code>",
        "en": "✅ <b>The bot is already up to date.</b> Commit: <code>{commit}</code>"
    },
    "self_update_restarting": {
        "vi": "✅ <b>Đã áp dụng mã nguồn:</b> <code>{old}</code> → <code>{new}</code>\n📸 Snapshot: <code>{snapshot}</code>\n🔄 Đang khởi động lại; bot sẽ báo hoàn tất sau khi kết nối Telegram...",
        "en": "✅ <b>Source applied:</b> <code>{old}</code> → <code>{new}</code>\n📸 Snapshot: <code>{snapshot}</code>\n🔄 Restarting; completion will be reported after reconnecting to Telegram..."
    },
    "self_update_completed": {
        "vi": "✅ <b>Đã cập nhật xong!</b> Bot đã khởi động lại và kết nối Telegram thành công.\n<code>{old}</code> → <code>{new}</code>\n📸 Snapshot: <code>{snapshot}</code>",
        "en": "✅ <b>Update completed!</b> The bot restarted and reconnected to Telegram successfully.\n<code>{old}</code> → <code>{new}</code>\n📸 Snapshot: <code>{snapshot}</code>"
    },
    "self_update_busy": {
        "vi": "⏳ Bot đang cập nhật hoặc chuẩn bị khởi động lại. Vui lòng chờ.",
        "en": "⏳ An update or restart is already in progress. Please wait."
    },
    "self_update_missing_git": {
        "vi": "❌ Chưa cài Git. Hãy cài <code>git</code> trên máy chạy bot rồi thử lại.",
        "en": "❌ Git is not installed. Install <code>git</code> on the bot host and try again."
    },
    "self_update_not_git": {
        "vi": "❌ Git không tìm thấy metadata .git của bot tại <code>{directory}</code>. Chưa thay file nào. Kiểm tra bằng <code>git rev-parse --show-toplevel</code> ngay trong thư mục này; không xóa .env/session hay clone lại vội.",
        "en": "❌ Git could not find the bot's .git metadata at <code>{directory}</code>. No files changed. Run <code>git rev-parse --show-toplevel</code> in this directory; do not delete .env/session files or re-clone yet."
    },
    "self_update_git_ownership": {
        "vi": "⚠️ Git chặn thư mục do quyền sở hữu (dubious ownership): <code>{directory}</code>. Không cần clone lại. Nếu tin cậy thư mục này, mở terminal tại đó và chạy <code>git config --global --add safe.directory &quot;$(pwd -P)&quot;</code>, rồi thử lại. Bot không tự bỏ kiểm tra bảo mật của Git.",
        "en": "⚠️ Git rejected the directory's ownership (dubious ownership): <code>{directory}</code>. No re-clone needed. If you trust this directory, open a terminal there and run <code>git config --global --add safe.directory &quot;$(pwd -P)&quot;</code>, then retry. The bot does not bypass Git's security checks."
    },
    "self_update_wrong_directory": {
        "vi": "⚠️ Bot đang chạy từ <code>{directory}</code>, nhưng Git nhận thư mục gốc là <code>{root}</code>. Đã dừng để không cập nhật nhầm repo cha. Kiểm tra đường dẫn chạy bot; chưa thay .env/session hay mã nguồn.",
        "en": "⚠️ The bot is running from <code>{directory}</code>, but Git reports <code>{root}</code> as its root. Stopped to avoid updating a parent repository. Check the bot's launch path; .env/session files and source are unchanged."
    },
    "self_update_dirty": {
        "vi": "⚠️ Mã nguồn có thay đổi cục bộ chưa commit. Đã hủy cập nhật để không ghi đè; hãy lưu và xử lý các thay đổi đó trước.",
        "en": "⚠️ Source files have uncommitted local changes. Update cancelled to avoid overwriting them; save and resolve those changes first."
    },
    "self_update_diverged": {
        "vi": "⚠️ Lịch sử Git cục bộ khác nhánh main trên GitHub. Không thể cập nhật fast-forward; hãy xử lý các commit riêng thủ công.",
        "en": "⚠️ Local Git history differs from GitHub main. A fast-forward update is not possible; resolve local commits manually."
    },
    "self_update_unsafe_file": {
        "vi": "❌ Bản mới chứa file cấu hình/dữ liệu cá nhân cần bảo vệ: <code>{filename}</code>. Đã hủy cập nhật.",
        "en": "❌ The update contains a protected configuration/personal data file: <code>{filename}</code>. Update cancelled."
    },
    "self_update_invalid_source": {
        "vi": "❌ Mã Python mới không hợp lệ. Chưa thay mã nguồn đang chạy.\n<code>{details}</code>",
        "en": "❌ The new Python source is invalid. Running source files were not changed.\n<code>{details}</code>"
    },
    "self_update_changed": {
        "vi": "⚠️ HEAD cục bộ đã thay đổi trong lúc tải bản mới. Đã hủy cập nhật; hãy thử lại.",
        "en": "⚠️ Local HEAD changed while downloading the update. Update cancelled; please try again."
    },
    "self_update_timeout": {
        "vi": "❌ Tải/cài đặt quá thời gian chờ. Chưa áp dụng mã nguồn mới; hãy kiểm tra mạng và thử lại.",
        "en": "❌ Download/installation timed out. New source was not applied; check the network and try again."
    },
    "self_update_command_failed": {
        "vi": "❌ Cập nhật không thành công; không khởi động lại bot.\n<code>{details}</code>",
        "en": "❌ Update failed; the bot will not restart.\n<code>{details}</code>"
    },

    # Nút bấm Menu chính
    "btn_update_now": {
        "vi": "🔄 Cập nhật ngay",
        "en": "🔄 Update Now"
    },
    "btn_preview_profile": {
        "vi": "👁️ Xem trước Profile",
        "en": "👁️ Preview Profile"
    },
    "btn_preview_bio": {
        "vi": "📝 Xem trước Bio",
        "en": "📝 Preview Bio"
    },
    "btn_weather_card": {
        "vi": "🌤️ Thời tiết chi tiết",
        "en": "🌤️ Weather Details"
    },
    "btn_stop_updater": {
        "vi": "⏹️ Dừng Updater",
        "en": "⏹️ Stop Updater"
    },
    "btn_start_updater": {
        "vi": "▶️ Chạy Updater",
        "en": "▶️ Start Updater"
    },
    "btn_pause": {
        "vi": "⏸️ Tạm dừng",
        "en": "⏸️ Pause"
    },
    "btn_resume": {
        "vi": "▶️ Tiếp tục",
        "en": "▶️ Resume"
    },
    "btn_settings": {
        "vi": "⚙️ Cài đặt & Cấu hình",
        "en": "⚙️ Settings & Setup"
    },
    "btn_status": {
        "vi": "📊 Làm mới trạng thái",
        "en": "📊 Refresh Status"
    },
    "btn_help": {
        "vi": "ℹ️ Trợ giúp",
        "en": "ℹ️ Help & Guide"
    },
    "btn_cancel": {
        "vi": "❌ Hủy bỏ thao tác",
        "en": "❌ Cancel Action"
    },
    "btn_back_main": {
        "vi": "⬅️ Quay lại Menu chính",
        "en": "⬅️ Back to Main Menu"
    },
    "btn_back": {
        "vi": "⬅️ Quay lại",
        "en": "⬅️ Back"
    },
    "btn_language": {
        "vi": "🌐 Ngôn ngữ / Language",
        "en": "🌐 Language / Ngôn ngữ"
    },

    # Nút bấm Menu Cài đặt
    "btn_change_account": {
        "vi": "🔑 Đổi tài khoản Telegram",
        "en": "🔑 Change Telegram Account"
    },
    "btn_login_account": {
        "vi": "🔑 Đăng nhập Telegram",
        "en": "🔑 Login Telegram"
    },
    "btn_set_name": {
        "vi": "✏️ Đổi Tên (BASE_NAME)",
        "en": "✏️ Change Name (BASE_NAME)"
    },
    "btn_set_city": {
        "vi": "📍 Đổi Thành phố",
        "en": "📍 Change City"
    },
    "btn_set_weather": {
        "vi": "⛅ Cấu hình Thời tiết",
        "en": "⛅ Weather Settings"
    },
    "btn_set_timezone": {
        "vi": "🕒 Đổi Múi giờ",
        "en": "🕒 Change Timezone"
    },
    "btn_set_api_creds": {
        "vi": "🆔 Cấu hình API ID & Hash",
        "en": "🆔 API ID & Hash Config"
    },
    "btn_set_format": {
        "vi": "🎨 Mẫu hiển thị (Format)",
        "en": "🎨 Display Formats"
    },
    "btn_custom_name_fmt": {
        "vi": "✏️ Tự nhập NAME_FORMAT",
        "en": "✏️ Custom NAME_FORMAT"
    },
    "btn_custom_bio_fmt": {
        "vi": "📝 Tự nhập BIO_FORMAT",
        "en": "📝 Custom BIO_FORMAT"
    },
    "btn_reset_fmt": {
        "vi": "🔄 Khôi phục mặc định",
        "en": "🔄 Reset to Defaults"
    },
    "btn_preview_bio_detail": {
        "vi": "📝 Xem trước Bio chi tiết",
        "en": "📝 Detailed Bio Preview"
    },

    # Trạng thái Dashboard
    "status_stopped": {
        "vi": "🔴 <b>Đang dừng</b>",
        "en": "🔴 <b>Stopped</b>"
    },
    "status_paused": {
        "vi": "⏸️ <b>Đang tạm dừng</b>",
        "en": "⏸️ <b>Paused</b>"
    },
    "status_running": {
        "vi": "🟢 <b>Đang chạy bình thường</b>",
        "en": "🟢 <b>Running Normally</b>"
    },
    "not_logged_in": {
        "vi": "<i>Chưa đăng nhập</i>",
        "en": "<i>Not logged in</i>"
    },
    "has_session": {
        "vi": "✔ Đã có SESSION_STRING",
        "en": "✔ SESSION_STRING configured"
    },
    "no_session": {
        "vi": "✘ Chưa đăng nhập",
        "en": "✘ Not logged in"
    },
    "not_updated": {
        "vi": "Chưa cập nhật",
        "en": "Not updated yet"
    },
    "no_info": {
        "vi": "Chưa có thông tin",
        "en": "No info available"
    },

    # Tiêu đề & Nội dung Dashboard
    "dashboard_title": {
        "vi": "🤖 <b>BẢNG ĐIỀU KHIỂN TELEGRAM PROFILE UPDATER</b>",
        "en": "🤖 <b>TELEGRAM PROFILE UPDATER DASHBOARD</b>"
    },
    "field_status": {
        "vi": "• <b>Tình trạng:</b>",
        "en": "• <b>Status:</b>"
    },
    "field_account": {
        "vi": "• <b>Tài khoản Userbot:</b>",
        "en": "• <b>Userbot Account:</b>"
    },
    "field_current_name": {
        "vi": "• <b>Tên hiển thị hiện tại:</b>",
        "en": "• <b>Current Display Name:</b>"
    },
    "field_current_bio": {
        "vi": "• <b>Bio hiện tại:</b>",
        "en": "• <b>Current Bio:</b>"
    },
    "field_music": {
        "vi": "• <b>Đang nghe (Last.fm):</b>",
        "en": "• <b>Now Playing (Last.fm):</b>"
    },
    "field_weather": {
        "vi": "• <b>Thời tiết:</b>",
        "en": "• <b>Weather:</b>"
    },
    "field_base_name": {
        "vi": "• <b>Tên cố định (BASE_NAME):</b>",
        "en": "• <b>Fixed Name (BASE_NAME):</b>"
    },
    "field_city": {
        "vi": "• <b>Thành phố:</b>",
        "en": "• <b>City:</b>"
    },
    "field_timezone": {
        "vi": "• <b>Múi giờ:</b>",
        "en": "• <b>Timezone:</b>"
    },
    "field_last_update": {
        "vi": "• <b>Lần cập nhật cuối:</b>",
        "en": "• <b>Last Update:</b>"
    },
    "field_total_updates": {
        "vi": "Tổng",
        "en": "Total"
    },
    "field_last_error": {
        "vi": "• <b>Lỗi gần nhất:</b>",
        "en": "• <b>Last Error:</b>"
    },
    "field_language": {
        "vi": "• <b>Ngôn ngữ:</b>",
        "en": "• <b>Language:</b>"
    },

    # Thẻ thời tiết
    "weather_card_title": {
        "vi": "🌤️ <b>THÔNG TIN THỜI TIẾT CHI TIẾT — {city}</b>",
        "en": "🌤️ <b>DETAILED WEATHER INFORMATION — {city}</b>"
    },
    "weather_condition": {
        "vi": "• <b>Tình trạng:</b> {icon} <b>{desc}</b>",
        "en": "• <b>Condition:</b> {icon} <b>{desc}</b>"
    },
    "weather_temp": {
        "vi": "• <b>Nhiệt độ hiện tại:</b> <code>{temp}</code> (Cảm nhận thực tế: <code>{feels}</code>)",
        "en": "• <b>Current Temp:</b> <code>{temp}</code> (Feels like: <code>{feels}</code>)"
    },
    "weather_humidity": {
        "vi": "• <b>Độ ẩm không khí:</b> 💦 <code>{hum}</code>",
        "en": "• <b>Air Humidity:</b> 💦 <code>{hum}</code>"
    },
    "weather_wind": {
        "vi": "• <b>Tốc độ gió:</b> 💨 <code>{wind}</code>",
        "en": "• <b>Wind Speed:</b> 💨 <code>{wind}</code>"
    },
    "weather_pressure": {
        "vi": "• <b>Áp suất khí quyển:</b> <code>{pressure}</code>",
        "en": "• <b>Pressure:</b> <code>{pressure}</code>"
    },
    "weather_sunrise": {
        "vi": "• <b>Mặt trời mọc (Bình minh):</b> 🌅 <code>{sunrise}</code>",
        "en": "• <b>Sunrise:</b> 🌅 <code>{sunrise}</code>"
    },
    "weather_sunset": {
        "vi": "• <b>Mặt trời lặn (Hoàng hôn):</b> 🌇 <code>{sunset}</code>",
        "en": "• <b>Sunset:</b> 🌇 <code>{sunset}</code>"
    },
    "weather_source": {
        "vi": "• <b>Nguồn cấp dữ liệu:</b> <i>{source}</i>",
        "en": "• <b>Data Source:</b> <i>{source}</i>"
    },
    "weather_tags_title": {
        "vi": "📌 <b>Các từ khóa thời tiết bạn có thể dùng trong Tên & Bio:</b>",
        "en": "📌 <b>Weather placeholders you can use in Name & Bio:</b>"
    },

    # Thẻ xem trước Bio
    "bio_preview_title": {
        "vi": "📝 <b>XEM TRƯỚC TIỂU SỬ TELEGRAM (BIO PREVIEW)</b>",
        "en": "📝 <b>TELEGRAM BIO PREVIEW & ANALYSIS</b>"
    },
    "bio_template_label": {
        "vi": "• <b>Mẫu BIO_FORMAT đang cấu hình:</b>",
        "en": "• <b>Configured BIO_FORMAT template:</b>"
    },
    "bio_actual_label": {
        "vi": "• <b>Bio hiển thị thực tế trên Profile:</b>",
        "en": "• <b>Actual display on Profile:</b>"
    },
    "bio_length_label": {
        "vi": "📊 <b>Độ dài:</b> <code>{len}/70 ký tự</code> ({status})",
        "en": "📊 <b>Length:</b> <code>{len}/70 chars</code> ({status})"
    },
    "bio_valid": {
        "vi": "🟢 Hợp lệ",
        "en": "🟢 Valid"
    },
    "bio_invalid": {
        "vi": "🔴 VƯỢT GIỚI HẠN 70 KÝ TỰ",
        "en": "🔴 EXCEEDS 70 CHARS LIMIT"
    },
    "bio_scenarios_title": {
        "vi": "🎭 <b>CÁC KỊCH BẢN HIỂN THỊ CỦA MẪU NÀY:</b>",
        "en": "🎭 <b>DISPLAY SCENARIOS FOR THIS TEMPLATE:</b>"
    },
    "bio_scenario_music": {
        "vi": "🎧 <b>1. Khi đang phát nhạc (Spotify / Apple Music):</b>",
        "en": "🎧 <b>1. When actively playing music (Spotify / Apple Music):</b>"
    },
    "bio_scenario_no_music": {
        "vi": "🌤️ <b>2. Khi không nghe nhạc (hiển thị thời tiết):</b>",
        "en": "🌤️ <b>2. When no music is playing (fallback to weather):</b>"
    },
    "bio_tip": {
        "vi": "💡 <i>Gợi ý: Dùng lệnh <code>/bioformat &lt;mẫu&gt;</code> để đổi ngay định dạng Bio!</i>",
        "en": "💡 <i>Tip: Use <code>/bioformat &lt;template&gt;</code> to update your Bio format instantly!</i>"
    },

    # Cài đặt
    "settings_title": {
        "vi": "⚙️ <b>CÀI ĐẶT & CẤU HÌNH HỆ THỐNG</b>",
        "en": "⚙️ <b>SYSTEM CONFIGURATION & SETTINGS</b>"
    },
    "settings_prompt": {
        "vi": "<i>Bấm vào một mục bên dưới để cấu hình:</i>",
        "en": "<i>Tap an option below to configure:</i>"
    },
    "lang_switched": {
        "vi": "✔ Đã chuyển ngôn ngữ sang: <b>Tiếng Việt 🇻🇳</b>",
        "en": "✔ Language successfully switched to: <b>English 🇬🇧</b>"
    },
    "choose_language": {
        "vi": "🌐 <b>CHỌN NGÔN NGỮ HIỂN THỊ (SELECT LANGUAGE)</b>\n\nVui lòng chọn ngôn ngữ bạn muốn sử dụng:",
        "en": "🌐 <b>SELECT DISPLAY LANGUAGE (CHỌN NGÔN NGỮ)</b>\n\nPlease select your preferred language:"
    }
}

def get_text(key: str, lang: str = "vi", **kwargs) -> str:
    """Lấy văn bản dịch theo ngôn ngữ đã chọn"""
    l = lang if lang in ("vi", "en") else "vi"
    tmpl = TEXTS.get(key, {}).get(l) or TEXTS.get(key, {}).get("vi") or key
    if kwargs:
        try:
            return tmpl.format(**kwargs)
        except Exception:
            return tmpl
    return tmpl

def get_weekday(idx: int, lang: str = "vi", short: bool = False) -> str:
    """Lấy tên thứ trong tuần (0: Thứ Hai / Monday ... 6: Chủ Nhật / Sunday)"""
    l = lang if lang in ("vi", "en") else "vi"
    table = WEEKDAYS_SHORT[l] if short else WEEKDAYS[l]
    return table[idx % 7]

def get_month_name(month_idx: int, lang: str = "vi") -> str:
    """Lấy tên tháng (1-12)"""
    l = lang if lang in ("vi", "en") else "vi"
    return MONTHS[l][(month_idx - 1) % 12]
