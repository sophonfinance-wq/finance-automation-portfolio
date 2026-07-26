"""Warp residual camera drift out of a clip that is otherwise good.

Precedent from 1af78d9: cancelling drift by warping is viable at small angles
(it was used at 2.9deg) and useless at large ones (13.4deg needed a 25% crop).
This clip drifts 1.75deg, well inside the viable band.

The transform per frame is built by COMPOSING consecutive-pair fits, not by
matching every frame back to frame 0 -- that direct fit collapses its inliers
and reports a confident wrong answer. Each frame is then warped by the inverse
of its accumulated transform, which puts every frame back in frame 0's
coordinate system, and a small centre crop hides the borders the warp exposes.
"""
import os, subprocess, sys
import cv2, numpy as np, imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
# No crop. Cropping to hide the warp borders would rescale the clip against its
# own poster, and the <video> replaces that poster in place -- a 6% zoom shows up
# as a pop the moment motion takes over. At this drift the exposed border is a
# few px, so it is edge-replicated instead and the framing stays 1:1 with the still.
CROP = 0.0


def to3(M):
    return np.vstack([M, [0, 0, 1]])


def stabilize(src, dst):
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()

    cum = [np.eye(3)]
    for a, b in zip(frames, frames[1:]):
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        p0 = cv2.goodFeaturesToTrack(ga, maxCorners=1500, qualityLevel=0.01,
                                     minDistance=8, blockSize=7)
        M = None
        if p0 is not None and len(p0) >= 12:
            p1, st, _ = cv2.calcOpticalFlowPyrLK(ga, gb, p0, None,
                                                 winSize=(21, 21), maxLevel=3)
            if p1 is not None:
                st = st.reshape(-1).astype(bool)
                src_p, dst_p = p0.reshape(-1, 2)[st], p1.reshape(-1, 2)[st]
                if len(src_p) >= 12:
                    M, _ = cv2.estimateAffinePartial2D(
                        src_p, dst_p, method=cv2.RANSAC, ransacReprojThreshold=2.0)
        cum.append(to3(M) @ cum[-1] if M is not None else cum[-1].copy())

    h, w = frames[0].shape[:2]
    x0, y0 = int(w * CROP), int(h * CROP)
    cw, ch = w - 2 * x0, h - 2 * y0
    out_w, out_h = w, h

    proc = subprocess.Popen(
        [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
         "-preset", "medium", "-an", dst], stdin=subprocess.PIPE)

    for f, C in zip(frames, cum):
        inv = np.linalg.inv(C)[:2, :]
        warped = cv2.warpAffine(f, inv, (w, h), flags=cv2.INTER_LANCZOS4,
                                borderMode=cv2.BORDER_REPLICATE)
        crop = warped[y0:y0 + ch, x0:x0 + cw]
        proc.stdin.write(cv2.resize(crop, (out_w, out_h),
                                    interpolation=cv2.INTER_LANCZOS4).tobytes())
    proc.stdin.close()
    proc.wait()
    print(f"stabilized {os.path.basename(src)} -> {os.path.basename(dst)} "
          f"({len(frames)} frames, crop {CROP:.1%})")


if __name__ == "__main__":
    stabilize(sys.argv[1], sys.argv[2])
