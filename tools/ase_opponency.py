"""Which way round should the ON and OFF chemosensors push?

`Senses` gives ASEL a current proportional to +dC/dt and ASER one proportional to -dC/dt,
which is a genuine opponent pair and the right biology: ASEL depolarises when a
water-soluble attractant rises, ASER when it falls (Suzuki et al. 2008). But both cells
projected onto the same first-layer interneurons with the same sign -- ASEL makes 19
contacts onto AIY and ASER 16 -- so AIY received (+dC/dt) + (-dC/dt) and **the opponency
cancelled itself at the first synapse**. That is why making both of them inhibitory together
only moved the pirouette ratio from 0.68 to 1.22: it shifted the common mode, which is not
where the signal is.

For the pair to mean anything, the two cells have to push their shared target in opposite
directions. One transmitter, two receptors, and this model already has the machinery --
the reversal potential is per synapse, so ASEL and ASER can answer with different ones
even though they are one anatomical class.

Which way round was an empirical question, and this tool is the instrument that settled
it: SETTLED AND ADOPTED. The shipped model answers glutamate from the ON cells with
chloride -- `NeuralParams.glucl_pre/post` carry ("ASEL","AWA","PHB") -> ("AIY","AVA",
"AIB") with the whole measurement chain in their provenance, and
tests/test_behaviour.py pins the AIB asymmetry as a fact of wiring. Do not re-run this
to decide anything; re-run it only to re-measure. The measurement is the
pirouette bias directly: drive the pair as a rising attractant would (ASEL up, ASER down)
and count reversals, then drive it as a falling one would and count again. A chemotaxing
animal reverses *less* while things improve, so

    improving reversal rate  <  worsening reversal rate

is the whole of Pierce-Shimomura's mechanism, and the ratio between them is what the
chemotaxis assay reports as the pirouette ratio -- above 1 for any animal that chemotaxes,
about 2 for a real one.

Run:  PYTHONPATH=. .venv/bin/python tools/ase_opponency.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.params import Params

WARMUP, MEASURE = 8.0, 90.0
SEEDS = (0, 1, 3, 5)
DRIVE = 3.0            # pA into the pair, the scale a real gradient delivers

# (label, which cells answer glutamate with a chloride channel)
# These arms are the 2026-08 sets the recorded run compared -- before PHB joined
# glucl_pre and AIB/AVA joined glucl_post -- kept as they were so a re-measurement
# stays comparable with the recorded numbers. The winner ("ASEL only") is what shipped,
# since widened; the arms are not the current default.
ASSIGNMENTS = [
    ("neither", ()),
    ("both", ("ASE", "AWC")),
    ("ASEL only (ON)", ("ASEL", "AWA")),
    ("ASER only (OFF)", ("ASER", "AWC")),
]


def _job(job):
    label, pre, sign, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(
        p.neural, glucl_pre=tuple(pre) or ("ASEL",),
        glucl_strength=1.0 if pre else 0.0))
    sim = Simulation(p, seed=seed, world=bare_world(p))

    on, off = sim.senses.ase_on, sim.senses.ase_off
    base = sim.senses.sense

    def wrapped(*a, **k):
        # Exactly what a gradient does to the pair: ON up and OFF down when improving.
        I = base(*a, **k)
        I[on] += sign * DRIVE
        I[off] -= sign * DRIVE
        return I

    sim.senses.sense = wrapped
    sim.run(WARMUP)

    rev, was = 0, True
    for _ in range(int(MEASURE / sim.dt)):
        sim.step()
        if was and not sim.senses.going_forward:
            rev += 1
        was = sim.senses.going_forward
    return dict(label=label, sign=sign, seed=seed, rate=rev * 60.0 / MEASURE)


def main():
    jobs = [(lab, pre, sgn, s)
            for lab, pre in ASSIGNMENTS for sgn in (+1, -1) for s in SEEDS]
    print("ASE OPPONENCY -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  reversals per minute under a held gradient, %.0f pA into the pair\n" % DRIVE)
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    print("  chloride on      | improving | worsening |  ratio   verdict")
    for lab, _ in ASSIGNMENTS:
        up = [r["rate"] for r in rows if r["label"] == lab and r["sign"] > 0]
        dn = [r["rate"] for r in rows if r["label"] == lab and r["sign"] < 0]
        if not up or not dn:
            continue
        u, d = float(np.mean(up)), float(np.mean(dn))
        ratio = d / u if u > 1e-9 else float("inf")
        verdict = "chemotaxis" if ratio > 1.05 else ("inverted" if ratio < 0.95 else "flat")
        print("  %-16s |   %5.2f   |   %5.2f   |  %5.2f   %s"
              % (lab, u, d, ratio, verdict))

    print()
    print("  a real animal is near 2. Anything at or below 1 means the biased random walk")
    print("  is biased the wrong way or not at all, and no amount of sensory gain fixes")
    print("  that -- it is a statement about which way the pair pushes, not how hard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
