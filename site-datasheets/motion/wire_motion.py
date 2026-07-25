"""Wire an installed clip into the site: spec, footer pins, regenerated page.

Three things have to agree or the datasheet tests fail:
  * specs/<slug>.json media.motion must name the .mp4 (not the poster, which is
    the repo's way of spelling "no motion exists").
  * raster_footers.json must pin the motion file and its digest, because the
    control/test figures are burnt into the animation as well as the poster.
  * docs/engines/<slug>.html must be regenerated so data-video is emitted.
"""
import hashlib, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wire(slug):
    motion_rel = f"engine-{slug}-motion.mp4"
    motion_abs = f"{ROOT}/docs/assets/{motion_rel}"
    if not os.path.exists(motion_abs):
        raise SystemExit(f"{slug}: {motion_rel} not installed")

    # 1. spec
    spec_path = f"{ROOT}/site-datasheets/specs/{slug}.json"
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["media"]["motion"] = f"../assets/{motion_rel}"
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # 2. footer pins
    rf_path = f"{ROOT}/site-datasheets/raster_footers.json"
    with open(rf_path, encoding="utf-8") as fh:
        rf = json.load(fh)
    entry = rf["tiles"][slug]
    entry.setdefault("sha256", {})["motion"] = sha256(motion_abs)
    # rebuild in the order the file already uses: poster, motion, then the rest
    rf["tiles"][slug] = {
        "poster": entry["poster"],
        "motion": motion_rel,
        **{k: v for k, v in entry.items() if k not in ("poster", "motion")},
    }
    with open(rf_path, "w", encoding="utf-8") as fh:
        json.dump(rf, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # 3. regenerate the page
    subprocess.run([sys.executable, "site-datasheets/generate_datasheets.py",
                    "--slug", slug], cwd=ROOT, check=True)

    page = f"{ROOT}/docs/engines/{slug}.html"
    html = open(page, encoding="utf-8").read()
    ok = f'data-video="../assets/{motion_rel}"' in html
    print(f"{slug}: data-video emitted = {ok}")
    return ok


if __name__ == "__main__":
    all_ok = all(wire(s) for s in sys.argv[1:])
    raise SystemExit(0 if all_ok else 1)
