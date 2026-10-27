"""So sánh commit GitHub, hỏi xác nhận rồi snapshot/update/restart đúng phiên bản."""

import asyncio
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tokenize
from dataclasses import dataclass
from html import escape
from pathlib import Path

from i18n import get_text
from code_snapshot import SNAPSHOT_DIR, create_snapshot
from update_completion import STATUS_DIR, UpdateCompletion


REPO_URL = "https://github.com/thinhzero/tg-name.git"
UPDATE_BRANCH = "main"
PROJECT_DIR = Path(__file__).resolve().parent
GIT_REPOSITORY_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE",
    "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS", "GIT_IMPLICIT_WORK_TREE", "GIT_CURL_VERBOSE",
}


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
    snapshot: str = ""


@dataclass(frozen=True)
class UpdatePlan:
    current: str
    latest: str
    ahead: int = 0
    local_ahead: int = 0


class UpdateRequests:
    def __init__(self):
        self.pending = {}

    def create(self, owner_id, plan, userbot=False):
        token = secrets.token_urlsafe(12)
        self.pending[(owner_id, userbot)] = (token, time.monotonic() + 300, plan)
        return token

    def consume(self, owner_id, token, userbot=False):
        if not isinstance(token, str) or not token.isascii() or len(token) > 128:
            return None
        request = self.pending.get((owner_id, userbot))
        if not request or not secrets.compare_digest(request[0], token):
            return None
        self.pending.pop((owner_id, userbot))
        return request[2] if request[1] >= time.monotonic() else None

    def cancel(self, owner_id, userbot=False):
        self.pending.pop((owner_id, userbot), None)


update_requests = UpdateRequests()


def update_buttons(token, lang="vi"):
    return [[
        {"text": "✅ Yes, update" if lang == "en" else "✅ Có, cập nhật", "callback_data": f"update_confirm:{token}"},
        {"text": "❌ No" if lang == "en" else "❌ Không", "callback_data": f"update_cancel:{token}"},
    ]]


class BotUpdater:
    def __init__(self, project_dir=PROJECT_DIR):
        self.project_dir = Path(project_dir).resolve()
        self._lock = asyncio.Lock()
        self._restart_pending = False
        self.restart_event = asyncio.Event()
        self.completion = UpdateCompletion(self.project_dir)

    @property
    def is_busy(self):
        return self._lock.locked() or self._restart_pending

    async def _run(self, *command, cwd=None, timeout=120, allowed_codes=(0,)):
        env = os.environ.copy()
        if command[0] == "git":
            env["LC_ALL"] = "C"
            # Không để biến Git của shell/process cha chuyển lệnh sang repo khác.
            # Giữ PATH/PREFIX/LD_PRELOAD để Git và termux-exec vẫn hoạt động.
            for key in list(env):
                if key in GIT_REPOSITORY_ENV or key.startswith(("GIT_TRACE", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
                    env.pop(key)
        env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd or self.project_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
        try:
            output, errors = await asyncio.wait_for(process.communicate(), timeout)
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
        stderr = errors.decode("utf-8", errors="replace").rstrip("\r\n")
        if process.returncode not in allowed_codes:
            details = "\n".join(part for part in (text, stderr) if part)
            raise UpdateError("self_update_command_failed", details=details[-1800:])
        return subprocess.CompletedProcess(command, process.returncode, stdout=text, stderr=stderr)

    async def _git(self, *args, **kwargs):
        return await self._run("git", *args, **kwargs)

    async def _check_checkout(self):
        repo = await self._git("rev-parse", "--show-toplevel", allowed_codes=(0, 128))
        if repo.returncode:
            errors = repo.stderr.lower()
            if "dubious ownership" in errors or "unsafe repository" in errors:
                raise UpdateError("self_update_git_ownership", directory=str(self.project_dir))
            if "not a git repository" in errors:
                raise UpdateError("self_update_not_git", directory=str(self.project_dir))
            raise UpdateError("self_update_command_failed", details=repo.stderr[-1800:])
        root = Path(repo.stdout).resolve()
        try:
            same_directory = root.samefile(self.project_dir)
        except OSError:
            same_directory = root == self.project_dir
        if not same_directory:
            raise UpdateError("self_update_wrong_directory", directory=str(self.project_dir), root=str(root))

    async def _check_clean(self):
        result = await self._git("status", "--porcelain", "--untracked-files=no")
        if result.stdout:
            raise UpdateError("self_update_dirty")

    @staticmethod
    def _validate_source(source, files):
        for filename in files:
            path = Path(filename)
            # Không bao giờ lấy cấu hình/dữ liệu cá nhân từ bản cập nhật.
            if (path.name in (".env", "name.txt") or ".session" in path.suffixes or ".session-" in path.name
                    or SNAPSHOT_DIR in path.parts or STATUS_DIR in path.parts or (path.name.startswith(".env.") and path.name != ".env.example")):
                raise UpdateError("self_update_unsafe_file", filename=filename)
            if path.suffix == ".py":
                with tokenize.open(source / path) as handle:
                    compile(handle.read(), filename, "exec")

    async def check(self):
        """Chỉ fetch lịch sử để đếm commit; không clone/checkout/cài thư viện."""
        if self.is_busy:
            raise UpdateError("self_update_busy")
        async with self._lock:
            if not shutil.which("git"):
                raise UpdateError("self_update_missing_git")
            await self._check_checkout()

            current = (await self._git("rev-parse", "HEAD")).stdout
            remote = await self._git("ls-remote", "--exit-code", REPO_URL, f"refs/heads/{UPDATE_BRANCH}")
            latest = remote.stdout.split()[0]
            if current == latest:
                return UpdatePlan(current, latest)
            shallow = (await self._git("rev-parse", "--is-shallow-repository")).stdout == "true"
            args = ["fetch", "--quiet", "--no-tags", "--no-write-fetch-head"]
            if shallow:
                args.append("--unshallow")
            await self._git(*args, "--", REPO_URL, latest, timeout=180)
            counts = (await self._git("rev-list", "--left-right", "--count", f"{current}...{latest}")).stdout.split()
            if (await self._git("rev-parse", "HEAD")).stdout != current:
                raise UpdateError("self_update_changed")
            return UpdatePlan(current, latest, ahead=int(counts[1]), local_ahead=int(counts[0]))

    async def update(self, progress, *, plan=None, secret_values=(), notify=None):
        """Chỉ áp dụng đúng commit đã được người dùng xác nhận."""
        if self.is_busy:
            raise UpdateError("self_update_busy")
        if not isinstance(plan, UpdatePlan):
            raise UpdateError("self_update_confirmation_required")
        async with self._lock:
            if not shutil.which("git"):
                raise UpdateError("self_update_missing_git")
            await self._check_checkout()
            current = (await self._git("rev-parse", "HEAD")).stdout
            if current != plan.current:
                raise UpdateError("self_update_changed")
            latest = plan.latest
            if latest == current:
                return UpdateResult(current, latest)
            ancestor = await self._git("merge-base", "--is-ancestor", current, latest, allowed_codes=(0, 1))
            if plan.local_ahead or ancestor.returncode:
                raise UpdateError("self_update_diverged")
            await self._check_clean()
            await progress("self_update_downloading")
            with tempfile.TemporaryDirectory(prefix="tg-name-update-") as temp_dir:
                source = Path(temp_dir) / "source"
                await self._git(
                    "clone", "--quiet", "--single-branch", "--branch", UPDATE_BRANCH,
                    "--", REPO_URL, str(source), timeout=180,
                )
                # Nhánh main có thể có commit mới sau lúc bấm Có; chỉ lấy đúng
                # commit đã hiện ở màn hình xác nhận, không tự mở rộng phạm vi.
                await self._git("checkout", "--quiet", "--detach", latest, cwd=source)
                # Fetch từ bản clone đã kiểm tra, không thay remote origin của người dùng.
                await self._git("fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--", str(source), latest)

                await progress("self_update_validating")
                tracked = (await self._git("ls-files", "-z", cwd=source)).stdout
                files = [filename for filename in tracked.split("\0") if filename]
                try:
                    self._validate_source(source, files)
                except (SyntaxError, UnicodeError, OSError) as exc:
                    raise UpdateError("self_update_invalid_source", details=str(exc)) from exc

                await self._check_clean()
                if (await self._git("rev-parse", "HEAD")).stdout != current:
                    raise UpdateError("self_update_changed")
                await progress("self_update_snapshot")
                local_files = (await self._git("ls-files", "--cached", "--others", "--exclude-standard", "-z")).stdout
                try:
                    snapshot = await asyncio.to_thread(
                        create_snapshot, self.project_dir, [path for path in local_files.split("\0") if path],
                        current, latest, secret_values,
                    )
                except (OSError, ValueError) as exc:
                    raise UpdateError("self_update_snapshot_failed", details=type(exc).__name__) from exc

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
            result = UpdateResult(current, latest, updated=True, snapshot=snapshot)
            if notify is not None:
                try:
                    self.completion.record(result, notify)
                except (OSError, ValueError) as exc:
                    print(f"[ℹ️] Đã áp dụng code nhưng chưa lưu được thông báo restart ({type(exc).__name__}).")
            return result

    def request_restart(self):
        self.restart_event.set()


bot_updater = BotUpdater()


async def show_update_error(edit, exc, lang):
    if isinstance(exc, UpdateError):
        details = {key: escape(str(value)) for key, value in exc.details.items()}
        await edit(get_text(exc.key, lang, **details), parse_mode="html")
    else:
        await edit(get_text("self_update_command_failed", lang, details=escape(str(exc)[:1800])), parse_mode="html")


async def run_update_check(edit, lang="vi", updater=bot_updater, *, owner_id=0, userbot=False):
    """Chỉ kiểm tra và hỏi; không bao giờ tự áp dụng khi gọi /updatecheck."""
    update_requests.cancel(owner_id, userbot)
    try:
        plan = await updater.check()
    except Exception as exc:
        await show_update_error(edit, exc, lang)
        return
    if not plan.ahead and not plan.local_ahead:
        await edit(get_text("self_update_latest", lang, commit=plan.current[:7]), parse_mode="html")
        return
    if plan.local_ahead:
        await edit(get_text("self_update_compare_diverged", lang, ahead=plan.ahead, local=plan.local_ahead), parse_mode="html")
        return
    token = update_requests.create(owner_id, plan, userbot)
    text = get_text("self_update_offer", lang, count=plan.ahead, old=plan.current[:7], new=plan.latest[:7])
    if userbot:
        text += get_text("self_update_text_confirm", lang, token=token)
        await edit(text, parse_mode="html")
    else:
        await edit(text, parse_mode="html", buttons=update_buttons(token, lang))


async def run_update_action(edit, owner_id, token, lang="vi", updater=bot_updater, *, confirm=True, userbot=False, secret_values=()):
    plan = update_requests.consume(owner_id, token, userbot)
    if plan is None:
        await edit(get_text("self_update_expired", lang), parse_mode="html")
        return
    if not confirm:
        await edit(get_text("self_update_cancelled", lang), parse_mode="html")
        return

    async def progress(key):
        await edit(get_text(key, lang), parse_mode="html")

    try:
        result = await updater.update(progress, plan=plan, secret_values=secret_values, notify={"owner_id": owner_id, "lang": lang, "userbot": userbot})
    except Exception as exc:
        await show_update_error(edit, exc, lang)
        return
    if not result.updated:
        await edit(get_text("self_update_latest", lang, commit=result.current[:7]), parse_mode="html")
        return
    try:
        await edit(get_text("self_update_restarting", lang, old=result.current[:7], new=result.latest[:7], snapshot=escape(result.snapshot)), parse_mode="html")
    finally:
        updater.request_restart()


async def notify_update_completed(send, owner_id, lang="vi", userbot=False, legacy=True, updater=bot_updater):
    # HEAD đã đổi nhưng runtime cũ vẫn có thể nhận /start trong lúc chuẩn bị exec.
    if getattr(updater, "_restart_pending", False):
        return False
    completion = getattr(updater, "completion", None)
    if completion is None:
        return False

    async def current():
        return (await updater._git("rev-parse", "HEAD")).stdout
    return await completion.deliver(send, current, owner_id, lang, userbot, legacy)


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
