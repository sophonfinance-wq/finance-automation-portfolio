# Entity good-standing automation

A deterministic, **read-only** control engine for a closely-held real-estate
family's entity good-standing — every legal entity proved, state by state, to
have its annual/biennial report filed on time, its franchise tax paid in the
exact statutory amount by its due date, its registered agent of record the one
under contract, and its Secretary-of-State status ACTIVE.

A group that forms one entity per project and qualifies it into each state it
operates in has to keep dozens of `(entity, state)` registrations alive at once,
and a good-standing record is a snapshot that was true the day the state produced
it. It goes stale in ways nobody watches. Three failures hide inside that, and
none of them look wrong in a register of one-line entries.

**The filing lapses.** The annual report or the franchise-tax payment slips past
its statutory due date, so the entity drifts toward administrative suspension
while the internal register still shows it Active — just late. A suspended entity
cannot sue, cannot close a sale, and cannot borrow, and the family finds out at
exactly the wrong moment.

**The obligation is short or misdated.** The franchise tax is paid, but a dollar
under the flat statutory amount, or the stated due date does not match the one
the statute re-derives, or the agent named on the state's record is not the agent
actually under contract — so service of process lands somewhere nobody is
watching. The paper looks complete; the standing is not there.

**The rollup drifts from the evidence.** The compliance report calls an entity in
good standing, or counts a family as clean, on a determination nobody recomputed
from the state records underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 26 controls, writes
`standing_report.json` and `standing_report.md`, and exits with the verdict code.
The corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 26 controls

| Family | Count | Asks |
|---|---|---|
| `set_`  | 1 | Is the standing file complete, and are the review date and filing year readable? |
| `ent_`  | 4 | Are the entity ids unique, typed and status-valid, and is each entity's jurisdiction set declared and known? |
| `jur_`  | 2 | Does every state an active entity belongs to have a matrix row and a record on file? |
| `rec_`  | 4 | Is every state record well-formed, uniquely numbered, attributable to an entity, and for a state that entity actually joined? |
| `fil_`  | 4 | Does each report due date re-derive from the statute, was it filed on time, its fee met, and what is due to renew inside the lead window? |
| `tax_`  | 3 | Is the franchise tax the flat statutory amount, on the statutory date, paid on time? |
| `agt_`  | 2 | Is the agent of record the contracted agent, with its fee paid? |
| `sts_`  | 1 | Does an entity the register calls Active read ACTIVE on every SOS record? |
| `lic_`  | 1 | Where a jurisdiction requires a city business license, is it current? |
| `dis_`  | 1 | Is every dissolved entity cancelled in every state it ever belonged to? |
| `roll_` | 3 | Does each good-standing flag recompute, do the report counts tie the summary, and does the renewal watchlist tie the evidence? |

Three are worth calling out.

**The determination recomputes, it is not read back.**
`roll_standing_recomputes` is the control the engine exists for. The standing
summary is a *determination*, and a determination that is not recomputed from the
evidence is an assertion. The engine rebuilds every entity's good-standing flag
from the jurisdiction matrix and the state records — report timeliness, franchise
amount and timeliness, SOS status, agent, licence — and compares it to the one on
file.

**The statutory date is re-derived, not trusted.** `fil_due_date_recomputes` and
`tax_due_date_recomputes` rebuild each stated due date from the filing year plus
the jurisdiction's statutory month and day, and compare. A due date the register
states but the statute does not re-derive is a date nobody can defend the
timeliness test against.

**Every amount is met at the statutory figure.** `tax_amount_meets` and
`fil_report_fee_paid` compare with exact `>=`. A franchise tax a dollar short of
the flat statutory amount is an unpaid franchise tax — the state does not
part-credit it — and the shortfall accrues penalty and interest until the entity
is suspended.

## The renewal window is a flag, not a failure

`fil_renewal_lead_time` marks a record whose *next* report is due inside the
file's own lead-time window: the entity is still in good standing, but the
upcoming filing needs to be made before it lapses. `roll_watchlist_ties` proves
the stated watchlist is exactly the set of filings actually due — so the filing
chase is sent to the right place and no lapse is missed. Both are
`REVIEW`-severity: worth a human's eyes, not a hard stop.

## Dissolution is completeness, not a single certificate

A wound-down entity that keeps a live registration in even one state it once
qualified into keeps accruing that state's franchise tax and report obligations —
a dormant liability that surfaces years later as a suspension and a bill.
`dis_cancellation_complete` walks every state a dissolved entity ever belonged to
and proves each carries a filed certificate of cancellation.

## Tests

```bash
python -m pytest standing_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the entities, the jurisdiction matrix and the state records are stated — and
even the records' statutory due dates are computed from the matrix, so they cannot
drift from the statute they claim to follow. The generator computes everything the
engine later checks as a rollup — each entity's good-standing determination, the
renewal watchlist, and the family in-good-standing / not counts — through the
*same* good-standing kernel the engine recomputes with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The entity families, the entities, the jurisdictions
(Marran, Kelder, Tolvane, Verrado), the registered agents, the SOS file numbers
and every flat fee and filing date are invented, and the compliance period is set
in a fictional future. No employer or client workpaper, entity, methodology, path
or figure is reproduced.
