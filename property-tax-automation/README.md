# Property tax automation

A deterministic, **read-only** control engine for a residential developer's
property tax cycle — parcel completeness, each jurisdiction's own statutory
calendar, ownership through closing, and the accrual behind it.

A homebuilder's property tax problem is not the arithmetic on one bill. It is that
the unit of taxation and the unit of ownership come apart, continuously, in a
direction nobody is watching.

A project starts as one parent parcel. It is platted, and becomes forty. The
assessor picks the split up on its own schedule, which is not the developer's.
Then the units close — one at a time, over eighteen months — and each closing
moves exactly one parcel off the developer's books while the tax roll keeps
billing the account it always has. The bill still arrives. It still looks right.
It is simply, increasingly, for somebody else's houses.

Nothing in the payables cycle catches this. The invoice is genuine, the payee is
genuinely the county, the amount genuinely matches the notice. The only thing
wrong is *whose parcel it is*, and that fact lives in a closing file the person
approving the payment has never seen.

The second problem is the calendar. A developer operating across state lines is
subject to regimes that share no due dates, no instalment count and no penalty
arithmetic. Applying one jurisdiction's habits to another's parcel is how a
delinquency is found after the penalty has already attached.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 26 controls, writes
`proptax_report.json` and `proptax_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 26 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the roll file complete, and are the tax year and review date readable? |
| `par_`  | 5 | Is the register sound, and does it carry one live parcel per lot the plat created? |
| `asmt_` | 4 | Does the assessment foot, does the charge follow from it, is a jump worth protesting? |
| `inst_` | 5 | Do the instalments match *this* jurisdiction's calendar and penalty arithmetic? |
| `own_`  | 6 | Did the tax follow the ownership through each closing? |
| `acr_`  | 4 | Does the accrual match the charge, stop at escrow and tie to the ledger? |
| `pay_`  | 1 | Does what was paid match what was actually owed? |

Four are worth calling out.

**The roll kept billing a parcel that had already closed.**
`own_no_payment_after_escrow` is the control the engine exists for. It compares
each instalment's *due period* against the parcel's close of escrow — not the
payment date, because a payment made in October for a period that began in July is
correct or incorrect depending only on when the period ran. Its mirror on the
ledger side is `acr_stops_at_escrow`: accruing tax on a house somebody else owns
overstates the liability and understates the margin on the sale that already
happened.

**Regimes are data, not code.** Three jurisdictions ship in the corpus: a
two-instalment spring/autumn regime on a calendar fiscal year, a two-instalment
regime on a fiscal year opening 1 July — which pushes its second instalment into
the *following* calendar year — and a single-instalment regime. No control
hard-codes a due date, an instalment count or a penalty rate; each reads the
profile for its own parcel's jurisdiction. A fourth jurisdiction is a row, not a
patch.

**Proration is re-derived from days actually held.** A test closes two parcels on
the same date in two different regimes and asserts the seller's shares come out in
different proportions — because the fiscal years open six months apart. Seller
share plus buyer share must equal the annual charge at **zero tolerance**: the two
shares settle with two different parties, so a proration that does not sum means
somebody paid twice or nobody paid at all, and which one is not visible from
either side of the closing table.

**Penalty and interest are re-derived, never read off the notice.** The county's
figure is the one being checked, so trusting it would make the control circular.
Penalty attaches once on the whole instalment the moment it is late; interest
accrues per whole 30-day period past the due date; both at the regime's own rates.
The clean baseline includes an instalment settled seven weeks late *on purpose*,
so the arithmetic is exercised rather than merely asserted to be zero.

## Completeness, not just accuracy

`par_plat_completeness` counts live parcels per project against the lot count the
plat created. A plat of forty lots showing thirty-nine parcels is not missing a
bill — it is still being billed for the fortieth somewhere else, usually on the
parent parcel nobody retired. The retired parent is excluded from the count on
purpose; counting it would mask exactly the gap the control looks for.

## Tests

```bash
python -m pytest proptax_engine/tests -q
```

389 tests: a clean baseline parametrized over the registry, 27 planted-defect
files each built to trip one named control, boundary tests on every date and cent
threshold, and read-only/determinism proofs that hash the corpus before and after
a full run.

## The baseline is derived, not typed

Only the regimes, the projects, the parcels' assessed values and the closings are
stated. The generator computes everything the engine later checks as a tie-out:
the annual charge from the levy rate on the assessed value, the instalment split
from the regime's own shares, the due dates from the regime's calendar, penalty
and interest from the days actually late, each closing's proration from the days
held in that regime's fiscal year, the monthly accrual, and the ledger balance
behind it.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The portfolio, the states, the counties, the
projects, the parcel numbers and every assessed value are invented, and the tax
year is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
