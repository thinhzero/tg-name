#!/usr/bin/env python3
"""
setup.py - Công cụ cài đặt và cấu hình trực quan cho Telegram Profile Updater & Helper Bot.
Hỗ trợ:
- Cài đặt thư viện phụ thuộc (pip install)
- Cấu hình Telegram API (API_ID, API_HASH)
- Đăng nhập tài khoản lấy SESSION_STRING trực tiếp
- Cấu hình Helper Bot (BOT_TOKEN từ @BotFather & ADMIN_ID)
- Cấu hình OpenWeatherMap & kiểm tra API Key trực tiếp
- Tùy chỉnh định dạng Tên, Bio, Múi giờ, Thành phố
- Xem trước (Preview) Name và Bio trước khi chạy
- Khởi động bot trực tiếp hoặc qua PM2
"""

import os
import sys
import json
import asyncio
import subprocess
import urllib.request
import urllib.parse
from getpass import getpass

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
REQUIREMENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")

# Màu hiển thị terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

DEFAULT_CONFIG = {
    "API_ID": "",
    "API_HASH": "",
    "SESSION_STRING": "",
    "SESSION_NAME": "bot",
    "BOT_TOKEN": "",
    "ADMIN_ID": "",
    "WEATHER_API": "",
    "CITY": "Bac Ninh",
    "BASE_NAME": "tên",
    "TIMEZONE": "Asia/Ho_Chi_Minh",
    "LANGUAGE": "vi",
    "NAME_FORMAT": "{base_name} | HH:mm - DD/MM | {gmt} | {random}",
    "BIO_FORMAT": "{weather} ⏰ HH:mm",
    "LASTFM_USERNAME": "",
    "LASTFM_API_KEY": ""
}

def format_env_val(v) -> str:
    if v is None:
        return '""'
    s = str(v).replace("\r", "")
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'

def load_env() -> dict:
    config = DEFAULT_CONFIG.copy()
    if not os.path.exists(ENV_FILE):
        return config
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_FILE)
        for k, v in vals.items():
            if v is not None and (v.strip() or not config.get(k)):
                config[k] = v.replace("\\n", "\n")
    except Exception as e:
        print(f"{RED}[Lỗi khi đọc .env]: {e}{RESET}")
    return config

def save_env(updates: dict):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    handled = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={format_env_val(updates[k])}\n")
                handled.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in handled:
            new_lines.append(f"{k}={format_env_val(v)}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        if os.name == "posix":
            os.fchmod(f.fileno(), 0o600)
        f.writelines(new_lines)
    print(f"{GREEN}✔ Đã lưu cấu hình vào .env thành công!{RESET}")

def check_dependencies():
    print(f"\n{BOLD}{CYAN}=== KIỂM TRA THƯ VIỆN PHỤ THUỘC ==={RESET}")
    packages = ["telethon", "dotenv", "aiohttp", "pytz"]
    missing = []
    for pkg in packages:
        try:
            __import__(pkg)
            print(f"  {GREEN}✔ {pkg} đã được cài đặt{RESET}")
        except ImportError:
            print(f"  {RED}✘ {pkg} chưa được cài đặt{RESET}")
            missing.append(pkg)

    if missing:
        choice = input(f"\n{YELLOW}Bạn có muốn tự động cài đặt các thư viện thiếu không? (y/n) [y]: {RESET}").strip().lower()
        if choice in ("", "y", "yes"):
            print(f"\n{CYAN}Đang chạy pip install...{RESET}")
            if os.path.exists(REQUIREMENTS_FILE):
                cmd = [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]
            else:
                cmd = [sys.executable, "-m", "pip", "install", "telethon", "python-dotenv", "aiohttp", "pytz"]
            res = subprocess.call(cmd)
            if res == 0:
                print(f"{GREEN}✔ Đã cài đặt đầy đủ thư viện thành công!{RESET}")
            else:
                print(f"{RED}✘ Lỗi khi cài đặt thư viện qua pip.{RESET}")
    else:
        print(f"{GREEN}✔ Toàn bộ thư viện đều đã sẵn sàng!{RESET}")

def test_weather_api(api_key: str, city: str):
    city_encoded = urllib.parse.quote(city)
    if api_key:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid={api_key}&units=metric&lang=vi"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    temp = round(float(data["main"]["temp"]))
                    feels = round(float(data["main"].get("feels_like", temp)))
                    hum = data["main"].get("humidity", "N/A")
                    desc = data["weather"][0]["description"]
                    return True, f"OpenWeatherMap: {city} {temp}°C (cảm giác {feels}°C), độ ẩm {hum}%, thời tiết: {desc}"
                return False, f"HTTP status: {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "API Key không hợp lệ (401). Lưu ý: Key mới tạo trên OpenWeatherMap cần 10-30 phút để kích hoạt."
            elif e.code == 404:
                return False, f"Không tìm thấy thành phố '{city}' (404)."
            return False, f"Lỗi HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, f"Lỗi kết nối tới OpenWeatherMap: {e}"
    else:
        # Tự động lấy miễn phí qua wttr.in (không cần API Key)
        url = f"https://wttr.in/{city_encoded}?format=j1&lang=vi"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=7) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    cc = data.get("current_condition", [{}])[0]
                    temp = cc.get("temp_C", "N/A")
                    feels = cc.get("FeelsLikeC", temp)
                    hum = cc.get("humidity", "N/A")
                    desc_list = cc.get("lang_vi") or cc.get("weatherDesc") or [{}]
                    desc = desc_list[0].get("value", "Bình thường") if desc_list else "Bình thường"
                    return True, f"wttr.in (Tự động miễn phí, không cần API Key): {city} {temp}°C (cảm giác {feels}°C), độ ẩm {hum}%, thời tiết: {desc}"
                return False, f"HTTP status: {resp.status}"
        except Exception as e:
            return True, f"Sử dụng tên thành phố ({city}) - chưa kết nối được wttr.in: {e}"

def test_telegram_bot_token(bot_token: str):
    if not bot_token:
        return False, "Chưa nhập Bot Token."
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    result = data.get("result", {})
                    return True, f"Bot hợp lệ: @{result.get('username')} ({result.get('first_name')})"
            return False, f"HTTP status: {resp.status}"
    except Exception as e:
        return False, f"Token không hợp lệ hoặc lỗi kết nối: {e}"

def test_lastfm_user(username: str, api_key: str = "") -> tuple:
    if not username:
        return True, "Chưa cấu hình Last.fm (bỏ qua)."
    if not api_key:
        return False, "Cần LASTFM_API_KEY riêng từ https://www.last.fm/api/account/create."
    try:
        key = api_key
        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={urllib.parse.quote(username)}&api_key={key}&format=json&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "TelegramProfileUpdater/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if "error" in data:
                    return False, f"Lỗi Last.fm: {data.get('message', 'Không tìm thấy user')}"
                recent = data.get("recenttracks", {})
                tracks = recent.get("track", [])
                total = recent.get("@attr", {}).get("total", "0")
                if tracks:
                    first = tracks[0] if isinstance(tracks, list) else tracks
                    t_name = first.get("name", "")
                    a_info = first.get("artist", {})
                    a_name = a_info.get("#text") if isinstance(a_info, dict) else str(a_info)
                    is_playing = first.get("@attr", {}).get("nowplaying") == "true"
                    status = "Đang phát 🎧" if is_playing else "Bài gần nhất 🎵"
                    return True, f"Kết nối Last.fm tốt! ({total} scrobbles). {status}: {t_name} - {a_name}"
                return True, f"Kết nối Last.fm tốt! (User {username} chưa có bài hát nào)."
            return False, f"Mã HTTP: {resp.status}"
    except Exception as e:
        return False, f"Lỗi kết nối Last.fm: {e}"

def configure_telegram(config: dict) -> dict:
    print(f"\n{BOLD}{CYAN}=== 1. CẤU HÌNH TELEGRAM API (USER ACCOUNT) ==={RESET}")
    print(f"Lấy API_ID và API_HASH tại: {CYAN}https://my.telegram.org{RESET}")
    print(f"(Nhấn Enter để giữ nguyên giá trị mặc định trong ngoặc vuông)\n")

    curr_id = config.get("API_ID", DEFAULT_CONFIG["API_ID"])
    in_id = input(f"Nhập API_ID [{curr_id}]: ").strip()
    api_id = in_id if in_id else curr_id
    while not api_id.isdigit() or int(api_id) <= 0:
        api_id = input("API_ID bắt buộc, phải là số dương từ my.telegram.org/apps: ").strip()

    curr_hash = config.get("API_HASH", DEFAULT_CONFIG["API_HASH"])
    in_hash = getpass("Nhập API_HASH (ẩn; Enter giữ giá trị đã lưu): ").strip()
    api_hash = in_hash if in_hash else curr_hash
    while not api_hash:
        api_hash = getpass("API_HASH bắt buộc, lấy tại my.telegram.org/apps: ").strip()

    updates = {"API_ID": api_id, "API_HASH": api_hash}

    # Tùy chọn đăng nhập lấy SESSION_STRING
    has_session = bool(config.get("SESSION_STRING", "").strip())
    print(f"\nTrạng thái SESSION_STRING hiện tại: {'Đã có' if has_session else 'Chưa có'}")
    prompt_login = "Bạn có muốn tạo lại SESSION_STRING không? (y/n) [n]: " if has_session else "Bạn có muốn đăng nhập Telegram ngay để tạo SESSION_STRING? (y/n) [y]: "
    default_ans = "n" if has_session else "y"

    choice = input(f"{YELLOW}{prompt_login}{RESET}").strip().lower()
    if (not choice and default_ans == "y") or choice in ("y", "yes"):
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            async def do_login():
                print(f"\n{CYAN}Đang kết nối tới Telegram Server...{RESET}")
                client = TelegramClient(StringSession(), int(api_id), api_hash)
                await client.start()
                s_string = client.session.save()
                me = await client.get_me()
                await client.disconnect()
                return s_string, me

            session_string, me = asyncio.run(do_login())
            user_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            print(f"\n{GREEN}✔ Đăng nhập thành công tài khoản: {user_name} (@{me.username or 'Không có username'}, ID: {me.id}){RESET}")
            updates["SESSION_STRING"] = session_string
            if not config.get("ADMIN_ID"):
                updates["ADMIN_ID"] = str(me.id)
        except Exception as e:
            print(f"{RED}✘ Không thể đăng nhập Telegram: {e}{RESET}")
            manual_s = getpass("\nDán SESSION_STRING thủ công (ẩn; Enter bỏ qua): ").strip()
            if manual_s:
                updates["SESSION_STRING"] = manual_s

    return updates

def configure_helper_bot(config: dict) -> dict:
    print(f"\n{BOLD}{CYAN}=== 2. CẤU HÌNH HELPER BOT (BOTFATHER) ==={RESET}")
    print("Helper Bot cho phép bạn điều khiển cập nhật profile Telegram qua tin nhắn / nút bấm trực quan.")
    print("Tạo bot và lấy BOT_TOKEN miễn phí từ: https://t.me/BotFather")
    print("(Nếu không dùng Helper Bot qua bot token, bạn vẫn có thể gõ lệnh .name, .update trên userbot)\n")

    curr_token = config.get("BOT_TOKEN", "")
    in_token = getpass("Nhập BOT_TOKEN (ẩn; Enter giữ nguyên, 'none' để tắt Helper Bot): ").strip()

    if in_token:
        bot_token = "" if in_token.lower() in ("none", "null", "huy", "bo qua", "trong") else in_token
    else:
        bot_token = curr_token

    if bot_token:
        print(f"\n{CYAN}Đang kiểm tra BOT_TOKEN...{RESET}")
        ok, msg = test_telegram_bot_token(bot_token)
        if ok:
            print(f"{GREEN}✔ {msg}{RESET}")
        else:
            print(f"{YELLOW}⚠️ {msg}{RESET}")

    curr_admin = config.get("ADMIN_ID", "")
    in_admin = input(f"Telegram ID của chính bạn [{curr_admin or 'chưa có'}]: ").strip()
    admin_id = in_admin if in_admin else curr_admin
    while bot_token and (not admin_id.isdigit() or int(admin_id) <= 0):
        admin_id = input("Bật Helper Bot cần ADMIN_ID của bạn (số dương): ").strip()

    return {"BOT_TOKEN": bot_token, "ADMIN_ID": admin_id}

def run_bot_first_setup(config: dict):
    """Chỉ nhận token/admin ở terminal; API và đăng nhập làm trong chat bot."""
    print(f"\n{BOLD}{CYAN}=== CÀI ĐẶT QUA TELEGRAM ==={RESET}")
    print("Chỉ cần BOT_TOKEN và ADMIN_ID. Không nhập API_ID/API_HASH ở terminal.")
    token = getpass("BOT_TOKEN (ẩn; Enter giữ token đã lưu): ").strip() or config.get("BOT_TOKEN", "")
    while not token:
        token = getpass("Cần BOT_TOKEN từ @BotFather (ẩn): ").strip()
    admin_id = input(f"ADMIN_ID của chính bạn [{config.get('ADMIN_ID') or 'chưa có'}]: ").strip() or config.get("ADMIN_ID", "")
    while not admin_id.isdigit() or int(admin_id) <= 0:
        admin_id = input("ADMIN_ID phải là ID số dương của chính bạn: ").strip()
    save_env({"BOT_TOKEN": token, "ADMIN_ID": admin_id})
    print("Mở chat riêng với bot, nhấn Start. Bot chỉ nhận cấu hình từ ADMIN_ID đã lưu.")
    print("Nhập API riêng và đăng nhập Telegram bằng các nút trong chat; Ctrl+C để dừng.")
    project_dir = os.path.dirname(os.path.abspath(__file__))
    subprocess.call([sys.executable, os.path.join(project_dir, "name.py")], cwd=project_dir)

def configure_weather(config: dict) -> dict:
    print(f"\n{BOLD}{CYAN}=== 3. CẤU HÌNH THỜI TIẾT (OPENWEATHERMAP) ==={RESET}")
    print("Đăng ký API Key miễn phí tại: https://home.openweathermap.org/api_keys")
    print("(Nếu không muốn hiển thị thời tiết, bạn có thể để trống)\n")

    curr_city = config.get("CITY", DEFAULT_CONFIG["CITY"])
    in_city = input(f"Nhập Tỉnh / Thành phố [{curr_city}]: ").strip()
    city = in_city if in_city else curr_city

    curr_key = config.get("WEATHER_API", "")
    in_key = getpass("Nhập WEATHER_API (ẩn; Enter giữ nguyên, 'none' để dùng wttr.in): ").strip()
    if in_key:
        api_key = "" if in_key.lower() in ("none", "null", "trong", "trống") else in_key
    else:
        api_key = curr_key

    print(f"\n{CYAN}Đang kiểm tra kết nối thời tiết tới {city}...{RESET}")
    ok, msg = test_weather_api(api_key, city)
    if ok:
        print(f"{GREEN}✔ {msg}{RESET}")
    else:
        print(f"{YELLOW}⚠️ {msg}{RESET}")

    return {"CITY": city, "WEATHER_API": api_key}

def configure_lastfm(config: dict) -> dict:
    print(f"\n{BOLD}{CYAN}=== 4. CẤU HÌNH ÂM NHẠC LAST.FM (SPOTIFY / APPLE MUSIC) ==={RESET}")
    print("Hiển thị bài hát đang nghe trên Bio hoặc Tên Telegram.")
    print("Tạo tài khoản miễn phí tại: https://www.last.fm và kết nối Spotify / Apple Music.")
    print("(Nếu không muốn dùng tính năng này, bạn có thể để trống)\n")

    curr_user = config.get("LASTFM_USERNAME", "")
    show_user = curr_user if curr_user else "Chưa cấu hình"
    in_user = input(f"Nhập Last.fm Username [{show_user}]: ").strip()
    if in_user:
        username = "" if in_user.lower() in ("none", "null", "trong", "trống", "0") else in_user
    else:
        username = curr_user

    curr_key = config.get("LASTFM_API_KEY", DEFAULT_CONFIG["LASTFM_API_KEY"])
    in_key = getpass("Nhập LASTFM_API_KEY riêng (ẩn; Enter giữ nguyên, 'none' để xóa): ").strip()
    api_key = in_key if in_key else curr_key
    if api_key.lower() in ("none", "null", "0"):
        api_key = ""

    if username:
        print(f"\n{CYAN}Đang kiểm tra tài khoản Last.fm: {username}...{RESET}")
        ok, msg = test_lastfm_user(username, api_key)
        if ok:
            print(f"{GREEN}✔ {msg}{RESET}")
        else:
            print(f"{YELLOW}⚠️ {msg}{RESET}")

    return {"LASTFM_USERNAME": username, "LASTFM_API_KEY": api_key}

def configure_display(config: dict) -> dict:
    print(f"\n{BOLD}{CYAN}=== 5. CẤU HÌNH HIỂN THỊ PROFILE & MÚI GIỜ ==={RESET}\n")

    curr_base = config.get("BASE_NAME", DEFAULT_CONFIG["BASE_NAME"])
    in_base = input(f"Tên cố định (BASE_NAME) hiển thị trên Telegram [{curr_base}]: ").strip()
    base_name = in_base if in_base else curr_base

    curr_tz = config.get("TIMEZONE", DEFAULT_CONFIG["TIMEZONE"])
    in_tz = input(f"Múi giờ (TIMEZONE) [{curr_tz}]: ").strip()
    timezone = in_tz if in_tz else curr_tz

    curr_lang = config.get("LANGUAGE", DEFAULT_CONFIG["LANGUAGE"])
    print(f"\nNgôn ngữ hiển thị (LANGUAGE): vi = Tiếng Việt, en = English")
    in_lang = input(f"Chọn ngôn ngữ (vi/en) [{curr_lang}]: ").strip().lower()
    language = in_lang if in_lang in ("vi", "en") else curr_lang

    curr_nfmt = config.get("NAME_FORMAT", DEFAULT_CONFIG["NAME_FORMAT"])
    print(f"\nCác từ khóa hỗ trợ: {{base_name}}, HH, mm, ss, DD, MM, YYYY, {{gmt}}, {{random}}, {{thu}}, {{day}}, {{city}}, {{music}}, {{music_or_weather}}")
    print("Ví dụ mẫu: {base_name} | HH:mm - DD/MM | {gmt} | {random}")
    in_nfmt = input(f"Định dạng Tên (NAME_FORMAT) [{curr_nfmt}]: ").strip()
    name_format = in_nfmt if in_nfmt else curr_nfmt

    curr_bfmt = config.get("BIO_FORMAT", DEFAULT_CONFIG["BIO_FORMAT"])
    print(f"\nCác từ khóa hỗ trợ: {{weather}}, {{music}}, {{music_or_weather}}, HH, mm, DD, MM, YYYY, {{city}}")
    print("Ví dụ mẫu: {music_or_weather} ⏰ HH:mm hoặc {weather} ⏰ HH:mm")
    in_bfmt = input(f"Định dạng Bio (BIO_FORMAT) [{curr_bfmt}]: ").strip()
    bio_format = in_bfmt if in_bfmt else curr_bfmt

    return {
        "BASE_NAME": base_name,
        "TIMEZONE": timezone,
        "LANGUAGE": language,
        "NAME_FORMAT": name_format,
        "BIO_FORMAT": bio_format
    }

def preview_profile(config: dict):
    print(f"\n{BOLD}{CYAN}=== XEM TRƯỚC (PREVIEW) PROFILE TELEGRAM ==={RESET}")
    base_name = config.get("BASE_NAME", "tên")
    city = config.get("CITY", "Bac Ninh")
    tz_str = config.get("TIMEZONE", "Asia/Ho_Chi_Minh")

    try:
        from profile_engine import generate_preview, generate_bio_preview
        p_name, _ = generate_preview()
        bio_preview = generate_bio_preview(config)
    except Exception:
        p_name = f"{base_name} | 12:00 - 01/01/2026"
        p_bio = f"📍 {city} ⏰ 12:00"
        bio_preview = {
            "current": p_bio,
            "current_len": len(p_bio),
            "with_music": f"🎧 Blinding Lights - The Weeknd ⏰ 12:00",
            "with_music_len": 40,
            "no_music": p_bio,
            "no_music_len": len(p_bio),
            "is_over_limit": len(p_bio) > 70
        }

    trunc_name_notice = f" {YELLOW}(Tối đa 64 ký tự){RESET}" if len(p_name) > 64 else f" {GREEN}(Hợp lệ){RESET}"
    bio_valid_notice = f" {RED}(VƯỢT GIỚI HẠN 70 KÝ TỰ!){RESET}" if bio_preview["is_over_limit"] else f" {GREEN}(Hợp lệ){RESET}"

    print(f"\n  ┌─ {BOLD}TÊN HIỂN THỊ (First Name):{RESET}")
    print(f"  │  {GREEN}{p_name[:64]}{RESET} ({len(p_name)}/64 ký tự){trunc_name_notice}")
    print(f"  ├─ {BOLD}TIỂU SỬ (Bio/About) THỰC TẾ:{RESET}")
    print(f"  │  {GREEN}{bio_preview['current']}{RESET} ({bio_preview['current_len']}/70 ký tự){bio_valid_notice}")
    print(f"  ├─ {BOLD}KỊCH BẢN BIO KHI PHÁT NHẠC (Last.fm):{RESET}")
    print(f"  │  {CYAN}{bio_preview['with_music']}{RESET} ({bio_preview['with_music_len']}/70 ký tự)")
    print(f"  ├─ {BOLD}KỊCH BẢN BIO KHI KHÔNG NGHE NHẠC:{RESET}")
    print(f"  │  {CYAN}{bio_preview['no_music']}{RESET} ({bio_preview['no_music_len']}/70 ký tự)")
    print(f"  └────────────────────────────────────────────────")

def run_wizard():
    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════════════╗")
    print(f"║     HƯỚNG DẪN CÀI ĐẶT NHANH (FULL SETUP WIZARD)           ║")
    print(f"╚═══════════════════════════════════════════════════════════╝{RESET}")

    check_dependencies()
    config = load_env()

    updates = {}
    updates.update(configure_telegram(config))
    config.update(updates)

    updates.update(configure_helper_bot(config))
    config.update(updates)

    updates.update(configure_weather(config))
    config.update(updates)

    updates.update(configure_lastfm(config))
    config.update(updates)

    updates.update(configure_display(config))
    config.update(updates)

    save_env(updates)
    preview_profile(config)

    print(f"\n{GREEN}{BOLD}🎉 CÀI ĐẶT HOÀN TẤT!{RESET}")
    ask_start_bot()

def ask_start_bot():
    print(f"\n{BOLD}Bạn muốn làm gì tiếp theo?{RESET}")
    print("  1. Chạy hệ thống đầy đủ ngay bây giờ (python3 name.py)")
    print("  2. Chạy Helper Bot riêng biệt (python3 helper_bot.py)")
    print("  3. Chạy nền bằng PM2 (pm2 start name.py)")
    print("  0. Quay lại / Thoát")
    c = input(f"{YELLOW}Lựa chọn của bạn [0]: {RESET}").strip()
    if c == "1":
        print(f"\n{CYAN}Đang khởi động hệ thống... (Nhấn Ctrl+C để dừng){RESET}\n")
        subprocess.call([sys.executable, "name.py"])
    elif c == "2":
        print(f"\n{CYAN}Đang khởi động Helper Bot... (Nhấn Ctrl+C để dừng){RESET}\n")
        subprocess.call([sys.executable, "helper_bot.py"])
    elif c == "3":
        try:
            print(f"\n{CYAN}Đang chạy pm2 start name.py...{RESET}")
            subprocess.call(["pm2", "start", "name.py", "--name", "tele-updater", "--interpreter", sys.executable])
            subprocess.call(["pm2", "save"])
            print(f"{GREEN}✔ Hệ thống đã được khởi chạy dưới nền với PM2!{RESET}")
            print(f"  - Xem log: {CYAN}pm2 logs tele-updater{RESET}")
            print(f"  - Dừng bot: {CYAN}pm2 stop tele-updater{RESET}")
        except Exception as e:
            print(f"{RED}Không thể gọi lệnh pm2: {e}{RESET}")

def main():
    while True:
        config = load_env()
        print(f"\n{BOLD}{CYAN}============================================================")
        print("  ⚙️  TELEGRAM PROFILE UPDATER & HELPER BOT - SETUP TOOL")
        print(f"============================================================{RESET}")
        print("  1. Chạy cài đặt từng bước (Quick Setup Wizard - Khuyên dùng)")
        print("  2. Cấu hình Telegram User Account & Đăng nhập lấy Session String")
        print("  3. Cấu hình Helper Bot (BOT_TOKEN từ @BotFather & ADMIN_ID)")
        print("  4. Cấu hình thời tiết OpenWeatherMap & Thành phố")
        print("  5. Cấu hình âm nhạc Last.fm (Spotify / Apple Music)")
        print("  6. Cấu hình hiển thị (Tên cố định, Múi giờ, Định dạng)")
        print("  7. Kiểm tra và cài đặt thư viện phụ thuộc (pip install)")
        print("  8. Xem trước (Preview) Name & Bio hiện tại")
        print("  9. Khởi động hệ thống (Chạy trực tiếp hoặc qua PM2)")
        print("  10. Cài qua Telegram (chỉ nhập BOT_TOKEN + ADMIN_ID, rồi chạy bot)")
        print("  0. Thoát")
        print(f"{CYAN}------------------------------------------------------------{RESET}")

        choice = input(f"{YELLOW}Nhập lựa chọn (0-10): {RESET}").strip()

        if choice == "1":
            run_wizard()
        elif choice == "2":
            updates = configure_telegram(config)
            save_env(updates)
        elif choice == "3":
            updates = configure_helper_bot(config)
            save_env(updates)
        elif choice == "4":
            updates = configure_weather(config)
            save_env(updates)
        elif choice == "5":
            updates = configure_lastfm(config)
            save_env(updates)
        elif choice == "6":
            updates = configure_display(config)
            save_env(updates)
        elif choice == "7":
            check_dependencies()
        elif choice == "8":
            preview_profile(config)
        elif choice == "9":
            ask_start_bot()
        elif choice == "10":
            check_dependencies()
            run_bot_first_setup(config)
        elif choice in ("0", "q", "exit"):
            print(f"{GREEN}Tạm biệt!{RESET}")
            break
        else:
            print(f"{RED}Lựa chọn không hợp lệ, vui lòng chọn lại.{RESET}")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print(f"\n\n{YELLOW}Đã thoát công cụ cấu hình.{RESET}")
