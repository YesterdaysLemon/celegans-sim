"""Sweep the conditional-oscillator parameters in the *full* closed loop.

Isolated-cell tuning does not survive network embedding -- the first attempt produced a
backwards wave -- so this measures the quantities that actually matter (wave direction,
coherence, net progress) on the real body rather than on a single unit.
"""
import dataclasses
import itertools
import multiprocessing as mp
import sys

import numpy as np

from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import travelling_index

WARMUP = 8.0
MEASURE = 26.0


def evaluate(job):
    ca_ratio, adapt_tau, k_offset, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(
        p.neural, ca_ratio=ca_ratio, adapt_ratio=2.0 * ca_ratio,
        adapt_tau=adapt_tau, k_offset=k_offset))
    sim = Simulation(p, seed=seed)
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()
    start = sim.body.centroid().copy()
    ks, path = [], 0.0
    prev = start
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20 == 0:
            ks.append(sim.body.curvature().copy())
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    K = np.array(ks)
    net = float(np.linalg.norm(sim.body.centroid() - start)) / MEASURE
    twi = travelling_index(K)
    fs = 1.0 / (20 * dt)
    mid = K[:, K.shape[1] // 2]
    sp = np.abs(np.fft.rfft(mid - mid.mean()))
    f = float(np.fft.rfftfreq(len(mid), 1 / fs)[sp.argmax()])
    return dict(ca_ratio=ca_ratio, adapt_tau=adapt_tau, k_offset=k_offset, seed=seed,
                twi=twi, net=net, ratio=net * MEASURE / max(path, 1e-9),
                f=f, k_rms=float(np.sqrt((K ** 2).mean())))


def main():
    jobs = list(itertools.product(
        [0.30, 0.36, 0.42, 0.50],      # ca_ratio -- lower means closer to the Hopf point
        [0.16, 0.24, 0.34, 0.48],      # adapt_tau
        [10.0],
        [0],
    ))
    with mp.Pool(min(10, mp.cpu_count() - 2)) as pool:
        rows = pool.map(evaluate, jobs)
    rows.sort(key=lambda r: -r['net'])
    print(" ca_ratio  tau_n  k_off  seed     TWI    f Hz   net mm/s  net/path   k_rms")
    for r in rows:
        print("   %.2f     %.2f   %4.1f    %d   %+.3f   %.2f    %.4f    %.3f    %5.2f"
              % (r['ca_ratio'], r['adapt_tau'], r['k_offset'], r['seed'],
                 r['twi'], r['f'], r['net'], r['ratio'], r['k_rms']))
    print("\n  reflexive baseline: TWI +0.60, f 1.14 Hz, net 0.105, net/path 0.70, k_rms 2.1")
    print("  real animal:        TWI ~+1.0, f 0.30 Hz, net 0.219,             k_rms 4.3")
    print("  (0.30 and 0.219 are not jointly reachable -- see tools/thrust.py)")


if __name__ == "__main__":
    main()
