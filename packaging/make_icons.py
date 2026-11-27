"""Draw the extension's icons: a download arrow landing in a tray, on a
rounded square. Run it after changing the drawing; the PNGs and the .ico
are committed.

    pip install pillow
    python packaging/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZES = (16, 32, 48, 128)
BACKGROUND = (22, 96, 136, 255)     # deep blue-teal
FOREGROUND = (255, 255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "wherefrom" / "extension" / "icons"
# The programs' and installer's icon (Windows)
ICO = Path(__file__).resolve().parent / "wherefrom.ico"


def draw(scale=512):
    """The icon at a large size; it's scaled down for each PNG, which smooths the edges."""
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    s = scale / 128                  # drawn in a 128-unit grid
    pen.rounded_rectangle((4 * s, 4 * s, 124 * s, 124 * s), radius=26 * s, fill=BACKGROUND)
    # Arrow: shaft and head
    pen.rectangle((56 * s, 24 * s, 72 * s, 66 * s), fill=FOREGROUND)
    pen.polygon([(36 * s, 60 * s), (92 * s, 60 * s), (64 * s, 90 * s)], fill=FOREGROUND)
    # Tray: a U shape under the arrow
    pen.rectangle((28 * s, 96 * s, 100 * s, 106 * s), fill=FOREGROUND)
    pen.rectangle((28 * s, 80 * s, 38 * s, 106 * s), fill=FOREGROUND)
    pen.rectangle((90 * s, 80 * s, 100 * s, 106 * s), fill=FOREGROUND)
    return image


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw()
    for size in SIZES:
        big.resize((size, size), Image.LANCZOS).save(OUT / f"icon-{size}.png", optimize=True)
        print(OUT / f"icon-{size}.png")
    big.save(ICO, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print(ICO)


if __name__ == "__main__":
    main()
