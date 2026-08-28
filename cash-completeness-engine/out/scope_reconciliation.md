# Scope Reconciliation - Cash Completeness [FICTIONAL DATA]

**As of:** 2026-06-30 &nbsp;|&nbsp; **Register population:** 10 accounts, 594,629.81 &nbsp;|&nbsp; **TB cash rows:** 8, 634,985.34

> Population is built from the bank side (registers), not the trial balance. A TB-first reconciliation cannot see accounts the TB is missing; this schedule proves every register account landed in exactly one bucket.

## Buckets

| Bucket | Accounts | Total |
|--------|---------:|------:|
| exceptions_A | 3 | 246,073.40 |
| exceptions_B | 2 | 0.00 |
| exceptions_C | 1 | 96,155.75 |
| exceptions_D | 0 | 0.00 |
| tb_matched_ties | 4 | 252,400.66 |
| **All buckets** | **10** | **594,629.81** |

## Bucket membership

### exceptions_A (3 accounts)

- `417-001-1010`
- `424-002-1020`
- `628-001-1010`

### exceptions_B (2 accounts)

- `309-002-1015`
- `628-002-1015`

### exceptions_C (1 accounts)

- `501-001-1010`

### exceptions_D (0 accounts)

- (none)

### tb_matched_ties (4 accounts)

- `001-001-1015`
- `309-001-1010`
- `615-001-1010`
- `706-001-1010`

## Foot check

- PASS: every register account appears in exactly one bucket and the bucket totals re-add to the register population.

## Placeholder / mis-keyed GL keys (1)

> These register accounts tie to the trial balance and stay in their scope bucket above, but their GL key matches a mis-keyed placeholder pattern (e.g. `001-001-...`). A key like this can foot perfectly and still be wrong; give each one a human look before sign-off.

| Entity | Bank | GL (raw) | GL (normalized) | Register balance |
|--------|------|----------|-----------------|-----------------:|
| Demo Holdings LLC | Coastal Mutual | `001-001-00-1015` | `001-001-1015` | 12,406.90 |
