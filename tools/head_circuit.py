"""Does a head reflex distributed over its own neurons replace the invented delay?

`SensoryParams.head_delay` is the largest fitted number in this model: 0.60 s of transport
delay in the head reflex, with nothing in a real stretch receptor remotely that slow. It
was adopted because it was the only thing that brought the undulation frequency into the
animal's band, and three separate results have since argued it is the wrong kind of object:

  * it is unearned -- mechanotransduction takes milliseconds;
  * it kills gait modulation, because a fixed delay contributes fixed phase at every
    frequency and so pins the loop's crossover regardless of mechanical load, and the
    animal correspondingly slows in water where a real one speeds up;
  * it cost the travelling-wave index, +0.75 down to +0.61, and thrust is the travelling
    index (tools/thrust.py), so it bought the frequency partly by giving away speed.

The reason it was needed is structural. The lumped reflex hands every head motor neuron
the same number -- the mean curvature of the front 17% of the body -- so twelve cells that
act on different pieces of body all see the same thing at the same time. No spatial spread
means no phase spread, and the phase had to come from somewhere.

But those cells do not act on the same piece of body. Weighted by their own neuromuscular
maps, RMD, SMD and SMB act between s = 0.135 and s = 0.229: a tenth of a body length, which
the travelling wave takes about 0.28 s to cross. Letting each cell read the curvature
around the piece it moves supplies that phase from the anatomy instead of from a constant
-- and, unlike a delay, it should follow the mechanical load, because the time the wave
takes to cross the head is itself a property of the medium.

Scored on four things at once, because the delay was adopted on one of them and quietly
cost the others:

    frequency   0.30-0.50 Hz on agar
    TWI         as high as possible; it is the fraction of the thrust ceiling collected
    wavelength  0.65 L
    speed       against the ceiling for its own kinematics, not against a fixed number

Run:  PYTHONPATH=. .venv/bin/python tools/head_circuit.py
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 40.0
SEEDS = (0, 3, 7)
# First pass: distributing the reflex does not lower the frequency at all -- 1.27 to 1.32
# Hz against the lumped reflex's 1.18 with no delay. A spread of delays low-passes the
# loop rather than adding phase to it, and this crossover is phase-limited, so the
# anatomical spread cannot substitute for the invented one. It does transport better
# though: net speed 0.15 against 0.124 and net-to-path 0.76 against 0.63. So the question
# becomes whether it needs *less* delay for the same frequency, and keeps the better wave.
# Second pass, with the delay actually applied in both modes (it had been a no-op in
# distributed mode, which made the first sweep meaningless). Distributed + 0.20 s beats
# the shipped lumped + 0.60 s on the two things that matter most -- travelling index
# +0.68 against +0.58, net speed 0.176 against 0.124 -- with a third of the invented
# delay. What it gives up is curvature, 3.43 against 4.32, so this pass goes after that.
FIELDS = (0.08, 0.10, 0.14)
GAINS = (150.0, 260.0)
DELAYS = (0.15, 0.20, 0.28)


def _job(job):
    distributed, field, gain, delay, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, head_distributed=distributed, head_field=field,
        head_proprio_gain=gain, head_delay=delay))
    sim = Simulation(p, seed=seed, world=bare_world(p))

    sim.run(6.0)
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
    return dict(distributed=distributed, field=field, gain=gain, delay=delay, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(False, 0.10, 150.0, 0.60, s) for s in SEEDS]          # the shipped lumped one
    jobs += [(True, f, g, d, s)
             for f, g, d in itertools.product(FIELDS, GAINS, DELAYS) for s in SEEDS]
    print("HEAD CIRCUIT -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  lumped+delay against distributed with no delay at all\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["distributed"], r["field"], r["gain"], r["delay"]), []).append(r)
    f = lambda g, k: float(np.nanmean([x[k] for x in g]))          # noqa: E731

    print("  reflex       field gain delay | freq Hz wavelen  TWI    k_rms  net mm/s  n/p")
    for key in sorted(agg, key=lambda k: (k[0], k[1], k[2], k[3])):
        g = agg[key]
        label = "distributed" if key[0] else "lumped"
        print("  %-11s %5.2f %4.0f %5.2f | %6.3f %6.2f  %+.3f  %5.2f  %.4f  %.2f"
              % (label, key[1], key[2], key[3], f(g, "freq"), f(g, "wavelength"),
                 f(g, "twi"), f(g, "k_rms"), f(g, "speed"), f(g, "net_path")))

    print()
    print("  the lumped row is the model as it ships: 0.45 Hz, TWI +0.61, 0.105 mm/s,")
    print("  bought with a 0.60 s delay that nothing in the animal justifies. A")
    print("  distributed row that matches it on frequency while beating it on TWI has")
    print("  earned the delay back and bought speed with it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
