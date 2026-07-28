"""Can the body carry the rhythm, so that the frequency stops being an accident?

`tools/head_mode.py` established that the head loop has several coexisting limit cycles
and that the integration step is what selects between them. The frequency clusters near
0.15, 0.70 and 1.0-1.4 Hz and flips between clusters on changes to dt too small to move
any physical quantity. A model whose headline kinematic number is chosen by its own
timestep does not have a well-defined gait.

The way out has been visible in this project's notes since day two and never taken. From
NEXT.md: "If the body reflex gets strong enough to dominate, that attractor should become
the robust one and four of the table's five rows fix themselves at once." The pieces are
already here -- each B-type motor neuron is a Morris-Lecar unit whose regenerative
conductance is `ca_ratio`, currently sized to sit *at* its Hopf bifurcation rather than
past it. A chain of such units coupled by proprioception sets its frequency from segmental
dynamics and coupling delay, which is a physical selector, rather than from one loop's
phase-crossover, which is not.

So the axis is: turn the segmental oscillators up, turn the head down, and ask whether the
frequency stops depending on the step size.

The headline column is **drift**, the difference in frequency between dt = 0.5 ms and
dt = 0.125 ms for the same parameters. Everything else in the table is there to make sure
a stable answer is not stable because the animal has stopped moving:

  * ca_ratio past ~0.26 was previously reported to make each segment free-run, with the
    tail reaching four times the head's amplitude and the wave travelling *backwards*.
    That was measured with the head reflex at full strength, fighting them. The question
    here is whether the same conductance behaves differently once the head is not
    competing for control of the wave, so TWI is reported alongside.
  * head_proprio_gain at 0 is included as a control and is expected to fail: dorsal and
    ventral members of a class have identical dynamics and are gap-coupled, so with
    nothing dorsoventrally antisymmetric driving them they phase-lock to each other and
    the animal contracts both sides at once. If that row shows a healthy gait, something
    else is supplying the antisymmetry and it is worth knowing what.

What it measured, and it does not work in this form.

   ca_ratio  head_gain |  freq @0.5   freq @0.125    drift  |   TWI     k_rms   speed
     0.20        150    |    1.250       1.633         31%  |  +0.714    2.70    0.3398  <- shipped
     0.20         60    |    1.083       1.000          8%  |  +0.640    1.61    0.1413
     0.20         25    |    0.567       0.333         41%  |  +0.448    1.08    0.0350
     0.30        150    |    1.250       0.167         87%  |  +0.147    6.10    0.0225
     0.30         25    |    0.117       0.150         29%  |  +0.041    6.16    0.0244
     0.40         60    |    0.100       0.150         50%  |  +0.087    6.52    0.0052
     0.40          0    |    0.100       0.150         50%  |  +0.086    6.36    0.0229

Turning the segmental oscillators up does raise curvature -- k_rms goes from 2.7 to about
6.3, against a measured 4.3, having been too *low* at the shipped setting -- and it
destroys the wave doing it. TWI falls from +0.71 to +0.15 and then to zero, and net speed
with it, to around 0.02 mm/s. The units free-run and lock to each other rather than
organising into a travelling wave, and weakening the head does not rescue that: the
ca_ratio 0.40 rows are equally dead at head gains of 150, 60, 25 and 0. So proprioceptive
coupling as currently built cannot impose a phase gradient on segments that have their own
rhythm; it can only carry phase to segments that do not. That is the same conclusion the
earlier ca_ratio sweep reached from the other direction, and it now holds with the head
out of the way, which was the obvious objection to it.

The one real gain is narrower than hoped and worth keeping: **head_proprio_gain 60 instead
of 150 cuts the step-size drift from 31% to 8%** while holding TWI at +0.64. That is a
more trustworthy gait, though not a more accurate one -- it is slower than the animal
(0.14 against 0.219 mm/s) where the shipped setting is faster (0.34), and its curvature is
further from the measured value, so it has not been adopted. It is recorded because the
drift column is the honest one and 8% is the best number in it.

The body-as-oscillator route therefore needs more than a gain: something that makes the
coupling impose a phase *lag* between neighbours, rather than a shared conductance that
encourages them to lock in phase. An explicit propagation delay in the proprioceptive
field, or asymmetric coupling, is the next thing to try, and it is a design change rather
than a parameter.

!! The step-size numbers in this file are withdrawn. !!

Every "drift between dt = 0.5 and 0.125 ms" measured here was taken while `BodyParams.dt`
was not synchronised with `NeuralParams.dt`, so refining the neural step left the body
advancing 0.5 ms per call and running up to four times fast relative to its own nervous
system. The drift measured the desynchronisation, not numerical error. With the two
synchronised the frequency holds 0.44-0.45 Hz across a sixteen-fold range of step size.
See NEXT.md, day ten. The parameter results below stand -- they were taken at a single
step size, where the coupling was correct -- but nothing here about convergence does.

Run:  PYTHONPATH=. .venv/bin/python tools/body_oscillator.py
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import travelling_index
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 10.0, 30.0
SEEDS = (0, 3)
STEPS_MS = (0.5, 0.125)
CA_RATIO = (0.20, 0.30, 0.40)
HEAD_GAIN = (150.0, 60.0, 25.0, 0.0)


def _job(job):
    dt_ms, ca, head_gain, seed = job
    p = Params()
    p = dataclasses.replace(
        p,
        neural=dataclasses.replace(p.neural, dt=dt_ms * 1e-3, ca_ratio=ca),
        sensory=dataclasses.replace(p.sensory, head_proprio_gain=head_gain))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()

    start = sim.body.centroid().copy()
    t0 = sim.t
    ks = []
    every = max(1, int(round(0.005 / dt)))         # fixed 200 Hz sampling at every dt
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % every == 0:
            ks.append(sim.body.curvature().copy())
    K = np.array(ks)
    speed = float(np.linalg.norm(sim.body.centroid() - start)) / (sim.t - t0)

    mid = K[:, K.shape[1] // 2]
    mid = mid - mid.mean()
    P = np.abs(np.fft.rfft(mid * np.hanning(len(mid)))) ** 2
    fr = np.fft.rfftfreq(len(mid), 0.005)
    return dict(dt_ms=dt_ms, ca=ca, head_gain=head_gain, seed=seed,
                freq=float(fr[1 + np.argmax(P[1:])]),
                fast_frac=float(P[fr > 1.5].sum() / max(P[1:].sum(), 1e-30)),
                twi=travelling_index(K), speed=speed,
                k_rms=float(np.sqrt((K ** 2).mean())))


def main():
    jobs = [(d, c, h, s)
            for d, c, h in itertools.product(STEPS_MS, CA_RATIO, HEAD_GAIN)
            for s in SEEDS]
    print("BODY OSCILLATOR -- %d trials x %.0f s" % (len(jobs), WARMUP + MEASURE))
    print("  looking for a cell where the frequency does not move with the step\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["ca"], r["head_gain"], r["dt_ms"]), []).append(r)
    f = lambda g, k: float(np.mean([x[k] for x in g]))            # noqa: E731

    print("  ca_ratio  head_gain |  freq @0.5   freq @0.125    drift  |"
          "   TWI     k_rms   speed mm/s")
    best = []
    for ca, hg in itertools.product(CA_RATIO, HEAD_GAIN):
        a, b = agg.get((ca, hg, 0.5)), agg.get((ca, hg, 0.125))
        if not a or not b:
            continue
        fa, fb = f(a, "freq"), f(b, "freq")
        drift = abs(fb - fa) / max(fa, 1e-9)
        mark = "   <- shipped" if (ca, hg) == (0.20, 150.0) else ""
        print("    %.2f      %5.0f    |   %6.3f      %6.3f      %5.0f%%  |"
              "  %+.3f   %5.2f    %.4f%s"
              % (ca, hg, fa, fb, 100 * drift, f(b, "twi"), f(b, "k_rms"),
                 f(b, "speed"), mark))
        best.append((drift, ca, hg, fa, fb))

    print()
    print("  the shipped configuration drifts by about a third. A cell that drifts under")
    print("  ~10%% while holding TWI above +0.5 is a gait set by the body rather than by")
    print("  the integrator, which is the thing worth having even if its frequency still")
    print("  needs work. Real animal: 0.30-0.50 Hz, curvature rms 4.3 /mm.")
    if best:
        best.sort()
        print()
        print("  least drift: ca_ratio %.2f, head_gain %.0f  (%.3f -> %.3f Hz, %.0f%%)"
              % (best[0][1], best[0][2], best[0][3], best[0][4], 100 * best[0][0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
