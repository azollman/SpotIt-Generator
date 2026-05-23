#!/usr/bin/env python3
"""
generate_test_images.py – Create 57 numbered test PNGs for generator.py,
plus a test card-back image usable with --back-image.

Usage:
    python generate_test_images.py [--output ./test_symbols] [--seed 0]
"""

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args():
    p = argparse.ArgumentParser(description="Generate 57 numbered test symbol PNGs")
    p.add_argument("--output", default="./test_symbols",
                   help="Output folder (default: ./test_symbols)")
    p.add_argument("--seed", type=int, default=0,
                   help="Random seed for colors (default: 0)")
    p.add_argument("--size", type=int, default=256,
                   help="Image canvas size in pixels (default: 256)")
    return p.parse_args()


def random_vivid_color(rng: random.Random) -> tuple:
    """Return a vivid, saturated RGB color (avoids near-white/near-black)."""
    h = rng.random()
    s = rng.uniform(0.65, 1.0)
    v = rng.uniform(0.55, 0.95)
    # HSV → RGB
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    segments = [
        (v, t, p), (q, v, p), (p, v, t),
        (p, q, v), (t, p, v), (v, p, q),
    ]
    r, g, b = segments[i % 6]
    return (int(r * 255), int(g * 255), int(b * 255))


def make_number_image(number: int, color: tuple, size: int) -> Image.Image:
    """Render a number centered on a transparent background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    text = str(number)

    # Try to load a bold system font; fall back to Pillow's built-in bitmap font
    font = None
    font_size = int(size * 0.62)
    for attempt in range(8):
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
            break
        except OSError:
            pass
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
            break
        except OSError:
            pass
        try:
            # Common Linux path
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            break
        except OSError:
            pass
        font_size = int(font_size * 0.85)

    if font is None:
        font = ImageFont.load_default()

    # Center text
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]

    # Subtle dark shadow for legibility
    shadow = tuple(max(0, c - 80) for c in color)
    draw.text((x + 3, y + 3), text, font=font, fill=(*shadow, 180))
    draw.text((x, y), text, font=font, fill=(*color, 255))

    return img


def make_back_image(size: int) -> Image.Image:
    """Generate a simple card-back test image: dark circle with a star pattern."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy, r = size / 2, size / 2, size / 2 - 4
    # Background circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 60, 255))

    # Decorative ring
    ring_r = r * 0.88
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=(200, 180, 0, 255), width=max(2, size // 80),
    )

    # Eight-pointed star in the centre
    import math
    star_pts = []
    outer, inner = r * 0.42, r * 0.18
    for i in range(16):
        angle = math.pi * i / 8 - math.pi / 2
        radius = outer if i % 2 == 0 else inner
        star_pts.append((cx + radius * math.cos(angle),
                         cy + radius * math.sin(angle)))
    draw.polygon(star_pts, fill=(200, 180, 0, 255))

    # Small "BACK" label near the bottom
    label = "TEST BACK"
    font_size = max(12, size // 16)
    font = None
    for attempt in range(6):
        for name in ("arial.ttf", "DejaVuSans-Bold.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(name, font_size)
                break
            except OSError:
                pass
        if font:
            break
        font_size = int(font_size * 0.85)
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2 - bbox[0], cy + r * 0.62 - bbox[1]),
              label, font=font, fill=(200, 180, 0, 220))

    return img


def main():
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    for n in range(1, 58):
        color = random_vivid_color(rng)
        img = make_number_image(n, color, args.size)
        path = output_dir / f"symbol_{n:02d}.png"
        img.save(path, "PNG")
        print(f"  {path.name}  color=rgb{color}")

    # Save alongside (not inside) the symbols folder so the generator's
    # "exactly 57 files" check isn't tripped.
    back_path = output_dir.parent / "test_back.png"
    make_back_image(args.size).save(back_path, "PNG")
    print(f"  {back_path}  (card back test image)")

    print(f"\nDone. 57 symbols + 1 back image saved.")
    print(f"Run:  python generator.py {output_dir}/")
    print(f"      python generator.py {output_dir}/ --back-image {back_path}")


if __name__ == "__main__":
    main()
