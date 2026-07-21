#!/usr/bin/env python3
"""Compose the homepage "why" film from fetched assets + site footage.

Usage: python compose.py [--voice sloane|arthur] [--install]
  --install copies why-film.mp4/.vtt/-poster.jpg into docs/assets.

Deterministic given the same inputs; every stat overlay carries its source.
Deps: pillow, imageio-ffmpeg (any Python >= 3.10).
"""
import argparse
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ASSETS = REPO / "docs" / "assets"
WORK = HERE / "work"
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1280, 720, 30
TAIL = 0.9
WHITE = (255, 255, 255, 255)
BLUE = (92, 157, 255, 255)        # site blue lifted for legibility on footage
BLUE_DEEP = (15, 98, 254, 255)    # exact site blue (glyph dot)
MONO_SOFT = (255, 255, 255, 200)
ORDER = ["open", "days", "reopen", "people", "turn", "engines", "speed", "close"]

HN = "/System/Library/Fonts/HelveticaNeue.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"


def _face(path, want):
    for i in range(18):
        try:
            f = ImageFont.truetype(path, 20, index=i)
        except OSError:
            break
        if f.getname()[1].lower() == want.lower():
            return i
    return 0


IB, IM, IL = _face(HN, "Bold"), _face(HN, "Medium"), _face(HN, "Light")


def F(s, f="bold"):
    return ImageFont.truetype(HN, s, index={"bold": IB, "med": IM, "light": IL}[f])


def M(s):
    return ImageFont.truetype(MENLO, s, index=0)


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.20158, 2.20158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def stext(img, xy, text, font, fill, blur=7, off=(0, 4), salpha=185):
    """Transparent overlay text: soft shadow + crisp face, no background card."""
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + off[0], xy[1] + off[1]), text, font=font,
                            fill=(0, 0, 0, salpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(img).text(xy, text, font=font, fill=fill)


def ctext(img, cx, y, text, font, fill, **kw):
    w = ImageDraw.Draw(img).textlength(text, font=font)
    stext(img, (cx - w / 2, y), text, font, fill, **kw)


def scrim(img, box, alpha=95):
    x0, y0, x1, y1 = box
    g = Image.new("RGBA", (x1 - x0, y1 - y0), (8, 14, 30, alpha))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)), (x0, y0))


def logo(img, t=1.0):
    """Site brand mark + wordmark, top-left."""
    a = int(235 * min(1.0, t * 3))
    ox, oy, s = 46, 38, 1.05
    pts = [(ox + p[0] * s, oy + p[1] * s) for p in [(10, 30), (19, 21), (27, 26), (38, 14)]]
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).line(pts, fill=(0, 0, 0, 150), width=4, joint="curve")
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(img)
    d.line(pts, fill=(255, 255, 255, a), width=4, joint="curve")
    dot = (ox + 38 * s, oy + 14 * s)
    d.ellipse([dot[0] - 4, dot[1] - 4, dot[0] + 4, dot[1] + 4], fill=(*BLUE_DEEP[:3], a))
    d.rectangle([ox + 10 * s, oy + 35 * s, ox + 38 * s, oy + 38 * s], fill=(255, 255, 255, a))
    stext(img, (ox + 52, oy + 12), "SOPHON FINANCE SYSTEMS", M(15), (255, 255, 255, a),
          blur=4, off=(0, 2), salpha=130)


def slide(final_x, t, from_right=True, dist=380):
    k = ease_back(t)
    return final_x + (dist * (1 - k) if from_right else -dist * (1 - k))


def ov_open(img, t):
    pass


def ov_days(img, t):
    ts = (t - 0.14) / 0.3
    if ts <= 0:
        return
    x = slide(715, ts, True)
    scrim(img, (int(x) - 30, 140, 1270, 470))
    stext(img, (x, 160), "6.4", F(150), WHITE)
    stext(img, (x + 290, 240), "DAYS", F(54), BLUE)
    stext(img, (x, 330), "the median monthly close —", F(30, "med"), WHITE)
    stext(img, (x, 370), "barely moved in 15 years", F(30, "med"), WHITE)
    stext(img, (x, 424), "APQC benchmark · Ventana/ISG", M(16), MONO_SOFT, blur=4, off=(0, 2))


def ov_reopen(img, t):
    ts = (t - 0.14) / 0.3
    if ts <= 0:
        return
    x = slide(64, ts, False)
    scrim(img, (int(x) - 30, 150, int(x) + 560, 480))
    stext(img, (x, 168), "75%", F(150), WHITE)
    stext(img, (x, 340), "have reopened the books", F(32, "med"), BLUE)
    stext(img, (x, 382), "to fix an error found after close", F(28, "med"), WHITE)
    stext(img, (x, 432), "FloQast / Dimensional Research", M(16), MONO_SOFT, blur=4, off=(0, 2))


def ov_people(img, t):
    t1 = (t - 0.1) / 0.28
    if t1 > 0:
        x = slide(64, t1, False)
        scrim(img, (int(x) - 26, 120, int(x) + 440, 330))
        stext(img, (x, 138), "99%", F(104), WHITE)
        stext(img, (x, 258), "report burnout", F(29, "med"), BLUE)
        stext(img, (x, 296), "FloQast / Univ. of Georgia", M(15), MONO_SOFT, blur=4, off=(0, 2))
    t2 = (t - 0.42) / 0.28
    if t2 > 0:
        x = slide(740, t2, True)
        scrim(img, (int(x) - 26, 380, 1270, 600))
        stext(img, (x, 398), "300,000", F(96), WHITE)
        stext(img, (x, 510), "walked away in two years", F(28, "med"), BLUE)
        stext(img, (x, 548), "WSJ / Bureau of Labor Statistics", M(15), MONO_SOFT, blur=4, off=(0, 2))


def ov_turn(img, t):
    a = ease_out((t - 0.05) / 0.3)
    img.alpha_composite(Image.new("RGBA", img.size, (8, 14, 30, int(140 * a))))
    a1 = ease_out((t - 0.1) / 0.3)
    ctext(img, W / 2, 268, "IT ISN'T THE PEOPLE.", F(64, "light"),
          (255, 255, 255, int(255 * a1)))
    a2 = ease_out((t - 0.35) / 0.35)
    ctext(img, W / 2, 356, "IT'S THE WORK.", F(100), (*BLUE[:3], int(255 * a2)))


def ov_engines(img, t):
    words = [("DRAFT", WHITE), ("VERIFY", BLUE), ("APPROVE", WHITE)]
    if (t - 0.15) / 0.2 > 0:
        scrim(img, (150, 560, 1130, 680), alpha=110)
    x = 235
    for i, (w_, col) in enumerate(words):
        ts = (t - (0.15 + i * 0.2)) / 0.2
        if ts > 0:
            k = ease_back(ts)
            y = 582 + (1 - k) * 120
            stext(img, (x, int(y)), w_, F(52), col)
        x += ImageDraw.Draw(img).textlength(w_, font=F(52)) + 26
        if i < 2:
            ts2 = (t - (0.27 + i * 0.2)) / 0.15
            if ts2 > 0:
                a = int(255 * ease_out(ts2))
                ay = 618
                sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(sh).line([(x + 4, ay), (x + 44, ay)], fill=(0, 0, 0, 150), width=6)
                img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
                d3 = ImageDraw.Draw(img)
                d3.line([(x + 4, ay), (x + 44, ay)], fill=(255, 255, 255, a), width=6)
                d3.polygon([(x + 58, ay), (x + 40, ay - 11), (x + 40, ay + 11)],
                           fill=(255, 255, 255, a))
            x += 76


def ov_speed(img, t):
    ts = (t - 0.3) / 0.3
    if ts <= 0:
        return
    x = slide(700, ts, True)
    scrim(img, (int(x) - 30, 150, 1270, 490))
    stext(img, (x, 172), "0.15", F(150), WHITE)
    stext(img, (x + 350, 252), "SEC", F(54), BLUE)
    stext(img, (x, 342), "our demo close, end to end —", F(29, "med"), WHITE)
    stext(img, (x, 380), "checked on every single run", F(29, "med"), BLUE)
    stext(img, (x, 434), "measured 2026-07-20 · time python -m close_engine", M(15),
          MONO_SOFT, blur=4, off=(0, 2))


def tracked(img, cx, y, text, font, fill, tracking):
    d = ImageDraw.Draw(img)
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def ov_close(img, t):
    if t < 0.62:
        # Over the welcome handshake: the two taglines.
        if t < 0.40:
            return
        a1 = ease_out((t - 0.42) / 0.2)
        ctext(img, W / 2, 496, "AUTOMATE THE WORK.", F(58), (255, 255, 255, int(255 * a1)))
        a2 = ease_out((t - 0.52) / 0.2)
        ctext(img, W / 2, 566, "KEEP THE JUDGMENT.", F(58), (*BLUE[:3], int(255 * a2)))
        return
    # Endcard: the exact brand lockup, drawn vector-crisp over the generated
    # background plate — never AI-rendered typography.
    k = (t - 0.62) / 0.38
    d = ImageDraw.Draw(img)
    a_g = int(255 * ease_out(k / 0.35))
    if a_g > 0:
        s = 3.2
        ox, oy = W / 2 - 24 * s, 138
        pts = [(ox + p[0] * s, oy + p[1] * s) for p in [(10, 30), (19, 21), (27, 26), (38, 14)]]
        d.line(pts, fill=(255, 255, 255, a_g), width=10, joint="curve")
        dot = (ox + 38 * s, oy + 14 * s)
        d.ellipse([dot[0] - 10, dot[1] - 10, dot[0] + 10, dot[1] + 10],
                  fill=(*BLUE_DEEP[:3], a_g))
        d.rectangle([ox + 10 * s, oy + 35 * s, ox + 38 * s, oy + 38 * s],
                    fill=(255, 255, 255, a_g))
    a_w = int(255 * ease_out((k - 0.18) / 0.3))
    if a_w > 0:
        tracked(img, W / 2, 296, "SOPHON", F(118), (255, 255, 255, a_w), 30)
    a_r = ease_out((k - 0.34) / 0.25)
    if a_r > 0:
        half = 185 * a_r
        d.rectangle([W / 2 - half, 446, W / 2 + half, 451], fill=(*BLUE_DEEP[:3], 255))
    a_f = int(255 * ease_out((k - 0.42) / 0.25))
    if a_f > 0:
        tracked(img, W / 2, 470, "FINANCE SYSTEMS", M(26), (200, 216, 245, a_f), 14)
    a_t = int(255 * ease_out((k - 0.55) / 0.3))
    if a_t > 0:
        ctext(img, W / 2, 546, "AUTOMATE THE WORK.", F(34, "med"),
              (255, 255, 255, a_t), blur=0, off=(0, 0), salpha=0)
        ctext(img, W / 2, 592, "KEEP THE JUDGMENT.", F(34, "med"),
              (*BLUE[:3], a_t), blur=0, off=(0, 0), salpha=0)
    a_u = int(220 * ease_out((k - 0.7) / 0.28))
    if a_u > 0:
        tracked(img, W / 2, 658, "sophonfinance.com", M(19), (160, 178, 210, a_u), 3)


OVERLAYS = {"open": ov_open, "days": ov_days, "reopen": ov_reopen, "people": ov_people,
            "turn": ov_turn, "engines": ov_engines, "speed": ov_speed, "close": ov_close}

# beat -> ordered shots (path, start_s, share of beat). The founder appears at his
# desk (engines), leading the boardroom (engines), and welcoming clients (close).
SHOTS = {
    "open":    [(ASSETS / "hero-web.mp4", 0.4, 0.35), (WORK / "hf_night.mp4", 0.2, 0.65)],
    "days":    [(WORK / "hf_meeting.mp4", 0.2, 1.0)],
    "reopen":  [(WORK / "hf_reopen.mp4", 0.2, 0.55), (ASSETS / "hero-web.mp4", 12.2, 0.45)],
    "people":  [(WORK / "hf_team.mp4", 0.2, 1.0)],
    "turn":    [(WORK / "hf_turn.mp4", 0.2, 1.0)],
    "engines": [(WORK / "hf_founder1.mp4", 0.2, 0.50), (WORK / "hf_fmeet.mp4", 0.2, 0.50)],
    "speed":   [(ASSETS / "hero2-web.mp4", 6.2, 0.28), (ASSETS / "hero2-web.mp4", 21.1, 0.24), (ASSETS / "hero2-web.mp4", 24.2, 0.48)],
    "close":   [(WORK / "hf_sign.mp4", 0.2, 0.28), (WORK / "hf_welcome.mp4", 0.2, 0.34), (WORK / "hf_endcard.mp4", 0.2, 0.38)],
}

CAPTIONS = {
    "open": "Every month, the books have to close. And every month, good people give up their nights to get there.",
    "days": "The close takes 6.4 days — and in fifteen years, that number has barely moved.",
    "reopen": "Three out of four accountants have had to reopen the books to fix an error found after close.",
    "people": "99% report burnout. 300,000 have walked away.",
    "turn": "It isn't the people. It's the work.",
    "engines": "So we built engines that absorb the mechanical month: drafting, tying out, citing every figure to its source.",
    "speed": "Our public demo close runs in 0.15 seconds — checked, on every single run, by a verifier that never gets tired.",
    "close": "Machines do the work. Your people keep the judgment. Sophon Finance Systems.",
}


def dur_of(p):
    out = subprocess.run([FF, "-i", str(p)], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def extract(durs):
    raw = WORK / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir()
    for bid in ORDER:
        beat_dur = durs[bid] + TAIL
        for si, (src, t0, share) in enumerate(SHOTS[bid]):
            outdir = raw / f"{bid}_{si}"
            outdir.mkdir()
            subprocess.run([
                FF, "-y", "-ss", f"{t0:.2f}", "-t", f"{beat_dur * share + 0.3:.2f}",
                "-i", str(src),
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
                "-q:v", "2", str(outdir / "f%04d.png")], check=True, capture_output=True)
    return raw


def compose(raw, durs):
    frames = WORK / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    n = 0
    for bi, bid in enumerate(ORDER):
        beat_dur = durs[bid] + TAIL
        steps = int(round(beat_dur * FPS))
        bounds = []
        acc = 0.0
        for _src, _t0, share in SHOTS[bid]:
            bounds.append((acc, acc + share))
            acc += share
        for i in range(steps):
            t = i / max(1, steps - 1)
            si = 0
            for k, (a, b) in enumerate(bounds):
                if t >= a:
                    si = k
            a, b = bounds[si]
            local = (t - a) / (b - a)
            shot_frames = sorted((raw / f"{bid}_{si}").glob("f*.png"))
            fi = min(len(shot_frames) - 1, int(local * (b - a) * beat_dur * FPS))
            img = Image.open(shot_frames[fi]).convert("RGBA")
            OVERLAYS[bid](img, t)
            if not (bid == "close" and si == 2):
                logo(img, 1.0 if (bi, i) != (0, 0) else 0.4)
            if bi == 0 and i < 12:
                img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - i / 12)))))
            img.convert("RGB").save(frames / f"f{n:05d}.jpg", quality=90)
            n += 1
    print("frames:", n)
    return frames


def mux(frames, durs, voice):
    total = sum(durs[b] + TAIL for b in ORDER)
    gap = WORK / "gap.wav"
    subprocess.run([FF, "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={TAIL}",
                    str(gap)], check=True, capture_output=True)
    lst = WORK / "vo_list.txt"
    with open(lst, "w") as fh:
        for b in ORDER:
            wav = WORK / f"vo_{b}.wav"
            subprocess.run([FF, "-y", "-i", str(WORK / f"vo_{voice}_{b}.mp3"),
                            "-ar", "44100", "-ac", "1", str(wav)], check=True, capture_output=True)
            fh.write(f"file 'vo_{b}.wav'\nfile 'gap.wav'\n")
    vo_all = WORK / "vo_all.wav"
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-ar", "44100", str(vo_all)], check=True, capture_output=True)
    out = WORK / "why-film.mp4"
    subprocess.run([
        FF, "-y", "-framerate", str(FPS), "-i", str(frames / "f%05d.jpg"),
        "-i", str(vo_all), "-i", str(ASSETS / "site-music.mp3"),
        "-filter_complex",
        f"[2:a]volume=0.14,afade=t=in:d=2,afade=t=out:st={total-3:.2f}:d=3,atrim=0:{total:.2f}[m];"
        f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=3,loudnorm=I=-16:TP=-1.5[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True)
    print("film ->", out, out.stat().st_size // 1024, "KB, total", round(total, 1), "s")

    def ts(x):
        mm = int(x // 60)
        return f"{mm:02d}:{x - mm * 60:06.3f}"
    pos = 0.0
    with open(WORK / "why-film.vtt", "w") as fh:
        fh.write("WEBVTT\n\n")
        for b in ORDER:
            d = durs[b] + TAIL
            fh.write(f"{ts(pos)} --> {ts(pos + d - 0.2)}\n{CAPTIONS[b]}\n\n")
            pos += d

    poster_src = sorted((WORK / "frames").glob("f*.jpg"))
    idx = int(round((durs["open"] + TAIL) * FPS + (durs["days"] + TAIL) * FPS * 0.6))
    subprocess.run([FF, "-y", "-i", str(poster_src[min(idx, len(poster_src) - 1)]),
                    "-qscale:v", "3", str(WORK / "why-film-poster.jpg")],
                   check=True, capture_output=True)
    print("captions + poster ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="sloane", choices=["sloane", "arthur"])
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()
    durs = {b: dur_of(WORK / f"vo_{args.voice}_{b}.mp3") for b in ORDER}
    print("vo durations:", {k: round(v, 2) for k, v in durs.items()})
    frames = compose(extract(durs), durs)
    mux(frames, durs, args.voice)
    if args.install:
        for f in ["why-film.mp4", "why-film.vtt", "why-film-poster.jpg"]:
            shutil.copy(WORK / f, ASSETS / f)
        print("installed into docs/assets")


if __name__ == "__main__":
    main()
