"""Retest the head reflex now that the body reflex actually works.

Backing the head reflex off was tried before and made things worse -- but that was when
the body reflex was crippled by a non-adapting stretch receptor, so the head was the only
thing driving the animal and weakening it could only hurt. With the body reflex working,
the balance is completely different: the head's in-phase drive to the anterior may now be
the main thing holding the travelling-wave index down at +0.5.
"""
from __future__ import annotations
import multiprocessing as mp, sys
from dataclasses import replace
import numpy as np
from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

def run(job):
    head, seed = job
    p = Params()
    p = replace(p, sensory=replace(Params().sensory, head_proprio_gain=head))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy(); prev = start.copy(); path = 0.0; kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0: kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid(); path += float(np.hypot(*(c - prev))); prev = c.copy()
    kap = np.array(kap); net = float(np.hypot(*(sim.body.centroid() - start)))
    return dict(head=head, seed=seed, twi=travelling_index(kap), net=net/35.0,
                ratio=net/max(path,1e-9), krms=float(np.sqrt((kap**2).mean())),
                kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(h, s) for h in (150.0, 250.0, 400.0, 600.0, 900.0) for s in (0, 3)]
    with mp.Pool(10) as pool: out = pool.map(run, jobs)
    print("%9s %5s %8s %10s %9s %8s %8s"
          % ("head gain","seed","TWI","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%9.0f %5d %+8.3f %10.4f %9.3f %8.2f %8.2f"
              % (r["head"], r["seed"], r["twi"], r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\ncurrent default head gain 150: TWI +0.48-0.57, net 0.095-0.106")
    print("real animal: net 0.219 mm/s, k_rms 4.3, k_max 9.8")
    print("prescribed travelling wave on this body: TWI +0.996, net 0.174")
