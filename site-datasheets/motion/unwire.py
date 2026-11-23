"""Revert a tile to its static poster.

The default when a clip cannot be made good must be "no motion", never "ship the
best bad take". This sets media.motion back to media.poster -- this repo's way of
spelling "no motion exists", which makes the generator withhold data-video -- drops
the motion pin from raster_footers.json, removes the clip, and relabels the
section so the page stops promising "brand animation" it does not have.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root
STATIC_LABEL = "engine tile"


def unwire(slug):
    spec_path = f"{ROOT}/site-datasheets/specs/{slug}.json"
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["media"]["motion"] = spec["media"]["poster"]
    spec["media"]["run_label"] = STATIC_LABEL
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    rf_path = f"{ROOT}/site-datasheets/raster_footers.json"
    with open(rf_path, encoding="utf-8") as fh:
        rf = json.load(fh)
    entry = rf["tiles"].get(slug)
    if entry:
        entry.pop("motion", None)
        entry.get("sha256", {}).pop("motion", None)
        with open(rf_path, "w", encoding="utf-8") as fh:
            json.dump(rf, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    clip = f"{ROOT}/docs/assets/engine-{slug}-motion.mp4"
    if os.path.exists(clip):
        os.remove(clip)

    subprocess.run([sys.executable, "site-datasheets/generate_datasheets.py",
                    "--slug", slug], cwd=ROOT, check=True)
    html = open(f"{ROOT}/docs/engines/{slug}.html", encoding="utf-8").read()
    still_wired = 'data-video="' in html
    print(f"{slug}: reverted to static, data-video present = {still_wired}")
    return not still_wired


if __name__ == "__main__":
    ok = all(unwire(s) for s in sys.argv[1:])
    raise SystemExit(0 if ok else 1)
