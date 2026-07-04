# Journal Entry Register — 2026-03

_Seed 2026. 7 entries posted; 0 refused (out of tie)._

## JE-2026-03-PREPAID — Prepaid amortization (straight-line)

- Category: `prepaid_amortization`
- Control: debits 3,400.00 == credits 3,400.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| DH | 6400 · Insurance expense | PP-01 2026-03 amortization | 1,200.00 |  |
| DH | 1400 · Prepaid expenses | Relieve prepaid PP-01 |  | 1,200.00 |
| MF | 6500 · Software expense | PP-02 2026-03 amortization | 1,200.00 |  |
| MF | 1400 · Prepaid expenses | Relieve prepaid PP-02 |  | 1,200.00 |
| BW | 5000 · Cost of services | PP-03 2026-03 amortization | 500.00 |  |
| BW | 1400 · Prepaid expenses | Relieve prepaid PP-03 |  | 500.00 |
| DH | 6650 · G&A - shared services | PP-04 2026-03 amortization | 500.00 |  |
| DH | 1400 · Prepaid expenses | Relieve prepaid PP-04 |  | 500.00 |
| | | **Totals** | **3,400.00** | **3,400.00** |

## JE-2026-03-DEPREC — Fixed-asset depreciation (straight-line, monthly)

- Category: `depreciation`
- Control: debits 9,000.00 == credits 9,000.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| DH | 6100 · Depreciation expense | FA-01 2026-03 | 750.00 |  |
| DH | 1510 · Accumulated depreciation | Accum. dep. FA-01 |  | 750.00 |
| MF | 6100 · Depreciation expense | FA-02 2026-03 | 2,500.00 |  |
| MF | 1510 · Accumulated depreciation | Accum. dep. FA-02 |  | 2,500.00 |
| BW | 6100 · Depreciation expense | FA-03 2026-03 | 2,500.00 |  |
| BW | 1510 · Accumulated depreciation | Accum. dep. FA-03 |  | 2,500.00 |
| DH | 6100 · Depreciation expense | FA-04 2026-03 | 1,250.00 |  |
| DH | 1510 · Accumulated depreciation | Accum. dep. FA-04 |  | 1,250.00 |
| MF | 6100 · Depreciation expense | FA-05 2026-03 | 2,000.00 |  |
| MF | 1510 · Accumulated depreciation | Accum. dep. FA-05 |  | 2,000.00 |
| | | **Totals** | **9,000.00** | **9,000.00** |

## JE-2026-03-LEASE — Deferred rent + CAM straight-lining (intercompany split)

- Category: `deferred_rent_cam`
- Control: debits 17,812.50 == credits 17,812.50 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| DH | 6000 · Rent expense | LSE-01 rent share | 5,187.50 |  |
| DH | 6050 · CAM expense | LSE-01 CAM share | 750.00 |  |
| DH | 1800 · Due from affiliates | Due from affiliates (lease cost share) | 5,937.50 |  |
| DH | 2200 · Deferred rent liability | Deferred rent liability build |  | 375.00 |
| DH | 2100 · Accrued liabilities | Accrued lease cash obligation |  | 11,500.00 |
| MF | 6000 · Rent expense | LSE-01 rent share | 3,112.50 |  |
| MF | 6050 · CAM expense | LSE-01 CAM share | 450.00 |  |
| MF | 2800 · Due to affiliates | Due to affiliate (lease cost share) |  | 3,562.50 |
| BW | 6000 · Rent expense | LSE-01 rent share | 2,075.00 |  |
| BW | 6050 · CAM expense | LSE-01 CAM share | 300.00 |  |
| BW | 2800 · Due to affiliates | Due to affiliate (lease cost share) |  | 2,375.00 |
| | | **Totals** | **17,812.50** | **17,812.50** |

## JE-2026-03-MGMTFEE — Management-fee accrual (net of in-month payments)

- Category: `mgmt_fee_accrual`
- Control: debits 14,000.00 == credits 14,000.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| BW | 6200 · Management fee expense | MGT-01 monthly management fee | 8,000.00 |  |
| BW | 1000 · Cash | MGT-01 in-month payment |  | 3,000.00 |
| BW | 2300 · Management fee payable | MGT-01 fee payable |  | 5,000.00 |
| MF | 6200 · Management fee expense | MGT-02 monthly management fee | 6,000.00 |  |
| MF | 2300 · Management fee payable | MGT-02 fee payable |  | 6,000.00 |
| | | **Totals** | **14,000.00** | **14,000.00** |

## JE-2026-03-INTEREST — Related-party note interest accrual

- Category: `note_interest`
- Control: debits 6,875.00 == credits 6,875.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| BW | 6300 · Interest expense | NOTE-01 interest expense | 2,500.00 |  |
| BW | 2400 · Accrued interest payable | NOTE-01 accrued interest |  | 2,500.00 |
| MF | 1800 · Due from affiliates | NOTE-01 interest receivable | 2,500.00 |  |
| MF | 4900 · Intercompany interest income | NOTE-01 interest income |  | 2,500.00 |
| MF | 6300 · Interest expense | NOTE-02 interest expense | 937.50 |  |
| MF | 2400 · Accrued interest payable | NOTE-02 accrued interest |  | 937.50 |
| DH | 1800 · Due from affiliates | NOTE-02 interest receivable | 937.50 |  |
| DH | 4900 · Intercompany interest income | NOTE-02 interest income |  | 937.50 |
| | | **Totals** | **6,875.00** | **6,875.00** |

## JE-2026-03-GNA — G&A cost allocation (fixed ratio, sums to 100%)

- Category: `gna_allocation`
- Control: debits 24,000.00 == credits 24,000.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| DH | 6600 · G&A - allocated | Allocated G&A share | 6,000.00 |  |
| DH | 6650 · G&A - shared services | Relieve shared-services pool |  | 15,000.00 |
| DH | 1800 · Due from affiliates | Due from affiliates (G&A allocation) | 9,000.00 |  |
| MF | 6600 · G&A - allocated | Allocated G&A share | 5,250.00 |  |
| MF | 2800 · Due to affiliates | Due to affiliate (G&A allocation) |  | 5,250.00 |
| BW | 6600 · G&A - allocated | Allocated G&A share | 3,750.00 |  |
| BW | 2800 · Due to affiliates | Due to affiliate (G&A allocation) |  | 3,750.00 |
| | | **Totals** | **24,000.00** | **24,000.00** |

## JE-2026-03-INSUR — Insurance premium allocation (shared policies)

- Category: `insurance_allocation`
- Control: debits 2,600.00 == credits 2,600.00 (ties)

| Entity | Account | Memo | Debit | Credit |
|--------|---------|------|------:|-------:|
| DH | 6400 · Insurance expense | POL-01 2026-03 insurance amortization | 573.50 |  |
| DH | 1450 · Prepaid insurance | Relieve prepaid insurance POL-01 |  | 573.50 |
| MF | 6400 · Insurance expense | POL-01 2026-03 insurance amortization | 542.50 |  |
| MF | 1450 · Prepaid insurance | Relieve prepaid insurance POL-01 |  | 542.50 |
| BW | 6400 · Insurance expense | POL-01 2026-03 insurance amortization | 434.00 |  |
| BW | 1450 · Prepaid insurance | Relieve prepaid insurance POL-01 |  | 434.00 |
| MF | 6400 · Insurance expense | POL-02 2026-03 insurance amortization | 630.00 |  |
| MF | 1450 · Prepaid insurance | Relieve prepaid insurance POL-02 |  | 630.00 |
| BW | 6400 · Insurance expense | POL-02 2026-03 insurance amortization | 420.00 |  |
| BW | 1450 · Prepaid insurance | Relieve prepaid insurance POL-02 |  | 420.00 |
| | | **Totals** | **2,600.00** | **2,600.00** |
