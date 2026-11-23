# 🏦 Cash Management

Five **validation-only** controls that model a cash manager's monthly close — the
independent double-check a controller relies on before cash is trusted. Each is
read-only, holds every amount in **integer cents**, is fully deterministic, and
ends at **READY FOR HUMAN REVIEW**. None of them post, draft a journal entry, or
write back to any source system. All data is invented.

## The five controls

| Module | Control |
|---|---|
| `cash_engine.bank_rec` | **Bank → GL bridge.** Bank ending + deposits in transit − outstanding checks ± approved error plugs must equal the adjusted book balance. Error plugs are review-gated. |
| `cash_engine.outstanding_checks` | **Outstanding / void / stale check register.** Per-account check-number uniqueness, void-amount rules, aging against a stale-date policy, and an independently re-added outstanding total. |
| `cash_engine.wire_approval` | **Wire dual-approval / segregation of duties.** No approved or scheduled wire without two distinct approvers, both different from the initiator; scheduling discipline. |
| `cash_engine.bank_register` | **Running-balance continuity.** Every running balance re-derived row by row; closing foots; opening ties to prior close; optional bank statement tie-out. |
| `cash_engine.cash_concentration` | **Concentration sweep tie-out.** Sub-account sweeps re-added to the concentration inflow; opening + sweeps − disbursements re-derived to the displayed close. |

## ▶️ Run it

```bash
# from this folder (cash-management/)
python -m cash_engine --demo     # runs all five controls on seeded fictional data

# tests
python -m pytest                 # behaviour suites + a 5,000-case invariant grid
```

## How the tests prove it

Each control ships a behaviour suite plus a shared **curated invariant grid**
(`cash_engine/tests/test_curated_invariant_grid.py`, 5,000 parametrized cases).
Every grid point drives a validator **end-to-end twice**: once on an input
constructed to tie (must come back mechanically clean) and once on a one-cent (or
one-field) tamper of the same input (must trip the exact finding code). A stub
that always passes — or always fails — cannot survive any point of the grid.

## Boundary

Every example uses fictional entities ("Cedar Demo LLC"), an invented bank
("Demo National Bank"), and invented amounts. No employer or client balance,
entity, bank, path, or workpaper coordinate appears anywhere in this package.
Mechanical cleanliness is only a **precondition** for human review — never a
sign-off, and never a posting authorization.
