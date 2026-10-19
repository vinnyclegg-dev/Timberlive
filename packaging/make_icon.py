"""Draw the app icon (a log end with tree rings and a red 'live' dot) into app/timberlive_app/ui/icon.ico and icon.png.

    runtime/python packaging/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

UI = Path(__file__).resolve().parent.parent / "app" / "timberlive_app" / "ui"
S = 512


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=96, fill=(31, 36, 42, 255))
    c, r = S // 2, 190
    d.ellipse((c - r, c - r, c + r, c + r), fill=(110, 66, 33, 255))           # bark
    r2 = r - 22
    d.ellipse((c - r2, c - r2, c + r2, c + r2), fill=(222, 170, 108, 255))     # wood
    for i, rr in enumerate(range(r2 - 26, 20, -30)):                           # rings
        col = (176, 118, 62, 255) if i % 2 == 0 else (200, 142, 82, 255)
        d.ellipse((c - rr, c - rr + 4, c + rr, c + rr + 4), outline=col, width=9)
    d.ellipse((c - 16, c - 12, c + 16, c + 20), fill=(150, 96, 48, 255))       # pith
    d.ellipse((S - 168, 44, S - 52, 160), fill=(31, 36, 42, 255))              # live dot ring
    d.ellipse((S - 152, 60, S - 68, 144), fill=(235, 64, 64, 255))
    return img


if __name__ == "__main__":
    img = draw()
    img.resize((128, 128), Image.LANCZOS).save(UI / "icon.png")
    img.save(UI / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", UI / "icon.ico")
