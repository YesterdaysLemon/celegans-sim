"""The vulval-muscle filter must not be able to lay eggs by diverging.

`NEXT.md` names the failure mode in advance: *"a parameter that makes the integrator
unstable in a profitable direction -- is where a population will end up."* The vulval
muscle was the model's only forward-Euler first-order state,

    vm += (target - vm) * (dt / vm_tau)

which amplifies by ``|1 - dt/vm_tau|`` and diverges outright for ``vm_tau < dt/2``.

Divergence here does not raise, does not produce a NaN, and does not visibly break the
animal. It **lays eggs**. ``vm`` is reset to 0 on every lay, so the instability self-limits
by firing the Schmitt trigger once per refractory period, and the animal is otherwise
completely normal -- #42 measured locomotion bit-identical to wild type with an egg count
of 1 against 0 for the control.

That is the whole reason this file exists. A blow-up that is *profitable*, *bounded*, and
*invisible in every other observable* is the one an evolutionary search finds and no
behavioural test notices. Exponential Euler removes it as a category rather than as a
tuning: ``exp(-dt/tau)`` is in [0, 1) for every positive tau, so the filter is a
contraction no matter how the parameter is set.
"""

from __future__ import annotations

import numpy as np
import pytest

from worm import dataset
from worm.egglaying import EggLaying
from worm.params import Params


@pytest.fixture(scope="module")
def conn():
    return dataset.load()


def _run(conn, vm_tau, dt, steps, activation):
    """Drive the filter directly with a constant sub-threshold input.

    Constant on purpose. The point is that the integrator itself must not manufacture
    excursions the input does not contain, so any excursion seen here comes from the
    recurrence and nothing else.
    """
    p = Params()
    ep = type(p.egglaying)(**{**p.egglaying.__dict__, "vm_tau": vm_tau})
    egl = EggLaying(conn, ep, dt)
    trace = np.empty(steps)
    for i in range(steps):
        egl.step(activation, ingested_delta=0.0, serotonin=0.0, on_food=1.0)
        trace[i] = egl.vm
    return egl, trace


@pytest.mark.parametrize("vm_tau", [0.35, 1e-3, 2.5e-4, 1e-4, 1e-6])
def test_vulval_filter_is_a_contraction_at_any_tau(conn, vm_tau):
    """`vm` stays inside [0, 1] however small the time constant is made.

    dt is 0.5 ms here, so vm_tau = 2.5e-4 is exactly dt/2 -- the point the forward-Euler
    form goes marginally unstable -- and everything below it diverges. Under exponential
    Euler all five are contractions and the smallest simply tracks the target.
    """
    p = Params()
    dt = p.neural.dt
    a = np.full(dataset.load().n, 0.5)
    egl, trace = _run(conn, vm_tau, dt, 4000, a)

    assert np.all(np.isfinite(trace)), "vm went non-finite at vm_tau = %g" % vm_tau
    # The target is a clipped drive times a gate, both in [0, 1], so the state cannot
    # legitimately leave [0, 1]. A small margin for the last-bit arithmetic, nothing more.
    assert trace.min() >= -1e-12, "vm went to %.6g at vm_tau = %g" % (trace.min(), vm_tau)
    assert trace.max() <= 1.0 + 1e-12, "vm reached %.6g at vm_tau = %g" % (trace.max(), vm_tau)


def test_the_unstable_regime_is_actually_reachable_and_actually_unstable(conn):
    """The check above is only worth having if forward Euler really does blow up here.

    Without this, `test_vulval_filter_is_a_contraction_at_any_tau` could be passing because
    the chosen taus are all benign rather than because the integrator was fixed -- and it
    would keep passing if someone put the forward-Euler line back. So: run the old
    recurrence by hand on the same numbers and require it to leave [0, 1].
    """
    p = Params()
    dt = p.neural.dt
    unstable = [t for t in (2.5e-4, 1e-4, 1e-6) if t < dt / 2.0]
    assert unstable, "no test tau is below dt/2 = %g, so nothing here is in the unstable regime" % (dt / 2.0)

    for vm_tau in unstable:
        # The exact line this file replaced, with a constant target, which is the most
        # benign input it could be given.
        target, vm, peak = 0.5, 0.0, 0.0
        for _ in range(200):
            vm += (target - vm) * (dt / vm_tau)
            peak = max(peak, abs(vm))
        assert peak > 1.0, (
            "forward Euler at vm_tau = %g stayed inside [0, 1] (peak %.6g), so this tau "
            "does not exercise the instability" % (vm_tau, peak))
        # ...and the fixed form on the identical input does not.
        decay = float(np.exp(-dt / vm_tau))
        vm, peak_fixed = 0.0, 0.0
        for _ in range(200):
            vm = target + (vm - target) * decay
            peak_fixed = max(peak_fixed, abs(vm))
        assert peak_fixed <= 1.0 + 1e-12, (
            "exponential Euler at vm_tau = %g reached %.6g" % (vm_tau, peak_fixed))


def test_divergence_cannot_buy_eggs(conn):
    """The consequence, stated as the thing a fitness function would have measured.

    #42's evidence was an egg count of 1 against 0 for the control, from an animal whose
    locomotion was bit-identical to wild type. Here the input is held constant and
    sub-threshold, so a *stable* filter can never cross `vm_threshold` and no egg is
    possible. Any egg laid is manufactured by the integrator.
    """
    p = Params()
    dt = p.neural.dt
    a = np.full(dataset.load().n, 0.5)
    for vm_tau in (0.35, 1e-4, 1e-6):
        egl, trace = _run(conn, vm_tau, dt, 4000, a)
        assert egl.laid == 0, (
            "vm_tau = %g laid %d egg(s) on a constant sub-threshold input, peak vm %.6g "
            "against a threshold of %.6g -- that is the integrator paying out, not the "
            "animal" % (vm_tau, egl.laid, trace.max(), p.egglaying.vm_threshold))
        # And the run must not be vacuous: a filter pinned at zero would also lay nothing.
        assert trace.max() > 0.0, (
            "vm never left zero at vm_tau = %g, so this proves nothing about laying" % vm_tau)


def test_resting_window_is_a_duration_not_a_step_count(conn):
    """Halving dt must not double the averaging window.

    `rest_samples` was a step count, so the window was 2 s at dt = 0.5 ms and 8 s at
    dt = 2 ms. That is the dt-dependence this project has already paid for three times.
    """
    p = Params()
    for dt in (p.neural.dt, p.neural.dt / 2.0, p.neural.dt * 4.0):
        egl = EggLaying(conn, p.egglaying, dt)
        seconds = egl._rest_steps * dt
        assert seconds == pytest.approx(p.egglaying.rest_seconds, rel=1e-9), (
            "at dt = %g the window is %.6g s, not %.6g s" % (dt, seconds, p.egglaying.rest_seconds))
        # Vacuity: a window of zero steps would satisfy any duration check that only
        # multiplied back out.
        assert egl._rest_steps > 0


# --------------------------------------------------------------------------------------
# The other shape of the same problem: an equation that is not solved, and does not say so.

def test_unreachable_rest_tension_raises_instead_of_paralysing():
    """`Muscle._balance` bisects a fixed bracket and used to return its endpoint quietly.

    Two different silent phenotypes came out of that one unchecked solve: `rest_tension`
    of 1.0 gave a paralysed straight animal -- |kappa|max 0.0, speed 0.0000 -- and 0.0 gave
    speed 0.0000 by the opposite route. Neither warned, and both read as a modelling
    result rather than as an equation nobody solved.

    Same failure class as the vulval filter above. The arithmetic completes, produces
    finite numbers, and hands back a worm-shaped object that is wrong.
    """
    import dataclasses

    from worm.engine import Simulation

    p = Params()
    for rest_tension in (1.0, 0.0):
        bad = dataclasses.replace(
            p, muscle=dataclasses.replace(p.muscle, rest_tension=rest_tension))
        with pytest.raises(ValueError, match="unreachable"):
            Simulation(bad, seed=1)

    # And the guard has to leave the shipped model alone, or it is not a guard, it is a
    # break. This is the assertion that stops the test above being satisfiable by a
    # `_balance` that simply always raises.
    Simulation(p, seed=1)
