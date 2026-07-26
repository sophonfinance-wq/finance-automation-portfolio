"""Close the loop seam without disturbing frame 0.

Every tile plays with loop=true, so the wrap from last frame to first is visible
on the page every few seconds. Measured across the batch, the seam averaged ~16x
a normal frame-to-frame step, and on some clips 40x.

The obvious fixes both break something here:

  * A cross-dissolve of the tail onto the head makes frame 0 a blend of two
    moments, so it no longer matches the poster it replaces -- trading a jump
    every loop for a pop on every swap.
  * Ping-pong (forward then reversed) is seamless by construction but runs the
    mechanism backwards: sheets feed out of the sorter, the report slides back
    in. Wrong for a machine that is meant to read as working.

So the tail is dissolved toward FRAME 0 itself. The last K frames ease back to
the opening pose, the wrap becomes exact, and frame 0 is untouched, so the poster
handoff is unchanged. On a subtle mechanical loop this reads as the mechanism
settling back to rest rather than as a dissolve. The duplicated final frame is
dropped so the wrap does not stutter.
"""
import os, subprocess, sys
import cv2, numpy as np, imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BLEND_FRACTION = 0.20      # of the clip, eased back to the opening pose
CRF = "30"


def ease(t):
    """Smoothstep, so the settle starts and ends gently."""
    return t * t * (3.0 - 2.0 * t)


def close_loop(src, dst, blend_fraction=BLEND_FRACTION, crf=CRF):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    n = len(frames)
    k = max(2, int(round(n * blend_fraction)))
    first = frames[0].astype(np.float32)

    out = []
    for i, f in enumerate(frames[:-1]):          # drop the duplicate wrap frame
        j = i - (n - 1 - k)
        if j >= 0:
            a = ease(min(1.0, (j + 1) / k))
            f = (f.astype(np.float32) * (1.0 - a) + first * a)
        out.append(np.clip(f, 0, 255).astype(np.uint8))

    h, w = out[0].shape[:2]
    proc = subprocess.Popen(
        [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-crf", crf, "-preset", "slow", "-an",
         "-movflags", "+faststart", dst], stdin=subprocess.PIPE)
    for f in out:
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()
    return len(out)


def seam_ratio(path):
    """Loop discontinuity as a multiple of a normal frame-to-frame step."""
    cap = cv2.VideoCapture(path)
    fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(cv2.cvtColor(cv2.resize(f, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    steps = [float(np.mean(np.abs(b - a))) for a, b in zip(fr, fr[1:])]
    seam = float(np.mean(np.abs(fr[0] - fr[-1])))
    return seam, seam / max(float(np.median(steps)), 1e-6)


if __name__ == "__main__":
    for slug in sys.argv[1:]:
        src = f"{ROOT}/docs/assets/engine-{slug}-motion.mp4"
        tmp = f"{HERE}/loop-{slug}.mp4"
        before = seam_ratio(src)
        close_loop(src, tmp)
        after = seam_ratio(tmp)
        print(f"{slug:<14} seam {before[0]:6.2f} ({before[1]:6.1f}x) -> "
              f"{after[0]:6.2f} ({after[1]:5.1f}x)   {os.path.getsize(tmp)//1024}KB")
