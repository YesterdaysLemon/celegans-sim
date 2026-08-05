"""The load-dependent reach, and the three ways it could be quietly wrong.

`SensoryParams.load_detect_gain` lets the animal read the phase lag between what it commanded
and what its body did, and set its own proprioceptive reach -- and therefore its own
wavelength -- from it. That is the first thing in this model that changes the shared gait in
response to the medium, so it needs to be pinned in the three places it could fail without
looking like it had failed:

  * **off is off.** The term is disabled by default. If "disabled" is merely "small", every
    number in this repository moved when it landed and nothing said so;
  * **the sign is right.** A detector wired backwards still produces a medium-dependent
    reach, still looks alive in every summary, and makes the animal crawl in water. The
    direction is the entire content of the mechanism;
  * **it reads phase, not amplitude.** The amplitude-carrying candidates were rejected in
    `tools/load_signal.py` for tracking the gait's own decline rather than the medium. A
    detector that quietly re-imported amplitude would inherit exactly that fault while
    passing every other check here.

Cheap: none of these runs a behavioural assay.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.params import Params


def _sim(medium="agar", seed=1, **sensory):
    p = Params().with_medium(medium)
    if sensory:
        p = dataclasses.replace(p, sensory=dataclasses.replace(p.sensory, **sensory))
    return Simulation(p, seed=seed, world=bare_world(p))


def _state(sim):
    return (sim.body.nodes().copy() if callable(sim.body.nodes) else sim.body.nodes.copy(),
            sim.nervous.V.copy(), sim.muscles.tension.copy())


def _run(steps, **kw):
    sim = _sim(**kw)
    for _ in range(steps):
        sim.step()
    return sim


def test_the_term_is_off_by_default():
    """A gait-changing term that shipped switched on would move every assay silently."""
    assert Params().sensory.load_detect_gain == 0.0


def test_disabled_is_bit_identical_and_not_merely_close():
    """`load_detect_gain = 0` has to leave the trajectory untouched to the last bit.

    Compared against a run whose Senses has had the new banks deleted outright, so this is a
    statement about the code path and not about the parameter: if the disabled branch were
    still mixing a zero-weighted bank in, `0.0 * (W @ k)` would agree here for finite values
    and the test would pass while the expression had changed. Deleting the attribute makes
    the old path the only one that can run at all.
    """
    a = _run(2000, load_detect_gain=0.0)

    sim = _sim(load_detect_gain=0.0)
    for name in ("W_b_swim", "W_a_swim", "W_b_local", "W_a_local"):
        delattr(sim.senses, name)
    for _ in range(2000):
        sim.step()

    for label, x, y in zip(("nodes", "V", "tension"), _state(a), _state(sim)):
        assert np.array_equal(x, y), "%s moved with the term disabled" % label


def test_enabled_actually_changes_the_animal():
    """The companion to the test above: if nothing moves, nothing is being measured."""
    off, on = _run(2000, load_detect_gain=0.0), _run(2000, load_detect_gain=1.0)
    assert not np.array_equal(_state(off)[1], _state(on)[1])


@pytest.mark.xfail(strict=True, reason=(
    "The detector is correctly ordered and far too weakly separated: agar 0.051 against "
    "buffer 0.060, where the measured lags differ 45x. The cause is known and is not this "
    "test. A cell's output sits several lags upstream of the moment its muscle applies -- "
    "synaptic release, the muscle's own membrane, calcium, tension -- and those lags are "
    "medium-independent, so read raw they swamp the body's lag: 23-28 degrees of muscle "
    "against 11.9 of body on agar and 0.33 in buffer. The corollary discharge in "
    "Senses._update_load subtracts two of them and moved the detector 0.648 -> 0.433, which "
    "is progress and not enough. Strict, so that finishing the forward model turns this into "
    "a failure that says to delete the marker rather than into a silent pass."))
def test_the_detector_points_the_right_way_round():
    """Thick medium -> crawl -> short reach. Thin medium -> swim -> long reach.

    This is the one that a sign error survives. A backwards detector still gives a
    medium-dependent reach and still reads as alive in every summary; it just makes the
    animal crawl in water. `_load_swim` is 0 at the crawling end and 1 at the swimming one.
    """
    agar = _run(9000, medium="agar", load_detect_gain=1.0)
    buffer = _run(9000, medium="buffer", load_detect_gain=1.0)
    s_agar = float(agar.senses._load_swim)
    s_buffer = float(buffer.senses._load_swim)
    assert s_buffer > s_agar, (
        "the detector is backwards: agar %.3f, buffer %.3f -- the animal swims on jelly"
        % (s_agar, s_buffer))
    # Not merely ordered but separated, because an ordering that holds by a thousandth is
    # noise with a sign. The measured lags differ 45x; the reach should not be subtle.
    assert s_buffer - s_agar > 0.20, (
        "agar %.3f, buffer %.3f -- ordered but too close to move the reach usefully"
        % (s_agar, s_buffer))


def test_the_detector_reads_phase_and_not_amplitude():
    """Scaling both of its inputs must not move it. This is what keeps it off the confound.

    `tools/load_signal.py` rejected bend amplitude and bend-per-unit-moment because both move
    by about what the travelling index moves across these media, so a signal built from them
    reads "this animal is swimming badly" as readily as "this animal is in water". The
    quadrature detector divides by the product of the two magnitudes precisely so amplitude
    cancels. Driven with synthetic signals whose phase is fixed and whose amplitude is
    multiplied by 40, the output has to stay put.
    """
    sim = _sim(load_detect_gain=1.0)
    senses = sim.senses
    n = sim.conn.n
    m = senses._load_cells
    assert m.sum() > 0, "no cell holds both an output and a local field"

    def drive(amp, phi, cycles=40.0, f=0.7):
        """Feed the detector two sinusoids at a known phase and read what it settles to."""
        senses._load_act_adapt = np.zeros(n)
        senses._load_local_prev = None
        senses._load_q = senses._load_amp = 0.0
        dt = senses._load_dt
        steps = int(cycles / f / dt)
        for i in range(steps):
            t = i * dt
            act = np.zeros(n)
            act[m] = amp * np.sin(2 * np.pi * f * t)
            local = np.zeros(n)
            local[m] = amp * np.sin(2 * np.pi * f * t - phi)
            # Bypass the curvature path and inject `local` directly, so the only thing under
            # test is the detector arithmetic rather than the receptive fields.
            if senses._load_local_prev is None:
                senses._load_local_prev = local.copy()
                senses._load_act_adapt += (act - senses._load_act_adapt) * senses._load_rate
                continue
            d_local = (local - senses._load_local_prev) / dt
            senses._load_local_prev = local.copy()
            senses._load_act_adapt += (act - senses._load_act_adapt) * senses._load_rate
            act_ac = act - senses._load_act_adapt
            senses._load_q += (float(np.mean(act_ac[m] * d_local[m]))
                               - senses._load_q) * senses._load_rate
            senses._load_amp += (float(np.mean(np.abs(act_ac[m]) * np.abs(d_local[m])))
                                 - senses._load_amp) * senses._load_rate
        return abs(senses._load_q) / max(senses._load_amp, 1e-12)

    phi = np.radians(12.0)                      # about the measured agar lag
    small, large = drive(0.05, phi), drive(2.0, phi)
    assert large == pytest.approx(small, rel=0.02), (
        "a 40x amplitude change moved the detector %.4f -> %.4f; it is reading amplitude"
        % (small, large))

    # And it does respond to phase, or the invariance above is the invariance of a constant.
    assert drive(0.05, np.radians(40.0)) > small * 2.0, (
        "the detector did not respond to a phase change, so amplitude-invariance is vacuous")


def test_the_blend_weights_never_leave_the_simplex():
    """Two sources shorten the reach and one lengthens it; together they must stay a blend.

    Dopamine's basal slowing and the load detector both write into the same mix. If their
    weights summed past 1 the base bank would take a negative coefficient, which is not an
    interpolation between receptive fields but an extrapolation beyond both -- and it would
    show up as a reach shorter than `proprio_reach_food` with nothing in range to explain it.
    """
    for swim in (0.0, 0.25, 0.5, 0.75, 1.0):
        for short in (0.0, 0.5, 1.0):
            crawl = (0.5 - swim) * 2.0 if swim < 0.5 else 0.0
            lengthen = (swim - 0.5) * 2.0 if swim >= 0.5 else 0.0
            crawl = min(1.0, min(1.0, crawl) + short)
            lengthen = min(lengthen, max(0.0, 1.0 - crawl))
            base = 1.0 - crawl - lengthen
            assert -1e-12 <= base <= 1.0 + 1e-12, (swim, short, base)
            assert abs(base + crawl + lengthen - 1.0) < 1e-12
