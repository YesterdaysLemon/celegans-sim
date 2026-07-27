"""Oscillator strength against proprioceptive coupling.

The division of labour the model assumes is: the limit cycle supplies amplitude, and
proprioception supplies phase. That only holds if the coupling is strong enough to entrain
the cycle. Too far past the Hopf point and each segment free-runs, which is what the first
attempt did -- the posterior locked to itself and the wave ran backwards.

ca_ratio 0.24 is the bifurcation point (Hopf margin 1.0); below it the units are quiescent
and the model falls back to the purely reflexive one, which is the control.
"""
import dataclasses
import itertools
import multiprocessing as mp

import numpy as np

from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import travelling_index

WARMUP = 8.0
MEASURE = 26.0
REGIONS = [("head", 0.00, 0.20), ("mid", 0.40, 0.60), ("tail", 0.80, 1.00)]


def evaluate(job):
    ca_ratio, proprio, seed = job
    p = Params()
    p = dataclasses.replace(
        p,
        neural=dataclasses.replace(p.neural, ca_ratio=ca_ratio, adapt_ratio=2.0 * ca_ratio),
        sensory=dataclasses.replace(p.sensory, proprio_gain=proprio))
    sim = Simulation(p, seed=seed)
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()
    start = sim.body.centroid().copy()
    ks, path, prev = [], 0.0, sim.body.centroid().copy()
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20 == 0:
            ks.append(sim.body.curvature().copy())
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    K = np.array(ks)
    net = float(np.linalg.norm(sim.body.centroid() - start)) / MEASURE
    amp = {}
    n = K.shape[1]
    for name, lo, hi in REGIONS:
        seg = K[:, int(lo * n):max(int(hi * n), int(lo * n) + 1)]
        amp[name] = float(seg.std(axis=0).mean())
    return dict(ca_ratio=ca_ratio, proprio=proprio, seed=seed,
                twi=travelling_index(K), net=net,
                ratio=net * MEASURE / max(path, 1e-9),
                k_rms=float(np.sqrt((K ** 2).mean())), **amp)


def main():
    jobs = list(itertools.product([0.20, 0.26, 0.30, 0.36],
                                  [30.0, 60.0, 120.0, 240.0],
                                  [0]))
    with mp.Pool(min(10, mp.cpu_count() - 2)) as pool:
        rows = pool.map(evaluate, jobs)
    rows.sort(key=lambda r: -r['net'])
    print(" ca_ratio  proprio     TWI    net mm/s  net/path  k_rms   amp head/mid/tail")
    for r in rows:
        print("   %.2f      %5.0f   %+.3f    %.4f    %.3f    %5.2f   %5.2f %5.2f %5.2f"
              % (r['ca_ratio'], r['proprio'], r['twi'], r['net'], r['ratio'],
                 r['k_rms'], r['head'], r['mid'], r['tail']))
    print("\n  reflexive baseline: TWI +0.60, net 0.105, net/path 0.70, k_rms 2.1")
    print("  real animal:        TWI ~+1.0, net 0.219,             k_rms 4.3, amp roughly flat")


if __name__ == "__main__":
    main()
