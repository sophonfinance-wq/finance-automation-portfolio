"""Poll Higgsfield jobs to completion and download each result.

Job ids persist on Higgsfield's servers, so this is safe to re-run: anything
already downloaded is skipped and nothing is re-generated (or re-charged).
"""
import json, os, subprocess, sys, time, urllib.request

JOBS = {
    "checkage-v2": "3572abbc-aedf-40e1-98e0-24813ba2b7e1",
    "waterfall": "1529c9eb-f8be-4a59-a721-e4bb65839cfa",
}
HF = os.path.expanduser("~/.local/bin/higgsfield")
OUT = os.path.dirname(os.path.abspath(__file__))


def status(job_id):
    r = subprocess.run([HF, "generate", "get", job_id, "--json"],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"status": "unparsed", "raw": (r.stdout or r.stderr)[:300]}


def main():
    pending = {s: j for s, j in JOBS.items()
               if not os.path.exists(f"{OUT}/raw-{s}.mp4")}
    for attempt in range(1, 161):
        for slug in list(pending):
            d = status(pending[slug])
            st = d.get("status", "?")
            if st == "completed":
                url = d.get("result_url") or ""
                dest = f"{OUT}/raw-{slug}.mp4"
                urllib.request.urlretrieve(url, dest)
                print(f"[{attempt}] {slug} COMPLETED -> {os.path.getsize(dest)} bytes", flush=True)
                del pending[slug]
            elif st in ("failed", "canceled", "error"):
                print(f"[{attempt}] {slug} {st}: {json.dumps(d)[:400]}", flush=True)
                del pending[slug]
            else:
                print(f"[{attempt}] {slug} {st}", flush=True)
        if not pending:
            print("ALL DONE", flush=True)
            return 0
        time.sleep(15)
    print(f"TIMEOUT still pending: {list(pending)}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
