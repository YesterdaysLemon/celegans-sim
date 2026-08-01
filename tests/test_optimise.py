"""Fail-closed scoring for evolutionary candidates."""

from tools import optimise
from worm.errors import InvalidGenome


def _healthy_result():
    return {
        "speed": 0.219,
        "net_ratio": 0.60,
        "freq": 0.40,
        "wavelength": 0.65,
        "kappa_max": 9.8,
        "kappa_rms": 4.3,
        "dv_corr": -0.5,
        "backwards": False,
    }


def test_one_lethal_seed_invalidates_the_whole_candidate():
    cost, metrics = optimise.score([
        _healthy_result(),
        {"failed": "diverged", "lethal": "DivergentSimulation()", "backwards": True},
    ])

    assert cost == 1e6
    assert metrics == {"lethal": True, "n_lethal": 1, "n_seeds": 0}


def test_nonlethal_seed_failure_keeps_the_existing_partial_scoring_behavior():
    cost, metrics = optimise.score([
        _healthy_result(),
        {"failed": "transient infrastructure error", "backwards": True},
    ])

    assert cost < 1e6
    assert metrics["n_seeds"] == 1
    assert "lethal" not in metrics


def test_evaluate_one_marks_invalid_genomes_as_lethal(monkeypatch):
    def invalid(_values):
        raise InvalidGenome("bad candidate")

    monkeypatch.setattr(optimise, "build", invalid)
    result = optimise.evaluate_one(({}, 0))

    assert "InvalidGenome" in result["lethal"]
    assert result["failed"] == result["lethal"]


def test_evaluate_one_preserves_nonlethal_exception_semantics(monkeypatch):
    def broken(_values):
        raise RuntimeError("worker problem")

    monkeypatch.setattr(optimise, "build", broken)
    result = optimise.evaluate_one(({}, 0))

    assert "RuntimeError" in result["failed"]
    assert "lethal" not in result
