"""Which AWB helps the escape: the OFF cell (relief), the ON cell (presence), or neither?

AWB is the volatile-repellent olfactory pair (Troemel et al. 1997); imaging shows
odor-removal (OFF) responses. Wiring here: AWB -> AIZ (13), ADF (13), RIA, AVB (3).
Injected via a wrapped sense() so no model code changes before the measurement: the
OFF arm adds gain * max(0, -drep) (fires as the repellent CLEARS -- relief), the ON
arm gain_t * rep + gain_d * max(0, drep) (fires in and into it). drep is recomputed
from the world against the senses' own adapted baseline (read before sense updates
it, so the deviation matches what ASH saw this step).

Plate: the nociception drop (strength 0.9, ls 5) at (6,0); animal at the origin.
Scored on how fast and how far it gets clear.

Run:  PYTHONPATH=. .venv/bin/python tools/awb_probe.py

Reading of the first run (2026-08-25, 6 seeds, 120 s, after the ASE opponency landed):

    arm none  d_final 34.78  d_max 35.05  t_clear 25.2 s   cleared 6/6
    arm off   d_final 27.95  d_max 28.19  t_clear 37.3 s   cleared 6/6
    arm on    d_final 30.93  d_max 30.93  t_clear 45.1 s   cleared 6/6
    paired d_final vs none:  off -6.83 mm   on -3.85 mm

NEGATIVE, both signs: routing AWB through the wiring as reconstructed makes escape
measurably WORSE whichever way it is rectified, because AWB's principal targets (AIZ,
13 contacts; ADF, 13) feed the reversal-adjacent path, and injecting current there --
relief-timed or presence-timed -- slows clearance. The same wrong-way-wiring shape as
PHB -> AVA and ASEL -> AIB, but with no receptor-level fix named by any prior
measurement here. The follow-up hypothesis, recorded and not adopted: an OFF-response
AWB with chloride on AIZ (relief inhibiting the reversal path) would have the
Pierce-Shimomura shape; it wants its own paired run before any list is widened.

The second chance was run (2026-08-26, issue #203), and it is the THIRD negative:

    arm none   d_final 34.78  d_max 35.05  t_clear 25.2 s   cleared 6/6
    arm offcl  d_final 26.89  d_max 28.32  t_clear 24.8 s   cleared 6/6
    paired d_final vs none: -7.89 mm  [-8.4 +1.1 -21.9 +12.1 -6.1 -24.2]

The chloride half of the hypothesis does what it promised -- clearance time fell from
the OFF arm's 37.3 s back to 24.8 s, level with deaf -- but the animal still ends
7.9 mm CLOSER to the drop than the deaf control, 4 of 6 seeds worse. Relief inhibiting
AIZ gets the escape started on time and then bleeds it of distance. Two notes for
whoever reopens this: (1) the surgical route was forced -- widening the glucl class
lists would also flip AWA -> AIZ (x17) and AWBL -> AIBR (x1), measured in trial()'s
comment -- so any adoption needs a per-pair mechanism first; (2) with three paired
measurements against it (ON, OFF, OFF+chloride), AWB's deafness is now the
best-supported null in the sensory roster. It stays deaf, on the record and on purpose.
"""
import os

import numpy as np
from concurrent.futures import ProcessPoolExecutor

from worm.engine import Simulation
from worm.params import Params
from worm.world import World

T = 120.0
SEEDS = list(range(6))
GAIN_OFF = 2000.0     # pA per unit/s of falling repellent (the relief signal)
GAIN_ON_T = 20.0      # tonic, beside ADL's 0.8*chemo_gain
GAIN_ON_D = 2000.0    # rising differential


def trial(job):
    seed, arm = job
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    w.add_repellent_source(6.0, 0.0, strength=0.9, length_scale=5.0)
    ang = (seed % 8) * (2 * np.pi / 8)
    sim = Simulation(p, seed=seed, world=w, placement=(0.0, 0.0, float(ang)))
    s = sim.senses
    awb = sim.conn.select("AWBL", "AWBR")
    base = s.sense

    if arm == "offcl":
        # The receptor-level half of the hypothesis: chloride on AWB -> AIZ, and on
        # that pair alone. The class-list mechanism (NeuralParams.glucl_pre/post) cannot
        # express this without contamination -- widening the lists would also flip
        # AWA -> AIZ (x17) and AWBL -> AIBR (x1), measured 2026-08-26 -- so the probe
        # rewrites the two matrix entries surgically, the way an adoption would have
        # to (a per-pair route, not a wider list).
        nv = sim.nervous
        aiz = sim.conn.select("AIZL", "AIZR")
        gc = p.neural.glucl_strength
        E = nv.E_syn.copy()
        E[np.ix_(aiz, awb)] = (1.0 - gc) * p.neural.E_exc + gc * p.neural.E_inh
        nv.E_syn = E
        nv.GE_syn = nv.G_syn * E

    def wrapped(world, nodes, *a, **k):
        rep = float(world.sample(world.repellent, nodes[0][0], nodes[0][1]))
        prior = s.rep_adapt
        I = base(world, nodes, *a, **k)
        if prior is not None and arm != "none":
            drep = rep - prior
            if arm in ("off", "offcl"):
                I[awb] += GAIN_OFF * max(0.0, -drep)
            else:
                I[awb] += GAIN_ON_T * rep + GAIN_ON_D * max(0.0, drep)
        return I

    s.sense = wrapped
    n = len(sim.body.nodes())
    dmax, t_clear = 0.0, None
    step_per = int(round(0.25 / sim.dt))
    for k in range(int(T / 0.25)):
        for _ in range(step_per):
            sim.step()
        mid = sim.body.nodes()[n // 2]
        d = float(np.hypot(mid[0] - 6.0, mid[1]))
        dmax = max(dmax, d)
        if t_clear is None and d > 8.0:
            t_clear = (k + 1) * 0.25
    mid = sim.body.nodes()[n // 2]
    return dict(seed=seed, arm=arm,
                d_final=float(np.hypot(mid[0] - 6.0, mid[1])),
                d_max=dmax, t_clear=t_clear if t_clear is not None else 999.0,
                cleared=t_clear is not None)


if __name__ == "__main__":
    arms = ("none", "off", "on", "offcl")
    jobs = [(s, a) for s in SEEDS for a in arms]
    with ProcessPoolExecutor(max_workers=min(14, os.cpu_count() or 4)) as ex:
        rows = list(ex.map(trial, jobs))
    for a in arms:
        sel = [r for r in rows if r["arm"] == a]
        print("arm %-4s  d_final %5.2f  d_max %5.2f  t_clear %6.1f  cleared %d/%d" % (
            a, np.mean([r["d_final"] for r in sel]),
            np.mean([r["d_max"] for r in sel]),
            np.mean([r["t_clear"] for r in sel]),
            sum(r["cleared"] for r in sel), len(sel)))
    for a in ("off", "on", "offcl"):
        dd = [next(r["d_final"] for r in rows if r["seed"] == s and r["arm"] == a)
              - next(r["d_final"] for r in rows if r["seed"] == s and r["arm"] == "none")
              for s in SEEDS]
        print("arm %-4s paired d_final vs none: %+0.2f  [%s]" % (
            a, np.mean(dd), " ".join("%+0.1f" % v for v in dd)))
