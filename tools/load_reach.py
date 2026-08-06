"""Does letting the animal set its own reach open the wavelength span?

This is the measurement the whole chain was built for, and it is the first one in this project
where the animal changes its own gait in response to the medium rather than being told to.

WHAT CAME BEFORE, IN THE ORDER IT HAPPENED.

`tools/reach_span.py` found that **both of the animal's wavelengths are already reachable** --
0.60 L on agar at reach 0.10 against its 0.65 crawl, and 1.30 L in buffer at reach 0.24
against its 1.54 swim. Nothing was saturated and nothing was missing from the mechanism. What
was missing was the *selection*: something to tell the reach which medium the animal was in.

`tools/load_signal.py` then asked whether anything in the animal's own geometry could supply
that, because the answer could have been no -- this nervous system senses curvature and
nothing else. It found one signal that works: the phase lag between the moment a muscle
applies and the bend that follows, 47.9 ms on agar against 1.1 ms in buffer, and **the only
quantity measured in this project that does not saturate by K = 9.**

`SensoryParams.load_detect_gain` reads it, as a quadrature phase detector on each cell's own
output against its own local curvature, and blends between receptive-field banks. Measured:

    medium    detector   swimming fraction   effective reach
    agar        0.1541         0.143              0.117
    viscous     0.0131         0.958              0.233
    buffer      0.0082         0.983              0.237

So the animal is choosing 0.117 on agar and 0.237 in buffer, which is the pair `reach_span.py`
measured the two wavelengths at. **That is not the result.** The reach is an input; the
wavelength is what has to move, and nothing so far has measured whether it follows when the
reach is being driven by a closed loop rather than set by hand.

THE REASON THAT IS A REAL QUESTION AND NOT A FORMALITY.

Every number above was measured with the reach *fixed*. Here it is inside the loop: the reach
sets the wavelength, the wavelength sets the phase the detector reads, and the detector sets
the reach. A closed loop can settle somewhere neither end predicts, oscillate between the two
banks, or sit at a compromise that is worse than either. `reach_span.py` also found the gait
noticeably fragile away from the shipped 0.16 -- frequency sd 0.012 there against 0.229 and
0.295 at other reaches -- so a term that moves the animal off it at runtime is exactly the
kind of thing that could find that fragility.

HOW TO READ IT, FIXED BEFORE THE RUN.

Paired by seed, both arms, three media. The comparison is the **wavelength span**, buffer over
agar, because that is the quantity gait modulation is about and neither end says anything on
its own. The animal spans 2.37x. Every configuration this project has tried spans 1.0 to 1.2x.

  * **the span opens towards 2.37x and the gait survives** -- the mechanism works and this is
    the first real gait modulation in the model. Then it needs `tools/scorecard.py` and
    `tools/ethogram.py` against the frozen baseline before adoption, and a port to the runtime;
  * **the span opens and the gait degrades** -- the wavelength was bought rather than earned.
    Read the travelling index and the net speed in both media before believing the span; a
    worm that has stopped swimming has whatever wavelength you like;
  * **the span does not open** -- the reach moves, and the wavelength does not follow it inside
    the loop the way it did when set by hand. That would be a genuine surprise and would say
    the open-loop table in `reach_span.py` does not survive being closed;
  * **the animal falls apart in one medium** -- the bistability warning cashing in. Look at the
    per-seed scatter rather than the mean.

Frequency is reported beside it. Nothing in this project has moved the frequency span past
1.4x and this mechanism does not target it, so a frequency result either way is information
rather than the point.

Run:  PYTHONPATH=. .venv/bin/python tools/load_reach.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import paired, pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 30.0
SEEDS = (0, 3, 7)

# Off against on. The off arm is bit-identical to the model without this code, which
# `tests/test_load_reach.py` pins, so it is the shipped animal rather than an approximation.
ARMS = (("off", 0.0), ("on ", 1.0))

# Three media, because the middle one is where every other mechanism in this project has been
# found to saturate. K = 40, 9, 1.58.
MEDIA = ("agar", "viscous", "buffer")
K = {"agar": 40.0, "viscous": 9.0, "buffer": 1.58}

# Fang-Yen et al. 2010: frequency Hz, wavelength L.
ANIMAL = {"agar": (0.30, 0.65), "buffer": (1.76, 1.54)}


def _job(job):
    label, gain, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, sensory=dataclasses.replace(p.sensory, load_detect_gain=gain))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    # Longer than the usual 6 s settle: the detector's own averages run at `load_tau` through
    # two stages, so the reach is still moving for several seconds after the gait has settled.
    # Measuring across that transient would report a wavelength the animal was on its way out
    # of rather than one it had chosen.
    sim.run(20.0)
    start = sim.body.centroid().copy()
    t0 = sim.t
    prev, path = start.copy(), 0.0
    every = max(1, int(round(0.05 / sim.dt)))
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    net = float(np.linalg.norm(sim.body.centroid() - start))
    span = sim.t - t0

    # What the animal actually chose, so the table can show the mechanism working rather than
    # leaving it to be inferred from the wavelength it was supposed to produce.
    sw = float(sim.senses._load_swim)
    sp = sim.p.sensory
    crawl = (0.5 - sw) * 2.0 if sw < 0.5 else 0.0
    swim = (sw - 0.5) * 2.0 if sw >= 0.5 else 0.0
    reach = ((1.0 - crawl - swim) * sp.proprio_reach + crawl * sp.proprio_reach_food
             + swim * sp.proprio_reach_swim) if gain > 0.0 else sp.proprio_reach

    r = analyse(sim, seconds=MEASURE)
    wl = r["wavelength"]
    return dict(label=label, gain=gain, medium=medium, seed=seed, reach=reach,
                freq=r["freq"], wavelength=wl,
                # Averaged as wavenumber and inverted, because wavelength is 2*pi/|slope| and
                # diverges as a wave flattens towards standing -- one near-standing seed would
                # otherwise make a cell's mean meaningless. See tools/reach_span.py.
                wavenumber=(1.0 / wl if np.isfinite(wl) and wl > 0 else 0.0),
                twi=r["twi"], k_rms=r["kappa_rms"], power=r.get("power", float("nan")),
                speed=net / span, net_path=net / max(path, 1e-9))


def main():
    jobs = [(lab, g, med, s) for s in SEEDS for med in MEDIA for lab, g in ARMS]
    print("LOAD-DEPENDENT REACH -- %d trials, %.0f s each, %d seeds"
          % (len(jobs), MEASURE, len(SEEDS)))
    print("  does letting the animal choose its own reach open the wavelength span?\n")
    rows = pooled(_job, jobs, procs=8, timeout=10800)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["label"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  arm  medium   K      n | reach | freq Hz         wavelen  TWI     net mm/s  n/p")
    for lab, _ in ARMS:
        for med in MEDIA:
            g = agg.get((lab, med))
            if not g:
                print("  %s  %-8s %5.2f  -- | not measured" % (lab, med, K[med]))
                continue
            print("  %s  %-8s %5.2f %2d | %.3f | %6.3f +-%.3f  %6.2f  %+.3f  %.4f  %.2f"
                  % (lab, med, K[med], len(g), mean(g, "reach"), mean(g, "freq"),
                     sd(g, "freq"), mean(g, "wavelength"), mean(g, "twi"),
                     mean(g, "speed"), mean(g, "net_path")))

    missing = [(lab, med) for lab, _ in ARMS for med in MEDIA if (lab, med) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so the spans below are not the paired")
        print("  comparison this file claims to make:")
        for c in missing:
            print("    %s in %s: no trial returned" % c)
        for k, n in short:
            print("    %s in %s: %d of %d seeds" % (k[0], k[1], n, len(SEEDS)))

    print("\n  WAVELENGTH SPAN, buffer over agar, per seed and then averaged")
    print("  The animal spans %.2fx. Everything this project has tried spans 1.0 to 1.2x."
          % (ANIMAL["buffer"][1] / ANIMAL["agar"][1]))
    w_span, f_span = {}, {}
    for lab, _ in ARMS:
        a, b = agg.get((lab, "agar")), agg.get((lab, "buffer"))
        km, ksd, n = paired(a, b, "wavenumber")
        fm, fsd, _ = paired(a, b, "freq")
        if n < len(SEEDS) or not np.isfinite(km) or km <= 0:
            print("  %s wavelength span: only %d of %d seeds paired -- withheld"
                  % (lab, n, len(SEEDS)))
            continue
        # k_buffer/k_agar is the reciprocal of the wavelength ratio, and stays finite when a
        # wave goes standing. The sd is carried across the inversion to first order.
        w_span[lab] = (1.0 / km, ksd / (km * km))
        f_span[lab] = (fm, fsd)
        print("  %s wavelength %.2f +-%.2fx   |  frequency %.2f +-%.2fx   (n=%d)"
              % (lab, w_span[lab][0], w_span[lab][1], fm, fsd, n))

    if len(w_span) < len(ARMS):
        print("\n  Both arms are needed for a verdict and only one is complete.")
        return 1

    off, on = w_span["off"], w_span["on "]
    scatter = max(off[1], on[1])
    target = ANIMAL["buffer"][1] / ANIMAL["agar"][1]
    print("\n  VERDICT")
    print("  wavelength span %.2f +-%.2fx off -> %.2f +-%.2fx on, seed scatter %.2f"
          % (off[0], off[1], on[0], on[1], scatter))

    # Read against the scatter rather than against a bare threshold, because this project has
    # spent a day discovering that its spans carry +-0.44 and nobody was printing it.
    opened = (on[0] - off[0]) > max(0.20, 2.0 * scatter)
    gait_ok = True
    costs = []
    for med in MEDIA:
        a, b = agg.get(("off", med)), agg.get(("on ", med))
        if not a or not b:
            continue
        dt_, _, _ = paired(a, b, "twi", op="diff")
        ds, _, _ = paired(a, b, "speed", op="diff")
        costs.append((med, mean(a, "twi"), mean(b, "twi"), mean(a, "speed"), mean(b, "speed")))
        # A quarter of the travelling index is the line between "a different gait" and "not a
        # gait". Set here rather than after looking at the number.
        if np.isfinite(dt_) and dt_ < -0.25:
            gait_ok = False

    if opened and gait_ok:
        print("  The span OPENS, by more than the seeds disagree, and the wave survives it.")
        print("  That is the first gait modulation in this model that the animal produces")
        print("  for itself. It reaches %.0f%% of the animal's %.2fx, from %.0f%% before."
              % (100.0 * (on[0] - 1.0) / (target - 1.0), target,
                 100.0 * (off[0] - 1.0) / (target - 1.0)))
        print("  Before adoption: tools/scorecard.py and tools/ethogram.py against the frozen")
        print("  baseline on identical seeds, then the port to wasm/assembly/index.ts.")
    elif opened:
        print("  The span opens and the wave does not survive it -- the travelling index")
        print("  falls by more than a quarter somewhere. The wavelength was bought rather")
        print("  than earned, and a worm that has stopped swimming has whatever wavelength")
        print("  you like. Not adoptable in this form.")
    else:
        print("  The span does NOT open: %.2f -> %.2f against a scatter of %.2f."
              % (off[0], on[0], scatter))
        print("  The reach moves -- the table above shows it -- and the wavelength does not")
        print("  follow it inside the loop the way it did when the reach was set by hand in")
        print("  tools/reach_span.py. That is a real surprise and it says the open-loop table")
        print("  does not survive being closed. Look at the per-seed scatter first.")

    print("\n  And what it cost, because a span is worthless if the animal stopped swimming:")
    for med, twi_a, twi_b, sp_a, sp_b in costs:
        print("    %-8s TWI %+.3f -> %+.3f, net %.4f -> %.4f mm/s"
              % (med, twi_a, twi_b, sp_a, sp_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
