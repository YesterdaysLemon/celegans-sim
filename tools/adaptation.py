"""Does adapting the stretch receptor let the wave travel?

Sweeps the proprioceptive gain now that the receptor high-passes its input. The point is
not just that adaptation helps on its own -- it is that it removes the failure mode that
capped the gain. Previously, turning the gain up amplified the static component of the
bend along with the dynamic one and curled the animal up; with the static part adapted
away there should be room to push.

    PYTHONPATH=. python tools/adaptation.py
"""

from __future__ import annotations

import multiprocessing as mp
import sys
from dataclasses import replace

import numpy as np

from tools.diagnose_loop import analyse, bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

GAINS = (45.0, 90.0, 180.0, 360.0, 700.0)
SEEDS = (0, 3)


def run(job) -> dict:
    gain, tau, seed = job
    p = Params()
    p = replace(p, sensory=replace(p.sensory, proprio_gain=gain, proprio_tau_adapt=tau))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy()
    prev = start.copy()
    path = 0.0
    kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0:
            kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid()
            path += float(np.hypot(*(c - prev)))
            prev = c.copy()
    kap = np.array(kap)
    net = float(np.hypot(*(sim.body.centroid() - start)))
    return dict(gain=gain, tau=tau, seed=seed, twi=travelling_index(kap),
                net=net / 35.0, ratio=net / max(path, 1e-9),
                krms=float(np.sqrt((kap ** 2).mean())), kmax=float(np.abs(kap).max()))


def main() -> int:
    # tau = 1e6 s is effectively no adaptation, i.e. the old behaviour, for comparison.
    jobs = [(g, t, s) for t in (1e6, 2.5) for g in GAINS for s in SEEDS]
    with mp.Pool(10) as pool:
        out = pool.map(run, jobs)
    print("%-14s %7s %5s %8s %10s %9s %8s %8s"
          % ("receptor", "gain", "seed", "TWI", "net mm/s", "net/path", "k_rms", "k_max"))
    for r in out:
        label = "absolute" if r["tau"] > 1e5 else "adapting"
        print("%-14s %7.0f %5d %+8.3f %10.4f %9.3f %8.2f %8.2f"
              % (label, r["gain"], r["seed"], r["twi"], r["net"], r["ratio"],
                 r["krms"], r["kmax"]))
    print("\nshipped: TWI +0.33, net 0.005 mm/s, net/path 0.07, k_rms 4.1, k_max 10")
    print("real animal: net 0.219 mm/s, k_rms 4.3, k_max 9.8")
    print("this body given a prescribed travelling wave: TWI +0.996, net 0.174 mm/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
