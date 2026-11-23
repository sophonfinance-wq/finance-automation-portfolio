"""The engine must be strictly read-only and fully deterministic.

Three contract tests:

1. analyzing a corpus does not change a single byte on disk,
2. two generations with the same seed produce identical ``.json`` documents,
3. two runs over the same corpus produce identical findings once the one
   legitimately varying value, ``generated_utc``, is popped.

``.xlsx`` is deliberately excluded from the byte comparison: the writer stamps
times, so the workbook is not reproducible and is gitignored.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ap_engine.engine import analyze_document, analyze_folder
from ap_engine.generate import generate_corpus
from ap_engine.report import build_json_report, build_markdown_report


def _digest_dir(folder: Path) -> dict[str, tuple[int, bytes]]:
    """Map filename -> (size, sha256 digest) for every file in ``folder``."""
    out: dict[str, tuple[int, bytes]] = {}
    for path in sorted(folder.iterdir(), key=lambda p: p.name):
        data = path.read_bytes()
        out[path.name] = (len(data), hashlib.sha256(data).digest())
    return out


def test_analysis_never_mutates_source_documents(corpus_dir: Path) -> None:
    """Analyzing must not change any source artifact on disk (read-only)."""
    before = _digest_dir(corpus_dir)
    analyze_folder(corpus_dir)
    # And again directly, per document set.
    for path in sorted(corpus_dir.glob("*.json"), key=lambda p: p.name):
        analyze_document(path)
    after = _digest_dir(corpus_dir)
    assert before == after, "source documents were modified -- engine is not read-only"


def test_generation_is_deterministic(tmp_path: Path) -> None:
    """Two fresh generations with the same seed produce identical documents."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_corpus(a)
    generate_corpus(b)
    da = _digest_dir(a)
    db = _digest_dir(b)
    assert sorted(da) == sorted(db)
    compared = 0
    for name in sorted(da):
        if name.endswith(".json"):
            assert da[name] == db[name], f"non-deterministic JSON: {name}"
            compared += 1
    assert compared > 0, "no .json documents were compared"


def test_findings_are_stable_across_runs(corpus_dir: Path) -> None:
    """Re-analyzing yields identical findings (order and content)."""
    first = build_json_report(analyze_folder(corpus_dir))
    second = build_json_report(analyze_folder(corpus_dir))
    assert first.pop("generated_utc")
    assert second.pop("generated_utc")
    assert first == second


def test_markdown_artifact_is_byte_stable(corpus_dir: Path) -> None:
    """The markdown artifact carries no timestamp, so it is byte-identical."""
    first = build_markdown_report(analyze_folder(corpus_dir))
    second = build_markdown_report(analyze_folder(corpus_dir))
    assert first == second
    assert first.encode("ascii")  # raises if a non-ASCII byte crept in


def test_finding_order_follows_the_registry(corpus_dir: Path) -> None:
    """Findings appear in registry order, which is what makes reports diffable."""
    from ap_engine.engine import REGISTRY

    order = [rule_id for rule_id, _ in REGISTRY]
    for report in analyze_folder(corpus_dir):
        positions = [order.index(f.rule) for f in report.findings]
        assert positions == sorted(positions), report.document
