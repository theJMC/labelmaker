#!/usr/bin/env python3
"""
generate_labels.py

Reads a spreadsheet (xlsx or csv) with columns: name, group, position 1, position 2
and produces a printable A4 PDF of name labels, laid out in a grid
(default: 3 columns x 8 rows = 24 labels per page — matches common
"Avery-style" label sheets, e.g. L7160).

Usage:
    python generate_labels.py input.xlsx -o labels.pdf
    python generate_labels.py input.csv -o labels.pdf --cols 2 --rows 7

If your label sheet has different dimensions/margins than the default,
adjust the --cols/--rows/--margin options, or edit the LAYOUT DEFAULTS
below to match your specific label product.
"""

import argparse
import sys

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------------
# LABEL PRESETS — exact label width/height in mm, and grid layout.
# Page margins are derived automatically so the grid is centred on A4,
# assuming labels sit edge-to-edge with no gutter (true for most sheets,
# including Q-Connect / Avery equivalents).
# ---------------------------------------------------------------------------
PRESETS = {
    # Q-Connect KF26054: 99.1 x 38.1mm, 14 per A4 sheet (2 cols x 7 rows)
    # Equivalent to Avery L7163 / J8163.
    "kf26054": {"cols": 2, "rows": 7, "label_w": 99.1 * mm, "label_h": 38.1 * mm},
}

DEFAULT_COLS = 3
DEFAULT_ROWS = 8
LABEL_PADDING = 4 * mm      # inner padding within each label cell
DRAW_CUT_LINES = True       # light guide lines around each label

pdfmetrics.registerFont(TTFont("Comfortaa", "Comfortaa-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Comfortaa-Bold", "Comfortaa-Bold.ttf"))

def read_spreadsheet(path):
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    # normalise column names (case/whitespace-insensitive matching)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = ["name", "group", "position 1", "position 2"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Spreadsheet is missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    df = df.fillna("")
    return df[required].to_dict("records")


# Colours matching the reference label design
COLOR_NAME = colors.black
COLOR_GROUP = colors.HexColor("#1a73e8")   # blue
COLOR_POS1 = colors.HexColor("#188038")    # green
COLOR_POS2 = colors.HexColor("#d93025")    # red

# Prefixes shown before each position value (edit to taste, or set to "" for none)
POS1_PREFIX = "O: "
POS2_PREFIX = "F: "

# Quadrant proportions: name box takes COL1_FRAC of the width and ROW1_FRAC
# of the height; group/position boxes share the remaining space.
COL1_FRAC = 0.66
ROW1_FRAC = 0.66

BOLD_FONT = "Comfortaa-Bold"
FONT = "Comfortaa"
MAX_FONT_SIZE = 72
MIN_FONT_SIZE = 32


def _max_font_for_box(c, text, font, box_w, box_h, pad, max_size=MAX_FONT_SIZE, min_size=MIN_FONT_SIZE):
    """Largest font size (steps of 0.5) that fits text inside a box of given size, both by width and height."""
    if not text:
        return max_size
    avail_w = max(box_w - 2 * pad, 1)
    avail_h = max(box_h - 2 * pad, 1)
    size = min(max_size, avail_h)  # font size in pt is a close proxy for single-line text height
    while size > min_size and (c.stringWidth(text, font, size) > avail_w or size > avail_h):
        size -= 0.5
    return max(size, min_size)


def _draw_centered(c, text, font, size, box_x, box_w, box_y, box_h, color, align="left"):
    """Draw text vertically centred within a box; horizontally left- or right-aligned."""
    c.setFont(font, size)
    c.setFillColor(color)
    baseline = box_y + (box_h - size) / 2 + size * 0.22  # rough optical centring
    if align == "right":
        c.drawRightString(box_x + box_w - LABEL_PADDING, baseline, text)
    else:
        c.drawString(box_x + LABEL_PADDING, baseline, text)


def draw_label(c, x, y, w, h, record):
    """Draw one label's content inside the box (x, y, w, h) — origin is bottom-left.

    Layout: an asymmetric 2x2 grid — the name box takes COL1_FRAC of the
    width and ROW1_FRAC of the height (top-left, as large as possible);
    group/position boxes fill the remaining strip and share one font size.

        [Name, large, black, top-left     ] [Group, blue, top-right   ]
        [Position 1, green, bottom-left   ] [Position 2, red, bot-right]
    """
    if DRAW_CUT_LINES:
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.3)
        c.rect(x, y, w, h)

    pad = LABEL_PADDING
    col1_w = w * COL1_FRAC
    col2_w = w - col1_w
    row2_h = h * (1 - ROW1_FRAC)   # bottom row height
    row1_h = h - row2_h            # top row height

    name = str(record["name"]).strip().title()
    group = str(record["group"]).strip()
    pos1 = str(record["position 1"]).strip()
    pos2 = str(record["position 2"]).strip()
    pos1_text = f"{POS1_PREFIX}{pos1}" if pos1 else ""
    pos2_text = f"{POS2_PREFIX}{pos2}" if pos2 else ""

    # --- Name: maximize independently within its own (large) box ---
    name_size = _max_font_for_box(c, name, BOLD_FONT, col1_w, row1_h, pad)
    _draw_centered(c, name, BOLD_FONT, name_size, x, col1_w, y + row2_h, row1_h, COLOR_NAME, align="left")

    # --- Group / position 1 / position 2: one shared font size across all three ---
    boxes = [
        (group, col2_w, row1_h),
        (pos1_text, col1_w, row2_h),
        (pos2_text, col2_w, row2_h),
    ]
    candidate_sizes = [_max_font_for_box(c, t, BOLD_FONT, bw, bh, pad) for t, bw, bh in boxes if t]
    shared_size = min(candidate_sizes) if candidate_sizes else 10

    if group:
        _draw_centered(c, group, FONT, shared_size, x + col1_w, col2_w, y + row2_h, row1_h, COLOR_GROUP, align="right")
    if pos1_text:
        _draw_centered(c, pos1_text, FONT, shared_size, x, col1_w, y, row2_h, COLOR_POS1, align="left")
    if pos2_text:
        _draw_centered(c, pos2_text, FONT, shared_size, x + col1_w, col2_w, y, row2_h, COLOR_POS2, align="right")


def generate_pdf(records, output_path, cols=DEFAULT_COLS, rows=DEFAULT_ROWS,
                  label_w=None, label_h=None):
    page_w, page_h = A4

    if label_w and label_h:
        # Exact label dimensions given (e.g. from a preset) — centre the
        # grid on the page, labels sitting edge-to-edge (no gutter).
        margin_x = (page_w - cols * label_w) / 2
        margin_y = (page_h - rows * label_h) / 2
    else:
        # No exact dimensions — divide the printable area evenly.
        margin_x = 8 * mm
        margin_y = 13 * mm
        label_w = (page_w - 2 * margin_x) / cols
        label_h = (page_h - 2 * margin_y) / rows

    per_page = cols * rows
    c = canvas.Canvas(output_path, pagesize=A4)

    for i, record in enumerate(records):
        pos_on_page = i % per_page
        if pos_on_page == 0 and i != 0:
            c.showPage()

        col = pos_on_page % cols
        row = pos_on_page // cols

        x = margin_x + col * label_w
        # y counted from top of page downward
        y = page_h - margin_y - (row + 1) * label_h

        draw_label(c, x, y, label_w, label_h, record)

    c.save()


def main():
    parser = argparse.ArgumentParser(description="Generate an A4 sheet of name labels from a spreadsheet.")
    parser.add_argument("input", help="Path to input .xlsx or .csv file")
    parser.add_argument("-o", "--output", default="labels.pdf", help="Output PDF path (default: labels.pdf)")
    parser.add_argument("--cols", type=int, default=None, help=f"Labels per row (ignored if --preset is used; default: {DEFAULT_COLS})")
    parser.add_argument("--rows", type=int, default=None, help=f"Label rows per page (ignored if --preset is used; default: {DEFAULT_ROWS})")
    parser.add_argument("--preset", choices=sorted(PRESETS.keys()),
                         help="Use exact dimensions for a known label sheet, e.g. kf26054 (Q-Connect KF26054, 99.1x38.1mm, 14/sheet)")
    args = parser.parse_args()

    try:
        records = read_spreadsheet(args.input)
    except Exception as e:
        print(f"Error reading spreadsheet: {e}", file=sys.stderr)
        sys.exit(1)

    if not records:
        print("No rows found in spreadsheet — nothing to generate.", file=sys.stderr)
        sys.exit(1)

    if args.preset:
        p = PRESETS[args.preset]
        cols, rows = p["cols"], p["rows"]
        generate_pdf(records, args.output, cols=cols, rows=rows,
                     label_w=p["label_w"], label_h=p["label_h"])
    else:
        cols = args.cols or DEFAULT_COLS
        rows = args.rows or DEFAULT_ROWS
        generate_pdf(records, args.output, cols=cols, rows=rows)

    per_page = cols * rows
    pages = (len(records) + per_page - 1) // per_page
    print(f"Generated {len(records)} label(s) across {pages} page(s) -> {args.output}")


if __name__ == "__main__":
    main()