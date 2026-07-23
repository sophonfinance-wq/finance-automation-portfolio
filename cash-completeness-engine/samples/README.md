# Sample dataset - 100% fictional

> All entities, banks, account numbers, GL codes, and amounts below are
> invented for demonstration. Any resemblance to real organizations is
> coincidental.

**Story.** A mid-year bank migration from **First Legacy Bank** (legacy) to
**Union National Bank** (successor), with one account at **Coastal Mutual**.
The trial balance was cut as of **2026-06-30**; the register extracts cover
the full bank-side population, including accounts the TB never picked up.
A trial-balance-first tie-out looks clean; a bank-side-first tie-out finds
five exception classes.

## Register population (`registers/*.csv`)

Each CSV is one bank account: `#`-prefixed metadata (entity, bank,
bank_account_no, gl_account, status, as_of) followed by transaction rows
`date,description,amount,running_balance,counterparty`.

| File | Entity | Bank | GL (as keyed) | Register bal | Expected class |
|---|---|---|---|---:|---|
| juniper42_union_national_operating.csv | Juniper 42 Development LLC | Union National | 615-001-00-1010 | 187,442.19 | clean tie |
| bluffside9_coastal_mutual_operating.csv | Bluffside 9 Townhomes LLC | Coastal Mutual | 309-001-1010 | 42,918.55 | clean tie |
| saltgrass6_union_national_operating.csv | Saltgrass 6 Services LLC | Union National | 7060011010 (undashed) | 9,633.02 | clean tie |
| juniper42_union_national_deposit.csv | Juniper 42 Development LLC | Union National | 424-002-00-1020 | 63,205.88 | A - unmapped successor |
| wrenfield28_union_national_operating.csv | Wrenfield 28 Development LLC | Union National | 628-001-00-1010 | 154,777.40 | A - unmapped successor |
| harbor17_union_national_operating.csv | Harbor 17 Investor LLC | Union National | 417-001-00-1010 | 28,090.12 | A - unmapped successor |
| bluffside9_first_legacy_project_closed.csv | Bluffside 9 Townhomes LLC | First Legacy | 309-002-00-1015 | 0.00 (closed) | B - stale close-out (simple sweep) |
| wrenfield28_first_legacy_development_closed.csv | Wrenfield 28 Development LLC | First Legacy | 628-002-00-1015 | 0.00 (closed) | B - stale close-out (two-member waterfall) |
| kestrel_union_national_operating.csv | Kestrel Capital Partners LLC | Union National | 501-001-00-1010 | 96,155.75 | C - timing (25,000.00 deposit dated 2026-07-01) |
| demoholdings_coastal_mutual_moneymarket.csv | Demo Holdings LLC | Coastal Mutual | 001-001-00-1015 | 12,406.90 | ties, but placeholder GL key (mis-keyed) |

## Trial balance (`trial_balance.csv`)

Cash lines only, as of 2026-06-30. Notable rows:

- `309-002-1015` (75,310.66) and `628-002-00-1015` (231,000.00) - **stale
  close-out balances**; the registers show fully traced sweeps to zero
  (`Transfer to Kestrel Capital Partners LLC` / `To close account`, and a
  60/40 waterfall `Wire to Harbor 17 Investor LLC` + `Wire to Demo Holdings
  LLC` / `Close account`).
- `501-001-1010` (71,155.75) - differs from the register by exactly the
  post-cutoff 25,000.00 deposit (**timing**).
- `760-001-1010` (5,118.27) - **phantom row**: digit-transposed typo of the
  real Saltgrass GL `706-001-1010`; no register has ever matched it.
- `001-001-1015` (12,406.90) - ties to the register, but the GL key is a
  placeholder pattern (`001-001-...`) that `is_placeholder_gl` should flag.
- The three live Union National successor accounts have **no TB row at
  all** - the completeness gap a TB-first reconciliation cannot see.

GL formats deliberately vary (`615-001-00-1010`, `309-001-1010`,
`7060011010`) to exercise `normalize_gl`.
