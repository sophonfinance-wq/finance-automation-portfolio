"""Coverage tests for the safe formula evaluator (``triangulate.formula``).

These pin down the shunting-yard evaluator's arithmetic, precedence,
parenthesisation, reference resolution and the exact error paths -- the
guarantees the deterministic audit relies on to re-derive cell values without
ever calling :func:`eval`.
"""

from __future__ import annotations

import pytest

from triangulate.formula import FormulaError, evaluate


# --------------------------------------------------------------------------- #
# Arithmetic + precedence (input -> expected derived from actual behaviour)    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "formula, values, expected",
    [
        ("=B2+B3", {"B2": 10, "B3": 5}, 15.0),
        ("=B2-B3", {"B2": 10, "B3": 5}, 5.0),
        ("=B2*B3", {"B2": 10, "B3": 5}, 50.0),
        ("=B2/B3", {"B2": 10, "B3": 4}, 2.5),
        ("=B2+B3*B4", {"B2": 1, "B3": 2, "B4": 3}, 7.0),  # * before +
        ("=B2*B3+B4", {"B2": 2, "B3": 3, "B4": 4}, 10.0),
        ("=(B2+B3)*B4", {"B2": 1, "B3": 2, "B4": 3}, 9.0),  # parens override
        ("=B2-B3-B4", {"B2": 10, "B3": 3, "B4": 2}, 5.0),  # left-assoc
        ("=B2/B3/B4", {"B2": 100, "B3": 5, "B4": 2}, 10.0),  # left-assoc
        ("=B2*B3-B4", {"B2": 10, "B3": 5, "B4": 4}, 46.0),
        ("=((B2))", {"B2": 7}, 7.0),  # nested redundant parens
        ("=2+3", {}, 5.0),  # numeric literals only
        ("=2.5*4", {}, 10.0),  # decimal literal
        ("=B2+B3+B4", {"B2": 1, "B3": 2, "B4": 3}, 6.0),
    ],
)
def test_evaluate_arithmetic_and_precedence(formula, values, expected):
    assert evaluate(formula, values) == expected


def test_leading_equals_is_optional():
    # The leading '=' is stripped; with or without it the result is identical.
    assert evaluate("=B2+B3", {"B2": 4, "B3": 6}) == evaluate(
        "B2+B3", {"B2": 4, "B3": 6}
    )
    assert evaluate("B2+B3", {"B2": 4, "B3": 6}) == 10.0


def test_whitespace_is_ignored():
    assert evaluate("=  B2  +   B3 ", {"B2": 1, "B3": 2}) == 3.0


def test_multi_letter_cell_references_resolve():
    assert evaluate("=AA1+AB2", {"AA1": 4, "AB2": 5}) == 9.0


def test_return_type_is_float_even_for_integers():
    result = evaluate("=B2+B3", {"B2": 1, "B3": 1})
    assert isinstance(result, float)
    assert result == 2.0


# --------------------------------------------------------------------------- #
# Error paths                                                                  #
# --------------------------------------------------------------------------- #
def test_missing_cell_raises_formula_error():
    with pytest.raises(FormulaError, match="missing cell"):
        evaluate("=B9", {"B2": 1})


def test_none_valued_cell_treated_as_missing():
    with pytest.raises(FormulaError, match="missing cell"):
        evaluate("=B2", {"B2": None})


def test_trailing_operator_is_malformed():
    with pytest.raises(FormulaError):
        evaluate("=B2+", {"B2": 1})


def test_empty_formula_is_malformed():
    with pytest.raises(FormulaError):
        evaluate("=", {})


@pytest.mark.parametrize("bad", ["=(B2+B3", "=B2+B3)", "=B2)(", "=(B2+B3))"])
def test_unbalanced_parentheses_raise(bad):
    with pytest.raises(FormulaError):
        evaluate(bad, {"B2": 1, "B3": 2})


def test_empty_parentheses_then_ref_is_a_known_quirk():
    # NOTE (suspected quirk, not asserted as "correct"): an empty '()' followed
    # by a bare reference does NOT raise; the empty parens contribute nothing
    # and the lone ref is returned. We pin the actual observed behaviour so a
    # future change here is caught, without endorsing it.
    assert evaluate("=()B2", {"B2": 5}) == 5.0


def test_lowercase_reference_is_unexpected_character():
    # Refs must be uppercase; a lowercase token is not recognised.
    with pytest.raises(FormulaError):
        evaluate("=b2", {"b2": 1})


def test_unary_minus_is_not_supported():
    # The evaluator has no unary-minus rule -> malformed, not a silent 0.
    with pytest.raises(FormulaError):
        evaluate("=-B2", {"B2": 5})


def test_division_by_zero_propagates_zerodivision():
    # The evaluator does not swallow ZeroDivisionError; it surfaces it.
    with pytest.raises(ZeroDivisionError):
        evaluate("=B2/B3", {"B2": 1, "B3": 0})


@pytest.mark.parametrize("char", ["@", "#", "%", "&", "$", "!"])
def test_unexpected_characters_raise(char):
    with pytest.raises(FormulaError):
        evaluate(f"=B2{char}B3", {"B2": 1, "B3": 2})


def test_two_adjacent_numbers_are_malformed():
    with pytest.raises(FormulaError):
        evaluate("=2 3", {})


# --------------------------------------------------------------------------- #
# Properties / invariants                                                      #
# --------------------------------------------------------------------------- #
def test_addition_is_commutative_over_refs():
    a = evaluate("=B2+B3", {"B2": 7, "B3": 11})
    b = evaluate("=B3+B2", {"B2": 7, "B3": 11})
    assert a == b


def test_parenthesisation_changes_result():
    # 1 + 2 * 3 == 7, but (1 + 2) * 3 == 9 -> precedence genuinely matters.
    vals = {"B2": 1, "B3": 2, "B4": 3}
    assert evaluate("=B2+B3*B4", vals) != evaluate("=(B2+B3)*B4", vals)


def test_subtraction_round_trip_identity():
    # (a + b) - b == a
    vals = {"B2": 123.0, "B3": 45.0}
    assert evaluate("=(B2+B3)-B3", vals) == 123.0
