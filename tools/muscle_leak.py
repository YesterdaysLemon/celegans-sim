"""Is the coupling weak, or is my muscle leak too high?

What decides how much neighbouring muscle cells smooth each other is the ratio of coupling
conductance to the cell's own leak, not the coupling alone. Boyle & Cohen's 370 pS is a
measurement; the 2.2 nS leak in this model is not -- I picked it to give a 23 ms membrane
time constant, which was a guess. Real body-wall muscle has a capacitance of 50-70 pF
(Goodman et al. 2012), so a leak of 1 nS gives a 50 ms time constant, equally plausible,
and triples the relative strength of the measured coupling.

That is the defensible way to get the benefit: revisit the number I invented, not inflate
the number somebody measured.
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
    gleak, seed = job
    p = Params()
    p = replace(p, muscle=replace(Params().muscle, g_leak=gleak))
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
    tau = 50.0 / gleak      # ms, with C = 50 pF
    return dict(g=gleak, tau=tau, seed=seed, twi=travelling_index(kap),
                coh_post=float(coh[(s>=0.6)&(s<0.8)].mean()),
                coh_tail=float(coh[s>=0.8].mean()),
                net=net/35.0, ratio=net/max(path,1e-9),
                krms=float(np.sqrt((kap**2).mean())), kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(g, s) for g in (2.2, 1.4, 1.0, 0.7) for s in (0, 3, 7)]
    with mp.Pool(9) as pool: out = pool.map(run, jobs)
    print("%8s %8s %5s %8s %9s %9s %10s %9s %8s %8s"
          % ("g_leak","tau ms","seed","TWI","coh post","coh tail","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%8.2f %8.0f %5d %+8.3f %9.2f %9.2f %10.4f %9.3f %8.2f %8.2f"
              % (r["g"], r["tau"], r["seed"], r["twi"], r["coh_post"], r["coh_tail"],
                 r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\n2.2 nS is the current value (23 ms). coupling stays at the measured 0.37 nS.")
    print("real animal: net 0.219 mm/s, k_rms 4.3, k_max 9.8")
