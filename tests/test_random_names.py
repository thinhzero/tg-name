import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from random_names import RandomNames


class RandomNamesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-name-random-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "name.txt"
        self.store = RandomNames(self.path)

    def test_missing_file_is_empty_without_seed(self):
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.choose(), "")
        self.assertFalse(self.path.exists())

    def test_seed_is_only_used_once_even_if_all_entries_are_removed(self):
        example = Path(self.temp.name) / "name.example.txt"
        example.write_text("eat29\n", encoding="utf-8")
        store = RandomNames(self.path, example)
        entry, = store.entries()
        self.assertEqual(entry.text, "eat29")
        store.remove(entry.uid)
        self.assertEqual(store.entries(), [])
        self.assertEqual(self.path.read_text(), "")

    def test_existing_file_is_not_replaced_by_seed(self):
        self.path.write_text("local\n")
        store = RandomNames(self.path, Path(self.temp.name) / "missing.txt")
        self.assertEqual(store.choose(), "local")

    def test_missing_seed_does_not_create_an_empty_file(self):
        store = RandomNames(self.path, Path(self.temp.name) / "missing.txt")
        with self.assertRaises(FileNotFoundError):
            store.entries()
        self.assertFalse(self.path.exists())

    def test_reads_bom_blank_lines_and_deduplicates(self):
        self.path.write_bytes("\ufeff eat29 \r\n\r\nsleep\neat29\n# literal\n".encode())
        self.assertEqual([entry.text for entry in self.store.entries()], ["eat29", "sleep", "# literal"])

    def test_adds_multiple_plain_text_lines_without_duplicates(self):
        added = self.store.add(" eat29 \nsleep\n\neat29\n")
        self.assertEqual([entry.text for entry in added], ["eat29", "sleep"])
        self.assertEqual(self.path.read_text(), "eat29\nsleep\n")
        self.assertEqual(self.store.add("eat29\n sleep "), [])

    def test_uids_survive_reordering_deletion_and_reload(self):
        first, second, third = self.store.add("eat29\nsleep\nwork")
        self.path.write_text("work\neat29\nsleep\n")
        self.assertEqual([entry.uid for entry in self.store.entries()], [third.uid, first.uid, second.uid])
        self.assertEqual(self.store.remove(first.uid), first)
        self.assertEqual(RandomNames(self.path).entries(), [third, second])

    def test_unknown_uid_does_not_change_file(self):
        self.store.add("eat29")
        original = self.path.read_bytes()
        self.assertIsNone(self.store.remove("unknown"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_remove_accepts_uppercase_uid(self):
        entry, = self.store.add("eat29")
        self.assertEqual(self.store.remove(entry.uid.upper()), entry)
        self.assertEqual(self.store.entries(), [])

    def test_choose_uses_the_current_lines(self):
        self.store.add("eat29\nsleep")
        with patch("random_names.random.choice", side_effect=lambda entries: entries[-1]):
            self.assertEqual(self.store.choose(), "sleep")
            self.path.write_text("manual edit\n")
            self.assertEqual(self.store.choose(), "manual edit")

    def test_failed_atomic_write_preserves_data_and_cleans_temp_file(self):
        self.store.add("eat29")
        with patch("random_names.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.store.add("sleep")
        self.assertEqual(self.path.read_text(), "eat29\n")
        self.assertEqual(list(self.path.parent.glob(".name-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
