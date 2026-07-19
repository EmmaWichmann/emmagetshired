"""
card_generator.py
------------------
Builds shareable PNG images (the "wrapped" recap and the streak card)
using Pillow. Returns raw image bytes that Flask sends straight to the
browser as a downloadable/shareable image — like a Spotify Wrapped card
or a Duolingo streak flex.
"""

from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

WIDTH, HEIGHT = 1080, 1080  # square, Instagram-story-crop friendly

COLORS = {
    "bg": (245, 238, 216),
    "bark": (92, 61, 46),
    "moss": (107, 124, 90),
    "clay": (139, 90, 58),
    "gold": (201, 168, 76),
    "cream": (250, 246, 236),
}


def _font(size, bold=False):
    """Falls back to Pillow's default font if no system font is found,
    so this never crashes even in a bare environment."""
    try:
        path = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        )
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _base_card():
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    # soft border
    draw.rectangle([30, 30, WIDTH - 30, HEIGHT - 30], outline=COLORS["clay"], width=3)
    return img, draw


def make_wrapped_card(total_logs, total_pts, top_category, month_name):
    img, draw = _base_card()

    eyebrow_font = _font(28)
    title_font = _font(64, bold=True)
    stat_font = _font(90, bold=True)
    label_font = _font(30)

    draw.text((WIDTH / 2, 140), f"{month_name.upper()} WRAPPED", font=eyebrow_font,
               fill=COLORS["clay"], anchor="mm")
    draw.text((WIDTH / 2, 220), "onemoretime", font=title_font, fill=COLORS["bark"], anchor="mm")

    draw.text((WIDTH / 2, 420), str(total_logs), font=stat_font, fill=COLORS["moss"], anchor="mm")
    draw.text((WIDTH / 2, 490), "things logged this month", font=label_font,
               fill=COLORS["clay"], anchor="mm")

    draw.text((WIDTH / 2, 640), str(total_pts), font=stat_font, fill=COLORS["gold"], anchor="mm")
    draw.text((WIDTH / 2, 710), "total points earned", font=label_font,
               fill=COLORS["clay"], anchor="mm")

    if top_category:
        top_text = f"{top_category['emoji']} {top_category['name']}"
        draw.text((WIDTH / 2, 860), "your top category", font=label_font,
                   fill=COLORS["clay"], anchor="mm")
        draw.text((WIDTH / 2, 910), top_text, font=_font(46, bold=True),
                   fill=COLORS["bark"], anchor="mm")

    draw.text((WIDTH / 2, HEIGHT - 70), "one more time, one more time",
               font=_font(24), fill=COLORS["clay"], anchor="mm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def make_streak_card(streak):
    img, draw = _base_card()

    draw.text((WIDTH / 2, 200), "onemoretime", font=_font(52, bold=True),
               fill=COLORS["bark"], anchor="mm")

    flame_font = _font(160)
    draw.text((WIDTH / 2, 480), "🔥", font=flame_font, anchor="mm")

    num_font = _font(140, bold=True)
    draw.text((WIDTH / 2, 680), str(streak), font=num_font, fill=COLORS["gold"], anchor="mm")

    label = f"day{'s' if streak != 1 else ''} in a row"
    draw.text((WIDTH / 2, 780), label, font=_font(40), fill=COLORS["clay"], anchor="mm")

    draw.text((WIDTH / 2, HEIGHT - 70), "showing up for myself",
               font=_font(24), fill=COLORS["clay"], anchor="mm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
