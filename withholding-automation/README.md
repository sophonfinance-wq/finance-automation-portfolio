# Non-resident withholding & 1042-S automation

A deterministic, **read-only** control engine for a US withholding agent's
non-resident (Chapter 3/4 FDAP) withholding and Form 1042 / 1042-S reconciliation
— every cross-border interest, dividend, royalty and rent payment proved, payment
by payment, to be rated from the payee's status and the treaty table, every
reduced rate supported by a valid Form W-8, the deposits tied to the liability, and
the annual Form 1042 tied to the 1042-S slips it transmits.

A withholding determination is a snapshot of a payee's status on the day a payment
went out, and it goes stale — or was wrong to begin with — in ways nobody watches.
Four failures hide inside a folder of withholding workpapers, and none of them look
wrong.

**The rate is reduced without support.** A payment is withheld at a treaty rate
while the W-8 that would support it is missing or expired past its three-year term.
The paper shows a low rate; the support for it is not there.

**The classification is off.** A US payee is withheld on when it should not be; an
accrued-but-unpaid coupon is treated as paid; a non-participating FFI is given
treaty relief it is barred from; a contingent coupon is coded as exempt portfolio
interest.

**The deposit drifts from the liability.** The tax withheld across the year does
not equal what was deposited, or the annual return is filed after its due date.

**The return does not tie to the slips.** The Form 1042 total gross or total tax
does not equal the sum of the 1042-S slips, or a reportable payee has no slip.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 28 controls, writes
`nrw_report.json` and `nrw_report.md`, and exits with the verdict code. The corpus
contains planted defects on purpose, so a non-zero exit is the engine working.

## The 28 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the withholding file complete, and is the review date readable? |
| `payee_` | 5 | Are the payee ids unique, is each foreign payee's country in the rate table, are the Chapter 3/4 status and LOB codes classified? |
| `rate_`  | 2 | Does the treaty table define every (country, income-type) rate a payment needs, and is every rate within statutory bounds? |
| `pay_`   | 4 | Is every payment well-formed, coded to a known income code, attributable to a payee, and of a known status? |
| `wh_`    | 4 | Is the US payee excluded and the accrued coupon un-withheld, does each applied rate recompute from the payee's status, and does each tax equal rate × gross? |
| `exm_`   | 5 | Is every treaty reduction supported by an unexpired W-8 (with a renewal flag), is portfolio interest non-contingent, and does the FATCA override force statutory? |
| `dep_`   | 2 | Do the deposits tie the tax withheld, and was Form 1042 filed on time? |
| `rec_`   | 5 | One slip per reportable payee, 1042 gross and tax tied to the slips, the 1042-T count tied to the slips, and the W-8 watchlist tied to the evidence? |

Three are worth calling out.

**The rate recomputes, it is not read back.** `wh_rate_recomputes` is the control
the engine exists for. The rate applied to a payment is a *determination* — FATCA
override, then the portfolio-interest exemption, then a treaty rate behind a valid
W-8, then the statutory default — and a determination that is not recomputed from
the evidence is an assertion. The engine rebuilds every rate through the shared
kernel and compares.

**The order of precedence is the whole of the rule.** A payment can qualify for
several reductions at once, and they do not commute: a non-participating FFI that
also holds a treaty claim is withheld at the statutory rate, not the treaty rate.
`exm_fatca_override` and `exm_portfolio_interest_eligible` hold the boundaries the
kernel encodes.

**Every total ties to the cent.** `dep_total_ties_withheld`, `rec_gross_ties` and
`rec_withheld_ties` compare with exact `==` in integer cents. A deposit a cent
short of the liability is an under-deposit; a 1042 total a cent off the slips is a
return that reports a different number than the slips underneath it.

## The renewal window is a flag, not a failure

`exm_w8_renewal_window` marks a payee whose W-8 expires inside the file's own
lead-time window: the form is still valid, but a fresh one needs to be collected
before it lapses. `rec_w8_watchlist_ties` proves the stated watchlist is exactly
the set of payees actually due. Both are `REVIEW`-severity: worth a human's eyes,
not a hard stop.

## Tests

```bash
python -m pytest withholding_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent, basis point and date threshold, and
read-only / determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the payees, the treaty table, the income-code table, the payment base facts
(gross, income code, sub-character, status) and the deposits are stated. The
generator computes everything the engine later checks as a determination or rollup
— each payment's applied rate and tax withheld, the 1042-S slips, the Form 1042
totals, the W-8 renewal watchlist — the rate through the *same* withholding kernel
the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The filers, the foreign payees, the jurisdictions,
the banks and benefit providers, the treaty rates and every amount are invented,
and the reporting period is set in a fictional future. No employer or client
workpaper, entity, methodology, path or figure is reproduced.
