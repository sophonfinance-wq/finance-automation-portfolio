"""Refit a raw Higgsfield clip to its poster and install it as an engine tile clip.

Matches the encoding the existing tile clips already use: ~1280 wide, 30 fps,
silent, faststart, h264/yuv420p. The scale is taken from the POSTER's aspect,
not assumed -- dropping a true 16:9 render onto a 1.79 poster stretches the
artwork against its own still (the mistake 1af78d9 had to undo).
"""
import os, subprocess, sys
import cv2, imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root
TARGET_W = 1280
CRF = "30"


def install(slug):
    raw = f"{HERE}/raw-{slug}.mp4"
    poster = f"{ROOT}/docs/assets/engine-{slug}.webp"
    dest = f"{ROOT}/docs/assets/engine-{slug}-motion.mp4"

    p = cv2.imread(poster, cv2.IMREAD_COLOR)
    ph, pw = p.shape[:2]
    # even dimensions only -- yuv420p cannot encode an odd height
    w = TARGET_W
    h = int(round(w * ph / pw / 2)) * 2
    cmd = [FF, "-y", "-loglevel", "error", "-i", raw,
           "-vf", f"scale={w}:{h}:flags=lanczos,fps=30",
           "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-crf", CRF, "-preset", "slow", "-an",
           "-movflags", "+faststart", dest]
    subprocess.run(cmd, check=True)
    print(f"{slug}: poster {pw}x{ph} (ar {pw/ph:.3f}) -> clip {w}x{h} "
          f"(ar {w/h:.3f}), {os.path.getsize(dest)//1024}KB")
    return dest


if __name__ == "__main__":
    for s in sys.argv[1:]:
        install(s)
