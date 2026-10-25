import importlib.util
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 25, 4, 35, tzinfo=timezone.utc).astimezone(tz)


@unittest.skipUnless(HAS_DEPENDENCIES, "Cài requirements.txt để kiểm thử định dạng profile")
class RandomProfileTests(unittest.TestCase):
    def setUp(self):
        import profile_engine
        self.engine = profile_engine
        self.names = Mock()
        self.names.choose.return_value = "eat29"
        for patcher in (
            patch.object(profile_engine, "random_names", self.names),
            patch.object(profile_engine, "datetime", FrozenDatetime),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def render(self, template, tz="Asia/Ho_Chi_Minh", **kwargs):
        return self.engine.render_format(template, "HzzMonet", {}, "Hanoi", tz, **kwargs)

    def test_requested_format(self):
        self.assertEqual(
            self.render(self.engine.DEFAULT_NAME_FORMAT),
            "HzzMonet | 11:35 - 25/10 | GMT +7 | eat29",
        )
        self.names.choose.assert_called_once()

    def test_gmt_supports_fractional_negative_and_zero_offsets(self):
        self.assertEqual(self.render("{gmt}", "Asia/Kathmandu"), "GMT +5:45")
        self.assertEqual(self.render("{gmt}", "Etc/GMT+3"), "GMT -3")
        self.assertEqual(self.render("{gmt}", "America/St_Johns"), "GMT -2:30")
        self.assertEqual(self.render("{gmt}", "UTC"), "GMT +0")

    def test_invalid_timezone_keeps_the_existing_vietnam_fallback(self):
        self.assertEqual(self.render("{gmt}", "unknown"), "GMT +7")

    def test_random_contents_are_literal_not_template_tokens(self):
        value = "HH {base_name} {random} {gmt} <text>"
        self.assertEqual(self.render("{random}", random_text=value), value)
        result = self.engine.render_format("{base_name} | {random}", "HH {random}", {}, "Hanoi", "UTC", random_text="MM")
        self.assertEqual(result, "HH {random} | MM")

    def test_random_is_only_chosen_once_for_repeated_placeholder(self):
        self.assertEqual(self.render("{random} / {random}"), "eat29 / eat29")
        self.names.choose.assert_called_once()

    def test_templates_without_random_do_not_read_the_list(self):
        self.assertEqual(self.render("{base_name} | HH:mm"), "HzzMonet | 11:35")
        self.names.choose.assert_not_called()

    def test_name_and_bio_preview_use_the_same_random_entry(self):
        self.names.choose.side_effect = ["eat29", "sleep"]
        name, bio = self.engine.generate_preview({"NAME_FORMAT": "{random}", "BIO_FORMAT": "{random}"})
        self.assertEqual((name, bio), ("eat29", "eat29"))
        self.names.choose.assert_called_once()

    def test_bio_scenarios_share_one_random_choice(self):
        result = self.engine.generate_bio_preview(template="{random}")
        self.assertEqual((result["current"], result["with_music"], result["no_music"]), ("eat29",) * 3)
        self.names.choose.assert_called_once()

    def test_empty_list_does_not_leave_an_unresolved_placeholder(self):
        self.names.choose.return_value = ""
        self.assertEqual(self.render("{random}"), "")

    def test_existing_name_length_limit_is_kept(self):
        self.names.choose.return_value = "a" * 100
        name, bio = self.engine.generate_preview({"NAME_FORMAT": "{random}", "BIO_FORMAT": "{random}"})
        self.assertEqual(len(name), 64)
        self.assertEqual(len(bio), 70)


if __name__ == "__main__":
    unittest.main()
