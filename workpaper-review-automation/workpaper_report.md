# Workpaper review — handback report

**Verdict: FAIL**

| Package | Entity | Verdict | Findings |
|---|---|---|---:|
| WP-ALPHA-AMOUNT-RECLASSIFIED-AS-DATE | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-ATTACHMENT-HASH-DRIFT | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-CITATION-OFF-BY-A-DOLLAR | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-CITATION-UNRESOLVABLE | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-COVER-NOTE-COUNT-MISMATCH | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-EVIDENCE-OVERCLAIM | Northwind Terrace Holdings LLC | FAIL | 2 |
| WP-ALPHA-ORPHANED-DEPENDANT | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-PRESENTATION-STRAY-UNDERLINE | Northwind Terrace Holdings LLC | FLAG | 1 |
| WP-ALPHA-RESIDUAL-PLUGGED | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA-TYPED-CURRENT-YEAR-INPUT | Northwind Terrace Holdings LLC | FAIL | 1 |
| WP-ALPHA | Northwind Terrace Holdings LLC | PASS | 0 |

## WP-ALPHA-AMOUNT-RECLASSIFIED-AS-DATE — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | DATE_MISREAD | `Consolidation!D20` | cell is presented as a date but is an addend in a total; a date is never an addend |

- `Consolidation!D20` DATE_MISREAD — feeds_total True; label Member pickup 1; value 46,166.00

## WP-ALPHA-ATTACHMENT-HASH-DRIFT — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | ATTACHMENT_DRIFT | `cover_note` | cover note attachment hash does not match the package |

- `cover_note` ATTACHMENT_DRIFT — note_sha256 3F0B76EEFDCE13BAF506652C662244D7CAAF6A94A464CD274995DC321A42EE71; package_sha256 60E4B862B5310261AA30C0FF3E7B49C83F64CA85D3F906D0B0735455A675A72A

## WP-ALPHA-CITATION-OFF-BY-A-DOLLAR — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | CITATION_MISMATCH | `Consolidation!D20` | citation E-001 quotes a figure the address does not hold |

- `Consolidation!D20` CITATION_MISMATCH — citation_id E-001; describes Member pickup 1; difference (1.00); quoted (733,170.61); resolved (733,171.61); rounding_sized True

## WP-ALPHA-CITATION-UNRESOLVABLE — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | CITATION_MISMATCH | `Consolidation!ZZ999` | citation E-001 points at an address not present in the package |

- `Consolidation!ZZ999` CITATION_MISMATCH — citation_id E-001; describes Member pickup 1

## WP-ALPHA-COVER-NOTE-COUNT-MISMATCH — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | QUESTION_COUNT_MISMATCH | `cover_note` | cover note states 3/2; the question block carries 1/2 |

- `cover_note` QUESTION_COUNT_MISMATCH — block_confirmations 2; block_decisions 1; stated_confirmations 2; stated_decisions 3

## WP-ALPHA-EVIDENCE-OVERCLAIM — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | CITATION_MISMATCH | `Consolidation!ZZ999` | citation E-001 points at an address not present in the package |
| FAIL | EVIDENCE_OVERCLAIM | `cover_note` | note claims all evidence is embedded; 1 citation(s) do not resolve |

- `Consolidation!ZZ999` CITATION_MISMATCH — citation_id E-001; describes Member pickup 1
- `cover_note` EVIDENCE_OVERCLAIM — unresolved ['E-001']

## WP-ALPHA-ORPHANED-DEPENDANT — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | ORPHANED_DEPENDANT | `Consolidation!D30` | dependant of moved block 'source matrix' was not re-pointed |

- `Consolidation!D30` ORPHANED_DEPENDANT — block source matrix

## WP-ALPHA-PRESENTATION-STRAY-UNDERLINE — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FLAG | PRESENTATION_DRIFT | `Consolidation!D29` | font_underline present here, absent from the prior-year master |

- `Consolidation!D29` PRESENTATION_DRIFT — direction stray; kind font_underline

## WP-ALPHA-RESIDUAL-PLUGGED — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | RESIDUAL_PLUGGED | `consolidated vs parent (149.94)` | residual was plugged rather than disclosed |

- `consolidated vs parent (149.94)` RESIDUAL_PLUGGED — residual consolidated vs parent (149.94)

## WP-ALPHA-TYPED-CURRENT-YEAR-INPUT — Northwind Terrace Holdings LLC

| Severity | Control | Address | Finding |
|---|---|---|---|
| FAIL | UNSOURCED_INPUT | `Consolidation!D20` | current-year amount is typed, not linked to a source record |

- `Consolidation!D20` UNSOURCED_INPUT — label Member pickup 1; value (733,171.61)
