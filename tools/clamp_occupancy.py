"""The clamp experiment's instrument: how much of the cycle the cord spends on the rail.

`worm/params.py` documents (at v_clamp) that motor neurons under strong proprioceptive
drive reach the lower rail at the extremes of each cycle, and calls it saturation rather
than instability. H2 in the research log says the saturation is an artefact of injecting
*current* where the animal has *channels*, and `SensoryParams.proprio_conductance` is
the switch that tests it. This measures what the switch actually changes:

  occupancy   per A/B motor neuron, the fraction of sampled steps its voltage sits
              within 0.5 mV of either v_clamp rail, averaged over the pool -- reported
              separately for the B (forward) and A (backward) classes, and hi/lo rails.
  gait        the same run's frequency, wavelength, TWI, curvature, dorsoventral
              antagonism, direction and net speed, from tools.diagnose_loop.analyse --
              because an occupancy number bought by breaking the gait is worthless.

Modes: `current` is the shipped animal; a bare number is a proprio_conductance in nS
(current gain zeroed by the mode switch itself -- the policy replaces, not supplements).

Run:  PYTHONPATH=. .venv/bin/python tools/clamp_occupancy.py current 5 10 20 40
      (each arm runs SEEDS x MEASURE s; ~a minute a trial, parallel)

THE RECORD (both sweeps 2026-08-16, seeds 0/1/3, agar). First, the excitatory-only cut:

  mode       B@lo   B@hi   A@lo   A@hi |  freq  wave    twi dvcorr  k_rms    mm/s
  current      0%     0%     0%     0% |  0.68  0.84  +0.87  -0.73   4.45   0.304
  2..80 nS     0%     0%     0%     0% |  0.66  0.79  +0.65  -0.06..-0.29  ~3.1   ~0.19

H2's premise is NULL at shipped defaults -- the cord pools do not occupy the rail --
and rectifying away the inhibitory half collapsed the antagonism: the signed current's
hyperpolarising half was real push-pull. Second, with the reciprocal-inhibition arm:

  mode       B@lo   B@hi   A@lo   A@hi |  freq  wave    twi dvcorr  k_rms    mm/s
  current      0%     0%     0%     0% |  0.68  0.84  +0.87  -0.73   4.45   0.304
  5            0%     0%     0%     0% |  0.67  0.79  +0.90  -0.81   4.43   0.361
  10           0%     0%     0%     0% |  0.68  0.78  +0.91  -0.82   4.57   0.325
  20..80      0%     0%     0%     0% |  0.68  0.75  +0.90  -0.82   4.66   ~0.30

The channel translation matches or beats the current on every guardrail once both
halves are kept, plateauing above ~10 nS (the tanh saturates the drive, so g stops
mattering). 5 nS is the speed optimum of this sweep.

TRACK A: this is reference-worm physiology. The measurement decides nothing by itself;
adoption of a conductance default is a separate decision against reference evidence.
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

SETTLE = 6.0
MEASURE = 30.0
SEEDS = (0, 1, 3)
RAIL_EPS = 0.5          # mV: "on the rail" means within this of v_clamp


def _job(job):
    mode, seed = job
    p = Params()
    if mode != "current":
        p = dataclasses.replace(
            p, sensory=dataclasses.replace(p.sensory, proprio_conductance=float(mode)))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(SETTLE)

    b_pool = np.unique(np.concatenate((sim.senses.db, sim.senses.vb)))
    a_pool = np.unique(np.concatenate((sim.senses.da, sim.senses.va)))
    lo, hi = p.neural.v_clamp
    every = max(1, int(round(0.01 / sim.dt)))
    counts = {"b_hi": 0.0, "b_lo": 0.0, "a_hi": 0.0, "a_lo": 0.0}
    samples = 0
    start = sim.body.centroid().copy()
    t0 = sim.t
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            V = sim.nervous.V
            counts["b_hi"] += float(np.mean(V[b_pool] >= hi - RAIL_EPS))
            counts["b_lo"] += float(np.mean(V[b_pool] <= lo + RAIL_EPS))
            counts["a_hi"] += float(np.mean(V[a_pool] >= hi - RAIL_EPS))
            counts["a_lo"] += float(np.mean(V[a_pool] <= lo + RAIL_EPS))
            samples += 1
    speed = float(np.linalg.norm(sim.body.centroid() - start)) / (sim.t - t0)

    r = analyse(sim, seconds=MEASURE)
    out = dict(mode=str(mode), seed=seed, speed=speed,
               freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
               k_rms=r["kappa_rms"], k_max=r["kappa_max"], dv_corr=r["dv_corr"],
               direction=r["direction"])
    for k, v in counts.items():
        out[k] = v / max(samples, 1)
    return out


def main(argv):
    modes = argv or ["current"]
    jobs = [(m, s) for m in modes for s in SEEDS]
    print("CLAMP OCCUPANCY -- %d seeds x %.0f s per arm, rail = within %.1f mV of "
          "v_clamp\n" % (len(SEEDS), MEASURE, RAIL_EPS))
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1
    print("  %-8s %6s %6s %6s %6s | %5s %5s %6s %6s %6s %7s  %s"
          % ("mode", "B@lo", "B@hi", "A@lo", "A@hi",
             "freq", "wave", "twi", "dvcorr", "k_rms", "mm/s", "direction"))
    for m in modes:
        got = [r for r in rows if r["mode"] == str(m)]
        if not got:
            print("  %-8s all seeds failed" % m)
            continue
        col = lambda k: np.array([r[k] for r in got], dtype=float)
        d = [r["direction"] for r in got]
        print("  %-8s %5.0f%% %5.0f%% %5.0f%% %5.0f%% | %5.2f %5.2f %+6.2f %+6.2f "
              "%6.2f %7.3f  %d/%d fwd"
              % (m, 100 * col("b_lo").mean(), 100 * col("b_hi").mean(),
                 100 * col("a_lo").mean(), 100 * col("a_hi").mean(),
                 col("freq").mean(), col("wavelength").mean(), col("twi").mean(),
                 col("dv_corr").mean(), col("k_rms").mean(), col("speed").mean(),
                 d.count("head->tail"), len(d)))
    print("\n  Track A note: occupancy says where the voltage lives, not which animal")
    print("  is right. Adoption is a separate decision against reference evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
