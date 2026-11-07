import importlib.util
import json
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Requires Pillow")
class SpeedCardTests(unittest.TestCase):
    def test_card_is_png_and_only_renders_allowlisted_numbers(self):
        from PIL import Image, ImageDraw
        from speed_card import speed_card
        data = {"download": 120000000, "upload": 35000000, "ping": 12.5,
                "client": {"ip": "203.0.113.44", "isp": "SECRET"},
                "server": {"name": "SECRET"}, "share": "https://SECRET"}
        labels = []
        original = ImageDraw.ImageDraw.text
        def record(draw, xy, text, *args, **kwargs):
            labels.append(text)
            return original(draw, xy, text, *args, **kwargs)
        with patch.object(ImageDraw.ImageDraw, "text", record):
            result = speed_card(json.dumps(data))
        self.assertEqual(result.name, "speedtest.png")
        self.assertEqual(Image.open(result).size, (1080, 480))
        self.assertTrue({"120.00", "35.00", "12.50"} <= set(labels))
        self.assertNotIn("SECRET", " ".join(labels))
        self.assertNotIn("203.0.113.44", " ".join(labels))

    def test_invalid_numbers_cannot_enter_image(self):
        from speed_card import speed_card
        for value in (True, -1, float("nan"), float("inf"), "203.0.113.44"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                speed_card(json.dumps({"download": value, "upload": 1, "ping": 1}))
