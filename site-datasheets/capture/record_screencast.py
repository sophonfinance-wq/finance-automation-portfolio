#!/usr/bin/env python
"""Capture the Triangulate CLI run for the datasheet 'See it run' zone.

Runs `python -m triangulate --demo-adversarial` in the engine directory and
writes the terminal transcript to capture/out/triangulate-demo.txt. Encoding
that transcript into a webp poster + mp4 loop is a manual/vendor step (the page
ships with the existing assets/tile-triangulate.* pair until a capture is made).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "ai-validation-framework"
OUT = Path(__file__).resolve().parent / "out"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "triangulate", "--demo-adversarial"],
        cwd=str(ENGINE), capture_output=True, text=True, timeout=180,
    )
    transcript = OUT / "triangulate-demo.txt"
    transcript.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    print("captured %d bytes -> %s (exit %d)"
          % (transcript.stat().st_size, transcript, proc.returncode))
    print("To encode a poster+loop, hand the transcript to the video/CAD vendor,")
    print("or render with asciinema + agg if available:")
    print("  asciinema rec --command 'python -m triangulate --demo-adversarial' demo.cast")
    print("  agg demo.cast triangulate-demo.gif   # then encode gif -> mp4/webp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
