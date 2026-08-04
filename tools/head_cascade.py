"""Can a cascade of head-cell lags buy the frequency the invented delay was buying?

`SensoryParams.head_delay` is 0.28 s and is the largest fitted number in the model. Its own
note says what it is: not a receptor property but "the size of what the model is missing,
stated plainly", and it names the candidate for what it stands in for --

    RMD, SMD and SMB are lumped here into one reflex with one gain and one filter; the
    real thing is several cell classes with their own dynamics... A distributed
    multi-stage circuit accumulates phase that a single first-order lag cannot.
    Replacing this number with that circuit is the way to earn it back.

Half of that has been done and it is important to say which half, because it is the half
that did *not* work. `head_distributed` gives every head cell its own patch of body to read,
and `tools/head_circuit.py` measured the result: the delay fell from 0.60 s to 0.28 and the
travelling wave got better, but the delay did not go away, and the reason is recorded there --

    a spread of delays low-passes the loop rather than adding phase to it, and this
    crossover is phase-limited, so the anatomical spread cannot substitute for the
    invented one.

Cells in *parallel*, each with the same first-order filter, average. They do not compose.
One lag contributes at most 90 degrees of phase however hard it is driven, and a loop that
needs 180 cannot get there from one filter, so the rest had to be bought with a pure delay.

Stages in *series* are the other object, and the arithmetic is the entire hypothesis. N
stages of `head_tau / N` each contribute `arctan(w*tau/N)`, so together they give
`N*arctan(w*tau/N)`: about `w*tau` at low frequency, identical to the single lag, but rising
to N*90 degrees rather than 90. As N grows that converges on `exp(-i*w*tau)`. **A cascade is
not an approximation of a transport delay -- it is what a transport delay is, built out of
cells instead of out of a ring buffer.**

So the prediction is specific and falsifiable: at a fixed `head_delay`, adding stages should
*lower* the frequency, and there should be a stage count that reaches the shipped 0.65 Hz
with `head_delay = 0`. If adding stages does nothing to the frequency, the hypothesis is
wrong in the same way the spatial spread was, and this file should say so and stop.

Three things are scored besides frequency, because the delay was adopted on frequency alone
and quietly cost the others:

    TWI         the fraction of the mechanical thrust ceiling collected (tools/thrust.py);
                this is what distributing bought and what a replacement must not give back
    wavelength  0.65 L in the animal
    k_rms       4.3 /mm in the animal; the delay's own table shows it trading against this

And one thing rides on it that is not about the gait at all. `headHist` is 210,936 B, **89%
of an animal** (`node wasm/memory.mjs`) -- a 560-sample ring per joint, held only to look up
one sample 0.28 s old. A cascade is `head_stages` scalars per joint. A configuration that
reaches the right frequency at `head_delay = 0` does not improve the population budget, it
removes nine tenths of it.

Nothing here is adopted and nothing is ported to the runtime. `head_stages = 1` is bit
identical to the shipped model, verified against nodes and membrane potentials over 4000
steps, which is the state a thing should be measured in before it is believed.

Run:  PYTHONPATH=. .venv/bin/python tools/head_cascade.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 40.0
SEEDS = (0, 3, 7)

# The shipped row is (1, 0.28). Everything else asks whether stages can pay for delay.
STAGES = (1, 2, 3, 4)
DELAYS = (0.00, 0.10, 0.20, 0.28)

# What the animal does, for the columns that have a target at all.
TARGET = dict(freq=(0.30, 0.50), wavelength=0.65, k_rms=4.3, speed=0.219)


def _job(job):
    stages, delay, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, head_stages=stages, head_delay=delay))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)                       # let the loop settle onto whichever cycle it picks
    start = sim.body.centroid().copy()
    t0 = sim.t
    prev, path = start.copy(), 0.0
    every = max(1, int(round(0.05 / sim.dt)))
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    net = float(np.linalg.norm(sim.body.centroid() - start))
    span = sim.t - t0

    r = analyse(sim, seconds=MEASURE)
    return dict(stages=stages, delay=delay, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(st, d, s) for st in STAGES for d in DELAYS for s in SEEDS]
    print("HEAD CASCADE -- %d trials x %.0f s, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  does N first-order stages in series pay for the invented delay?\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["stages"], r["delay"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  stages delay | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    for key in sorted(agg):
        g = agg[key]
        mark = "  <- shipped" if key == (1, 0.28) else ""
        print("  %6d %5.2f | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f%s"
              % (key[0], key[1], mean(g, "freq"), sd(g, "freq"), mean(g, "wavelength"),
                 mean(g, "twi"), mean(g, "k_rms"), mean(g, "speed"),
                 mean(g, "net_path"), mark))

    # The hypothesis, read directly rather than left to the eye: at fixed delay, does
    # adding stages lower the frequency? If this column is flat, the cascade is doing what
    # the spatial spread did and the idea is dead.
    print("\n  Frequency against stage count, at each delay. The hypothesis says these fall.")
    print("  delay |" + "".join("  %d stages" % s for s in STAGES))
    for d in DELAYS:
        cells = []
        for st in STAGES:
            g = agg.get((st, d))
            cells.append("   %6.3f" % mean(g, "freq") if g else "       --")
        print("  %5.2f |%s" % (d, "".join(cells)))

    shipped = agg.get((1, 0.28))
    if shipped:
        f_ship, twi_ship = mean(shipped, "freq"), mean(shipped, "twi")
        print("\n  Shipped (1 stage, 0.28 s): %.3f Hz, TWI %+.3f." % (f_ship, twi_ship))
        # A replacement has to land the frequency *and* keep the wave. Report both, and
        # report the ones that fail the second test too -- a row that hits the frequency by
        # destroying the travelling wave is how the delay got adopted in the first place.
        best = [(k, agg[k]) for k in agg if k[1] == 0.0]
        if best:
            print("  With no delay at all:")
            for k, g in sorted(best):
                df, dt_ = mean(g, "freq") - f_ship, mean(g, "twi") - twi_ship
                print("    %d stage(s): %.3f Hz (%+.3f), TWI %+.3f (%+.3f)"
                      % (k[0], mean(g, "freq"), df, mean(g, "twi"), dt_))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
