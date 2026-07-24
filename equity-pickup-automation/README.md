# Equity-method pickup & eliminations automation

A deterministic, **read-only** control engine for equity-method pickup and
consolidation eliminations — every parent's investment-in-sub carrying value
re-footed as a begin + contributions + pickup − distributions roll-forward,
every equity pickup re-derived as ownership × sub net income, and every
Investment account proved paired to its sub's Equity-Parent account and
extinguished for exactly the carrying value, so consolidation nets to zero
entity block by entity block.

The engine deliberately does **not** opine on impairment or fair value. Those
are judgment calls owned by a valuation workpaper, and a valuation workpaper
does not re-foot a roll-forward. This engine is that re-foot: everything here
is a hard equality, a threshold, a date gate, a membership test or a
re-derivation.

Three failures hide inside an equity-method workpaper, and none of them look
wrong on their own page.

**The pickup drifts from the ownership math.** Somebody keys the pickup, or
carries last quarter's percentage, and the parent books a share of income that
its ownership percentage does not produce — or routes a pickup through a
holding that is carried at cost and should book none at all.

**The elimination goes stale.** The carrying value moves all period but the
elimination entry does not, leaving a residual on consolidation that is
neither an asset nor equity; or a holding never gets paired to the sub's
equity at all, and the same net assets survive twice.

**The rollup drifts from the evidence.** The trial balance carries a
"should be" column nobody re-derives, member allocations stop summing to the
income they split, and a preferred-return accrual compounds a day-count error
forward period after period.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 25 controls, writes
`epu_report.json` and `epu_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 25 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the consolidation file complete — all eight artifacts, exactly once each? |
| `rf_`    | 4 | Does every roll-forward row foot exactly, name a registered holding, cover every holding exactly once, and carry the ownership share of the sub's declared distributions? |
| `epu_`   | 4 | Does each pickup recompute as ownership × sub net income, do cost-method holdings book none, is ownership in bounds and never over-allocated, and does every holding resolve to registered entities and a result row? |
| `elim_`  | 5 | Does every elimination block self-balance, is every equity holding paired investment-to-equity, is the full carrying value extinguished, does every block name a real equity holding, and do the accounts follow the code link-key convention? |
| `pref_`  | 4 | Do the preferred-return day counts, accruals, capital chain and period continuity all re-derive from the schedule's own dates and rates? |
| `alloc_` | 7 | Do the member allocations foot and sum to exactly the sub's net income, is every member a holder, and do the investment, pickup, should-be and adjustment columns of the trial balance tie out? |

Three are worth calling out.

**The pickup recomputes, it is not read back.** `epu_pickup_rederives` is the
control the engine exists for. The pickup is a *determination*, and a
determination that is not recomputed from the ownership percentage and the
sub's result is an assertion. The engine rebuilds every pickup through the
shared kernel — floor division, residual cent to the final holder, so a 50/50
split of an odd cent still sums back to the income it divides — and compares
exactly. `alloc_tb_pickup_ties` then ties the ledger to the *re-derived*
share, not the stated one, so a mis-keyed roll-forward cannot vouch for a
mis-keyed ledger.

**The elimination must extinguish, not merely balance.**
`elim_block_balances` proves debits equal credits inside every block, but a
balanced elimination can still be last period's: `elim_extinguishes_investment`
proves the credit to the Investment account equals the carrying value the
roll-forward *ends* at, and `elim_pairing_complete` proves every equity
holding has both sides of the pair at all. The parenthetical company code is
the machine link key — `elim_account_link_key` re-derives Investment
`<parent>-1<sub>`, pickup `<parent>-3<sub>` and Equity-Parent `<sub>-29xx`
from the entity codes, because the pairing is only mechanically checkable
while the convention holds.

**The accrual is derived from dates, not from its own day count.**
`pref_accrual_rederives` recomputes capital × rate × days/basis with the day
count taken from the period's dates, so a misstated `days` figure cannot
launder the accrual it multiplied — `pref_day_count` catches the count and the
accrual control stays honest independently. The capital chain and the
period-continuity gate close the loop: contributions earn from the next
period, the return never compounds into capital, and every period starts the
day after the prior one ends.

## The unposted adjustment is a flag, not a failure

`alloc_tb_adjustment_math` proves every trial-balance adjustment is exactly
should-be minus balance — an adjustment of the wrong size is a hard FAIL. But
an adjustment that is *right* and simply unposted is a different thing: the
workpaper is internally consistent and a human decides when the entry moves.
`alloc_tb_unposted_adjustment` marks it `REVIEW`-severity — worth a human's
eyes, not a hard stop — and it is the corpus's one FLAG-only file, proving the
FAIL/FLAG split is wired through the verdict roll-up.

## Tests

```bash
python -m pytest pickup_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and day threshold, kernel tests
pinning the floor-division and residual-cent rules, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the entities, the holdings, the sub results, the roll-forward opening
facts and the preferred-return period facts are stated. The generator computes
everything the engine later checks as a determination — each holding's pickup
and distribution share, every roll-forward ending value, the elimination
blocks, the member allocation, the accrual chain and the trial-balance
balances — through the *same* pickup kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced
the data.

---

Engine 35 · `SFS-E35-EPU` · mnemonic **EPU** (equity pick-up).

🔒 **All data is fictional.** The reporting groups, parents, subsidiaries,
members, company codes, ownership percentages and every balance and date are
invented, and the fiscal period is set in a fictional future. No employer or
client workpaper, entity, methodology, path or figure is reproduced.
