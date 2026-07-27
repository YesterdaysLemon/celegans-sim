"""Test the peak_moment candidate from the reflex sweep, and check the ratio caveat.

The reflex-gain table reports amplitude(reflex on) / amplitude(reflex off), and near the
tail the denominator is nearly zero because the passive response has died away. A ratio of
19 there could be a real regenerated wave or two small numbers divided by each other. So
this reports absolute amplitudes alongside, and the region-wise travelling index, which is
what actually decides whether the animal moves.
"""
from __future__ import annotations
import multiprocessing as mp, sys
from dataclasses import replace
import numpy as np
from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

def run(job):
    moment, seed = job
    p = Params()
    p = replace(p, muscle=replace(Params().muscle, peak_moment=moment))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy(); prev = start.copy(); path = 0.0; kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0: kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid(); path += float(np.hypot(*(c-prev))); prev = c.copy()
    kap = np.array(kap); net = float(np.hypot(*(sim.body.centroid() - start)))
    s = sim.muscles.joint_s
    post = (s >= 0.45)
    # Absolute oscillation amplitude, so a ratio cannot flatter a dead tail.
    amp = kap.std(axis=0)
    return dict(moment=moment, seed=seed, twi=travelling_index(kap),
                twi_post=travelling_index(kap[:, post]),
                amp_mid=float(amp[(s>0.4)&(s<0.6)].mean()),
                amp_tail=float(amp[s>0.75].mean()),
                net=net/35.0, ratio=net/max(path,1e-9),
                krms=float(np.sqrt((kap**2).mean())), kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(m, s) for m in (2.6, 3.2, 4.0) for s in (0, 3, 7)]
    with mp.Pool(9) as pool: out = pool.map(run, jobs)
    print("%7s %5s %8s %9s %9s %9s %10s %9s %8s %8s"
          % ("moment","seed","TWI","TWI post","amp mid","amp tail","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%7.1f %5d %+8.3f %+9.3f %9.3f %9.3f %10.4f %9.3f %8.2f %8.2f"
              % (r["moment"], r["seed"], r["twi"], r["twi_post"], r["amp_mid"],
                 r["amp_tail"], r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\n2.6 is the current default. real animal: net 0.219, k_rms 4.3, k_max 9.8")
    print("amp columns are absolute curvature s.d. in /mm -- a dead tail cannot hide there")
