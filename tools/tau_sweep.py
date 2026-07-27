"""adapt_tau at the critically-poised operating point, three seeds each."""
import dataclasses, itertools, multiprocessing as mp
import numpy as np
from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import travelling_index

WARMUP, MEASURE = 8.0, 30.0


def evaluate(job):
    tau, k_off, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(
        p.neural, ca_ratio=0.20, adapt_ratio=0.40, adapt_tau=tau, k_offset=k_off))
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
            c = sim.body.centroid(); path += float(np.linalg.norm(c - prev)); prev = c.copy()
    K = np.array(ks)
    d = float(np.linalg.norm(sim.body.centroid() - start))
    return tau, k_off, seed, travelling_index(K), d / MEASURE, d / max(path, 1e-9)


def main():
    jobs = list(itertools.product([0.08, 0.12, 0.18, 0.25, 0.30], [10.0], [0, 3, 7]))
    with mp.Pool(min(10, mp.cpu_count() - 2)) as pool:
        rows = pool.map(evaluate, jobs)
    agg = {}
    for tau, k_off, seed, twi, net, ratio in rows:
        agg.setdefault((tau, k_off), []).append((twi, net, ratio))
    print("  tau_n  k_off      TWI    net mm/s (sd)   net/path")
    for (tau, k_off), v in sorted(agg.items(), key=lambda kv: -np.mean([x[1] for x in kv[1]])):
        t, n, r = (np.array([x[i] for x in v]) for i in range(3))
        print("   %.2f   %4.1f    %+.3f    %.4f (%.4f)   %.3f"
              % (tau, k_off, t.mean(), n.mean(), n.std(), r.mean()))


if __name__ == "__main__":
    main()
