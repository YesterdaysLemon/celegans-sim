"""The dataset must match C. elegans anatomy. A wrong connectome produces a worm that
looks plausible and is wrong, which is the failure mode hardest to notice."""

import numpy as np
import pytest

from worm import dataset


@pytest.fixture(scope="module")
def conn():
    return dataset.load()


def test_canonical_neuron_count(conn):
    assert conn.n == 302
    assert len(set(conn.names)) == 302


def test_canonical_class_count(conn):
    # C. elegans has 118 anatomical neuron classes.
    assert len(set(conn.cls)) == 118


def test_body_wall_muscles(conn):
    assert conn.n_muscles == 95
    quads = {}
    for name in conn.muscle_names:
        quads.setdefault(name[:3], []).append(name)
    assert {k: len(v) for k, v in quads.items()} == {
        "MDL": 24, "MDR": 24, "MVL": 23, "MVR": 24}


def test_gabaergic_roster(conn):
    """26 GABAergic neurons (McIntire et al. 1993), of which AVL and DVB are excitatory."""
    inhibitory = {conn.names[i] for i in range(conn.n) if conn.inhibitory[i]}
    expected = ({"DD%02d" % i for i in range(1, 7)}
                | {"VD%02d" % i for i in range(1, 14)}
                | {"RIS", "RMED", "RMEV", "RMEL", "RMER"})
    assert inhibitory == expected
    assert len(inhibitory) == 24
    for n in ("AVL", "DVB"):
        assert not conn.inhibitory[conn.index[n]]


def test_gap_junctions_are_symmetric(conn):
    assert np.array_equal(conn.gap, conn.gap.T)
    assert np.all(np.diag(conn.gap) == 0)


def test_no_self_synapses(conn):
    assert np.all(np.diag(conn.syn) == 0)


def test_every_muscle_is_innervated(conn):
    assert np.all(conn.nmj.sum(axis=1) > 0)


def test_motor_neurons_target_the_correct_side(conn):
    """The dorsal/ventral logic of the motor circuit, straight out of the anatomy.

    DB and DA excite dorsal muscle; VB and VA excite ventral. The D-type inhibitors are
    crossed: DD inhibits dorsal, VD inhibits ventral. That crossing is what turns a
    one-sided excitation into an antagonistic pair.
    """
    dorsal = conn.muscle_side > 0
    for cls, side in (("DB", "D"), ("DA", "D"), ("AS", "D"), ("DD", "D"),
                      ("VB", "V"), ("VA", "V"), ("VD", "V")):
        idx = conn.group(cls)
        to_d = conn.nmj[np.ix_(np.where(dorsal)[0], idx)].sum()
        to_v = conn.nmj[np.ix_(np.where(~dorsal)[0], idx)].sum()
        if side == "D":
            assert to_d > 0 and to_v == 0, "%s should be dorsal-only" % cls
        else:
            assert to_v > 0 and to_d == 0, "%s should be ventral-only" % cls
    assert conn.inhibitory[conn.group("DD")].all()
    assert conn.inhibitory[conn.group("VD")].all()


def test_command_interneurons_gap_junction_to_motor_neurons(conn):
    """AVB drives forward locomotion through B-type, AVA backward through A-type."""
    def gap(a, b):
        return conn.gap[np.ix_(conn.group(b), conn.group(a))].sum()
    assert gap("AVB", "DB") > 0 and gap("AVB", "VB") > 0
    assert gap("AVA", "DA") > 0 and gap("AVA", "VA") > 0


def test_soma_positions_ordered_and_bounded(conn):
    assert np.all(np.diff(conn.soma_pos) >= 0)
    assert conn.soma_pos.min() >= 0.0 and conn.soma_pos.max() <= 1.0


def test_touch_and_chemosensory_neurons_present(conn):
    for name in ("ALML", "ALMR", "AVM", "PLML", "PLMR",
                 "ASEL", "ASER", "AWCL", "AWCR", "AFDL", "ASHL", "URXL"):
        assert name in conn.index
    assert conn.modality[conn.index["AFDL"]] == "thermosensory"
    assert "mechanosensory" in conn.modality[conn.index["ALML"]]
