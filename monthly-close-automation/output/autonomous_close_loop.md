# Autonomous Close Loop — Human-Out-of-the-Loop Remediation [FICTIONAL]

> 🔒 Fictional, seeded data. The loop drives a *drifted* posted close back to a certifiable state by resyncing each recurring-entry category to the seeded sub-ledger of record — then posts on its own authority, quarantining what it cannot certify.

**Verdict: ⚑ AUTO-POSTED (PARTIAL)** — The current period was posted autonomously. Some scope could not be certified without authority the loop does not have, so it was quarantined and logged rather than acted on.

- Period **2026-03** (seed 2026)
- Injected drift: **5** fault(s) · initial findings: **19**
- Remediation turns: **4** / budget **10** · categories resynced: **prepaid amortization, mgmt fee accrual, note interest, gna allocation**
- Adjustments booked: **11** · gross movement **33,000.04**
- Quarantined: **1** · halted-on: **0**

## Injected drift (the contaminated close)

| Fault | Control | Root cause |
|-------|---------|------------|
| `interco_one_sided` | `C2` | Intercompany note lost its far leg — the lender mirror was dropped |
| `missing_recurring_entry` | `C3` | An expected recurring accrual is silently absent from the register |
| `rounded_total_leg` | `C8` | A clearing leg booked as round(total) instead of the sum of rounded lines |
| `shadow_tamper` | `C9` | One posted amount is off by a single cent from the sub-ledger |
| `prior_period_mutation` | `C10` | A signed-off, locked prior period was quietly rewritten |

## The loop, turn by turn

### Turn 1 — resync `prepaid amortization`  ·  cleared C9  ·  18 → 16 critical

| Entity | Account | From Dr/Cr | To Dr/Cr | Δ Dr | Δ Cr |
|--------|---------|-----------:|---------:|-----:|-----:|
| DH | 1400 | 0.00/1,700.01 | 0.00/1,700.00 | 0.00 | -0.01 |
| DH | 6400 | 1,200.01/0.00 | 1,200.00/0.00 | -0.01 | 0.00 |

### Turn 2 — resync `mgmt fee accrual`  ·  cleared C3, C9  ·  16 → 9 critical

| Entity | Account | From Dr/Cr | To Dr/Cr | Δ Dr | Δ Cr |
|--------|---------|-----------:|---------:|-----:|-----:|
| BW | 1000 | 0.00/0.00 | 0.00/3,000.00 | 0.00 | 3,000.00 |
| BW | 2300 | 0.00/0.00 | 0.00/5,000.00 | 0.00 | 5,000.00 |
| BW | 6200 | 0.00/0.00 | 8,000.00/0.00 | 8,000.00 | 0.00 |
| MF | 2300 | 0.00/0.00 | 0.00/6,000.00 | 0.00 | 6,000.00 |
| MF | 6200 | 0.00/0.00 | 6,000.00/0.00 | 6,000.00 | 0.00 |

### Turn 3 — resync `note interest`  ·  cleared C2, C7, C9  ·  9 → 6 critical

| Entity | Account | From Dr/Cr | To Dr/Cr | Δ Dr | Δ Cr |
|--------|---------|-----------:|---------:|-----:|-----:|
| MF | 1800 | 0.00/0.00 | 2,500.00/0.00 | 2,500.00 | 0.00 |
| MF | 4900 | 0.00/0.00 | 0.00/2,500.00 | 0.00 | 2,500.00 |

### Turn 4 — resync `gna allocation`  ·  cleared C2, C5, C8, C9  ·  6 → 1 critical

| Entity | Account | From Dr/Cr | To Dr/Cr | Δ Dr | Δ Cr |
|--------|---------|-----------:|---------:|-----:|-----:|
| DH | 1800 | 9,000.01/0.00 | 9,000.00/0.00 | -0.01 | 0.00 |
| DH | 6650 | 0.00/15,000.01 | 0.00/15,000.00 | 0.00 | -0.01 |

## Held, not acted on

- **QUARANTINE** `C10` — closed period mutated (held + logged; not auto-overwritten)

## Why it's defensible

Autonomous does not mean ungated. The loop never invents a number: every correction is the engine's own re-derivation from the seeded sub-ledger of record, and every movement is booked as an adjustment. The ten controls remain the acceptance test — the loop only posts once they are silent over the non-quarantined scope. What it cannot certify with authority it has (a broken opening carryforward) or should not overwrite (a signed-off locked period) is held and logged, not acted on. The verdict doubles as a CI exit code.
