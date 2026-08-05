"""Is the wavelength blind to the medium, or merely fixed?

Every gait-modulation sweep so far has reported a wavelength span -- buffer over agar -- and
it has never moved. 1.06x, 1.01x, 1.03x across three lag budgets; 1.10x, 1.10x, 1.16x, 1.17x
across four force-velocity strengths; 1.10x with the head reflex distributed and 1.06x with it
cascaded. The animal's is **2.37x**: it opens from a 0.65 L crawl to a 1.54 L swim. Frequency
in this model has moved for many reasons and wavelength has moved for none, and nothing has
ever been aimed at it.

`SensoryParams.proprio_reach` is what sets it, and its own note already measures that it
works: reach 0.16 gives a 0.85 L wave and reach 0.10 gives 0.62 L. So this is **not** a
question about whether wavelength can be changed -- it plainly can. It is a question about
whether anything about the *medium* reaches it.

THE DISTINCTION THIS FILE EXISTS TO DRAW.

    "wavelength is stuck"          -- the mechanism that sets it is saturated or broken
    "wavelength is fixed"          -- the mechanism works fine and simply has no input
                                      from the medium

Those want completely different work. The first is a modelling failure to hunt; the second is
a missing connection to install, and a cheap one, because `proprio_reach` is already a live
knob that the dopamine pathway already modulates. Telling them apart costs one sweep.

WHAT EACH OUTCOME MEANS, fixed before the run.

  * **wavelength moves with reach, but the span stays ~1.0 at every reach** -- wavelength is
    fixed rather than stuck. It is entirely reach-set and completely medium-blind, so
    frequency and wavelength are **independent** failures needing separate mechanisms, and
    the wavelength half is a wire that was never run rather than a mechanism that does not
    work. That is the cheapest possible answer and the one I expect;
  * **the span grows with reach** -- there is latent medium-dependence in the proprioceptive
    path that a longer reach exposes, which would be a genuine lead and the first sign of
    load-dependence anywhere in this model;
  * **the frequency span moves with reach too** -- wavelength and frequency are coupled
    through the reach, and a single mechanism might fix both. That would change the plan
    more than either of the above.

A fourth possibility worth naming so it is not mistaken for the first: if wavelength barely
moves *at all* with reach in buffer while moving normally on agar, then the mechanism is
saturated at the swimming end specifically, and that is the "stuck" case after all.

Reach is swept above and below the shipped 0.16. The 0.10 end is the documented floor -- the
basal-slowing fallback -- and going far above 0.16 is uncharted, which is the point: nobody
has asked what a long reach does in water.

Run:  PYTHONPATH=. .venv/bin/python tools/reach_span.py
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

REACHES = (0.10, 0.16, 0.24, 0.32)
MEDIA = ("agar", "buffer")
ANIMAL = {"agar": (0.30, 0.65), "buffer": (1.76, 1.54)}


def _job(job):
    reach, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, sensory=dataclasses.replace(p.sensory, proprio_reach=reach))
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
    return dict(reach=reach, medium=medium, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(r, med, s) for s in SEEDS for med in MEDIA for r in REACHES]
    print("REACH SPAN -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  is the wavelength blind to the medium, or merely fixed?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["reach"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  reach   medium   n | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    for med in MEDIA:
        for rc in REACHES:
            g = agg.get((rc, med))
            mark = "  <- shipped" if rc == 0.16 else ""
            if not g:
                print("  %.2f    %-8s -- | not measured%s" % (rc, med, mark))
                continue
            print("  %.2f    %-8s %2d | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f%s"
                  % (rc, med, len(g), mean(g, "freq"), sd(g, "freq"),
                     mean(g, "wavelength"), mean(g, "twi"), mean(g, "k_rms"),
                     mean(g, "speed"), mean(g, "net_path"), mark))

    missing = [(rc, m) for m in MEDIA for rc in REACHES if (rc, m) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so what follows is not the comparison this")
        print("  file claims to make:")
        for rc, m in missing:
            print("    reach %.2f in %s: no trial returned" % (rc, m))
        for k, n in short:
            print("    reach %.2f in %s: %d of %d seeds" % (k[0], k[1], n, len(SEEDS)))

    print("\n  DOES REACH MOVE THE WAVELENGTH, AND DOES THE MEDIUM REACH IT?")
    print("  The animal: 0.65 L on agar, 1.54 L in buffer -- a span of %.2fx."
          % (ANIMAL["buffer"][1] / ANIMAL["agar"][1]))
    w_spans, f_spans, moved = [], [], {}
    for rc in REACHES:
        a, b = agg.get((rc, "agar")), agg.get((rc, "buffer"))
        if not a or not b:
            continue
        wa, wb = mean(a, "wavelength"), mean(b, "wavelength")
        fa, fb = mean(a, "freq"), mean(b, "freq")
        w_spans.append((rc, wb / max(wa, 1e-9)))
        f_spans.append((rc, fb / max(fa, 1e-9)))
        print("  reach %.2f: wavelength %.2f -> %.2f L, span %.2fx  |  freq span %.2fx"
              % (rc, wa, wb, wb / max(wa, 1e-9), fb / max(fa, 1e-9)))

    for med in MEDIA:
        lo, hi = agg.get((REACHES[0], med)), agg.get((REACHES[-1], med))
        if lo and hi:
            moved[med] = mean(hi, "wavelength") / max(mean(lo, "wavelength"), 1e-9)
            print("  %-8s wavelength across the reach sweep: %.2f -> %.2f L (%.2fx)"
                  % (med, mean(lo, "wavelength"), mean(hi, "wavelength"), moved[med]))

    if len(w_spans) >= 2 and len(moved) == len(MEDIA):
        w_lo, w_hi = w_spans[0][1], w_spans[-1][1]
        f_lo, f_hi = f_spans[0][1], f_spans[-1][1]
        print("\n  VERDICT")
        works_agar = moved["agar"] > 1.25
        works_buffer = moved["buffer"] > 1.25
        if works_agar and not works_buffer:
            print("  Reach moves the wavelength on agar (%.2fx) and barely in buffer (%.2fx)."
                  % (moved["agar"], moved["buffer"]))
            print("  The mechanism is saturated at the swimming end specifically -- the")
            print("  wavelength is STUCK there, not merely fixed, and that is a modelling")
            print("  failure to hunt rather than a wire to run.")
        elif abs(w_hi - w_lo) < 0.20 and works_agar and works_buffer:
            print("  Reach moves the wavelength in both media (%.2fx on agar, %.2fx in"
                  % (moved["agar"], moved["buffer"]))
            print("  buffer) and the span stays flat: %.2fx to %.2fx. So the wavelength is"
                  % (w_lo, w_hi))
            print("  FIXED, not stuck -- the mechanism works and simply has no input from")
            print("  the medium. Frequency and wavelength are independent failures, and the")
            print("  wavelength half is a wire that was never run rather than a mechanism")
            print("  that does not work. Making proprio_reach load-dependent is the change.")
        elif w_hi - w_lo >= 0.20:
            print("  The wavelength span grows with reach, %.2fx to %.2fx. There is latent"
                  % (w_lo, w_hi))
            print("  medium-dependence in the proprioceptive path that a longer reach")
            print("  exposes -- the first sign of load-dependence anywhere in this model.")
        else:
            print("  Reach does not move the wavelength much in either medium (%.2fx, %.2fx),"
                  % (moved["agar"], moved["buffer"]))
            print("  which contradicts the table under SensoryParams.proprio_reach. Read the")
            print("  kymograph before believing anything else here.")

        if abs(f_hi - f_lo) >= 0.20:
            print("\n  And the FREQUENCY span moved with reach too, %.2fx to %.2fx, so the two"
                  % (f_lo, f_hi))
            print("  are coupled through the reach and one mechanism might fix both.")
        else:
            print("\n  The frequency span did not move with reach (%.2fx to %.2fx), which is"
                  % (f_lo, f_hi))
            print("  the independence the second reading above describes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
