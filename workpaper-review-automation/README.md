# Workpaper Review & Handback — engine 53

**The problem it owns:** a tax workpaper package whose numbers are agreed, and which a reviewer
still cannot verify without redoing the preparer's work.

Every failure mode here **survives a footing check**. That is why it needs its own engine: the
totals tie, the controls are zero, and the package is still not reviewable.

| | |
|---|---|
| Package | `workpaper_engine` |
| Controls | 9 |
| Tests | 20,076 gated + a `SWEEP=1` wide pass |
| Data | fictional, seeded (`SEED = 20260912`) |
| Writes | never — the engine is read-only |

## The six ways a correct package is still not reviewable

**A figure is correct and untraceable.** A current-year amount typed onto a consolidation foots
perfectly and says nothing about where it came from. The reviewer's only options are to trust it or
rebuild it.

**A citation resolves to a plausible wrong number.** The reference is valid, the cell exists, a
believable figure comes back — and it is the wrong cell. The closer the wrong figure sits to the
right one, the longer it survives, so `CITATION_MISMATCH` grades a rounding-sized gap exactly as
seriously as a large one. There is no tolerance band anywhere in this engine, and that is deliberate:
a tolerance band is the mechanism that hides this defect.

**A sweep repairs what was never broken.** Dates are stored as integers, so every amount in a
date-shaped band looks like a date. `DATE_MISREAD` leans on a structural fact rather than the value:
**a date is never an addend.** A cell summed into a total and presented as a date has been misread,
and no footing check will say so, because the underlying number never changed. Amounts merely
*sitting* in the band are flagged and explicitly protected so a later sweep cannot convert them.

**A dependant is orphaned.** A block is moved after confirming no *other* document references it.
Same-document references carry no document name, so the check missed them.

**The cover note and the workbook disagree.** The note says three open questions; the file carries
fifteen. Both are internally consistent — only comparing them finds it. The count is taken from the
question block inside the file, never from a tracker.

**A residual is silenced rather than disclosed.** A known, accepted, immaterial difference is plugged
to zero, and the package now looks cleaner than it is.

## Controls

| Control | Severity | Fires when |
|---|---|---|
| `UNSOURCED_INPUT` | FAIL | a current-year amount is typed rather than linked to a source record |
| `CITATION_MISMATCH` | FAIL | a citation quotes a figure its address does not hold, or does not resolve |
| `DATE_MISREAD` | FAIL / FLAG | a date is an addend in a total; or an amount sits in the date-serial band |
| `ORPHANED_DEPENDANT` | FAIL | a dependant of a moved block was not re-pointed |
| `QUESTION_COUNT_MISMATCH` | FAIL | the note's counts differ from the question block |
| `ATTACHMENT_DRIFT` | FAIL | the note's attachment hash is not the package's |
| `RESIDUAL_PLUGGED` | FAIL | a residual was plugged rather than disclosed |
| `PRESENTATION_DRIFT` | FLAG | a rule is missing against, or stray from, the prior-year master |
| `EVIDENCE_OVERCLAIM` | FAIL | the note claims complete evidence while citations do not resolve |

`PRESENTATION_DRIFT` reports `font_underline` and `cell_border` as the distinct properties they are.
They look identical to a reader and are fixed differently; conflating them is how a presentation
sweep reports success while the file still looks wrong.

## Run it

```bash
cd workpaper-review-automation
python run.py                      # generate + analyze + write both reports
python -m pytest -q                # 20,076 tests
SWEEP=1 python -m pytest -q        # + the wide band sweep
python -m workpaper_engine samples # analyze an existing folder, read-only
```

Exit codes: `0` PASS · `1` FLAG, human review · `2` FAIL · `3` usage/IO.

## Design notes

Integer cents throughout, exact `==`, no tolerance band. Seeded generation is byte-stable, so a
regenerated corpus can be diffed. The engine refuses rather than fudges — a value that should be
integer cents and is not raises `AmountInvalidError` rather than being coerced, because silently
rounding a source figure would make the engine the author of the number it is meant to audit.

The corpus ships one clean package plus one package per defect class, so every control has something
to catch and the clean baseline proves no control fires on a sound package.

Beyond the case tests, six curated invariant grids assert properties rather than examples: the money
kernel conserves every cent across 10,000 points; `CITATION_MISMATCH` fires **iff** the quoted and
resolved figures differ, swept across offsets that include exactly one cent; a value is a date
candidate **iff** it is whole dollars inside the serial band, swept across both boundaries and across
fractional cents; and a cell presented as a date while feeding a total fails at every point of the
band, because no value can make a date an acceptable addend. `SWEEP=1` widens the same grids rather
than adding different ones, so a sweep failure always reproduces at the gated size.

All data is invented. No real entity, person, place, figure, document or path appears anywhere.
