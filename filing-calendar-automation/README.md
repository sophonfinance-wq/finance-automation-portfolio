# Filing-obligation calendar automation

A deterministic, **read-only** control engine for a fiscal-year filing-obligation
calendar — every entity, in every jurisdiction, proved obligation by obligation to
have filed or validly extended each return and payment before its statutory due
date, paid each fixed-amount voucher in the exact statutory amount, and to carry a
status register that ties to the filed evidence with nothing missing and nothing
orphaned.

This engine does not prepare a return or compute a tax. It takes the finished
calendar and asks the narrower, entirely evidentiary question: was every deadline
met or validly deferred, and does the register tie to the paper underneath it?

A filing calendar is a matrix of dates that was correct the day someone typed it,
and it goes wrong in ways nobody watches until a notice arrives. Four failures
hide inside that, and none of them look wrong in a grid of dates.

**The due date drifts.** An original or extended due date is typed a day off, or an
extension offset is applied to the wrong form, and the whole register keys its
follow-up off a deadline that is not the statutory one.

**The deadline passes.** An obligation is neither filed nor extended, its due date
slides past the review date, and it sits in the register looking like every other
open row — until it is a late-filing penalty.

**The evidence and the register part company.** A row is marked filed with a
receipt number but no voucher was archived, or a voucher sits in the archive with
no row that claims it, and the count of "done" no longer means what it says.

**The fixed amount is not fixed.** The annual LLC tax is a statutory constant; a
voucher cut for a cent more or less than that constant is wrong on its face.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`filing_report.json` and `filing_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the calendar file complete, and is the review date readable? |
| `due_`   | 4 | Does every obligation carry a readable year-end, map to the statutory table, and store an original and extended due date that re-derive from it? |
| `ext_`   | 4 | Do the extension flag and extended date agree, is anything overdue or filed late, and what falls due inside the lead window? |
| `pay_`   | 1 | Is each fixed-amount payment the exact statutory constant? |
| `evd_`   | 3 | Does every filed row tie to a voucher, every extension to an acceptance, and every piece of evidence back to a row? |
| `ros_`   | 3 | Does every active entity carry a row, is every row attributable to a rostered entity, and is every obligation id unique? |
| `wfl_`   | 2 | Does the internal workflow schedule run in order, and has any actual slipped past its goal? |
| `cnt_`   | 1 | Does an entity marked final in the prior year stay dissolved this year? |
| `rpt_`   | 3 | Does each obligation's status recompute, do the counts tie the register, and does the due-soon watchlist tie it? |

Three are worth calling out.

**The status recomputes, it is not read back.** `rpt_status_recomputes` is the
control the engine exists for. The status summary is a *determination*, and a
determination that is not recomputed from the register is an assertion. The engine
rebuilds every obligation's status — filed, filed-late, overdue, open,
not-applicable — from its own dates and compares it to the one on file.

**The deadline is met at the date.** `ext_filed_on_time` compares with exact `<=`:
a return filed on the applicable due date is on time, a day past it is late.
`ext_applicable_overdue` uses the same edge: an obligation unfiled with its
deadline on the review date is overdue. There is no grace band.

**The due date is a re-derivation, not a copy.** `due_original_matches` and
`due_extended_matches` rebuild each deadline from the form and the year-end against
the statutory table — the extended date is the original advanced by the form's
whole-month offset — and compare. A date typed a day off does not re-derive.

## The extension gate

An obligation's *applicable* deadline is the extended date when an extension was
filed and the original otherwise, and `ext_flag_valid` proves the flag and the
extended date never disagree — an extended date on a row that filed no extension
has no basis, and an extension flag with no extended date has nothing to run to.

## The watchlist and slippage are flags, not failures

`ext_due_soon` marks an unfiled obligation falling due inside the file's own
lead-time window: the deadline has not passed, but the filing needs chasing.
`wfl_actual_slippage` marks an internal prep or review step completed after its
goal — the early warning before a statutory deadline is missed.
`rpt_watchlist_ties` proves the stated due-soon list is exactly the set actually
due. All three are `REVIEW`-severity: worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest filing_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control (each proved to trip *only* its intended control), boundary tests on every
day, cent and status threshold, and read-only / determinism proofs that hash the
corpus before and after a full run.

## The baseline is derived, not typed

Only the roster, the statutory due-dates table, the obligation base facts and the
evidence are stated. The generator computes everything the engine later checks as
a rollup — each obligation's original and extended due date, its status, the
portfolio overdue and filed counts, and the due-soon watchlist — through the *same*
due-date kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The filing groups, the entities, the jurisdictions,
the form codes, the EINs and every date and amount are invented, and the fiscal
year is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
