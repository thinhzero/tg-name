"""Chuẩn bị thư viện trước khi import các module Telegram (chỉ dùng stdlib)."""

import importlib
import importlib.util
import os
import subprocess
import sys
import venv
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEPENDENCIES = {"telethon": "Telethon", "dotenv": "python-dotenv", "aiohttp": "aiohttp", "pytz": "pytz", "speedtest": "speedtest-cli"}


def missing_dependencies():
    missing = []
    for module, package in DEPENDENCIES.items():
        try:
            importlib.import_module(module)
        except (ImportError, OSError):
            missing.append(package)
    return missing


def ensure_dependencies():
    missing = missing_dependencies()
    if not missing:
        return True
    print(f"[📦] Thư viện còn thiếu/lỗi: {', '.join(missing)}", flush=True)
    requirements = PROJECT_DIR / "requirements.txt"
    if not requirements.is_file():
        print("[❌] Không tìm thấy requirements.txt cạnh name.py. Hãy tải đầy đủ repo.")
        return False

    if sys.prefix == sys.base_prefix:
        # Không ép pip ghi vào Python hệ thống / bỏ qua PEP 668.
        environment = PROJECT_DIR / ".venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        try:
            if Path(sys.executable).absolute() == python.absolute():
                print("[❌] Python trong .venv không nhận đúng virtualenv; hãy sửa môi trường này trước khi chạy lại.")
                return False
            if not environment.exists():
                print("[📦] Đang tạo .venv riêng cho bot...", flush=True)
                venv.EnvBuilder(with_pip=True).create(environment)
            elif not (environment / "pyvenv.cfg").is_file() or not python.is_file():
                print("[❌] .venv đã tồn tại nhưng không phải virtualenv hợp lệ; không ghi đè thư mục này.")
                return False
            original = getattr(sys, "orig_argv", [sys.executable, *sys.argv])
            print("[🔄] Chuyển sang Python trong .venv...", flush=True)
            os.execv(str(python), [str(python), *original[1:]])
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[❌] Không chuẩn bị được .venv ({type(exc).__name__}). Ubuntu/Debian: cài python3-venv rồi chạy lại.")
        return False

    try:
        if importlib.util.find_spec("pip") is None:
            result = subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], timeout=120)
            if result.returncode:
                print("[❌] Không cài được pip. Hãy cài pip cho môi trường Python này rồi chạy lại.")
                return False
        print("[📦] Đang tự cài thư viện từ requirements.txt...", flush=True)
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
            "--no-input", "-r", str(requirements),
        ], cwd=PROJECT_DIR, timeout=600)
        if result.returncode:
            print("[❌] Cài thư viện thất bại. Kiểm tra mạng/quyền cài đặt rồi chạy lại python name.py.")
            return False
        importlib.invalidate_caches()
        if missing_dependencies():
            print("[❌] Thư viện vẫn chưa dùng được sau khi cài. Kiểm tra log pip phía trên.")
            return False
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[❌] Không cài được thư viện ({type(exc).__name__}). Kiểm tra pip/mạng rồi chạy lại.")
        return False
