#!/usr/bin/env python3
"""Fetch every why-film source asset from Higgsfield job ids into work/.

Usage: python fetch_assets.py [--voice sloane|arthur]
Requires the authenticated `higgsfield` CLI on PATH.
"""
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"


def job(jid):
    out = subprocess.run(["higgsfield", "generate", "get", jid, "--json"],
                         capture_output=True, text=True).stdout
    return json.loads(out)


def fetch(jid, dest, tries=120, wait=10):
    if dest.exists():
        print("have", dest.name)
        return True
    for _ in range(tries):
        d = job(jid)
        st = d.get("status")
        if st == "completed" and d.get("result_url"):
            urllib.request.urlretrieve(d["result_url"], dest)
            print("got", dest.name)
            return True
        if st in ("failed", "nsfw", "cancelled"):
            print("FAILED", dest.name, st)
            return False
        time.sleep(wait)
    print("TIMEOUT", dest.name)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="sloane", choices=["sloane", "arthur"])
    args = ap.parse_args()
    WORK.mkdir(exist_ok=True)
    m = json.loads((HERE / "manifest.json").read_text())
    ok = True
    for name, jid in m["video_jobs"].items():
        ok &= fetch(jid, WORK / f"{name}.mp4")
    for name, jid in m.get("animated_from_stills", {}).items():
        ok &= fetch(jid, WORK / f"{name}.mp4")
    for name, jid in m.get("still_jobs", {}).items():
        ok &= fetch(jid, WORK / f"{name}.png")
    for beat, jid in m[f"vo_jobs_{args.voice}"].items():
        ok &= fetch(jid, WORK / f"vo_{args.voice}_{beat}.mp3")
    print("all ok" if ok else "SOME ASSETS MISSING")


if __name__ == "__main__":
    main()
