"""
Generate high-end, corporate-GUI animated demo GIFs (one per system).

Premium render pipeline:
  * 2x supersampling (rendered at 2000x1880, LANCZOS-downscaled) for crisp text
  * taller mobile-friendly frames so code, output, and status badges read larger
  * light report-card panels + clean accent colors for the portfolio flow style
  * a header progress bar, a blinking caret, KPI fade-ins, and a glowing badge
A shared design system makes the demos read as one product. Code + output are
authentic per engine. No screen recorder needed.

Run:  python make_system_gifs.py   ->  writes ./systems/<key>.gif
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).parent / "systems"
OUT.mkdir(exist_ok=True)

W, H = 1000, 940
S = 2                       # supersample factor
RW, RH = W * S, H * S

# ----- palette ------------------------------------------------------------- #
BG_TOP    = (248, 250, 252)
BG_BOT    = (241, 245, 249)
CARD      = (255, 255, 255)
PANEL     = (255, 255, 255)
KPI_BG    = (248, 250, 252)
BORDER    = (203, 213, 225)
BORDER2   = (226, 232, 240)
TITLEBAR  = (255, 255, 255)
TEXT      = (15, 23, 42)
DIM       = (51, 65, 85)
FAINT     = (100, 116, 139)
GUTTER    = (148, 163, 184)
GREEN     = (21, 128, 61)
RED       = (185, 28, 28)
AMBER     = (180, 83, 9)
WHITE     = (240, 244, 250)

C_KW   = (109, 40, 217)
C_FN   = (37, 99, 235)
C_TYPE = (8, 145, 178)
C_STR  = (180, 83, 9)
C_NUM  = (21, 128, 61)
C_COM  = (100, 116, 139)
C_PLN  = (51, 65, 85)

DOTS = [(239, 68, 68), (245, 158, 11), (34, 197, 94)]
SLOW_FACTOR = 1.55


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def darken(c, t=0.55):
    return tuple(int(x * t) for x in c)


def f(name, size):
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}.ttf", size * S)


UI       = f("segoeui", 19)
UI_SM    = f("segoeui", 16)
UI_XS    = f("segoeui", 15)
UI_H     = f("seguisb", 33)
UI_SB    = f("seguisb", 16)
UI_KPI   = f("seguisb", 32)
UI_BADGE = f("seguisb", 26)
MONO     = f("consola", 17)
MONO_B   = f("consolab", 17)


class G:
    """Scale-aware drawing surface (logical coords in, supersampled out)."""

    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img, "RGBA")

    def rr(self, box, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle([c * S for c in box], radius=r * S,
                                 fill=fill, outline=outline, width=max(1, width * S))

    def rect(self, box, fill):
        self.d.rectangle([c * S for c in box], fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line([c * S for c in pts], fill=fill, width=max(1, width * S))

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse([c * S for c in box], fill=fill, outline=outline, width=max(1, width * S))

    def polygon(self, pts, fill=None, outline=None, width=1):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill, outline=outline, width=max(1, width * S))

    def pline(self, pts, fill, width=1, joint=None):
        self.d.line([(x * S, y * S) for x, y in pts], fill=fill, width=max(1, width * S), joint=joint)

    def text(self, xy, s, font, fill, anchor=None):
        self.d.text((xy[0] * S, xy[1] * S), s, font=font, fill=fill, anchor=anchor)

    def textlen(self, s, font):
        return self.d.textlength(s, font=font) / S

    def tracked(self, xy, s, font, fill, tr=1.6):
        x, y = xy
        for ch in s:
            self.text((x, y), ch, font, fill)
            x += self.textlen(ch, font) + tr


def vgrad(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        col = lerp(c1, c2, t)
        for x in range(w):
            px[x, y] = col
    return img


def soft_shadow(boxes, radius=18, alpha=120, dy=7):
    """Return an RGBA layer with blurred dark rounded rects for the given boxes."""
    layer = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for box in boxes:
        b = [box[0] * S, (box[1] + dy) * S, box[2] * S, (box[3] + dy) * S]
        d.rounded_rectangle(b, radius=radius * S, fill=(0, 0, 0, alpha))
    return layer.filter(ImageFilter.GaussianBlur(radius * S * 0.6))


def draw_icon(g, name, box, color=WHITE):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    if name == "calendar":
        g.rr([x + 3, y + 5, x + w - 3, y + h - 3], 3, outline=color, width=2)
        g.line([x + 3, y + 11, x + w - 3, y + 11], fill=color, width=2)
        for gx in (x + 8, x + 14, x + 20):
            for gy in (y + 16, y + 22):
                g.ellipse([gx - 1, gy - 1, gx + 1, gy + 1], fill=color)
    elif name == "recon":
        g.line([x + 4, y + 10, x + w - 4, y + 10], fill=color, width=2)
        g.polygon([(x + w - 4, y + 10), (x + w - 9, y + 6), (x + w - 9, y + 14)], fill=color)
        g.line([x + 4, y + h - 10, x + w - 4, y + h - 10], fill=color, width=2)
        g.polygon([(x + 4, y + h - 10), (x + 9, y + h - 14), (x + 9, y + h - 6)], fill=color)
    elif name == "tiers":
        for i, ww in enumerate((20, 14, 8)):
            yy = y + 7 + i * 7
            g.rect([cx - ww / 2, yy, cx + ww / 2, yy + 4], fill=color)
    elif name == "shield":
        g.pline([(x + 6, y + 14), (x + 11, y + 19), (x + w - 6, y + 8)], fill=color, width=3, joint="curve")
    elif name == "triangle":
        pts = [(cx, y + 5), (x + 5, y + h - 5), (x + w - 5, y + h - 5)]
        g.pline(pts + [pts[0]], fill=color, width=2, joint="curve")
        for p in pts:
            g.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=color)
    elif name == "brain":
        g.ellipse([x + 5, y + 5, x + w - 5, y + h - 5], outline=color, width=2)
        g.line([cx, y + 6, cx, y + h - 6], fill=color, width=2)
        for px, py in ((cx - 5, y + 11), (cx + 5, y + 14), (cx - 4, y + h - 12), (cx + 5, y + h - 13)):
            g.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)


def draw_phone_badge(g, accent, active=False, pulse=False):
    """Small mobile command/status badge used in every engine demo."""
    x1, y1, x2, y2 = 656, 104, 964, 126
    fill = lerp((255, 255, 255), accent, 0.06 if active else 0)
    outline = accent if active else BORDER
    dot = lerp(accent, WHITE, 0.35 if pulse else 0.0) if active else FAINT

    g.rr([x1, y1, x2, y2], 11, fill=fill, outline=outline)
    g.rr([x1 + 12, y1 + 4, x1 + 28, y1 + 18], 3,
         fill=(255, 255, 255), outline=accent, width=2)
    g.ellipse([x1 + 19, y1 + 16, x1 + 21, y1 + 18], fill=accent)
    g.ellipse([x2 - 23, y1 + 7, x2 - 13, y1 + 17], fill=dot)
    g.text((x1 + 38, y1 + 3), "mobile command", UI_XS, DIM)
    g.text((x1 + 170, y1 + 3), "status -> phone", UI_XS, accent if active else FAINT)


def build_base(sys):
    accent = sys["accent"]
    acc_dk = darken(accent, 0.45)

    img = vgrad(RW, RH, BG_TOP, BG_BOT)
    # faint dot grid in body
    dd = ImageDraw.Draw(img)
    for yy in range(150, H - 70, 26):
        for xx in range(40, W - 30, 30):
            dd.ellipse([xx * S, yy * S, xx * S + S, yy * S + S], fill=(226, 232, 240))

    # shadows: card + the two panels
    sh = soft_shadow([[14, 12, 986, H - 12]], radius=22, alpha=34, dy=9)
    img = Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB")
    sh2 = soft_shadow([[28, 144, 972, 498], [28, 516, 972, H - 52]], radius=16, alpha=42, dy=6)
    img = Image.alpha_composite(img.convert("RGBA"), sh2).convert("RGB")

    g = G(img)
    # window card + subtle top highlight
    g.rr([14, 12, 986, H - 12], 13, fill=CARD, outline=BORDER, width=1)
    g.line([26, 13, 974, 13], fill=(226, 232, 240))
    # title bar
    g.rr([14, 12, 986, 52], 13, fill=TITLEBAR)
    g.rect([14, 40, 986, 52], TITLEBAR)
    for i, c in enumerate(DOTS):
        g.ellipse([34 + i * 20 - 5, 27, 34 + i * 20 + 5, 37], fill=c)
    g.text((110, 23), sys["file"], UI_SM, DIM)
    tw = g.textlen(sys["file"], UI_SM)
    g.rect([110, 45, 110 + tw, 47], accent)            # active-tab underline
    g.text((986 - 22, 24), "FINANCE  ·  AUTOMATION  ·  PLATFORM", UI_XS, FAINT, anchor="ra")

    # header: gradient logo + icon, name, subtitle
    logo = vgrad(44 * S, 44 * S, lerp(accent, (255, 255, 255), 0.18), acc_dk)
    mask = Image.new("L", (44 * S, 44 * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 44 * S - 1, 44 * S - 1], radius=10 * S, fill=255)
    img.paste(logo, (32 * S, 66 * S), mask)
    g = G(img)
    draw_icon(g, sys["icon"], (40, 74, 28, 28))
    g.text((90, 65), sys["name"], UI_H, TEXT)
    g.text((92, 97), sys["subtitle"], UI_SM, DIM)

    # python chip (static)
    cx = W - 132
    g.rr([cx, 78, cx + 96, 100], 11, fill=KPI_BG, outline=BORDER)
    g.ellipse([cx + 12, 85, cx + 20, 93], fill=accent)
    g.text((cx + 28, 80), "Python 3.14", UI_XS, DIM)
    draw_phone_badge(g, accent)

    # progress track
    g.rect([32, 132, W - 32, 135], BORDER2)

    # code panel frame
    g.rr([28, 144, 972, 498], 11, fill=PANEL, outline=BORDER2, width=1)
    g.rect([28, 156, 31, 486], accent)
    g.text((46, 154), "engine.py", MONO, DIM)
    g.text((148, 156), sys["code_caption"], UI_XS, FAINT)
    g.line([40, 184, 960, 184], fill=BORDER2)

    # output panel frame + empty KPI cards + output label
    g.rr([28, 516, 972, H - 52], 11, fill=PANEL, outline=BORDER2, width=1)
    kx = 44
    for _ in sys["kpis"]:
        g.rr([kx, 528, kx + 284, 588], 9, fill=KPI_BG, outline=BORDER2, width=1)
        # gradient top accent bar
        bar = vgrad(int((284 - 4) * S), 3 * S, accent, acc_dk)
        img.paste(bar, (int((kx + 2) * S), 528 * S))
        kx += 304
    g = G(img)
    g.tracked((44, 606), "OUTPUT", UI_XS, FAINT, tr=2.4)
    g.line([44, 626, 956, 626], fill=BORDER2)

    # footer (static)
    g.line([32, H - 44, W - 32, H - 44], fill=BORDER2)
    g.ellipse([34, H - 35, 42, H - 27], fill=accent)
    g.text((50, H - 38), "main", UI_XS, DIM)
    g.text((104, H - 38), sys["footer"], UI_XS, FAINT)
    g.ellipse([W - 152, H - 35, W - 144, H - 27], fill=GREEN)
    g.text((W - 136, H - 38), f"tests  {sys['tests']} passed", UI_XS, GREEN)

    return img, accent, acc_dk


def render_frame(base, sys, accent, acc_dk, code_n, con_n, kpi_t, badge_t,
                 caret, progress, running, pulse):
    img = base.copy()
    g = G(img)

    # progress fill
    fillw = int((W - 64) * progress)
    if fillw > 0:
        g.rect([32, 132, 32 + fillw, 135], accent)

    # status pill
    px1 = W - 132 - 150
    if running:
        pc, txt = accent, "RUNNING"
        r = 4 + (1 if pulse else 0)
        dot_c = lerp(accent, WHITE, 0.4 if pulse else 0.0)
    else:
        pc, txt = sys["badge_color"], sys["pill"]
        r, dot_c = 4, pc
    g.rr([px1, 78, px1 + 150, 100], 11, fill=KPI_BG, outline=BORDER)
    g.ellipse([px1 + 18 - r, 89 - r, px1 + 18 + r, 89 + r], fill=dot_c)
    g.text((px1 + 30, 80), txt, UI_SB, pc)
    draw_phone_badge(g, accent, active=running or badge_t > 0, pulse=pulse)

    # code lines
    y = 196
    for i, segs in enumerate(sys["code"][:code_n]):
        g.text((44, y), f"{i + 1:>2}", MONO, GUTTER)
        x = 74
        for s in segs:
            fnt = MONO_B if (len(s) > 2 and s[2]) else MONO
            g.text((x, y), s[0], fnt, s[1])
            x += g.textlen(s[0], fnt)
        y += 25
    if caret and 0 < code_n <= len(sys["code"]):
        last = sys["code"][code_n - 1]
        cx = 74 + sum(g.textlen(s[0], MONO_B if (len(s) > 2 and s[2]) else MONO) for s in last)
        cyy = 196 + (code_n - 1) * 25
        g.rect([cx + 2, cyy + 1, cx + 4, cyy + 21], accent)

    # KPI values (fade in)
    if kpi_t > 0:
        kx = 44
        for value, label in sys["kpis"]:
            g.text((kx + 16, 538), value, UI_KPI, lerp(KPI_BG, TEXT, kpi_t))
            g.tracked((kx + 17, 570), label.upper(), UI_XS, lerp(KPI_BG, DIM, kpi_t), tr=0.8)
            kx += 304

    # console lines
    y = 640
    for segs in sys["console"][:con_n]:
        x = 44
        for s in segs:
            fnt = MONO_B if (len(s) > 2 and s[2]) else MONO
            g.text((x, y), s[0], fnt, s[1])
            x += g.textlen(s[0], fnt)
        y += 20

    # status badge with glow
    if badge_t > 0:
        bc = sys["badge_color"]
        glow = lerp(PANEL, bc, 0.14 * badge_t)
        g.rr([40, 818, 960, 884], 12, fill=glow)
        g.rr([44, 822, 956, 880], 10, fill=(255, 255, 255),
             outline=lerp(PANEL, bc, badge_t), width=2)
        g.rect([44, 822, 48, 880], bc)
        g.text((68, 830), sys["badge"], UI_BADGE, lerp(PANEL, bc, badge_t))
        g.text((68, 858), sys["badge_sub"], UI_XS, lerp(PANEL, DIM, badge_t))

    return img.resize((W, H), Image.LANCZOS)


def render(sys):
    base, accent, acc_dk = build_base(sys)
    C, K = len(sys["code"]), len(sys["console"])
    total = C + K
    frames, dur = [], []

    def add(cn, kn, kpi, badge, caret, prog, running, pulse, ms):
        frames.append(render_frame(base, sys, accent, acc_dk, cn, kn, kpi, badge,
                                    caret, prog, running, pulse))
        dur.append(ms)

    add(0, 0, 0, 0, False, 0.0, True, False, 320)          # boot
    for i in range(1, C + 1):                               # type code
        add(i, 0, 0, 0, i % 2 == 1, i / total * 0.5, True, i % 2 == 0, 95)
    add(C, 0, 0, 0, True, 0.5, True, True, 160)
    for j, a in enumerate((0.34, 0.7, 1.0)):                # KPI fade-in
        add(C, 0, a, 0, True, 0.5, True, j % 2 == 0, 70)
    for j in range(1, K + 1):                               # stream console
        add(C, j, 1.0, 0, j % 2 == 0, (C + j) / total * 0.5 + 0.5, True, j % 2 == 1, 140)
    for a in (0.4, 0.75, 1.0):                              # badge glow-in + resolve
        add(C, K, 1.0, a, True, 1.0, False, False, 90)
    add(C, K, 1.0, 1.0, True, 1.0, False, False, 2600)      # hold

    # shared global palette -> small, flicker-free GIF
    master = frames[-1].convert("P", palette=Image.ADAPTIVE, colors=256)
    pframes = [fr.convert("RGB").quantize(palette=master, dither=Image.NONE) for fr in frames]
    path = OUT / f"{sys['key']}.gif"
    pframes[0].save(path, save_all=True, append_images=pframes[1:],
                    duration=[int(ms * SLOW_FACTOR) for ms in dur], loop=0, optimize=True)
    print(f"  {sys['key']:<12} {len(frames):>2} frames  {path.stat().st_size // 1024:>4} KB")


# --------------------------------------------------------------------------- #
# Per-system content (authentic code + real output)
# --------------------------------------------------------------------------- #
def kw(t): return (t, C_KW)
SYSTEMS = [
    {
        "key": "close", "accent": (37, 99, 235), "icon": "calendar",
        "file": "close_engine.py", "name": "Month-End Close Engine",
        "subtitle": "recurring journal entries · tie-out controls · 3 entities",
        "code_caption": "largest-remainder allocation + post control",
        "tests": 41, "footer": "seed 2026 · stdlib + openpyxl · integer-cent math",
        "pill": "CLEAN", "badge_color": GREEN, "badge": "CLOSE: CLEAN",
        "badge_sub": "every entry balances · schedules tie to the GL",
        "kpis": [("6", "Recurring JEs"), ("0", "Out-of-tie"), ("$3.57M", "Trial balance")],
        "code": [
            [kw("def"), (" allocate_by_ratio", C_FN), ("(total, weights_bps):", C_PLN)],
            [("    # split by basis points — parts sum to total", C_COM)],
            [("    ", C_PLN), kw("assert"), (" sum(weights_bps) == ", C_PLN), ("10_000", C_NUM)],
            [("    base = [total * w // ", C_PLN), ("10_000", C_NUM), (" for w ", C_PLN), kw("in"), (" weights]", C_PLN)],
            [("    rem = total - sum(base)", C_PLN), ("   # remainder pennies", C_COM)],
            [("    ", C_PLN), kw("for"), (" i ", C_PLN), kw("in"), (" largest_remainders(base)[:rem]:", C_PLN)],
            [("        base[i] += ", C_PLN), ("1", C_NUM), ("              # largest-remainder", C_COM)],
            [("    ", C_PLN), kw("return"), (" base", C_PLN), ("        # exact — no penny lost", C_COM)],
            [("", C_PLN)],
            [("    ", C_PLN), kw("def"), (" post", C_FN), ("(self, entry):", C_PLN)],
            [("        ", C_PLN), kw("if"), (" entry.debits != entry.credits:", C_PLN)],
            [("            ", C_PLN), kw("raise"), (" OutOfTie(entry.ref)", C_TYPE), ("   # refuse", C_COM)],
        ],
        "console": [
            [("$ ", (37, 99, 235)), ("python -m close_engine --period 2026-03", TEXT)],
            [("Month-end close — period 2026-03 (seed 2026)", DIM)],
            [("  Posted entries : ", DIM), ("6", TEXT)],
            [("  Refused (tie)  : ", DIM), ("0", TEXT)],
            [("  Trial balance  : Dr 3,573,687.50 / Cr 3,573,687.50 ", DIM), ("[OK]", GREEN)],
            [("  Prepaid amort.  acct 1400   8,100.00   ", DIM), ("ok", GREEN)],
            [("  Close status: ", DIM), ("CLEAN", GREEN, True)],
        ],
    },
    {
        "key": "recon", "accent": (8, 145, 178), "icon": "recon",
        "file": "recon_engine.py", "name": "Cash & Debt Reconciliation",
        "subtitle": "bank/lender-to-GL · materiality flagging · evidence log",
        "code_caption": "3-part debt formula + materiality classifier",
        "tests": 31, "footer": "by account number, never by row · 5-section evidence log",
        "pill": "2 FLAGS", "badge_color": AMBER, "badge": "2 FLAGS ESCALATED",
        "badge_sub": "deposit-in-transit + keying error caught",
        "kpis": [("9", "Accounts"), ("2", "Flagged"), ("$50", "Materiality")],
        "code": [
            [kw("def"), (" lender_three_part_total", C_FN), ("(stmt):", C_PLN)],
            [("    # principal + interest/reserve + late paydown", C_COM)],
            [("    ", C_PLN), kw("return"), (" round(stmt.principal", C_PLN)],
            [("                 + stmt.current_interest_reserve", C_PLN)],
            [("                 + stmt.late_paydown, ", C_PLN), ("2", C_NUM), (")", C_PLN)],
            [("", C_PLN)],
            [kw("def"), (" classify", C_FN), ("(variance, materiality):", C_PLN)],
            [("    ", C_PLN), kw("if"), (" abs(variance) <= TIE_TOLERANCE: ", C_PLN), kw("return")],
            [("        ", C_PLN), ('"clean"', C_STR), ("               # an exact tie", C_COM)],
            [("    ", C_PLN), kw("if"), (" abs(variance) <= materiality: ", C_PLN), kw("return"), (" ", C_PLN), ('"timing"', C_STR)],
            [("    ", C_PLN), kw("return"), (" ", C_PLN), ('"flag"', C_STR), ("                  # escalate", C_COM)],
        ],
        "console": [
            [("$ ", (8, 145, 178)), ("python -m recon_engine", TEXT)],
            [("Cash & Debt Reconciliation Engine", DIM)],
            [("  Accounts in scope : ", DIM), ("9", TEXT), ("  (cash=4 debt=4 skip=1)", FAINT)],
            [("  Clean ", DIM), ("5", GREEN), ("   Timing ", DIM), ("1", AMBER), ("   Flagged ", DIM), ("2", RED)],
            [("Flagged for review:", DIM)],
            [("  FLAG-001  CASH-1001  Maple Fund LP   ", AMBER), ("-1,875.40", TEXT)],
            [("  FLAG-002  DEBT-2003  Cedar Ridge     ", AMBER), ("12,500.00", TEXT)],
        ],
    },
    {
        "key": "surplus", "accent": (180, 83, 9), "icon": "tiers",
        "file": "surplus_engine.py", "name": "Tax Surplus / ACB Model",
        "subtitle": "Canadian foreign-affiliate surplus pools · 4-tier chain",
        "code_caption": "distribution waterfall with exempt cap",
        "tests": 26, "footer": "Reg. 5907 implemented generically · USD→CAD · fictional data",
        "pill": "TIES OUT", "badge_color": GREEN, "badge": "ROLL-FORWARD TIES",
        "badge_sub": "closing FY N  ==  opening FY N+1",
        "kpis": [("4", "Entity tiers"), ("$54.9M", "Total surplus"), ("Reg 5907", "Framework")],
        "code": [
            [kw("def"), (" run_waterfall", C_FN), ("(dist, opening, exempt_cap=", C_PLN), ("0.60", C_NUM), ("):", C_PLN)],
            [("    # order: exempt → taxable → pre-acq capital", C_COM)],
            [("    cap = dist * exempt_cap", C_PLN), ("          # Reg. 5907 exempt cap", C_COM)],
            [("    exempt  = min(opening.exempt, dist, cap)", C_PLN)],
            [("    rem     = dist - exempt", C_PLN)],
            [("    taxable = min(opening.taxable, rem)", C_PLN)],
            [("    rem    -= taxable", C_PLN)],
            [("    preacq  = min(opening.preacq, rem)", C_PLN)],
            [("    ", C_PLN), kw("return"), (" [Draw(", C_PLN), ('"exempt"', C_STR), (", exempt),", C_PLN)],
            [("            Draw(", C_PLN), ('"taxable"', C_STR), (", taxable),", C_PLN)],
            [("            Draw(", C_PLN), ('"preacq"', C_STR), (", preacq)]   # reconciles", C_PLN)],
        ],
        "console": [
            [("$ ", (180, 83, 9)), ("python -m surplus_engine --start 2021 --end 2024", TEXT)],
            [("Consolidated Surplus & ACB Summary  [FICTIONAL]", DIM)],
            [("  FY24  Birchwood Op Co      exempt ", DIM), ("10.07M", TEXT), ("  tax ", DIM), ("5.21M", TEXT)],
            [("  FY24  Cedar Mezz Holdings  exempt ", DIM), (" 3.07M", TEXT), ("  ", DIM), ("(cap)", AMBER)],
            [("  ACB moves only on capital events — never on income", FAINT)],
            [("  Grand total surplus (CAD): ", DIM), ("$54,922,699", GREEN, True)],
        ],
    },
    {
        "key": "partnership-tax", "accent": (8, 145, 178), "icon": "calendar",
        "file": "partnership_tax.py", "name": "Partnership 1065 Automation",
        "subtitle": "1065 map - K-1 preview - 704(c) built-in gain - review checks",
        "code_caption": "source bundle to Form 1065 / Schedule K / K-1",
        "tests": 40, "footer": "fictional bundle + 704(c) module - exact penny allocation",
        "pill": "READY", "badge_color": GREEN, "badge": "READY FOR REVIEW",
        "badge_sub": "1065 map, K-1 preview, and checks packaged",
        "kpis": [("5", "Return areas"), ("2", "Checks"), ("3", "Partners")],
        "code": [
            [kw("def"), (" build_tax_package", C_FN), ("(source):", C_PLN)],
            [("    # reverse-engineer source support into return-ready maps", C_COM)],
            [("    workpapers = extract_workpapers(source)", C_PLN)],
            [("    lines = map_form_1065(workpapers)", C_PLN)],
            [("    schedule_k = build_schedule_k(lines)", C_PLN)],
            [("    k1s = allocate_k1s(schedule_k, source.partners)", C_PLN)],
            [("    checks = run_review_checks(lines, schedule_k, k1s)", C_PLN)],
            [("    ", C_PLN), kw("assert"), (" all(c.status == ", C_PLN), ('\"OK\"', C_STR), (" for c in checks)", C_PLN)],
            [("    ", C_PLN), kw("return"), (" TaxPackage(workpapers, lines, k1s, checks)", C_TYPE)],
        ],
        "console": [
            [("$ ", (8, 145, 178)), ("python -m partnership_tax", TEXT)],
            [("Partnership 1065 Automation", DIM)],
            [("  Partnership : ", DIM), ("Demo 721 Development LP", TEXT)],
            [("  Workpapers  : ", DIM), ("tax_workpapers.md", TEXT)],
            [("  Preview     : ", DIM), ("form_1065_preview.json", TEXT)],
            [("  CHK-001 Form 1065 line 22 ties to Schedule K line 1 ", DIM), ("OK", GREEN, True)],
            [("  CHK-002 K-1 allocations sum to Schedule K line 1     ", DIM), ("OK", GREEN, True)],
            [("  Package status: ", DIM), ("READY FOR REVIEW", GREEN, True)],
        ],
    },
    {
        "key": "validation", "accent": (109, 40, 217), "icon": "shield",
        "file": "validation_engine.py", "name": "Validation Engine",
        "subtitle": "read-only rules over finished workbooks · PASS / REVIEW / FAIL",
        "code_caption": "@check registry · deterministic, read-only",
        "tests": 23, "footer": "opened read_only=True · byte-identical (sha256) after run",
        "pill": "DEFECTS CAUGHT", "badge_color": (109, 40, 217), "badge": "DEFECTS CAUGHT",
        "badge_sub": "strictly read-only · 0 files modified",
        "kpis": [("7", "Workbooks"), ("6", "Rules"), ("0", "Files modified")],
        "code": [
            [("@", C_FN), ("check", C_FN), ('("expected_formula")', C_STR)],
            [kw("def"), (" expected_formula", C_FN), ("(ctx):", C_PLN)],
            [("    # a total must be a formula, not hardcoded", C_COM)],
            [("    ", C_PLN), kw("for"), (" cell ", C_PLN), kw("in"), (" ctx.formula_cells():", C_PLN)],
            [("        ", C_PLN), kw("if"), (" ", C_PLN), kw("not"), (" cell.is_formula:", C_PLN)],
            [("            ", C_PLN), kw("yield"), (" Finding(FAIL, cell.ref,", C_TYPE)],
            [('                "expected a formula"', C_STR), (")", C_PLN)],
            [("", C_PLN)],
            [("@", C_FN), ("check", C_FN), ('("debit_credit_balance")', C_STR)],
            [kw("def"), (" trial_balance_ties", C_FN), ("(ctx):", C_PLN)],
            [("    ", C_PLN), kw("if"), (" ctx.debits != ctx.credits:   # never writes", C_PLN)],
            [("        ", C_PLN), kw("yield"), (" Finding(FAIL, ", C_TYPE), ('"TB"', C_STR), (", ...)", C_PLN)],
        ],
        "console": [
            [("$ ", (109, 40, 217)), ("python run.py", TEXT), ("   # audit 7 workbooks, read-only", FAINT)],
            [("  clean__Demo_Holdings .............. ", DIM), ("PASS", GREEN)],
            [("  hardcoded_total__Maple_Fund ....... ", DIM), ("FAIL", RED)],
            [("  unbalanced_tb__Birchwood_Op ....... ", DIM), ("FAIL", RED)],
            [("  stale_note__Cedar_Ridge ........... ", DIM), ("REVIEW", AMBER)],
            [("  cap_leftover__Sandbox_Capital ..... ", DIM), ("REVIEW", AMBER)],
            [("Overall: ", DIM), ("3 FAIL · 3 REVIEW · 1 PASS", TEXT)],
        ],
    },
    {
        "key": "triangulate", "accent": (109, 40, 217), "icon": "triangle",
        "file": "reviewer.py", "name": "Triangulate — AI Validation",
        "subtitle": "separation of duties applied to the AI itself · human-gated",
        "code_caption": "live Claude reviewer — stdlib urllib, no SDK",
        "tests": 21, "footer": "Preparer → Reviewer → Specialist → Audit → Human",
        "pill": "VERDICT: FAIL", "badge_color": RED, "badge": "VERDICT: FAIL",
        "badge_sub": "2 Critical · returned for rebuild",
        "kpis": [("3", "AI roles"), ("Opus 4.8", "Reviewer"), ("2", "Critical")],
        "code": [
            [kw("class"), (" AnthropicReviewer", C_TYPE), ("(LLMReviewer):", C_PLN)],
            [("    # live Claude reviewer — flags, never fixes", C_COM)],
            [("    ", C_PLN), kw("def"), (" generate_findings", C_FN), ("(self, view):", C_PLN)],
            [("        req = Request(API_URL, method=", C_PLN), ('"POST"', C_STR), (",", C_PLN)],
            [('          headers={"x-api-key": key,', C_PLN)],
            [('                   "anthropic-version": "2023-06-01"},', C_STR)],
            [("          data=json.dumps({", C_PLN)],
            [('            "model": "claude-opus-4-8",', C_STR)],
            [('            "system": GUARDRAILED_PROMPT,', C_STR), ("  # flag", C_COM)],
            [('            "output_config": {"format": SCHEMA}})) ', C_PLN)],
            [("        ", C_PLN), kw("return"), (" [Finding(**f) ", C_TYPE), kw("for"), (" f ", C_PLN), kw("in"), (" call(req)]", C_PLN)],
        ],
        "console": [
            [("$ ", (109, 40, 217)), ("python -m triangulate", TEXT)],
            [("TRIANGULATE ORCHESTRATOR — AI VALIDATION PIPELINE", DIM)],
            [("  Preparer → Reviewer → Specialist → Audit → Human", FAINT)],
            [("  ", DIM), ("[Critical]", RED), (" B5 TIE_OUT_MISMATCH 543k ≠ 544k", TEXT)],
            [("  ", DIM), ("[High]", AMBER), ("     B7 HARDCODED_NO_FORMULA", TEXT)],
            [("  Reviewer is read-only — digest unchanged  ok", FAINT)],
            [("VERDICT: ", DIM), ("FAIL", RED, True), ("  [cannot sign off]", DIM)],
        ],
    },
    {
        "key": "brain", "accent": (79, 70, 229), "icon": "brain",
        "file": "brain_engine.py", "name": "Knowledge Brain Engine",
        "subtitle": "carries the laws + reviewer corrections; cite or generate a fix prompt",
        "code_caption": "review transcript -> cited directives -> apply prompt",
        "tests": 75, "footer": "stdlib TF-IDF - no embeddings / LLM / network - fictional transcripts",
        "pill": "FIX PROMPT READY", "badge_color": GREEN, "badge": "FIX PROMPT READY",
        "badge_sub": "every change traced to the transcript - apply downstream",
        "kpis": [("4", "Directives"), ("100%", "Cited"), ("0", "Uncited")],
        "code": [
            [kw("def"), (" remediate", C_FN), ("(self, review):", C_PLN)],
            [("    # a reviewer's spoken corrections -> an apply-ready prompt", C_COM)],
            [("    directives = self.directives_for(review)", C_PLN)],
            [("    ", C_PLN), kw("if"), (" ", C_PLN), kw("not"), (" directives:", C_PLN)],
            [("        ", C_PLN), kw("return"), (" REFUSE        ", C_PLN), ("# no source, no guess", C_COM)],
            [("    prompt = build_apply_prompt(directives)  ", C_PLN), ("# copy-paste", C_COM)],
            [("    log = [FixPacket(d, cite(d)) ", C_PLN), kw("for"), (" d ", C_PLN), kw("in"), (" directives]", C_PLN)],
            [("    ", C_PLN), kw("return"), (" Remediation(prompt, log)   ", C_PLN), ("# each change cited", C_COM)],
        ],
        "console": [
            [("$ ", (79, 70, 229)), ('python -m brain_engine remediate "Surplus Review"', TEXT)],
            [("Reviewer corrections -> ready-to-paste fix prompt:", DIM)],
            [("  1. Change distribution formula to column E, not D", DIM)],
            [("     [Surplus Review - 2025-04-08 - 00:02:11 - Q. Harlow]", FAINT)],
            [("  + 3 more changes, each cited verbatim + timestamp", FAINT)],
            [("  Apply-ready: paste into your AI; each change cited.", GREEN, True)],
        ],
    },
]


if __name__ == "__main__":
    print("Rendering premium system GIFs (2x supersampled):")
    for sys in SYSTEMS:
        render(sys)
    print("Done ->", OUT)
