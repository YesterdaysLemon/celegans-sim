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

Two readings distinguish the possibilities:

  * frequency rises with refinement at fixed head_tau, and a larger head_tau brings it
    back down at the fine step -> the filter is the right knob, it is simply too small,
    and the slow attractor is still reachable.
  * frequency rises with refinement and head_tau cannot bring it back -> the fast mode is
    not being held off by that filter at all and the head loop needs rethinking.

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
STEPS_MS = (0.5, 0.125)
HEAD_TAU = (0.22, 0.35, 0.50, 0.80, 1.20)


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
