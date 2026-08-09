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
    from tools.export_model import GENES

    expected = (
        "sen_proprio_gain", "sen_head_proprio_gain", "sen_cord_drive",
        "sen_gate_bias", "sen_gate_hysteresis", "sen_tonic_forward",
        "sen_omega_current", "sen_omega_ventral_fraction", "mod_serotonin_mod1",
        "sen_chemo_gain", "sen_thermo_gain", "sen_oxygen_gain",
        "sen_repellent_d_gain", "sen_food_gain", "sen_touch_gain",
    )
    assert EXPORT_GENES == expected
    assert EXPORT_GENES == GENES
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
    # world.diffusion_oxygen used to be asserted here as a dead parameter that must not be
    # mutable. #48 deleted it instead: the oxygen field is solved from the standing
    # bacterial mass, not integrated, so there is nothing for a transport coefficient to
    # multiply. Asserting it is absent from BOUNDS would now pass for a name that does not
    # exist -- a check covering less than its comment claims, which is this repository's
    # most repeated bug. Assert the deletion itself instead.
    assert "world.diffusion_oxygen" not in flatten(Params())
    assert not hasattr(Params().world, "diffusion_oxygen")


# --------------------------------------------------------------- optimise.py vs the genome
#
# Two lists search the same model and only one of them was pinned.
#
# `worm/genome.py::BOUNDS` is the evolutionary allow-list, 15 dotted keys, pinned above
# against `tools/export_model.py::GENES`. `tools/optimise.py::SPACE` is the parameter search,
# 7 leaf names, pinned against nothing. They overlap in three, and the owner's decision on
# #111 was to keep both and pin the relationship rather than retire either -- `SPACE` covers
# four parameters `BOUNDS` deliberately excludes, so it is not redundant with `wasm/evolve.mjs`.
#
# WHAT IS ASSERTED, AND WHAT DELIBERATELY IS NOT.
#
# Not the ranges. `worm/genome.py`'s own comment says the three shared fields "retain that
# tool's ranges", and measured, none of the three does:
#
#     proprio_gain        SPACE (20.0, 300.0)   BOUNDS (8.0,  80.0)
#     head_proprio_gain   SPACE ( 0.0, 700.0)   BOUNDS (40.0, 280.0)
#     tonic_forward       SPACE (20.0, 160.0)   BOUNDS (10.0,  35.0)
#
# That comment is wrong and is recorded here rather than corrected, because #111 keeps the
# change surface under `worm/` at exactly zero and a docstring fix there would spend that
# property on prose. Asserting equality would pin a claim the repository does not honour;
# asserting the current numbers would freeze an envelope somebody may legitimately retune.
#
# What is asserted is the part that can rot silently and would matter:
#
#   * every `SPACE` name resolves against a real `Params()` -- the `hasattr` failure that
#     lost `sen_nose_touch_gain` from the exporter (#31), one layer along;
#   * the partition stays put -- which three are shared, which four are search-only. A
#     parameter quietly becoming evolvable, or quietly ceasing to be, is a change to what
#     selection can reach and should not happen by accident;
#   * the shared envelopes still OVERLAP. Disjoint ranges would mean the optimiser and the
#     evolutionary driver were exploring different regions of the same parameter while both
#     claiming to search it, which is the failure that has no symptom.
SHARED = ("proprio_gain", "head_proprio_gain", "tonic_forward")
SEARCH_ONLY = ("proprio_reach", "peak_moment", "head_tau", "head_reach")


def _space_and_bounds():
    from tools.optimise import SPACE
    return SPACE, {k.split(".")[-1]: (k, v) for k, v in BOUNDS.items()}


def test_every_optimise_parameter_resolves_against_params():
    space, _ = _space_and_bounds()
    flat = flatten(Params())
    for name in space:
        matches = [k for k in flat if k.split(".")[-1] == name]
        assert len(matches) == 1, (
            "tools/optimise.py::SPACE searches %r, which resolves to %d parameters on "
            "Params() (expected exactly 1). A name that resolves to nothing is a search "
            "dimension that silently does nothing." % (name, len(matches)))


def test_the_optimise_genome_partition_has_not_drifted():
    space, leaf = _space_and_bounds()
    shared = tuple(sorted(n for n in space if n in leaf))
    search_only = tuple(sorted(n for n in space if n not in leaf))
    assert shared == tuple(sorted(SHARED)), (
        "the set of parameters searched by BOTH tools/optimise.py and evolution changed: "
        "%s, was %s. That changes what selection can reach." % (shared, tuple(sorted(SHARED))))
    assert search_only == tuple(sorted(SEARCH_ONLY)), (
        "the set of parameters tools/optimise.py searches that evolution may NOT touch "
        "changed: %s, was %s." % (search_only, tuple(sorted(SEARCH_ONLY))))


def test_shared_search_envelopes_overlap():
    space, leaf = _space_and_bounds()
    for name in SHARED:
        lo, hi = space[name]
        dotted, bound = leaf[name]
        assert lo < bound.high and bound.low < hi, (
            "%s: tools/optimise.py searches [%g, %g] and %s allows [%g, %g] -- disjoint. "
            "Two searches over one parameter that cannot reach each other's region is a "
            "silent disagreement about what the parameter is for."
            % (name, lo, hi, dotted, bound.low, bound.high))
