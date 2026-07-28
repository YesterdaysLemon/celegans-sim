"""Which of the head loop's two limit cycles the animal lands in, and what decides it.

`NeuralParams` records that the head reflex loop has two stable limit cycles: a slow one
near 0.3 Hz, which is the real crawling gait, and a fast one near 2.2 Hz set by the loop's
own phase-crossover frequency. `head_tau` -- a first-order lag standing for the stretch
receptor's own kinetics -- exists to cut the loop gain at the fast frequency and leave the
slow attractor. That was calibrated at dt = 0.5 ms.

The timestep study (tools/timestep_convergence.py) then found the gait frequency climbing
without limit as the step is refined: 0.72, 1.03, 1.23, 1.41, 1.62 Hz at 2.0 down to
0.125 ms, with the increments not shrinking. A quantity that keeps moving by the same
*fraction* on every halving is not converging to anything, and the direction of travel is
straight at the fast attractor.

The hypothesis this tool tests is therefore uncomfortable and worth stating plainly: **the
shipped gait frequency may be set by numerical damping rather than by the filter.** A
coarse step damps the fast mode for free; refine it and the damping goes away and the fast
mode takes back over. If that is right then head_tau is under-sized -- it was fitted
against a model that was getting help it did not know about -- and the honest fix is to
converge first and re-tune it second.

What the measurements actually said, in two passes.

First pass, head_tau from 0.22 to 1.20 at two step sizes. The hypothesis is confirmed
outright. At dt = 0.5 ms the power above 1.5 Hz is 1.0-2.0% at *every* head_tau -- the
fast mode is simply absent. At dt = 0.125 ms with the shipped head_tau = 0.22 it is
**53%**: the fast mode owns the animal. So head_tau = 0.22 does not suppress the fast
mode and never did; the coarse step was doing it, for free and invisibly.

   dt ms   head_tau |   freq Hz    power above 1.5 Hz    k_rms    speed mm/s
   0.125     0.22    |    1.633           53.2%           2.70    0.3398
   0.125     0.35    |    1.483           15.1%           2.70    0.3123
   0.125     0.50    |    0.733            3.1%           3.76    0.1503
   0.125     0.80    |    0.150            1.7%           2.94    0.1527
   0.500     0.22    |    1.250            1.5%           2.29    0.2086   <- shipped
   0.500     0.80    |    0.967            1.3%           1.85    0.1269

Second pass, refining further, looking for a head_tau at which the answer stops depending
on the step. There is not one, and that is the more important result:

   dt ms   head_tau |   freq Hz    power above 1.5 Hz    k_rms    speed mm/s
   0.062     0.40    |    0.150            2.7%           5.15    0.0641
   0.062     0.50    |    0.167            1.3%           5.12    0.0787
   0.062     0.60    |    0.167            0.8%           5.04    0.0661
   0.125     0.40    |    1.400            9.1%           2.61    0.3093
   0.125     0.50    |    0.733            3.1%           3.76    0.1503
   0.250     0.50    |    0.700            1.8%           3.14    0.1836
   0.250     0.60    |    0.117            2.0%           2.74    0.1435
   0.500     0.50    |    1.067            1.0%           2.31    0.2001

The frequencies do not scatter smoothly. They cluster -- near 0.15, near 0.70, near 1.0
to 1.4 -- and which cluster a run lands in flips on changes to dt and head_tau far too
small to be moving any physical quantity. This is a head loop with several coexisting
limit cycles and nothing principled selecting between them; the step size is acting as
the selector. "The undulation frequency" is therefore not a well-defined property of this
model as it stands, which is a stronger statement than the frequency merely being wrong.

The way out is the one this project has circled since day two and never finished: make the
*body* the oscillator rather than the head. A chain of segmental units coupled by
proprioception has its frequency set by segmental dynamics and coupling delay, which is a
far more robust selector than one loop's phase-crossover. The B-class Morris-Lecar units
are already in place for it.

!! The step-size numbers in this file are withdrawn. !!

Every "drift between dt = 0.5 and 0.125 ms" measured here was taken while `BodyParams.dt`
was not synchronised with `NeuralParams.dt`, so refining the neural step left the body
advancing 0.5 ms per call and running up to four times fast relative to its own nervous
system. The drift measured the desynchronisation, not numerical error. With the two
synchronised the frequency holds 0.44-0.45 Hz across a sixteen-fold range of step size.
See NEXT.md, day ten. The parameter results below stand -- they were taken at a single
step size, where the coupling was correct -- but nothing here about convergence does.

Run:  PYTHONPATH=. .venv/bin/python tools/head_mode.py
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import pooled
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 10.0, 30.0
SEEDS = (0, 3)
STEPS_MS = (0.5, 0.25, 0.125, 0.0625)
HEAD_TAU = (0.40, 0.50, 0.60)


def _job(job):
    dt_ms, head_tau, seed = job
    p = Params()
    p = dataclasses.replace(
        p,
        neural=dataclasses.replace(p.neural, dt=dt_ms * 1e-3),
        sensory=dataclasses.replace(p.sensory, head_tau=head_tau))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()

    start = sim.body.centroid().copy()
    t0 = sim.t
    ks = []
    every = max(1, int(round(0.005 / dt)))        # fixed 200 Hz, independent of dt
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
    freq = float(fr[1 + np.argmax(P[1:])])
    # How much of the curvature power sits above 1.5 Hz: the fast mode's signature,
    # independent of where the single dominant peak happens to land.
    fast = float(P[fr > 1.5].sum() / max(P[1:].sum(), 1e-30))
    return dict(dt_ms=dt_ms, head_tau=head_tau, seed=seed, freq=freq, speed=speed,
                fast_frac=fast, k_rms=float(np.sqrt((K ** 2).mean())))


def main():
    jobs = [(d, h, s) for d, h in itertools.product(STEPS_MS, HEAD_TAU) for s in SEEDS]
    print("HEAD MODE -- %d trials x %.0f s" % (len(jobs), WARMUP + MEASURE))
    print("  the 0.125 ms rows cost four times the 0.5 ms ones\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["dt_ms"], r["head_tau"]), []).append(r)
    f = lambda g, k: float(np.mean([x[k] for x in g]))            # noqa: E731

    print("   dt ms   head_tau |   freq Hz    power above 1.5 Hz    k_rms    speed mm/s")
    for key in sorted(agg):
        g = agg[key]
        mark = "   <- shipped" if key == (0.5, 0.22) else ""
        print("   %5.3f     %.2f    |   %6.3f          %5.1f%%          %5.2f    %.4f%s"
              % (key[0], key[1], f(g, "freq"), 100 * f(g, "fast_frac"),
                 f(g, "k_rms"), f(g, "speed"), mark))

    print()
    print("  a real animal on agar undulates at 0.30-0.50 Hz. The slow attractor this")
    print("  model is trying to reach was measured at 0.31 Hz with a 0.70 L wavelength.")
    print("  Read down each dt block: if a larger head_tau walks the frequency down at")
    print("  0.125 ms the way it does at 0.5 ms, the filter is the right knob and was")
    print("  simply calibrated against a step that was damping the fast mode for free.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
