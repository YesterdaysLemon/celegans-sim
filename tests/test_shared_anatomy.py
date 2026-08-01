"""Large anatomical matrices are shared, immutable, and copy-on-ablation."""

from dataclasses import replace
import os
import pickle

import numpy as np
import pytest

from worm import dataset
from worm.engine import Simulation
from worm.nervous import NervousSystem
from worm.params import Params
from worm.world import World


NUMERIC_CONNECTOME_FIELDS = (
    "soma_pos", "inhibitory", "gap", "syn", "syn_reversal",
    "muscle_side", "muscle_lr", "muscle_pos", "nmj", "nmj_reversal",
)


def _assert_immutable(array):
    assert not array.flags.writeable
    with pytest.raises(ValueError):
        array.flat[0] = array.flat[0]
    with pytest.raises(ValueError):
        array.setflags(write=True)
    # Bypass the subclass method to prove the immutable backing, rather than a Python
    # override alone, is what prevents re-enabling writes.
    with pytest.raises(ValueError):
        np.ndarray.setflags(array, write=True)
    with pytest.raises(ValueError):
        array.flags.writeable = True


def test_connectome_load_cache_canonicalises_arguments():
    dataset.clear_cache()
    relative = os.path.relpath(dataset.DATA)
    first = dataset.load()
    second = dataset.load(relative, e_exc=np.float64(0), e_inh=np.float64(-48))

    assert first is second
    assert dataset.load.cache_info().misses == 1
    assert dataset.load.cache_info().hits == 1


def test_shared_connectome_is_deeply_read_only_where_anatomy_is_numeric():
    conn = dataset.load()
    for name in NUMERIC_CONNECTOME_FIELDS:
        _assert_immutable(getattr(conn, name))
    with pytest.raises(TypeError):
        conn.index["made-up"] = 0
    with pytest.raises(TypeError):
        conn.meta["sources"]["made-up"] = {}


def test_immutable_connectome_remains_pickle_compatible():
    conn = dataset.load()
    restored, same, reversal, same_reversal = pickle.loads(pickle.dumps(
        (conn, conn, conn.syn_reversal, conn.nmj_reversal)))

    assert restored is same
    assert restored.names == conn.names
    assert restored.index == conn.index
    assert restored.syn_reversal is restored.nmj_reversal
    assert reversal is same_reversal is restored.syn_reversal
    for name in NUMERIC_CONNECTOME_FIELDS:
        _assert_immutable(getattr(restored, name))
    with pytest.raises(TypeError):
        restored.index["made-up"] = 0


def test_neural_pickle_preserves_shared_immutable_identity_and_ablation_copies():
    root = Params()
    conn = dataset.load(e_exc=root.neural.E_exc, e_inh=root.neural.E_inh)
    first = NervousSystem(conn, root.neural, np.random.default_rng(1))
    second = NervousSystem(conn, root.neural, np.random.default_rng(2))

    restored_first, restored_second = pickle.loads(pickle.dumps((first, second)))
    assert restored_first.conn is restored_second.conn
    assert restored_first.E_pre is restored_first.conn.syn_reversal
    for name in ("G_gap", "G_syn", "gap_total", "E_pre", "E_syn", "GE_syn"):
        left = getattr(restored_first, name)
        right = getattr(restored_second, name)
        assert left is right, name
        _assert_immutable(left)

    shared_gap = restored_second.G_gap
    shared_syn = restored_second.G_syn
    idx = conn.select("AVBL")
    restored_first.set_ablated(idx)
    assert restored_first.G_gap is not shared_gap
    assert restored_first.G_syn is not shared_syn
    assert restored_first.G_gap.flags.writeable
    assert restored_first.G_syn.flags.writeable
    assert restored_second.G_gap is shared_gap
    assert restored_second.G_syn is shared_syn


def test_simulation_pickle_compatibility_and_copy_on_ablation():
    params = Params()
    world = World(params.world, np.random.default_rng(0))
    restored = pickle.loads(pickle.dumps(Simulation(params, seed=3, world=world)))

    assert restored.conn.n == 302
    for name in NUMERIC_CONNECTOME_FIELDS:
        _assert_immutable(getattr(restored.conn, name))
    shared_gap = restored.nervous.G_gap
    shared_nmj = restored.muscles.G
    restored.set_ablated(["AVBL"])
    assert restored.nervous.G_gap is not shared_gap
    assert restored.muscles.G is not shared_nmj
    assert restored.nervous.G_gap.flags.writeable
    assert restored.muscles.G.flags.writeable


def test_neural_anatomy_is_shared_across_per_animal_parameters():
    root = Params()
    conn = dataset.load(e_exc=root.neural.E_exc, e_inh=root.neural.E_inh)
    changed = replace(root.neural, noise_sigma=root.neural.noise_sigma + 0.1)
    first = NervousSystem(conn, root.neural, np.random.default_rng(1))
    second = NervousSystem(conn, changed, np.random.default_rng(2))

    for name in ("G_gap", "G_syn", "gap_total", "E_pre", "E_syn", "GE_syn"):
        a = getattr(first, name)
        b = getattr(second, name)
        assert a is b, name
        assert not a.flags.writeable


def test_ablation_takes_private_copies_without_changing_another_worm():
    p = Params().neural
    conn = dataset.load(e_exc=p.E_exc, e_inh=p.E_inh)
    first = NervousSystem(conn, p, np.random.default_rng(1))
    second = NervousSystem(conn, p, np.random.default_rng(2))
    shared_gap = second.G_gap
    shared_syn = second.G_syn
    idx = conn.select("AVBL")

    first.set_ablated(idx)

    assert first.G_gap is not shared_gap
    assert first.G_syn is not shared_syn
    assert first.G_gap.flags.writeable
    assert first.G_syn.flags.writeable
    assert np.all(first.G_gap[idx, :] == 0.0)
    assert np.all(first.G_syn[:, idx] == 0.0)
    assert second.G_gap is shared_gap
    assert second.G_syn is shared_syn
    assert np.any(second.G_gap[idx, :] != 0.0)
    assert np.any(second.G_syn[:, idx] != 0.0)


def test_conductance_changes_get_distinct_derived_anatomy():
    p = Params().neural
    conn = dataset.load(e_exc=p.E_exc, e_inh=p.E_inh)
    first = NervousSystem(conn, p, np.random.default_rng(1))
    changed = NervousSystem(conn, replace(p, g_syn=p.g_syn * 2.0),
                            np.random.default_rng(2))

    assert first.G_syn is not changed.G_syn
    assert np.array_equal(changed.G_syn, first.G_syn * 2.0)
