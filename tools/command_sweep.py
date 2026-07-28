"""Can the command layer be made to change its mind, and does locomotion survive it?

`tools/command_probe.py` measured the problem on the shipped model: the forward and
backward command pools correlate at +0.76, the direction difference sits 3.81 standard
deviations from its own decision boundary, and ASE driven seventeen times harder than the
real chemosensory pathway ever drives it moves that difference by 0.04 sigma. So nothing
sensory can reach the decision, and the animal never reverses.

This sweep is what sets the parameters added for that, all of which are zero on the
shipped model. See NeuralParams for the biology; in short, `command_cross_inhibition`
retargets the synapses between the two pools onto an inhibitory receptor,
`command_adapt_ratio` makes the winning side tire, and `command_ca_ratio` (on the cells
named by `command_ca_classes`, placed by `command_ca_offset`) gives it the regenerative
limb that lets a state persist.

Scored on both halves of the question at once, because either alone is easy to fake. A
model that reverses constantly and cannot crawl is not progress, so every row carries the
locomotion numbers next to the behavioural ones.

Two columns do most of the work, and both were added after a sweep that lacked them read
as a success:

  dur s    mean episode length. This is what separates a reversal from a threshold
           flicker. Adaptation alone reaches thirty reversals a minute with every episode
           lasting 0.07 s, which is one fifteenth of an undulation cycle and is not an
           animal reversing.
  margin   distance from the decision boundary in units of the difference's own standard
           deviation. Rows measured at different `gate_bias` are not comparable without
           it, because changing the dynamics changes the spread the threshold sits in.

`JOBS` is an explicit list rather than a product, because the useful comparisons are
specific pairings rather than a grid. Edit it and re-run; each pass is about four minutes.

Run:  PYTHONPATH=. .venv/bin/python tools/command_sweep.py
"""
from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import estimate, pooled
from tools.diagnose_loop import travelling_index
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 10.0, 60.0
SEEDS = (0, 3, 7)

# The pairings below are the ones left standing after five passes; the full history and
# the numbers are in NEXT.md under day six. In short: cross-inhibition never moved the
# correlation, adaptation alone only ever produced 0.07 s flickers, and regenerative
# calcium supplies both missing properties -- correlation +0.69 -> -0.04 and episodes of
# seconds -- while costing about half the locomotion. These rows separate the two
# candidate explanations for that cost, neither of which survived: holding gate_bias so
# the animal never reverses at all, and moving the calcium off AVB (which poises the B
# cord through 58 gap contacts) onto AVA alone (whose 102 contacts land on an A cord that
# carries no regenerative conductance, so it is poising nothing).
# Latched vs graded: does separating "which cord" from "how much" free the decision?
JOBS = [
    (False, 0.00, 0.09, "graded (shipped)"),
    (True,  0.01, 0.12, "latch b=0.12 h=0.01"),
    (True,  0.02, 0.12, "latch b=0.12 h=0.02"),
    (True,  0.04, 0.12, "latch b=0.12 h=0.04"),
    (True,  0.01, 0.14, "latch b=0.14 h=0.01"),
    (True,  0.02, 0.14, "latch b=0.14 h=0.02"),
    (True,  0.04, 0.14, "latch b=0.14 h=0.04"),
    (True,  0.01, 0.15, "latch b=0.15 h=0.01"),
    (True,  0.02, 0.15, "latch b=0.15 h=0.02"),
    (True,  0.04, 0.15, "latch b=0.15 h=0.04"),
    (True,  0.01, 0.16, "latch b=0.16 h=0.01"),
    (True,  0.02, 0.16, "latch b=0.16 h=0.02"),
    (True,  0.04, 0.16, "latch b=0.16 h=0.04"),
]


def _job(job):
    latched, hyst, bias, label, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, gate_latched=latched, gate_hysteresis=hyst, gate_bias=bias))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    fwd_i, bwd_i = sim.senses.avb, sim.senses.ava
    dt = p.neural.dt

    for _ in range(int(WARMUP / dt)):
        sim.step()

    start = sim.body.centroid().copy()
    fwd, bwd, gate, ks = [], [], [], []
    path, prev = 0.0, start.copy()
    for i in range(int(MEASURE / dt)):
        sim.step()
        if i % 20:
            continue
        a = sim.nervous.activation()
        fwd.append(float(np.mean(a[fwd_i])))
        bwd.append(float(np.mean(a[bwd_i])))
        gate.append(sim.senses.readout["gate_forward"])
        ks.append(sim.body.curvature().copy())
        c = sim.body.centroid()
        path += float(np.linalg.norm(c - prev))
        prev = c.copy()

    fwd, bwd, gate, K = np.array(fwd), np.array(bwd), np.array(gate), np.array(ks)
    diff = fwd - bwd
    sd = float(diff.std())
    net = float(np.linalg.norm(sim.body.centroid() - start))
    back = (gate < 0.5).astype(int)
    rev = int((np.diff(back) > 0).sum())
    # Mean episode length. This is what separates a reversal from a flicker: a real one
    # lasts seconds and covers ground, while a difference sitting on top of its own
    # threshold crosses constantly and goes nowhere.
    sample = MEASURE / max(len(gate), 1)
    rev_dur = float(back.sum()) * sample / rev if rev else float("nan")

    return dict(
        latched=latched, hyst=hyst, bias=bias, label=label, seed=seed,
        fwd=float(fwd.mean()), bwd=float(bwd.mean()),
        corr=float(np.corrcoef(fwd, bwd)[0, 1]) if fwd.std() > 0 and bwd.std() > 0
        else float("nan"),
        diff=float(diff.mean()), diff_sd=sd,
        margin=(float(diff.mean()) - bias) / sd if sd > 0 else float("nan"),
        gate=float(gate.mean()), rev_rate=rev * 60.0 / MEASURE, rev_dur=rev_dur,
        frac_rev=float(back.mean()),
        speed=net / MEASURE, net_path=net / max(path, 1e-9),
        twi=travelling_index(K), k_rms=float(np.sqrt((K ** 2).mean())),
    )


def main():
    jobs = [(la, h, b, lb, s) for la, h, b, lb in JOBS for s in SEEDS]
    print("COMMAND SWEEP -- %d trials x %.0f s  (estimated %.0f s)"
          % (len(jobs), WARMUP + MEASURE, estimate(len(jobs), WARMUP + MEASURE)))
    rows = pooled(_job, jobs)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["label"],), []).append(r)
    f = lambda g, k: float(np.nanmean([x[k] for x in g]))         # noqa: E731

    print()
    print("  configuration          |  corr   difference   margin   rev/min   dur s  %rev |"
          "  speed   net/path    TWI    k_rms")
    for key in sorted(agg):
        g = agg[key]
        mark = ""
        print("  %-22s | %+.3f   %+.4f     %5.2f    %5.2f   %5.2f  %4.1f |"
              "  %.4f   %.3f    %+.3f  %5.2f%s"
              % (key[0], f(g, "corr"), f(g, "diff"), f(g, "margin"),
                 f(g, "rev_rate"), f(g, "rev_dur"), 100 * f(g, "frac_rev"),
                 f(g, "speed"), f(g, "net_path"), f(g, "twi"), f(g, "k_rms"), mark))

    print()
    print("  want: reversals at 3.2-3.5 /min (Zhao et al. 2003) with forward locomotion")
    print("  held near 0.246 mm/s, net/path 0.905 and TWI +0.78. A margin near 1.5 sigma")
    print("  is what makes a reversal an ordinary event rather than a rare accident, and a")
    print("  correlation near zero or below is what gives a sensory neuron any purchase on")
    print("  the decision at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
