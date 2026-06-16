"""Command-line entrypoint for the Knowledge Brain engine.

Query a corpus of fully fictional finance/tax meeting transcripts and get answers
that always carry a citation — or an explicit refusal when nothing is sourced.

Modes
-----
    python -m brain_engine                          # brain index summary
    python -m brain_engine ask "<question>"         # top cited card(s)
    python -m brain_engine --cite "<assertion>"     # one paste-ready footnote
    python -m brain_engine --prep "<topic>"         # meeting-prep briefing

With ``--out DIR`` the engine also writes the Markdown deliverables
(brain_index.md, citation_example.md, meeting_prep_example.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .engine import MIN_RELEVANCE, BrainEngine
from .generate import DEFAULT_SEED, build_corpus
from .report import (
    REFUSAL,
    render_ask,
    render_citation,
    render_index,
    render_prep,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _REPO_ROOT / "out"

# Topics used for the written example deliverables (deterministic).
_CITE_EXAMPLE = "return of capital in excess of basis"
_PREP_EXAMPLE = "warranty reserve book-tax treatment"


def _safe_print(text: str) -> None:
    """Print ``text`` even on consoles whose encoding can't render every char.

    Windows consoles often default to cp1252, which cannot encode the emoji used
    in the confidentiality banners. Re-encode via the stream's encoding with a
    replacement fallback rather than crashing the CLI.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(enc, errors="replace").decode(enc) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brain_engine",
        description="Queryable, citation-governed finance knowledge brain (fictional transcripts).",
    )
    parser.add_argument(
        "ask",
        nargs="?",
        default=None,
        metavar='ask "<question>"',
        help='ask a question; prints the top matching card(s) with citation blocks',
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="the question text (when using the 'ask' subcommand)",
    )
    parser.add_argument(
        "--cite",
        metavar='"<assertion>"',
        default=None,
        help="return the single best authoritative card as a paste-ready footnote",
    )
    parser.add_argument(
        "--prep",
        metavar='"<topic>"',
        default=None,
        help="produce a meeting-prep briefing of prior decisions/rules/open-items",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="corpus seed (reproducibility)")
    parser.add_argument(
        "--min-relevance",
        type=float,
        default=MIN_RELEVANCE,
        help="relevance floor below which the brain refuses to answer",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="directory to write Markdown deliverables (index / citation / prep examples)",
    )
    return parser


def _write_deliverables(engine: BrainEngine, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    index_path = out_dir / "brain_index.md"
    index_path.write_text(render_index(engine), encoding="utf-8")
    written.append(index_path)

    cite_path = out_dir / "citation_example.md"
    cite_path.write_text(
        render_citation(_CITE_EXAMPLE, engine.cite(_CITE_EXAMPLE)), encoding="utf-8"
    )
    written.append(cite_path)

    prep_path = out_dir / "meeting_prep_example.md"
    prep_path.write_text(
        render_prep(_PREP_EXAMPLE, engine.prep(_PREP_EXAMPLE)), encoding="utf-8"
    )
    written.append(prep_path)
    return written


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main. Returns a process exit code.

    Exit codes: ``0`` on a sourced answer (or the index/file writes); ``3`` when
    the brain refuses (nothing cleared the relevance floor) so refusals are
    scriptable.
    """
    args = build_parser().parse_args(argv)
    if not 0.0 <= args.min_relevance <= 1.0:
        print("error: --min-relevance must be in [0,1]", file=sys.stderr)
        return 2

    corpus = build_corpus(seed=args.seed)
    engine = BrainEngine(corpus, min_relevance=args.min_relevance)

    if args.out:
        written = _write_deliverables(engine, Path(args.out))
        _safe_print(f"Wrote {len(written)} deliverables to {Path(args.out).resolve()}")
        for path in written:
            _safe_print(f"    - {path.name}")
        _safe_print("")

    # --cite mode -----------------------------------------------------------
    if args.cite is not None:
        hit = engine.cite(args.cite)
        _safe_print(render_citation(args.cite, hit))
        return 0 if hit is not None else 3

    # --prep mode -----------------------------------------------------------
    if args.prep is not None:
        hits = engine.prep(args.prep)
        _safe_print(render_prep(args.prep, hits))
        return 0 if hits else 3

    # ask mode --------------------------------------------------------------
    if args.ask == "ask" or args.question is not None:
        # Support both: ask "<q>"  and  a bare question after the 'ask' token.
        question = args.question if args.question is not None else ""
        if args.ask != "ask" and args.ask:
            question = args.ask
        if not question.strip():
            print('error: ask requires a question, e.g. ask "how is warranty handled?"', file=sys.stderr)
            return 2
        hits = engine.ask(question)
        _safe_print(render_ask(question, hits))
        return 0 if hits else 3

    # A single positional that is not the 'ask' keyword is treated as a question.
    if args.ask and args.ask != "ask":
        hits = engine.ask(args.ask)
        _safe_print(render_ask(args.ask, hits))
        return 0 if hits else 3

    # default: brain index summary -----------------------------------------
    _safe_print(render_index(engine))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
