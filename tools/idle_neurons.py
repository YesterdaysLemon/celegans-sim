"""Which neurons can the world not reach? The deafness audit.

Every sensory pathway in the model routes to named cells (worm/senses.py), the
proprioceptive and head-reflex fields to computed supports, the command drive to the
AVB/AVA pools. Everything else participates only through the reconstructed wiring --
which is the JOB of an interneuron, and is how the pharyngeal circuit genuinely works
(worm/pharynx.py: food reaches MC through NSM and the anatomy). But a SENSORY neuron
with no routed transduction is a cell the world cannot touch: whatever it does in the
real animal, here it is deaf.

This measures the roster instead of asserting it. Run after adding any sensory route;
the point is that "which cells are still deaf" stays a command, not a memory.

Run:  PYTHONPATH=. .venv/bin/python tools/idle_neurons.py

Reading of the first run (2026-08-24), so the headline is on the record:

  103/302 reachable. The deaf sensory cells that matter, with the biology that wants
  them: PHA/PHB (tail chemosensors -- the head/tail repellent comparison that decides
  escape DIRECTION, Hilliard 2002); BAG (O2 downshift, the missing half of aerotaxis
  -- URX senses the upshift); AWB (volatile repellent odour beside routed ADL); ADF/
  ASI/ASG/ASJ (food-quality chemosensors). The AS class (11 cord motor neurons) is
  field-blind while DA/DB/VA/VB all carry receptive fields. PVD (harsh touch) is
  unrouted. HSN/VC are NOT idle -- egg-laying reads them as actuators -- and the DD/VD
  cross-inhibitors are driven by the anatomy, which is correct.

Second reading (2026-08-24, after the phasmid + BAG routes went in): 109/302 reachable.
PHA/PHB now carry the repellent at the tail and BAG the oxygen downshift, so the top
two entries above are paid off; AWB, ADF/ASI/ASG/ASJ, the AS class and PVD remain.
"""

from __future__ import annotations

import collections

import numpy as np

from worm.engine import Simulation
from worm.params import Params


def routed_map(sim):
    sn = sim.senses
    routed: dict[int, list[str]] = {}

    def mark(idx, label):
        for i in np.atleast_1d(idx):
            routed.setdefault(int(i), []).append(label)

    mark(sn.ase_on, 'attractant'); mark(sn.ase_off, 'attractant')
    mark(sn.awc, 'odour'); mark(sn.awa, 'odour')
    mark(sn.ash, 'repellent'); mark(sn.adl, 'repellent'); mark(sn.ask, 'repellent')
    mark(sn.phasmid, 'tail repellent')
    mark(sn.afd, 'temperature'); mark(sn.urx, 'oxygen')
    mark(sn.bag, 'oxygen downshift')
    mark(sn.touch_anterior, 'touch'); mark(sn.touch_posterior, 'touch')
    mark(sn.nose_touch, 'nose touch')
    mark(sn.dopaminergic, 'food'); mark(sn.nsm, 'food')
    mark(sn.avb, 'command'); mark(sn.ava, 'command')
    mark(np.where(np.abs(sn.W_b).sum(axis=1) > 0)[0], 'proprioception')
    mark(np.where(np.abs(sn.W_a).sum(axis=1) > 0)[0], 'proprioception')
    mark(np.where(np.abs(sn.W_head).sum(axis=1) > 0)[0], 'head reflex')
    mark(np.where(sn.W_head_sign != 0)[0], 'head reflex')
    if hasattr(sn, '_omega_v'):
        mark(sn._omega_v, 'omega'); mark(sn._omega_d, 'omega')
    if hasattr(sim, 'sleep'):
        mark(sim.sleep.ris, 'sleep drive')   # the homeostat's current -- worm/sleep.py
    return routed


def classes(names, ix):
    c = collections.Counter()
    for i in ix:
        stem = ''.join(ch for ch in names[i] if not ch.isdigit()).rstrip('LR') or names[i]
        c[stem] += 1
    return ', '.join(f'{k}x{v}' if v > 1 else k for k, v in sorted(c.items()))


def main():
    sim = Simulation(Params(), seed=0)
    conn = sim.conn
    routed = routed_map(sim)
    names = [conn.names[i] for i in range(conn.n)]
    kinds = getattr(conn, 'kind', ['?'] * conn.n)

    unrouted = [i for i in range(conn.n) if i not in routed]
    sens = [i for i in unrouted if 'sensory' in str(kinds[i]).lower()]
    motor = [i for i in unrouted if 'motor' in str(kinds[i]).lower()]
    inter = [i for i in unrouted if i not in sens and i not in motor]

    print(f'{conn.n} neurons; {len(routed)} reachable by some input route; '
          f'{len(unrouted)} only through the wiring')
    print(f'\nDEAF SENSORY ({len(sens)}) -- the world cannot touch these:')
    print(f'  {classes(names, sens)}')
    print(f'\nFIELD-BLIND MOTOR ({len(motor)}) -- driven by anatomy alone '
          f'(HSN/VC are read as actuators; DD/VD inhibition IS the anatomy):')
    print(f'  {classes(names, motor)}')
    print(f'\nWIRING-ONLY INTER ({len(inter)}) -- which is an interneuron\'s job:')
    print(f'  {classes(names, inter)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
