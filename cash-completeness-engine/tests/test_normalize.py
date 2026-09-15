"""GL normalization: format equivalence and placeholder detection."""

from __future__ import annotations

import pytest

from ccengine.normalize import is_placeholder_gl, normalize_gl

CANONICAL = "615-001-1133"


# ---------------------------------------------------------------------------
# Format equivalence: every real-world spelling collapses to one key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "615-001-00-1133",     # filler segment
        "615-001-1133",        # already canonical
        6150011133,            # int (spreadsheet export)
        6150011133.0,          # whole float (spreadsheet export)
        "6150011133",          # unseparated ten digits
        "615001001133",        # unseparated twelve digits with 00 filler
        " 615-001-1133 ",      # stray whitespace
        chr(0xFEFF) + "615-001-1133",  # UTF-8 byte-order mark
        "615.001.00.1133",     # alternative separator
    ],
)
def test_equivalent_spellings_collapse_to_canonical(raw):
    assert normalize_gl(raw) == CANONICAL


def test_spec_examples_all_match_each_other():
    assert (
        normalize_gl("615-001-00-1133")
        == normalize_gl("615-001-1133")
        == normalize_gl(6150011133)
        == "615-001-1133"
    )


def test_leading_and_trailing_segments_are_positional_and_kept():
    # Only *interior* zero-only fillers are dropped.
    assert normalize_gl("001-001-0000") == "001-001-0000"
    assert normalize_gl("000-123-4567") == "000-123-4567"


def test_non_ten_digit_inputs_return_bare_digit_string():
    assert normalize_gl("12-34") == "1234"
    assert normalize_gl("615-001-113") == "615001113"
    assert normalize_gl(42) == "42"


def test_digit_free_input_passes_through_verbatim():
    # A mis-keyed "BAL" stays visible and two identical typos still match.
    assert normalize_gl("BAL") == "BAL"
    assert normalize_gl(" BAL ") == "BAL"
    assert normalize_gl("BAL") == normalize_gl("BAL")


@pytest.mark.parametrize(
    "bad",
    [None, "", "   ", True, False, 12.5, float("nan"), float("inf")],
)
def test_unusable_inputs_raise_value_error(bad):
    with pytest.raises(ValueError):
        normalize_gl(bad)


# ---------------------------------------------------------------------------
# Placeholder detection: typo lines must be flagged, never matched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "suspicious",
    [
        None,               # cannot normalize
        "",                 # blank
        12.5,               # non-whole float
        "BAL",              # no digits at all
        "0000000000",       # all zeros
        "000-000-0000",     # all zeros, separated
        "001-001-1133",     # mis-keyed BAL-row prefix
        "001-001-0000",     # mis-keyed BAL-row prefix, zero natural account
        "001-001-00-1133",  # same prefix through the filler spelling
    ],
)
def test_placeholder_keys_are_flagged(suspicious):
    assert is_placeholder_gl(suspicious) is True


@pytest.mark.parametrize(
    "real",
    ["615-001-1133", "615-001-00-1133", 6150011133, "12-34", "424-002-1101"],
)
def test_real_keys_are_not_flagged(real):
    assert is_placeholder_gl(real) is False
