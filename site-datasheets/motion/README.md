# Engine-tile motion

Animates an engine tile from **its own poster**, so the artwork that moves is the
artwork already shipped. Each clip is a Higgsfield `kling3_0` image-to-video job
recorded in `manifest.json` with its prompt, attempt count and measured verdict.

The previous motion batch (`1af78d9`) recorded its recipe only in a commit
message and committed no tooling, so this pipeline had to be rebuilt from
scratch. It lives here so the next batch starts from evidence.

## Running it

Needs the authenticated `higgsfield` CLI on PATH, plus `numpy`,
`opencv-python-headless` and `imageio-ffmpeg` (which bundles a static ffmpeg —
this Mac has no Homebrew):

```bash
uv venv --python ~/.local/bin/python3.12 .venv-motion
uv pip install --python .venv-motion/bin/python numpy opencv-python-headless imageio-ffmpeg
```

```bash
python site-datasheets/motion/batch.py prompts <slug>      # inspect, costs nothing
python site-datasheets/motion/batch.py submit  <slug>...   # ~12.5 credits per clip
python site-datasheets/motion/batch.py poll                # download completed jobs
python site-datasheets/motion/batch.py verify              # run the gates
python site-datasheets/motion/batch.py install <slug>...   # refit, install, wire, regenerate
python site-datasheets/motion/retry.py <slug>...           # re-roll with a harder camera lock
python site-datasheets/motion/write_manifest.py            # rebuild this manifest from results
```

`install` wires only what passed; a failing tile keeps its static poster.

## The gates, and why they are shaped the way they are

Each gate here exists because a simpler version of it gave a confidently wrong
answer during the 2026-07-25 batch.

**Rotation** — `verify_motion.py`, `<= 0.30 deg`. Measured by composing
consecutive-pair rigid fits. Matching every frame back to frame 0 collapses its
inliers and reads a clean 12.43 deg that flips to -13.35; neighbour fits sit
under the noise floor.

**Measure rotation on the SOURCE render, never the shipped file.** The
accumulation is resolution-dependent. One clip reads 0.178 deg at 1920x1080 and
1.771 deg after a *lossless* downscale to 1280x720, while the shipped crf-30 file
reads 1.478 — lower than lossless. A pure resize cannot introduce rotation, so
that spread is tracking noise on smaller features, not motion. Re-gating the
delivered 720p file will make a good batch look broken.

**Footer text** — `check_footer_text.py`, NCC `>= 0.90` on controls / tests /
read-only. The control and test counts are burnt into the pixels and pinned in
`raster_footers.json`, and the page cites them in prose, so they must survive.
Absolute pixel difference cannot do this job: H.264 softening alone moves thin
antialiased ink 15-20 levels with nothing moving, and a shadow crossing the strip
reads the same as a redraw. NCC is invariant to brightness and contrast, and each
frame is compared to the clip's *own* frame 0 so the codec cancels out.

`part_no` is advisory with a `0.55` floor. It sits at the longest lever arm from
frame centre, so the residual rotation the first gate already permits displaces it
more than any other label. The loose floor still catches what the check is for —
the label being occluded or re-lettered, which is what ruled out `sizing`.

**Handoff** — frame 0 vs poster, `< 8/255`. The `<video>` replaces the poster in
place, so a mismatch shows up as a pop. All shipped clips land at 3.7-4.3.

**Aspect** — the clip must match its poster's aspect. These tiles are true 16:9
(1600x900); the older tiles at 1.791 needed refitting in `1af78d9`.

**Loop seam** — every tile plays with `loop=true`, so the wrap from last frame
back to first is on screen every few seconds. Measured across the whole site, 34
of 37 clips jumped at that wrap; the previous batch's `upgrade`, `warranty` and
`draw` are the worst on the site at 7–12 (absolute mean-abs, 0–255). `install_motion.py`
now eases the tail back to frame 0 so the wrap is continuous, which brings every
clip here to ≤2.4 — at or better than `intercompany` (2.11), which already ships
and reads as a clean loop.

Judge the seam in **absolute** terms, not as a multiple of the median frame step.
A nearly-static clip has a tiny median step, so a perfectly acceptable seam can
read as "6x" while being visually nothing.

Two rejected alternatives, for the record. Cross-dissolving the tail onto the
*head* makes frame 0 a blend of two moments, so it no longer matches the poster
and the swap pops — trading a jump every loop for a pop on every load. Ping-pong
is seamless by construction but runs the machine backwards, which is wrong for a
mechanism meant to read as working.

Do the loop close in the SAME pass as the scale and encode. Running it as a
second pass over the finished 720p file costs a generation of H.264 and pushed
the poster handoff from ~3.8 to ~6.2 with no visible benefit. Blending needs
pixel access so the decode is unavoidable, but let ffmpeg do the scaling:
measured on one clip, ffmpeg-only scored 3.69, python-decode + ffmpeg-scale 4.91,
and python-decode + cv2-resize 5.99. (Expressing the blend as an ffmpeg `blend=`
expression keeps everything in YUV and scores 3.69, but it evaluates per pixel
per frame and is far too slow for a batch.)

## The gate the numbers cannot replace

**Every clip must be looked at.** The four measurements above check the camera, the
burnt-in figures, the poster handoff and the loop. Not one of them looks at
whether the machine stays a machine, and that is where this generator actually
fails. Of 30 clips that passed all four numeric gates, visual review found real
defects in 16: paper draping like wet cloth off the output tray, an input ream
draining to bare metal and refilling, infeed paper turning into a steel plate, a
coil spring melting, a stainless tray dissolving and re-forming, a drive belt
coming apart into loose straps, a dial gauge fading in from nothing.

Two clips (`spending`, `financing`) passed *every* number on their final take —
rotation 0.08 and 0.09 degrees, text intact — and were still obviously wrong on
sight, the report hanging off the tray like a curtain past the caption strip.
Numbers alone would have shipped both.

Build a contact sheet per clip (8 frames evenly sampled, 2 columns) and review
them. `motion-work` in the working tree has the throwaway script for this. When a
clip fails, run `unwire.py` — the default for a clip that cannot be made good is
its static poster, never the best bad take.

## Trim the tail

The generator drifts further from its source frame the longer it runs: averaged
over this batch, drift at 90% of duration was 1.5x the drift at 30%, and most of
the artifacts above appear in the last third. `install_motion.py` therefore drops
the final sixth (`TRIM_TAIL`). That alone rescued `inforeturn`, whose report
drooped only after frame 103 and which is clean once trimmed.

It is not a cure-all. `checkage`'s paper melt starts at frame 17, 14% in, and
trimming cannot touch it. Trim removes late-onset defects; early ones need a
re-roll, and some tiles never converge.

## Prompting

Lead with the lock and name the rigid parts. The difference between attempt 1 and
attempt 2 on `checkage` — 1.75 deg of drift versus 0.20 — was naming the body,
the surface, the horizon line and the caption strip explicitly and forbidding
tilt, skew and re-lettering of the strip by name. `batch.py` derives the
mechanism sentence from each tile's own `poster_alt`, trimmed: the alts are
written for screen readers, and feeding all 600 chars of one in invites the
generator to redraw the machinery instead of animating it.

Where a tile keeps letting a sheet cross the caption strip, add the
"nothing crosses the strip" clause — see `attempt 4` in `manifest.json`.

## Warping is not a fallback

`stabilize.py` cancels residual drift by warping each frame back. It worked in
`1af78d9` at 2.9 deg. It does **not** rescue the failures seen here: these are 3D
perspective drifts, so cancelling the in-plane component leaves the caption strip
still tilted, and at ~2 deg the edge replication smears the strip badly enough
that text NCC goes *negative*. Cropping to hide the smear rescales the clip
against its own poster, which reintroduces the handoff pop. Re-roll instead.

## Not animated

`gaalloc`, `pickup` and `sizing` keep static posters after four attempts each —
each one either would not hold the camera or disturbed a burnt-in label. For them
`media.motion` still equals `media.poster`, which is this repo's way of spelling
"no motion exists", so the generator emits no `data-video`. Their `run_label` is
set to `engine tile` so the page does not promise motion it does not have.
