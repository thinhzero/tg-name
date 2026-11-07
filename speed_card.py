"""Local numeric-only speed card; never loads remote images or embeds raw results."""

from io import BytesIO
import math


def speed_card(output):
    import json
    from PIL import Image, ImageDraw, ImageFont

    data = json.loads(output)
    values = []
    for key, divisor in (("download", 1e6), ("upload", 1e6), ("ping", 1)):
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10 ** 15:
            raise ValueError("Invalid speed result")
        values.append(f"{value / divisor:,.2f}")
    image = Image.new("RGB", (1080, 480), "#1a1a19")
    draw = ImageDraw.Draw(image)

    def font(size):
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default(size=size)

    draw.text((48, 36), "NETWORK SPEED", font=font(32), fill="#f0efec")
    draw.text((48, 86), "tg-name / private result", font=font(20), fill="#c3c2b7")
    for index, (label, value, unit) in enumerate(zip(("Download", "Upload", "Ping"), values, ("Mbps", "Mbps", "ms"))):
        x = 48 + index * 344
        draw.text((x, 174), label, font=font(24), fill="#c3c2b7")
        size = 48
        while draw.textbbox((0, 0), value, font=font(size))[2] > 300 and size > 16:
            size -= 2
        draw.text((x, 220), value, font=font(size), fill="#f0efec")
        draw.text((x, 288), unit, font=font(22), fill="#c3c2b7")
    draw.line((48, 362, 1032, 362), fill="#52514e", width=1)
    draw.text((48, 398), "IP HIDDEN  /  Generated locally. No share link.", font=font(22), fill="#c3c2b7")
    result = BytesIO()
    image.save(result, format="PNG")
    result.seek(0)
    result.name = "speedtest.png"
    return result
