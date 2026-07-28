"""Is the gait converged at dt = 0.5 ms, or is some of it numerical?

This is not a performance tool, although it started as one. Everything in this simulator
costs 2000 steps per simulated second, so halving the timestep is the largest single lever
on runtime and the obvious thing to reach for. It is also the most dangerous, and the
reason is specific: **the model's largest open discrepancy is the undulation frequency**,
1.2 Hz against 0.30-0.50 Hz for a real animal on agar, and the gait is a limit cycle that
emerges from a delayed feedback loop rather than being prescribed anywhere. A limit
cycle's period is exactly the kind of quantity that shifts with integration error. So:

  * If the gait metrics are flat from dt = 0.125 ms up to 0.5 ms, the model is converged
    where it runs, the frequency discrepancy is entirely physics, and a larger step can be
    considered on its merits.
  * If they are still moving at 0.5 ms, then part of the headline discrepancy is the
    integrator, every frequency result in NEXT.md is contaminated, and the timestep should
    come *down* rather than up regardless of what it costs.

Either answer is worth more than the speed. The question has never been asked here, and
until it is, no frequency result in this project is safe -- which is the real argument
against raising dt to go faster: it would make a known-unresolved number cheaper to
compute without making it truer.

Integration is exponential Euler on the neurons, which is unconditionally stable, so
nothing will blow up at any step size tried here. Stability is not the question;
accuracy is, and a stable wrong answer is the failure mode to look for.

!! The step-size numbers in this file are withdrawn. !!

Every "drift between dt = 0.5 and 0.125 ms" measured here was taken while `BodyParams.dt`
was not synchronised with `NeuralParams.dt`, so refining the neural step left the body
advancing 0.5 ms per call and running up to four times fast relative to its own nervous
system. The drift measured the desynchronisation, not numerical error. With the two
synchronised the frequency holds 0.44-0.45 Hz across a sixteen-fold range of step size.
See NEXT.md, day ten. The parameter results below stand -- they were taken at a single
step size, where the coupling was correct -- but nothing here about convergence does.

Run:  PYTHONPATH=. .venv/bin/python tools/timestep_convergence.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

MEASURE = 60.0
SEEDS = (0, 3, 7)
STEPS_MS = (0.125, 0.25, 0.5, 1.0, 2.0)      # 0.5 is the shipped value


def _job(job):
    dt_ms, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, dt=dt_ms * 1e-3))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    # Net displacement over the whole measurement window, not sim.speed's trailing two
    # seconds -- a two-second estimator on a 1 Hz gait is noisy enough to muddy a
    # convergence trend, which is the one thing this tool must not do.
    sim.run(4.0)
    start = sim.body.centroid().copy()
    t0 = sim.t
    r = analyse(sim, seconds=MEASURE, warmup=0.0)
    net = float(np.linalg.norm(sim.body.centroid() - start)) / (sim.t - t0)
    return dict(dt_ms=dt_ms, seed=seed, freq=r["freq"], wavelength=r["wavelength"],
                twi=r["twi"], speed=net, speed_2s=r["speed"], kappa_rms=r["kappa_rms"],
                kappa_max=r["kappa_max"], dv_corr=r["dv_corr"],
                direction=r["direction"])


def main():
    jobs = [(d, s) for d in STEPS_MS for s in SEEDS]
    print("TIMESTEP CONVERGENCE -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  cost scales as 1/dt, so the 0.125 ms rows are 16x the 2 ms ones\n")
    rows = pooled(_job, jobs)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault(r["dt_ms"], []).append(r)
    f = lambda g, k: float(np.mean([x[k] for x in g]))            # noqa: E731
    sd = lambda g, k: float(np.std([x[k] for x in g]))            # noqa: E731

    print("   dt ms   steps/s |   freq Hz (sd)    wavelen L      TWI     k_rms   speed mm/s")
    for d in sorted(agg):
        g = agg[d]
        mark = "   <- shipped" if d == 0.5 else ""
        print("   %5.3f    %5.0f  |  %5.3f (%.3f)     %5.2f      %+.3f    %5.2f    %.4f%s"
              % (d, 1e3 / d, f(g, "freq"), sd(g, "freq"), f(g, "wavelength"),
                 f(g, "twi"), f(g, "kappa_rms"), f(g, "speed"), mark))

    # Convergence is a statement about successive refinement, so report it that way:
    # how much each metric still moves when the step is halved. If the model is converged
    # at the shipped value, the change from 0.25 to 0.5 is within the seed spread.
    print()
    print("  change on halving the step, as a fraction of the coarser value")
    print("   dt ms pair      freq      wavelen      TWI       speed   | seed sd of freq")
    ds = sorted(agg)
    for a, b in zip(ds, ds[1:]):
        ga, gb = agg[a], agg[b]
        rel = lambda k: (f(ga, k) - f(gb, k)) / abs(f(gb, k)) if f(gb, k) else float("nan")  # noqa: E731
        print("   %5.3f <- %5.3f  %+7.1f%%  %+8.1f%%  %+8.1f%%  %+8.1f%%  |  %.3f Hz"
              % (a, b, 100 * rel("freq"), 100 * rel("wavelength"),
                 100 * rel("twi"), 100 * rel("speed"), sd(gb, "freq")))
    print()
    print("  read the top row first: it is the finest refinement available and therefore")
    print("  the best evidence about whether the shipped step is small enough. A change")
    print("  larger than the seed spread in the last column is a real one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
