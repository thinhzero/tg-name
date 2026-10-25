"""Chạy shell Linux cho admin: không tương tác, có timeout và giới hạn output."""

import asyncio
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

from i18n import get_text


PROJECT_DIR = Path(__file__).resolve().parent
SENSITIVE_KEYS = {"BOT_TOKEN", "API_HASH", "SESSION_STRING", "WEATHER_API", "LASTFM_API_KEY"}
SENSITIVE_NAME = re.compile(r"(?:^|_)(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|API_HASH|SESSION_STRING|PRIVATE_KEY)(?:_|$)", re.I)


class ShellError(Exception):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


@dataclass
class ShellResult:
    command: str
    output: str
    returncode: int
    timed_out: bool = False
    truncated: bool = False


def config_secrets(config):
    return [value for key, value in config.items() if value and (key in SENSITIVE_KEYS or SENSITIVE_NAME.search(key))]


def redact(text, values):
    for value in sorted(set(values), key=len, reverse=True):
        if value:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})", "[REDACTED]", text)
    text = re.sub(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b", "[REDACTED]", text)
    return re.sub(r"-----BEGIN [^\n]*PRIVATE KEY-----.*?(?:-----END [^\n]*PRIVATE KEY-----|$)", "[REDACTED PRIVATE KEY]", text, flags=re.S)


class ShellRunner:
    def __init__(self, cwd=PROJECT_DIR, timeout=30, max_output=65536):
        self.cwd = Path(cwd)
        self.timeout = timeout
        self.max_output = max_output
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize(command):
        command = command.strip()
        # Chấp nhận cả cách gõ ví dụ /shell {uptime}.
        if command.startswith("{") and command.endswith("}"):
            command = command[1:-1].strip()
        if not command or len(command) > 4096 or "\0" in command:
            raise ShellError("shell_usage")
        return command

    async def run(self, command, secret_values=()):
        if not sys.platform.startswith("linux"):
            raise ShellError("shell_linux_only")
        command = self.normalize(command)
        if self._lock.locked():
            raise ShellError("shell_busy")
        async with self._lock:
            env = os.environ.copy()
            secrets = list(secret_values)
            for key in list(env):
                if key in SENSITIVE_KEYS or SENSITIVE_NAME.search(key):
                    secrets.append(env.pop(key))
            shell = "/bin/bash" if Path("/bin/bash").is_file() else "/bin/sh"
            try:
                process = await asyncio.create_subprocess_exec(
                    shell, "-c", command, cwd=self.cwd, env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ShellError("shell_failed") from exc

            output = bytearray()
            limited = False
            timed_out = False

            def kill_group():
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            async def stop():
                kill_group()
                try:
                    await asyncio.wait_for(process.communicate(), timeout=5)
                except asyncio.TimeoutError:
                    pass

            async def collect():
                nonlocal limited
                while chunk := await process.stdout.read(4096):
                    available = self.max_output - len(output)
                    output.extend(chunk[:available])
                    if len(chunk) > available and not limited:
                        limited = True
                        kill_group()
                await process.wait()

            try:
                await asyncio.wait_for(collect(), timeout=self.timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await stop()
            except BaseException:
                await stop()
                raise

            text = output.decode("utf-8", errors="replace")
            # Bỏ escape màu/điều khiển terminal, giữ newline và tab để dễ đọc.
            text = re.sub(r"\x1b\][^\x07]*?(?:\x07|\x1b\\)", "", text)
            text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
            text = "".join(char for char in text if char in "\n\t" or (ord(char) >= 32 and ord(char) != 127))
            return ShellResult(
                redact(command, secrets), redact(text.strip(), secrets),
                process.returncode if process.returncode is not None else -1,
                timed_out=timed_out, truncated=limited,
            )


def clipped_html(text, budget):
    parts = []
    size = 0
    for char in text:
        part = escape(char)
        units = len(part.encode("utf-16-le")) // 2
        if size + units > budget:
            return "".join(parts) + "…", True
        parts.append(part)
        size += units
    return "".join(parts), False


def format_shell_result(result, lang="vi"):
    command, command_shortened = clipped_html(result.command, 500)
    output, output_shortened = clipped_html(result.output or get_text("shell_empty_output", lang), 2500)
    text = f"💻 <b>Shell · Linux</b>\n<code>{command}</code>\nExit: <code>{result.returncode}</code>\n<pre>{output}</pre>"
    if result.timed_out:
        text += "\n" + get_text("shell_timeout", lang)
    if result.truncated or output_shortened or command_shortened:
        text += "\n" + get_text("shell_truncated", lang)
    return text


shell_runner = ShellRunner()


async def run_shell_message(command, edit, lang="vi", runner=shell_runner, secret_values=()):
    try:
        result = await runner.run(command, secret_values=secret_values)
        message = format_shell_result(result, lang)
    except ShellError as exc:
        message = get_text(exc.key, lang)
    except Exception:
        message = get_text("shell_failed", lang)
    await edit(message, parse_mode="html")
