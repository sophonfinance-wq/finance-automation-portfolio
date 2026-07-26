"""Re-roll the clips that failed a gate, with an intensified camera lock.

Most failures are stochastic -- the same template produced locked-off clips for
the majority -- so a re-roll is usually enough. But every failure seen so far is
either bodily rotation or the strip moving with it, so the retry prompt leads
with the lock instead of burying it mid-paragraph, and states the tolerance in
terms the model can act on (frame edges, not degrees).

The previous job id is kept in jobs.json under `rejected` rather than
overwritten: it stays downloadable from Higgsfield and records what was tried.
"""
import json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch

INTENSIFIER = (
    "ABSOLUTELY NO CAMERA MOVEMENT. This is a rigid still photograph and the "
    "camera is bolted down. Every edge of the frame, every corner of the machine "
    "and the whole bottom caption strip must stay in exactly the same place in "
    "every single frame -- not drifting, not rotating, not tipping, not sliding, "
    "not breathing, not one pixel. If nothing else moves, that is correct. "
)


def retry(slugs):
    jobs = batch.load_jobs()
    for slug in slugs:
        prev = jobs.get(slug, {})
        prompt = INTENSIFIER + batch.prompt_for(slug)
        r = subprocess.run(
            [batch.HF, "generate", "create", "kling3_0", "--prompt", prompt,
             "--start-image", batch.poster_png(slug), "--mode", "pro",
             "--duration", "5", "--aspect_ratio", "16:9", "--sound", "off",
             "--json"], capture_output=True, text=True)
        try:
            ids = json.loads(r.stdout)
            job_id = ids[0] if isinstance(ids, list) else ids.get("id")
        except Exception:
            print(f"{slug}: UNPARSED -> {r.stdout[:160]}{r.stderr[:160]}")
            continue
        rejected = prev.get("rejected", [])
        if prev.get("job_id"):
            rejected.append(prev["job_id"])
        jobs[slug] = {"job_id": job_id, "attempt": prev.get("attempt", 1) + 1,
                      "prompt": prompt, "rejected": rejected}
        batch.save_jobs(jobs)
        # move the rejected clip aside so poll() re-downloads into raw-<slug>.mp4
        raw = f"{batch.WORK}/raw-{slug}.mp4"
        if os.path.exists(raw):
            os.replace(raw, f"{batch.WORK}/rejected-{slug}-a{prev.get('attempt', 1)}.mp4")
        print(f"{slug}: retry {jobs[slug]['attempt']} -> {job_id}")
        time.sleep(2)


if __name__ == "__main__":
    retry(sys.argv[1:])
