"""Does the amine load-sensing path put the model's (f, lambda) locus in motion?

THE MECHANISM UNDER TEST, and why it is exempt from the constraint that killed the others.

Every gait-modulation mechanism measured before this one reads the body's bending, and
below K ~ 8 the bending dynamics carry no information about the medium at all
(tools/loop_medium.py, tools/fv_phase.py) -- so force-velocity, reflex gains, lag shapes
and every other in-loop observer inherit the same saturation. The amine path reads the
one quantity measured to survive: the drag force on the cuticle, c x v, which keeps
scaling with the drag coefficients all the way down the continuum because the
coefficients are in it as factors. CEP/ADE/PDE transduce it (the same dopaminergic
mechanoreceptors that carry lawn texture; Vidal-Gadea et al. 2011, PNAS 108:17504 --
dopamine holds the crawl; Korta et al. 2007, PMID 17575043 -- load modulates the swim),
dopamine integrates it, and two effects engage as it falls: the head reflex's lag budget
shrinks (a load-scaled *time*, the thing the loop was measured to lack) and the
proprioceptive reach lengthens (the swim is a longer wave, and reach is the knob measured
to set wavelength without touching frequency).

THE CONFIGURATION. `worm/params.py` defaults for everything except:

    head_stages = 4, head_delay = 0, head_stage_tau = 0.125   (the measured-equivalent
        cascade -- the ring-buffer delay cannot be rescaled at runtime, stage taus can)
    load_gain, load_half        the transduction  (calibrated by the probe run, see below)
    dopamine_head_lag           lag scale = clip(1 - c*(0.5 - DA), 0.4, 1)
    proprio_reach_swim, dopamine_reach_swim      the wavelength half

The protocol is tools/flambda_locus.py's, cell for cell -- nine media geometric in K,
three seeds, settle 6 s, net/path over 30 s, analyse over 30 s -- so every number here
has a paired fv-locus baseline. Dopamine's own time constant is 6 s, so it is within 2%
of its level before the analysis window opens.

WHAT EACH OUTCOME WOULD MEAN, fixed before the run.

  * **The locus moves along the chord** -- the along-chord coordinate advances materially
    past the baseline's 0.234 -> 0.347, in the animal's direction, with the wave still
    travelling (TWI above +0.4 everywhere). Then a load signal from outside the bending
    dynamics does what nothing inside them could, and the mechanism graduates from
    research path to adoption candidate -- which is an owner decision with named
    preconditions: the food/load confound at SensoryParams.load_gain, runtime parity for
    five constants plus the cascade, and a full behavioural scorecard, because dopamine
    now moves during ordinary locomotion and everything it touches moves with it.
  * **Frequency moves, wavelength does not (or the reverse)** -- one effect works, one is
    mis-sized or mis-aimed; the locus bends off the chord. Calibration data, not failure:
    the two coefficients are independent by construction and the next probe adjusts one.
  * **The agar end moves** -- dopamine fails to saturate on agar and the calibrated crawl
    shifts. The path as parameterised is not adoptable whatever the buffer end does,
    because it buys the swim by spending the crawl, which is the trade fv was refused
    for. The load_gain/load_half pair needs rework before anything else is read.
  * **Nothing moves** -- dopamine never leaves its ceiling, or the effects are too small
    at the chosen coefficients. The probe table distinguishes which.

A locus bought with a broken gait is not modulation, so TWI, curvature, net speed and
net/path print per medium, with the same TWI floor as the baseline tool.

WHAT THE FULL RUN FOUND (2026-08-13, 27 of 27 cells, run at the probe calibration with
no re-tuning). The first pre-registered outcome, with the crawl-end check passed first:

  * **The agar end did not move.** 0.656 +-0.016 Hz at 0.84 L against the baseline's
    0.656 at 0.83, dopamine saturated at its ceiling, lag scale 1.000, blend 0.000. The
    path does not spend the crawl. (Not bit-identical, and the docstring should not be
    read as claiming it: the mechanoreceptors themselves are depolarised on agar and
    their wired synapses carry that; behaviourally it lands on the shipped numbers.)
  * **The locus runs along the chord.** Along-chord +0.234 -> +0.595: this configuration
    traverses 36% of the animal's crawl->swim line against the baseline's 11%, and hugs
    the chord *more* tightly than the baseline through the middle of the continuum
    (perp -0.015 L against -0.087 at K = 7.9). The K ~ 8 knee is gone: below it the
    baseline moved 0.000 Hz and this moves 0.900 -> 1.233, because the transduced drag
    force (0.109 -> 0.002 uN/mm) keeps discriminating after the bending dynamics have
    gone blind. Frequency span 1.88x clean (baseline 1.31x), wave speed 0.548 -> 1.324
    L/s, 2.42x (baseline 1.39x; animal 13.9x).
  * **Two blemishes, kept in the table rather than averaged away.** Seed 3 at K = 26.7
    fell out of the travelling wave for its analysis window (0.167 Hz, lambda 13.9 L,
    TWI +0.30 -- a long reversal episode; its two sibling seeds sit exactly on the locus
    at 0.750 Hz / 0.90 L), which is what the 5.25 +-6.15 row and the printed "6.28x
    lambda span" are made of -- the clean lambda span is 0.84 -> 1.09 L, 1.30x against
    the baseline's 1.10x. And the wavelength plateaus at ~1.08 L from K = 5.3 down while
    the frequency keeps climbing, so the thin end bends below the chord (perp -0.124 at
    K = 1.58): the reach blend saturates against its proprio_reach_swim = 0.32 ceiling.
    That is a calibration knob with a name, not a wall.

READING. A signal from outside the bending dynamics does what three arcs of measurement
proved nothing inside them could: the operating point keeps moving all the way down the
continuum, in the animal's direction, along the animal's line, at zero measured cost to
the calibrated crawl. What remains between this and the animal is size, and the knobs are
explicit: the swim reach ceiling (the lambda plateau), the head-lag floor of 0.4 (the
loop still carries 0.54 of its budget in buffer; the animal needs less), and the
serotonin arm of Vidal-Gadea's result, which this pass never touched. Adoption stays an
owner decision with the preconditions named in the docstring above -- the food/load
confound first among them -- and NEXT.md carries the calibration path.

THE SECOND CALIBRATION (2026-08-13, after the buffer-end grid). A 3x3 sweep of the two
knobs at the swim end found them still separable -- at fixed lag, reach moves lambda with
f flat; at fixed reach, lag moves f -- and found one cliff: reach 0.48 with the lag
coefficient left at 1.0 breaks the wave outright (0.70 Hz, lambda 2.8 L, TWI +0.54), so
reach must be paired with lag, which is the phase-consistency wave_speed.py's law always
demanded. The winner, reach_swim 0.48 with head_lag 1.30 (the effective lag scale bottoms
at ~0.42, essentially the floor), then ran the full nine-media locus, 27/27:

    K 40:   0.656 +-0.016 Hz  0.86 L   TWI +0.831   perp -0.003 L   (crawl untouched)
    K 7.94: 0.911            1.13     +0.783        +0.091
    K 3.54: 1.267            1.32     +0.756        +0.065
    K 1.58: 1.478 +-0.016    1.30     +0.726        -0.059

    along-chord +0.242 -> +0.786 (first calibration +0.595, baseline +0.347)
    spans: f 2.25x, lambda 1.53x, v = 0.566 -> 1.919 L/s, 3.39x
    (animal: 5.87x, 2.37x, 13.9x; buffer wave speed 71% of the animal's swim)

No cliff appears at any intermediate medium -- every TWI is +0.72 or better -- and the
one distortion is a bulge above the chord peaking at +0.15 L around K = 5.3, the
wavelength getting ahead of the frequency mid-continuum, closing again at both ends. The
tool's default configuration is this calibration; the first calibration's table above is
kept because the pair shows what each knob bought.

Run:  PYTHONPATH=. .venv/bin/python tools/amine_gait.py
"""

from __future__ import annotations

import dataclasses
import json
import os

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from tools.flambda_locus import CRAWL, SWIM, TWI_FLOOR, _chord_coords, _plot, media_sweep
from worm.engine import Simulation
from worm.params import Params

MEASURE = 30.0
SEEDS = (0, 3, 7)

# The amine configuration. Calibrated by the 2026-08-13 probe run; the values are TUNED
# and say so, and the baseline every row is compared against is the shipped model through
# the identical protocol (tools/flambda_locus.py, same seeds, same media).
LOAD_GAIN = float(os.environ.get("AMINE_LOAD_GAIN", 60.0))
LOAD_HALF = float(os.environ.get("AMINE_LOAD_HALF", 1.0))
HEAD_LAG = float(os.environ.get("AMINE_HEAD_LAG", 1.30))
REACH_SWIM = float(os.environ.get("AMINE_REACH_SWIM", 0.48))
REACH_BLEND = float(os.environ.get("AMINE_REACH_BLEND", 2.0))

# The shipped model's locus on the same protocol (tools/flambda_locus.py, 2026-08-12),
# for the side-by-side: (K, freq, wavelength).
BASELINE = [(40.00, 0.656, 0.83), (26.70, 0.767, 0.86), (17.82, 0.800, 0.88),
            (11.89, 0.833, 0.88), (7.94, 0.844, 0.88), (5.30, 0.856, 0.87),
            (3.54, 0.844, 0.87), (2.36, 0.844, 0.89), (1.58, 0.833, 0.91)]


def amine_params(med) -> Params:
    p = Params()
    return dataclasses.replace(
        p, medium=med,
        sensory=dataclasses.replace(
            p.sensory, head_stages=4, head_delay=0.0, head_stage_tau=0.125,
            load_gain=LOAD_GAIN, load_half=LOAD_HALF, proprio_reach_swim=REACH_SWIM),
        modulator=dataclasses.replace(
            p.modulator, dopamine_head_lag=HEAD_LAG, dopamine_reach_swim=REACH_BLEND))


def _job(job):
    u_index, seed = job
    med = media_sweep()[u_index]
    p = amine_params(med)
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
    lam = r["wavelength"]
    return dict(u_index=u_index, K=med.anisotropy, seed=seed,
                freq=r["freq"], wavelength=lam,
                phase_v=lam * r["freq"] if np.isfinite(lam) else float("nan"),
                twi=r["twi"], k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9),
                da=float(sim.modulators.level["dopamine"]),
                lag=float(sim.modulators.head_lag_scale()),
                blend=float(sim.modulators.swim_reach_blend()))


def main():
    sweep = media_sweep()
    cache = os.environ.get("AMINE_GAIT_CACHE", ".amine_gait_cache.jsonl")
    rows, seen = [], set()
    if os.path.exists(cache):
        with open(cache) as fh:
            for line in fh:
                r = json.loads(line)
                rows.append(r)
                seen.add((r["u_index"], r["seed"]))
    total = len(sweep) * len(SEEDS)
    print("AMINE GAIT -- the load-sensing path against the shipped locus, %d media x %d seeds"
          % (len(sweep), len(SEEDS)))
    print("  config: load_gain %.0f, load_half %.2f, head_lag %.2f, reach_swim %.2f, "
          "blend %.1f" % (LOAD_GAIN, LOAD_HALF, HEAD_LAG, REACH_SWIM, REACH_BLEND))
    if rows:
        print("  resuming: %d of %d cached" % (len(rows), total))
    print(flush=True)
    for i in range(len(sweep)):
        pending = [(i, s) for s in SEEDS if (i, s) not in seen]
        if not pending:
            continue
        got = [r for r in pooled(_job, pending, procs=8, timeout=14400) if r]
        with open(cache, "a") as fh:
            for r in got:
                fh.write(json.dumps(r) + "\n")
        rows.extend(got)
        print("  chunk done: K %.2f -- %d/%d" % (sweep[i].anisotropy, len(rows), total),
              flush=True)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault(r["u_index"], []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    base = {K: (f, wl) for K, f, wl in BASELINE}
    print("\n     K     n |  DA    lag   blend | freq Hz         wavelen L     |"
          " baseline f, wl | TWI     net mm/s  n/p")
    table = []
    for rank, i in enumerate(sorted(agg, key=lambda j: -sweep[j].anisotropy)):
        g = agg[i]
        K = sweep[i].anisotropy
        fq, wl = mean(g, "freq"), mean(g, "wavelength")
        ch = chr(ord("a") + rank)
        table.append((ch, K, fq, wl, mean(g, "twi"), len(g)))
        bf, bw = base.get(round(K, 2), (float("nan"), float("nan")))
        flag = "  ** TWI below %.1f" % TWI_FLOOR if mean(g, "twi") < TWI_FLOOR else ""
        print("  %s %6.2f  %d | %5.3f  %5.3f  %5.3f | %6.3f +-%.3f  %5.2f +-%.2f  |"
              "  %5.3f  %4.2f  | %+.3f  %.4f  %.2f%s"
              % (ch, K, len(g), mean(g, "da"), mean(g, "lag"), mean(g, "blend"),
                 fq, sd(g, "freq"), wl, sd(g, "wavelength"), bf, bw,
                 mean(g, "twi"), mean(g, "speed"), mean(g, "net_path"), flag))

    print()
    _plot([(ch, fq, wl) for ch, _K, fq, wl, _twi, _n in table])
    print("  letters: this configuration.  Baseline locus (shipped model, same protocol):")
    print("  bunched at 0.66-0.86 Hz x 0.83-0.91 L, 11%% of the chord, flambda_locus.py.")

    good = [(K, fq, wl) for _ch, K, fq, wl, twi, _n in table
            if twi >= TWI_FLOOR and np.isfinite(fq) and np.isfinite(wl)]
    print("\n  THE LOCUS AGAINST THE ANIMAL'S LINE (baseline in parentheses)")
    base_coords = {round(K, 2): _chord_coords(f, wl) for K, f, wl in BASELINE}
    for K, fq, wl in good:
        along, perp = _chord_coords(fq, wl)
        b = base_coords.get(round(K, 2), (float("nan"), float("nan")))
        print("    K %6.2f:  along %+.3f (%+.3f)   perp %+.4f (%+.4f) L"
              % (K, along, b[0], perp, b[1]))
    if len(good) >= 2:
        a0 = _chord_coords(*good[0][1:])[0]
        a1 = _chord_coords(*good[-1][1:])[0]
        fs = [fq for _K, fq, _wl in good]
        ws = [wl for _K, _fq, wl in good]
        print("\n  VERDICT MATERIAL")
        print("    along-chord: %+.3f -> %+.3f (baseline +0.234 -> +0.347)" % (a0, a1))
        print("    spans: f %.2fx (baseline 1.31x, animal 5.87x), lambda %.2fx"
              " (baseline 1.10x, animal 2.37x)"
              % (max(fs) / max(min(fs), 1e-9), max(ws) / max(min(ws), 1e-9)))
        print("    v = f*lambda: %.3f -> %.3f L/s (baseline 0.548 -> 0.761,"
              " animal 0.195 -> 2.71)"
              % (good[0][1] * good[0][2], good[-1][1] * good[-1][2]))
    print("\n  Outcomes fixed in the docstring before the run; the agar end is read")
    print("  first, because a swim bought by spending the crawl is the fv trade again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
