"""Tải link trực tiếp → Telegram: một tác vụ, file tạm riêng, có giới hạn và hủy."""

import asyncio
import re
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from urllib.parse import unquote

from i18n import get_text
from public_http import PublicHTTPError, checked_url, open_public, public_session
from shell_commands import clipped_html


MAX_FILE_SIZE = 100 * 1024 * 1024
TRANSFER_TIMEOUT = 300


def readable_size(size):
    value = max(0, size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def readable_time(seconds):
    if seconds is None:
        return "?"
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def safe_filename(value):
    value = unicodedata.normalize("NFKC", value).replace("\\", "/").split("/")[-1]
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    value = re.sub(r'[<>:"|?*]', "_", value).strip(" .")
    return value.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "download.bin"


def guess_filename(url, headers):
    disposition = headers.get("Content-Disposition", "")
    if disposition and len(disposition) <= 4096:
        message = Message()
        message["Content-Disposition"] = disposition
        name = message.get_filename()
        if name:
            return safe_filename(name)
    return safe_filename(unquote(checked_url(url).path))


async def link_argument(event, argument):
    if argument.strip():
        return argument.strip()
    if not getattr(event, "is_reply", False):
        return ""
    try:
        reply = await event.get_reply_message()
    except Exception:
        return ""
    text = getattr(reply, "raw_text", "") or ""
    return next((part for part in text.split() if part.startswith(("https://", "http://"))), "")


class TransferProgress:
    def __init__(self, edit, filename, lang="vi", interval=2):
        self.edit, self.filename, self.lang, self.interval = edit, filename, lang, interval
        self.phase = None
        self.started = 0
        self.last_edit = float("-inf")
        self.available = True

    async def update(self, current, total, phase="download"):
        if not self.available:
            return
        now = time.monotonic()
        changed = phase != self.phase
        if changed:
            self.phase, self.started = phase, now
        if not changed and now - self.last_edit < self.interval:
            return
        self.last_edit = now
        current, total = max(0, current), max(0, total or 0)
        percent = min(100, current * 100 / total) if total else None
        count = min(10, int(percent // 10)) if percent is not None else 0
        bar = "█" * count + "─" * (10 - count)
        elapsed = max(0, now - self.started)
        speed = current / max(elapsed, 1)
        text = get_text(
            "transfer_progress", self.lang, phase=get_text(f"transfer_{phase}", self.lang),
            filename=clipped_html(self.filename, 240)[0], bar=bar,
            percent=f"{percent:.1f}%" if percent is not None else "?",
            current=readable_size(current), total=readable_size(total) if total else "?",
            speed=readable_size(speed), elapsed=readable_time(elapsed),
            eta=readable_time(max(0, total - current) / speed if total and speed else None),
        )
        try:
            # Không tạo task cho từng chunk; progress chậm/lỗi không làm hỏng file.
            await asyncio.wait_for(self.edit(text, parse_mode="html"), timeout=5)
        except Exception:
            # Không liên tục đợi retry/edit một tin đã xóa hoặc bị FloodWait.
            self.available = False


@dataclass
class TransferJob:
    task: asyncio.Task
    owner_id: int
    chat_id: int
    userbot: bool
    cancelled_by_owner: bool = False


class FileTransfers:
    def __init__(self, max_size=MAX_FILE_SIZE, timeout=TRANSFER_TIMEOUT):
        self.max_size, self.timeout = max_size, timeout
        self.job = None

    @staticmethod
    async def _status(edit, key, lang, **details):
        try:
            await asyncio.wait_for(edit(get_text(key, lang, **details), parse_mode="html"), timeout=5)
        except Exception:
            # Tin trạng thái bị xóa/lỗi mạng không đổi kết quả upload hoặc giữ job vô hạn.
            pass

    async def _transfer(self, url, edit, upload, directory, lang):
        async with public_session(timeout=120) as session:
            async with open_public(session, url) as response:
                total = response.content_length or 0
                if total > self.max_size:
                    raise PublicHTTPError("too_large")
                filename = guess_filename(str(response.url), response.headers)
                path = directory / filename
                progress = TransferProgress(edit, filename, lang)
                downloaded = 0
                with path.open("xb") as handle:
                    async for chunk in response.content.iter_chunked(65536):
                        downloaded += len(chunk)
                        if downloaded > self.max_size:
                            raise PublicHTTPError("too_large")
                        handle.write(chunk)
                        await progress.update(downloaded, total)
        if not downloaded:
            raise PublicHTTPError("empty_file")
        await progress.update(0, downloaded, "upload")

        async def upload_progress(current, total):
            await progress.update(current, total, "upload")
        await upload(path, filename, upload_progress)
        return filename

    async def run(self, url, edit, upload, *, owner_id, chat_id, userbot=False, lang="vi"):
        if not url:
            await self._status(edit, "transfer_usage", lang)
            return False
        try:
            url = str(checked_url(url))
        except PublicHTTPError:
            await self._status(edit, "transfer_unsafe", lang)
            return False
        if self.job is not None:
            await self._status(edit, "transfer_busy", lang)
            return False
        job = self.job = TransferJob(asyncio.current_task(), owner_id, chat_id, userbot)
        try:
            await self._status(edit, "transfer_starting", lang)
            with tempfile.TemporaryDirectory(prefix="tg-name-transfer-") as temporary:
                filename = await asyncio.wait_for(self._transfer(url, edit, upload, Path(temporary), lang), timeout=self.timeout)
            await self._status(edit, "transfer_done", lang, filename=clipped_html(filename, 240)[0])
            return True
        except asyncio.CancelledError:
            if not job.cancelled_by_owner:
                raise
            await self._status(edit, "transfer_cancelled", lang)
        except asyncio.TimeoutError:
            await self._status(edit, "transfer_timeout", lang)
        except Exception as exc:
            key = "transfer_failed"
            if isinstance(exc, PublicHTTPError):
                key = {"unsafe_url": "transfer_unsafe", "too_large": "transfer_too_large", "empty_file": "transfer_empty"}.get(exc.reason, key)
            await self._status(edit, key, lang, limit=readable_size(self.max_size))
        finally:
            if self.job is job:
                self.job = None
        return False

    def cancel(self, owner_id, chat_id, userbot=False):
        job = self.job
        if job is None or (job.owner_id, job.chat_id, job.userbot) != (owner_id, chat_id, userbot) or job.task.done():
            return False
        job.cancelled_by_owner = True
        job.task.cancel()
        return True

    async def close(self, *, userbot=None):
        job = self.job
        if job and (userbot is None or job.userbot == userbot) and job.task is not asyncio.current_task():
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)


file_transfers = FileTransfers()
