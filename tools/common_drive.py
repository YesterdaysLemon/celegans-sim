"""Test whether a shared oscillating drive is forcing the motor neurons into lockstep.

The dorsoventral drive leaving the B-type motor neurons is a pure standing wave (travelling
index -0.006). They are all oscillating in phase with each other. Something is broadcasting
a common rhythm to the whole cord, and proprioception -- the only thing that can give them
a phase gradient along the body -- is a small perturbation on top of it.

The obvious suspect is AVB. It is the forward command interneuron and it gap-junctions onto
every B-type motor neuron, and gap junctions are bidirectional: if AVB is itself oscillating
it broadcasts one synchronous rhythm to the entire cord. In a real animal AVB is *tonically*
active during forward locomotion, not rhythmic.

This clamps the command interneurons to a fixed potential -- tonic drive, no rhythm -- and
asks whether the wave starts travelling.

    PYTHONPATH=. python tools/common_drive.py
"""

from __future__ import annotations

import sys

import numpy as np

from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params
from worm.senses import _output_position


def measure(clamp: bool, seed: int, seconds: float = 30.0) -> dict:
    p = Params()
    sim = Simulation(p, seed=seed, world=bare_world(p))
    conn = sim.conn
    command = conn.select("AVBL", "AVBR", "PVCL", "PVCR")
    db, vb = conn.group("DB"), conn.group("VB")
    db = db[np.argsort([_output_position(conn, int(i)) for i in db])]
    vb = vb[np.argsort([_output_position(conn, int(i)) for i in vb])]
    n = min(len(db), len(vb))

    sim.run(6.0)
    hold = sim.nervous.V[command].mean() if clamp else None

    start = sim.body.centroid().copy()
    prev = start.copy()
    path = 0.0
    neuro, curve, avb = [], [], []
    for i in range(int(seconds / sim.dt)):
        sim.step()
        if clamp:
            sim.nervous.V[command] = hold
        if i % 40 == 0:
            s = sim.nervous.s
            neuro.append(s[db[:n]] - s[vb[:n]])
            curve.append(sim.body.curvature().copy())
            avb.append(float(sim.nervous.V[command].mean()))
        if i % 200 == 0:
            c = sim.body.centroid()
            path += float(np.hypot(*(c - prev)))
            prev = c.copy()
    net = float(np.hypot(*(sim.body.centroid() - start)))
    a = np.array(avb)
    return dict(twi_neuro=travelling_index(np.array(neuro)),
                twi_curve=travelling_index(np.array(curve)),
                net=net / seconds, ratio=net / max(path, 1e-9),
                avb_swing=float(a.max() - a.min()))


def main() -> int:
    print("%-26s %5s %11s %11s %10s %9s %10s"
          % ("command interneurons", "seed", "TWI neurons", "TWI body", "net mm/s",
             "net/path", "AVB swing"))
    for clamp, label in ((False, "free (as shipped)"), (True, "clamped tonic")):
        for seed in (0, 3):
            r = measure(clamp, seed)
            print("%-26s %5d %+11.3f %+11.3f %10.4f %9.3f %9.1f mV"
                  % (label, seed, r["twi_neuro"], r["twi_curve"], r["net"], r["ratio"],
                     r["avb_swing"]), flush=True)
    print("\nAVB should be tonic during forward locomotion, not rhythmic. If clamping it")
    print("raises the travelling index, gap-junctional broadcast is forcing the lockstep.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
