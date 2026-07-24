# Surety bond & collateral automation

A deterministic, **read-only** control engine for a residential developer's surety
bond programme — the lifecycle of each bond, the cash posted as collateral behind
it, and the aggregate exposure it consumes.

A developer cannot pull a permit, record a plat or turn a street over to a city
without posting surety, so the bonds accumulate: a statutory licence bond per
operating entity, a performance bond per set of subdivision improvements, a
maintenance bond running through the warranty period after the city accepts the
work, a street-use bond for the right of way. Each carries its own obligee, term
and premium — and some are collateralised with the developer's own cash.

The failure mode is quiet, and it runs in both directions.

**Cash that never comes back.** A bond does its job, the city accepts the work,
the obligation ends, the register is marked released — and nobody writes to the
surety. The collateral stays where it is. It raises no payable, ages on no report,
and sits in restricted cash looking exactly like cash. Nothing in the ordinary
accounting cycle notices, because the money is not *owed*; it is already paid.

**Capacity nobody is using.** The mirror image is a bond nobody released. Premium
keeps renewing on an obligation that ended two years ago, and the penal sum keeps
consuming the aggregate limit of the indemnity agreement — so the next project's
bond is declined for capacity the programme does not actually need.

The controls here are lifecycle controls. A bond has a beginning, a term, an
obligation it secures and an end; the collateral, the premium and the exposure
each have to follow that lifecycle, and each is tested against it rather than
against itself.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 29 controls, writes
`bond_report.json` and `bond_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 29 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the programme file complete, and is the review date readable? |
| `reg_`  | 5 | Is the register sound: unique numbers, real projects, terms that run forwards? |
| `stat_` | 3 | Does each bond meet its statute and sit with the right obligee? |
| `life_` | 7 | Is the bond in force, continuously renewed, and released only when the obligation ended? |
| `coll_` | 6 | Did the collateral follow the bond — and did it come back? |
| `prem_` | 5 | Is the premium rated, amortised, and stopped at release? |
| `expo_` | 2 | Does aggregate exposure fit inside the facility, and does the summary foot? |

Four are worth calling out.

**A released bond may not hold collateral in silence.**
`life_no_release_while_collateral_outstanding` is the control the programme exists
for. It does not ask for the cash to already be back — a refund genuinely in
flight is normal, and says so in `collateral_refund_status`. It asks that
*something is chasing it*. Silence is the failure. In the corpus, dropping a
single refund entry leaves $34,250 with the surety on a bond the obligee
discharged 198 days earlier, and the control names it.

**Collateral is tied three ways at once.** It can never exceed the penal sum it
supports (`coll_not_exceed_penal_sum`); the register's outstanding balance must
equal postings less refunds (`coll_ledger_ties_register`); and the total must
equal the restricted-cash balance on the general ledger
(`coll_ties_restricted_cash_gl`). The register can agree with its own ledger and
still disagree with the balance sheet — and it is the balance sheet that gets
audited. All three compare at **zero tolerance**.

**Renewal continuity, not renewal existence.** `life_renewal_continuity` fails on
a gap between the old term ending and the new one starting. Both bonds look
perfectly valid on their own; the unbonded window only exists *between* them, and
it is exactly the window a claim would land in. A boundary test asserts that a
renewal starting the day after expiry passes and one starting a day later fails.

**The clock is stated, never sampled.** Every expiry, ageing and horizon test is
made against an `as_of` date carried *in the programme file*. The engine never
calls `date.today()`. A control whose answer changed tomorrow could not be
diffed, cached or reproduced — and the committed report would churn on every run.

## Tolerance

One control is deliberately tolerant, and says so. `prem_rate_within_schedule`
compares premium charged against the rate card applied to the penal sum, floored
at the surety's minimum premium — but sureties do adjust for credit and term, so
an exact match is not expected. The tolerance comes **from the rate schedule**,
not from the engine's opinion, and the control is a FLAG rather than a FAIL.
Everything else compares with exact `==`.

## Tests

```bash
python -m pytest bond_engine/tests -q
```

420 tests. The suite is in four parts:

- **Clean baseline** — parametrized over the registry, so a regression names the
  control that broke rather than reporting that something in a 29-rule registry is
  unhappy. The clean file must produce *no* findings at all, not even a flag.
- **Planted defects** — 30 files, each carrying exactly one defect built to trip
  one named control. A test asserts every registered rule has a defect that
  demonstrates it firing, and that no defect targets a rule that does not exist.
- **Control semantics** — boundary tests. A control that fires a day early is as
  wrong as one that never fires, and only a boundary test tells them apart:
  collateral may *equal* the penal sum but not exceed it by a cent; a maintenance
  bond may be released the day the warranty ends but not the day before; exposure
  may reach the facility limit but not pass it.
- **Read-only and determinism** — the source corpus is hashed before and after a
  full run and must be byte-identical; the generator is re-run and must produce
  the same bytes; the rendered reports must carry no timestamp or absolute path.

## The baseline is derived, not typed

Only the facility, the rate card, the statutory minimums, the projects, the bonds
and the two ledgers are stated. Every figure the engine later checks as a *tie-out*
is computed by the generator from those inputs: each bond's premium from the rate
card, its outstanding collateral from the postings against it, restricted cash
from the ledger as a whole, prepaid premium straight-line to the review date, and
the exposure summary from the bonds still active.

So the relationships the engine tests are the same relationships that produced the
data. A defect that changes a *base* fact re-derives everything downstream, which
keeps the break confined to the one control it was built for; a defect that
targets a tie-out edits the stated figure alone.

---

🔒 **All data is fictional.** The developer, its surety, the states, the cities,
the projects, the bond numbers and every amount are invented, and the review
period is set in a fictional future. No employer or client workpaper, entity,
methodology, path or figure is reproduced.
