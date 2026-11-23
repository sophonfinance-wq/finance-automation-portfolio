# Information return issuance & threshold tie-out

A deterministic, **read-only** control engine for the annual information-return
run — every payee the group paid something reportable to, reassembled entity by
entity, tested against the box threshold that decides whether a form is owed, and
every box footed back to the payment lines it came from.

Once a year the group rebuilds a population it never maintained: interest paid to
lenders and affiliates, non-employee compensation to vendors, card and third-party
settlement. The box catalog carries a threshold per box. The ledger extract carries
every payment line. The form register carries what was actually issued, with the
payer's taxpayer number, the payee's, the box amount and any backup withholding.
A transmittal per entity accompanies the forms, and an annual rollup adds the
transmittals together.

Nothing here approves a payment. Whether a disbursement should have been released
is a separate engine's question, and that engine explicitly declines to ask
whether what it released was reportable. Three failures hide inside the run, and
none of them look wrong in a ledger that was never organised around who has to
receive a form.

**The population has a hole in it.** A payee clears a threshold in one entity and
is never cut a form. Nothing in the ledger notices: the payments posted, the
invoices closed, and the omission exists only in a population nobody re-ran. The
same hole appears in reverse when a payee has no taxpayer number on file and
nothing is withheld against it.

**A box amount stops being footed.** The figure on the form is re-keyed from a
summary rather than added from the entity's own payment lines. It is off by an
invoice, and the form goes out reporting an amount the ledger does not support.

**The transmittal stops tying the forms.** The count or the total is maintained
beside the register rather than struck from it, so the one page the authority reads
first disagrees with the forms behind it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`inforeturn_report.json` and `inforeturn_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_` | 1 | Is the reporting file complete, and is the reporting year readable? |
| `ent_` | 2 | Are the payer entity ids unique, and is every payer identified? |
| `pye_` | 3 | Are the payee ids unique, is every payee type known, and is every taxpayer number on file readable? |
| `box_` | 2 | Is every catalogued box a known series with a usable threshold, and is each box defined once? |
| `led_` | 3 | Is every payment line attributable, non-negative integer cents, and inside the reporting year? |
| `frm_` | 4 | Is every form complete, correctly attributed to its payer, unduplicated, and footed to the ledger? |
| `thr_` | 3 | Is a form issued exactly where one is owed, never where one is not, and what sits just under? |
| `bwh_` | 1 | Does backup withholding recompute at the statutory rate, in both directions? |
| `rpt_` | 3 | Do the transmittals, the annual rollup and the watchlist foot the forms? |

Three are worth calling out.

**A form is owed exactly where one is owed.** `thr_required_form_issued` and
`thr_no_unrequired_form` are exact complements, and shipping only the first is the
common mistake. An excess form is not harmless: a below-threshold form with nothing
withheld reports a payee who was not reportable, and that payee now has to
reconcile a statement against a return that should never have been filed. The
threshold is met **at** the cent — a year total of exactly the threshold is
reportable and a cent under it is not — and the corpus puts a real row on that
edge, so the boundary is tested rather than assumed.

**Withheld tax obliges a form the threshold would not have.** Where a box attracts
backup withholding and the payee has no taxpayer number on file, tax is withheld
on the payment, and withheld tax is reported however small the payment was. That
override is the one rule that makes the completeness control non-obvious, and the
corpus carries a payee paid far under the threshold whose form is owed for exactly
this reason.

**Withholding is recomputed in both directions.** `bwh_rate_recomputes` rebuilds
the figure from the reported amount with truncating basis-point arithmetic and
compares with exact `==`. Missing withholding is the group's own liability whether
or not it was taken. Withholding taken where a number *is* on file is the payee's
money held without cause. One re-derivation catches both.

## The review band is a flag, not a failure

`thr_near_threshold_review` marks a payee sitting inside the file's own
`near_threshold_cents` band below a threshold: no form is owed today, and one late
invoice posting to the year tips it over. The band is where the cycle gets re-run
rather than re-opened after the forms have gone out. `rpt_watchlist_ties` marks a
disagreement between the stated watchlist and the population behind it. Both are
`REVIEW`-severity: worth a human's eyes, not a hard stop.

## Tests

```bash
python -m pytest inforeturn_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, day and taxpayer-number digit, and read-only
/ determinism proofs that hash the corpus before and after a full run.

## One issuance predicate, defined once

Deciding whether a payee/box owes a form, and what has to be withheld on it, lives
alone in `issuance.py`, and both the generator and the controls import it. That is
deliberate. If the engine recomputed a form's requirement by *different* logic than
the logic that produced it, the two would disagree on exactly the edge cases that
matter — a total landing on the threshold, a payee with no number paid a token
amount, a shortfall at the edge of the band — and the tie-out control would be
measuring the disagreement between two implementations rather than the correctness
of the determination.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The groups, the entities, the payees, the taxpayer
numbers, the box catalog and every payment, threshold and issue date are invented,
the taxpayer-number format is deliberately unlike any real identifier, and the
reporting year is set in a fictional future. No employer or client workpaper,
entity, methodology, path or figure is reproduced.
