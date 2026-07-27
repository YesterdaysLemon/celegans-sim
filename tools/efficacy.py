"""Is the muscle efficacy gradient attenuating the wave before it reaches the tail?

The phase profile now shows a clean monotonic phase gradient of -379 degrees along the
cord -- more than the -300 a 0.65 L wavelength needs. The motor neurons are producing a
properly travelling pattern. What they are not producing is a constant-amplitude one: the
curvature amplitude falls about sevenfold from head to tail, so the head's large standing
oscillation dominates the power and the posterior, which travels fine, contributes almost
nothing.

One obvious suspect is built in on purpose. Boyle et al. taper muscle strength from 0.70 at
the head to 0.29 at the tail, and this model copies that as efficacy_head/efficacy_tail =
1.0/0.41. In their model the taper creates a head-to-tail gradient of natural frequencies
that helps entrain the chain. Here it may simply be starving the posterior.
"""
from __future__ import annotations
import multiprocessing as mp, sys
from dataclasses import replace
import numpy as np
from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

def run(job):
    tail, seed = job
    p = Params()
    p = replace(p, muscle=replace(Params().muscle, efficacy_tail=tail))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)
    start = sim.body.centroid().copy(); prev = start.copy(); path = 0.0; kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0: kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid(); path += float(np.hypot(*(c-prev))); prev = c.copy()
    kap = np.array(kap); net = float(np.hypot(*(sim.body.centroid()-start)))
    s = sim.muscles.joint_s; amp = kap.std(axis=0)
    head_amp = float(amp[s < 0.3].mean()); tail_amp = float(amp[s > 0.7].mean())
    return dict(tail=tail, seed=seed, twi=travelling_index(kap),
                twi_post=travelling_index(kap[:, s >= 0.45]),
                decay=head_amp/max(tail_amp, 1e-9), net=net/35.0,
                ratio=net/max(path,1e-9), krms=float(np.sqrt((kap**2).mean())),
                kmax=float(np.abs(kap).max()))

if __name__ == "__main__":
    jobs = [(t, s) for t in (0.41, 0.70, 1.00, 1.40) for s in (0, 3, 7)]
    with mp.Pool(9) as pool: out = pool.map(run, jobs)
    print("%9s %5s %8s %9s %8s %10s %9s %8s %8s"
          % ("eff_tail","seed","TWI","TWI post","head/tail","net mm/s","net/path","k_rms","k_max"))
    for r in out:
        print("%9.2f %5d %+8.3f %+9.3f %8.2f %10.4f %9.3f %8.2f %8.2f"
              % (r["tail"], r["seed"], r["twi"], r["twi_post"], r["decay"],
                 r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\n0.41 is the current default (Boyle's taper). 1.00 = no taper.")
    print("head/tail is the curvature amplitude ratio -- lower means the wave survives.")
    print("real animal: net 0.219 mm/s, k_rms 4.3, k_max 9.8")
