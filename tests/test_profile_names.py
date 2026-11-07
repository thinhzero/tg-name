import asyncio
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


HAS_DEPENDENCIES = all(importlib.util.find_spec(name) for name in ("telethon", "dotenv", "aiohttp", "pytz"))


@unittest.skipUnless(HAS_DEPENDENCIES, "Install requirements.txt to test profile names")
class ProfileNameTests(unittest.TestCase):
    def setUp(self):
        import profile_engine
        self.module = profile_engine

    def render(self, template, base="Alice", random_text="rest"):
        return self.module.render_profile_name(template, base, {}, "Hanoi", "UTC", random_text=random_text)

    def test_base_is_literal_and_suffix_is_rendered(self):
        self.assertEqual(self.render("{base_name} | {gmt} | {random}", "HH {random}"),
                         ("HH {random}", "| GMT +0 | rest"))

    def test_boundary_is_template_placeholder_not_matching_rendered_base(self):
        self.assertEqual(self.render("{base_name} | {random}", "Alice", "Alice walks"),
                         ("Alice", "| Alice walks"))

    def test_suffix_only_templates_are_preserved(self):
        self.assertEqual(self.render("{random}"), ("Alice", "rest"))

    def test_empty_suffix_clears_last_name(self):
        for template in ("{base_name}", "{base_name}  ", "{random}"):
            with self.subTest(template=template):
                self.assertEqual(self.render(template, random_text=""), ("Alice", ""))

    def test_each_field_has_its_own_limit(self):
        self.assertEqual(self.render("{base_name} {random}", "A" * 90, "B" * 90),
                         ("A" * 64, "B" * 64))

    def test_preview_preserves_tuple_and_joins_separately_capped_fields(self):
        config = {"BASE_NAME": "A" * 90, "NAME_FORMAT": "{base_name} {random}", "BIO_FORMAT": "{random}"}
        with patch.object(self.module.random_names, "choose", return_value="B" * 90) as choose:
            preview = self.module.generate_preview(config)
        self.assertIsInstance(preview, tuple)
        self.assertEqual(preview, ("A" * 64 + " " + "B" * 64, "B" * 70))
        choose.assert_called_once()

    def test_loop_sends_split_fields_and_explicitly_clears_last_name_on_retry(self):
        async def run_case(template, expected_last, retry):
            engine = self.module.ProfileEngine()
            engine.is_running = True
            requests = []

            async def send(request):
                requests.append(request)
                if retry and len(requests) == 1:
                    raise self.module.AboutTooLongError(request)

            client = AsyncMock(side_effect=send)
            client.is_connected = Mock(return_value=True)
            engine.user_client = client
            fake_state = SimpleNamespace(
                config={"BASE_NAME": "HH {random}", "NAME_FORMAT": template,
                        "BIO_FORMAT": "bio", "CITY": "Hanoi", "TIMEZONE": "UTC"},
                is_paused=False, update_count=0,
                force_update_event=SimpleNamespace(wait=AsyncMock(side_effect=asyncio.CancelledError)),
            )
            with patch.object(self.module, "state", fake_state), \
                 patch.object(self.module, "get_detailed_weather", AsyncMock(return_value={"formatted": "sunny"})), \
                 patch.object(self.module, "chat_log", Mock()):
                await engine._loop()
            self.assertEqual(len(requests), 2 if retry else 1)
            for request in requests:
                self.assertEqual(request.first_name, "HH {random}")
                self.assertEqual(request.last_name, expected_last)
            expected_name = "HH {random}" + (" " + expected_last if expected_last else "")
            self.assertEqual(fake_state.current_name, expected_name)
            if retry:
                self.assertTrue(requests[-1].about.startswith("📍 Hanoi"))

        for template, last in (("{base_name}", ""), ("{base_name} | {gmt}", "| GMT +0")):
            for retry in (False, True):
                with self.subTest(template=template, retry=retry):
                    asyncio.run(run_case(template, last, retry))


if __name__ == "__main__":
    unittest.main()
