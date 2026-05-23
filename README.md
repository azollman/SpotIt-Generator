# Spot It Card Deck Generator

A Python script that generates a complete [Spot It](https://www.asmodee.us/en/games/spot-it/)-style card deck from a folder of your own symbol images.

> **Trademark notice:** "Spot It" is a registered trademark of Asmodee. This project is an independent, open-source tool for generating custom card decks using the same mathematical structure. It is not affiliated with, endorsed by, or produced by Asmodee or any of its subsidiaries.

---

## What it does

Given 57 images (PNG or SVG), the generator produces:

- **55 cards** (`card_001.png` – `card_055.png`) — every pair of cards shares exactly one symbol, the defining property of the game
- **`deck.pdf`** — print-ready US Letter sheets with crop marks, dynamically laid out based on card size
- **`verify.txt`** — checks all 1,485 card pairs and confirms the one-shared-symbol property holds

The mathematical foundation is the **order-7 finite projective plane PG(2,7)**, which guarantees the shared-symbol property by construction.

---

## Requirements

- Python 3.8+
- [Pillow](https://python-pillow.org/)
- [NumPy](https://numpy.org/)
- [ReportLab](https://www.reportlab.com/)
- [cairosvg](https://cairosvg.org/) *(only required if any of your symbols are SVG files)*

Install all dependencies:

```bash
pip install -r requirements.txt
```

### cairosvg on Windows

cairosvg requires the GTK3/Cairo runtime. If you only have PNG symbols you can skip it — the import only runs when an `.svg` file is encountered. If you need SVG support, install the [GTK3 runtime for Windows](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer) first.

---

## Quick start

```bash
# 1. (Optional) Generate numbered test symbols to try it out
python generate_test_images.py --output ./test_symbols

# 2. Generate the deck
python generator.py ./test_symbols --output ./output
```

Output lands in `./output/`.

---

## Usage

```
python generator.py <image_folder> [options]
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `image_folder` | *(required)* | Path to a folder containing **exactly 57** PNG or SVG files |
| `--output` | `./output` | Directory where output files are written |
| `--seed` | `42` | Random seed — fix this to reproduce the same deck |
| `--card-diameter-inches` | `3.46` | Physical card diameter (3.46" is standard Spot It size) |
| `--dpi` | `300` | Resolution for rasterization and PDF |
| `--card-size` | `diameter × dpi` | Override pixel diameter of each card |
| `--pack-iterations` | `800` | Force-simulation iterations for circle packing per card |

### Examples

```bash
# Standard deck from your own symbols
python generator.py ./my_symbols/

# Smaller, faster test run
python generator.py ./my_symbols/ --card-diameter-inches 2.5 --dpi 150 --pack-iterations 400

# Reproducible deck with a specific seed
python generator.py ./my_symbols/ --seed 1234 --output ./deck_1234
```

---

## Preparing your symbols

- Provide **exactly 57 image files** (PNG and/or SVG) in a single flat folder
- **PNG:** use a transparent alpha channel, or a pure white background — the generator detects which and masks accordingly
- **SVG:** rasterized automatically at 512×512 before processing
- The generator computes a tight bounding box per symbol so blank canvas space doesn't eat into the allocated circle area
- Symbol images can be any size or aspect ratio; they are scaled to fit their allocated circle on the card

---

## How it works

### 1. Symbol loading
Each image is loaded and converted to RGBA. If the alpha channel is nearly opaque throughout, pure white (within a tolerance of ±10) is treated as transparent. A tight bounding box is computed from the resulting mask.

### 2. Projective plane construction
The 57 cards and their symbol assignments are derived from **PG(2,7)** — the projective plane of order 7 — constructed algebraically over GF(7). This produces 57 lines of 8 points each where every pair of lines intersects at exactly one point. 55 of those 57 lines become cards. The mapping from mathematical point indices to your symbol images is randomly shuffled (controlled by `--seed`).

### 3. Circle packing
Each card's 8 symbols are placed using a force-directed simulation:
- Circles start at evenly-spaced angles with area-uniform radial distribution
- Each iteration applies pairwise repulsion (hard at overlap, soft at long range), a boundary repulsion keeping symbols away from the card edge, and a minimal centering nudge
- After convergence, each circle expands to 90% of its maximum non-overlapping radius, using half the pairwise center distance so expanded symbols never bleed into each other
- A 1/8" inner margin is reserved around the card edge

### 4. Rendering
Each card is rendered with Pillow: symbols are cropped to their tight bounding box, scaled to their allocated circle, rotated by a random angle, and composited onto a white circular canvas. A circular clip mask is applied at the end.

### 5. Output
Individual PNGs are saved, a multi-page PDF is assembled with ReportLab (grid size calculated dynamically from card diameter and page margins), and `verify.txt` exhaustively checks every card pair.

---

## Test image generator

`generate_test_images.py` creates 57 numbered PNGs (1–57) in random vivid colors — useful for verifying layout and packing before committing to real artwork.

```bash
python generate_test_images.py [--output ./test_symbols] [--seed 0] [--size 256]
```

---

## License

MIT. See [LICENSE](LICENSE) for details.

This project uses the mathematical structure of a finite projective plane, which is in the public domain. The name "Spot It" and the original game are the intellectual property of Asmodee; this tool does not reproduce any copyrighted game content.
