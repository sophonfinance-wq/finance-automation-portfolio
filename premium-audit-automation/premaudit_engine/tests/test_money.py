import pytest

from ..money import MoneyError, format_cents, parse_cents


@pytest.mark.parametrize("text,cents", [
    ("1,324.20", 132420),
    ("-2,580.00", -258000),
    (".00", 0),
    ("0.01", 1),
    ("12,906.04", 1290604),
    ("547,539.01", 54753901),
])
def test_parse_known_values(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.parametrize("bad", ["", "12", "1.2", "1.234", "12,34x.00", "--1.00", "1..00"])
def test_parse_refuses_malformed(bad):
    with pytest.raises(MoneyError):
        parse_cents(bad)


def test_format_negative_and_grouping():
    assert format_cents(-258000) == "-2,580.00"
    assert format_cents(92404088) == "924,040.88"
    assert format_cents(0) == "0.00"
