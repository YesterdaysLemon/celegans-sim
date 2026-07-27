"""Localise the standing wave: is it already standing in the muscle drive, or only in the body?

The body's curvature is two-thirds a standing wave, and the mechanics have been exonerated
twice -- driven by a prescribed travelling moment the same body reaches a travelling index
of +0.996 and very nearly the animal's speed, and no bending stiffness over a 1600-fold
range gets the closed loop above +0.44.

So the fault is upstream. This measures the travelling index at each stage of the chain,
which says exactly where the wave stops travelling:

    motor neuron output  ->  muscle tension  ->  bending moment  ->  body curvature

If the drive is already standing at the neurons, the problem is in the circuit. If it
travels in the neurons and stands in the muscle, the problem is the neuromuscular map. If
it travels all the way to the moment and only the curvature stands, the problem is
mechanical after all and the earlier controls are wrong.

    PYTHONPATH=. python tools/where_it_stands.py
"""

from __future__ import annotations

import sys

import numpy as np

from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params


def main() -> int:
    p = Params()
    for seed in (0, 3):
        sim = Simulation(p, seed=seed, world=bare_world(p))
        sim.run(6.0)

        conn = sim.conn
        db, vb = conn.group("DB"), conn.group("VB")
        # Order the motor neurons by where along the body they actually act, so that
        # "along the body" means the same thing at every stage of the chain.
        from worm.senses import _output_position
        db = db[np.argsort([_output_position(conn, int(i)) for i in db])]
        vb = vb[np.argsort([_output_position(conn, int(i)) for i in vb])]

        neuro, muscle, moment, curve = [], [], [], []
        for i in range(int(30.0 / sim.dt)):
            sim.step()
            if i % 40 == 0:
                # Dorsoventral drive at each stage. It is the difference between the two
                # sides that bends the body, so that is what has to travel.
                s = sim.nervous.s
                n = min(len(db), len(vb))
                neuro.append(s[db[:n]] - s[vb[:n]])
                d, v = sim.muscles.row_tension()
                muscle.append(d - v)
                moment.append(sim.muscles.joint_moment().copy())
                curve.append(sim.body.curvature().copy())

        print("seed %d" % seed)
        for name, arr in (("motor neuron release (DB-VB)", neuro),
                          ("muscle tension (dorsal-ventral)", muscle),
                          ("bending moment", moment),
                          ("body curvature", curve)):
            a = np.array(arr)
            print("   %-32s TWI %+.3f" % (name, travelling_index(a)))
    print("\n+1 = pure travelling head to tail, 0 = pure standing wave (no net thrust).")
    print("Reference: this body driven by a prescribed travelling moment gives +0.996.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
