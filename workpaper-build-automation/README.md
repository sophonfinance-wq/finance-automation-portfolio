# Tax Workpaper Build & Carry-Down — `SFS-E50-WPB`

A deterministic engine that **builds** the annual tax workpaper package for a new fiscal year — and
then proves what it built. Its product is a constructed package: a trial balance harvested from a
locked general-ledger extract by exact account number and scoped to one entity block; a balance
sheet and statement of operations classified from the prior year's map and footing to zero; a
members' equity schedule that freezes every prior-year layer, advances every rolling caption by
exactly one year, derives each current-year contribution and distribution as the *movement* in its
account, and allocates the result on the carried split; member capital accounts, book and tax, with
liability shares and outside basis; an earnings-and-profits roll-forward; an evidence tab with its
citation; and a build register naming every constructed cell beside the derivation that produced it.

```bash
python run.py                                       # generate, build, control, report
python -m workpaper_engine samples --build out      # build packages + registers into out/
python -m workpaper_engine samples                  # run the controls over an existing folder
python -m pytest workpaper_engine/tests -q
```

**Builder first · 24 controls · 10,367 tests · 27 seeded build files · 9 artifacts · zero tolerance.**

---

## The headline API

```python
from workpaper_engine.build import build_package, capture_prebuild_image

image   = capture_prebuild_image(prior_year, captured_at=..., document_id=...)
package = build_package(
    sources,                       # the locked current-year GL extract, entity-block scoped
    prior_year,                    # last year's signed workpaper package
    {"allocation": ...,            # member split percentages, in integer basis points
     "exception": ...,             # placeholders and mislabels a reviewer already accepted
     "counterpart_stub": ...,      # the counterpart entity's copy of the investment
     "prebuild_image": image},     # the custody backup the edit scope is diffed against
)

package.package_doc()    # trial balance, balance sheet, P&L, equity, member capital, E&P, evidence
package.register_doc()   # every constructed cell with its derivation
package.manifest_doc()   # locked-source, pre-build and built-package digests
```

The build is a **pure function of its inputs**. It never writes to the extract, the prior package or
the registers, and it takes no clock reading — every date in the output comes from the inputs, so the
same inputs produce the same package bytes today and next year.

## Why this is worth an engine

Rolling a workpaper is not copying one, and every failure mode shares one property: **the package
still foots.** That is what lets them survive review.

- **A prior-year layer moves.** History is supposed to be a constant. A sort applied to the equity
  schedule, a formula left live in a frozen row, a re-derivation that reaches back a year — any of
  these rewrites a figure that was signed off, and the schedule still adds up.
- **A caption is left at last year's date.** The cheapest defect to create and one of the most
  expensive to find: a reviewer reconciles a current-year column against a prior-year heading, cannot
  make it agree, and has no reason to suspect the heading.
- **A current-year flow is typed rather than derived.** A contributions account holds every
  contribution since the entity was formed. Dropping that balance onto a current-year row restates
  the whole history as this year's activity — and the closing total was footed from the same row.
- **A row's form is read off a formula.** Some rows carry a cumulative residual and some a year
  delta; which one a row is depends on the account's balances at *both* year-ends. A formula survives
  a copy and a balance does not, so classifying from the formula gets it wrong every time one was
  filled down.
- **The build edits more than it declared.** A rebuild that touches a cell outside the build register
  changed something nobody reviewed, and the only way to know is to hold the pre-build image and diff
  against it — which is only meaningful if the backup itself is still the one that was taken.
- **The evidence stops being evidence.** A support tab whose citation names the wrong tab, or whose
  rows no longer tie the source by account number, reconciles to nothing a reviewer can open.

## Inputs

| Artifact | What it contributes |
|---|---|
| `locked_source` | current-year accounts, titles and balances, scoped to an entity block, with the citation fields and the book-to-tax adjustment |
| `prior_package` | frozen history, the classification map, last year's equity total, member closings, accumulated E&P and every rolling caption |
| `allocation_register` | member split pairs in integer basis points, by purpose |
| `exception_register` | account numbers already accepted, and tie-out differences already disclosed |
| `counterpart_stub` | the other side of the investment held in this block |
| `prebuild_image` | the working file captured immediately before the build ran |

The build emits three more: `built_package`, `build_register` and `manifest`.

## What it builds, schedule by schedule

1. **Trial balance** — current-year balances harvested from the locked source by exact account
   number, entity-block scoped. An account with no balance carries no figure onto the workpaper and
   stays on the evidence tab, which is what makes completeness provable rather than assumed.
2. **Balance sheet and statement of operations** — classified from the prior-year map, footing to
   zero.
3. **Members' equity** — every prior layer frozen as a constant; each caption advanced by exactly one
   year; a contribution or distribution row per non-retained-earnings equity account computed as
   *current source balance less prior-year balance*; income rows allocated on the carried split; and
   a closing total.
4. **Member capital accounts** — a new year block per member: opening from last year's closing,
   contributions, ordinary income on the carried split, distributions, closing — book and tax — plus
   the liability share and tax basis.
5. **Earnings and profits** — a new block: prior accumulated plus current taxable, dated.
6. **Evidence** — the harvested rows with a citation block naming the source file, tab, balance
   column and harvest date, and a subtotal that has to foot to zero.
7. **Build register and manifest** — every constructed cell with its derivation, and three content
   digests for chain of custody.

## The 24 controls

| # | Control | What it asserts about the built package |
|---|---|---|
| 1 | `frozen_layers_byte_equal` | every prior-year layer carried byte-equal, in order |
| 2 | `captions_advance_one_year` | captions advanced exactly one year, no stale label on a rolled row |
| 3 | `capital_flow_equals_delta` | each current-year flow equals the source-less-prior delta for its account |
| 4 | `split_pairs_sum_to_one` | every carried split pair sums to exactly 100.00% |
| 5 | `income_split_rows_exact` | income rows equal the result times each member's split |
| 6 | `equity_total_rolls` | equity total = prior total + flows + result |
| 7 | `equity_ties_balance_sheet` | equity ties balance-sheet equity, except a disclosed exception |
| 8 | `member_capital_chain` | opening + contributions + income − distributions = closing, book and tax, every block |
| 9 | `member_closing_ties_equity` | members' closing book capital sums to the equity schedule |
| 10 | `tax_basis_is_capital_plus_liability` | basis = tax capital + liability share |
| 11 | `ep_chain_rolls` | prior accumulated + current taxable = year-end accumulated |
| 12 | `retained_earnings_beginning_rolls` | beginning retained earnings = prior opening + prior result |
| 13 | `row_form_classified_from_balances` | cumulative-residual vs year-delta decided from balances at both year-ends, never from a formula |
| 14 | `evidence_ties_locked_source` | every evidence row ties the source by exact account number |
| 15 | `evidence_subtotal_foots` | the subtotal is the sum of its rows, and that sum is zero |
| 16 | `citation_block_correct` | the citation names the right file, tab, column and harvest date |
| 17 | `locked_source_digest_matches` | the extract still hashes to the manifest — a moved source invalidates the build |
| 18 | `prebuild_image_digest_matches` | the custody backup is still the one that was taken |
| 19 | `edit_scope_matches_register` | only cells the register names differ from the pre-build image |
| 20 | `cross_schedule_reciprocity` | intercompany rows agree with the balance sheet; the investment agrees with its counterpart stub |
| 21 | `source_completeness` | every source account left off the workpaper is flat in the source |
| 22 | `exception_register_honored` | a placeholder or mislabel is tolerated only if registered |
| 23 | `render_hygiene` | no formula-error marker, external link or local path in the rendered package |
| 24 | `history_labels_survive` | no prior-year history label dropped by the roll |

Control 7 downgrades a single finding to **FLAG** when the difference it found is one the package
itself discloses: the engine can confirm a disclosure exists and quantifies the exact difference, but
not that it is *right*, and that judgement belongs to a person.

## Guarantees

- **Builder is pure; controls are read-only.** The build never writes to its inputs and the controls
  never write at all, so neither can introduce the break the other reports.
- **Integer cents, exact `==`.** No tolerance band anywhere. A tolerated penny is a figure the ledger
  does not support, and because this engine *builds* the workpaper, that penny is then frozen into
  every future year's history.
- **One derivation kernel.** `workpaper_engine.build` is imported by the builder, the generator and
  the controls alike, so a control cannot quietly disagree with the pipeline about how a cell was
  derived.
- **Cells keyed by row identity, never by position.** A re-sorted schedule holds exactly the same
  cells; the thing a sort actually breaks — the order of a frozen history — has its own control.
- **Every fiscal year read from the file.** Never the system clock, which is what makes the committed
  corpus and report diffable.
- **One planted defect per control.** The seeded corpus ships 26 defect files and each trips exactly
  one control, so every control has been seen firing on its own.

## Data

All data shipped here is **fictional** — invented groups, entity blocks, account numbers, balances
and dates. No real entity, project, place, ledger or filesystem path appears anywhere in this
package. `samples/` is regenerated byte-identically by `python run.py`; `out/` is generated build
output and is not tracked.
