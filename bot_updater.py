"""Tải bản mới từ GitHub, cập nhật fast-forward và khởi động lại tiến trình."""

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path


REPO_URL = "https://github.com/thinhzero/tg-name.git"
UPDATE_BRANCH = "main"
PROJECT_DIR = Path(__file__).resolve().parent


class UpdateError(Exception):
    def __init__(self, key, **details):
        super().__init__(key)
        self.key = key
        self.details = details


@dataclass
class UpdateResult:
    current: str
    latest: str
    updated: bool = False


class BotUpdater:
    def __init__(self, project_dir=PROJECT_DIR):
        self.project_dir = Path(project_dir).resolve()
        self._lock = asyncio.Lock()
        self._restart_pending = False
        self.restart_event = asyncio.Event()

    @property
    def is_busy(self):
        return self._lock.locked() or self._restart_pending

    async def _run(self, *command, cwd=None, timeout=120, allowed_codes=(0,)):
        env = os.environ.copy()
        env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd or self.project_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if process.returncode is None:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise UpdateError("self_update_timeout") from exc
        text = output.decode("utf-8", errors="replace").rstrip("\r\n")
        if process.returncode not in allowed_codes:
            raise UpdateError("self_update_command_failed", details=text[-1800:])
        return subprocess.CompletedProcess(command, process.returncode, stdout=text)

    async def _git(self, *args, **kwargs):
        return await self._run("git", *args, **kwargs)

    async def _check_clean(self):
        result = await self._git("status", "--porcelain", "--untracked-files=no")
        if result.stdout:
            raise UpdateError("self_update_dirty")

    @staticmethod
    def _validate_source(source, files):
        for filename in files:
            path = Path(filename)
            # Không bao giờ lấy cấu hình/dữ liệu cá nhân từ bản cập nhật.
            if path.name in (".env", "name.txt") or ".session" in path.suffixes or ".session-" in path.name:
                raise UpdateError("self_update_unsafe_file", filename=filename)
            if path.suffix == ".py":
                with tokenize.open(source / path) as handle:
                    compile(handle.read(), filename, "exec")

    async def update(self, progress):
        """Chỉ thay mã nguồn sau khi tải, kiểm tra và cài dependencies thành công."""
        if self.is_busy:
            raise UpdateError("self_update_busy")

        async with self._lock:
            if not shutil.which("git"):
                raise UpdateError("self_update_missing_git")
            repo = await self._git("rev-parse", "--show-toplevel", allowed_codes=(0, 128))
            if repo.returncode or Path(repo.stdout).resolve() != self.project_dir:
                raise UpdateError("self_update_not_git")

            current = (await self._git("rev-parse", "HEAD")).stdout
            remote = await self._git("ls-remote", "--exit-code", REPO_URL, f"refs/heads/{UPDATE_BRANCH}")
            latest = remote.stdout.split()[0]
            if current == latest:
                return UpdateResult(current, latest)

            await self._check_clean()
            await progress("self_update_downloading")
            with tempfile.TemporaryDirectory(prefix="tg-name-update-") as temp_dir:
                source = Path(temp_dir) / "source"
                await self._git(
                    "clone", "--quiet", "--single-branch", "--branch", UPDATE_BRANCH,
                    "--", REPO_URL, str(source), timeout=180,
                )
                latest = (await self._git("rev-parse", "HEAD", cwd=source)).stdout
                if latest == current:
                    return UpdateResult(current, latest)
                # Fetch từ bản clone đã kiểm tra, không thay remote origin của người dùng.
                await self._git("fetch", "--quiet", "--no-tags", "--", str(source), f"refs/heads/{UPDATE_BRANCH}")
                ancestor = await self._git("merge-base", "--is-ancestor", current, latest, allowed_codes=(0, 1))
                if ancestor.returncode:
                    raise UpdateError("self_update_diverged")

                await progress("self_update_validating")
                tracked = (await self._git("ls-files", "-z", cwd=source)).stdout
                files = [filename for filename in tracked.split("\0") if filename]
                try:
                    self._validate_source(source, files)
                except (SyntaxError, UnicodeError, OSError) as exc:
                    raise UpdateError("self_update_invalid_source", details=str(exc)) from exc

                requirements = source / "requirements.txt"
                installed = self.project_dir / "requirements.txt"
                if requirements.exists() and (not installed.exists() or requirements.read_bytes() != installed.read_bytes()):
                    await progress("self_update_dependencies")
                    await self._run(
                        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-input", "-r", str(requirements), cwd=source, timeout=600,
                    )

                # Kiểm tra lại vì việc clone/cài thư viện có thể mất vài phút.
                if (await self._git("rev-parse", "HEAD")).stdout != current:
                    raise UpdateError("self_update_changed")
                await self._check_clean()
                await self._git("merge", "--ff-only", "--no-edit", "--no-overwrite-ignore", latest)

            self._restart_pending = True
            return UpdateResult(current, latest, updated=True)

    def request_restart(self):
        self.restart_event.set()


bot_updater = BotUpdater()


async def _run_until_restart(main):
    main_task = asyncio.create_task(main())
    restart_task = asyncio.create_task(bot_updater.restart_event.wait())
    try:
        done, _ = await asyncio.wait((main_task, restart_task), return_when=asyncio.FIRST_COMPLETED)
        if main_task in done:
            await main_task
        return bot_updater.restart_event.is_set()
    finally:
        for task in (main_task, restart_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(main_task, restart_task, return_exceptions=True)


def run_with_restart(main):
    """Đóng các client trước khi exec; giữ nguyên PID cho cả chạy trực tiếp lẫn PM2."""
    original_argv = getattr(sys, "orig_argv", [sys.executable, *sys.argv])
    argv = [sys.executable, *original_argv[1:]]
    if asyncio.run(_run_until_restart(main)):
        print("[🔄] Đang khởi động lại bot với mã nguồn mới...", flush=True)
        os.execv(sys.executable, argv)
