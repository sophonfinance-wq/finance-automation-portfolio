# Lien waiver tracking automation

A deterministic, **read-only** control engine for a residential developer's
mechanics-lien waiver coverage — every progress payment down the subcontractor
tier chain matched to a lien waiver of the right kind, through the right date, for
the right amount, so that no lien survives to attach to the developer's title.

A developer pays a general contractor, who pays subcontractors, who pay their own
lower-tier subs and material suppliers. Every one of those parties can file a
mechanics lien against the project. A lien waiver is the release that gives it up,
and the waiver has to march in lockstep with the money.

Three failures hide inside that, and none of them look wrong while a waiver is on
file.

**The conditional that never became unconditional.** A subcontractor signs a
*conditional* waiver when it is paid — conditional on the payment actually
clearing. Once the cheque clears, it owes an *unconditional* waiver. The cheque
clears; the unconditional is never chased; the file looks complete because *a*
waiver is on record. The lien right is still live.

**The coverage that stops short of the money.** A waiver runs through a date. If a
payment covers work through the end of February but the waiver only releases
through the end of January, the last month of paid work is unwaived — and nobody
notices, because there is a waiver in the folder.

**The tier nobody waived.** The subcontractor released. Its own rebar supplier,
paid out of that same progress payment, did not. A downstream lien survives the
upstream release, and it attaches to the same title.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 25 controls, writes
`lien_report.json` and `lien_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 25 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the portfolio file complete, and is the review date readable? |
| `party_` | 5 | Is the contract register sound, and does the tier chain hold — unique ids, valid tiers, real parents, known projects? |
| `pay_`   | 4 | Is each progress payment fully described, tied to a real sub, positive, and sensibly dated? |
| `wvr_`   | 5 | Is each waiver well-formed, uniquely identified, of a known type, tied to a real payment, for the right amount? |
| `cov_`   | 3 | Is every payment covered to its paid-through date, is every *cleared* payment released *unconditionally*, and is any stale conditional flagged? |
| `tier_`  | 3 | Did every required lower-tier party release, far enough, through a correctly re-derived date? |
| `exp_`   | 2 | Does the unwaived exposure per project re-derive, and does every paid project appear? |
| `rpt_`   | 2 | Do the waiver-log counts reconcile to the register? |

Three are worth calling out.

**The conditional does not survive the cheque.** `cov_cleared_unconditional` is
the control the engine exists for. A conditional waiver releases *only if* the
payment clears; once it has, the unconditional release is owed. A cleared payment
sitting behind a conditional waiver alone looks covered and is not. Its sibling
`cov_payment_covered` catches the other failure — money out the door with no
release reaching its paid-through date at all — and `cov_stale_conditional` flags
the conditional that has aged past the window in which it should have been
upgraded, reading its ageing band from the register rather than inventing one.

**The tier nobody waived.** `tier_waiver_covers` compares each required
lower-tier party's release against the date its parent was paid through, and
`tier_required_recomputes` proves that required date is the parent's *own* latest
paid-through date rather than a figure typed in and trusted. A supplier that
releases only through last month, while its sub was paid through this month, has
left the most recent downstream work unwaived.

**The exposure re-derives, it is not read back.** `exp_recomputes` rebuilds the
unwaived exposure per project from the payments and the releases — a payment
counts until an *unconditional* waiver stands behind it — rather than trusting the
carried-forward total a controller reports to the lender.

## Tests

```bash
python -m pytest lien_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the subcontracts, the payments and the lower-tier parties are stated. The
generator computes everything the engine later checks as a tie-out: the
conditional and unconditional waivers behind each payment, the date each
lower-tier party must release through, the unwaived exposure per project, and the
waiver-log counts.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the subcontractors, the suppliers,
the payments and every amount are invented, and the construction period is set in
a fictional future. No employer or client workpaper, entity, methodology, path or
figure is reproduced.
