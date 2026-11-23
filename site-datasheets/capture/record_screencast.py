#!/usr/bin/env python
"""Capture and render the real Triangulate adversarial CLI demo.

The engine command is the source of every frame.  The script writes a UTF-8
transcript, a WebP poster, two evidence crops, and a silent H.264 MP4 loop.
Pillow and imageio-ffmpeg are capture-time tools only; the datasheet generator
and the public engine remain stdlib-only apart from the repository requirements.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "ai-validation-framework"
OUT = Path(__file__).resolve().parent / "out"
ASSETS = ROOT / "docs" / "assets"

WIDTH = 1280
HEIGHT = 720
FPS = 12
COMMAND = "python -m triangulate --demo-adversarial --no-artifacts"


def _capture() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "triangulate", "--demo-adversarial", "--no-artifacts"],
        cwd=str(ENGINE), capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 1:
        detail = proc.stdout + proc.stderr
        raise RuntimeError(
            f"adversarial demo must exit 1 (FAIL); got {proc.returncode}\n{detail}"
        )
    transcript = (proc.stdout + proc.stderr).replace("\r\n", "\n").replace("\r", "\n")
    # --no-artifacts should keep machine paths out of the public evidence.
    if str(ROOT).lower() in transcript.lower() or str(Path.home()).lower() in transcript.lower():
        raise RuntimeError("capture contains a machine-specific path")
    return transcript


def _font(ImageFont, size: int, bold: bool = False):
    names = [
        Path("C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]
    for path in names:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _terminal_lines(transcript: str) -> list[str]:
    lines = ["$ " + COMMAND, ""]
    for raw in transcript.splitlines():
        wrapped = textwrap.wrap(raw, width=104, replace_whitespace=False,
                                drop_whitespace=False) or [""]
        lines.extend(line.rstrip() for line in wrapped)
    return lines


def _line_colour(line: str) -> str:
    if line.startswith("$"):
        return "#7ee787"
    if "VERDICT: FAIL" in line or "[Critical]" in line:
        return "#ff7b72"
    if "Critical=" in line or "Fix Packet" in line:
        return "#e3b341"
    if "HumanGate(automated-policy)" in line:
        return "#79c0ff"
    if line and set(line) <= {"-", "="}:
        return "#484f58"
    return "#c9d1d9"


def _render_window(Image, ImageDraw, ImageFont, lines: list[str], start: int,
                   *, width: int = WIDTH, height: int = HEIGHT,
                   title: str = "TRIANGULATE · REAL CLI · FICTIONAL SEEDED DATA"):
    image = Image.new("RGB", (width, height), "#0d1117")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 58), fill="#161b22")
    for i, colour in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        x = 24 + i * 24
        draw.ellipse((x, 22, x + 12, 34), fill=colour)
    title_font = _font(ImageFont, 18, bold=True)
    body_font = _font(ImageFont, 19)
    draw.text((118, 18), title, font=title_font, fill="#f0f6fc")
    line_h = 26
    capacity = max(1, (height - 94) // line_h)
    visible = lines[start:start + capacity]
    y = 76
    for line in visible:
        draw.text((28, y), line, font=body_font, fill=_line_colour(line))
        y += line_h
    draw.text((width - 282, height - 24), "source: public repo · seed 20240101",
              font=_font(ImageFont, 12), fill="#8b949e")
    return image


def _section(lines: list[str], needle: str, before: int, count: int) -> list[str]:
    index = next(i for i, line in enumerate(lines) if needle in line)
    start = max(0, index - before)
    return lines[start:start + count]


def _encode_assets(transcript: str) -> None:
    try:
        import imageio_ffmpeg
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - capture workstation dependency
        raise RuntimeError("capture requires Pillow and imageio-ffmpeg") from exc

    ASSETS.mkdir(parents=True, exist_ok=True)
    lines = _terminal_lines(transcript)

    poster = _render_window(Image, ImageDraw, ImageFont, lines, 0)
    poster.save(ASSETS / "triangulate-cli.webp", "WEBP", quality=88, method=6)

    verdict_lines = _section(lines, "VERDICT: FAIL", before=5, count=13)
    verdict = _render_window(
        Image, ImageDraw, ImageFont, verdict_lines, 0, width=1120, height=430,
        title="TRIANGULATE · VERDICT EVIDENCE",
    )
    verdict.save(ASSETS / "triangulate-cli-verdict.webp", "WEBP", quality=90, method=6)

    fix_lines = _section(lines, "Fix Packet", before=1, count=15)
    fix = _render_window(
        Image, ImageDraw, ImageFont, fix_lines, 0, width=1120, height=500,
        title="TRIANGULATE · FIX PACKET EVIDENCE",
    )
    fix.save(ASSETS / "triangulate-cli-fix-packet.webp", "WEBP", quality=90, method=6)

    capacity = (HEIGHT - 94) // 26
    max_start = max(0, len(lines) - capacity)
    frame_count = FPS * 14
    hold = FPS * 2
    writer = imageio_ffmpeg.write_frames(
        str(ASSETS / "triangulate-cli.mp4"), (WIDTH, HEIGHT), fps=FPS,
        codec="libx264", quality=7, pix_fmt_out="yuv420p",
        ffmpeg_log_level="error", output_params=["-movflags", "+faststart"],
    )
    writer.send(None)
    try:
        for frame_no in range(frame_count):
            if frame_no < hold:
                start = 0
            elif frame_no >= frame_count - hold:
                start = max_start
            else:
                progress = (frame_no - hold) / max(1, frame_count - 2 * hold - 1)
                start = round(max_start * progress)
            frame = _render_window(Image, ImageDraw, ImageFont, lines, start)
            writer.send(frame.tobytes())
    finally:
        writer.close()


def main() -> int:
    transcript = _capture()
    OUT.mkdir(parents=True, exist_ok=True)
    transcript_path = OUT / "triangulate-demo.txt"
    transcript_path.write_bytes(transcript.encode("utf-8"))
    _encode_assets(transcript)
    outputs = [
        transcript_path,
        ASSETS / "triangulate-cli.webp",
        ASSETS / "triangulate-cli.mp4",
        ASSETS / "triangulate-cli-verdict.webp",
        ASSETS / "triangulate-cli-fix-packet.webp",
    ]
    for path in outputs:
        print(f"captured {path.stat().st_size} bytes -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
