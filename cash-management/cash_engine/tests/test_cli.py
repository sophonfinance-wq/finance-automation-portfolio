"""The demo CLI runs all five controls clean and never authorizes posting."""

from cash_engine.cli import _run_all, main


def test_demo_runs_all_five_controls_clean():
    results = _run_all()
    assert len(results) == 5
    for _name, result in results:
        assert result.mechanical_clean
        assert result.verdict == "READY FOR HUMAN REVIEW"
        assert result.validation_only
        assert not result.posting_authorized


def test_demo_exit_code_is_zero(capsys):
    code = main(["--demo"])
    assert code == 0
    out = capsys.readouterr().out
    assert "nothing posted" in out.lower()
