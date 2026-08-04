"""Does giving the muscle a force-velocity curve widen the gait-modulation span?

`MediumParams` records the diagnosis this is aimed at. The loop's frequency is set by its
total lag; every element of that lag is a fixed constant except the body's drag response; and
by K = 9 that one term has become small against the rest. So the frequency saturates, the
model spans 1.29x across the drag continuum, and the animal spans 5.87x.

The fix cannot be a bigger gain on an existing term. It has to be a **second load-dependent
element**, and muscle force-velocity is the obvious physiological candidate: real muscle
produces less force the faster it shortens (Hill 1938), and how fast it shortens depends on
how hard the medium is resisting.

THE ARGUMENT AGAINST IT, WHICH IS WHY THIS IS A MEASUREMENT AND NOT A PATCH.

Force-velocity derates on *shortening rate*, and the shortening rate is a property of the
gait rather than of the medium directly. This model's gait is currently similar at both ends
-- kappa_rms 4.45 on agar and 4.39 in buffer, at 0.66 and 0.83 Hz -- so `d(kappa)/dt` is
roughly 18 and 23 /(mm*s) respectively. If the derating applies about equally at both ends it
cancels out of the span and buys nothing. The term is also damping-like, and damping is lag,
so it could as easily *narrow* the span by making the fixed part of the loop's lag larger.

Both of those are real possibilities and neither is settled by argument. Hence the sweep.

WHAT EACH OUTCOME MEANS, fixed before the run.

  * **span widens with falling vmax** -- the second load-dependent element is what was
    missing, force-velocity supplies it, and the next question is how much of the animal's
    5.87x it can reach before the gait stops looking like a gait;
  * **span flat** -- the derating cancels out of the span exactly as feared. Force-velocity
    is still more faithful muscle than none, but it is not the gait-modulation mechanism, and
    the load-dependence has to come from proprioception instead;
  * **span narrows** -- the term is behaving as added fixed lag, which is the failure mode
    the diagnosis predicts for anything that does not actually vary with load. That would be
    a clean confirmation of the diagnosis by a route nobody wanted.

`fv_vmax = 0` is off and is bit-identical to the model without this code, verified on nodes,
membrane potentials and muscle tension. The other values bracket the scale: an animal at
kappa_rms 4.4 and 0.7 Hz sweeps roughly 19 /(mm*s), so 100 barely touches it, 20 is
comparable, and 8 makes it dominant.

Nothing is adopted here and nothing is ported to the runtime.

Run:  PYTHONPATH=. .venv/bin/python tools/force_velocity.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 30.0
SEEDS = (0, 3, 7)

# 0 is off. The rest bracket the characteristic shortening rate the gait actually reaches.
VMAXES = (0.0, 100.0, 20.0, 8.0)
MEDIA = ("agar", "buffer")
ANIMAL = {"agar": (0.30, 0.65), "buffer": (1.76, 1.54)}


def _job(job):
    vmax, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, muscle=dataclasses.replace(p.muscle, fv_vmax=vmax))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)
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

    r = analyse(sim, seconds=MEASURE)
    return dict(vmax=vmax, medium=medium, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(v, med, s) for s in SEEDS for med in MEDIA for v in VMAXES]
    print("FORCE-VELOCITY -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  does a second load-dependent element widen the span?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["vmax"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  vmax    medium   n | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    for med in MEDIA:
        for v in VMAXES:
            g = agg.get((v, med))
            label = "off" if v == 0.0 else "%.0f" % v
            mark = "  <- shipped" if v == 0.0 else ""
            if not g:
                print("  %-6s  %-8s -- | not measured%s" % (label, med, mark))
                continue
            print("  %-6s  %-8s %2d | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f%s"
                  % (label, med, len(g), mean(g, "freq"), sd(g, "freq"),
                     mean(g, "wavelength"), mean(g, "twi"), mean(g, "k_rms"),
                     mean(g, "speed"), mean(g, "net_path"), mark))

    missing = [(v, m) for m in MEDIA for v in VMAXES if (v, m) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so the spans below are not the comparison")
        print("  this file claims to make:")
        for v, m in missing:
            print("    vmax %.0f in %s: no trial returned" % (v, m))
        for k, n in short:
            print("    vmax %.0f in %s: %d of %d seeds" % (k[0], k[1], n, len(SEEDS)))

    print("\n  SPAN AGAINST FORCE-VELOCITY STRENGTH")
    print("  The animal spans %.2fx in frequency and %.2fx in wavelength."
          % (ANIMAL["buffer"][0] / ANIMAL["agar"][0],
             ANIMAL["buffer"][1] / ANIMAL["agar"][1]))
    spans = []
    for v in VMAXES:
        a, b = agg.get((v, "agar")), agg.get((v, "buffer"))
        if not a or not b:
            continue
        fa, fb = mean(a, "freq"), mean(b, "freq")
        wa, wb = mean(a, "wavelength"), mean(b, "wavelength")
        spans.append((v, fb / max(fa, 1e-9)))
        print("  vmax %-5s %.3f -> %.3f Hz, span %.2fx  |  wavelength %.2f -> %.2f L, %.2fx"
              % ("off" if v == 0.0 else "%.0f" % v, fa, fb, fb / max(fa, 1e-9),
                 wa, wb, wb / max(wa, 1e-9)))

    if len(spans) >= 2:
        base = spans[0][1]
        best_v, best = max(spans[1:], key=lambda s: s[1]) if len(spans) > 1 else (None, base)
        print("\n  VERDICT")
        if best - base > 0.20:
            print("  The span widens from %.2fx (off) to %.2fx at vmax %.0f. Force-velocity"
                  % (base, best, best_v))
            print("  supplies the second load-dependent element the diagnosis said was")
            print("  missing. Next question is how much of the animal's 5.87x it reaches")
            print("  before the gait stops looking like a gait -- read TWI and net speed.")
        elif abs(best - base) <= 0.20:
            print("  The span goes %.2fx to %.2fx, which is flat. The derating cancels out"
                  % (base, best))
            print("  of the span, as the argument against this predicted: shortening rate is")
            print("  a property of the gait and the gait is similar at both ends. More")
            print("  faithful muscle, not the gait-modulation mechanism. Proprioception next.")
        else:
            print("  The span narrows, %.2fx to %.2fx. The term is acting as added fixed lag"
                  % (base, min(s for _, s in spans[1:])))
            print("  rather than as load-dependence, which is the failure mode the diagnosis")
            print("  predicts for anything that does not actually vary with load. A clean")
            print("  confirmation of the diagnosis by a route nobody wanted.")

        print("\n  And what it cost the gait, because a span is worthless if the animal")
        print("  stopped swimming to get it:")
        for med in MEDIA:
            off, on = agg.get((0.0, med)), agg.get((VMAXES[-1], med))
            if off and on:
                print("    %-8s TWI %+.3f -> %+.3f, net %.4f -> %.4f mm/s, kappa_rms %.2f -> %.2f"
                      % (med, mean(off, "twi"), mean(on, "twi"), mean(off, "speed"),
                         mean(on, "speed"), mean(off, "k_rms"), mean(on, "k_rms")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
