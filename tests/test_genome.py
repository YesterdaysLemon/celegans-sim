"""Genome paths must be deterministic, bounded, and reconstruct Params explicitly."""

from dataclasses import replace

import pytest

from worm.genome import BOUNDS, EXPORT_GENES, MUTABLE_KEYS, flatten, unflatten, validate
from worm.params import Params


def test_flatten_is_deterministic_and_numeric():
    first = flatten(Params())
    second = flatten(Params())

    assert list(first) == list(second)
    assert list(first)[:3] == ["neural.C_m", "neural.g_leak", "neural.E_leak"]
    assert all(type(value) is float for value in first.values())
    assert "neural.v_th_from_rest" not in first       # boolean switch
    assert "neural.depression_classes" not in first   # structural tuple
    assert "medium.name" not in first                 # structural string


def test_numeric_round_trip_preserves_types_and_values():
    base = Params()
    changed = replace(
        base,
        neural=replace(base.neural, gap_iters=5, noise_sigma=1.25),
        sensory=replace(base.sensory, chemo_gain=31.5),
    )

    rebuilt = unflatten(flatten(changed), base=base, require_complete=True)
    assert rebuilt == changed
    assert type(rebuilt.neural.gap_iters) is int


def test_partial_reconstruction_is_immutable_and_explicit():
    base = Params()
    rebuilt = unflatten({"sensory.food_gain": 14.0}, base=base)

    assert rebuilt is not base
    assert rebuilt.sensory is not base.sensory
    assert rebuilt.sensory.food_gain == 14.0
    assert base.sensory.food_gain == 11.0
    assert rebuilt.neural is base.neural


def test_mutable_table_matches_runtime_gene_order_and_defaults():
    expected = (
        "sen_proprio_gain", "sen_head_proprio_gain", "sen_cord_drive",
        "sen_gate_bias", "sen_gate_hysteresis", "sen_tonic_forward",
        "sen_omega_current", "sen_omega_ventral_fraction", "sen_chemo_gain",
        "sen_thermo_gain", "sen_oxygen_gain", "sen_repellent_d_gain",
        "sen_food_gain", "sen_touch_gain",
    )
    assert EXPORT_GENES == expected
    assert MUTABLE_KEYS == tuple(BOUNDS)

    genome = flatten(Params(), mutable_only=True)
    assert tuple(genome) == MUTABLE_KEYS
    assert validate(genome, mutable_only=True, require_complete=True) == genome
    for key, value in genome.items():
        low, high, scale = BOUNDS[key]
        assert low <= value <= high
        assert scale > 0.0


def test_mutable_reconstruction_rejects_fixed_or_out_of_range_values():
    with pytest.raises(KeyError, match="non-mutable"):
        unflatten({"neural.C_m": 2.0}, mutable_only=True)
    with pytest.raises(ValueError, match="outside"):
        unflatten({"sensory.omega_ventral_fraction": 1.01}, mutable_only=True)


@pytest.mark.parametrize("values, error", [
    ({"sensory.food_gain": float("nan")}, ValueError),
    ({"sensory.food_gain": float("inf")}, ValueError),
    ({"sensory.food_gain": True}, TypeError),
    ({"neural.gap_iters": 2.5}, ValueError),
    ({"not.a.path": 1.0}, KeyError),
    ({1: 1.0}, TypeError),
])
def test_validation_fails_loudly(values, error):
    with pytest.raises(error):
        validate(values)


def test_incomplete_genome_can_be_required_explicitly():
    with pytest.raises(ValueError, match="missing parameter keys"):
        validate({"sensory.food_gain": 12.0}, mutable_only=True,
                 require_complete=True)


def test_fixed_and_dead_constants_are_not_mutable_genes():
    assert "neural.C_m" not in BOUNDS
    assert "neural.E_leak" not in BOUNDS
    assert "body.length" not in BOUNDS
    assert "body.EI" not in BOUNDS
    assert "body.dt" not in BOUNDS
    assert "world.ingestion_rate" not in BOUNDS
    assert "world.food_diffusion_scale" not in BOUNDS
    assert "world.diffusion_oxygen" not in BOUNDS
