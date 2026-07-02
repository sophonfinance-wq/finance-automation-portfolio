"""Generator behaviour — determinism, the --out flag, clean exits."""

from __future__ import annotations

import subprocess
import sys

import atlas_data as data
import generate

from atlas_tests.conftest import ARTIFACT_PATH, ATLAS_DIR


def test_render_is_deterministic_in_process() -> None:
    assert generate.render() == generate.render()


def test_two_generator_runs_are_byte_identical(tmp_path) -> None:
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    assert generate.main(["--out", str(first)]) == 0
    assert generate.main(["--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_out_flag_is_honored(tmp_path) -> None:
    target = tmp_path / "custom-name.html"
    assert generate.main(["--out", str(target)]) == 0
    assert target.is_file()
    assert target.stat().st_size > 10_000


def test_out_flag_creates_parent_directories(tmp_path) -> None:
    target = tmp_path / "nested" / "deeper" / "atlas.html"
    assert generate.main(["--out", str(target)]) == 0
    assert target.is_file()


def test_committed_artifact_is_fresh() -> None:
    # The committed file must be exactly what the current model renders.
    assert ARTIFACT_PATH.read_bytes() == generate.render().encode("utf-8")


def test_main_reports_model_counts(tmp_path, capsys) -> None:
    assert generate.main(["--out", str(tmp_path / "a.html")]) == 0
    out = capsys.readouterr().out
    assert "Finance Operations Atlas" in out
    assert "%d rows" % len(data.FINDIT) in out
    total_events = sum(len(rows) for rows in data.CALENDAR.values())
    assert "%d events" % total_events in out


def test_cli_exits_cleanly(tmp_path) -> None:
    target = tmp_path / "atlas.html"
    proc = subprocess.run(
        [sys.executable, "generate.py", "--out", str(target)],
        cwd=str(ATLAS_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Finance Operations Atlas" in proc.stdout
    assert target.is_file()


def test_payload_json_is_pure_ascii() -> None:
    assert all(ord(ch) < 128 for ch in generate.payload_json())


def test_render_ends_with_closed_document(rendered: str) -> None:
    assert rendered.endswith("</html>\n")
