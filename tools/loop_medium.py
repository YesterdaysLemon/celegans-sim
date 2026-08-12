"""Which stage of the loop actually feels the medium, and does it stop below K = 9?

THE QUESTION THIS INHERITS.

`tools/flambda_locus.py` (2026-08-12) measured the model's (f, lambda) locus across nine
media and found one coupling, not two knobs: f and lambda move together, roughly along the
animal's crawl->swim chord, and the whole excursion is bunched -- 11% of the chord
traversed, 89% of the frequency motion above K = 9. NEXT.md's question is now *where* that
coupling lives and *why* it runs out.

THE INSTRUMENT.

`tools/loop_phase.py`'s lock-in, pointed at the medium instead of the step size. Open the
head loop (`head_proprio_gain = 0`), inject a pure sinusoid with the reflex's own
dorsoventral sign pattern, and read each stage's gain and phase at the drive frequency:

    injected current -> neuron voltage -> synaptic release -> muscle tension -> curvature

Drag appears in exactly one arrow of that chain -- tension to curvature; nothing upstream
of the body touches `MediumParams`. So the open-loop prediction is not *which* stage moves
with K (it can only be the last one, short of an operating-point surprise) but **how much,
where along K, and whether the motion runs out below K = 9 the way the closed-loop
frequency does.**

Two arms, as in the parent tool: body reflex closed at its shipped gain (the animal the
locus was measured on), and body gain 0 -- every feedback path open, purely feedforward --
so if the body stage does saturate, the arm pair says whether the saturation is in the
passive mechanics or in the body-reflex loop around them.

And one quantitative check tying it back to the closed loop: a negative-feedback loop
oscillates where its total phase reaches 180 degrees. The receptor's own transfer function
is analytic -- a transport delay `head_delay` = 0.28 s plus a first-order lag `head_tau` =
0.22 s -- so each medium's measured plant phase plus the receptor phase gives a predicted
crossover frequency. That prediction is held against the closed-loop frequencies the locus
run measured on the same media (K = 40: 0.656 Hz, 17.8: 0.800, 7.9: 0.844, 3.5: 0.844,
1.58: 0.833). The *pattern* across K is the robust comparison -- an absolute offset from a
sign-convention slip would shift every medium equally and the saturation shape would
survive it.

WHAT EACH OUTCOME WOULD MEAN, fixed before the run.

  * **The body stage's phase moves with K above K ~ 9 and is flat below** -- the
    saturation is localised to the mechanics, the only load-dependent arrow. If the
    feedforward arm shows the same shape, it is the *passive* body: sensible physics,
    since in thin fluid the body's bending modes relax far faster than the undulation
    period (6e-6 s in buffer, `worm/params.py`), so the body goes quasi-static, its phase
    contribution collapses toward zero, and there is nothing left for the medium to vary.
    The mechanism question then becomes: what load-dependence does the real animal carry
    that this body does not -- and the answer must scale a *time*, which is what NEXT.md's
    per-segment-propagation suspicion always wanted.
  * **An upstream stage moves with K** -- neurons, release or muscle phase change with
    the medium. Nothing upstream touches drag, so this could only be an operating-point
    effect (voltage-dependent time constants seeing a different mean drive). Worth more
    than the expected outcome, because nobody predicted it.
  * **No stage's phase moves appreciably anywhere** -- then the open-loop frame does not
    explain even the 1.31x modulation that exists, the crossover prediction will fail
    against the measured frequencies, and the modulation lives somewhere a lock-in cannot
    see (amplitude nonlinearity, the limit cycle itself). That would retire this
    instrument for the medium question, which is worth knowing before anything is built
    on it.

Media are `tools/flambda_locus.py::media_sweep` indices (8, 6, 4, 2, 0) -- K = 40, 17.8,
7.9, 3.5, 1.58 -- so every point here is a point there. Frequencies bracket the measured
operating band (0.656-0.856 Hz) rather than chasing the animal's: the crossover being
predicted is this model's.

THE ANALYTIC PREDICTION, committed while the first full run was still executing and
before any of its output had been read. An elastica bending mode of wavenumber k under
normal drag c_n relaxes with tau = c_n / (EI k^4); its phase against an oscillating
moment is -arctan(omega tau). With the measured EI = 0.095 uN mm^2 and each medium's
measured operating point from the locus run, the single-mode estimate of the curvature
stage's phase is:

       K     c_n uN s/mm^2   tau_body    omega*tau   predicted body phase
     40.00      128.0         0.410 s      1.69          -59 deg
     26.70       36.2         0.134 s      0.64          -33 deg
     17.82       10.2         0.041 s      0.21          -12 deg
     11.89        2.89        0.012 s      0.061          -3.5 deg
      7.94        0.816       3.3e-3 s     0.017          -1.0 deg
      1.58        0.0052      2.4e-5 s     1.3e-4         -0.0 deg

So the prediction is sharp and falsifiable: the collapse of the body's phase lives
almost entirely between K = 40 and K = 8, which is exactly where the closed-loop
frequency motion was found to live (89% above K = 9). If the lock-in's curvature-stage
column tracks this table to within, say, a factor of two, the saturation is passive
mechanics -- the body going quasi-static -- and the analytic form says why nothing below
K = 9 can matter: omega*tau is already 0.02 there and falling like c_n. A rough loop
budget from the same numbers over-predicts the frequency span by about 2x (60 deg of
freed phase against ~190 deg/Hz of total slope gives ~0.32 Hz where 0.18 Hz is
measured), which is the accuracy a one-mode caricature deserves; the *placement* of the
knee is the prediction that counts.

Mechanics note: the sweep is chunked by (arm, medium) and every chunk's rows are appended
to a JSONL cache (`.loop_medium_cache.jsonl`, or `LOOP_MEDIUM_CACHE`), so a run killed by
a timeout or a container restart resumes from the last finished chunk instead of starting
over. The first launch of the full run was lost exactly that way, with zero of 100 trials
recoverable; the science is unchanged, the plumbing learned something.

Run:  PYTHONPATH=. .venv/bin/python tools/loop_medium.py
"""

from __future__ import annotations

import dataclasses
import json
import os

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from tools.flambda_locus import media_sweep
from worm.engine import Simulation
from worm.params import Params

SETTLE_CYCLES = 6.0
MEASURE_CYCLES = 10.0
SAMPLE_HZ = 400.0
DRIVE = 60.0               # pA, as in loop_phase.py
FREQS = (0.5, 0.65, 0.8, 1.0, 1.2)
MEDIA_IX = (8, 6, 4, 2, 0)             # K = 40, 17.8, 7.9, 3.5, 1.58
SEEDS = (0, 3)
BODY_GAINS = (30.0, 0.0)               # shipped body reflex, and every path open

# Closed-loop frequencies measured on the same media by tools/flambda_locus.py,
# 2026-08-12, three seeds. The prediction below is held against this pattern.
MEASURED_F = {8: 0.656, 6: 0.800, 4: 0.844, 2: 0.844, 0: 0.833}


def _lockin(x, t, f):
    """Amplitude and phase of x at frequency f. Phase in degrees, lag negative."""
    x = np.asarray(x) - np.mean(x)
    w = np.exp(-2j * np.pi * f * np.asarray(t))
    c = 2.0 * np.sum(x * w) / len(x)
    return float(np.abs(c)), float(np.degrees(np.angle(c)))


def _job(job):
    freq, med_ix, ca, seed = job
    med = media_sweep()[med_ix]
    p = Params()
    p = dataclasses.replace(
        p, medium=med,
        sensory=dataclasses.replace(p.sensory, head_proprio_gain=0.0,
                                    proprio_gain=ca))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    dt = p.neural.dt

    sgn = sim.senses.W_head_sign * sim.senses.g_scale_head
    dorsal = np.flatnonzero(sim.senses.W_head_sign < 0)
    ventral = np.flatnonzero(sim.senses.W_head_sign > 0)
    head_win = sim.senses._head_window

    base = sim.senses.sense
    clock = {"t": 0.0}

    def wrapped(*a, **k):
        I = base(*a, **k)
        I += sgn * (DRIVE * np.sin(2 * np.pi * freq * clock["t"]))
        return I

    sim.senses.sense = wrapped

    n_settle = int(SETTLE_CYCLES / freq / dt)
    n_meas = int(MEASURE_CYCLES / freq / dt)
    every = max(1, int(round(1.0 / (SAMPLE_HZ * dt))))

    for _ in range(n_settle):
        clock["t"] = sim.t
        sim.step()

    t0 = sim.t
    ts, drive, volt, rel, tens, curv = [], [], [], [], [], []
    for i in range(n_meas):
        clock["t"] = sim.t
        sim.step()
        if i % every:
            continue
        ts.append(sim.t - t0)
        drive.append(np.sin(2 * np.pi * freq * (sim.t - dt)))
        v, s = sim.nervous.V, sim.nervous.s
        volt.append(float(v[ventral].mean() - v[dorsal].mean()))
        rel.append(float(s[ventral].mean() - s[dorsal].mean()))
        d, ven = sim.muscles.row_tension()
        tens.append(float(d[:5].mean() - ven[:5].mean()))
        kk = np.clip(sim.body.curvature() / 5.0, -2.0, 2.0)
        curv.append(float(np.dot(head_win, kk)))

    out = {}
    for name, sig in (("drive", drive), ("volt", volt), ("rel", rel),
                      ("tens", tens), ("curv", curv)):
        amp, ph = _lockin(sig, ts, freq)
        out[name + "_a"] = amp
        out[name + "_p"] = ph
    out.update(freq=freq, med_ix=med_ix, K=med.anisotropy, ca=ca, seed=seed)
    return out


def _wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def _receptor_phase(f):
    """The analytic part of the loop: transport delay plus first-order lag, degrees."""
    p = Params().sensory
    return -360.0 * f * p.head_delay - np.degrees(np.arctan(2 * np.pi * f * p.head_tau))


def main():
    sweep = media_sweep()
    cache = os.environ.get("LOOP_MEDIUM_CACHE", ".loop_medium_cache.jsonl")
    rows, seen = [], set()
    if os.path.exists(cache):
        with open(cache) as fh:
            for line in fh:
                r = json.loads(line)
                rows.append(r)
                seen.add((r["freq"], r["med_ix"], r["ca"], r["seed"]))
    total = len(FREQS) * len(MEDIA_IX) * len(BODY_GAINS) * len(SEEDS)
    print("LOOP MEDIUM -- %d trials, lock-in on the open head loop across five media"
          % total)
    print("  which stage's phase follows K, and does it stop below K = 9?")
    if rows:
        print("  resuming: %d of %d trials cached in %s" % (len(rows), total, cache))
    print(flush=True)
    for ca in BODY_GAINS:
        for mi in MEDIA_IX:
            pending = [(f, mi, ca, s) for s in SEEDS for f in FREQS
                       if (f, mi, ca, s) not in seen]
            if not pending:
                continue
            got = [r for r in pooled(_job, pending, procs=8, timeout=14400) if r]
            with open(cache, "a") as fh:
                for r in got:
                    fh.write(json.dumps(r) + "\n")
            rows.extend(got)
            print("  chunk done: body gain %.0f, K %.2f -- %d/%d total"
                  % (ca, sweep[mi].anisotropy, len(rows), total), flush=True)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["ca"], r["med_ix"], r["freq"]), []).append(r)
    m = lambda g, k: float(np.mean([x[k] for x in g]))              # noqa: E731

    print("  stage phases in degrees relative to the injected sinusoid; 'plant' is the")
    print("  whole open loop, current -> head curvature.\n")
    for ca in BODY_GAINS:
        print("  body gain %.0f %s" % (ca, "(shipped)" if ca else "(all feedback open)"))
        print("     K    f Hz |  neuron  release  muscle  curvature |  plant ph  plant gain")
        for mi in MEDIA_IX:
            for f in FREQS:
                g = agg.get((ca, mi, f))
                if not g:
                    print("   %5.2f  %4.2f | not measured" % (sweep[mi].anisotropy, f))
                    continue
                plant_p = _wrap(m(g, "curv_p") - m(g, "drive_p"))
                print("   %5.2f  %4.2f | %+7.1f %+7.1f %+7.1f  %+8.1f  | %+8.1f  %.3e"
                      % (sweep[mi].anisotropy, f,
                         _wrap(m(g, "volt_p") - m(g, "drive_p")),
                         _wrap(m(g, "rel_p") - m(g, "volt_p")),
                         _wrap(m(g, "tens_p") - m(g, "rel_p")),
                         _wrap(m(g, "curv_p") - m(g, "tens_p")),
                         plant_p, m(g, "curv_a") / DRIVE))
            print()

    # Localisation: per stage, how much its phase moves K 40 -> 7.9 against 7.9 -> 1.58,
    # at the frequency nearest the measured operating band.
    F_AT = 0.8
    print("  LOCALISATION at %.1f Hz -- phase change per stage, thick half against thin" % F_AT)
    print("  half of the K continuum. The saturating stage is the one whose first column")
    print("  is large and second is near zero.\n")
    stages = (("neuron", "volt_p", "drive_p"), ("release", "rel_p", "volt_p"),
              ("muscle", "tens_p", "rel_p"), ("curvature", "curv_p", "tens_p"))
    for ca in BODY_GAINS:
        print("  body gain %.0f:" % ca)
        for label, a, b in stages:
            ph = {}
            for mi in (8, 4, 0):
                g = agg.get((ca, mi, F_AT))
                if g:
                    ph[mi] = _wrap(m(g, a) - m(g, b))
            if len(ph) == 3:
                print("    %-9s  K 40 -> 7.9: %+7.1f deg    K 7.9 -> 1.58: %+7.1f deg"
                      % (label, _wrap(ph[4] - ph[8]), _wrap(ph[0] - ph[4])))
        print()

    # The crossover: plant phase plus the analytic receptor phase reaches -180 where the
    # closed loop should oscillate. Interpolated in f per medium, then held against the
    # closed-loop frequencies flambda_locus measured. Pattern, not absolute value.
    print("  PREDICTED CROSSOVER against the measured closed-loop frequency")
    print("     K    | f_180 shipped-body  f_180 open-body |  measured f (flambda_locus)")
    for mi in MEDIA_IX:
        preds = []
        for ca in BODY_GAINS:
            fs, tot = [], []
            for f in FREQS:
                g = agg.get((ca, mi, f))
                if not g:
                    continue
                fs.append(f)
                # Unwrapped-by-construction: delay phase grows linearly, plant phase is
                # wrapped per point; interpolate on the wrapped-to-monotone sum.
                tot.append(_wrap(m(g, "curv_p") - m(g, "drive_p")) + _receptor_phase(f))
            pred = float("nan")
            if len(fs) >= 2:
                fs, tot = np.array(fs), np.array(tot)
                order = np.argsort(fs)
                fs, tot = fs[order], tot[order]
                for i in range(len(fs) - 1):
                    lo, hi = tot[i], tot[i + 1]
                    if (lo + 180.0) * (hi + 180.0) <= 0.0:
                        pred = float(fs[i] + (fs[i + 1] - fs[i])
                                     * (-180.0 - lo) / (hi - lo))
                        break
            preds.append(pred)
        print("   %5.2f  |      %5.3f              %5.3f       |   %.3f"
              % (sweep[mi].anisotropy, preds[0], preds[1], MEASURED_F[mi]))

    print()
    print("  Read the localisation table first: the medium can only enter at the")
    print("  curvature stage, so the question is the *shape* of its K-dependence, and")
    print("  whether the shipped-body and open-body arms share it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
