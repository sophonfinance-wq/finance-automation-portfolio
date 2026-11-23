# ACB FX — Single-Rate vs Per-Layer [FICTIONAL]

> 🔒 Fictional entities and amounts. Illustrates the public ITA 261 / Reg. 5907 principle that each ACB layer is translated at its own year's rate; not real data or methodology.

ACB is built from capital events in different years. Translating the net closing balance at one rate (the Summary-layer convention) assumes every layer arose at that rate. Translating each layer at its own year's rate is the correct treatment — and can change the CAD figure's magnitude or sign.

| Entity | Cur | Closing ACB (FC) | Single-rate ACB (CAD) | Per-layer ACB (CAD) | Divergence (CAD) | Sign flip | FC ties |
|--------|-----|----------------:|----------------------:|--------------------:|-----------------:|:---------:|:-------:|
| Birchwood Op Co | USD | 0.00 | 0.00 | 0.00 | 0.00 | — | ✓ |
| Cedar Mezz Holdings LLC | USD | 0.00 | 0.00 | (660.35) | (660.35) | ⚑ yes | ✓ |
| Maple Fund LP | USD | 0.00 | 0.00 | 0.00 | 0.00 | — | ✓ |
| Demo Holdings Inc. | CAD | 0.00 | 0.00 | 0.00 | 0.00 | — | ✓ |

_FC ties = signed functional-currency layers sum back to the engine's closing ACB (the per-layer model cannot drift from the engine). ⚑ = per-layer and single-rate CAD figures have opposite signs._

## Layer detail

### Cedar Mezz Holdings LLC (USD)

| FY | Event | Amount (FC) | Rate | Signed (CAD) |
|----|-------|------------:|-----:|-------------:|
| 2023 | Contribution | 35,502.71 | 1.3383 | 47,513.28 |
| 2024 | Return of capital | 35,502.71 | 1.3569 | (48,173.63) |
| | **Per-layer ACB (CAD)** | | | **(660.35)** |
| | _Single-rate ACB (CAD)_ | | 1.3569 | _0.00_ |
