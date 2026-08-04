"""Is the buffer-end frequency set by the medium, or by the body's own internal damping?

`tools/head_medium.py` found that this model's gait modulation **saturates by K = 9**. All of
the response happens between agar (K = 40) and viscous (K = 9) -- 1.29x -- and from K = 9 to
buffer (K = 1.58) there is nothing at all: 0.99x and 1.00x. The animal does not saturate,
which is how it reaches 1.76 Hz where this model reaches 0.83.

Between viscous and buffer the external normal drag falls by **173x** and the undulation
frequency does not move. Something that is not the medium is setting it, and this file is
about the most obvious candidate.

WHY INTERNAL DAMPING, AND WHY THE MODEL'S OWN NOTE IS THE REASON TO SUSPECT IT.

`BodyParams.internal_damping` is the tissue viscosity: `gamma = internal_damping * stiff / l`,
a moment per unit bending *rate*, sitting alongside `K = EI * stiff / l`, a moment per unit
bending angle. Its docstring says, correctly citing Fang-Yen et al. (2010), that the measured
bound is < 5e-4 uN mm^2 s and that this is

    negligible against the external medium.

**That is a claim about agar.** External normal drag goes 128 -> 0.90 -> 0.0052 across the
three media -- four and a half orders of magnitude -- while `internal_damping` is a constant.
A term that is negligible against 128 need not be negligible against 0.0052, and if it stops
being negligible somewhere around K = 9 then below that point the body's dissipation is
dominated by something the medium cannot touch. The frequency would pin, which is exactly the
shape of what was measured.

So this is not a new mechanism being proposed. It is an existing assumption being checked
outside the regime it was made in, which is the cheaper thing to do first.

The shipped value is 2.0e-4, within Fang-Yen's bound but the same order as the bound itself,
so there is a lot of room below it that stays inside the measurement. Zero is included as the
limit case; `Params.validate` permits it.

HOW TO READ IT, WRITTEN DOWN BEFORE THE RUN.

Both media, because the quantity of interest is the *span* and one end cannot supply it.

  * **buffer frequency rises as damping falls, agar roughly unchanged** -- the hypothesis
    holds. Internal damping is what pins the swimming end, the docstring's "negligible"
    is an agar-only claim, and gait modulation has a knob for the first time;
  * **nothing moves in buffer** -- internal damping is exonerated and the limit is neural or
    lies in the muscle. That is worth as much: it removes the obvious suspect and points the
    search at force-velocity, where the work is much larger;
  * **agar moves as much as buffer** -- the term is not negligible anywhere, the docstring is
    wrong more broadly than suspected, and every gait number in this repository was measured
    with a mechanical parameter doing more than it was documented to do.

Frequency is not sufficient on its own. A frequency bought by an animal that has stopped
holding a wave is not modulation, so the travelling index, the wavelength and the net speed
are reported beside it -- and the wavelength is the one to watch, because the animal opens
from 0.65 L to 1.54 L across this continuum and the model manages 1.10x.

Run:  PYTHONPATH=. .venv/bin/python tools/damping_sweep.py
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

# Shipped, then three decades below it, then off. All inside Fang-Yen's < 5e-4 bound.
DAMPINGS = (2.0e-4, 5.0e-5, 1.0e-5, 0.0)

# Both ends of the continuum. The middle is omitted because head_medium.py established that
# the model already responds between agar and viscous; what is unexplained is below K = 9.
MEDIA = ("agar", "buffer")

ANIMAL = {"agar": (0.30, 0.65), "buffer": (1.76, 1.54)}     # frequency Hz, wavelength L


def _job(job):
    damping, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, body=dataclasses.replace(p.body, internal_damping=damping))
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
    return dict(damping=damping, medium=medium, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(d, med, s) for s in SEEDS for med in MEDIA for d in DAMPINGS]
    print("DAMPING SWEEP -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  is the buffer-end frequency the medium's doing, or the body's own?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["damping"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  damping    medium   n | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    for med in MEDIA:
        for d in DAMPINGS:
            g = agg.get((d, med))
            mark = "  <- shipped" if d == 2.0e-4 else ""
            if not g:
                print("  %.1e  %-8s -- | not measured%s" % (d, med, mark))
                continue
            print("  %.1e  %-8s %2d | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f%s"
                  % (d, med, len(g), mean(g, "freq"), sd(g, "freq"),
                     mean(g, "wavelength"), mean(g, "twi"), mean(g, "k_rms"),
                     mean(g, "speed"), mean(g, "net_path"), mark))

    missing = [(d, m) for m in MEDIA for d in DAMPINGS if (d, m) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so what follows is not the comparison this")
        print("  file claims to make:")
        for d, m in missing:
            print("    damping %.1e in %s: no trial returned" % (d, m))
        for k, n in short:
            print("    damping %.1e in %s: %d of %d seeds" % (k[0], k[1], n, len(SEEDS)))

    print("\n  WHAT MOVED, per medium, from the shipped damping to zero")
    moved = {}
    for med in MEDIA:
        hi, lo = agg.get((DAMPINGS[0], med)), agg.get((DAMPINGS[-1], med))
        if not hi or not lo:
            print("  %-8s not measurable, an end is missing" % med)
            continue
        f_hi, f_lo = mean(hi, "freq"), mean(lo, "freq")
        w_hi, w_lo = mean(hi, "wavelength"), mean(lo, "wavelength")
        moved[med] = f_lo / max(f_hi, 1e-9)
        print("  %-8s freq %.3f -> %.3f Hz (%.2fx), wavelength %.2f -> %.2f L  "
              "[animal: %.2f Hz, %.2f L]"
              % (med, f_hi, f_lo, moved[med], w_hi, w_lo, *ANIMAL[med]))

    if len(moved) == len(MEDIA):
        b, a = moved["buffer"], moved["agar"]
        print("\n  VERDICT")
        if b > 1.15 and a < 1.10:
            print("  Buffer moved %.2fx while agar moved %.2fx. Internal damping is what" % (b, a))
            print("  pins the swimming end: the docstring's \"negligible against the external")
            print("  medium\" is an agar-only claim, and gait modulation has a knob.")
        elif b <= 1.15 and a <= 1.10:
            print("  Buffer moved %.2fx and agar %.2fx -- neither. Internal damping is" % (b, a))
            print("  exonerated and it was the cheap suspect. The limit is neural or in the")
            print("  muscle; force-velocity is the next place to look, and it is real work.")
        else:
            print("  Buffer %.2fx, agar %.2fx. The term is doing more than it is documented" % (b, a))
            print("  to do, and not only at the swimming end. Every gait number in this")
            print("  repository was measured with it in place; re-read before trusting them.")

        # Frequency alone is not the claim. Say what the wave did, because a faster animal
        # that has stopped holding a wave is not a swimming animal.
        print("\n  And what it cost the wave, because frequency alone is not modulation:")
        for med in MEDIA:
            lo = agg.get((DAMPINGS[-1], med))
            hi = agg.get((DAMPINGS[0], med))
            if lo and hi:
                print("    %-8s TWI %+.3f -> %+.3f, net %.4f -> %.4f mm/s, n/p %.2f -> %.2f"
                      % (med, mean(hi, "twi"), mean(lo, "twi"), mean(hi, "speed"),
                         mean(lo, "speed"), mean(hi, "net_path"), mean(lo, "net_path")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
