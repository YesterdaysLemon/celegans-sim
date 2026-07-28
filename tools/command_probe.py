"""Who, if anyone, can change the animal's mind about which way to go.

The direction decision is one number. `Senses.sense` reads the mean activation of the
forward command pool (AVB, PVC) minus the backward one (AVA, AVD, AVE) and puts the
difference through a sigmoid; everything downstream -- which cord gets the descending
drive, which proprioceptive field is engaged -- follows from that. So every sensory
behaviour that needs a reversal has to act by moving that one difference across
`gate_bias`, and the question this tool answers is whether anything can.

Three numbers decide it:

  distance   how far the difference sits from the 50/50 point.
  sigma      how much the difference fluctuates on its own, which is what a spontaneous
             reversal has to be made of. distance/sigma is the margin: a threshold sitting
             at 3 sigma is crossed roughly once an hour, one at 1.5 sigma once a minute.
  authority  how far the difference moves when a named neuron is driven with a known
             current. Divided by sigma, this is what a sensory input is actually worth.

The pools are also correlated, and that turns out to matter more than any of the gains.
Every command interneuron in this connectome is cholinergic or glutamatergic, and the
model collapses both to a 0 mV reversal, so the forward and backward pools are wired to
each other *excitatorily* -- 70 contacts backward-from-forward, 33 forward-from-backward,
plus 10 gap junctions. Two pools that excite each other rise and fall together, and their
difference is the one quantity that common drive cannot move. If the correlation is
strongly positive, no amount of gain anywhere upstream fixes the steering, because the
signal is being injected into the common mode of a circuit that only reads the
differential mode.

Run:  PYTHONPATH=. .venv/bin/python tools/command_probe.py
"""

from __future__ import annotations

import sys

import numpy as np

from tools.assays import estimate, pooled
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

SETTLE, MEASURE = 8.0, 32.0

# (label, neuron group, current in pA). The ASE rows bracket what the chemosensory
# pathway actually delivers: tools/assays.py triage measures 0.58 pA rms and 0.90 pA peak
# reaching ASE on a real lawn gradient, and the 10 pA row is well past anything
# physiological, so if the difference does not move there it will not move at all.
PROBES = [
    ("baseline",      None,             0.0),
    ("ASEL +1pA",     ("ASEL",),        1.0),
    ("ASEL +10pA",    ("ASEL",),       10.0),
    ("ASER +10pA",    ("ASER",),       10.0),
    ("AVA +5pA",      ("AVA",),         5.0),
    ("AVA +20pA",     ("AVA",),        20.0),
    ("AVB -20pA",     ("AVB",),       -20.0),
]
SEEDS = (0, 3, 7)


def _job(job):
    label, group, amount, seed = job
    p = Params()
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))

    if group is not None:
        # Connectome.group matches anatomical classes and .select matches individual
        # neurons; the probe list mixes both ("AVA" the class, "ASEL" the cell).
        idx = np.union1d(sim.conn.group(*group), sim.conn.select(*group))
        if len(idx) == 0:
            raise RuntimeError("no neurons matched %r" % (group,))
        base = sim.senses.sense

        def wrapped(*a, **k):
            I = base(*a, **k)
            I[idx] += amount
            return I

        sim.senses.sense = wrapped

    fwd_i, bwd_i = sim.senses.avb, sim.senses.ava
    dt = p.neural.dt
    for _ in range(int(SETTLE / dt)):
        sim.step()

    fwd, bwd, gate = [], [], []
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20:
            continue
        a = sim.nervous.activation()
        fwd.append(float(np.mean(a[fwd_i])))
        bwd.append(float(np.mean(a[bwd_i])))
        gate.append(sim.senses.readout["gate_forward"])

    fwd, bwd, gate = np.array(fwd), np.array(bwd), np.array(gate)
    diff = fwd - bwd
    return dict(label=label, seed=seed,
                fwd=float(fwd.mean()), bwd=float(bwd.mean()),
                fwd_sd=float(fwd.std()), bwd_sd=float(bwd.std()),
                diff=float(diff.mean()), diff_sd=float(diff.std()),
                corr=float(np.corrcoef(fwd, bwd)[0, 1]) if fwd.std() > 0 and bwd.std() > 0
                else float("nan"),
                gate=float(gate.mean()),
                crossings=int((np.diff((gate < 0.5).astype(int)) > 0).sum()))


def main():
    # procs is overridable so this can be run on whatever cores a longer job has left
    # spare, rather than competing with it for all of them.
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    jobs = [(lab, grp, amt, s) for lab, grp, amt in PROBES for s in SEEDS]
    print("COMMAND PROBE -- %d trials x %.0f s on %d cores  (estimated %.0f s)"
          % (len(jobs), SETTLE + MEASURE, procs,
             estimate(len(jobs), SETTLE + MEASURE, procs)))
    rows = pooled(_job, jobs, procs=procs)
    if not rows:
        print("  no trials completed")
        return 1

    p = Params().sensory
    agg = {}
    for r in rows:
        agg.setdefault(r["label"], []).append(r)
    f = lambda g, k: float(np.mean([x[k] for x in g]))            # noqa: E731

    base = agg.get("baseline")
    d0 = f(base, "diff") if base else float("nan")
    sd0 = f(base, "diff_sd") if base else float("nan")

    print()
    print("  probe          fwd act   bwd act   difference (sd)    gate    shift    crossings")
    for lab, _, _ in PROBES:
        g = agg.get(lab)
        if not g:
            continue
        shift = f(g, "diff") - d0
        print("  %-13s  %.3f     %.3f     %+.4f (%.4f)   %.3f   %+.4f   %d"
              % (lab, f(g, "fwd"), f(g, "bwd"), f(g, "diff"), f(g, "diff_sd"),
                 f(g, "gate"), shift, sum(x["crossings"] for x in g)))

    print()
    print("  THE MARGIN")
    print("    the gate flips when the difference falls below gate_bias = %.3f" % p.gate_bias)
    print("    resting difference          %+.4f" % d0)
    print("    distance to the boundary    %+.4f" % (d0 - p.gate_bias))
    print("    its own fluctuation (sd)     %.4f" % sd0)
    if sd0 > 0:
        print("    margin                      %5.2f sigma" % ((d0 - p.gate_bias) / sd0))

    print()
    print("  WHAT EACH INPUT IS WORTH, in units of that fluctuation")
    for lab, _, _ in PROBES:
        g = agg.get(lab)
        if not g or lab == "baseline":
            continue
        shift = f(g, "diff") - d0
        print("    %-13s %+7.3f sigma   (%.0f%% of the distance to the boundary)"
              % (lab, shift / sd0 if sd0 else float("nan"),
                 100 * shift / (p.gate_bias - d0) if d0 != p.gate_bias else float("nan")))

    print()
    print("  COMMON MODE")
    if base:
        print("    correlation between the forward and backward pools: %+.3f"
              % f(base, "corr"))
        print("    forward pool sd %.4f, backward pool sd %.4f"
              % (f(base, "fwd_sd"), f(base, "bwd_sd")))
        print()
        print("    A strongly positive correlation means the two pools move together, so")
        print("    the difference -- the only thing the decision reads -- is the component")
        print("    that common input cannot address. That is a wiring statement, not a")
        print("    gain one, and it is not fixable by turning any gain up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
