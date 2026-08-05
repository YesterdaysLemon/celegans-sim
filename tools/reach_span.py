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
    # Wavenumber rather than wavelength, because wavelength is 2*pi/|slope| and therefore
    # heavy-tailed: as the wave flattens towards standing it diverges, and `np.nanmean` does
    # not filter `inf`. One near-standing seed would otherwise make a cell's mean wavelength
    # -- and any ratio built from it -- meaningless or infinite. Averaging in wavenumber and
    # inverting afterwards is the well-behaved direction.
    wl = r["wavelength"]
    return dict(reach=reach, medium=medium, seed=seed,
                freq=r["freq"], wavelength=wl,
                wavenumber=(1.0 / wl if np.isfinite(wl) and wl > 0 else 0.0),
                twi=r["twi"], k_rms=r["kappa_rms"],
                # Recorded because a frequency is only meaningful if a peak exists: `power`
                # is the dominant bin's share of the spectrum, and a broadband animal going
                # nowhere still yields a confident-looking argmax. `direction` because
                # wavelength uses |slope| and so reads the same for a tail->head wave.
                power=r.get("power", float("nan")),
                direction=r.get("direction", ""),
                speed=net / span, net_path=net / max(path, 1e-9))


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

    # ---- spans, paired by seed -------------------------------------------------------
    #
    # A span is computed per seed and then averaged, rather than as a ratio of two pooled
    # means. The seeds were always paired -- same seed, both media -- and pooling first threw
    # that away: it left no error bar on any span, let the two ends come from different seed
    # subsets, and put a survivorship bias in the numerator whenever a buffer trial diverged
    # and its agar partner did not. Every threshold below is compared against the spread it
    # now has instead of against a bare point estimate.
    def paired(rc, key):
        a = {r["seed"]: r for r in agg.get((rc, "agar"), [])}
        b = {r["seed"]: r for r in agg.get((rc, "buffer"), [])}
        both = sorted(set(a) & set(b))
        vals = []
        for s in both:
            lo = a[s][key]
            if abs(lo) > 1e-12:
                vals.append(b[s][key] / lo)
        return vals, both

    print("\n  DOES REACH MOVE THE WAVELENGTH, AND DOES THE MEDIUM REACH IT?")
    print("  The animal: 0.65 L on agar, 1.54 L in buffer -- a span of %.2fx."
          % (ANIMAL["buffer"][1] / ANIMAL["agar"][1]))
    print("  Spans are per-seed ratios, mean +- sd, over seeds that returned BOTH media.")
    w_spans, f_spans = {}, {}
    for rc in REACHES:
        # Wavelength span from wavenumbers, inverted: k_buffer/k_agar is the reciprocal of
        # the wavelength ratio, and it stays finite when a wave goes standing.
        kvals, both = paired(rc, "wavenumber")
        fvals, _ = paired(rc, "freq")
        if len(both) < len(SEEDS):
            print("  reach %.2f: only %d of %d seeds have both media -- span withheld"
                  % (rc, len(both), len(SEEDS)))
            continue
        wv = [1.0 / v for v in kvals if v > 1e-12]
        if not wv or not fvals:
            print("  reach %.2f: no usable paired ratio" % rc)
            continue
        w_spans[rc] = (float(np.mean(wv)), float(np.std(wv)))
        f_spans[rc] = (float(np.mean(fvals)), float(np.std(fvals)))
        print("  reach %.2f: wavelength span %.2f +-%.2f  |  frequency span %.2f +-%.2f  (n=%d)"
              % (rc, w_spans[rc][0], w_spans[rc][1], f_spans[rc][0], f_spans[rc][1], len(both)))

    # Does reach move the wavelength at all, within each medium? This is the question the
    # STUCK/FIXED distinction turns on, and it is asked per medium rather than pooled.
    moved = {}
    for med in MEDIA:
        lo, hi = agg.get((REACHES[0], med)), agg.get((REACHES[-1], med))
        if not lo or not hi:
            continue
        klo, khi = mean(lo, "wavenumber"), mean(hi, "wavenumber")
        if klo > 1e-12 and khi > 1e-12:
            moved[med] = (1.0 / khi) / (1.0 / klo)
            print("  %-8s wavelength across reach %.2f -> %.2f: %.2f -> %.2f L  (%.2fx)"
                  % (med, REACHES[0], REACHES[-1], 1.0 / klo, 1.0 / khi, moved[med]))

    # Health of the measurement itself, because a confident frequency on a broadband animal
    # is the failure mode these tables cannot otherwise show.
    weak = [(rc, m, mean(g, "power")) for (rc, m), g in sorted(agg.items())
            if np.isfinite(mean(g, "power")) and mean(g, "power") < 0.02]
    if weak:
        print("\n  Weak spectral peaks (dominant bin < 2% of power) -- treat these")
        print("  frequencies as unreliable rather than merely imprecise:")
        for rc, m, pw in weak:
            print("    reach %.2f in %-8s power %.4f" % (rc, m, pw))

    if len(w_spans) >= 2 and len(moved) == len(MEDIA):
        rcs = sorted(w_spans)
        w_lo, w_hi = w_spans[rcs[0]][0], w_spans[rcs[-1]][0]
        f_lo, f_hi = f_spans[rcs[0]][0], f_spans[rcs[-1]][0]
        # Spread pooled across the arms, so a threshold is judged against the scatter the
        # measurement actually has rather than against a number chosen in advance.
        w_sd = float(np.mean([w_spans[r][1] for r in rcs]))
        trend = abs(w_hi - w_lo)
        print("\n  VERDICT")
        print("  wavelength span %.2f -> %.2f across the reach sweep, typical seed sd %.2f"
              % (w_lo, w_hi, w_sd))

        # STUCK vs FIXED turns on whether reach moves the wavelength *in buffer*. Agar is
        # not used as a conjunct: SensoryParams.proprio_reach already records 0.62 L at
        # reach 0.10 and 0.85 L at 0.16, so "reach works on agar" is satisfied by data
        # already in the repository and would carry no information here.
        works_buffer = moved["buffer"] > 1.25
        near_flat = trend <= max(0.20, 2.0 * w_sd)
        if not works_buffer:
            print("  Reach barely moves the wavelength in buffer (%.2fx) though it moves it"
                  % moved["buffer"])
            print("  on agar (%.2fx). The mechanism is saturated at the swimming end:" % moved["agar"])
            print("  the wavelength is STUCK there, which is a modelling failure to hunt")
            print("  rather than a wire to run.")
        elif near_flat:
            print("  Reach moves the wavelength in buffer (%.2fx) and on agar (%.2fx), and"
                  % (moved["buffer"], moved["agar"]))
            print("  the span does not respond to it. The wavelength is FIXED, not stuck --")
            print("  the mechanism works and simply has no input from the medium. Frequency")
            print("  and wavelength are independent failures, and the wavelength half is a")
            print("  wire that was never run. Making proprio_reach load-dependent is the change.")
        elif w_hi > w_lo:
            print("  The wavelength span GROWS with reach, and by more than the seed scatter.")
            print("  There is latent medium-dependence in the proprioceptive path that a")
            print("  longer reach exposes -- the first sign of load-dependence in this model.")
        else:
            print("  The wavelength span SHRINKS with reach, by more than the seed scatter.")
            print("  Unexpected, and it has no ready explanation: a longer reach is averaging")
            print("  the medium's effect away rather than exposing it. Look at the kymograph.")

        f_sd = float(np.mean([f_spans[r][1] for r in rcs]))
        if abs(f_hi - f_lo) > max(0.20, 2.0 * f_sd):
            print("\n  The FREQUENCY span also moved with reach, %.2f -> %.2f (sd %.2f), so"
                  % (f_lo, f_hi, f_sd))
            print("  the two are coupled through the reach and one mechanism might fix both.")
        else:
            print("\n  The frequency span did not move with reach: %.2f -> %.2f, sd %.2f."
                  % (f_lo, f_hi, f_sd))
            print("  That is the independence the FIXED reading describes.")
    else:
        print("\n  Too few complete arms to reach a verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
