"""
Fictional corpus generator for the workpaper review & handback engine.
======================================================================

Builds a deterministic, seeded set of package files: one clean package that
every control passes, and one package per defect class so each control has
something to catch. Byte-stable -- the same seed produces the same bytes, so a
regenerated corpus can be diffed.

All entities, people, places, figures, documents and paths are **invented**. No
real client, engagement or amount appears here.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any

__all__ = ["generate_corpus", "build_clean_package", "DEFECTS"]

SEED = 20260912

#: Invented entities. Any resemblance to a real venture is unintended.
ENTITIES = (
    ("WP-ALPHA", "Northwind Terrace Holdings LLC"),
    ("WP-BRAVO", "Selby Crossing Investors LLC"),
    ("WP-CHARLIE", "Lyndon Quarter Development LLC"),
)

PERIOD = "FYE 6/30/2026"

DEFECTS = (
    "typed_current_year_input",
    "citation_off_by_a_dollar",
    "citation_unresolvable",
    "amount_reclassified_as_date",
    "orphaned_dependant",
    "cover_note_count_mismatch",
    "attachment_hash_drift",
    "residual_plugged",
    "presentation_stray_underline",
    "evidence_overclaim",
)


def _sha(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()


def build_clean_package(package_id: str, entity: str, rng: random.Random) -> dict[str, Any]:
    """A package that every control passes."""
    sha = _sha(package_id + entity)
    cells: list[dict[str, Any]] = []

    # sourced current-year inputs
    for i in range(6):
        cells.append(
            {
                "sheet": "Consolidation",
                "cell": "D%d" % (20 + i),
                "label": "Member pickup %d" % (i + 1),
                "value_cents": rng.randrange(-900_000_00, 900_000_00),
                "origin": "sourced",
                "is_current_year": True,
                "display_kind": "amount",
                "feeds_total": True,
                "source_ref": "SRC-%03d" % (i + 1),
            }
        )
    # a derived total
    cells.append(
        {
            "sheet": "Consolidation",
            "cell": "D30",
            "label": "Total member pickups",
            "value_cents": sum(c["value_cents"] for c in cells),
            "origin": "derived",
            "is_current_year": True,
            "display_kind": "amount",
        }
    )
    # inherited prior-year content: typed is fine here
    cells.append(
        {
            "sheet": "Consolidation",
            "cell": "D41",
            "label": "Prior-year opening equity",
            "value_cents": -4_182_400_00,
            "origin": "typed",
            "is_current_year": False,
            "display_kind": "amount",
        }
    )
    # a genuine date, presented as a date
    cells.append(
        {
            "sheet": "Evidence Index",
            "cell": "G5",
            "label": "Source period end",
            "value_cents": 46_203_00,
            "origin": "sourced",
            "is_current_year": True,
            "display_kind": "date",
            "source_ref": "SRC-DATE-1",
        }
    )

    citations = [
        {
            "citation_id": "E-001",
            "describes": "Member pickup 1",
            "quoted_cents": cells[0]["value_cents"],
            "resolves_to": "Consolidation!D20",
            "document": "Invented Partnership Return 2025.pdf",
            "page": 12,
        },
        {
            "citation_id": "E-002",
            "describes": "Total member pickups",
            "quoted_cents": cells[6]["value_cents"],
            "resolves_to": "Consolidation!D30",
            "document": "Invented Workpaper 2026.xlsx",
            "page": None,
        },
    ]

    presentation = [
        {"sheet": "Consolidation", "cell": "D30", "kind": "cell_border",
         "present_in_master": True, "present_in_current": True},
        {"sheet": "Consolidation", "cell": "D29", "kind": "font_underline",
         "present_in_master": False, "present_in_current": False},
    ]

    questions = [
        {"cell": "C14", "kind": "decide", "summary": "Invented treatment question one"},
        {"cell": "C15", "kind": "confirm", "summary": "Invented confirmation one"},
        {"cell": "C16", "kind": "confirm", "summary": "Invented confirmation two"},
    ]

    return {
        "doc_type": "workpaper_package",
        "package_id": package_id,
        "entity": entity,
        "period_label": PERIOD,
        "attachment_sha256": sha,
        "cells": cells,
        "citations": citations,
        "presentation": presentation,
        "questions": questions,
        "cover_note": {
            "stated_decisions": 1,
            "stated_confirmations": 2,
            "attachment_sha256": sha,
            "claims_all_evidence_embedded": False,
        },
        "disclosed_residuals": ["consolidated vs parent (149.94)"],
        "plugged_residuals": [],
        "moved_blocks": [
            {
                "block": "source matrix",
                "dependants": [
                    {"address": "Consolidation!D30", "repointed": True},
                ],
            }
        ],
        "meta": {"fictional": True, "seed": SEED},
    }


def _apply_defect(pkg: dict[str, Any], defect: str) -> dict[str, Any]:
    """Plant exactly one defect so exactly one control should fire."""
    p = json.loads(json.dumps(pkg))
    p["package_id"] = "%s-%s" % (pkg["package_id"], defect.upper().replace("_", "-"))

    if defect == "typed_current_year_input":
        p["cells"][0]["origin"] = "typed"
        p["cells"][0].pop("source_ref", None)
    elif defect == "citation_off_by_a_dollar":
        p["citations"][0]["quoted_cents"] += 100
    elif defect == "citation_unresolvable":
        p["citations"][0]["resolves_to"] = "Consolidation!ZZ999"
    elif defect == "amount_reclassified_as_date":
        # An amount that is summed into a total, wrongly converted to a date.
        p["cells"][0]["value_cents"] = 46_166_00
        p["cells"][0]["display_kind"] = "date"
        p["cells"][6]["value_cents"] = sum(
            c["value_cents"] for c in p["cells"][:6]
        )
        p["citations"][0]["quoted_cents"] = p["cells"][0]["value_cents"]
        p["citations"][1]["quoted_cents"] = p["cells"][6]["value_cents"]
    elif defect == "orphaned_dependant":
        p["moved_blocks"][0]["dependants"][0]["repointed"] = False
    elif defect == "cover_note_count_mismatch":
        p["cover_note"]["stated_decisions"] = 3
    elif defect == "attachment_hash_drift":
        p["cover_note"]["attachment_sha256"] = _sha("stale-" + pkg["package_id"])
    elif defect == "residual_plugged":
        p["plugged_residuals"] = ["consolidated vs parent (149.94)"]
        p["disclosed_residuals"] = []
    elif defect == "presentation_stray_underline":
        p["presentation"][1]["present_in_current"] = True
    elif defect == "evidence_overclaim":
        p["cover_note"]["claims_all_evidence_embedded"] = True
        p["citations"][0]["resolves_to"] = "Consolidation!ZZ999"
    else:  # pragma: no cover - guarded by DEFECTS
        raise ValueError("unknown defect %r" % (defect,))
    p["meta"]["planted_defect"] = defect
    return p


def generate_corpus(folder: str, seed: int = SEED) -> list[str]:
    """Write the corpus into ``folder``; return the filenames written, sorted."""
    os.makedirs(folder, exist_ok=True)
    rng = random.Random(seed)
    written: list[str] = []

    clean = build_clean_package(ENTITIES[0][0], ENTITIES[0][1], rng)
    docs: list[dict[str, Any]] = [clean]
    for defect in DEFECTS:
        docs.append(_apply_defect(clean, defect))

    for doc in docs:
        name = "%s.json" % doc["package_id"].lower()
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=True)
            fh.write("\n")
        written.append(name)
    return sorted(written)
