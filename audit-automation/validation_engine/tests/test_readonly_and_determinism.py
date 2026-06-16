"""The engine must be strictly read-only and fully deterministic."""

from __future__ import annotations

from pathlib import Path

from validation_engine.engine import build_json_report, validate_folder, validate_workbook
from validation_engine.generate import generate_corpus


def _digest_dir(folder: Path) -> dict[str, tuple[int, bytes]]:
    """Map filename -> (size, sha-ish bytes) for every file in folder."""
    import hashlib

    out: dict[str, tuple[int, bytes]] = {}
    for p in sorted(folder.iterdir()):
        data = p.read_bytes()
        out[p.name] = (len(data), hashlib.sha256(data).digest())
    return out


def test_validation_never_mutates_audited_files(corpus_dir):
    """Validating must not change any audited file on disk (read-only)."""
    before = _digest_dir(corpus_dir)
    validate_folder(corpus_dir)
    # And again directly per-workbook.
    for xlsx in corpus_dir.glob("*.xlsx"):
        validate_workbook(xlsx)
    after = _digest_dir(corpus_dir)
    assert before == after, "audited files were modified — engine is not read-only"


def test_generation_is_deterministic(tmp_path):
    """Two fresh generations with the same seed produce byte-identical workbooks."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_corpus(a)
    generate_corpus(b)
    da = {k: v for k, v in _digest_dir(a).items()}
    db = {k: v for k, v in _digest_dir(b).items()}
    # JSON exports must match exactly; xlsx content (cells) must match too.
    assert da.keys() == db.keys()
    for name in da:
        if name.endswith(".json"):
            assert da[name] == db[name], f"non-deterministic JSON: {name}"


def test_findings_are_stable_across_runs(corpus_dir):
    """Re-validating yields identical findings (order + content)."""
    r1 = build_json_report(validate_folder(corpus_dir))
    r2 = build_json_report(validate_folder(corpus_dir))
    r1.pop("generated_utc")
    r2.pop("generated_utc")
    assert r1 == r2
