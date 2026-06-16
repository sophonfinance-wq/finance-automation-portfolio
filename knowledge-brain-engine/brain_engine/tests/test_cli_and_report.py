"""CLI and report-rendering tests, including the refusal banner and file writes."""

from __future__ import annotations

from brain_engine import cli
from brain_engine.engine import BrainEngine
from brain_engine.generate import build_corpus
from brain_engine.report import (
    REFUSAL,
    citation_block,
    render_ask,
    render_citation,
    render_index,
    render_prep,
)


def _engine():
    return BrainEngine(build_corpus())


# --- report layer: every answer carries a citation ------------------------
def test_citation_block_contains_verbatim_quote_and_tag() -> None:
    engine = _engine()
    hit = engine.ask("warranty reserve book-tax")[0]
    block = citation_block(hit)
    assert hit.card.rule_text in block
    assert hit.card.provenance.date in block
    assert hit.card.provenance.speaker in block
    assert hit.card.provenance.timestamp in block


def test_render_ask_includes_citation_tag() -> None:
    engine = _engine()
    q = "return of capital beyond basis"
    text = render_ask(q, engine.ask(q))
    assert "FICTIONAL" in text
    assert "—" in text  # citation tag em-dashes present
    assert REFUSAL not in text


def test_render_ask_refusal_when_empty() -> None:
    text = render_ask("parking policy", [])
    assert REFUSAL in text


def test_render_citation_refusal_when_none() -> None:
    text = render_citation("the weather", None)
    assert REFUSAL in text


def test_render_citation_has_paste_ready_footnote() -> None:
    engine = _engine()
    a = "return of capital in excess of basis is a deemed gain"
    text = render_citation(a, engine.cite(a))
    assert "byte-identical" in text
    assert engine.cite(a).card.rule_text in text


def test_render_prep_splits_settled_and_open() -> None:
    engine = _engine()
    topic = "warranty reserve book-tax treatment"
    text = render_prep(topic, engine.prep(topic))
    assert "Settled prior positions" in text
    assert "Open items to resolve" in text


def test_render_index_lists_provenance() -> None:
    engine = _engine()
    text = render_index(engine)
    assert "Meetings ingested:" in text
    assert "CARD-WARRANTY-01" in text
    assert "Knowledge cards:" in text


# --- CLI: default index ---------------------------------------------------
def test_cli_default_prints_index(capsys) -> None:
    code = cli.main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Knowledge Brain" in out
    assert "Meetings ingested:" in out


# --- CLI: ask mode --------------------------------------------------------
def test_cli_ask_returns_zero_and_cites(capsys) -> None:
    code = cli.main(["ask", "return of capital beyond basis"])
    out = capsys.readouterr().out
    assert code == 0
    assert "CARD-ROC" in out


def test_cli_ask_refusal_exit_code(capsys) -> None:
    code = cli.main(["ask", "office parking and lunch policy"])
    out = capsys.readouterr().out
    assert code == 3
    assert REFUSAL in out


# --- CLI: cite mode -------------------------------------------------------
def test_cli_cite_returns_footnote(capsys) -> None:
    code = cli.main(["--cite", "return of capital in excess of basis is a deemed gain"])
    out = capsys.readouterr().out
    assert code == 0
    assert "byte-identical" in out


def test_cli_cite_refusal_exit_code(capsys) -> None:
    code = cli.main(["--cite", "the weather forecast next week"])
    out = capsys.readouterr().out
    assert code == 3
    assert REFUSAL in out


# --- CLI: prep mode -------------------------------------------------------
def test_cli_prep_returns_briefing(capsys) -> None:
    code = cli.main(["--prep", "warranty reserve book-tax treatment"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Settled prior positions" in out


# --- CLI: writes deliverables ---------------------------------------------
def test_cli_writes_deliverables(tmp_path, capsys) -> None:
    code = cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    assert code == 0
    assert (tmp_path / "brain_index.md").exists()
    assert (tmp_path / "citation_example.md").exists()
    assert (tmp_path / "meeting_prep_example.md").exists()


def test_written_index_contains_fictional_and_provenance(tmp_path, capsys) -> None:
    cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    text = (tmp_path / "brain_index.md").read_text(encoding="utf-8")
    assert "FICTIONAL" in text
    assert "00:03:02" in text  # a known timestamp in the corpus


def test_citation_example_file_is_byte_identical_to_source(tmp_path, capsys) -> None:
    cli.main(["--out", str(tmp_path)])
    capsys.readouterr()
    engine = _engine()
    a = "return of capital in excess of basis"
    hit = engine.cite(a)
    text = (tmp_path / "citation_example.md").read_text(encoding="utf-8")
    assert hit is not None
    assert hit.card.rule_text in text
