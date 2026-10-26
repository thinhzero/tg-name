"""Snapshot source hiện tại, không sao chép Git/env/session hay dữ liệu runtime."""

import ast
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from shell_commands import SENSITIVE_NAME, config_secrets


SNAPSHOT_DIR = "snapshots"
EXCLUDED_DIRS = {".git", SNAPSHOT_DIR, ".venv", "venv", "env", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
SOURCE_SUFFIXES = {".py", ".pyi", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java", ".kt", ".rb", ".php", ".sql", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".md", ".txt", ".example", ".service"}
CREDENTIAL_PATTERN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\b\d{6,12}:[A-Za-z0-9_-]{30,}\b|-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----)")


def redact_snapshot_text(text, secret_values):
    for value in sorted({str(value) for value in secret_values if value and len(str(value)) >= 8}, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|\b\d{6,12}:[A-Za-z0-9_-]{30,}\b)", "[REDACTED]", text)
    # Chỉ khớp header PEM thật + newline/base64, không khớp regex xử lý key
    # nằm trong chính source code (tránh làm hỏng snapshot của shell_commands.py).
    return re.sub(
        r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=\r\n \t]+(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----)?",
        "[REDACTED PRIVATE KEY]", text,
    )


def sensitive_name(name):
    return name.upper() == "API_ID" or bool(SENSITIVE_NAME.search(name))


def source_path(path):
    if path.is_absolute() or ".." in path.parts or any(part in EXCLUDED_DIRS for part in path.parts):
        return False
    name = path.name.lower()
    if name.startswith(".env") and name != ".env.example":
        return False
    if ".session" in name or name == "name.txt":
        return False
    if path.suffix.lower() not in SOURCE_SUFFIXES and name not in {".gitignore", "dockerfile", "makefile", "license"}:
        return False
    if path.suffix.lower() in {".json", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".txt"}:
        if re.search(r"(?:^|[_.-])(?:credentials?|secrets?|tokens?|sessions?|passwords?|api(?:[_-]?keys?)?)(?:[_.-]|$)", name):
            return False
    return True


def sanitize_source(text, suffix, secret_values):
    if suffix == ".json":
        data = json.loads(text)
        changed = False

        def clean(value):
            nonlocal changed
            if isinstance(value, dict):
                for key, item in value.items():
                    if sensitive_name(key) and item:
                        value[key] = "[REDACTED]"
                        changed = True
                    else:
                        clean(item)
            elif isinstance(value, list):
                for item in value:
                    clean(item)
        clean(data)
        if changed:
            text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            raise ValueError("Cannot safely snapshot invalid Python source") from exc
        if tree is not None:
            data = text.encode("utf-8")
            lines = data.splitlines(keepends=True)
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(line))
            replacements = {}

            def mask(value):
                if isinstance(value, ast.Constant) and value.value not in (None, "", b"", 0, False):
                    start = offsets[value.lineno - 1] + value.col_offset
                    end = offsets[value.end_lineno - 1] + value.end_col_offset
                    replacements[(start, end)] = b'"[REDACTED]"'

            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if CREDENTIAL_PATTERN.search(node.value) or any(str(value) in node.value for value in secret_values if value and len(str(value)) >= 8):
                        mask(node)
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(target, ast.Name) and sensitive_name(target.id) for target in targets):
                        mask(node.value)
                elif isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if isinstance(key, ast.Constant) and isinstance(key.value, str) and sensitive_name(key.value):
                            mask(value)
                elif isinstance(node, ast.keyword) and node.arg and sensitive_name(node.arg):
                    mask(node.value)
            for (start, end), replacement in sorted(replacements.items(), reverse=True):
                data = data[:start] + replacement + data[end:]
            text = data.decode("utf-8")
    text = redact_snapshot_text(text, secret_values)
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    if suffix not in {".py", ".json"}:
        # Cấu hình dạng KEY=value / key: value; không lưu literal API/token.
        text = re.sub(
            r"(?im)^(\s*(?:export\s+)?(?:(?:const|let|var)\s+)?[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*[:=]\s*)([^\n]+)$",
            lambda match: match[1] + '"[REDACTED]"' if sensitive_name(match[2]) else match[0], text,
        )
    if suffix == ".py":
        try:
            ast.parse(text)
        except SyntaxError as exc:
            raise ValueError("Redacted snapshot would contain invalid Python") from exc
    return text


def create_snapshot(project_dir, files, current, latest, secret_values=()):
    root = Path(project_dir).resolve()
    snapshots = root / SNAPSHOT_DIR
    if snapshots.is_symlink():
        raise OSError("Snapshot directory must not be a symlink")
    snapshots.mkdir(mode=0o700, exist_ok=True)
    secrets = [*secret_values, *config_secrets(os.environ)]
    created = datetime.now(timezone.utc)
    name = f"{created:%Y%m%dT%H%M%S%fZ}-{current[:7]}-{os.urandom(3).hex()}"
    target = snapshots / name
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=snapshots))
    copied, omitted, redacted = [], [], []
    try:
        for filename in sorted(set(files)):
            path = Path(filename)
            if not source_path(path):
                omitted.append(filename)
                continue
            source = root / path
            if any((root / parent).is_symlink() for parent in [path, *path.parents]):
                omitted.append(filename)
                continue
            if not source.is_file():
                omitted.append(filename)
                continue
            try:
                original = source.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                omitted.append(filename)
                continue
            text = sanitize_source(original, path.suffix.lower(), secrets)
            destination = temporary / "code" / path
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with destination.open("w", encoding="utf-8", newline="") as handle:
                os.chmod(destination, 0o600)
                handle.write(text)
            copied.append(filename)
            if text != original:
                redacted.append(filename)
        manifest = {"version": 1, "created_at": created.isoformat(), "from_commit": current, "to_commit": latest, "files": copied, "omitted": omitted, "redacted": redacted}
        (temporary / "snapshot.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary / "snapshot.json", 0o600)
        temporary.rename(target)
    except BaseException:
        # Chỉ dọn thư mục tạm do chính lần snapshot này tạo.
        shutil.rmtree(temporary)
        raise
    return target.relative_to(root).as_posix()
