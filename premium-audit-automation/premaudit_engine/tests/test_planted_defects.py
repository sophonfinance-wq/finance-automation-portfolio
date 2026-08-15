import pytest

from ..generate import generate_report
from ..model import ParseRefusal
from ..parse import parse_report


@pytest.mark.parametrize("defect", ["printed_total_off", "missing_total_line",
                                    "malformed_amount"])
@pytest.mark.parametrize("seed", [2, 11, 23])
def test_each_defect_refuses(defect, seed):
    gen = generate_report(seed, defect=defect)
    with pytest.raises(ParseRefusal):
        parse_report(gen.text, gen.company)


def test_refusal_names_the_job():
    gen = generate_report(5, defect="printed_total_off")
    with pytest.raises(ParseRefusal) as exc:
        parse_report(gen.text, gen.company)
    assert exc.value.failures
    assert all(f.job for f in exc.value.failures)


def test_off_by_one_cent_is_not_tolerated():
    gen = generate_report(17, defect="printed_total_off")
    with pytest.raises(ParseRefusal) as exc:
        parse_report(gen.text, gen.company)
    deltas = [f.delta_cents for f in exc.value.failures if f.delta_cents is not None]
    assert deltas and all(abs(d) == 1 for d in deltas)
