# Partnership 1065 Tax Workpapers - 2025 (FICTIONAL)

> Fully synthetic demonstration data. No real taxpayer, partner, EIN, or client figure is included.

**Partnership:** Demo 721 Development LP
**EIN:** 00-0000000
**Package status:** READY FOR REVIEW

## 1. AI-assisted source intake

| Source area | What the system extracts |
|---|---|
| Trial balance / P&L | income, deductions, book depreciation, ordinary income drivers |
| Balance sheet | cash, receivables, property, liabilities, capital tie-out |
| Member capital accounts | beginning capital, contributions, distributions, partner percentages |
| Syndication cost support | nondeductible book/tax adjustment |
| Return PDF / line map | 1065, Schedule K, Schedule L, M-1, M-2, and K-1 output targets |

## 2. Book to tax bridge

| Item | Amount | Source |
|---|---:|---|
| Book income per workpapers | 615,550.00 | Trial balance / P&L |
| Nondeductible syndication costs | 85,000.00 | `SYN-001` |
| Book depreciation addback | 415,000.00 | `TB-7600` |
| Tax depreciation deduction | (462,000.00) | `DEPR-001` |
| **Ordinary business income** | **653,550.00** | Schedule K line 1 |

## 3. Form 1065 line map

| Form | Line | Description | Amount | Source IDs |
|---|---|---|---:|---|
| Form 1065 | 1c | Gross receipts / income | 1,867,500.00 | `TB-4000`, `TB-4900` |
| Form 1065 | 14 | Depreciation | 462,000.00 | `DEPR-001` |
| Form 1065 | 20 | Other deductions | 751,950.00 | `TB-6200`, `TB-6100`, `TB-6350`, `TB-7000`, `TB-7300` |
| Form 1065 | 21 | Total deductions | 1,213,950.00 | `TB-6200`, `TB-6100`, `TB-6350`, `TB-7000`, `TB-7300`, `DEPR-001` |
| Form 1065 | 22 | Ordinary business income | 653,550.00 | `K-ORD` |
| Schedule K | 1 | Ordinary business income | 653,550.00 | `K-ORD` |
| Schedule L | 14 | Total assets | 13,353,550.00 | `BS-CASH`, `BS-REC`, `BS-PROP` |
| Schedule L | 21 | Total liabilities | 8,750,000.00 | `BS-LIAB` |
| Schedule M-1 | 1 | Net income per books | 615,550.00 | `TB-4000`, `TB-4900` |
| Schedule M-1 | 9 | Income per return | 653,550.00 | `K-ORD` |
| Schedule M-2 | 1 | Beginning capital | 2,800,000.00 | `M2-BOY` |
| Schedule M-2 | 2 | Capital contributed | 1,250,000.00 | `M2-CONTRIB` |
| Schedule M-2 | 3 | Net income | 653,550.00 | `K-ORD` |
| Schedule M-2 | 6 | Distributions | 100,000.00 | `M2-DIST` |
| Schedule M-2 | 9 | Ending capital | 4,603,550.00 | `M2-BOY`, `M2-CONTRIB`, `M2-DIST`, `K-ORD` |

## 4. Partner K-1 allocation preview

| Partner | Ordinary income | BOY capital | Contributions | Distributions | EOY capital |
|---|---:|---:|---:|---:|---:|
| Demo Sponsor GP Inc. | 65.36 | 280.00 | 125.00 | 10.00 | 460.36 |
| Maple Institutional Partner LLC | 588,129.64 | 2,519,720.00 | 1,124,875.00 | 89,990.00 | 4,142,734.64 |
| Cedar Class B Investor LLC | 65,355.00 | 280,000.00 | 125,000.00 | 10,000.00 | 460,355.00 |

## 5. Source index

| Source ID | Tab / area | Cell | Label | Amount | Note |
|---|---|---|---|---:|---|
| `TB-4000` | Trial Balance | E12 | Rental revenue | 1,843,000.00 | Pulled from fictional GL export. |
| `TB-4900` | Trial Balance | E12 | Interest income | 24,500.00 | Pulled from fictional GL export. |
| `TB-6200` | P&L | D8 | Management fees | 185,000.00 | Mapped from fictional workpaper detail. |
| `TB-6100` | P&L | D8 | Repairs and maintenance | 74,250.00 | Mapped from fictional workpaper detail. |
| `TB-6350` | P&L | D8 | Real estate taxes | 121,800.00 | Mapped from fictional workpaper detail. |
| `TB-7000` | P&L | D8 | Interest expense | 312,500.00 | Mapped from fictional workpaper detail. |
| `TB-7300` | P&L | D8 | Professional fees | 58,400.00 | Mapped from fictional workpaper detail. |
| `TB-7600` | P&L | D8 | Book depreciation | 415,000.00 | Mapped from fictional workpaper detail. |
| `SYN-001` | Syndication Costs | D8 | Syndication costs | 85,000.00 | Mapped from fictional workpaper detail. |
| `SYN-001` | Book-Tax Adjustments | C14 | Nondeductible syndication costs | 85,000.00 | Schedule M-1 support. |
| `TB-7600` | Book-Tax Adjustments | C14 | Book depreciation addback | 415,000.00 | Schedule M-1 support. |
| `DEPR-001` | Book-Tax Adjustments | C14 | Tax depreciation deduction | (462,000.00) | Schedule M-1 support. |
| `BS-CASH` | Balance Sheet | C9 | Cash | 740,000.00 | Schedule L input. |
| `BS-REC` | Balance Sheet | C10 | Receivables | 90,000.00 | Schedule L input. |
| `BS-PROP` | Balance Sheet | C14 | Property, net | 12,523,550.00 | Schedule L input. |
| `BS-LIAB` | Balance Sheet | C24 | Liabilities | 8,750,000.00 | Schedule L input. |
| `M2-BOY` | Member Capital Accounts | F19 | Beginning capital | 2,800,000.00 | Partner capital rollforward source. |
| `M2-CONTRIB` | Member Capital Accounts | I19 | Capital contributions | 1,250,000.00 | Partner capital rollforward source. |
| `M2-DIST` | Member Capital Accounts | L19 | Distributions | 100,000.00 | Partner capital rollforward source. |
| `K-ORD` | 1065 Line Map | K1 | Ordinary income | 653,550.00 | Mapped to Schedule K and K-1 line 1. |

## 6. CEO / partner-ready summary

The system generated the 1065 workpaper bridge, mapped the workpapers to return lines, allocated Schedule K income to the fictional partners, and ran review checks before marking the package ready for review.
