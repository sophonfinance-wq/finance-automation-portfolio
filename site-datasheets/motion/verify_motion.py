"""Verify a generated engine-tile clip before it is allowed near the site.

Two things go wrong with image-to-video on these tiles, and both have shipped before:

  1. The camera orbits the whole diagram instead of animating anything inside it
     (see 1af78d9). Rotation is measured against a RE-ANCHORED frame -- matching
     every frame to frame 0 collapses its inliers and reads a clean-looking lie.
     Consecutive-pair fits sit under the noise floor and accumulate honestly.

  2. The footer strip is redrawn, so the control/test counts the page cites in
     text no longer match the numbers burned into the artwork (see ff44d03).
     The strip is compared back to the poster it came from, pixel for pixel.
"""
import sys, json
import numpy as np
import cv2

FOOTER_TOP = 0.86      # footer strip band, as a fraction of frame height
ROT_LIMIT = 0.30       # degrees of cumulative bodily rotation we accept
FOOTER_LIMIT = 6.0     # mean abs 0-255 difference in the footer band


def frames(path):
    cap = cv2.VideoCapture(path)
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    cap.release()
    return out


def rotation_track(fr):
    """Cumulative camera rotation in degrees, from consecutive-pair rigid fits."""
    cum, series = 0.0, [0.0]
    for a, b in zip(fr, fr[1:]):
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        p0 = cv2.goodFeaturesToTrack(ga, maxCorners=1200, qualityLevel=0.01,
                                     minDistance=8, blockSize=7)
        if p0 is None or len(p0) < 12:
            series.append(cum)
            continue
        p1, st, _ = cv2.calcOpticalFlowPyrLK(ga, gb, p0, None,
                                             winSize=(21, 21), maxLevel=3)
        if p1 is None:
            series.append(cum)
            continue
        st = st.reshape(-1).astype(bool)
        src, dst = p0.reshape(-1, 2)[st], p1.reshape(-1, 2)[st]
        if len(src) < 12:
            series.append(cum)
            continue
        M, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                           ransacReprojThreshold=2.0)
        if M is not None:
            cum += float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
        series.append(cum)
    return series


def footer_drift(fr, poster):
    """Mean abs difference of the footer band vs the poster, per frame."""
    h, w = fr[0].shape[:2]
    p = cv2.resize(poster, (w, h), interpolation=cv2.INTER_AREA)
    y = int(h * FOOTER_TOP)
    ref = cv2.cvtColor(p[y:], cv2.COLOR_BGR2GRAY).astype(np.float32)
    return [float(np.mean(np.abs(cv2.cvtColor(f[y:], cv2.COLOR_BGR2GRAY).astype(np.float32) - ref)))
            for f in fr]


def motion_energy(fr):
    """Mean abs frame-to-frame change above the footer -- proves it actually moves."""
    h = fr[0].shape[0]
    y = int(h * FOOTER_TOP)
    vals = []
    for a, b in zip(fr, fr[1:]):
        ga = cv2.cvtColor(a[:y], cv2.COLOR_BGR2GRAY).astype(np.float32)
        gb = cv2.cvtColor(b[:y], cv2.COLOR_BGR2GRAY).astype(np.float32)
        vals.append(float(np.mean(np.abs(gb - ga))))
    return vals


def main(video, poster_path):
    fr = frames(video)
    poster = cv2.imread(poster_path, cv2.IMREAD_COLOR)
    if not fr or poster is None:
        print(json.dumps({"error": "unreadable", "video": video}))
        return 2

    rot = rotation_track(fr)
    foot = footer_drift(fr, poster)
    energy = motion_energy(fr)

    rot_span = max(rot) - min(rot)
    foot_max = max(foot)
    report = {
        "video": video,
        "frames": len(fr),
        "size": f"{fr[0].shape[1]}x{fr[0].shape[0]}",
        "rotation_span_deg": round(rot_span, 3),
        "rotation_ok": bool(rot_span <= ROT_LIMIT),
        "footer_drift_max": round(foot_max, 2),
        "footer_ok": bool(foot_max <= FOOTER_LIMIT),
        "motion_energy_mean": round(float(np.mean(energy)), 3),
        "moves": bool(np.mean(energy) > 0.20),
    }
    report["verdict"] = ("PASS" if report["rotation_ok"] and report["footer_ok"]
                         and report["moves"] else "FAIL")
    print(json.dumps(report, indent=1))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
