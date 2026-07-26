"""Refit a raw Higgsfield clip to its poster, close its loop, and install it.

Scale, loop-close and encode happen in ONE pass from the 1920x1080 source.
Doing the loop close as a second pass over the already-encoded 720p file costs a
generation of H.264: measured, that alone pushed the poster handoff from ~3.8 to
~6.2 out of 255 with no visible change to the picture.

The scale is taken from the POSTER's aspect, not assumed -- dropping a true 16:9
render onto a 1.79 poster stretches the artwork against its own still (the
mistake 1af78d9 had to undo). These tiles happen to be true 16:9, but the older
ones are not, so the rule stays.
"""
import os, subprocess, sys
import cv2, numpy as np, imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root
TARGET_W = 1280
CRF = "30"
BLEND_FRACTION = 0.20      # tail eased back to the opening pose, to close the loop


def ease(t):
    return t * t * (3.0 - 2.0 * t)


def install(slug, blend_fraction=BLEND_FRACTION):
    raw = f"{HERE}/raw-{slug}.mp4"
    poster_path = f"{ROOT}/docs/assets/engine-{slug}.webp"
    dest = f"{ROOT}/docs/assets/engine-{slug}-motion.mp4"

    p = cv2.imread(poster_path, cv2.IMREAD_COLOR)
    ph, pw = p.shape[:2]
    w = TARGET_W
    h = int(round(w * ph / pw / 2)) * 2       # even height; yuv420p needs it

    # Blend at native resolution and let ffmpeg do the scaling. Measured on one
    # clip: ffmpeg-only 3.69 handoff, python-decode + ffmpeg-scale 4.91, and
    # python-decode + cv2-resize 5.99 -- the decode round-trip and the cv2 resize
    # each cost about a point. Blending needs pixel access, so the decode is
    # unavoidable, but the resize is not. (Doing the blend as an ffmpeg blend=
    # expression keeps it all in YUV and scores 3.69, but it evaluates per pixel
    # per frame and is far too slow to run across a batch.)
    cap = cv2.VideoCapture(raw)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    src_h, src_w = frames[0].shape[:2]

    n = len(frames)
    k = max(2, int(round(n * blend_fraction)))
    first = frames[0].astype(np.float32)

    proc = subprocess.Popen(
        [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{src_w}x{src_h}", "-r", str(fps), "-i", "-",
         "-vf", f"scale={w}:{h}:flags=lanczos",
         "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-crf", CRF, "-preset", "slow", "-an",
         "-movflags", "+faststart", dest], stdin=subprocess.PIPE)

    for i, f in enumerate(frames[:-1]):        # drop the duplicated wrap frame
        j = i - (n - 1 - k)
        if j >= 0:
            a = ease(min(1.0, (j + 1) / k))
            f = np.clip(f.astype(np.float32) * (1.0 - a) + first * a, 0, 255).astype(np.uint8)
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()

    print(f"{slug}: poster {pw}x{ph} (ar {pw/ph:.3f}) -> clip {w}x{h} "
          f"(ar {w/h:.3f}), {n - 1} frames, {os.path.getsize(dest)//1024}KB")
    return dest


if __name__ == "__main__":
    for s in sys.argv[1:]:
        install(s)
