"""Thông báo một lần sau restart; chỉ lưu metadata commit/snapshot, không lưu khóa."""

import asyncio
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime
from html import escape
from pathlib import Path

from i18n import get_text


STATUS_DIR = ".update-status"
NOTICE_ENV = "TG_NAME_UPDATE_NOTICE"


class UpdateCompletion:
    def __init__(self, project_dir):
        self.root = Path(project_dir).resolve()
        self.directory = self.root / STATUS_DIR
        self.lock = asyncio.Lock()
        self.delivered = None

    @staticmethod
    def checked(data):
        if not isinstance(data, dict):
            return None
        old, latest, snapshot = (data.get(key) for key in ("current", "latest", "snapshot"))
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40,64}", value) for value in (old, latest)) or old == latest:
            return None
        if not isinstance(snapshot, str) or len(snapshot) > 256:
            return None
        path = Path(snapshot)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 2 or path.parts[0] != "snapshots":
            return None
        owner = data.get("owner_id")
        if not isinstance(owner, int) or isinstance(owner, bool) or owner <= 0 or not isinstance(data.get("userbot"), bool):
            return None
        receipt_id = hashlib.sha256(f"{latest}\n{snapshot}".encode()).hexdigest()
        return {
            "id": receipt_id, "current": old, "latest": latest, "snapshot": snapshot,
            "owner_id": owner, "userbot": data["userbot"], "lang": "en" if data.get("lang") == "en" else "vi",
        }

    @staticmethod
    def read(path):
        try:
            if path.is_symlink() or path.stat().st_size > 16384:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, filename, data):
        if self.directory.is_symlink():
            raise OSError("Update status directory must not be a symlink")
        self.directory.mkdir(mode=0o700, exist_ok=True)
        target = self.directory / filename
        if target.is_symlink():
            raise OSError("Update status file must not be a symlink")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, prefix=".pending-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def record(self, result, destination):
        data = self.checked({"current": result.current, "latest": result.latest, "snapshot": result.snapshot, **destination})
        if data is None:
            raise ValueError("Invalid update completion metadata")
        # execv giữ environment: vẫn có thể báo hoàn tất nếu ghi file thất bại.
        os.environ[NOTICE_ENV] = json.dumps(data)
        self.write("pending.json", data)

    def legacy_receipt(self, current, owner_id, lang, userbot):
        # Bản cũ đã tạo snapshot nhưng chưa biết ghi pending.json. Nhận diện lần
        # nâng cấp đầu tiên từ manifest gần đây, không suy đoán từ git pull/HEAD.
        snapshots = self.root / "snapshots"
        if snapshots.is_symlink() or not snapshots.is_dir():
            return None
        candidates = []
        for manifest in snapshots.glob("*/snapshot.json"):
            if manifest.parent.is_symlink():
                continue
            data = self.read(manifest)
            if not isinstance(data, dict) or data.get("to_commit") != current:
                continue
            try:
                created = datetime.fromisoformat(data["created_at"]).timestamp()
            except (ValueError, TypeError, KeyError, OverflowError):
                continue
            if not -60 <= time.time() - created <= 86400:
                continue
            receipt = self.checked({
                "current": data.get("from_commit"), "latest": current,
                "snapshot": manifest.parent.relative_to(self.root).as_posix(),
                "owner_id": owner_id, "userbot": userbot, "lang": lang,
            })
            if receipt:
                candidates.append((created, receipt))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    async def deliver(self, send, get_current, owner_id, lang="vi", userbot=False, legacy=True):
        async with self.lock:
            try:
                if self.directory.is_symlink():
                    return False
                data = None
                if os.environ.get(NOTICE_ENV):
                    try:
                        data = self.checked(json.loads(os.environ[NOTICE_ENV]))
                    except ValueError:
                        pass
                data = data or self.checked(self.read(self.directory / "pending.json"))
                if data and (data["owner_id"] != owner_id or data["userbot"] != userbot):
                    return False
                if data is None and (not legacy or not (self.root / "snapshots").is_dir()):
                    return False
                current = await get_current()
                recovered = data is None
                data = data or self.legacy_receipt(current, owner_id, lang, userbot)
                if not data or current != data["latest"]:
                    return False
                last = self.read(self.directory / "delivered.json") or {}
                if data["id"] == self.delivered or (isinstance(last, dict) and last.get("id") == data["id"]):
                    return False
                if recovered:
                    # Giữ lại lần nâng cấp từ updater cũ cả khi lần gửi đầu thất bại
                    # và admin chỉ mở lại bot sau cửa sổ nhận diện 24 giờ.
                    os.environ[NOTICE_ENV] = json.dumps(data)
                    try:
                        self.write("pending.json", data)
                    except OSError:
                        pass
                await send(get_text(
                    "self_update_completed", data["lang"], old=data["current"][:7], new=data["latest"][:7],
                    snapshot=escape(data["snapshot"]),
                ), parse_mode="html")
                self.delivered = data["id"]
                self.write("delivered.json", {"id": data["id"], "latest": data["latest"]})
                pending = self.read(self.directory / "pending.json")
                if isinstance(pending, dict) and pending.get("id") == data["id"]:
                    (self.directory / "pending.json").unlink()
                try:
                    inherited = json.loads(os.environ.get(NOTICE_ENV, "null"))
                except ValueError:
                    inherited = None
                if isinstance(inherited, dict) and inherited.get("id") == data["id"]:
                    os.environ.pop(NOTICE_ENV, None)
                return True
            except Exception as exc:
                # Không ảnh hưởng khởi động, không in request/URL/giá trị API.
                print(f"[ℹ️] Chưa hoàn tất thông báo cập nhật ({type(exc).__name__}); gửi /start để thử lại.")
                return False
