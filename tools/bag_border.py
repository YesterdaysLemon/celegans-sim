"""Does BAG change what the animal does at a lawn border? The due-diligence assay.

The phasmid + BAG batch (2026-08-24) routed BAG as the oxygen-downshift sensor -- the
falling edge of the same signal URX carries the level and rise of -- and pinned it at
the transduction level only. This measures the behavioural half of the claim. A lawn
dents the oxygen field (o2_depth over the lawn, an exp skirt of o2_length_scale beyond
it), so an animal approaching a lawn is an animal walking down an oxygen gradient: BAG
fires on the way in and is silent on the way out. In the animal that falling edge is
part of what makes a lawn edge a *place* -- worms slow and settle where oxygen drops
(Zimmer et al. 2009 for BAG's edge; the URX side of border behaviour is Gray et al.
2004).

Design: one worm placed at the CENTRE of a 1.5 mm lawn, 90 s -- paired per seed
against the identical animal with bag_gain = 0. Scored on where it spent its time
(dwell fraction inside the lawn plus its skirt), how many times it left, and how often
its heading flipped within 1 mm of the border.

The first design started the animal 1.5 mm *outside*, aimed at the lawn, and scored
approach: 1 of 16 animals ever arrived in 75 s. That is the known taxis-magnitude gap
(NEXT.md second tier) doing to the assay what it does to the animal, and an assay that
depends on a weak behaviour to deliver its subject to the measurement is measuring the
weak behaviour. Starting on the lawn, every border crossing is the animal's own, and
the question BAG can answer -- does the falling edge of oxygen hold you where the food
is -- gets asked every time it wanders out.

Run:  PYTHONPATH=. .venv/bin/python tools/bag_border.py [seeds]

Reading of the first run (2026-08-25, 8 seeds, 90 s, bag_gain 900 against 0):

    bag_gain    0   dwell 0.109   exits 1.2   d_final 15.74   d_max 16.97   flips 2.8
    bag_gain  900   dwell 0.172   exits 1.6   d_final 13.72   d_max 15.21   flips 5.1
    paired dwell on-off: +0.062   [+0.35 0 0 0 0 0 0 +0.15]

The edge response is real and the retention is thin. Near the border the routed animal
turns almost twice as often (2.8 -> 5.1 flips within 1 mm of the edge) -- that is the
falling edge of oxygen doing exactly what it was wired to do -- and its excursions end
~2 mm nearer the lawn. But the dwell gain is carried by 2 of 8 seeds; most animals
walk out in the opening seconds regardless, before pressure of any kind can matter.
That is the model's standing taxis-magnitude ceiling (NEXT.md, second tier) wearing an
oxygen costume, not a BAG defect: the turn the circuit asks for is shallower than the
animal's, so asking more often only goes so far. Re-run after a turn-depth mechanism
lands; do not tune this gain against the current turn.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from worm.engine import Simulation
from worm.params import Params
from worm.world import World

T = 90.0
LAWN_R = 1.5
SAMPLE_DT = 0.25


def trial(job):
    seed, bag = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(p.sensory, bag_gain=bag))
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, LAWN_R, density=1.0, attractant=1.0, length_scale=4.0)
    ang = (seed % 8) * (2 * np.pi / 8)
    sim = Simulation(p, seed=seed, world=w, placement=(0.0, 0.0, float(ang)))

    n_samp = int(round(T / SAMPLE_DT))
    step_per = max(1, int(round(SAMPLE_DT / p.neural.dt)))
    xs, ys = [], []
    for _ in range(n_samp):
        for _ in range(step_per):
            sim.step()
        mid = sim.body.nodes()[len(sim.body.nodes()) // 2]
        xs.append(float(mid[0])); ys.append(float(mid[1]))
    xs, ys = np.array(xs), np.array(ys)
    d = np.hypot(xs, ys)

    on = d < (LAWN_R + 0.3)
    dwell = float(on.mean())
    exits = int(((~on[1:]) & on[:-1]).sum())
    d_final = float(d[-1])
    d_max = float(d.max())

    near = np.abs(d[1:] - LAWN_R) < 1.0
    # A heading flip leaves a signature in consecutive displacements; the dot-product
    # sign change is the cheap proxy the other assays use.
    vx, vy = np.diff(xs), np.diff(ys)
    dots = vx[1:] * vx[:-1] + vy[1:] * vy[:-1]
    flips = (dots < 0) & near[1:]
    return dict(seed=seed, bag=bag, dwell=dwell, exits=exits,
                d_final=d_final, d_max=d_max,
                border_flips=int(flips.sum()))


def main():
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    jobs = [(s, b) for s in range(seeds) for b in (0.0, None)]
    jobs = [(s, Params().sensory.bag_gain if b is None else b) for s, b in jobs]
    with ProcessPoolExecutor(max_workers=min(14, os.cpu_count() or 4)) as ex:
        rows = list(ex.map(trial, jobs))

    gains = sorted({r["bag"] for r in rows})
    for g in gains:
        sel = [r for r in rows if r["bag"] == g]
        print("bag_gain %5.0f  dwell %.3f  exits %.1f  d_final %5.2f  d_max %5.2f  "
              "border flips %.1f" % (
                  g, np.mean([r["dwell"] for r in sel]),
                  np.mean([r["exits"] for r in sel]),
                  np.mean([r["d_final"] for r in sel]),
                  np.mean([r["d_max"] for r in sel]),
                  np.mean([r["border_flips"] for r in sel])))
    lo, hi = gains
    paired = []
    for s in range(seeds):
        a = next(r for r in rows if r["seed"] == s and r["bag"] == hi)
        b = next(r for r in rows if r["seed"] == s and r["bag"] == lo)
        paired.append(a["dwell"] - b["dwell"])
    paired = np.array(paired)
    print("paired dwell on-off: %+0.3f  [%s]" % (
        paired.mean(), " ".join("%+0.2f" % v for v in paired)))


if __name__ == "__main__":
    main()
