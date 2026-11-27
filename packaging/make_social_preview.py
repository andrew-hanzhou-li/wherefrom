"""Draw docs/social-preview.png, the card shown when someone shares the
repository's link (upload it in GitHub: Settings > General > Social preview).

    pip install pillow
    python packaging/make_social_preview.py

Uses Windows' Segoe UI when it's there, else Pillow's own font.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from make_icons import BACKGROUND, draw

WIDTH, HEIGHT = 1280, 640           # GitHub's recommended size
INK = (255, 255, 255)
SOFT = (200, 225, 238)
OUT = Path(__file__).resolve().parent.parent / "docs" / "social-preview.png"


def font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default(size)


def main():
    card = Image.new("RGB", (WIDTH, HEIGHT), tuple(c // 2 for c in BACKGROUND[:3]))
    icon = draw().resize((220, 220), Image.LANCZOS)
    card.paste(icon, (96, 150), icon)
    pen = ImageDraw.Draw(card)
    pen.text((360, 150), "wherefrom", font=font("segoeuib.ttf", 112), fill=INK)
    pen.text((364, 300), "Right-click any file to see", font=font("segoeui.ttf", 48), fill=INK)
    pen.text((364, 360), "where you downloaded it from.", font=font("segoeui.ttf", 48), fill=INK)
    pen.text((364, 450), "Even after it's renamed, moved or copied.", font=font("segoeui.ttf", 32), fill=SOFT)
    pen.text((364, 495), "Free and open source  ·  Nothing leaves your computer", font=font("segoeui.ttf", 32), fill=SOFT)
    OUT.parent.mkdir(exist_ok=True)
    card.save(OUT, optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
