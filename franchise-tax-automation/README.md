# Combined-group franchise-tax automation

A deterministic, **read-only** control engine for a combined-group franchise
(margin) tax return — a group of affiliated development companies filing one
combined return each fiscal year in the fictional State of Marran, with the
affiliate roster rebuilt from the prior year, the group margin apportioned to
Marran by a single receipts factor, and the tax re-derived from the workpapers.

The return is not one entity's; it is the whole group's, apportioned to Marran by
a single receipts factor. Preparing it means three things happen together, and
each is a place a number can go wrong.

**The combined group is redrawn.** The affiliate roster is rebuilt each year —
last year's members, plus the affiliates that joined, minus the ones that left —
and the affiliates *not* included this year have to be enumerated and reconciled,
not silently dropped. An affiliate that quietly falls off the roster is revenue
that leaves the combined base with nobody noticing.

**The margin is apportioned.** Consolidated group revenue, taken from the
consolidated tax trial-balance workpaper, is reduced by the group's elected
deduction to a taxable margin, and that margin is apportioned to Marran by the
single receipts factor — in-state receipts over everywhere receipts. A factor
struck against the wrong denominator, or a base that does not tie the trial
balance, is a tax computed on numbers nobody reconciled.

**The tax is a derived figure.** The tax is the margin times the apportionment
factor times the rate, in that order. A margin that does not re-derive from
revenue less the deduction, an apportioned figure that does not re-derive from the
factor, a tax that does not re-derive from the rate — each looks right on the
return and is wrong underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 21 controls, writes
`franchise_report.json` and `franchise_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 21 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the combined-return file complete, and is the review date readable? |
| `aff_` | 4 | Are the affiliate ids unique, each address and registration complete, each status known, and which registrations are due to renew? |
| `grp_` | 3 | Does the combined roster rebuild from the prior year, are its members registered, and is every removal enumerated and reconciled? |
| `tb_`  | 3 | Is every consolidated trial-balance line well-formed, uniquely numbered, and attributed to a combined member? |
| `apt_` | 4 | Are the receipts rows sound, do the totals tie the rows, and do the receipts and worksheet apportionment factors recompute? |
| `mgn_` | 4 | Does group revenue tie the trial balance, and do the margin, apportioned margin and tax re-derive? |
| `rpt_` | 2 | Does the summarised tax recompute from the workpapers, and does the return total tie the summary and roster? |

Three are worth calling out.

**The determination recomputes, it is not read back.** `rpt_summary_recomputes`
is the control the engine exists for. The tax summary is a *determination*, and a
determination that is not recomputed from the workpapers is an assertion. The
engine rebuilds the whole tax — group revenue from the trial balance, the
apportionment factor from the receipts, the margin from the elected deduction, the
tax from the rate — through the same kernel that produced the data, and compares.

**The roster rebuilds, it is not carried forward blind.** `grp_roster_continuity`
rebuilds the combined member list from last year's members plus this year's
additions less its removals, and `grp_excluded_reconciled` proves every affiliate
that left is enumerated on the "not included this year" list with a reason and is
not also a current member — so a member cannot vanish from the combined base
unrecorded.

**The apportionment factor is bounded and recomputed.** `apt_factor_recomputes`
recomputes the single receipts factor — in-state receipts over everywhere
receipts, floored to a basis point and bounded to `[0.00%, 100.00%]` — from the
workpaper's own totals and compares with exact `==`. A factor struck off the wrong
denominator, or one above 100%, does not tie.

## The registration-renewal window is a flag, not a failure

`aff_registration_renewal` marks an affiliate registration renewing inside the
file's own lead-time window: the registration is still current, but the renewal
needs to be lodged before it lapses. It is the one `REVIEW`-severity control —
worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest franchise_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, a 10,000-case invariant
grid over the shared money kernel, and read-only / determinism proofs that hash
the corpus before and after a full run.

## The baseline is derived, not typed

Only the affiliate register, the roster's prior-year members and this year's
additions and removals, the consolidated trial-balance revenue lines, the receipts
rows and the group's elected deduction and rate are stated. The generator computes
everything the engine later checks as a rollup — the current member list, the
receipts totals and apportionment factor, group revenue, the taxable margin, the
apportioned margin and the tax, the tax summary and the return totals — through the
*same* margin-tax kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The combined group, the affiliates, the fictional
State of Marran and City of Kelder, the addresses, the registrations, the
consolidated revenue and receipts, and every limit and date are invented, and the
fiscal year is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
