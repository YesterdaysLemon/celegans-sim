"""How much muscle-muscle coupling does it take to keep the tail coherent?

Boyle & Cohen's 370 pS is only about a tenth of a muscle cell's total conductance here, and
at that strength the coupling raises the travelling index by about 0.09 but leaves the tail
thrashing. The question is whether a defensible value fixes it, or whether the model simply
cannot tolerate realistic membrane noise and something else is missing.
"""
from __future__ import annotations
import multiprocessing as mp, sys
from dataclasses import replace
import numpy as np
from tools.diagnose_loop import bare_world, travelling_index
from tools.coherence import profile
from worm.engine import Simulation
from worm.params import Params

def run(job):
    ggap, seed = job
    p = Params()
    p = replace(p, muscle=replace(Params().muscle, g_muscle_gap=ggap))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy(); prev = start.copy(); path = 0.0
    stride, kap = 40, []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % stride == 0: kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid(); path += float(np.hypot(*(c-prev))); prev = c.copy()
    kap = np.array(kap); fs = 1.0/(sim.dt*stride)
    coh, f0, _ = profile(kap, fs); s = sim.muscles.joint_s
    net = float(np.hypot(*(sim.body.centroid()-start)))
    return dict(g=ggap, seed=seed, twi=travelling_index(kap),
                coh_post=float(coh[(s>=0.6)&(s<0.8)].mean()),
                coh_tail=float(coh[s>=0.8].mean()),
                net=net/35.0, ratio=net/max(path,1e-9),
                krms=float(np.sqrt((kap**2).mean())), kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(g, s) for g in (0.37, 1.2, 3.0, 8.0) for s in (0, 3, 7)]
    with mp.Pool(9) as pool: out = pool.map(run, jobs)
    print("%8s %5s %8s %9s %9s %10s %9s %8s %8s"
          % ("g_gap nS","seed","TWI","coh post","coh tail","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%8.2f %5d %+8.3f %9.2f %9.2f %10.4f %9.3f %8.2f %8.2f"
              % (r["g"], r["seed"], r["twi"], r["coh_post"], r["coh_tail"],
                 r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\n0.37 nS is Boyle & Cohen's measured value; muscle leak here is 2.2 nS.")
    print("noise is at its default 2.2 pA throughout. real animal: net 0.219 mm/s.")
