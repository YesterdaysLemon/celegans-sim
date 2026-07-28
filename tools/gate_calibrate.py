"""Place the new direction gate, and size the cord drive that replaces AVB's clamp.

The command difference (forward pool activation minus backward pool) measures 0.140 with
a standard deviation of 0.035 -- a genuine 25% spread, where the old absolute-activity
gate had none at all. What is left is to put the 50/50 point somewhere useful and to work
out how much drive the selected cord needs now that it is no longer getting it through
AVB's membrane potential.

Wanted: forward fraction near 0.9 (committed, but not pinned), a standard deviation big
enough that sensory input can move it, and forward locomotion back at 0.19 mm/s with a
travelling index near +0.75.
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import estimate, pooled
from tools.diagnose_loop import travelling_index
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 8.0, 26.0
SEEDS = (0, 3, 7)


def _job(job):
    tonic, drive, slope, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, tonic_forward=tonic, cord_drive=drive, gate_slope=slope,
        gate_bias=0.09))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()
    start = sim.body.centroid().copy()
    ks, gates, path, prev = [], [], 0.0, start.copy()
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20 == 0:
            ks.append(sim.body.curvature().copy())
            gates.append(sim.senses.readout["gate_forward"])
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    K, G = np.array(ks), np.array(gates)
    d = float(np.linalg.norm(sim.body.centroid() - start))
    return dict(tonic=tonic, drive=drive, slope=slope, seed=seed,
                speed=d / MEASURE, ratio=d / max(path, 1e-9),
                twi=travelling_index(K), k_rms=float(np.sqrt((K ** 2).mean())),
                gate=float(G.mean()), gate_sd=float(G.std()))


def main():
    jobs = list(itertools.product([22.0, 45.0, 70.0, 90.0], [0.0, 8.0, 20.0],
                                  [30.0], SEEDS))
    print("estimated %.0f s for %d trials" % (estimate(len(jobs), WARMUP + MEASURE), len(jobs)))
    rows = pooled(_job, jobs)
    agg = {}
    for r in rows:
        agg.setdefault((r["tonic"], r["drive"]), []).append(r)
    print("\n  tonic  cord_drive   gate (sd)     speed mm/s   net/path    TWI     k_rms")
    best = None
    for (tonic, drive), g in sorted(agg.items()):
        f = lambda k: np.mean([x[k] for x in g])            # noqa: E731
        print("   %3.0f      %4.0f      %.3f (%.3f)     %.4f      %.3f    %+.3f   %5.2f"
              % (tonic, drive, f("gate"), f("gate_sd"), f("speed"),
                 f("ratio"), f("twi"), f("k_rms")))
        score = f("speed") if f("gate_sd") > 0.01 else 0.0
        if best is None or score > best[0]:
            best = (score, tonic, drive)
    print("\n  reference before the decoupling: gate 0.98 with sd 0.000, speed 0.191,")
    print("  net/path 0.83, TWI +0.749. A gate sd of zero is the thing we are fixing,")
    print("  so a configuration that recovers the speed with sd 0 would be no progress.")
    if best:
        print("  best speed with a live gate: tonic %.0f, cord_drive %.0f" % best[1:])


if __name__ == "__main__":
    main()
