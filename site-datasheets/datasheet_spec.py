"""Load and validate one engine datasheet spec (pure, stdlib only)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPECS_DIR = ROOT / "specs"

REQUIRED_FIELDS: tuple[str, ...] = (
    "num", "slug", "part_no", "mnemonic", "family", "name", "tagline",
    "plain_summary", "rev", "status", "layers", "blocks", "edges",
    "spec_strip", "problem_statement", "scenarios", "instruction_set",
    "benchmarks", "control_characteristics", "limits", "media", "links",
    "meta",
)

#: Arrays where every row must carry a non-empty "source" (claim-lint).
SOURCED_ARRAYS: tuple[str, ...] = (
    "spec_strip", "benchmarks", "scenarios", "limits",
)

_REV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PART_RE = re.compile(r"^SFS-E\d{2}-[A-Z]{3}$")


def load_spec(slug: str) -> dict:
    path = SPECS_DIR / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec: dict) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in spec:
            problems.append(f"missing required field: {field}")
    if "rev" in spec and not _REV_RE.match(str(spec["rev"])):
        problems.append(f"rev must be ISO date YYYY-MM-DD, got {spec['rev']!r}")
    if "part_no" in spec and not _PART_RE.match(str(spec["part_no"])):
        problems.append(f"part_no must match SFS-E##-XXX, got {spec['part_no']!r}")
    if spec.get("status") not in (None, "PRODUCTION"):
        problems.append(f"status must be PRODUCTION, got {spec.get('status')!r}")
    for array_name in SOURCED_ARRAYS:
        for i, row in enumerate(spec.get(array_name, [])):
            if not str(row.get("source", "")).strip():
                problems.append(f"{array_name}[{i}] has empty source")
    return problems
