import datetime as dt
import json

from ..cli import main
from ..engine import build_package
from ..generate import generate_report
from ..model import AuditWindow, TriagePolicy
from ..report import package_json, package_markdown


def test_cli_builds_package(tmp_path):
    rc = main(["--seed", "7", "--out", str(tmp_path)])
    assert rc == 0
    js = list(tmp_path.glob("*.json"))
    md = list(tmp_path.glob("*.md"))
    assert len(js) == 1 and len(md) == 1
    payload = json.loads(js[0].read_text(encoding="utf-8"))
    assert payload["totals"]["full_cents"] == sum(
        l["amount_cents"] for l in payload["lines"])


def test_json_round_trips_and_sorts_keys():
    window = AuditWindow(dt.date(2025, 10, 15), dt.date(2026, 6, 1))
    gen = generate_report(21)
    pkg = build_package(gen.text, gen.company, window, TriagePolicy(), gen.coverage)
    payload = json.loads(package_json(pkg))
    assert payload["window"] == {"start": "2025-10-15", "end": "2026-06-01"}
    assert list(payload.keys()) == sorted(payload.keys())


def test_markdown_carries_totals_and_triage():
    window = AuditWindow(dt.date(2025, 10, 15), dt.date(2026, 6, 1))
    gen = generate_report(21)
    pkg = build_package(gen.text, gen.company, window, TriagePolicy(), gen.coverage)
    md = package_markdown(pkg)
    assert "## Triage" in md
    assert "Window 2025-10-15 .. 2026-06-01" in md
