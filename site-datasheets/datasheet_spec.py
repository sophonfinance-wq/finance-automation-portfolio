"""Load and validate one engine datasheet spec (pure, stdlib only)."""
from __future__ import annotations

import json
import re
from datetime import date
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

_ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "layers": ("id", "label", "plain", "engineering", "source_link"),
    "blocks": ("id", "label", "plain", "engineering", "source_link", "col", "row"),
    "edges": ("from", "to"),
    "spec_strip": ("label", "value", "source"),
    "scenarios": ("title", "narrative", "source"),
    "instruction_set": ("cmd", "operation", "output", "exit_code", "artifacts"),
    "benchmarks": ("label", "value", "unit", "source"),
    "limits": ("statement", "source"),
}

_CONTROL_ROWS: dict[str, tuple[str, ...]] = {
    "authority": ("rank", "level", "note"),
    "verdict_map": ("severity", "verdict", "action"),
    "modes": ("name", "detail"),
}


def load_spec(slug: str) -> dict:
    path = SPECS_DIR / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec: dict) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in spec:
            problems.append(f"missing required field: {field}")
    if "rev" in spec:
        rev = str(spec["rev"])
        if not _REV_RE.match(rev):
            problems.append(f"rev must be ISO date YYYY-MM-DD, got {spec['rev']!r}")
        else:
            try:
                date.fromisoformat(rev)
            except ValueError:
                problems.append(f"rev must be a real calendar date, got {spec['rev']!r}")
    if "part_no" in spec and not _PART_RE.match(str(spec["part_no"])):
        problems.append(f"part_no must match SFS-E##-XXX, got {spec['part_no']!r}")
    if spec.get("status") not in (None, "PRODUCTION"):
        problems.append(f"status must be PRODUCTION, got {spec.get('status')!r}")
    for array_name in SOURCED_ARRAYS:
        for i, row in enumerate(spec.get(array_name, [])):
            if isinstance(row, dict) and not str(row.get("source", "")).strip():
                problems.append(f"{array_name}[{i}] has empty source")

    for array_name, fields in _ROW_FIELDS.items():
        rows = spec.get(array_name, [])
        if not isinstance(rows, list) or not rows:
            problems.append(f"{array_name} must be a non-empty array")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"{array_name}[{i}] must be an object")
                continue
            for field in fields:
                if field not in row or row[field] in (None, ""):
                    problems.append(f"{array_name}[{i}] missing {field}")

    blocks = spec.get("blocks", [])
    if isinstance(blocks, list):
        ids = [row.get("id") for row in blocks if isinstance(row, dict)]
        if len(ids) != len(set(ids)):
            problems.append("blocks must use unique ids")
        for i, row in enumerate(blocks):
            if not isinstance(row, dict):
                continue
            if not isinstance(row.get("col"), int) or row.get("col", -1) < 0:
                problems.append(f"blocks[{i}].col must be a non-negative integer")
            if not isinstance(row.get("row"), int) or row.get("row", -1) < 0:
                problems.append(f"blocks[{i}].row must be a non-negative integer")
        valid_ids = set(ids)
        for i, edge in enumerate(spec.get("edges", [])):
            if isinstance(edge, dict) and (
                edge.get("from") not in valid_ids or edge.get("to") not in valid_ids
            ):
                problems.append(f"edges[{i}] references an unknown block")

    cc = spec.get("control_characteristics")
    if isinstance(cc, dict):
        # guarantees + determinism are universal; authority, verdict_map, modes, and
        # gate_policy are Triangulate-shaped and OPTIONAL — an engine that has no ranked
        # evidence hierarchy, no discrete verdict states, no operating modes, or no
        # human-approval gate simply omits them rather than inventing structure. Each is
        # validated only when present.
        for key in ("guarantees", "determinism"):
            if key not in cc:
                problems.append(f"control_characteristics missing {key}")
        for array_name, fields in _CONTROL_ROWS.items():
            if array_name not in cc:
                continue
            rows = cc.get(array_name, [])
            if not isinstance(rows, list) or not rows:
                problems.append(
                    f"control_characteristics.{array_name} must be a non-empty array"
                )
                continue
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    problems.append(f"control_characteristics.{array_name}[{i}] must be an object")
                    continue
                for field in fields:
                    if field not in row or row[field] in (None, ""):
                        problems.append(
                            f"control_characteristics.{array_name}[{i}] missing {field}"
                        )
        authority = cc.get("authority", [])
        if isinstance(authority, list) and authority:
            ranks = [row.get("rank") for row in authority if isinstance(row, dict)]
            if ranks != list(range(1, len(authority) + 1)):
                problems.append(
                    "control_characteristics.authority ranks must be sequential from 1"
                )
        guarantees = cc.get("guarantees")
        if not isinstance(guarantees, list) or not guarantees or any(
            not isinstance(item, str) or not item.strip() for item in guarantees
        ):
            problems.append(
                "control_characteristics.guarantees must be a non-empty string array"
            )
        determinism = cc.get("determinism")
        if not isinstance(determinism, dict):
            problems.append("control_characteristics.determinism must be an object")
        else:
            for key in ("seeded", "read_only", "offline_default"):
                if not isinstance(determinism.get(key), bool):
                    problems.append(
                        f"control_characteristics.determinism.{key} must be boolean"
                    )
        if "gate_policy" in cc:
            gate = cc.get("gate_policy")
            if not isinstance(gate, dict):
                problems.append("control_characteristics.gate_policy must be an object")
            else:
                if not isinstance(gate.get("human_approval_required"), bool):
                    problems.append(
                        "control_characteristics.gate_policy.human_approval_required must be boolean"
                    )
                for key in ("demo_gate", "note"):
                    if not isinstance(gate.get(key), str) or not gate[key].strip():
                        problems.append(
                            f"control_characteristics.gate_policy.{key} must be non-empty"
                        )
    elif "control_characteristics" in spec:
        problems.append("control_characteristics must be an object")

    media = spec.get("media")
    if isinstance(media, dict):
        for field in ("poster", "motion", "poster_alt", "caption"):
            if not isinstance(media.get(field), str) or not media[field].strip():
                problems.append(f"media missing {field}")
        if "crops" not in media:
            problems.append("media missing crops")
        crops = media.get("crops", [])
        if not isinstance(crops, list):
            problems.append("media.crops must be an array")
        else:
            for i, crop in enumerate(crops):
                if not isinstance(crop, dict):
                    problems.append(f"media.crops[{i}] must be an object")
                    continue
                for field in ("path", "label", "alt"):
                    if field not in crop or not str(crop[field]).strip():
                        problems.append(f"media.crops[{i}] missing {field}")
    elif "media" in spec:
        problems.append("media must be an object")

    links = spec.get("links")
    if isinstance(links, dict):
        for field in ("readme", "source", "tests", "codespaces"):
            if field not in links or not str(links[field]).strip():
                problems.append(f"links missing {field}")
    elif "links" in spec:
        problems.append("links must be an object")
    meta = spec.get("meta")
    if isinstance(meta, dict):
        if not isinstance(meta.get("description"), str) or not meta["description"].strip():
            problems.append("meta missing description")
    elif "meta" in spec:
        problems.append("meta must be an object")
    return problems
