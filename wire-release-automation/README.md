# Wire & Transfer Release Control — `SFS-E29-WRL`

Engine 29 of the finance-automation portfolio. A deterministic, **read-only**
control layer that stands in front of the wire room and decides, packet by
packet, whether an outbound wire, ACH or book transfer is *safe to release*.

Booking the cash entry is a separate engine's job, and that engine assumes the
money was allowed to leave. This engine is that gate.

## What it checks

A wire is irreversible the moment it posts, and the ways one goes wrong all look
ordinary in a folder of one-page wire forms:

- **The same person moves the money end to end** — one name initiates and
  authorizes the packet, or the second signature and its date were never filled
  in before the packet left the pending tray.
- **The money goes to the wrong account** — the beneficiary triplet does not
  match the approved template, a changed bank detail was released with no
  callback, or the routing number fails its own check-digit or names a bank it
  does not resolve to.
- **The release log drifts from the evidence** — the daily released-wire log
  calls a packet releasable on a determination nobody recomputed from the
  signatures, limits and templates underneath it.

Every packet's releasable determination is recomputed from the signers, the
beneficiary templates and the funding accounts, and compared.

## Control families

| Prefix  | Family                                                              |
|---------|--------------------------------------------------------------------|
| `set_`  | structural precondition (every artifact present, exactly once)     |
| `sod_`  | segregation of duties / dual-authorization completeness            |
| `sig_`  | authorized-signer & dollar-limit membership                        |
| `ben_`  | beneficiary-master integrity + new-account callback                |
| `aba_`  | ABA/routing checksum + receiving-bank-name re-derivation           |
| `fund_` | funding-account existence & sufficiency                            |
| `dup_`  | duplicate-payment detection                                        |
| `flow_` | three-stage workflow completeness (pending → scheduled → posted)   |
| `rpt_`  | the release rollup recomputes from the evidence it summarises      |

Each deterministic rule is one registered control. Every control is a hard
equality, threshold, date-gate, membership test or re-derivation — no judgment.

## Invariants

- **Read-only.** Source artifacts are parsed, never written back.
- **Integer cents, exact comparisons.** Amounts and limits are compared with
  exact `>` / `==`; there is no tolerance band.
- **Byte-stable, deterministic output.** No timestamps, absolute paths or
  hash-ordered iteration. The same corpus produces the same bytes.
- **Absent evidence is not a passing control.** A missing artifact fails a
  structural precondition first.
- **Verdict roll-up.** Any `FAIL` → `FAIL`; `FLAG`-only → `REVIEW`; all clean →
  `PASS`. The CLI exit code is the verdict (`0`/`1`/`2`, `3` on usage error).

## Run it

```
py -3 run.py
```

Regenerates the fictional corpus into `samples/`, runs every control over it, and
writes `wire_report.json` and `wire_report.md`. The corpus deliberately contains
one clean file plus one planted defect per control, so a non-zero exit is the
engine working.

```
py -3 -m pytest -q
```

Runs the full test suite: clean-baseline rule-by-rule, control-boundary
semantics, one planted defect per registered control, the money primitives, the
read-only/determinism guarantees, and the report/CLI contract.

## Fictional data

Everything shipped here is invented — the operating entities, signers, banks,
routing numbers, beneficiaries, amounts and dates — and the release period is set
in a fictional future. No real entity, person, bank, project or path appears
anywhere.
