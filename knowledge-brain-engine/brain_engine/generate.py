"""Seeded fictional transcript corpus for the Knowledge Brain demo.

This module is the "record -> transcribe" stage, faked: it hand-builds a small
corpus of obviously fictional finance/tax meetings, each as a list of timestamped
utterances. A subset of utterances are flagged as authoritative (an
``ExtractionSpec``); :func:`build_corpus` then lifts those into knowledge cards
whose ``rule_text`` is byte-identical to the source utterance text.

The decisions are invented dialogue but map onto real, *public* accounting / tax
concepts so the demo is recognisable to a reviewer:

* warranty-reserve book-tax attribution,
* return of capital beyond basis is a deemed gain,
* evidence must foot to an anchor,
* surplus elevates only on an actual distribution.

Everything — names, entities, dates, quotes — is fictional. ``DEFAULT_SEED`` keeps
the (already deterministic) corpus stable and mirrors the other engines' API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .model import (
    DECISION,
    DEFINITION,
    OPEN_ITEM,
    RULE,
    ChangeDirective,
    Corpus,
    KnowledgeCard,
    Meeting,
    Provenance,
    Utterance,
)

DEFAULT_SEED = 1107

# Title of the fictional review meeting that carries the change-directives. The
# remediation CLI resolves a review topic/title back to this meeting's directives.
REVIEW_MEETING_TITLE = "Surplus Workpaper Review — Reviewer Corrections"


@dataclass(frozen=True)
class ExtractionSpec:
    """Marks one utterance (by timestamp) in a meeting as a card to extract."""

    card_id: str
    timestamp: str  # HH:MM:SS — must match an utterance in the meeting
    topic_tags: Tuple[str, ...]
    kind: str


@dataclass(frozen=True)
class DirectiveSpec:
    """Marks one utterance (by timestamp) as a reviewer change-request to extract.

    Like :class:`ExtractionSpec`, but lifts the utterance into a
    :class:`ChangeDirective` rather than a standing :class:`KnowledgeCard`.
    """

    directive_id: str
    timestamp: str  # HH:MM:SS — must match an utterance in the meeting
    topic_tags: Tuple[str, ...]
    target: str = ""


@dataclass(frozen=True)
class _MeetingSpec:
    """A meeting plus the extraction / directive specs that pull from it."""

    meeting: Meeting
    extractions: Tuple[ExtractionSpec, ...]
    directives: Tuple[DirectiveSpec, ...] = ()


def _u(speaker: str, t_seconds: int, text: str) -> Utterance:
    return Utterance(speaker=speaker, t_seconds=t_seconds, text=text)


def _meeting_specs() -> List[_MeetingSpec]:
    """The hand-authored fictional corpus."""
    specs: List[_MeetingSpec] = []

    # --- Meeting 1: warranty reserve book-tax attribution --------------------
    m1 = Meeting(
        meeting_id="MTG-2025-WARRANTY",
        date="2025-01-14",
        title="Warranty Reserve Book-Tax Working Session",
        participants=("Avery Stone", "Dana Brook", "Priya Vale"),
        utterances=(
            _u("Avery Stone", 0, "Let's settle how the warranty reserve flows for the demo file."),
            _u("Dana Brook", 47, "The book warranty accrual and the tax deduction are different timing, so we never net them."),
            _u(
                "Priya Vale",
                182,
                "Decision: the warranty reserve is booked on an accrual basis but deducted for tax only when the claim is economically performed, so the book-tax difference is a deferred tax asset.",
            ),
            _u("Avery Stone", 305, "So the M-1 add-back is the accrual, and the reversal hits when the work is done."),
            _u(
                "Priya Vale",
                361,
                "Rule: every warranty book-tax adjustment must reference the originating accrual schedule by line, or the workpaper is not signed.",
            ),
            _u("Dana Brook", 540, "Open item: confirm whether the extended-warranty piece is a separate performance obligation before year end."),
        ),
    )
    specs.append(
        _MeetingSpec(
            m1,
            (
                ExtractionSpec("CARD-WARRANTY-01", "00:03:02", ("warranty", "book-tax", "deferred-tax"), DECISION),
                ExtractionSpec("CARD-WARRANTY-02", "00:06:01", ("warranty", "workpaper", "evidence"), RULE),
                ExtractionSpec("CARD-WARRANTY-03", "00:09:00", ("warranty", "revenue-recognition"), OPEN_ITEM),
            ),
        )
    )

    # --- Meeting 2: return of capital beyond basis --------------------------
    m2 = Meeting(
        meeting_id="MTG-2025-ROC",
        date="2025-02-03",
        title="Return of Capital and Basis Review",
        participants=("Marco Reyes", "Lena Frost", "Avery Stone"),
        utterances=(
            _u("Marco Reyes", 0, "We need a clean position on distributions that run past a partner's basis."),
            _u(
                "Lena Frost",
                95,
                "Definition: a return of capital is a distribution treated first as a tax-free recovery of basis, reducing the investor's adjusted basis dollar for dollar.",
            ),
            _u(
                "Lena Frost",
                221,
                "Decision: any return of capital in excess of the investor's remaining basis is recharacterized as a deemed capital gain in the year received.",
            ),
            _u("Avery Stone", 333, "So we floor basis at zero and the spill becomes gain, never a negative basis."),
            _u(
                "Marco Reyes",
                400,
                "Rule: basis can never go below zero, so the workpaper must clamp it and route the excess to the gain line.",
            ),
            _u("Lena Frost", 505, "Open item: decide if the state follows the federal recharacterization or defers it."),
        ),
    )
    specs.append(
        _MeetingSpec(
            m2,
            (
                ExtractionSpec("CARD-ROC-01", "00:01:35", ("return-of-capital", "basis", "definition"), DEFINITION),
                ExtractionSpec("CARD-ROC-02", "00:03:41", ("return-of-capital", "basis", "capital-gain"), DECISION),
                ExtractionSpec("CARD-ROC-03", "00:06:40", ("basis", "workpaper", "capital-gain"), RULE),
                ExtractionSpec("CARD-ROC-04", "00:08:25", ("return-of-capital", "state-tax"), OPEN_ITEM),
            ),
        )
    )

    # --- Meeting 3: evidence must foot to an anchor -------------------------
    m3 = Meeting(
        meeting_id="MTG-2025-EVIDENCE",
        date="2025-02-27",
        title="Workpaper Evidence and Tie-Out Standards",
        participants=("Priya Vale", "Theo Nguyen", "Dana Brook"),
        utterances=(
            _u("Priya Vale", 0, "Let's lock the tie-out standard so every number is defensible."),
            _u(
                "Theo Nguyen",
                72,
                "Rule: every figure on a calculation tab must foot to a cited anchor on the evidence tab; nothing load-bearing is hardcoded.",
            ),
            _u("Dana Brook", 168, "And the anchor has to be a real source line, not a memo."),
            _u(
                "Priya Vale",
                240,
                "Decision: if a value cannot be traced to an anchor, the reviewer refuses to sign and the figure is reworked, never estimated.",
            ),
            _u(
                "Theo Nguyen",
                360,
                "Definition: an anchor is the single cited source cell that a derived figure must reconcile to within tolerance.",
            ),
            _u("Dana Brook", 455, "Open item: agree the rounding tolerance for FX-translated anchors."),
        ),
    )
    specs.append(
        _MeetingSpec(
            m3,
            (
                ExtractionSpec("CARD-EVIDENCE-01", "00:01:12", ("evidence", "tie-out", "workpaper"), RULE),
                ExtractionSpec("CARD-EVIDENCE-02", "00:04:00", ("evidence", "tie-out", "refuse"), DECISION),
                ExtractionSpec("CARD-EVIDENCE-03", "00:06:00", ("evidence", "anchor", "definition"), DEFINITION),
                ExtractionSpec("CARD-EVIDENCE-04", "00:07:35", ("evidence", "fx", "tolerance"), OPEN_ITEM),
            ),
        )
    )

    # --- Meeting 4: surplus elevates only on distribution -------------------
    m4 = Meeting(
        meeting_id="MTG-2025-SURPLUS",
        date="2025-03-19",
        title="Foreign Affiliate Surplus Elevation Review",
        participants=("Lena Frost", "Marco Reyes", "Avery Stone"),
        utterances=(
            _u("Lena Frost", 0, "We need the rule for when subsidiary surplus moves up the chain."),
            _u(
                "Marco Reyes",
                88,
                "Decision: foreign-affiliate surplus elevates to the parent only on an actual distribution, measured at the owner's ownership percentage.",
            ),
            _u("Avery Stone", 205, "So undistributed earnings just accrue at the subsidiary and never lift on their own."),
            _u(
                "Marco Reyes",
                300,
                "Rule: adjusted cost base moves only on capital events such as contributions or returns of capital, never on operating income.",
            ),
            _u(
                "Lena Frost",
                410,
                "Definition: a distribution is the cash actually paid up to the owner in the year, and it is the only trigger that elevates surplus.",
            ),
            _u("Avery Stone", 520, "Open item: confirm the FX rate source for the elevation year before we publish."),
        ),
    )
    specs.append(
        _MeetingSpec(
            m4,
            (
                ExtractionSpec("CARD-SURPLUS-01", "00:01:28", ("surplus", "distribution", "elevation"), DECISION),
                ExtractionSpec("CARD-SURPLUS-02", "00:05:00", ("acb", "capital-event", "surplus"), RULE),
                ExtractionSpec("CARD-SURPLUS-03", "00:06:50", ("distribution", "definition", "surplus"), DEFINITION),
                ExtractionSpec("CARD-SURPLUS-04", "00:08:40", ("surplus", "fx"), OPEN_ITEM),
            ),
        )
    )

    # --- Meeting 5: REVIEW — reviewer issues explicit corrections -----------
    # This is the review-to-remediation meeting: the reviewer dictates specific,
    # timestamped change-requests against the surplus workpaper. Each flagged
    # utterance becomes a ChangeDirective (an instruction to APPLY), not a
    # standing card. Numbers are invented; concepts are generic and public.
    m5 = Meeting(
        meeting_id="MTG-2025-SURPLUS-REVIEW",
        date="2025-04-08",
        title=REVIEW_MEETING_TITLE,
        participants=("Quinn Harlow", "Marco Reyes", "Avery Stone"),
        utterances=(
            _u("Quinn Harlow", 0, "I reviewed the surplus workpaper; I have a handful of corrections to apply before sign-off."),
            _u(
                "Quinn Harlow",
                64,
                "Change the distribution formula to reference column E, not column D, across every year column.",
            ),
            _u("Marco Reyes", 150, "Understood — column E is the distributed figure, column D was the accrual."),
            _u(
                "Quinn Harlow",
                212,
                "Add back the warranty-reserve book-tax difference at the development level — about 46% of the adjustment.",
            ),
            _u("Avery Stone", 300, "So the add-back lands in the development tab, not the consolidated tab."),
            _u(
                "Quinn Harlow",
                366,
                "Re-run the evidence query and footnote each figure to its source anchor.",
            ),
            _u("Marco Reyes", 430, "I'll regenerate the tie-out and attach the anchors."),
            _u(
                "Quinn Harlow",
                498,
                "Keep the 26,000 item as a distribution to match the tax return, do not reclass it to income.",
            ),
            _u("Avery Stone", 560, "Got it — 26,000 stays on the distribution line to tie to the return."),
        ),
    )
    specs.append(
        _MeetingSpec(
            m5,
            extractions=(),  # a review meeting issues directives, not standing cards
            directives=(
                DirectiveSpec(
                    "DIR-SURPLUS-REVIEW-01",
                    "00:01:04",
                    ("surplus", "distribution", "formula", "review"),
                    target="distribution formula column reference",
                ),
                DirectiveSpec(
                    "DIR-SURPLUS-REVIEW-02",
                    "00:03:32",
                    ("warranty", "book-tax", "add-back", "review"),
                    target="warranty-reserve book-tax add-back",
                ),
                DirectiveSpec(
                    "DIR-SURPLUS-REVIEW-03",
                    "00:06:06",
                    ("evidence", "tie-out", "footnote", "review"),
                    target="evidence query re-run and footnotes",
                ),
                DirectiveSpec(
                    "DIR-SURPLUS-REVIEW-04",
                    "00:08:18",
                    ("distribution", "tax-return", "classification", "review"),
                    target="26,000 distribution classification",
                ),
            ),
        )
    )

    return specs


def _extract_cards(spec: _MeetingSpec) -> List[KnowledgeCard]:
    """Lift the flagged utterances of a meeting into knowledge cards.

    The card ``rule_text`` is copied byte-for-byte from the matched utterance, so
    a citation can never drift from what was actually said.
    """
    meeting = spec.meeting
    by_timestamp: Dict[str, Utterance] = {u.timestamp: u for u in meeting.utterances}
    cards: List[KnowledgeCard] = []
    for ext in spec.extractions:
        if ext.timestamp not in by_timestamp:
            raise KeyError(
                f"extraction {ext.card_id} points at {ext.timestamp} "
                f"but {meeting.meeting_id} has no utterance there"
            )
        utt = by_timestamp[ext.timestamp]
        provenance = Provenance(
            meeting_id=meeting.meeting_id,
            title=meeting.title,
            date=meeting.date,
            speaker=utt.speaker,
            timestamp=utt.timestamp,
        )
        cards.append(
            KnowledgeCard(
                card_id=ext.card_id,
                topic_tags=tuple(ext.topic_tags),
                rule_text=utt.text,  # verbatim, byte-identical
                kind=ext.kind,
                provenance=provenance,
            )
        )
    return cards


def _extract_directives(spec: _MeetingSpec) -> List[ChangeDirective]:
    """Lift the flagged review utterances of a meeting into change-directives.

    The directive ``request_text`` is copied byte-for-byte from the matched
    utterance, so a remediation prompt can never drift from what the reviewer
    actually asked for.
    """
    meeting = spec.meeting
    by_timestamp: Dict[str, Utterance] = {u.timestamp: u for u in meeting.utterances}
    directives: List[ChangeDirective] = []
    for spec_d in spec.directives:
        if spec_d.timestamp not in by_timestamp:
            raise KeyError(
                f"directive {spec_d.directive_id} points at {spec_d.timestamp} "
                f"but {meeting.meeting_id} has no utterance there"
            )
        utt = by_timestamp[spec_d.timestamp]
        provenance = Provenance(
            meeting_id=meeting.meeting_id,
            title=meeting.title,
            date=meeting.date,
            speaker=utt.speaker,
            timestamp=utt.timestamp,
        )
        directives.append(
            ChangeDirective(
                directive_id=spec_d.directive_id,
                topic_tags=tuple(spec_d.topic_tags),
                request_text=utt.text,  # verbatim, byte-identical
                provenance=provenance,
                target=spec_d.target,
            )
        )
    return directives


def build_corpus(seed: int = DEFAULT_SEED) -> Corpus:
    """Build the deterministic fictional corpus of meetings, cards, and directives.

    ``seed`` is accepted for API parity with the sibling engines; the corpus is
    hand-authored and fully deterministic, so the result is identical every run.
    """
    specs = _meeting_specs()
    meetings = [s.meeting for s in specs]
    cards: List[KnowledgeCard] = []
    directives: List[ChangeDirective] = []
    for spec in specs:
        cards.extend(_extract_cards(spec))
        directives.extend(_extract_directives(spec))
    return Corpus(meetings=meetings, cards=cards, directives=directives)
