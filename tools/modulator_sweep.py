"""Calibrate the modulator layer against the basal slowing response.

Sawin, Ranganathan & Horvitz (2000) is the assay: drop a well-fed animal onto a bacterial
lawn and it slows down, roughly halving its speed within a minute. Animals that cannot make
dopamine (cat-2) do not slow. It is the cleanest food-driven behaviour in the repertoire
and it needs nothing our model lacks -- CEP/ADE/PDE already receive food input, they simply
had no route from there to locomotion until the modulators existed.

This is also the first behavioural test in this project the animal has any chance of
passing. Chemotaxis needs the animal to *choose a direction*, which is still blocked;
slowing needs only a scalar turned down, which is exactly what a modulator does.

Scored as speed on food / speed off food. Real animals: about 0.5. Coefficients at zero
reproduce the unmodulated model exactly, and that is the control row.
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import estimate, pooled
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 10.0, 55.0
SEEDS = (0, 3)


def _plate(on_food):
    def build(p):
        w = World(p.world, np.random.default_rng(0))
        if on_food:
            # A lawn big enough that the animal stays on it for the whole measurement.
            w.add_food_patch(0.0, 0.0, 9.0, density=1.0, attractant=1.0, length_scale=9.0)
        return w
    return build


def _job(job):
    da_slow, ht_turn, on_food, seed = job
    p = Params()
    p = dataclasses.replace(p, modulator=dataclasses.replace(
        p.modulator, dopamine_slowing=da_slow, serotonin_slowing=0.5 * da_slow,
        serotonin_turning=ht_turn))
    sim = Simulation(p, seed=seed, world=_plate(on_food)(p),
                     placement=(0.0, 0.0, float((seed % 6) * (2 * np.pi / 6))))
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()
    start = sim.body.centroid().copy()
    path, prev = 0.0, start.copy()
    levels, gates = [], []
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20 == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
            r = sim.senses.readout
            levels.append([r.get(k, 0.0) for k in
                           ("dopamine", "serotonin", "octopamine", "pdf")])
            gates.append(r.get("gate_forward", 1.0))
    d = float(np.linalg.norm(sim.body.centroid() - start))
    L = np.array(levels)
    return dict(da_slow=da_slow, ht_turn=ht_turn, on_food=on_food, seed=seed,
                speed=d / MEASURE, path_speed=path / MEASURE,
                ratio=d / max(path, 1e-9),
                da=float(L[:, 0].mean()), ht=float(L[:, 1].mean()),
                gate=float(np.mean(gates)), gate_sd=float(np.std(gates)))


def main():
    jobs = list(itertools.product([0.0, 2.0, 4.0, 6.0, 10.0], [0.0, 0.6],
                                  [False, True], SEEDS))
    print("estimated %.0f s for %d trials" % (estimate(len(jobs), WARMUP + MEASURE), len(jobs)))
    rows = pooled(_job, jobs)

    agg = {}
    for r in rows:
        agg.setdefault((r["da_slow"], r["ht_turn"], r["on_food"]), []).append(r)
    print("\n  da_slow  ht_turn   condition   speed mm/s   path mm/s   gate (sd)   [DA]    [5HT]")
    keys = sorted({(k[0], k[1]) for k in agg})
    for da_slow, ht_turn in keys:
        for on_food in (False, True):
            g = agg.get((da_slow, ht_turn, on_food), [])
            if not g:
                continue
            f = lambda k: np.mean([x[k] for x in g])            # noqa: E731
            print("   %.1f      %.2f     %-9s     %.4f      %.4f    %.2f (%.2f)  %+.3f  %+.3f"
                  % (da_slow, ht_turn, "on food" if on_food else "off food",
                     f("speed"), f("path_speed"), f("gate"), f("gate_sd"),
                     f("da"), f("ht")))
        off = agg.get((da_slow, ht_turn, False), [])
        on = agg.get((da_slow, ht_turn, True), [])
        if off and on:
            so = np.mean([x["speed"] for x in off])
            sn = np.mean([x["speed"] for x in on])
            print("            -> slowing ratio on/off = %.2f   (real animal ~0.5)"
                  % (sn / max(so, 1e-9)))
    print("\n  da_slow 0.0 is the control: the modulator layer is present but inert, so")
    print("  those two rows must match the unmodulated model and each other.")


if __name__ == "__main__":
    main()
