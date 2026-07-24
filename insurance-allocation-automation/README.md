# Insurance cost allocation automation

A deterministic, **read-only** control engine for a residential developer's
insurance programme — the master premium apportioned across every project's job
cost, the builder's risk written over what is under construction, and the carrier
audit true-up that lands months after the term.

A developer does not buy insurance per project. It buys a programme: a general
liability tower, a builder's risk policy over whatever is under construction, an
excess layer above the primary. One premium arrives, and it has to become a number
on each project's job cost — correctly, reproducibly, and summing back to what was
actually paid.

Three failures hide inside that, and none of them look wrong in a column of
six-figure numbers.

**The residual cent.** Any allocation of one amount across N projects leaves a
remainder. Dropped, the allocation no longer sums to the premium; assigned twice,
it sums to a penny more. Neither is visible, and both make a job-cost tie-out fail
for a reason nobody can source.

**The basis drifts from the data.** A project joins mid-term, or the basis value
behind it was never filled in, and the weights quietly redistribute across
whatever remains — so every *other* project's share moves too. The total still
ties. Every individual share is wrong.

**The audit goes to the wrong year.** Carriers audit after the term and issue
additional or return premium months later. The projects that bore the deposit are
not necessarily the projects open when the credit arrives — some have closed.
Crediting whoever is open today takes money from the wrong job.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 24 controls, writes
`insurance_report.json` and `insurance_report.md`, and exits with the verdict
code. The corpus contains planted defects on purpose, so a non-zero exit is the
engine working.

## The 24 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the programme file complete, and is the review date readable? |
| `pol_`   | 5 | Is the policy register sound, and does the tower hold together with no gap? |
| `alloc_` | 7 | Does every share re-derive from its declared basis, to the cent, and reach only the projects the policy covers? |
| `br_`    | 3 | Does builder's risk cover the right things, for the right term, at a value that tracks the budget? |
| `aud_`   | 4 | Did the audit true-up go back to the projects that bore the deposit, on the basis they bore it? |
| `gl_`    | 3 | Does the allocation reach job cost, and does the prepaid and programme total tie the ledger? |
| `rpt_`   | 1 | Does the per-unit metric in the board pack recompute? |

Three are worth calling out.

**The share re-derives, it is not read back.** `alloc_shares_recompute` is the
control the engine exists for. Summing to the premium is necessary and not
sufficient: an allocation can foot perfectly while the leftover penny sits on the
wrong project. The engine re-derives every share by the same largest-remainder
method that should have produced it and compares each one exactly — so the penny
is checked where it landed, not merely counted. Its footing sibling
`alloc_sums_to_premium` catches the other failure: a share moved without a
compensating move, where a real penny of premium is sitting on no project at all.

**The basis is a choice, and the choice is data.** `alloc_basis_data_complete`
catches the quietest failure of all: a covered project whose basis value never
arrived drops out of the weighting and silently moves every other project's share,
while the total still ties. Each basis — hard cost, insured value, unit count — is
a field on the project register, so adding one is a column, never a change to a
control.

**The true-up returns to the projects that paid.** `aud_credits_deposit_bearers`
compares the projects an audit credits against the projects the audited policy
actually allocated to. A credit to a project that never bore the deposit, or a
closed project that bore it and is never made whole, is wrong in both directions
at once — and `aud_uses_deposit_basis` proves the split used the *deposit* basis,
a historical fact, rather than the exposure open today.

## The tower has no gap

`pol_tower_has_no_gap` proves each excess layer attaches no higher than the
primary limit beneath it, and `pol_no_coverage_gap` proves successive terms of the
same line leave no uninsured day between them. Both are the most expensive kind of
clerical error in insurance: invisible until a loss lands in the band nobody
bought, where every policy responds correctly by declining.

## Tests

```bash
python -m pytest insurance_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per named
control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the projects, the policies and the audits are stated. The generator computes
everything the engine later checks as a tie-out: each project's share of every
premium from the declared basis, the reallocation of each audit on the basis that
split its deposit, what lands on job cost, the per-unit metric, the prepaid balance
straight-lined across each term, and the programme total.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The programmes, the carriers, the projects, the
policy numbers and every premium and basis value are invented, and the policy year
is set in a fictional future. No employer or client workpaper, entity, methodology,
path or figure is reproduced.
