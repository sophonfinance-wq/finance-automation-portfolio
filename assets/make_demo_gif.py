"""
Generate an animated terminal demo GIF for the portfolio README.

Renders the real demo output (test suite + close engine + Triangulate) as a
terminal that types out line by line, then loops. No screen recorder needed —
the GIF is produced programmatically with Pillow.

Run:  python make_demo_gif.py   ->  writes ./demo.gif
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "demo.gif"
W, H = 760, 432
PAD_X, TOP = 24, 64
LINE_H = 40

BG = (13, 17, 23)
BAR = (22, 27, 34)
DOTS = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]
BLUE = (88, 166, 255)
TEXT = (201, 209, 217)
DIM = (139, 148, 158)
GREEN = (63, 185, 80)
RED = (248, 81, 73)

FONT = "C:/Windows/Fonts/consola.ttf"
FONT_B = "C:/Windows/Fonts/consolab.ttf"
SIZE = 21
font = ImageFont.truetype(FONT, SIZE)
font_b = ImageFont.truetype(FONT_B, SIZE)

# Each line is a list of (text, color[, bold]) segments.
LINES = [
    [("$ python -m pytest -q", BLUE)],
    [("........................  ", DIM), ("10,010 passed", GREEN)],
    [("", TEXT)],
    [("$ python -m close_engine --period 2026-03", BLUE)],
    [("  Trial balance : Dr 3,573,687.50 / Cr 3,573,687.50 ", TEXT), ("[OK]", GREEN)],
    [("  Close status: ", TEXT), ("CLEAN", GREEN, True)],
    [("", TEXT)],
    [("$ python -m triangulate", BLUE)],
    [("  VERDICT: ", TEXT), ("FAIL", RED, True), ("  [cannot sign off]", DIM)],
    [("  [Critical]", RED), (" B5 TIE_OUT_MISMATCH", TEXT)],
]


def base_frame() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 40], fill=BAR)
    for i, c in enumerate(DOTS):
        d.ellipse([20 + i * 22 - 6, 14, 20 + i * 22 + 6, 26], fill=c)
    d.text((W / 2, 20), "finance-automation-portfolio — live demo",
           font=font, fill=DIM, anchor="mm")
    return img


def draw_lines(img: Image.Image, n: int) -> None:
    d = ImageDraw.Draw(img)
    for row, segments in enumerate(LINES[:n]):
        x, y = PAD_X, TOP + row * LINE_H
        for seg in segments:
            txt, color = seg[0], seg[1]
            f = font_b if (len(seg) > 2 and seg[2]) else font
            d.text((x, y), txt, font=f, fill=color)
            x += d.textlength(txt, font=f)


frames, durations = [], []
for n in range(1, len(LINES) + 1):
    img = base_frame()
    draw_lines(img, n)
    frames.append(img)
    durations.append(180 if LINES[n - 1][0][0] == "" else 460)
# Hold the final frame.
final = base_frame()
draw_lines(final, len(LINES))
frames.append(final)
durations.append(2600)

frames[0].save(
    OUT, save_all=True, append_images=frames[1:],
    duration=durations, loop=0, optimize=True,
)
print("Wrote", OUT, f"({OUT.stat().st_size // 1024} KB, {len(frames)} frames)")
