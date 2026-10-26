import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code_snapshot import create_snapshot, sanitize_source


class CodeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-snapshot-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, text="local data"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def snapshot(self, files, secrets=()):
        return self.root / create_snapshot(self.root, files, "a" * 40, "b" * 40, secrets)

    def test_snapshot_keeps_source_and_commit_manifest(self):
        self.write("name.py", "VERSION = 1\n")
        self.write("tests/local_test.py", "assert 1 == 1\n")
        snapshot = self.snapshot(["name.py", "tests/local_test.py"])
        self.assertEqual((snapshot / "code/name.py").read_text(), "VERSION = 1\n")
        self.assertTrue((snapshot / "code/tests/local_test.py").is_file())
        manifest = json.loads((snapshot / "snapshot.json").read_text())
        self.assertEqual(manifest["from_commit"], "a" * 40)
        self.assertEqual(manifest["to_commit"], "b" * 40)
        self.assertEqual(manifest["files"], ["name.py", "tests/local_test.py"])

    def test_credentials_sessions_runtime_archives_and_prior_backups_are_not_copied(self):
        private = [".env", ".env.backup", "bot.session", "custom.session-wal", ".git/config", ".venv/private.py", "__pycache__/cache.pyc", "snapshots/old/code/old.py", "private.pem", "dump.db", "bot.zip", "name.txt", "secrets.json", "api.json", "passwords.txt"]
        for path in private:
            self.write(path, "private-value")
        self.write("name.py", "VERSION = 1\n")
        snapshot = self.snapshot([*private, "name.py"])
        self.assertEqual([path.relative_to(snapshot / "code").as_posix() for path in (snapshot / "code").rglob("*") if path.is_file()], ["name.py"])
        self.assertNotIn("private-value", (snapshot / "snapshot.json").read_text())

    def test_inline_python_api_and_session_literals_are_redacted(self):
        original = 'API_ID = 12345678\nAPI_HASH = "private-api-hash"\nconfig = {"BOT_TOKEN": "private-token", "SESSION_STRING": "private-session"}\nprint("giữ tên tiếng Việt")\n'
        self.write("config.py", original)
        snapshot = self.snapshot(["config.py"])
        text = (snapshot / "code/config.py").read_text()
        for value in ("12345678", "private-api-hash", "private-token", "private-session"):
            self.assertNotIn(value, text)
        self.assertIn("giữ tên tiếng Việt", text)
        ast.parse(text)
        self.assertEqual((self.root / "config.py").read_text(), original)
        self.assertEqual(json.loads((snapshot / "snapshot.json").read_text())["redacted"], ["config.py"])

    def test_known_keys_are_redacted_even_when_not_named_as_credentials(self):
        self.write("module.py", 'VALUE = "private-api-key-value"\n')
        snapshot = self.snapshot(["module.py"], ["private-api-key-value"])
        self.assertNotIn("private-api-key-value", (snapshot / "code/module.py").read_text())

    def test_credential_detection_regex_source_is_not_corrupted(self):
        original = 'import re\ndef clean(text):\n    return re.sub(r"-----BEGIN [^\\n]*PRIVATE KEY-----.*?(?:-----END [^\\n]*PRIVATE KEY-----|$)", "hidden", text, flags=re.S)\n'
        self.write("redactor.py", original)
        snapshot = self.snapshot(["redactor.py"])
        text = (snapshot / "code/redactor.py").read_text()
        self.assertEqual(text, original)
        ast.parse(text)

    def test_escaped_private_key_literals_are_removed_without_breaking_python(self):
        value = "-----BEGIN OPENSSH PRIVATE KEY-----\n" + "a" * 64 + "\n-----END OPENSSH PRIVATE KEY-----"
        original = "VALUE = " + repr(value) + "\n"
        text = sanitize_source(original, ".py", [])
        self.assertNotIn("a" * 64, text)
        ast.parse(text)

    def test_json_and_shell_config_literals_are_redacted(self):
        result = sanitize_source('{"nested":{"api_hash":"private-hash","display":"Name"}}', ".json", [])
        self.assertNotIn("private-hash", result)
        self.assertEqual(json.loads(result)["nested"]["display"], "Name")
        result = sanitize_source('export BOT_TOKEN="private-token"\nconst API_KEY = "private-key"\n', ".sh", [])
        self.assertNotIn("private-token", result)
        self.assertNotIn("private-key", result)

    def test_symlinks_and_paths_outside_project_are_not_followed(self):
        outside = self.root / "external"
        outside.mkdir()
        (outside / "secret.py").write_text("private data")
        (self.root / "link.py").symlink_to(outside / "secret.py")
        (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
        snapshot = self.snapshot(["link.py", "linked-dir/secret.py", "../outside.py", str(outside / "secret.py")])
        self.assertFalse((snapshot / "code").exists())

    def test_snapshot_root_symlink_is_rejected(self):
        outside = self.root / "external"
        outside.mkdir()
        (self.root / "snapshots").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.snapshot([])
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_snapshot_cleans_only_its_temporary_folder(self):
        self.write("broken.py", 'API_HASH = "unfinished\n')
        self.write("snapshots/keep.txt", "existing backup")
        with self.assertRaises(ValueError):
            self.snapshot(["broken.py"])
        self.assertEqual((self.root / "snapshots/keep.txt").read_text(), "existing backup")
        self.assertEqual(list((self.root / "snapshots").glob(".pending-*")), [])

    def test_new_snapshots_do_not_overwrite_previous_ones(self):
        self.write("name.py", "VERSION = 1\n")
        first = self.snapshot(["name.py"])
        second = self.snapshot(["name.py"])
        self.assertNotEqual(first, second)
        self.assertTrue((first / "code/name.py").exists())
        if os.name == "posix":
            self.assertEqual((first / "code/name.py").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
