# Insurance compliance automation

A deterministic, **read-only** control engine for a residential developer's
certificate-of-insurance (COI) compliance — every consultant, general contractor
and subcontractor the developer hires proved, party by party, to have its
certificate on file, unexpired, and meeting the contract-required limits and
endorsements for its type.

This is the other half of the insurance story. Where a master premium lands on
each project's job cost is an *allocation* question owned by a separate engine —
and that engine explicitly declines to check whether a certificate is on file.
This engine is that check.

A COI is a one-page snapshot of coverage that was true the day the broker issued
it, and it goes stale in ways nobody watches. Three failures hide inside that,
and none of them look wrong in a folder of one-page certificates.

**The certificate lapses.** A policy expires and the renewal certificate never
arrives, so the party is uninsured on the developer's own job while its file
still shows a certificate — just an expired one. Between two valid renewals the
same gap can open for a single day, and an occurrence lands in it with nothing to
respond.

**The limits fall short of the contract.** The certificate is current, but the
per-occurrence or aggregate limit is below what the contract required for that
party type, or the additional-insured and waiver-of-subrogation endorsements the
contract demanded were never added. The paper looks complete; the protection is
not there.

**The rollup drifts from the evidence.** The monthly report calls a party
compliant, or counts a portfolio as clean, on a determination nobody recomputed
from the certificates underneath it.

```bash
python run.py
```

Regenerates the fictional corpus into `samples/`, runs all 22 controls, writes
`coi_report.json` and `coi_report.md`, and exits with the verdict code. The
corpus contains planted defects on purpose, so a non-zero exit is the engine
working.

## The 22 controls

| Family | Count | Asks |
|---|---|---|
| `set_`   | 1 | Is the compliance file complete, and is the review date readable? |
| `party_` | 4 | Are the party ids unique and typed, is each party's coverage set declared, and does the matrix define every requirement it names? |
| `cert_`  | 4 | Is every certificate well-formed, uniquely numbered, forward-dated and attributable to a party? |
| `cov_`   | 5 | Is each required coverage present, of a known line, adequate on both limits, and free of any uninsured day between renewals? |
| `end_`   | 2 | Are the additional-insured and waiver-of-subrogation endorsements the matrix requires actually on the governing certificate? |
| `exp_`   | 3 | Is the governing certificate in force now, what is due to renew inside the lead window, and does every party carry workers' comp? |
| `rpt_`   | 3 | Does each party's compliant flag recompute, do the report counts tie the summary, and does the renewal watchlist tie the evidence? |

Three are worth calling out.

**The determination recomputes, it is not read back.**
`rpt_party_compliant_recomputes` is the control the engine exists for. The
coverage summary is a *determination*, and a determination that is not recomputed
from the evidence is an assertion. The engine rebuilds every party's compliant
flag from the requirement matrix and the governing certificates — currency,
limits and endorsements — and compares it to the one on file.

**The governing certificate is the one in force.** Where a party has renewed a
line, the certificate whose term reaches furthest forward is the one every
currency, limit and endorsement test reads — the renewal, not the policy it
replaced — while `cov_no_uninsured_gap` walks the whole succession and proves no
uninsured day opened between a lapse and the certificate that followed it.

**Every limit is met at the requirement.** `cov_per_occurrence_meets` and
`cov_aggregate_meets` compare with exact `>=`. A limit a cent short of the
contract requirement is a limit short of the contract requirement, and a shortfall
on the aggregate is coverage that runs out before the job does — invisible until
it does.

## The renewal window is a flag, not a failure

`exp_renewal_lead_time` marks a governing certificate expiring inside the file's
own lead-time window: the coverage is still in force, but the renewal needs to be
chased before it lapses. `rpt_watchlist_ties` proves the stated watchlist is
exactly the set of certificates actually due — so the renewal chase is sent to
the right place and no lapse is missed. Both are `REVIEW`-severity: worth a
human's eyes, not a hard stop.

## Tests

```bash
python -m pytest coi_engine/tests -q
```

A clean baseline parametrized over the registry, one planted-defect file per
named control, boundary tests on every cent and date threshold, and read-only /
determinism proofs that hash the corpus before and after a full run.

## The baseline is derived, not typed

Only the parties, the requirement matrix and the certificates are stated. The
generator computes everything the engine later checks as a rollup — each party's
compliant determination, the renewal watchlist, and the portfolio compliant /
non-compliant counts — through the *same* compliance kernel the engine recomputes
with.

So the relationships the engine tests are the same relationships that produced the
data.

---

🔒 **All data is fictional.** The developers, the insured parties, the carriers,
the policy numbers and every limit and certificate date are invented, and the
compliance period is set in a fictional future. No employer or client workpaper,
entity, methodology, path or figure is reproduced.
