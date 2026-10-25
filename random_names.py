"""Danh sách random trong name.txt; UID phụ thuộc nội dung, không phụ thuộc số dòng."""

import hashlib
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
NAMES_FILE = PROJECT_DIR / "name.txt"
EXAMPLE_FILE = PROJECT_DIR / "name.example.txt"


@dataclass(frozen=True)
class RandomEntry:
    uid: str
    text: str


class RandomNames:
    def __init__(self, path=NAMES_FILE, example_path=None):
        self.path = Path(path)
        self.example_path = Path(example_path) if example_path is not None else None

    def entries(self):
        """Đọc lại mỗi lần để nhận cả thay đổi khi chỉnh name.txt bằng tay."""
        if not self.path.exists() and self.example_path is not None:
            seed = self.example_path.read_text(encoding="utf-8-sig")
            try:
                with self.path.open("x", encoding="utf-8") as handle:
                    handle.write(seed)
            except FileExistsError:
                pass
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return []
        values = dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())
        return [RandomEntry(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], value) for value in values]

    def _write(self, entries):
        # Ghi file tạm cùng thư mục rồi thay thế, tránh name.txt bị ghi dở.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".name-", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.writelines(f"{entry.text}\n" for entry in entries)
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def add(self, text):
        entries = self.entries()
        existing = {entry.text for entry in entries}
        added = []
        for line in text.splitlines():
            value = line.strip()
            if value and value not in existing:
                entry = RandomEntry(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], value)
                added.append(entry)
                existing.add(value)
        if added:
            self._write(entries + added)
        return added

    def remove(self, uid):
        uid = uid.strip().lower()
        entries = self.entries()
        matches = [entry for entry in entries if entry.uid == uid]
        # Không xóa nếu có xung đột hash (dù rất hiếm).
        if len(matches) != 1:
            return None
        self._write([entry for entry in entries if entry.uid != uid])
        return matches[0]

    def choose(self):
        entries = self.entries()
        return random.choice(entries).text if entries else ""


random_names = RandomNames(NAMES_FILE, EXAMPLE_FILE)
