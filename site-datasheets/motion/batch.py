"""Generate, verify and wire the remaining engine-tile motion clips.

Subcommands:
  prompts            print the derived prompt for each slug (no spend)
  submit [slugs...]  create Higgsfield jobs, record ids in jobs.json
  poll               poll every recorded job, download completed results
  verify             run the gates over downloaded clips, write verdicts.json
  install [slugs...] refit + install + wire the clips that passed

The prompt is the attempt-2 checkage wording, which is what moved that clip from
1.75deg of drift to 0.20deg: it names the rigid parts explicitly and forbids
tilting or re-lettering the caption strip. Only the mechanism sentence changes
per tile, and that is taken from the tile's own poster_alt so the motion
describes the artwork that is actually there.
"""
import json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # repo root
WORK = HERE
HF = os.path.expanduser("~/.local/bin/higgsfield")
JOBS = f"{WORK}/jobs.json"

REMAINING = ["bond", "capitalize", "closing", "coi", "contingency", "deposit",
             "depreciation", "energy", "expense", "filing", "financing",
             "franchise", "gaalloc", "grt", "inforeturn", "insurance",
             "interest", "labor", "lien", "payroll", "pickup", "proforma",
             "proptax", "sizing", "sov", "spending", "standing", "unitsales",
             "variance", "wire", "withholding"]

TEMPLATE = (
    "Treat the input as a locked-off studio photograph on a tripod. The camera is "
    "completely static: no orbit, no rotation, no pan, no tilt, no roll, no zoom, "
    "no push-in, no dolly, no parallax, no perspective change, no lens change. The "
    "machine body, the surface it rests on, the horizon line and the caption strip "
    "along the bottom edge are RIGID and must stay pixel-locked in exactly their "
    "original position, scale and angle for every frame. The bottom caption strip "
    "must remain perfectly horizontal and perfectly still; do not tilt, slide, skew, "
    "redraw or re-letter it. Animate ONLY small parts inside the open cutaway: the "
    "stack of pale workpapers at the left feeds forward one sheet at a time, {mech}, "
    "and the bound report at the right slides gently outward onto its tray. The round "
    "gauge needle sweeps slightly. Everything else in the frame is frozen. Subtle, "
    "restrained, precise mechanical motion, evenly paced for a seamless loop. "
    "Lighting, colour, matte cream background and metal finish unchanged. No people, "
    "no hands, no new objects, no text changes."
)


def mechanism(slug):
    spec = json.load(open(f"{ROOT}/site-datasheets/specs/{slug}.json", encoding="utf-8"))
    alt = spec["media"]["poster_alt"]
    m = re.search(r"inside,\s*(.*?)\.\s*A footer strip", alt, re.S)
    if not m:
        raise SystemExit(f"{slug}: could not read mechanism from poster_alt")
    mech = " ".join(m.group(1).split())
    # The alt text is written for screen readers, not for a video prompt: some
    # entries shout the mechanism in caps and several re-state "in the cutaway",
    # which the template already says. Both confuse the generator.
    mech = re.sub(r"\b([A-Z]{2,})\b", lambda w: w.group(1).lower(), mech)
    mech = re.sub(r"\s*(as the heart of|at the heart of)\s+the cutaway", "", mech, flags=re.I)
    mech = re.sub(r"\s*(inside|in|within)\s+the cutaway", "", mech, flags=re.I)
    mech = re.sub(r"^(a|an|the)\s+", "", mech, flags=re.I).strip(" ,;")
    # Some alts run 600 chars and are themselves truncated mid-clause in the repo.
    # The prompt only needs to name what moves; piling on station-by-station detail
    # invites the generator to re-draw the machinery rather than animate it.
    mech = re.split(r"\s*[:(]\s*", mech, maxsplit=1)[0]
    if len(mech) > 160:
        mech = mech[:160].rsplit(" ", 1)[0]
    mech = mech.strip(" ,;.—-")
    mech = re.sub(r"\s+(and|or|but|so|that|which|with|as|each|the)$", "", mech).strip(" ,;.—-")
    return f"inside the cutaway the {mech} works steadily through one slow cycle"


def prompt_for(slug):
    return TEMPLATE.format(mech=mechanism(slug))


def load_jobs():
    return json.load(open(JOBS)) if os.path.exists(JOBS) else {}


def save_jobs(j):
    json.dump(j, open(JOBS, "w"), indent=2)


def poster_png(slug):
    import imageio_ffmpeg
    png = f"{WORK}/engine-{slug}.png"
    if not os.path.exists(png):
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-i", f"{ROOT}/docs/assets/engine-{slug}.webp", png], check=True)
    return png


def submit(slugs):
    jobs = load_jobs()
    for slug in slugs:
        if jobs.get(slug, {}).get("job_id"):
            print(f"{slug}: already submitted ({jobs[slug]['job_id']})")
            continue
        p = prompt_for(slug)
        r = subprocess.run([HF, "generate", "create", "kling3_0", "--prompt", p,
                            "--start-image", poster_png(slug), "--mode", "pro",
                            "--duration", "5", "--aspect_ratio", "16:9",
                            "--sound", "off", "--json"],
                           capture_output=True, text=True)
        try:
            ids = json.loads(r.stdout)
            job_id = ids[0] if isinstance(ids, list) else ids.get("id")
        except Exception:
            print(f"{slug}: UNPARSED -> {r.stdout[:200]} {r.stderr[:200]}")
            continue
        jobs[slug] = {"job_id": job_id, "attempt": jobs.get(slug, {}).get("attempt", 0) + 1,
                      "prompt": p}
        save_jobs(jobs)
        print(f"{slug}: {job_id}")
        time.sleep(2)


def poll():
    jobs = load_jobs()
    pending = [s for s, d in jobs.items()
               if not os.path.exists(f"{WORK}/raw-{s}.mp4")]
    for attempt in range(1, 241):
        for slug in list(pending):
            r = subprocess.run([HF, "generate", "get", jobs[slug]["job_id"], "--json"],
                               capture_output=True, text=True)
            try:
                d = json.loads(r.stdout)
            except Exception:
                continue
            st = d.get("status", "?")
            if st == "completed":
                urllib.request.urlretrieve(d.get("result_url"), f"{WORK}/raw-{slug}.mp4")
                print(f"[{attempt}] {slug} downloaded", flush=True)
                pending.remove(slug)
            elif st in ("failed", "canceled", "error"):
                print(f"[{attempt}] {slug} {st}", flush=True)
                jobs[slug]["failed"] = True
                save_jobs(jobs)
                pending.remove(slug)
        if not pending:
            print("ALL DOWNLOADED", flush=True)
            return 0
        print(f"[{attempt}] waiting on {len(pending)}: {','.join(sorted(pending))}", flush=True)
        time.sleep(20)
    print(f"TIMEOUT: {pending}", flush=True)
    return 1


def verify():
    sys.path.insert(0, HERE)
    import verify_motion, check_footer_text
    import contextlib, io
    out = {}
    for slug in sorted(load_jobs()):
        clip = f"{WORK}/raw-{slug}.mp4"
        poster = f"{ROOT}/docs/assets/engine-{slug}.webp"
        if not os.path.exists(clip):
            continue
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            verify_motion.main(clip, poster)
        rep = json.loads(buf.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            txt_rc = check_footer_text.main(clip, poster)
        out[slug] = {"rotation_span_deg": rep["rotation_span_deg"],
                     "rotation_ok": rep["rotation_ok"],
                     "moves": rep["moves"],
                     "footer_text_ok": txt_rc == 0,
                     "pass": bool(rep["rotation_ok"] and rep["moves"] and txt_rc == 0)}
        print(f"{slug:<14} rot={rep['rotation_span_deg']:<6} moves={rep['moves']} "
              f"text_ok={txt_rc == 0}  => {'PASS' if out[slug]['pass'] else 'FAIL'}", flush=True)
    json.dump(out, open(f"{WORK}/verdicts.json", "w"), indent=2)
    print(f"\n{sum(v['pass'] for v in out.values())}/{len(out)} passed")
    return 0


def install(slugs):
    """Install + wire only the clips that passed. A FAIL is left unwired, so the
    page keeps its honest static tile rather than shipping a bad animation."""
    sys.path.insert(0, HERE)
    import install_motion, wire_motion
    verdicts = json.load(open(f"{WORK}/verdicts.json"))
    done, skipped = [], []
    for slug in slugs:
        if not verdicts.get(slug, {}).get("pass"):
            skipped.append(slug)
            continue
        install_motion.install(slug)
        wire_motion.wire(slug)
        done.append(slug)
    print(f"\ninstalled {len(done)}: {', '.join(done)}")
    if skipped:
        print(f"left static (did not pass) {len(skipped)}: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    args = sys.argv[2:] or REMAINING
    if cmd == "install":
        sys.exit(install(args))
    if cmd == "prompts":
        for s in args:
            print(f"--- {s}\n{prompt_for(s)}\n")
    elif cmd == "submit":
        submit(args)
    elif cmd == "poll":
        sys.exit(poll())
    elif cmd == "verify":
        sys.exit(verify())
    else:
        raise SystemExit(f"unknown command {cmd}")
