# Intercompany reciprocity automation

A deterministic, **read-only** control engine for a development group's
intercompany balances and cash-flow funding protocol.

A development group is a tree of entities, not one company: a holding parent over
a services arm that carries the payroll and a capital arm that guarantees the
construction loans, plus a predevelopment entity that carries land while it is
entitled. Cash moves between them constantly — advances down the chain, repayments
back up, equity into projects — and every move lands two entries on two sets of
books kept by two people.

So the failure mode lives **between** two entities, never inside one. Each
company's own books foot; the break surfaces only at consolidation, when the
intercompany balances are supposed to eliminate to zero and instead leave a
residual nobody can source. By then the period is closed.

The controls here are reciprocity controls, not single-entity checks:

1. **Every due-from equals the due-to that faces it.** Two controllers book the
   two sides independently, and the reconciliation exists because they drift. When
   every pair agrees, the group eliminates to zero on consolidation.
2. **Every closing rolls forward from the ledger.** A due-from closing is its
   opening plus advances less repayments — with equity excluded, because equity
   debits an investment account, not a receivable.
3. **Cash comes from the protocol-correct entity, and flows down the chain.**
   Project equity from the Capital arm by region; Services and predevelopment from
   the top parent; advances to descendants, not up the tree.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 23 controls, writes
`intercompany_report.json` and `intercompany_report.md`, and exits with the
verdict code. The corpus contains planted defects on purpose, so a non-zero exit
is the engine working.

## The 23 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 3 | Is the file complete, and does every entity code it names exist? |
| `ent_`  | 3 | Is the ownership tree sound: unique codes, real parents, no cycle? |
| `rec_`  | 3 | Does every due-from equal the due-to that faces it? |
| `led_`  | 5 | Does each closing roll forward from the transactions that moved it? |
| `fund_` | 4 | Did the cash come from the right entity, region and direction? |
| `liq_`  | 3 | Does the guarantor meet its floor, and is anyone off-target? |
| `appr_` | 2 | Is the ledger approved, and are large advances surfaced? |

Three are worth calling out.

**Reciprocity is checked, not assumed.** A due-from on entity A against B and the
due-to on B against A are booked by different people; the engine compares them to
the cent. There is a test that moves a single due-to by one cent and asserts the
reciprocity control fires while the pair-symmetry and roll-forward controls stay
silent — the balance is still two-sided and still ties to its own ledger, which is
exactly why the drift is invisible on either entity alone.

**A repayment reduces the reversed pair.** An advance's cash flows creditor to
debtor, so it moves the same pair the due-from is keyed on; a repayment's cash
flows debtor to creditor, so it reduces the reversed pair. The roll-forward keys
each accordingly, and equity fundings are excluded entirely — a closing that moved
by an equity amount has booked capital as a receivable.

**Funding is traced to a rule, not trusted.** Project equity must originate from a
Capital-group entity in the project's own region; Services and predevelopment
funding must come from the top parent, never the Capital arm; and an advance that
runs up the chain or across the tree is flagged, because it is more often a
distribution or a cash sweep mislabelled.

## Design guarantees

- **Read-only.** Period files are parsed and never written back. The engine cannot
  introduce a break; it can only report one.
- **Integer cents, exact comparison.** No floats accumulate and there is no
  tolerance band between a due-from and the due-to it faces. A value that should be
  integer cents but is not produces an `AMOUNT_INVALID` finding — contained to the
  one row it was read on — rather than being coerced.
- **Deterministic and byte-stable.** Same inputs, same findings, same order.
- **Absent evidence is not a passing control.** A missing due-to schedule fails
  completeness rather than letting reciprocity pass unread.

## Tests

310 tests, all passing:

```bash
python -m pytest
```

- Every one of the 23 controls has a planted defect that trips it, asserted by
  name, and coverage is asserted too.
- Boundaries are pinned: reciprocity fails at one cent of drift; the group's
  due-froms and due-tos are asserted to sum equal; the guarantor passes exactly at
  its liquidity floor and fails one cent below; target bands are inclusive at both
  ends; and equity is proven not to move a due-from.
- The clean baseline is asserted rule-by-rule, so a regression names the control
  that broke.

The baseline is *derived*, not typed: only the entity tree, the protocol
thresholds, the opening balances and the period transactions are stated. Every
closing balance is rolled forward, every due-to is the mirror of the due-from it
faces, and the ledger totals are summed from the lines — so the reciprocity, the
roll-forward and the footing the engine checks are the same relationships that
produced the data.

## Fictional data

Everything shipped here is invented — the entity group, its projects, the
reporting period and every amount — and the period is set in a fictional future.
No real entity, person, bank, project or path appears anywhere.
