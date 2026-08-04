"""Does the head cascade's phase follow the mechanical load, the way a fixed delay cannot?

This is the test the cascade was built for, and until it runs the cascade is only a better
gait for the same price.

WHAT IS BEING ASKED, AND WHY IT IS NOT THE SAME QUESTION AS THE LAST ONE.

`tools/head_cascade.py` established that four first-order stages of 0.125 s in series reach
the shipped undulation frequency with `head_delay = 0`, and improve the travelling wave, the
net speed and the path straightness while doing it. That is a result about *one* medium.

The reason to want the cascade was never the frequency on agar. It was the shape of the
phase. A pure transport delay contributes `2*pi*f*tau` -- exactly linear in frequency, the
same phase at every operating point -- so it pins the loop's crossover wherever it was fitted
regardless of what the medium does to the mechanical load. A cascade of N lags contributes
`N*arctan(w*tau/N)`, which saturates: its phase depends on where the loop is running, so the
crossover can move when the load does. That is the mechanism gait modulation needs, and it
has been argued in this repository for a long time without being measured.

THE NUMBER TO BEAT.

Fang-Yen et al. (2010) walked a real animal through the whole continuum by thickening the
fluid around it, and nothing about its nervous system changed between the ends -- only the
drag anisotropy K, which is `c_normal / c_tangential` and is the entire story of gait
modulation. The animal goes from a **0.30 Hz** crawl on agar (K = 40) to a **1.76 Hz** swim
in buffer (K = 1.58): a span of **5.9x**.

The shipped model manages 0.66 -> 0.85 Hz, a span of **1.29x**. The direction is right, which
it was not for a long time; the magnitude is four and a half times short, and NEXT.md puts
that shortfall on the critical path for the omega turn rather than beside it, because the
turn needs speed and tightness together and the tight end is slow for this same reason.

HOW TO READ THE RESULT, DECIDED BEFORE IT RUNS.

The comparison is the *span*, not any single frequency, and it is paired: both arms see the
same three media, the same three seeds, the same everything except the head reflex. Three
outcomes and what each means:

  * the cascade's span is materially wider than the shipped model's -- the mechanism works,
    and `head_delay` can be retired for a reason beyond tidiness;
  * the spans are the same -- the cascade is a better gait for the same price and no more,
    which is still worth adopting, but gait modulation needs a different mechanism and this
    file should say so plainly;
  * the cascade's span is narrower -- the argument was wrong in the direction nobody
    predicted, and that is worth more than either of the above.

Frequency is not the only thing that has to survive. A wider span bought by an animal that
has stopped swimming properly is not modulation, so the travelling index, the wavelength and
the net speed are reported beside it. Buffer is where a bad configuration hides: an animal
that barely translates has a small radius and a plausible frequency almost by construction.

Run:  PYTHONPATH=. .venv/bin/python tools/head_medium.py
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

# (label, stages, delay, stage_tau). The shipped reflex against the configuration
# tools/head_cascade.py landed on: same total lag, none of it a transport delay.
ARMS = [
    ("shipped ", 1, 0.28, 0.0),
    ("cascade ", 4, 0.00, 0.125),
]

# Ordered by anisotropy, because K is the axis that matters and the table should read along
# it. K = 40, 9, 1.58.
MEDIA = ("agar", "viscous", "buffer")

# Fang-Yen et al. 2010, the two ends of the continuum.
ANIMAL = {"agar": 0.30, "buffer": 1.76}


def _job(job):
    label, stages, delay, stage_tau, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, head_stages=stages, head_delay=delay, head_stage_tau=stage_tau))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)                       # let the loop settle onto whichever cycle it picks
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
    return dict(label=label, stages=stages, delay=delay, stage_tau=stage_tau,
                medium=medium, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    # Seed-major, so a run cut short by the pool timeout still holds every arm in every
    # medium at fewer seeds rather than one arm at all of them.
    jobs = [(lab, st, d, tau, med, s)
            for s in SEEDS for med in MEDIA for (lab, st, d, tau) in ARMS]
    print("HEAD MEDIUM -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  does the cascade's phase follow the mechanical load?\n")
    # The default 2400 s is not enough for this on a small machine and truncating the run is
    # worse than waiting for it; the seed-major ordering above is the fallback, not the plan.
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["label"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  arm       medium   K      n | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    K = {"agar": 40.0, "viscous": 9.0, "buffer": 1.58}
    for lab, *_ in ARMS:
        for med in MEDIA:
            g = agg.get((lab, med))
            if not g:
                print("  %s  %-8s %5.2f  -- | not measured" % (lab, med, K[med]))
                continue
            print("  %s  %-8s %5.2f %2d | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f"
                  % (lab, med, K[med], len(g), mean(g, "freq"), sd(g, "freq"),
                     mean(g, "wavelength"), mean(g, "twi"), mean(g, "k_rms"),
                     mean(g, "speed"), mean(g, "net_path")))

    missing = [(lab, med) for lab, *_ in ARMS for med in MEDIA if (lab, med) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so the spans below are not the paired")
        print("  comparison this file claims to make:")
        for c in missing:
            print("    %s in %s: no trial returned" % c)
        for k, n in short:
            print("    %s in %s: %d of %d seeds" % (k[0], k[1], n, len(SEEDS)))

    # The comparison. A span, not a frequency: the question is whether the loop's operating
    # point moves with the load, and neither end on its own says anything about that.
    print("\n  GAIT MODULATION -- frequency span across the drag continuum")
    print("  The animal goes %.2f Hz on agar to %.2f Hz in buffer, a span of %.2fx."
          % (ANIMAL["agar"], ANIMAL["buffer"], ANIMAL["buffer"] / ANIMAL["agar"]))
    spans = {}
    for lab, *_ in ARMS:
        a, b = agg.get((lab, "agar")), agg.get((lab, "buffer"))
        if not a or not b:
            print("  %s span: not measurable, an end is missing" % lab)
            continue
        fa, fb = mean(a, "freq"), mean(b, "freq")
        spans[lab] = fb / max(fa, 1e-9)
        print("  %s %.3f -> %.3f Hz, span %.2fx   (animal %.2fx, so %.0f%% of the way)"
              % (lab, fa, fb, spans[lab], ANIMAL["buffer"] / ANIMAL["agar"],
                 100.0 * (spans[lab] - 1.0) / (ANIMAL["buffer"] / ANIMAL["agar"] - 1.0)))

    if len(spans) == len(ARMS):
        lab_ship, lab_casc = ARMS[0][0], ARMS[1][0]
        widened = spans[lab_casc] - spans[lab_ship]
        print("\n  VERDICT")
        if widened > 0.15:
            print("  The cascade's span is wider by %.2fx. The phase does follow the load,"
                  % widened)
            print("  which is the mechanism the cascade was built for and the argument")
            print("  `head_delay` could never make. Retiring the delay now has a reason")
            print("  beyond tidiness.")
        elif widened < -0.15:
            print("  The cascade's span is *narrower* by %.2fx. The argument was wrong in"
                  % -widened)
            print("  the direction nobody predicted, which is worth more than confirming it.")
        else:
            print("  The spans differ by %+.2fx, which is nothing. The cascade is a better"
                  % widened)
            print("  gait for the same price -- worth adopting on the head_cascade.py")
            print("  numbers alone -- but gait modulation needs a different mechanism, and")
            print("  the frequency-dependent-phase argument does not survive this.")

        # A span bought by an animal that stopped swimming is not modulation. Buffer is
        # where that hides, so say what the buffer end actually looks like in both arms.
        print("\n  And what the buffer end costs, because a wide span is worthless if the")
        print("  animal is thrashing rather than swimming:")
        for lab, *_ in ARMS:
            g = agg.get((lab, "buffer"))
            if g:
                print("    %s TWI %+.3f, wavelength %.2f L, net %.4f mm/s, net/path %.2f"
                      % (lab, mean(g, "twi"), mean(g, "wavelength"),
                         mean(g, "speed"), mean(g, "net_path")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
