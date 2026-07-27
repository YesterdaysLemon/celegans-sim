"""With the receptor adapting, recover the curvature amplitude via muscle strength."""
from __future__ import annotations
import multiprocessing as mp, sys
from dataclasses import replace
import numpy as np
from tools.diagnose_loop import analyse, bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

def run(job):
    gain, moment, seed = job
    p = Params()
    p = replace(p, muscle=replace(Params().muscle, peak_moment=moment),
                sensory=replace(Params().sensory, proprio_gain=gain))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy(); prev = start.copy(); path = 0.0; kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0: kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid(); path += float(np.hypot(*(c - prev))); prev = c.copy()
    kap = np.array(kap); net = float(np.hypot(*(sim.body.centroid() - start)))
    return dict(gain=gain, moment=moment, seed=seed, twi=travelling_index(kap),
                net=net/35.0, ratio=net/max(path,1e-9),
                krms=float(np.sqrt((kap**2).mean())), kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(g, m, s) for g in (30.0, 45.0, 65.0) for m in (1.6, 2.6, 4.0) for s in (0, 3)]
    with mp.Pool(10) as pool: out = pool.map(run, jobs)
    print("%7s %8s %5s %8s %10s %9s %8s %8s"
          % ("gain","moment","seed","TWI","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%7.0f %8.1f %5d %+8.3f %10.4f %9.3f %8.2f %8.2f"
              % (r["gain"], r["moment"], r["seed"], r["twi"], r["net"], r["ratio"],
                 r["krms"], r["kmax"]))
    print("\nreal animal: net 0.219 mm/s, net/path >0.5, k_rms 4.3, k_max 9.8")
    print("shipped:     net 0.005, net/path 0.07, k_rms 4.1, k_max 10, TWI +0.33")
