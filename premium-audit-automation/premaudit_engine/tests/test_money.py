import pytest

from ..money import MoneyError, format_cents, parse_cents


@pytest.mark.parametrize("text,cents", [
    ("4,321.09", 432109),
    ("-1,111.11", -111111),
    (".00", 0),
    ("0.01", 1),
    ("23,456.70", 2345670),
    ("123,456.78", 12345678),
])
def test_parse_known_values(text, cents):
    assert parse_cents(text) == cents


@pytest.mark.parametrize("bad", ["", "12", "1.2", "1.234", "12,34x.00", "--1.00", "1..00"])
def test_parse_refuses_malformed(bad):
    with pytest.raises(MoneyError):
        parse_cents(bad)


def test_format_negative_and_grouping():
    assert format_cents(-111111) == "-1,111.11"
    assert format_cents(98765432) == "987,654.32"
    assert format_cents(0) == "0.00"
