"""Does the body's bending stiffness decide whether the wave travels or stands?

The bending modulus is the one "measured" constant in this model with a serious
disagreement behind it. Fang-Yen et al. (2010) got 9.5e-14 N m^2 by micropipette on a
whole animal; Sznitman et al. (2010) inferred 4.19e-16 N m^2 from swimming kinematics.
That is a factor of 230, and the difference is what each assumed about active muscle.

Which matters here, because this model simulates the muscle *separately*. If the whole-
animal figure already contains the tone of a tonically contracted body wall -- and at a
resting tension of 0.5 both sheets here are half contracted -- then using it double-counts
the stiffness. And a stiffer body is exactly what turns an undulation into a standing
wave: bend the head of a stiff rod and the whole rod bends at once, with no phase lag
along it. A floppier body keeps bends local, which is what lets a reflex build a wave that
travels.

    PYTHONPATH=. python tools/stiffness.py
"""

from __future__ import annotations

import multiprocessing as mp
import sys
from dataclasses import replace

import numpy as np

from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

EI_VALUES = (0.095, 0.20, 0.40, 0.80, 1.60)
SEEDS = (0, 3)

# Muscle moment is scaled with stiffness, because curvature goes as moment over EI. Drop
# EI alone and the same muscles bend the body to a curvature of several hundred per
# millimetre, which tells you nothing except that the model has left its regime. Holding
# curvature fixed isolates the thing actually under test: the balance between elastic and
# viscous forces along the body, which is what decides whether a bend stays local enough
# for a wave to travel.
BASE_EI = 0.095


def run(job) -> dict:
    EI, seed = job
    p = Params()
    scale = EI / BASE_EI
    p = replace(p,
                body=replace(p.body, EI=EI),
                muscle=replace(p.muscle, peak_moment=p.muscle.peak_moment * scale))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)
    start = sim.body.centroid().copy()
    prev = start.copy()
    path = 0.0
    kap = []
    for i in range(int(35.0 / sim.dt)):
        sim.step()
        if i % 40 == 0:
            kap.append(sim.body.curvature().copy())
        if i % 200 == 0:
            c = sim.body.centroid()
            path += float(np.hypot(*(c - prev)))
            prev = c.copy()
    kap = np.array(kap)
    net = float(np.hypot(*(sim.body.centroid() - start)))
    return dict(EI=EI, seed=seed, twi=travelling_index(kap), net=net / 35.0,
                ratio=net / max(path, 1e-9), kmax=float(np.abs(kap).max()),
                krms=float(np.sqrt((kap ** 2).mean())))


def main() -> int:
    jobs = [(e, s) for e in EI_VALUES for s in SEEDS]
    with mp.Pool(min(10, len(jobs))) as pool:
        out = pool.map(run, jobs)
    print("bending modulus vs whether the wave travels\n")
    print("%-10s %5s %8s %10s %9s %8s %8s"
          % ("EI", "seed", "TWI", "net mm/s", "net/path", "k_rms", "k_max"))
    for r in out:
        print("%-10.4f %5d %+8.3f %10.4f %9.3f %8.2f %8.2f"
              % (r["EI"], r["seed"], r["twi"], r["net"], r["ratio"], r["krms"], r["kmax"]))
    print("\nreal animal:  net 0.219 mm/s, k_rms 4.3, k_max 9.8 /mm")
    print("this body driven by a prescribed travelling wave: TWI +0.996, net 0.174 mm/s")
    print("Fang-Yen EI = 0.095 (whole animal, includes muscle tone)")
    print("Sznitman EI = 0.00042 (inferred from kinematics)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
