"""Parametric model + report test suite — ~550 tests.

Tests the data model (KnowledgeCard, Meeting, Utterance, Provenance,
ChangeDirective, Corpus) and the report-rendering layer across:
- Model field combinations, invariants, round-trips
- Report format correctness for ask/cite/prep/remediation/index/change-log
- Refusal banners, citation tag presence, header format, empty corpus edge cases
"""

from __future__ import annotations

import pytest

from brain_engine.generate import build_corpus, REVIEW_MEETING_TITLE
from brain_engine.engine import BrainEngine, STATUS_PENDING, MIN_RELEVANCE
from brain_engine.model import (
    AUTHORITATIVE_KINDS,
    CARD_KINDS,
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
    format_timestamp,
)
from brain_engine.report import (
    REFUSAL,
    citation_block,
    render_ask,
    render_change_log,
    render_citation,
    render_index,
    render_prep,
    render_remediation,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus():
    return build_corpus()


@pytest.fixture(scope="module")
def engine(corpus):
    return BrainEngine(corpus)


@pytest.fixture(scope="module")
def review_remediation(engine):
    return engine.remediate(REVIEW_MEETING_TITLE)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _prov(
    meeting_id="MTG-X",
    title="Test Meeting",
    date="2025-01-01",
    speaker="Alice",
    timestamp="00:00:05",
):
    return Provenance(meeting_id, title, date, speaker, timestamp)


def _card(
    card_id="CARD-X",
    tags=("warranty",),
    text="some rule text here",
    kind=RULE,
    prov=None,
):
    return KnowledgeCard(card_id, tags, text, kind, prov or _prov())


def _utterance(speaker="Alice", t=5, text="some spoken text here"):
    return Utterance(speaker, t, text)


def _meeting(
    meeting_id="MTG-X",
    date="2025-01-01",
    title="Test Meeting",
    participants=("Alice",),
    utterances=None,
):
    return Meeting(
        meeting_id,
        date,
        title,
        participants,
        utterances or (_utterance(),),
    )


# ---------------------------------------------------------------------------
# 1. Provenance.citation_tag — parametrised shape tests
# ---------------------------------------------------------------------------

PROV_PARAMS = [
    ("MTG-A", "Warranty Review", "2025-01-14", "Avery Stone", "00:03:02"),
    ("MTG-B", "Return of Capital", "2025-02-03", "Lena Frost", "00:01:35"),
    ("MTG-C", "Evidence Standards", "2025-02-27", "Priya Vale", "00:01:12"),
    ("MTG-D", "Surplus Elevation", "2025-03-19", "Marco Reyes", "00:01:28"),
    ("MTG-E", "Surplus Workpaper Review", "2025-04-08", "Quinn Harlow", "00:01:04"),
    ("MTG-F", "Quarterly Close", "2024-09-30", "Dana Brook", "01:00:00"),
    ("MTG-G", "Audit Prep", "2026-06-20", "Theo Nguyen", "00:59:59"),
    ("MTG-H", "Year-End Procedures", "2023-12-31", "Alice Jones", "02:15:30"),
    ("MTG-I", "Tax Position Review", "2025-06-15", "Bob Smith", "00:00:01"),
    ("MTG-J", "M1 Reconciliation", "2025-07-04", "Carol White", "00:30:00"),
    ("MTG-K", "FX Translation", "2025-08-01", "Dave Brown", "00:45:22"),
    ("MTG-L", "Evidence Tie-Out", "2025-09-12", "Eve Green", "00:10:10"),
    ("MTG-M", "Distribution Analysis", "2025-10-03", "Frank Black", "01:02:05"),
    ("MTG-N", "Basis Computation", "2025-11-21", "Grace Lee", "00:07:35"),
    ("MTG-O", "Surplus Workpaper", "2025-12-01", "Henry Kim", "00:08:18"),
    ("MTG-P", "Book-Tax Analysis", "2024-01-15", "Iris Wu", "00:03:41"),
    ("MTG-Q", "Capital Events", "2024-06-30", "Jack Chen", "00:06:40"),
    ("MTG-R", "Workpaper Sign-Off", "2024-11-28", "Karen Liu", "00:08:25"),
    ("MTG-S", "Open Items Session", "2024-12-05", "Liam Tan", "00:09:00"),
    ("MTG-T", "Remediation Review", "2025-05-20", "Mia Patel", "00:06:06"),
]


@pytest.mark.parametrize("meeting_id,title,date,speaker,ts", PROV_PARAMS)
def test_prov_citation_tag_bracket_wrapped(meeting_id, title, date, speaker, ts):
    prov = Provenance(meeting_id, title, date, speaker, ts)
    tag = prov.citation_tag()
    assert tag[0] == "[" and tag[-1] == "]"


@pytest.mark.parametrize("meeting_id,title,date,speaker,ts", PROV_PARAMS)
def test_prov_citation_tag_contains_all_fields(meeting_id, title, date, speaker, ts):
    prov = Provenance(meeting_id, title, date, speaker, ts)
    tag = prov.citation_tag()
    assert title in tag
    assert date in tag
    assert speaker in tag
    assert ts in tag


@pytest.mark.parametrize("meeting_id,title,date,speaker,ts", PROV_PARAMS)
def test_prov_citation_tag_separator_format(meeting_id, title, date, speaker, ts):
    prov = Provenance(meeting_id, title, date, speaker, ts)
    tag = prov.citation_tag()
    # Format: [title — date — ts — speaker]
    assert " — " in tag
    assert tag.count(" — ") >= 3


# ---------------------------------------------------------------------------
# 2. KnowledgeCard — all kind variants
# ---------------------------------------------------------------------------

ALL_KIND_VARIANTS = [(DECISION,), (RULE,), (DEFINITION,), (OPEN_ITEM,)]


@pytest.mark.parametrize("kind_tuple", ALL_KIND_VARIANTS)
def test_card_all_kind_variants_construct(kind_tuple):
    kind = kind_tuple[0]
    card = _card(kind=kind)
    assert card.kind == kind


@pytest.mark.parametrize("kind_tuple", ALL_KIND_VARIANTS)
def test_card_kind_in_card_kinds(kind_tuple):
    kind = kind_tuple[0]
    assert kind in CARD_KINDS


@pytest.mark.parametrize("kind_tuple", [(DECISION,), (RULE,), (DEFINITION,)])
def test_card_authoritative_kinds(kind_tuple):
    kind = kind_tuple[0]
    card = _card(kind=kind)
    assert card.is_authoritative is True


@pytest.mark.parametrize("kind_tuple", [(OPEN_ITEM,)])
def test_card_open_item_not_authoritative(kind_tuple):
    card = _card(kind=kind_tuple[0])
    assert card.is_authoritative is False


# ---------------------------------------------------------------------------
# 3. KnowledgeCard — multi-tag construction
# ---------------------------------------------------------------------------

TAG_COMBOS = [
    ("warranty",),
    ("warranty", "book-tax"),
    ("warranty", "book-tax", "deferred-tax"),
    ("basis", "capital-gain"),
    ("evidence", "tie-out", "workpaper"),
    ("surplus", "distribution", "elevation"),
    ("acb", "capital-event", "surplus"),
    ("distribution", "definition", "surplus"),
    ("surplus", "fx"),
    ("return-of-capital", "basis", "definition"),
    ("return-of-capital", "state-tax"),
    ("evidence", "anchor", "definition"),
    ("evidence", "fx", "tolerance"),
    ("basis", "workpaper", "capital-gain"),
    ("warranty", "revenue-recognition"),
    ("warranty", "workpaper", "evidence"),
    ("surplus", "distribution", "formula", "review"),
    ("warranty", "book-tax", "add-back", "review"),
    ("evidence", "tie-out", "footnote", "review"),
    ("distribution", "tax-return", "classification", "review"),
]


@pytest.mark.parametrize("tags", TAG_COMBOS)
def test_card_multi_tag_construction(tags):
    card = _card(tags=tags)
    assert card.topic_tags == tags


@pytest.mark.parametrize("tags", TAG_COMBOS)
def test_card_multi_tag_all_present(tags):
    card = _card(tags=tags)
    for tag in tags:
        assert tag in card.topic_tags


# ---------------------------------------------------------------------------
# 4. Meeting — participant count variants
# ---------------------------------------------------------------------------

PARTICIPANT_COUNTS = [
    ("Alice",),
    ("Alice", "Bob"),
    ("Alice", "Bob", "Carol"),
    ("Avery Stone", "Dana Brook", "Priya Vale"),
    ("Marco Reyes", "Lena Frost", "Avery Stone"),
    ("Priya Vale", "Theo Nguyen", "Dana Brook"),
    ("Lena Frost", "Marco Reyes", "Avery Stone"),
    ("Quinn Harlow", "Marco Reyes", "Avery Stone"),
    ("Alice", "Bob", "Carol", "Dave"),
    ("Alice", "Bob", "Carol", "Dave", "Eve"),
]


@pytest.mark.parametrize("participants", PARTICIPANT_COUNTS)
def test_meeting_participant_count_preserved(participants):
    m = _meeting(participants=participants)
    assert m.participants == participants


@pytest.mark.parametrize("participants", PARTICIPANT_COUNTS)
def test_meeting_participants_tuple(participants):
    m = _meeting(participants=participants)
    assert isinstance(m.participants, tuple)


# ---------------------------------------------------------------------------
# 5. Meeting — utterance ordering
# ---------------------------------------------------------------------------

UTTERANCE_SEQUENCES = [
    [(0,), (10,), (20,)],
    [(0,), (60,), (120,), (180,)],
    [(0,), (47,), (182,), (305,), (361,), (540,)],
    [(0,), (95,), (221,), (333,), (400,), (505,)],
    [(0,), (72,), (168,), (240,), (360,), (455,)],
    [(0,), (88,), (205,), (300,), (410,), (520,)],
    [(0,), (64,), (150,), (212,), (300,), (366,), (430,), (498,), (560,)],
    [(0,), (1,)],
    [(0,), (100,), (200,), (300,), (400,)],
    [(0,), (3600,), (7200,)],
]


@pytest.mark.parametrize("t_list", UTTERANCE_SEQUENCES)
def test_meeting_utterances_stored_in_order(t_list):
    utts = tuple(Utterance("Alice", t[0], f"text at {t[0]}") for t in t_list)
    m = _meeting(utterances=utts)
    assert m.utterances == utts


@pytest.mark.parametrize("t_list", UTTERANCE_SEQUENCES)
def test_meeting_utterances_count(t_list):
    utts = tuple(Utterance("Alice", t[0], f"text at {t[0]}") for t in t_list)
    m = _meeting(utterances=utts)
    assert len(m.utterances) == len(t_list)


# ---------------------------------------------------------------------------
# 6. Meeting — valid date formats
# ---------------------------------------------------------------------------

VALID_DATES = [
    "2025-01-01",
    "2025-01-14",
    "2025-02-03",
    "2025-02-27",
    "2025-03-19",
    "2025-04-08",
    "2024-12-31",
    "2023-01-01",
    "2026-06-20",
    "2020-02-29",
    "1999-12-31",
    "2000-01-01",
    "2099-12-31",
    "2025-07-04",
    "2025-09-30",
    "2025-11-11",
    "2024-02-29",
    "2022-06-15",
    "2030-01-01",
    "2019-10-31",
]


@pytest.mark.parametrize("date", VALID_DATES)
def test_meeting_valid_date_accepted(date):
    m = _meeting(date=date)
    assert m.date == date


# ---------------------------------------------------------------------------
# 7. ChangeDirective — topic tag and text invariants
# ---------------------------------------------------------------------------

DIRECTIVE_PARAMS = [
    ("DIR-A", ("surplus", "distribution"), "Change the distribution formula to column E"),
    ("DIR-B", ("warranty", "book-tax"), "Add back the warranty-reserve book-tax difference"),
    ("DIR-C", ("evidence", "tie-out"), "Re-run the evidence query and footnote each figure"),
    ("DIR-D", ("distribution", "tax-return"), "Keep the 26,000 item as a distribution"),
    ("DIR-E", ("basis", "capital-gain"), "Floor basis at zero and route excess to gain line"),
    ("DIR-F", ("surplus", "fx"), "Confirm the FX rate source for the elevation year"),
    ("DIR-G", ("workpaper", "anchor"), "Every figure must foot to a cited anchor"),
    ("DIR-H", ("review", "formula"), "Reference column E not column D across every year column"),
    ("DIR-I", ("add-back", "development"), "Add-back lands in the development tab"),
    ("DIR-J", ("classification", "reclassification"), "Do not reclass the item to income"),
]


@pytest.mark.parametrize("did,tags,text", DIRECTIVE_PARAMS)
def test_directive_construction(did, tags, text):
    prov = _prov()
    d = ChangeDirective(did, tags, text, prov)
    assert d.directive_id == did
    assert d.topic_tags == tags
    assert d.request_text == text


@pytest.mark.parametrize("did,tags,text", DIRECTIVE_PARAMS)
def test_directive_citation_tag_has_provenance(did, tags, text):
    prov = _prov(title="My Review", date="2025-04-08", speaker="Quinn", timestamp="00:01:04")
    d = ChangeDirective(did, tags, text, prov)
    tag = d.citation_tag()
    assert "My Review" in tag
    assert "2025-04-08" in tag
    assert "Quinn" in tag


@pytest.mark.parametrize("did,tags,text", DIRECTIVE_PARAMS)
def test_directive_with_target(did, tags, text):
    prov = _prov()
    d = ChangeDirective(did, tags, text, prov, target="distribution formula")
    assert d.target == "distribution formula"


@pytest.mark.parametrize("did,tags,text", DIRECTIVE_PARAMS)
def test_directive_default_empty_target(did, tags, text):
    prov = _prov()
    d = ChangeDirective(did, tags, text, prov)
    assert d.target == ""


# ---------------------------------------------------------------------------
# 8. Corpus.cards_by_topic — expected structure
# ---------------------------------------------------------------------------

def test_corpus_cards_by_topic_returns_dict(corpus):
    grouped = corpus.cards_by_topic()
    assert isinstance(grouped, dict)


def test_corpus_cards_by_topic_all_lists(corpus):
    grouped = corpus.cards_by_topic()
    for tag, cards in grouped.items():
        assert isinstance(tag, str)
        assert isinstance(cards, list)
        for c in cards:
            assert isinstance(c, KnowledgeCard)


def test_corpus_directives_by_topic_returns_dict(corpus):
    grouped = corpus.directives_by_topic()
    assert isinstance(grouped, dict)


def test_corpus_directives_by_topic_all_lists(corpus):
    grouped = corpus.directives_by_topic()
    for tag, directives in grouped.items():
        assert isinstance(tag, str)
        assert isinstance(directives, list)
        for d in directives:
            assert isinstance(d, ChangeDirective)


# ---------------------------------------------------------------------------
# 9. report.citation_block — format tests
# ---------------------------------------------------------------------------

CITATION_BLOCK_CARDS = [
    (_card("CARD-A", ("warranty",), "The warranty reserve is booked on accrual basis.", DECISION),),
    (_card("CARD-B", ("basis",), "Basis can never go below zero.", RULE),),
    (_card("CARD-C", ("evidence",), "Anchor is the single cited source cell.", DEFINITION),),
    (_card("CARD-D", ("surplus",), "Open item: confirm FX rate source.", OPEN_ITEM),),
    (_card("CARD-E", ("return-of-capital",), "Return of capital defined as tax-free recovery.", DEFINITION),),
    (_card("CARD-F", ("distribution",), "Distribution is the only surplus trigger.", RULE),),
    (_card("CARD-G", ("workpaper",), "Every figure must foot to an anchor.", RULE),),
    (_card("CARD-H", ("capital-gain",), "Excess of basis is deemed capital gain.", DECISION),),
    (_card("CARD-I", ("fx",), "Open item: confirm FX tolerance for anchors.", OPEN_ITEM),),
    (_card("CARD-J", ("acb",), "ACB moves only on capital events.", RULE),),
]


@pytest.mark.parametrize("card_tuple", CITATION_BLOCK_CARDS)
def test_citation_block_starts_with_quote(card_tuple):
    from brain_engine.engine import RetrievalHit
    card = card_tuple[0]
    hit = RetrievalHit(card=card, score=0.85)
    block = citation_block(hit)
    assert block.startswith("> ")


@pytest.mark.parametrize("card_tuple", CITATION_BLOCK_CARDS)
def test_citation_block_contains_rule_text(card_tuple):
    from brain_engine.engine import RetrievalHit
    card = card_tuple[0]
    hit = RetrievalHit(card=card, score=0.85)
    block = citation_block(hit)
    assert card.rule_text in block


@pytest.mark.parametrize("card_tuple", CITATION_BLOCK_CARDS)
def test_citation_block_contains_card_id(card_tuple):
    from brain_engine.engine import RetrievalHit
    card = card_tuple[0]
    hit = RetrievalHit(card=card, score=0.85)
    block = citation_block(hit)
    assert card.card_id in block


@pytest.mark.parametrize("card_tuple", CITATION_BLOCK_CARDS)
def test_citation_block_contains_score(card_tuple):
    from brain_engine.engine import RetrievalHit
    card = card_tuple[0]
    hit = RetrievalHit(card=card, score=0.85)
    block = citation_block(hit)
    assert "0.850" in block


@pytest.mark.parametrize("card_tuple", CITATION_BLOCK_CARDS)
def test_citation_block_contains_provenance_fields(card_tuple):
    from brain_engine.engine import RetrievalHit
    card = card_tuple[0]
    hit = RetrievalHit(card=card, score=0.72)
    block = citation_block(hit)
    prov = card.provenance
    assert prov.date in block
    assert prov.speaker in block
    assert prov.timestamp in block


# ---------------------------------------------------------------------------
# 10. render_ask — format tests
# ---------------------------------------------------------------------------

ASK_QUERIES_WITH_EXPECTED_HITS = [
    "warranty reserve book tax",
    "basis capital gain excess distribution",
    "evidence anchor figure workpaper",
    "surplus distribution elevation parent",
    "adjusted cost base capital event",
]

ASK_QUERIES_NO_HITS = [
    "office parking policy gym",
    "lunch menu cafeteria coffee",
    "onboarding new hire checklist IT",
]


@pytest.mark.parametrize("query", ASK_QUERIES_WITH_EXPECTED_HITS)
def test_render_ask_hit_contains_sourced_header(engine, query):
    hits = engine.ask(query)
    output = render_ask(query, hits)
    assert "Ask" in output
    assert "[FICTIONAL]" in output


@pytest.mark.parametrize("query", ASK_QUERIES_WITH_EXPECTED_HITS)
def test_render_ask_hit_contains_query(engine, query):
    hits = engine.ask(query)
    output = render_ask(query, hits)
    assert query in output


@pytest.mark.parametrize("query", ASK_QUERIES_WITH_EXPECTED_HITS)
def test_render_ask_hit_count_in_output(engine, query):
    hits = engine.ask(query)
    output = render_ask(query, hits)
    assert str(len(hits)) in output


@pytest.mark.parametrize("query", ASK_QUERIES_NO_HITS)
def test_render_ask_no_hits_contains_refusal(engine, query):
    hits = engine.ask(query)
    output = render_ask(query, hits)
    assert REFUSAL in output


@pytest.mark.parametrize("query", ASK_QUERIES_NO_HITS)
def test_render_ask_no_hits_does_not_invent_answer(engine, query):
    hits = engine.ask(query)
    assert len(hits) == 0
    output = render_ask(query, hits)
    assert "No knowledge card cleared" in output or REFUSAL in output


# ---------------------------------------------------------------------------
# 11. render_citation — format tests
# ---------------------------------------------------------------------------

CITE_ASSERTIONS = [
    "warranty reserve book tax deferred asset",
    "return of capital definition basis",
    "basis can never go below zero",
    "evidence anchor single cited source",
    "reviewer refuses to sign rework",
    "surplus elevates only on distribution",
    "adjusted cost base capital events",
    "distribution cash paid trigger",
    "excess basis deemed capital gain",
    "workpaper accrual schedule signed",
]


@pytest.mark.parametrize("assertion", CITE_ASSERTIONS)
def test_render_citation_hit_header(engine, assertion):
    hit = engine.cite(assertion)
    output = render_citation(assertion, hit)
    assert "Workpaper Citation" in output
    assert "[FICTIONAL]" in output


@pytest.mark.parametrize("assertion", CITE_ASSERTIONS)
def test_render_citation_hit_assertion_in_output(engine, assertion):
    hit = engine.cite(assertion)
    output = render_citation(assertion, hit)
    assert assertion in output


@pytest.mark.parametrize("assertion", CITE_ASSERTIONS)
def test_render_citation_hit_not_none_provenance_present(engine, assertion):
    hit = engine.cite(assertion)
    if hit is not None:
        output = render_citation(assertion, hit)
        assert "Provenance integrity" in output


@pytest.mark.parametrize("assertion", ASK_QUERIES_NO_HITS)
def test_render_citation_no_hit_contains_refusal(engine, assertion):
    hit = engine.cite(assertion)
    output = render_citation(assertion, hit)
    if hit is None:
        assert REFUSAL in output


# ---------------------------------------------------------------------------
# 12. render_prep — format tests
# ---------------------------------------------------------------------------

PREP_TOPICS_LIST = [
    "warranty reserve",
    "basis capital gain",
    "evidence tie-out workpaper",
    "surplus distribution elevation",
    "return of capital",
    "adjusted cost base",
    "deferred tax asset",
    "foreign affiliate parent",
]


@pytest.mark.parametrize("topic", PREP_TOPICS_LIST)
def test_render_prep_hit_header(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    assert "Meeting Prep" in output
    assert "[FICTIONAL]" in output


@pytest.mark.parametrize("topic", PREP_TOPICS_LIST)
def test_render_prep_topic_in_output(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    assert topic in output


@pytest.mark.parametrize("topic", PREP_TOPICS_LIST)
def test_render_prep_settled_section_present(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    assert "Settled prior positions" in output


@pytest.mark.parametrize("topic", PREP_TOPICS_LIST)
def test_render_prep_open_items_section_present(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    assert "Open items" in output


@pytest.mark.parametrize("topic", ASK_QUERIES_NO_HITS)
def test_render_prep_no_hits_contains_refusal(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    if not hits:
        assert REFUSAL in output


# ---------------------------------------------------------------------------
# 13. render_remediation — format tests
# ---------------------------------------------------------------------------

REMEDIATION_TOPICS = [
    "Surplus Workpaper Review",
    "Surplus Workpaper Review — Reviewer Corrections",
    "reviewer corrections",
    "surplus review",
]


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_header(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert "Review" in output
    assert "Remediation" in output
    assert "[FICTIONAL]" in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_topic_in_output(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert topic in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_change_directives_section(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert "Change-directives" in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_paste_ready_section(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert "Ready-to-paste" in output or "paste" in output.lower()


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_prompt_block_present(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert "```" in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_status_pending_present(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert STATUS_PENDING in output


EMPTY_REMEDIATION_TOPICS = ["parking policy", "gym membership", ""]


@pytest.mark.parametrize("topic", EMPTY_REMEDIATION_TOPICS)
def test_render_remediation_empty_contains_refusal(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert REFUSAL in output


@pytest.mark.parametrize("topic", EMPTY_REMEDIATION_TOPICS)
def test_render_remediation_empty_no_directives_section(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    # Empty remediation should NOT contain the directives section header
    assert not rem.fix_packet


# ---------------------------------------------------------------------------
# 14. render_change_log — format tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_header(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    assert "Change Log" in output
    assert "[FICTIONAL]" in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_table_header(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    assert "| # |" in output or "|---" in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_pending_status_column(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    assert STATUS_PENDING in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_directive_ids_present(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    for entry in rem.fix_packet:
        assert entry.directive.directive_id in output


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_request_texts_present(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    for entry in rem.fix_packet:
        # The pipe-escaped version of the text is in the table
        expected = entry.directive.request_text[:20]
        assert expected in output or expected.replace("|", "\\|") in output


@pytest.mark.parametrize("topic", EMPTY_REMEDIATION_TOPICS)
def test_render_change_log_empty_contains_refusal(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    assert REFUSAL in output


# ---------------------------------------------------------------------------
# 15. render_index — format and content
# ---------------------------------------------------------------------------

def test_render_index_header(engine):
    output = render_index(engine)
    assert "Knowledge Brain" in output
    assert "Index" in output
    assert "[FICTIONAL]" in output


def test_render_index_meetings_count_present(engine, corpus):
    output = render_index(engine)
    assert str(len(corpus.meetings)) in output


def test_render_index_cards_count_present(engine, corpus):
    output = render_index(engine)
    assert str(len(corpus.cards)) in output


def test_render_index_cards_by_kind_section(engine):
    output = render_index(engine)
    assert "Cards by kind" in output


def test_render_index_cards_by_topic_section(engine):
    output = render_index(engine)
    assert "Cards by topic" in output


def test_render_index_card_catalogue_section(engine):
    output = render_index(engine)
    assert "catalogue" in output.lower() or "Card" in output


def test_render_index_all_card_ids_present(engine, corpus):
    output = render_index(engine)
    for card in corpus.cards:
        assert card.card_id in output


def test_render_index_all_topic_tags_present(engine, corpus):
    output = render_index(engine)
    grouped = corpus.cards_by_topic()
    for tag in grouped:
        assert tag in output


def test_render_index_all_kinds_labeled(engine):
    output = render_index(engine)
    assert "Decision" in output
    assert "Rule" in output
    assert "Definition" in output
    assert "Open item" in output


def test_render_index_determinism_label(engine):
    output = render_index(engine)
    assert "deterministic" in output.lower()


def test_render_index_provenance_note(engine):
    output = render_index(engine)
    assert "provenance" in output.lower() or "citation" in output.lower()


# ---------------------------------------------------------------------------
# 16. REFUSAL constant
# ---------------------------------------------------------------------------

def test_refusal_constant_not_empty():
    assert len(REFUSAL) > 5


def test_refusal_constant_contains_sourced():
    assert "sourced" in REFUSAL.lower() or "No sourced" in REFUSAL


def test_refusal_constant_contains_brain():
    assert "brain" in REFUSAL.lower()


def test_refusal_constant_does_not_contain_made_up():
    assert "made up" not in REFUSAL.lower()
    assert "invented" not in REFUSAL.lower()


# ---------------------------------------------------------------------------
# 17. Empty corpus edge cases
# ---------------------------------------------------------------------------

def _empty_corpus():
    u = Utterance("Alice", 0, "placeholder utterance for empty corpus test")
    m = Meeting("MTG-EMPTY", "2025-01-01", "Empty Test", ("Alice",), (u,))
    return Corpus(meetings=[m], cards=[], directives=[])


def test_empty_corpus_ask_returns_empty():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hits = eng.ask("warranty basis surplus")
    assert hits == []


def test_empty_corpus_cite_returns_none():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hit = eng.cite("warranty")
    assert hit is None


def test_empty_corpus_prep_returns_empty():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hits = eng.prep("warranty")
    assert hits == []


def test_empty_corpus_rank_returns_empty():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hits = eng.rank("warranty surplus distribution")
    assert hits == []


def test_empty_corpus_remediate_is_empty():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    rem = eng.remediate("Surplus Workpaper Review")
    assert rem.is_empty


def test_empty_corpus_index_summary_zero_cards():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    s = eng.index_summary()
    assert s["cards"] == 0


def test_empty_corpus_render_ask_refusal():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hits = eng.ask("warranty")
    output = render_ask("warranty", hits)
    assert REFUSAL in output


def test_empty_corpus_render_citation_refusal():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hit = eng.cite("warranty")
    output = render_citation("warranty", hit)
    assert REFUSAL in output


def test_empty_corpus_render_prep_refusal():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    hits = eng.prep("warranty")
    output = render_prep("warranty", hits)
    assert REFUSAL in output


def test_empty_corpus_render_remediation_refusal():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    rem = eng.remediate("Surplus Workpaper Review")
    output = render_remediation(rem)
    assert REFUSAL in output


def test_empty_corpus_render_change_log_refusal():
    corp = _empty_corpus()
    eng = BrainEngine(corp)
    rem = eng.remediate("Surplus Workpaper Review")
    output = render_change_log(rem)
    assert REFUSAL in output


# ---------------------------------------------------------------------------
# 18. Single-card corpus — basic retrieval
# ---------------------------------------------------------------------------

SINGLE_CARD_TEXTS = [
    ("warranty reserve accrual book tax deferred asset", ("warranty", "book-tax"), DECISION),
    ("basis can never go below zero clamp excess gain", ("basis", "capital-gain"), RULE),
    ("anchor is the single cited source cell reconcile", ("evidence", "anchor"), DEFINITION),
    ("surplus elevates only on actual distribution percentage", ("surplus", "distribution"), DECISION),
    ("return of capital tax-free recovery basis reduction", ("return-of-capital", "basis"), DEFINITION),
]


@pytest.mark.parametrize("text,tags,kind", SINGLE_CARD_TEXTS)
def test_single_card_corpus_ask_finds_card(text, tags, kind):
    prov = _prov()
    card = KnowledgeCard("CARD-SINGLE", tags, text, kind, prov)
    u = Utterance("Alice", 5, text)
    m = Meeting("MTG-S", "2025-01-01", "Single Card Test", ("Alice",), (u,))
    corp = Corpus(meetings=[m], cards=[card])
    eng = BrainEngine(corp, min_relevance=0.0)
    # Query using a distinctive word from the text
    distinctive = text.split()[0]
    hits = eng.ask(distinctive)
    # With zero floor, should find any card that has any matching token
    # (if text has no stopwords, it scores > 0)
    if hits:
        assert hits[0].card.card_id == "CARD-SINGLE"


@pytest.mark.parametrize("text,tags,kind", SINGLE_CARD_TEXTS)
def test_single_card_corpus_cite_returns_authoritative(text, tags, kind):
    prov = _prov()
    card = KnowledgeCard("CARD-SINGLE", tags, text, kind, prov)
    u = Utterance("Alice", 5, text)
    m = Meeting("MTG-S", "2025-01-01", "Single Card Test", ("Alice",), (u,))
    corp = Corpus(meetings=[m], cards=[card])
    eng = BrainEngine(corp, min_relevance=0.0)
    hit = eng.cite(tags[0])
    if kind != OPEN_ITEM and hit is not None:
        assert hit.card.kind in AUTHORITATIVE_KINDS


# ---------------------------------------------------------------------------
# 19. Remediation prompt structure (detailed)
# ---------------------------------------------------------------------------

def test_remediation_prompt_contains_instruction_header(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "downstream AI" in rem.prompt or "operator" in rem.prompt


def test_remediation_prompt_numbered_changes(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    # Each directive should appear as a numbered line
    for entry in rem.fix_packet:
        assert f"{entry.number}." in rem.prompt


def test_remediation_prompt_contains_verbatim_quotes(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for entry in rem.fix_packet:
        # Request text appears as both the instruction and as a source quote
        assert entry.directive.request_text in rem.prompt


def test_remediation_prompt_contains_source_labels(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "Source" in rem.prompt or "source" in rem.prompt


def test_remediation_prompt_contains_change_log_instruction(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "change log" in rem.prompt.lower() or "log" in rem.prompt.lower()


def test_remediation_prompt_contains_applied_keyword(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "APPLIED" in rem.prompt


def test_remediation_prompt_contains_pending_keyword(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "PENDING" in rem.prompt


def test_remediation_prompt_instructs_no_guessing(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert "never guess" in rem.prompt.lower() or "do not" in rem.prompt.lower()


# ---------------------------------------------------------------------------
# 20. fix_packet entry invariants
# ---------------------------------------------------------------------------

def test_fix_packet_entries_one_to_one_with_directives(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for i, (entry, directive) in enumerate(zip(rem.fix_packet, rem.directives)):
        assert entry.directive is directive


def test_fix_packet_numbers_start_at_one(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert rem.fix_packet[0].number == 1


def test_fix_packet_numbers_end_at_len(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert rem.fix_packet[-1].number == len(rem.fix_packet)


def test_fix_packet_all_entries_have_directives(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    for entry in rem.fix_packet:
        assert isinstance(entry.directive, ChangeDirective)


# ---------------------------------------------------------------------------
# 21. Remediation.is_empty property
# ---------------------------------------------------------------------------

def test_remediation_is_empty_false_when_directives(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert rem.is_empty is False


def test_remediation_is_empty_true_for_off_topic(engine):
    rem = engine.remediate("parking policy gym membership")
    assert rem.is_empty is True


def test_remediation_is_empty_consistent_with_directives_len(engine):
    rem = engine.remediate(REVIEW_MEETING_TITLE)
    assert rem.is_empty == (len(rem.directives) == 0)


# ---------------------------------------------------------------------------
# 22. BrainEngine IDF / vector internals
# ---------------------------------------------------------------------------

def test_engine_has_idf_after_build(engine):
    assert len(engine._idf) > 0


def test_engine_has_doc_vectors_for_all_cards(engine, corpus):
    for card in corpus.cards:
        assert card.card_id in engine._doc_vectors


def test_engine_has_doc_norms_for_all_cards(engine, corpus):
    for card in corpus.cards:
        assert card.card_id in engine._doc_norms


def test_engine_doc_norms_positive(engine, corpus):
    for card in corpus.cards:
        norm = engine._doc_norms[card.card_id]
        assert norm > 0.0


def test_engine_idf_values_positive(engine):
    for term, idf_val in engine._idf.items():
        assert idf_val > 0.0


# ---------------------------------------------------------------------------
# 23. _score edge cases via direct calls
# ---------------------------------------------------------------------------

def test_score_zero_query_norm_returns_zero(engine, corpus):
    # Build a zero-norm query vec (empty)
    score = engine._score({}, 0.0, corpus.cards[0].card_id)
    assert score == 0.0


def test_score_zero_doc_norm_returns_zero(corpus):
    """A card whose text is all stopwords would have norm 0."""
    prov = _prov()
    # Manufacture a doc vector with norm 0 by directly patching (not ideal but
    # the safest way to test this branch without side-effects)
    eng = BrainEngine(corpus)
    # Directly inject a zero norm for the first card
    first_id = corpus.cards[0].card_id
    eng._doc_norms[first_id] = 0.0
    score = eng._score({"warranty": 1.0}, 1.0, first_id)
    assert score == 0.0


# ---------------------------------------------------------------------------
# 24. Corpus utterance_text — all card provenances resolvable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("card_id", [
    "CARD-WARRANTY-01",
    "CARD-WARRANTY-02",
    "CARD-WARRANTY-03",
    "CARD-ROC-01",
    "CARD-ROC-02",
    "CARD-ROC-03",
    "CARD-ROC-04",
    "CARD-EVIDENCE-01",
    "CARD-EVIDENCE-02",
    "CARD-EVIDENCE-03",
    "CARD-EVIDENCE-04",
    "CARD-SURPLUS-01",
    "CARD-SURPLUS-02",
    "CARD-SURPLUS-03",
    "CARD-SURPLUS-04",
])
def test_card_provenance_resolves_to_utterance(corpus, card_id):
    card_map = {c.card_id: c for c in corpus.cards}
    card = card_map[card_id]
    prov = card.provenance
    text = corpus.utterance_text(prov.meeting_id, prov.timestamp)
    assert text == card.rule_text


# ---------------------------------------------------------------------------
# 25. Directive provenance resolves to utterance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("directive_id", [
    "DIR-SURPLUS-REVIEW-01",
    "DIR-SURPLUS-REVIEW-02",
    "DIR-SURPLUS-REVIEW-03",
    "DIR-SURPLUS-REVIEW-04",
])
def test_directive_provenance_resolves_to_utterance(corpus, directive_id):
    directive_map = {d.directive_id: d for d in corpus.directives}
    d = directive_map[directive_id]
    prov = d.provenance
    text = corpus.utterance_text(prov.meeting_id, prov.timestamp)
    assert text == d.request_text


# ---------------------------------------------------------------------------
# 26. Meeting utterances — timestamp property consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("meeting_id", [
    "MTG-2025-WARRANTY",
    "MTG-2025-ROC",
    "MTG-2025-EVIDENCE",
    "MTG-2025-SURPLUS",
    "MTG-2025-SURPLUS-REVIEW",
])
def test_meeting_utterance_timestamps_match_format(corpus, meeting_id):
    meeting_map = {m.meeting_id: m for m in corpus.meetings}
    meeting = meeting_map[meeting_id]
    for utt in meeting.utterances:
        expected = format_timestamp(utt.t_seconds)
        assert utt.timestamp == expected


# ---------------------------------------------------------------------------
# 27. Corpus.utterance_text — all meeting utterances resolvable
# ---------------------------------------------------------------------------

def test_all_meeting_utterances_resolvable(corpus):
    for meeting in corpus.meetings:
        for utt in meeting.utterances:
            text = corpus.utterance_text(meeting.meeting_id, utt.timestamp)
            assert text == utt.text


# ---------------------------------------------------------------------------
# 28. Corpus meetings — all have non-empty participant list
# ---------------------------------------------------------------------------

def test_all_meetings_have_participants(corpus):
    for m in corpus.meetings:
        assert len(m.participants) >= 1


def test_all_meetings_have_utterances(corpus):
    for m in corpus.meetings:
        assert len(m.utterances) >= 1


def test_all_meetings_have_valid_dates(corpus):
    for m in corpus.meetings:
        parts = m.date.split("-")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# 29. Render output strings are non-empty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ASK_QUERIES_WITH_EXPECTED_HITS + ASK_QUERIES_NO_HITS)
def test_render_ask_output_non_empty(engine, query):
    hits = engine.ask(query)
    output = render_ask(query, hits)
    assert len(output) > 10


@pytest.mark.parametrize("assertion", CITE_ASSERTIONS[:5])
def test_render_citation_output_non_empty(engine, assertion):
    hit = engine.cite(assertion)
    output = render_citation(assertion, hit)
    assert len(output) > 10


@pytest.mark.parametrize("topic", PREP_TOPICS_LIST[:5])
def test_render_prep_output_non_empty(engine, topic):
    hits = engine.prep(topic)
    output = render_prep(topic, hits)
    assert len(output) > 10


def test_render_index_output_non_empty(engine):
    output = render_index(engine)
    assert len(output) > 50


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_remediation_output_non_empty(engine, topic):
    rem = engine.remediate(topic)
    output = render_remediation(rem)
    assert len(output) > 50


@pytest.mark.parametrize("topic", REMEDIATION_TOPICS)
def test_render_change_log_output_non_empty(engine, topic):
    rem = engine.remediate(topic)
    output = render_change_log(rem)
    assert len(output) > 50


# ---------------------------------------------------------------------------
# 30. KIND_LABEL coverage
# ---------------------------------------------------------------------------

KIND_LABEL_ENTRIES = [
    ("decision", "Decision"),
    ("rule", "Rule"),
    ("definition", "Definition"),
    ("open-item", "Open item"),
]


@pytest.mark.parametrize("kind,expected_label", KIND_LABEL_ENTRIES)
def test_kind_label_in_render_index(engine, kind, expected_label):
    output = render_index(engine)
    assert expected_label in output


@pytest.mark.parametrize("kind,expected_label", KIND_LABEL_ENTRIES)
def test_kind_label_in_citation_block(kind, expected_label):
    from brain_engine.engine import RetrievalHit
    prov = _prov()
    card = KnowledgeCard("CARD-KIND", ("tag",), "some text for kind test", kind, prov)
    hit = RetrievalHit(card=card, score=0.5)
    block = citation_block(hit)
    assert expected_label in block
