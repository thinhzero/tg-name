"""AFK/on và ping: không thêm thư viện, không đăng ký handler trùng."""

import asyncio
import re
import shutil
import time
from collections import OrderedDict
from html import escape

from i18n import get_text
from shell_commands import clipped_html
from chat_logging import chat_log


STARTED_AT = time.monotonic()
DEFAULT_AFK_DELETE_AFTER = 10


def parse_afk_args(argument):
    """[thời gian tự xóa] [lý do]; số không có đơn vị được hiểu là giây."""
    parts = argument.strip().split(maxsplit=1)
    if not parts:
        return DEFAULT_AFK_DELETE_AFTER, ""
    token = parts[0]
    match = re.fullmatch(r"([0-9]{1,6})([smh]?)", token, re.IGNORECASE)
    if match:
        seconds = int(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600}[match[2].lower()]
        if not 1 <= seconds <= 86400:
            raise ValueError("AFK deletion time must be between 1 second and 24 hours")
        return seconds, parts[1].strip() if len(parts) > 1 else ""
    if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?[smh]?", token, re.IGNORECASE):
        raise ValueError("Invalid AFK deletion time")
    return DEFAULT_AFK_DELETE_AFTER, argument.strip()


def elapsed(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


class Presence:
    def __init__(self, cooldown=60, delete_after=DEFAULT_AFK_DELETE_AFTER):
        self.since = None
        self.reason = ""
        self.cooldown = cooldown
        self.delete_after = delete_after
        self.replies = OrderedDict()
        self.tasks = set()

    @property
    def active(self):
        return self.since is not None

    def enable(self, reason="", *, delete_after=None):
        if delete_after is not None:
            self.delete_after = delete_after
        self.since = time.monotonic()
        self.reason = reason[:500].strip()
        self.replies.clear()

    def disable(self):
        self.since = None
        self.reason = ""
        self.replies.clear()

    def notice(self, lang="vi", name=None):
        return get_text(
            "afk_reply" if name is not None else "afk_enabled", lang,
            name=escape(name or ""), reason=escape(self.reason or get_text("afk_no_reason", lang)),
            duration=elapsed(time.monotonic() - self.since) if self.active else elapsed(0),
            delete_after=self.delete_after,
        )

    async def incoming(self, event, owner_id, name, lang="vi"):
        if not self.active or event.out or not owner_id:
            return
        if event.sender_id in (int(owner_id), 777000) or getattr(event.message, "via_bot_id", None):
            return
        since = self.since
        mentioned = bool(getattr(event, "is_private", False) or getattr(event.message, "mentioned", False))
        if not mentioned and event.is_reply:
            try:
                reply = await event.get_reply_message()
                mentioned = reply is not None and reply.sender_id == int(owner_id)
            except Exception:
                return
        if not mentioned or not self.active or self.since != since:
            return
        try:
            sender = await event.get_sender()
        except Exception:
            return
        if getattr(sender, "bot", False) or not self.active or self.since != since:
            return
        chat_log.afk(event, sender, self.reason, elapsed(time.monotonic() - since))
        key = (event.chat_id, event.sender_id)
        now = time.monotonic()
        if key in self.replies and now - self.replies[key] < self.cooldown:
            return
        self.replies[key] = now
        self.replies.move_to_end(key)
        while len(self.replies) > 1024:
            self.replies.popitem(last=False)
        try:
            delete_after = self.delete_after
            message = await event.reply(self.notice(lang, name), parse_mode="html", silent=True)
        except Exception:
            return
        if not self.active or self.since != since:
            try:
                await message.delete()
            except Exception:
                pass
            return
        task = asyncio.create_task(self._delete_later(message, delete_after))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _delete_later(self, message, delete_after):
        try:
            await asyncio.sleep(delete_after)
            await message.delete()
        except Exception:
            pass

    async def close(self):
        self.disable()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()


async def ping_message(target, edit, lang="vi"):
    target = target or "google.com"
    if target and (not re.fullmatch(r"[A-Za-z0-9_.:-]{1,253}", target) or target.startswith("-")):
        await edit(get_text("ping_usage", lang), parse_mode="html")
        return
    started = time.monotonic()
    await edit("🏓 Pong!", parse_mode="html")
    latency = (time.monotonic() - started) * 1000
    output = ""
    if target:
        executable = shutil.which("ping")
        if not executable:
            output = get_text("ping_missing", lang)
        else:
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    executable, "-c", "1", "-W", "2", target,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                data, _ = await asyncio.wait_for(process.communicate(), timeout=5)
                output = data.decode("utf-8", errors="replace")[:4096]
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError):
                output = get_text("ping_failed", lang)
            finally:
                if process is not None and process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.communicate()
    text = get_text("ping_result", lang, latency=f"{latency:.2f}", uptime=elapsed(time.monotonic() - STARTED_AT))
    if target:
        output, _ = clipped_html(output or get_text("ping_failed", lang), 2200)
        text += f"\n🌐 <code>{escape(target)}</code>\n<pre>{output}</pre>"
    await edit(text, parse_mode="html")


presence = Presence()
