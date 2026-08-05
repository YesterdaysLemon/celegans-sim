"""If the fixed lag is what pins the swimming end, cutting it should widen the span.

This is a direct test of the diagnosis in `MediumParams`, and it needs no new model code --
`SensoryParams.head_stage_tau` already lets the head reflex carry any lag budget you like.

THE CLAIM BEING TESTED.

The frequency is set by where the loop's total lag reaches half a period. That total is a sum
of fixed constants -- head_tau, head_delay, tau_calcium, tau_tension, the synapses -- plus
exactly one term that depends on the medium, the body's own drag response. By K = 9 the body's
contribution has become small against the fixed remainder, so below that the frequency is
pinned by numbers the medium cannot reach and the modulation saturates.

If that is right, the *fraction* of the loop's phase that the body supplies is what sets the
span, and cutting the fixed lag should raise that fraction. So:

    **prediction: as the head lag falls, the agar-to-buffer span widens.**

The absolute frequencies will go wrong -- less lag means a faster animal everywhere, and the
0.50 s budget is what puts agar at 0.65 Hz in the first place. That does not matter here. This
measures the *span*, which is the quantity gait modulation is about, and a configuration that
spans well at the wrong absolute frequency is a much better starting point than one that spans
badly at the right one: an overall lag can be restored elsewhere, a missing load-dependence
cannot.

WHAT EACH OUTCOME WOULD MEAN, fixed before the run.

  * **span widens as lag falls** -- the diagnosis holds. The fixed lag is what pins the
    swimming end, and the route to gait modulation is to cut it and then find something that
    slows the animal down on agar *through the load* rather than through a constant;
  * **span stays flat near 1.3x** -- the diagnosis is wrong. The body's drag response is not
    what the remaining modulation is made of either, and something else entirely sets the
    frequency in both media;
  * **span narrows** -- worth knowing and hardest to explain; it would mean the fixed lag is
    somehow carrying the load-dependence, which nothing in the model suggests.

Four stages throughout, with `head_delay = 0`, so the only thing changing between arms is the
lag budget. `tools/head_cascade.py` established that at 0.50 s this configuration is
indistinguishable from the shipped reflex, so the top arm doubles as the control.

Wavelength is reported beside frequency because the animal opens 0.65 L to 1.54 L across this
continuum and the model manages 1.10x; a span in frequency alone is half a result.

Run:  PYTHONPATH=. .venv/bin/python tools/lag_span.py
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
STAGES = 4

# Per-stage tau, so total head lag is 4x this. 0.125 -> 0.50 s, the shipped budget.
STAGE_TAUS = (0.125, 0.0625, 0.03125)
MEDIA = ("agar", "buffer")
ANIMAL = {"agar": (0.30, 0.65), "buffer": (1.76, 1.54)}


def _job(job):
    stage_tau, medium, seed = job
    p = Params().with_medium(medium)
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, head_stages=STAGES, head_delay=0.0, head_stage_tau=stage_tau))
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
    return dict(stage_tau=stage_tau, medium=medium, seed=seed,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def main():
    jobs = [(t, med, s) for s in SEEDS for med in MEDIA for t in STAGE_TAUS]
    print("LAG SPAN -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  does cutting the fixed lag widen the agar-to-buffer span?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["stage_tau"], r["medium"]), []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("  head lag  medium   n | freq Hz         wavelen  TWI     k_rms  net mm/s  n/p")
    for med in MEDIA:
        for t in STAGE_TAUS:
            g = agg.get((t, med))
            mark = "  <- shipped budget" if t == 0.125 else ""
            if not g:
                print("  %.3f s   %-8s -- | not measured%s" % (STAGES * t, med, mark))
                continue
            print("  %.3f s   %-8s %2d | %6.3f +-%.3f  %6.2f  %+.3f  %5.2f  %.4f  %.2f%s"
                  % (STAGES * t, med, len(g), mean(g, "freq"), sd(g, "freq"),
                     mean(g, "wavelength"), mean(g, "twi"), mean(g, "k_rms"),
                     mean(g, "speed"), mean(g, "net_path"), mark))

    missing = [(t, m) for m in MEDIA for t in STAGE_TAUS if (t, m) not in agg]
    short = [(k, len(g)) for k, g in sorted(agg.items()) if len(g) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so the spans below are not the comparison")
        print("  this file claims to make:")
        for t, m in missing:
            print("    head lag %.3f s in %s: no trial returned" % (STAGES * t, m))
        for k, n in short:
            print("    head lag %.3f s in %s: %d of %d seeds" % (STAGES * k[0], k[1], n, len(SEEDS)))

    print("\n  SPAN AGAINST FIXED LAG")
    print("  The animal spans %.2fx. The prediction is that these widen as the lag falls."
          % (ANIMAL["buffer"][0] / ANIMAL["agar"][0]))
    spans = []
    for t in STAGE_TAUS:
        a, b = agg.get((t, "agar")), agg.get((t, "buffer"))
        if not a or not b:
            print("  %.3f s: not measurable, an end is missing" % (STAGES * t))
            continue
        fa, fb = mean(a, "freq"), mean(b, "freq")
        wa, wb = mean(a, "wavelength"), mean(b, "wavelength")
        spans.append((STAGES * t, fb / max(fa, 1e-9)))
        print("  %.3f s: %.3f -> %.3f Hz, span %.2fx   |  wavelength %.2f -> %.2f L, %.2fx"
              % (STAGES * t, fa, fb, fb / max(fa, 1e-9), wa, wb, wb / max(wa, 1e-9)))

    if len(spans) >= 2:
        widest, narrowest = max(s for _, s in spans), min(s for _, s in spans)
        first, last = spans[0][1], spans[-1][1]
        print("\n  VERDICT")
        if last - first > 0.20:
            print("  The span widens from %.2fx to %.2fx as the lag falls from %.3f to %.3f s."
                  % (first, last, spans[0][0], spans[-1][0]))
            print("  The diagnosis holds: the fixed lag is what pins the swimming end. The")
            print("  route to gait modulation is to cut it and then slow the animal down on")
            print("  agar *through the load* rather than with another constant.")
        elif abs(last - first) <= 0.20:
            print("  The span goes %.2fx to %.2fx, which is flat. The diagnosis does not"
                  % (first, last))
            print("  survive: the body's drag response is not what the remaining modulation")
            print("  is made of either, and something else sets the frequency in both media.")
        else:
            print("  The span *narrows*, %.2fx to %.2fx. Hardest of the three to explain,"
                  % (first, last))
            print("  and nothing in the model suggests the fixed lag carries load-dependence.")
        print("\n  (widest %.2fx, narrowest %.2fx across the arms measured)"
              % (widest, narrowest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
