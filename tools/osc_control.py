"""Separate the two changes.

Two things landed together: the Morris-Lecar conditional oscillator, and scaling sensory
input by each target's resting conductance. ca_ratio = 0 removes the oscillator entirely
and leaves only the normalisation, so this sweep attributes the gain to one or the other
instead of assuming it.
"""
import dataclasses
import itertools
import multiprocessing as mp

import numpy as np

from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import travelling_index

WARMUP, MEASURE = 8.0, 30.0
REGIONS = [("head", 0.00, 0.20), ("mid", 0.40, 0.60), ("tail", 0.80, 1.00)]


def coherence(seg, f_idx):
    sp = np.abs(np.fft.rfft(seg - seg.mean(axis=0), axis=0)) ** 2
    tot = sp[1:].sum(axis=0)
    band = sp[max(f_idx - 1, 1):f_idx + 2].sum(axis=0)
    return float(np.mean(band / np.maximum(tot, 1e-12)))


def evaluate(job):
    ca_ratio, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(
        p.neural, ca_ratio=ca_ratio, adapt_ratio=2.0 * ca_ratio))
    sim = Simulation(p, seed=seed)
    dt = p.neural.dt
    for _ in range(int(WARMUP / dt)):
        sim.step()
    start = sim.body.centroid().copy()
    ks, path, prev = [], 0.0, start.copy()
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20 == 0:
            ks.append(sim.body.curvature().copy())
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    K = np.array(ks)
    n = K.shape[1]
    mid = K[:, n // 2]
    sp = np.abs(np.fft.rfft(mid - mid.mean()))
    sp[0] = 0
    f_idx = int(sp.argmax())
    fs = 1.0 / (20 * dt)
    out = dict(ca_ratio=ca_ratio, seed=seed,
               twi=travelling_index(K),
               net=float(np.linalg.norm(sim.body.centroid() - start)) / MEASURE,
               ratio=float(np.linalg.norm(sim.body.centroid() - start)) / max(path, 1e-9),
               f=float(np.fft.rfftfreq(len(mid), 1 / fs)[f_idx]),
               k_rms=float(np.sqrt((K ** 2).mean())))
    for name, lo, hi in REGIONS:
        seg = K[:, int(lo * n):max(int(hi * n), int(lo * n) + 1)]
        out["a_" + name] = float(seg.std(axis=0).mean())
        out["c_" + name] = coherence(seg, f_idx)
    return out


def main():
    jobs = list(itertools.product([0.00, 0.13, 0.20, 0.26, 0.32], [0, 3, 7]))
    with mp.Pool(min(10, mp.cpu_count() - 2)) as pool:
        rows = pool.map(evaluate, jobs)
    print(" ca_ratio  seed     TWI    f Hz   net mm/s  net/path   amp h/m/t        coherence h/m/t")
    for r in sorted(rows, key=lambda r: (r['ca_ratio'], r['seed'])):
        print("   %.2f      %d   %+.3f   %.2f    %.4f    %.3f   %4.1f %4.1f %4.1f   %.2f %.2f %.2f"
              % (r['ca_ratio'], r['seed'], r['twi'], r['f'], r['net'], r['ratio'],
                 r['a_head'], r['a_mid'], r['a_tail'],
                 r['c_head'], r['c_mid'], r['c_tail']))
    print()
    for ca in sorted({r['ca_ratio'] for r in rows}):
        g = [r for r in rows if r['ca_ratio'] == ca]
        print("  ca_ratio %.2f : net %.4f +- %.4f mm/s   TWI %+.3f   tail coherence %.2f"
              % (ca, np.mean([r['net'] for r in g]), np.std([r['net'] for r in g]),
                 np.mean([r['twi'] for r in g]), np.mean([r['c_tail'] for r in g])))
    print("\n  pre-change model: net 0.105, TWI +0.60, tail coherence 0.03-0.05")
    print("  real animal:      net 0.219, TWI ~+1.0")


if __name__ == "__main__":
    main()
