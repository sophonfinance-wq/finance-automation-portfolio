# Surplus Assurance Loop — Continuous Reconciliation [FICTIONAL]

> 🔒 Fictional data. The loop drives a *drifted* workpaper set back to a clean structural tie-out by re-deriving each fiscal period from cited source facts — one locked period at a time — then hands a verdict to a human.

**Verdict: ⚑ FLAG** — Converged, but material adjustments were booked. A human must review what changed before sign-off, even though every identity now ties.

- Fiscal range **2021–2024** · **212** structural identity checks per pass
- Injected drift: **3** fault(s) · initial breaks: **6**
- Remediation turns: **3** / budget **6** · periods locked: **2021, 2022, 2023**
- Adjustments booked: **4** · total magnitude **CAD 107,088.50** · materiality **CAD 1,000.00**
- Converged: **yes**

## Injected drift (the contaminated workpapers)

| Fault | Entity | FY | Root cause | Control that must catch it |
|-------|--------|----|------------|----------------------------|
| `F1-MISKEY-CLOSE` | Cedar Mezz Holdings LLC | 2021 | Fat-fingered closing cell: exempt surplus overstated on the 2021 workpaper | `exempt_conservation + continuity_exempt` |
| `F2-UNSUPPORTED-ELEVATION` | Maple Fund LP | 2022 | Intercompany elevation booked at the fund with no subsidiary distribution to support it | `elevation_exempt` |
| `F3-ACB-MISKEY` | Cedar Mezz Holdings LLC | 2023 | Mis-keyed ACB balance on the 2023 mezzanine workpaper | `acb_conservation + continuity_acb` |

## The loop, turn by turn

### Turn 1 — lock FY2021  ·  6 break(s) in → 4 out (2 cleared)

| Entity | FY | Field | From | To | Δ (FC) | Δ (CAD) |
|--------|----|-------|-----:|---:|-------:|--------:|
| Cedar Mezz Holdings LLC | 2021 | `closing.exempt_surplus` | 749,503.61 | 699,503.61 | (50,000.00) | 65,750.00 |

### Turn 2 — lock FY2022  ·  4 break(s) in → 2 out (2 cleared)

| Entity | FY | Field | From | To | Δ (FC) | Δ (CAD) |
|--------|----|-------|-----:|---:|-------:|--------:|
| Maple Fund LP | 2022 | `closing.exempt_surplus` | 113,173.49 | 105,173.49 | (8,000.00) | 10,632.00 |
| Maple Fund LP | 2022 | `elevated_exempt` | 8,000.00 | 0.00 | (8,000.00) | 10,632.00 |

### Turn 3 — lock FY2023  ·  2 break(s) in → 0 out (2 cleared)

| Entity | FY | Field | From | To | Δ (FC) | Δ (CAD) |
|--------|----|-------|-----:|---:|-------:|--------:|
| Cedar Mezz Holdings LLC | 2023 | `closing.acb` | 50,502.71 | 35,502.71 | (15,000.00) | 20,074.50 |

## How it works

Each turn the loop **observes** (runs the reconciliation harness), **detects** the earliest fiscal period that still fails an identity, **remediates** it by re-deriving the period from source facts via the engine (booking every field change as an adjustment), locks the period, and **re-verifies**. It repeats until all identities across every period and tier reconcile — or the turn budget is exhausted. The loop never invents a number: the final workpaper set is byte-identical to a clean engine run. A human gate returns PASS / FLAG / FAIL.
