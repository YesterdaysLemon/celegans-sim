"""Is the tail's incoherence just background noise, amplified by sparse innervation?

The tail muscle rows have 7 presynaptic motor neurons where the head has 22-25. The
per-muscle conductance normalisation then gives each of those few neurons about three
times the weight its counterpart has at the head, so anything random in a single posterior
neuron passes through with little averaging to suppress it.

Turning the background current noise off is a one-line test of whether that is what the
tail is doing.
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
    sigma, seed = job
    p = Params()
    p = replace(p, neural=replace(Params().neural, noise_sigma=sigma))
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
    coh, f0, _ = profile(kap, fs)
    s = sim.muscles.joint_s
    net = float(np.hypot(*(sim.body.centroid()-start)))
    return dict(sigma=sigma, seed=seed, f0=f0, twi=travelling_index(kap),
                coh_mid=float(coh[(s>=0.4)&(s<0.6)].mean()),
                coh_post=float(coh[(s>=0.6)&(s<0.8)].mean()),
                coh_tail=float(coh[s>=0.8].mean()),
                net=net/35.0, ratio=net/max(path,1e-9),
                krms=float(np.sqrt((kap**2).mean())))

if __name__ == "__main__":
    jobs = [(g, s) for g in (2.2, 1.0, 0.3, 0.0) for s in (0, 3, 7)]
    with mp.Pool(9) as pool: out = pool.map(run, jobs)
    print("%7s %5s %7s %8s %9s %9s %9s %10s %9s"
          % ("noise","seed","Hz","TWI","coh mid","coh post","coh tail","net mm/s","net/path"))
    for r in out:
        print("%7.1f %5d %7.2f %+8.3f %9.2f %9.2f %9.2f %10.4f %9.3f"
              % (r["sigma"], r["seed"], r["f0"], r["twi"], r["coh_mid"], r["coh_post"],
                 r["coh_tail"], r["net"], r["ratio"]))
    print("\n2.2 pA is the current default. coherence 1.0 = all motion is the undulation.")
    print("currently: mid 0.75-0.83, posterior 0.37-0.45, tail 0.02-0.05")
