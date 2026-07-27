"""Is the travelling-wave ceiling just the head dragging the average down?

The whole-body index sticks at about +0.58 no matter what the head reflex gain does. But
the head is only a fifth of the body and it is where the rhythm is generated -- a short
segment oscillating in place cannot support a travelling wave within itself. If it
contributes a large share of the curvature power as pure standing, it caps the whole-body
average on its own, and the body wave posterior to it could be much healthier than the
single number suggests.
"""
from __future__ import annotations
import sys
import numpy as np
from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

def main():
    p = Params()
    for seed in (0, 3):
        sim = Simulation(p, seed=seed, world=bare_world(p))
        sim.run(8.0)
        kap = []
        for i in range(int(35.0 / sim.dt)):
            sim.step()
            if i % 40 == 0: kap.append(sim.body.curvature().copy())
        kap = np.array(kap)
        s = sim.muscles.joint_s
        print("seed %d" % seed)
        for lo, hi, label in ((0.0, 1.0, "whole body"),
                              (0.0, 0.30, "head and neck  (0.00-0.30)"),
                              (0.30, 1.0, "body behind it (0.30-1.00)"),
                              (0.45, 1.0, "posterior half (0.45-1.00)")):
            m = (s >= lo) & (s < hi)
            sub = kap[:, m]
            power = float((sub.var(axis=0)).sum() / kap.var(axis=0).sum())
            print("   %-28s TWI %+.3f   %4.0f%% of the curvature power"
                  % (label, travelling_index(sub), 100 * power))
    print("\nprescribed travelling wave on this body: +0.996")
    return 0

if __name__ == "__main__":
    sys.exit(main())
