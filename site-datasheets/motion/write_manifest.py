"""Rebuild manifest.json from what actually happened, not from memory.

The previous motion batch (1af78d9) recorded its recipe only in a commit message
and committed no tooling, so this pipeline had to be rebuilt from scratch. Every
job id, prompt, attempt and measured verdict is written back out here so the next
batch starts from evidence. Job ids persist on Higgsfield and re-download by id,
so nothing needs regenerating to reproduce any clip.
"""
import json, os, subprocess, sys
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root
WORK = HERE
sys.path.insert(0, HERE)
import verify_motion, check_footer_text  # noqa: E402

PILOTS = {
    "checkage": {"job_id": "3572abbc-aedf-40e1-98e0-24813ba2b7e1", "attempt": 2,
                 "rejected": ["1c55e34f-7f00-4650-99ca-fce168006161"]},
    "waterfall": {"job_id": "1529c9eb-f8be-4a59-a721-e4bb65839cfa", "attempt": 1,
                  "rejected": []},
}


def measure(slug):
    """Gate numbers come from the SOURCE render, not the shipped file.

    Rotation is measured by accumulating 120 consecutive-pair fits, and that
    accumulation is resolution-dependent: the same clip reads 0.178deg at
    1920x1080 and 1.771deg after a LOSSLESS downscale to 1280x720. Compression is
    not the cause -- the shipped crf-30 file actually reads lower (1.478) than the
    lossless one. It is tracking noise on smaller features doing a random walk. A
    pure resize cannot introduce rotation, so the source is the honest place to
    judge whether the camera moved. Facts about the delivered file (bytes, and the
    handoff to its poster) are recorded from the installed clip.
    """
    clip = f"{WORK}/raw-{slug}.mp4"                 # source render
    installed = f"{ROOT}/docs/assets/engine-{slug}-motion.mp4"
    poster = f"{ROOT}/docs/assets/engine-{slug}.webp"
    if not os.path.exists(installed) or not os.path.exists(clip):
        return None
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        verify_motion.main(clip, poster)
    rep = json.loads(buf.getvalue())
    with contextlib.redirect_stdout(io.StringIO()):
        text_ok = check_footer_text.main(clip, poster) == 0
    cap = cv2.VideoCapture(installed)
    ok, f0 = cap.read()
    cap.release()
    p = cv2.imread(poster)
    import numpy as np
    p = cv2.resize(p, (f0.shape[1], f0.shape[0]), interpolation=cv2.INTER_AREA)
    handoff = float(np.mean(np.abs(p.astype(np.float32) - f0.astype(np.float32))))
    return {"measured_on": "source render 1920x1080",
            "rotation_span_deg": rep["rotation_span_deg"],
            "footer_text_ok": text_ok,
            "shipped_handoff_mean_abs": round(handoff, 2),
            "shipped_bytes": os.path.getsize(installed)}


def main():
    jobs = json.load(open(f"{WORK}/jobs.json"))
    jobs = {**PILOTS, **jobs}
    clips, unresolved = {}, []
    for slug in sorted(jobs):
        m = measure(slug)
        if m is None:
            unresolved.append(slug)
            continue
        e = jobs[slug]
        clips[slug] = {"job_id": e["job_id"], "file": f"engine-{slug}-motion.mp4",
                       "attempt": e.get("attempt", 1),
                       "rejected_job_ids": e.get("rejected", []),
                       "verified": m}
        if "prompt" in e:
            clips[slug]["prompt"] = e["prompt"]

    doc = json.load(open(f"{WORK}/manifest.json"))
    doc["generated"] = "2026-07-25"
    doc["clips"] = clips
    doc["not_animated"] = unresolved
    doc["_why_not_animated"] = (
        "These tiles would not hold a locked-off camera or kept moving their own "
        "caption strip across repeated attempts. They keep their static poster "
        "rather than ship an animation that drifts or occludes a burnt-in figure; "
        "media.motion still equals media.poster for them, which is this repo's way "
        "of spelling 'no motion exists', so the generator emits no data-video."
    ) if unresolved else ""
    doc.pop("remaining", None)
    json.dump(doc, open(f"{WORK}/manifest.json", "w"), indent=2)
    print(f"manifest: {len(clips)} clips recorded, {len(unresolved)} not animated")
    if unresolved:
        print("  not animated:", ", ".join(unresolved))


if __name__ == "__main__":
    main()
