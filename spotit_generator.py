#!/usr/bin/env python3
"""
spotit_generator.py – Generate a complete Spot It (Dobble) card deck.

Usage:
    python spotit_generator.py <image_folder> [options]
"""

import argparse
import io
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Generate a Spot It card deck from 57 images")
    p.add_argument("image_folder", help="Folder containing exactly 57 PNG/SVG files")
    p.add_argument("--card-diameter-inches", type=float, default=3.46,
                   help="Physical card diameter in inches (default: 3.46)")
    p.add_argument("--dpi", type=int, default=300,
                   help="Resolution in DPI (default: 300)")
    p.add_argument("--card-size", type=int, default=None,
                   help="Card pixel diameter (default: diameter_inches × dpi)")
    p.add_argument("--output", default="./output",
                   help="Output directory (default: ./output)")
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for reproducibility (default: 42)")
    p.add_argument("--pack-iterations", type=int, default=800,
                   help="Circle packing iterations per card (default: 800)")
    args = p.parse_args()
    if args.card_size is None:
        args.card_size = int(args.card_diameter_inches * args.dpi)
    return args


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 – Symbol loading and masking
# ─────────────────────────────────────────────────────────────────────────────

def _rasterize_svg(path: Path, size: int = 512) -> Image.Image:
    import cairosvg
    png_bytes = cairosvg.svg2png(url=str(path), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _load_png(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _compute_mask_and_bbox(img: Image.Image):
    """Return (masked_RGBA_image, tight_bbox) where bbox = (left, top, right, bottom)."""
    arr = np.array(img)          # H × W × 4
    alpha = arr[:, :, 3]

    if alpha.mean() > 240:
        # Alpha channel carries no useful transparency; detect white background
        rgb = arr[:, :, :3].astype(np.int16)
        is_white = np.all(np.abs(rgb - 255) <= 10, axis=2)
        mask_arr = (~is_white).astype(np.uint8) * 255
        new_img = img.copy()
        new_img.putalpha(Image.fromarray(mask_arr, "L"))
        eff_alpha = mask_arr
    else:
        new_img = img.copy()
        eff_alpha = alpha

    rows_hit = np.any(eff_alpha > 10, axis=1)
    cols_hit = np.any(eff_alpha > 10, axis=0)

    if not rows_hit.any():
        return new_img, (0, 0, img.width, img.height)

    rmin = int(np.argmax(rows_hit))
    rmax = int(len(rows_hit) - 1 - np.argmax(rows_hit[::-1]))
    cmin = int(np.argmax(cols_hit))
    cmax = int(len(cols_hit) - 1 - np.argmax(cols_hit[::-1]))

    return new_img, (cmin, rmin, cmax + 1, rmax + 1)


def load_all_symbols(folder: Path) -> list:
    """Return list of (RGBA_image, bbox) for all 57 symbols."""
    exts = {".png", ".svg"}
    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in exts)
    if len(files) != 57:
        sys.exit(f"Expected 57 images in {folder!s}, found {len(files)}")

    result = []
    for f in files:
        print(f"  Loading {f.name}")
        raw = _rasterize_svg(f) if f.suffix.lower() == ".svg" else _load_png(f)
        img, bbox = _compute_mask_and_bbox(raw)
        result.append((img, bbox))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – Projective plane PG(2, 7)
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_triple(x, y, z, q=7):
    """Return canonical representative of [x:y:z] in PG(2, q)."""
    for v in (x, y, z):
        if v != 0:
            inv = pow(v, q - 2, q)   # v^{-1} mod q via Fermat's little theorem
            return (x * inv % q, y * inv % q, z * inv % q)
    return None  # zero vector – caller guarantees this never happens


def build_pg2_7():
    """
    Construct PG(2, 7): the projective plane of order 7.

    Returns a list of 57 lines, each a sorted list of 8 point indices (0–56).
    Every pair of distinct lines shares exactly one point index.
    """
    q = 7
    seen_pts: dict = {}
    points: list = []
    for x in range(q):
        for y in range(q):
            for z in range(q):
                if x == y == z == 0:
                    continue
                n = _normalize_triple(x, y, z, q)
                if n not in seen_pts:
                    seen_pts[n] = len(points)
                    points.append(n)

    expected = q * q + q + 1   # 57
    assert len(points) == expected

    seen_lines: set = set()
    lines: list = []
    for a in range(q):
        for b in range(q):
            for c in range(q):
                if a == b == c == 0:
                    continue
                ln = _normalize_triple(a, b, c, q)
                if ln in seen_lines:
                    continue
                seen_lines.add(ln)
                la, lb, lc = ln
                pts_on = [
                    seen_pts[pt]
                    for pt in seen_pts
                    if (la * pt[0] + lb * pt[1] + lc * pt[2]) % q == 0
                ]
                assert len(pts_on) == q + 1, f"Line has {len(pts_on)} pts, expected {q+1}"
                lines.append(sorted(pts_on))

    assert len(lines) == expected
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – Circle packing
# ─────────────────────────────────────────────────────────────────────────────

_PACK_R = 0.11   # packing radius used during force simulation


def pack_circles(n: int, rng: random.Random, iterations: int,
                 inner_margin: float = 0.0) -> list:
    """
    Pack n circles inside the unit disk via force-directed simulation with
    simulated annealing.

    inner_margin: fraction of card radius to reserve as a blank border ring.
                  E.g. 0.072 ≈ 1/8" on a 3.46" card.

    Returns [(cx, cy, r), ...] where coords are fractions of card radius and r
    is 90% of the maximum non-overlapping radius available at each position.

    Three principles keep symbols spread across the full card:
      1. Initial positions use evenly-spaced angles + sqrt-radial sampling so
         circles start uniformly distributed in *area*, not clustered at centre.
      2. A long-range spreading force (not just contact repulsion) pushes circles
         apart until they are well separated, filling available space.
      3. A soft boundary repulsion prevents edge-hugging while keeping the outer
         ring of the card usable.  The centering force is kept tiny (0.003) so it
         only breaks symmetry in degenerate cases, not drives layout.
    """
    boundary = 1.0 - inner_margin   # usable radius in normalised coords

    # Initialise: evenly-spaced angles with jitter + sqrt radial for uniform area
    circles = []
    for i in range(n):
        angle = (2 * math.pi * i / n) + rng.uniform(-math.pi / n, math.pi / n)
        # sqrt maps uniform→uniform-in-area; keep away from exact centre and edge
        max_init = max(0.05, boundary - _PACK_R - 0.05)
        dist = math.sqrt(rng.uniform(0.04, max_init ** 2))
        circles.append([dist * math.cos(angle), dist * math.sin(angle), _PACK_R])

    for t in range(iterations):
        temp = 1.0 - t / iterations
        step = 0.025 * (0.05 + 0.95 * temp)

        forces = [[0.0, 0.0] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                xi, yi, ri = circles[i]
                xj, yj, rj = circles[j]
                dx, dy = xi - xj, yi - yj
                d = math.hypot(dx, dy) + 1e-9
                min_d = ri + rj
                # Hard repulsion resolves actual overlaps immediately
                if d < min_d:
                    push = (min_d - d + 0.004) * 1.5
                else:
                    # Soft spreading force active up to 3.5× touch distance;
                    # this is what fills the card rather than leaving blank rings
                    spread_d = min_d * 3.5
                    if d < spread_d:
                        push = ((spread_d - d) / spread_d) * 0.045
                    else:
                        push = 0.0
                if push:
                    fx, fy = dx / d * push, dy / d * push
                    forces[i][0] += fx
                    forces[i][1] += fy
                    forces[j][0] -= fx
                    forces[j][1] -= fy

        for i in range(n):
            x, y, r = circles[i]
            dc = math.hypot(x, y) + 1e-9

            # Boundary repulsion: smooth push inward from the last 25% of usable radius
            edge_gap = (boundary - r) - dc
            if edge_gap < 0.25:
                bpush = ((0.25 - edge_gap) / 0.25) ** 2 * 0.06
                forces[i][0] -= (x / dc) * bpush
                forces[i][1] -= (y / dc) * bpush

            # Minimal centering nudge — only to break exact symmetry
            forces[i][0] -= x * 0.003
            forces[i][1] -= y * 0.003

            nx = x + forces[i][0] * step
            ny = y + forces[i][1] * step

            # Hard boundary clamp (respects inner_margin)
            dc2 = math.hypot(nx, ny)
            max_dc = boundary - r
            if dc2 > max_dc and dc2 > 1e-9:
                nx = nx / dc2 * max_dc
                ny = ny / dc2 * max_dc
            circles[i][0] = nx
            circles[i][1] = ny

    # Expand each circle to 90% of its maximum non-overlapping radius.
    # Use d(i,j)/2 per pair so that when *both* circles expand they still
    # just-touch rather than overlapping (fixes visual symbol bleed).
    result = []
    for i in range(n):
        xi, yi, _ = circles[i]
        max_r = boundary - math.hypot(xi, yi)
        for j in range(n):
            if j != i:
                xj, yj, _ = circles[j]
                room = math.hypot(xi - xj, yi - yj) / 2.0
                if room < max_r:
                    max_r = room
        max_r = max(0.06, max_r)
        result.append((xi, yi, max_r * 0.90))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 – Card rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_card(sym_indices: list, symbols: list, card_size: int,
                rng: random.Random, pack_iters: int,
                inner_margin: float = 0.0) -> Image.Image:
    """Render one card; returns an RGB PIL Image."""
    half = card_size // 2
    card = Image.new("RGBA", (card_size, card_size), (255, 255, 255, 255))

    circles = pack_circles(len(sym_indices), rng, pack_iters, inner_margin)

    for sym_idx, (cx_n, cy_n, r_n) in zip(sym_indices, circles):
        sym_img, (bx0, by0, bx1, by1) = symbols[sym_idx]
        bw, bh = bx1 - bx0, by1 - by0
        if bw <= 0 or bh <= 0:
            continue

        # r_n is fraction of card radius; symbol diameter = r_n * card_size px
        sym_d = max(2, int(r_n * card_size))
        scale = sym_d / max(bw, bh)
        nw = max(1, int(bw * scale))
        nh = max(1, int(bh * scale))

        cropped = sym_img.crop((bx0, by0, bx1, by1))
        scaled = cropped.resize((nw, nh), Image.LANCZOS)

        angle = rng.uniform(0, 360)
        rotated = scaled.rotate(angle, expand=True, resample=Image.BICUBIC)
        if rotated.mode != "RGBA":
            rotated = rotated.convert("RGBA")

        paste_x = half + int(cx_n * half) - rotated.width // 2
        paste_y = half + int(cy_n * half) - rotated.height // 2
        card.paste(rotated, (paste_x, paste_y), rotated)

    # Border drawn after symbols so it appears on top
    ImageDraw.Draw(card).ellipse(
        [1, 1, card_size - 2, card_size - 2],
        outline=(34, 34, 34, 255), width=2
    )

    # Circular clip mask
    clip = Image.new("L", (card_size, card_size), 0)
    ImageDraw.Draw(clip).ellipse([0, 0, card_size - 1, card_size - 1], fill=255)

    out = Image.new("RGB", (card_size, card_size), (255, 255, 255))
    out.paste(card.convert("RGB"), (0, 0), clip)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 – Output
# ─────────────────────────────────────────────────────────────────────────────

def save_card_pngs(cards: list, output_dir: Path):
    for i, card in enumerate(cards):
        card.save(output_dir / f"card_{i + 1:03d}.png", "PNG")
    print(f"  Saved {len(cards)} card PNGs")


def save_pdf(cards: list, output_dir: Path,
             card_diameter_inches: float, dpi: int):
    page_w, page_h = letter          # 612 × 792 pt
    margin     = 0.5   * inch
    gutter     = 0.25  * inch
    card_pt    = card_diameter_inches * inch
    crop_len   = 0.125 * inch

    cols = max(1, int((page_w - 2 * margin + gutter) / (card_pt + gutter)))
    rows = max(1, int((page_h - 2 * margin + gutter) / (card_pt + gutter)))

    grid_w = cols * card_pt + (cols - 1) * gutter
    grid_h = rows * card_pt + (rows - 1) * gutter
    x0 = (page_w - grid_w) / 2
    y0 = (page_h - grid_h) / 2

    pdf_path = str(output_dir / "deck.pdf")
    c = rl_canvas.Canvas(pdf_path, pagesize=letter)

    def _crop_marks(card_x, card_y):
        c.setStrokeColorRGB(0x88 / 255, 0x88 / 255, 0x88 / 255)
        c.setLineWidth(0.5)
        # (corner_x, corner_y, h_direction, v_direction)
        corners = [
            (card_x,           card_y + card_pt, -1,  1),  # top-left
            (card_x + card_pt, card_y + card_pt,  1,  1),  # top-right
            (card_x,           card_y,            -1, -1),  # bottom-left
            (card_x + card_pt, card_y,             1, -1),  # bottom-right
        ]
        for cx_, cy_, hdx, vdy in corners:
            c.line(cx_, cy_, cx_ + hdx * crop_len, cy_)
            c.line(cx_, cy_, cx_, cy_ + vdy * crop_len)

    idx = 0
    while idx < len(cards):
        for row in range(rows):
            for col in range(cols):
                if idx >= len(cards):
                    break
                card_x = x0 + col * (card_pt + gutter)
                # PDF y=0 at bottom; row 0 is visually top → flip
                card_y = y0 + (rows - 1 - row) * (card_pt + gutter)

                buf = io.BytesIO()
                cards[idx].save(buf, format="PNG")
                buf.seek(0)
                c.drawImage(ImageReader(buf), card_x, card_y,
                            width=card_pt, height=card_pt)
                _crop_marks(card_x, card_y)
                idx += 1

        if idx < len(cards):
            c.showPage()

    c.save()
    print(f"  Saved deck.pdf  ({cols}×{rows} grid, {cols * rows} cards/page)")


def save_verify(deck: list, output_dir: Path):
    violations = []
    n = len(deck)
    for i in range(n):
        for j in range(i + 1, n):
            shared = set(deck[i]) & set(deck[j])
            if len(shared) != 1:
                violations.append(
                    f"Cards {i + 1:3d} & {j + 1:3d}: "
                    f"{len(shared)} shared symbol(s) → {sorted(shared)}"
                )

    total_pairs = n * (n - 1) // 2
    path = output_dir / "verify.txt"
    with open(path, "w") as f:
        for v in violations:
            f.write(v + "\n")
        f.write(f"\nChecked {total_pairs} pairs across {n} cards.\n")
        if violations:
            f.write(f"{len(violations)} VIOLATIONS FOUND\n")
        else:
            f.write("ALL PAIRS OK\n")

    status = "ALL PAIRS OK" if not violations else f"{len(violations)} violations"
    print(f"  Saved verify.txt  ({status}, {total_pairs} pairs checked)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    folder = Path(args.image_folder)
    if not folder.is_dir():
        sys.exit(f"Not a directory: {folder}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)

    print("Step 1: Loading symbols...")
    symbols = load_all_symbols(folder)

    print("Step 2: Building PG(2,7) projective plane...")
    all_lines = build_pg2_7()    # 57 lines × 8 point-indices each

    # Shuffle lines; take 55 for the deck.  Shuffle the symbol→image mapping
    # so the algebraic structure doesn't create visual patterns.
    rng.shuffle(all_lines)
    deck_lines = all_lines[:55]

    sym_map = list(range(57))
    rng.shuffle(sym_map)
    deck = [[sym_map[p] for p in line] for line in deck_lines]

    # 1/8" margin as a fraction of card radius
    inner_margin = 0.125 / (args.card_diameter_inches / 2)

    print("Steps 3 & 4: Packing circles and rendering cards...")
    cards = []
    for i, card_syms in enumerate(deck):
        # Unique, deterministic seed per card via bit-mixing
        card_seed = args.seed ^ (i * 0x9E3779B9 & 0xFFFFFFFF)
        card_rng  = random.Random(card_seed)
        card = render_card(card_syms, symbols, args.card_size,
                           card_rng, args.pack_iterations, inner_margin)
        cards.append(card)
        if (i + 1) % 11 == 0 or i == 54:
            print(f"  {i + 1}/55 cards rendered", flush=True)

    print("Step 5: Saving output...")
    save_card_pngs(cards, output_dir)
    save_pdf(cards, output_dir, args.card_diameter_inches, args.dpi)
    save_verify(deck, output_dir)

    print(f"\nDone.  {len(cards)} cards → {output_dir}/")
    print(f"  Card size: {args.card_size}×{args.card_size} px  "
          f"({args.card_diameter_inches}\" @ {args.dpi} DPI)")


if __name__ == "__main__":
    main()
