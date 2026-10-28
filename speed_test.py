"""Speedtest kế thừa ý tưởng source sth, chạy subprocess hủy được, không share/IP."""

import asyncio
import importlib.util
import ipaddress
import json
import math
import re
import shlex
import sys

from file_transfer import TransferJob
from i18n import get_text
from shell_commands import ShellRunner, clipped_html
from chat_logging import chat_log


def hidden_ips(text):
    def hide(match):
        try:
            ipaddress.ip_address(match[0])
            return "[hidden]"
        except ValueError:
            return match[0]
    text = re.sub(r"(?:\d{1,3}\.){3}\d{1,3}", hide, text)
    return re.sub(r"[0-9a-fA-F:.]*:[0-9a-fA-F:.]+(?:%[A-Za-z0-9_-]+)?", hide, text)


def speed_result(output, lang="vi"):
    data = json.loads(output)
    values = []
    for key in ("download", "upload", "ping"):
        value = data[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 10 ** 15:
            raise ValueError("Invalid speed result")
        values.append(value)
    server, client = data.get("server", {}), data.get("client", {})
    def field(value):
        return clipped_html(hidden_ips(value if isinstance(value, str) else "—"), 150)[0]
    return get_text("speed_result", lang, download=f"{values[0] / 1e6:.2f}", upload=f"{values[1] / 1e6:.2f}", ping=f"{values[2]:.2f}", server=field(server.get("name")), country=field(server.get("country")), isp=field(client.get("isp")))


class SpeedTests:
    def __init__(self, runner=None):
        self.runner = runner or ShellRunner(timeout=120, max_output=65536)
        self.job = None

    async def run(self, edit, *, owner_id, chat_id, userbot=False, lang="vi", secret_values=()):
        if self.job is not None:
            await edit(get_text("speed_busy", lang), parse_mode="html")
            return
        if importlib.util.find_spec("speedtest") is None:
            await edit(get_text("speed_missing", lang), parse_mode="html")
            return
        job = self.job = TransferJob(asyncio.current_task(), owner_id, chat_id, userbot)
        try:
            await edit(get_text("speed_running", lang), parse_mode="html")
            # Không gọi results.share(), không đưa JSON thô hoặc ảnh share vào chat.
            command = shlex.join([sys.executable, "-m", "speedtest", "--json", "--secure", "--no-pre-allocate"])
            result = await self.runner.run(command, secret_values=secret_values)
            if result.timed_out:
                text = get_text("speed_timeout", lang)
            elif result.returncode or result.truncated:
                text = get_text("speed_failed", lang)
                chat_log.emit("error", {"action": "speedtest", "error": "Measurement failed"})
            else:
                text = speed_result(result.output, lang)
            await edit(text, parse_mode="html")
        except asyncio.CancelledError:
            if not job.cancelled_by_owner:
                raise
            await edit(get_text("speed_cancelled", lang), parse_mode="html")
        except Exception as exc:
            chat_log.emit("error", {"action": "speedtest", "error": type(exc).__name__})
            await edit(get_text("speed_failed", lang), parse_mode="html")
        finally:
            if self.job is job:
                self.job = None

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


speed_tests = SpeedTests()
