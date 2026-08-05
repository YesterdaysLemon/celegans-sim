"""Is there anything in this animal's own geometry that tells it which medium it is in?

`SensoryParams.proprio_reach` records the result this file exists to serve. Reach 0.10 on
agar gives a 0.60 L wave against the animal's 0.65; reach 0.24 in buffer gives 1.30 L against
its 1.54. **Both of the animal's wavelengths are already reachable.** Nothing is saturated and
nothing is missing from the mechanism -- what is missing is the *selection*, something that
tells the reach which medium the animal is in.

The obvious way to supply that is also the one thing this project must not do: read the drag
coefficient. The animal has no medium sensor, and a model that gives it one has answered the
question by assuming it. So the selection has to come from a quantity the nervous system could
plausibly compute from what it already senses, and **this model's nervous system senses
exactly one thing about the body: curvature.** There is no force afferent, no velocity
afferent, no tension or effort signal anywhere in it. The medium reaches the circuit only
through realised body shape.

THAT IS A CONSTRAINT, AND IT MIGHT ALSO BE A DEAD END. WHICH IS THE POINT OF THIS FILE.

Before any of the wiring is built it is worth knowing whether *any* locally available
geometric quantity separates the media at all. If none of them does, the load-dependent reach
is unbuildable in this model as it stands -- not badly built, unbuildable -- and the honest
next step would be adding an afferent rather than rewiring an existing one. That is a
completely different project, and finding out costs one sweep rather than a week.

There is already one strong reason for pessimism, and it is in the data:

    kappa_rms is 4.46 on agar and 4.39 in buffer.

The amplitude of the bend, the most obvious candidate, is **the same in both media to within
2%**. This animal bends just as hard in water as on agar. So the easy answer is already gone
before the sweep starts, and that is exactly why it is worth checking the others rather than
assuming one of them works.

WHAT IS MEASURED, AND WHY EACH ONE COULD PLAUSIBLY CARRY LOAD.

Every quantity below is computable from a motor neuron's own state plus the curvature it
already reads. None requires a sense the model does not have.

  * `k_rms`        -- bending amplitude. The null candidate, included because a sweep that
                      omits the thing everyone expects to work cannot report that it does not;
  * `kdot_rms`     -- bending *rate*. Amplitude times frequency, so it inherits whatever
                      frequency separation exists and no more;
  * `freq`         -- the loop's own operating frequency. It does separate (0.69 vs 0.84 Hz),
                      but using it to set the reach makes the loop's output its own input,
                      which is a control problem rather than a sensor. Logged to size it,
                      flagged as circular;
  * `compliance`   -- **realised curvature per unit commanded moment**, `rms(kappa) /
                      rms(joint_moment)` at the same joint. This is the one with a mechanism
                      behind it: a body pushing against a stiff medium bends less for the same
                      muscular effort. It is a local comparison between what a motor unit
                      commanded and what its own stretch receptor then read, which is the
                      cheapest possible efference copy and the only quantity here that is a
                      load measurement rather than a proxy for one;
  * `lag_ms`       -- the time between commanded moment and realised curvature at the same
                      joint, by cross-correlation. The same physics as compliance seen in the
                      time domain rather than the amplitude domain: drag makes the body slow
                      to follow. Reported separately because the two can come apart, and if
                      only one of them separates that says which;
  * `harmonic2`    -- second-harmonic content of the curvature waveform. A body fighting a
                      medium it cannot easily move through should bend less sinusoidally;
  * `wavelength`   -- logged for completeness and flagged, because it is the quantity the
                      reach is meant to *set*. Using it as the input would close a loop the
                      wrong way round.

HOW TO READ IT, FIXED BEFORE THE RUN.

Three media, not two, and that is the whole design. A signal that separates agar from buffer
but does nothing in between cannot drive a graded reach -- it is a switch, and the animal's
gait modulation is continuous. So a candidate has to clear both of:

  * **separation** -- the buffer/agar ratio differs from 1 by more than twice the seed
    scatter, measured per seed and paired (`tools.assays.paired`);
  * **monotonicity** -- it moves the same way from agar to viscous as from viscous to buffer.
    K is 40, 9, 1.58, so this is asking whether the signal tracks the continuum or just its
    ends.

Both are printed for every candidate and the verdict names which ones passed. Outcomes:

  * **compliance or lag separates and is monotone** -- the load-dependent reach is buildable,
    and this names the signal to drive it with. That is the good case and the expected one;
  * **only `freq` separates** -- the only thing in this animal that knows about the medium is
    the very quantity gait modulation is trying to fix. Building the reach on it would be
    positive feedback on a 1.2x signal, which is a control-stability question before it is a
    biology one;
  * **nothing separates monotonically** -- the medium does not reach this animal's geometry in
    any usable way, the load-dependent reach cannot be built out of what is here, and the real
    finding is that the model needs an afferent it does not have. Expensive to hear and much
    cheaper than hearing it after the wiring.

Nothing is adopted here and nothing is ported to the runtime. This file only measures.

Run:  PYTHONPATH=. .venv/bin/python tools/load_signal.py
"""

from __future__ import annotations

import numpy as np

from tools.assays import paired, pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 30.0
SEEDS = (0, 3, 7)

# Ordered by drag anisotropy, because K is the axis the signal has to track: 40, 9, 1.58.
# Three points rather than two is what makes monotonicity a question at all.
MEDIA = ("agar", "viscous", "buffer")
K = {"agar": 40.0, "viscous": 9.0, "buffer": 1.58}

# Sampled away from both ends of the body. The head is driven by its own reflex rather than by
# the travelling wave, and the last few joints are a free end whose curvature is not resisted
# by much of anything -- neither is representative of what a mid-body motor unit experiences,
# which is the cell the reach would actually be modulating.
BODY = (0.25, 0.75)

# A candidate is a signal only if it separates the media by more than the seeds disagree, and
# tracks the continuum rather than just its ends. Fixed here rather than chosen after looking.
SEPARATION = 2.0        # multiples of the paired seed sd
CIRCULAR = ("freq", "wavelength")   # usable as evidence, not as an input; see the header


def _job(job):
    medium, seed = job
    p = Params().with_medium(medium)
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)

    dt = sim.dt
    stride = 4
    n = int(MEASURE / dt)
    s = sim.body.joint_s
    keep = (s > BODY[0]) & (s < BODY[1])
    kappa, moment = [], []
    for i in range(n):
        sim.step()
        if sim.steps % 1000 == 0:
            sim.check_invariants()
        if i % stride == 0:
            kappa.append(sim.body.curvature()[keep].copy())
            moment.append(sim.muscles.joint_moment()[keep].copy())
    kappa = np.asarray(kappa)
    moment = np.asarray(moment)
    fs = 1.0 / (dt * stride)

    # Everything below is on the AC part. A static bend contributes to an rms without being
    # part of the undulation, and the two media need not hold the same static offset -- which
    # would put a difference in every amplitude column that has nothing to do with load.
    k_ac = kappa - kappa.mean(axis=0)
    m_ac = moment - moment.mean(axis=0)

    k_rms = float(np.sqrt((k_ac ** 2).mean()))
    m_rms = float(np.sqrt((m_ac ** 2).mean()))
    kdot = np.diff(k_ac, axis=0) * fs
    kdot_rms = float(np.sqrt((kdot ** 2).mean()))

    # Compliance: bend realised per unit moment commanded. Guarded because a joint commanding
    # nothing has an undefined compliance rather than an infinite one.
    compliance = k_rms / m_rms if m_rms > 1e-12 else float("nan")

    # Lag: cross-correlate each joint's commanded moment against its own realised curvature
    # and take the peak, refined by the same parabolic fit `_dominant` uses. Per joint and
    # then median, because one joint sitting near a node of the wave has a flat correlation
    # and a meaningless argmax.
    lags = []
    span = int(round(0.6 * fs))            # +-0.6 s is far wider than any lag the body has
    for j in range(k_ac.shape[1]):
        a, b = m_ac[:, j], k_ac[:, j]
        if a.std() < 1e-12 or b.std() < 1e-12:
            continue
        c = np.correlate(b / b.std(), a / a.std(), mode="full") / len(a)
        mid = len(a) - 1
        lo, hi = max(0, mid - span), min(len(c), mid + span + 1)
        seg = c[lo:hi]
        k = int(np.argmax(seg))
        if 0 < k < len(seg) - 1:
            d = seg[k - 1] - 2.0 * seg[k] + seg[k + 1]
            if d < -1e-12:
                k = k + 0.5 * (seg[k - 1] - seg[k + 1]) / d
        lags.append((lo + k - mid) / fs)
    lag_ms = float(np.median(lags) * 1000.0) if lags else float("nan")

    # Second-harmonic content of the mid-body curvature, as a fraction of the fundamental.
    mid_k = k_ac[:, k_ac.shape[1] // 2]
    win = np.hanning(len(mid_k))
    spec = np.abs(np.fft.rfft(mid_k * win))
    fr = np.fft.rfftfreq(len(mid_k), 1.0 / fs)
    band = (fr > 0.08) & (fr < 5.0)
    harmonic2 = float("nan")
    if np.any(band):
        i0 = int(np.flatnonzero(band)[np.argmax(spec[band])])
        i2 = int(round(2.0 * fr[i0] / (fr[1] - fr[0])))
        if 0 < i2 < len(spec) and spec[i0] > 1e-12:
            harmonic2 = float(spec[i2] / spec[i0])

    r = analyse(sim, seconds=MEASURE)
    return dict(medium=medium, seed=seed,
                k_rms=k_rms, kdot_rms=kdot_rms, m_rms=m_rms,
                compliance=compliance, lag_ms=lag_ms, harmonic2=harmonic2,
                freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"])


CANDIDATES = [
    ("k_rms", "bending amplitude", "%.3f"),
    ("kdot_rms", "bending rate", "%.3f"),
    ("compliance", "bend per unit commanded moment", "%.3f"),
    ("lag_ms", "moment -> curvature lag, ms", "%.1f"),
    ("harmonic2", "2nd harmonic / fundamental", "%.4f"),
    ("freq", "loop frequency, Hz", "%.3f"),
    ("wavelength", "wavelength, L", "%.3f"),
]


def main():
    jobs = [(med, s) for s in SEEDS for med in MEDIA]
    print("LOAD SIGNAL -- %d trials, %.0f s each, %d seeds" % (len(jobs), MEASURE, len(SEEDS)))
    print("  does anything in this animal's own geometry know which medium it is in?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault(r["medium"], []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    missing = [m for m in MEDIA if m not in agg]
    short = [(m, len(agg[m])) for m in MEDIA if m in agg and len(agg[m]) < len(SEEDS)]
    if missing or short:
        print("  NOT EVERY MEDIUM WAS MEASURED, so monotonicity below is not the test this")
        print("  file claims to make:")
        for m in missing:
            print("    %s: no trial returned" % m)
        for m, n in short:
            print("    %s: %d of %d seeds" % (m, n, len(SEEDS)))
        print()

    print("  signal                              " + "".join("%-18s" % ("%s K=%.2f" % (m, K[m]))
                                                             for m in MEDIA if m in agg))
    for key, label, fmt in CANDIDATES:
        cells = [("%s +-%s" % (fmt, fmt)) % (mean(agg[m], key), sd(agg[m], key))
                 for m in MEDIA if m in agg]
        print("  %-34s" % label + "".join("%-18s" % c for c in cells))

    if len(agg) < len(MEDIA):
        print("\n  Too few media to reach a verdict.")
        return 1

    # ---- separation and monotonicity, paired by seed --------------------------------
    print("\n  DOES IT SEPARATE, AND DOES IT TRACK THE CONTINUUM?")
    print("  Ratios are per-seed and paired; a signal has to clear BOTH columns to be usable.")
    print("  %-34s %-20s %-12s %s" % ("signal", "buffer/agar", "monotone", "verdict"))
    usable, circular_only = [], []
    for key, label, _ in CANDIDATES:
        ratio, r_sd, n = paired(agg["agar"], agg["buffer"], key)
        mid, _, _ = paired(agg["agar"], agg["viscous"], key)
        far, _, _ = paired(agg["viscous"], agg["buffer"], key)
        if n < len(SEEDS) or not np.isfinite(ratio):
            print("  %-34s %-20s %-12s %s" % (label, "unpaired", "--", "withheld"))
            continue
        # Both legs must move the same way, and the sign is taken against 1.0 because these
        # are ratios. A signal that rises then falls is a switch, not a continuum.
        legs_ok = (np.isfinite(mid) and np.isfinite(far)
                   and np.sign(mid - 1.0) == np.sign(far - 1.0)
                   and abs(mid - 1.0) > 1e-9 and abs(far - 1.0) > 1e-9)
        separated = abs(ratio - 1.0) > SEPARATION * max(r_sd, 1e-9)
        if separated and legs_ok:
            tag = "CIRCULAR" if key in CIRCULAR else "USABLE"
            (circular_only if key in CIRCULAR else usable).append((key, label, ratio, r_sd))
        elif separated:
            tag = "ends only"
        elif legs_ok:
            tag = "monotone, not separated"
        else:
            tag = "no"
        print("  %-34s %.3f +-%.3f       %-12s %s"
              % (label, ratio, r_sd, "yes" if legs_ok else "no", tag))

    print("\n  VERDICT")
    if usable:
        # Ranked on |log(ratio)| rather than |ratio - 1|, because these are ratios and the
        # latter is asymmetric: a halving and a doubling are the same effect and would score
        # 0.5 against 1.0. The scatter is converted to the log scale the same way, so a
        # signal is judged on its effect relative to its own noise rather than on which side
        # of 1 it happens to fall.
        def snr(c):
            ratio, r_sd = c[2], c[3]
            return abs(np.log(ratio)) / max(r_sd / abs(ratio), 1e-9)
        best = max(usable, key=snr)
        print("  %d signal(s) separate the media monotonically and are not the reach's own"
              % len(usable))
        print("  output. The load-dependent reach is buildable, and the one to drive it with is")
        print("  **%s** -- %.3f +-%.3f across the continuum, the largest"
              % (best[1], best[2], best[3]))
        print("  separation relative to its own seed scatter. Next: a third receptive-field")
        print("  bank and a signed blend in Senses.step, then scorecard and ethogram against")
        print("  the frozen baseline before anything is adopted.")
        if circular_only:
            print("\n  (%s also separated, and is excluded on purpose: it is what the reach"
                  % ", ".join(c[1] for c in circular_only))
            print("  sets, so driving the reach from it closes the loop the wrong way round.)")
    elif circular_only:
        print("  The ONLY things that separate the media monotonically are %s --"
              % ", ".join(c[1] for c in circular_only))
        print("  which is to say, the quantities gait modulation is trying to fix. Driving the")
        print("  reach from its own output is positive feedback on a signal of about %.2fx,"
              % circular_only[0][2])
        print("  and that is a control-stability question before it is a biology one. The")
        print("  load-dependent reach is not cleanly buildable out of what this animal senses.")
    else:
        print("  NOTHING separates the media monotonically. The medium does not reach this")
        print("  animal's geometry in any form a motor neuron could act on, so the")
        print("  load-dependent reach cannot be built out of what is here -- not badly built,")
        print("  unbuildable. What the model is missing is an afferent it does not have, which")
        print("  is a different and much larger project than rewiring an existing one.")
        print("  Expensive to hear, and much cheaper than hearing it after the wiring.")

    print("\n  And the gait each medium is actually holding, because a signal measured off an")
    print("  animal that has stopped swimming is not a signal:")
    for m in MEDIA:
        if m in agg:
            print("    %-8s K=%5.2f  TWI %+.3f, kappa_rms %.2f, freq %.3f Hz"
                  % (m, K[m], mean(agg[m], "twi"), mean(agg[m], "k_rms"), mean(agg[m], "freq")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
