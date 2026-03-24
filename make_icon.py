"""Run once to regenerate the tray icon: python make_icon.py"""
from PIL import Image, ImageDraw
import os

SIZE = 64


def _make_frame(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background circle — deep violet
    d.ellipse([1, 1, size - 2, size - 2], fill=(90, 50, 200, 255))

    s = size / 64  # scale factor

    # --- Mic body (rounded rectangle) ---
    mw = int(18 * s)
    mh = int(26 * s)
    mx = (size - mw) // 2
    my = int(9 * s)
    d.rounded_rectangle([mx, my, mx + mw, my + mh], radius=mw // 2,
                         fill=(255, 255, 255, 255))

    # --- Mic stand arc ---
    aw = int(32 * s)
    ah = int(18 * s)
    ax = (size - aw) // 2
    ay = int(28 * s)
    d.arc([ax, ay, ax + aw, ay + ah], start=0, end=180,
          fill=(255, 255, 255, 255), width=max(2, int(3 * s)))

    # --- Pole ---
    px = size // 2
    py1 = int(ay + ah // 2)
    py2 = int(50 * s)
    d.line([px, py1, px, py2], fill=(255, 255, 255, 255),
           width=max(2, int(3 * s)))

    # --- Base ---
    bw = int(20 * s)
    bx = (size - bw) // 2
    d.line([bx, py2, bx + bw, py2], fill=(255, 255, 255, 255),
           width=max(2, int(3 * s)))

    return img


def make_icons():
    os.makedirs("assets", exist_ok=True)

    base = _make_frame(SIZE)
    base.save("assets/icon.png")

    # ICO needs multiple sizes for crisp rendering at all DPI levels
    sizes = [16, 24, 32, 48, 64]
    frames = [_make_frame(s) for s in sizes]
    frames[0].save(
        "assets/icon.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print("Saved: assets/icon.png  assets/icon.ico")


if __name__ == "__main__":
    make_icons()
