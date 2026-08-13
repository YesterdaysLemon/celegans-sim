"""Is muscle force-velocity a load-scaled time, or a brake that cancels out of the span?

THE CANDIDATE, AND WHY IT IS LEGITIMATE TO MEASURE DESPITE THE DO-NOT-REPEAT.

`MuscleParams.fv_vmax` is the one genuinely load-dependent element the model owns beyond
the body itself, kept alive in `worm/params.py` "as a candidate rather than as a fix" with
its own suspicion attached: the shortening rate depends on the gait, the gait is similar
in both media, so the derating may apply equally at both ends and cancel out of the span.
The do-not-repeat table forbids retrying force-velocity *as a closed-loop derating fix* --
`fv_vmax = 500` was measured there and narrowed the span. This is not that: it is the
open-loop screen NEXT.md now prescribes, measuring the *phase* force-velocity contributes
per medium, which the closed-loop numbers cannot separate from everything else riding on
them.

The physics makes the question sharp. Within a cycle, force-velocity multiplies tension by
a factor riding the shortening rate -- in quadrature with curvature -- so at the
fundamental it acts like damping applied at the muscle. Whether that shows up as *phase*
in the lock-in, and whether the phase depends on the *load* (buffer lets the body move
faster at matched drive, agar does not), is exactly what separates a load-scaled time --
the thing the loop needs below K = 9 -- from a uniform brake, which params.py's suspicion
says it is.

WHAT IS MEASURED.

`tools/loop_medium.py`'s lock-in, identical protocol, with `fv_vmax` at 1000 (a 9%
derating at gait scale) and 500 (17%, the value the closed-loop sweep used), across
K = 40, 7.9, 1.58 -- the two ends and the knee. The fv = 0 baseline is pulled from
`loop_medium`'s own cache, running any missing rows through `loop_medium._job` itself, so
the comparison is protocol-identical by construction. Shipped body reflex throughout;
seeds (0, 3).

AND THE VALIDATION THE RECORD HANDS US FOR FREE: the do-not-repeat table carries the
closed-loop frequencies at `fv_vmax = 500` -- 0.600 Hz on agar, 0.700 in buffer. The
crossover calculator was built on fv = 0 and matched every medium to 1.5%. If it also
predicts the fv = 500 closed-loop pair from open-loop phase alone, the screen is validated
on a second configuration and every future candidate can lean on it harder.

WHAT EACH OUTCOME WOULD MEAN, fixed before the run.

  * **Load-scaled time** -- the fv phase contribution grows systematically as K falls
    (the body moves faster in thin fluid at matched drive, so the derating engages
    harder), and the predicted crossovers spread apart. Then the closed-loop failure at
    500 was cost, not absence -- the mechanism is right and the dose was wrong -- and a
    gentler fv paired with a re-fit crawl becomes worth pricing, which is an owner
    decision because it re-fits the calibrated end.
  * **Flat** -- the fv phase is the same at every K to within a few degrees. params.py's
    cancellation suspicion is confirmed by direct measurement; force-velocity is a
    fidelity candidate but not a modulation mechanism, and the load-dependence the loop
    needs below K = 9 has to come from somewhere else -- proprioception is the remaining
    route this model has not tried.
  * **No phase at all** -- gain drops, phase unmoved anywhere. Same retirement, stronger:
    not even a time, just a brake.

WHAT THE FULL RUN FOUND (2026-08-13, 60 of 60 trials). The outcome is the fourth
combination, the one the pre-registered list did not enumerate: a load-scaled time, with
the wrong sign, saturating at the same knee.

  * **Force-velocity adds real phase, and it lands where the code says it must** -- the
    muscle column moves at most 1.1 deg while the curvature stage carries all of it,
    because fv multiplies the moment applied to the body, downstream of the measured
    tension.
  * **The phase is load-dependent, backwards.** At fv = 500 the added plant phase is
    -16.8 deg on agar, -34.3 at K = 7.9, -34.9 in buffer: it brakes hardest exactly where
    the animal accelerates, because in thin fluid the body shortens faster at matched
    drive and the derating engages harder. Predicted span 1.170 against 1.263 at fv = 0
    -- narrower, which is what the closed-loop sweep measured and could not explain.
  * **And it saturates at the same K ~ 8.** The added phase at K = 7.9 and K = 1.58
    differs by under a degree, at both doses. Anything that reads the body's motion
    inherits the body's saturation: below the knee the *entire plant* -- gain and phase,
    current to curvature at matched drive -- is measured K-independent, so no observer
    inside the reflex loop can even tell K = 1.58 from K = 7.9. The signal is not
    attenuated there; it does not exist.
  * **The validation held.** Predicted crossovers at fv = 500: 0.578 on agar against the
    closed-loop record's 0.600 (-3.7%), 0.677 in buffer against 0.700 (-3.3%) -- an
    amplitude-dependent nonlinearity screened at one amplitude, so a few percent is the
    expected cost. The span prediction is essentially exact: 1.170 predicted, 1.167
    measured. The calculator now stands on two configurations.

READING. Force-velocity retires as a gait-modulation mechanism with its mechanism named:
it converts load into lag with the wrong sign and stops converting at the same knee as
everything else. params.py's cancellation suspicion was close but generous -- the derating
does not cancel out of the span, it actively narrows it. The candidate remains what
params.py always said it was, more faithful muscle at a cost to the calibrated crawl.

The structural residue is the sharpest thing this screen produced: **below K ~ 8 the
bending dynamics carry no information about the medium at all**, so gait modulation there
cannot come from any mechanism that observes bending -- gain, phase, threshold or
otherwise, linear or not. What still distinguishes media below the knee is translation:
net speed falls 0.218 -> 0.038 mm/s from K = 7.9 to 1.58 while the bending stays
identical, because thrust collapses with the anisotropy. A mechanism that senses *slip*
-- the difference between how the body bends and how it advances -- would have signal all
the way down the continuum. Whether the animal has one, and whether this model should, is
a physiology question above this tool's pay grade; it is recorded in NEXT.md as the
constraint every future proposal has to pass.

Run:  PYTHONPATH=. .venv/bin/python tools/fv_phase.py
      (run tools/loop_medium.py first, or let this tool fill its cache for the baseline)
"""

from __future__ import annotations

import dataclasses
import json
import os

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from tools.flambda_locus import media_sweep
from tools.loop_medium import (FREQS, _job as _base_job, _lockin, _receptor_phase,
                               _wrap)
from worm.engine import Simulation
from worm.params import Params

SETTLE_CYCLES = 6.0
MEASURE_CYCLES = 10.0
SAMPLE_HZ = 400.0
DRIVE = 60.0
MEDIA_IX = (8, 4, 0)                   # K = 40, 7.9, 1.58
SEEDS = (0, 3)
BODY_GAIN = 30.0                       # shipped
FV_VALUES = (1000.0, 500.0)            # 9% and 17% derating at gait scale

# Closed-loop record at fv_vmax = 500 (NEXT.md do-not-repeat table): the validation pair.
CLOSED_LOOP_FV500 = {8: 0.600, 0: 0.700}
# Closed-loop record at fv = 0 (tools/flambda_locus.py).
MEASURED_F0 = {8: 0.656, 4: 0.844, 0: 0.833}


def _job(job):
    freq, med_ix, fv, seed = job
    med = media_sweep()[med_ix]
    p = Params()
    p = dataclasses.replace(
        p, medium=med,
        muscle=dataclasses.replace(p.muscle, fv_vmax=fv),
        sensory=dataclasses.replace(p.sensory, head_proprio_gain=0.0,
                                    proprio_gain=BODY_GAIN))
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
    out.update(freq=freq, med_ix=med_ix, K=med.anisotropy, fv=fv, seed=seed)
    return out


def _load_cache(path):
    rows = []
    if os.path.exists(path):
        with open(path) as fh:
            rows = [json.loads(line) for line in fh]
    return rows


def _append_cache(path, rows):
    with open(path, "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _crossover(points):
    """points: sorted (f, total_phase_deg). First 0-crossing by linear interpolation."""
    for (f0, p0), (f1, p1) in zip(points, points[1:]):
        if p0 * p1 <= 0.0:
            return f0 + (f1 - f0) * (0.0 - p0) / (p1 - p0)
    return float("nan")


def main():
    sweep = media_sweep()

    # The fv = 0 baseline, through loop_medium's own cache and job.
    base_cache = os.environ.get("LOOP_MEDIUM_CACHE", ".loop_medium_cache.jsonl")
    base_rows = [r for r in _load_cache(base_cache) if r["ca"] == BODY_GAIN]
    have = {(r["freq"], r["med_ix"], r["seed"]) for r in base_rows}
    missing = [(f, mi, BODY_GAIN, s) for mi in MEDIA_IX for s in SEEDS for f in FREQS
               if (f, mi, s) not in have]
    if missing:
        print("  baseline: running %d missing fv=0 rows via loop_medium" % len(missing),
              flush=True)
        got = [r for r in pooled(_base_job, missing, procs=8, timeout=14400) if r]
        _append_cache(base_cache, got)
        base_rows += got

    cache = os.environ.get("FV_PHASE_CACHE", ".fv_phase_cache.jsonl")
    rows = _load_cache(cache)
    seen = {(r["freq"], r["med_ix"], r["fv"], r["seed"]) for r in rows}
    total = len(FREQS) * len(MEDIA_IX) * len(FV_VALUES) * len(SEEDS)
    print("FV PHASE -- %d trials + fv=0 baseline, lock-in across three media" % total)
    print("  is force-velocity a load-scaled time, or a brake that cancels?")
    if rows:
        print("  resuming: %d of %d cached" % (len(rows), total))
    print(flush=True)
    for fv in FV_VALUES:
        for mi in MEDIA_IX:
            pending = [(f, mi, fv, s) for s in SEEDS for f in FREQS
                       if (f, mi, fv, s) not in seen]
            if not pending:
                continue
            got = [r for r in pooled(_job, pending, procs=8, timeout=14400) if r]
            _append_cache(cache, got)
            rows.extend(got)
            print("  chunk done: fv %.0f, K %.2f -- %d/%d" %
                  (fv, sweep[mi].anisotropy, len(rows), total), flush=True)
    if not rows:
        print("  no trials completed")
        return 1

    def agg_of(rowlist, keyfn):
        agg = {}
        for r in rowlist:
            agg.setdefault(keyfn(r), []).append(r)
        return agg

    m = lambda g, k: float(np.mean([x[k] for x in g]))              # noqa: E731
    base = agg_of(base_rows, lambda r: (r["med_ix"], r["freq"]))
    fvagg = agg_of(rows, lambda r: (r["fv"], r["med_ix"], r["freq"]))

    def stage(g, a, b):
        return _wrap(m(g, a) - m(g, b))

    print("\n  muscle and curvature stage phases, fv on against the fv = 0 baseline.")
    print("  'd' columns are fv-on minus baseline, the phase force-velocity adds.\n")
    print("   fv     K    f Hz | muscle   d_musc | curv     d_curv | plant ph  d_plant  gain ratio")
    for fv in FV_VALUES:
        for mi in MEDIA_IX:
            for f in FREQS:
                g = fvagg.get((fv, mi, f))
                b = base.get((mi, f))
                if not g or not b:
                    continue
                musc, musc0 = stage(g, "tens_p", "rel_p"), stage(b, "tens_p", "rel_p")
                curv, curv0 = stage(g, "curv_p", "tens_p"), stage(b, "curv_p", "tens_p")
                pl, pl0 = stage(g, "curv_p", "drive_p"), stage(b, "curv_p", "drive_p")
                print("  %5.0f %5.2f  %4.2f | %+6.1f  %+6.1f | %+6.1f  %+6.1f | %+7.1f  %+6.1f    %.2f"
                      % (fv, sweep[mi].anisotropy, f, musc, _wrap(musc - musc0),
                         curv, _wrap(curv - curv0), pl, _wrap(pl - pl0),
                         m(g, "curv_a") / max(m(b, "curv_a"), 1e-12)))
            print()

    print("  PREDICTED CROSSOVER (criterion 0 deg, loop sign inside the plant)")
    print("   fv     K    | predicted f | fv=0 predicted | closed-loop record")
    verdict_rows = {}
    for fv in (0.0,) + FV_VALUES:
        for mi in MEDIA_IX:
            src = base if fv == 0.0 else fvagg
            key = (lambda f: (mi, f)) if fv == 0.0 else (lambda f: (fv, mi, f))
            pts = []
            for f in FREQS:
                g = src.get(key(f))
                if g:
                    pts.append((f, stage(g, "curv_p", "drive_p") + _receptor_phase(f)))
            pred = _crossover(sorted(pts))
            verdict_rows[(fv, mi)] = pred
            rec = ""
            if fv == 500.0 and mi in CLOSED_LOOP_FV500:
                rec = "%.3f  <- validation" % CLOSED_LOOP_FV500[mi]
            elif fv == 0.0 and mi in MEASURED_F0:
                rec = "%.3f" % MEASURED_F0[mi]
            print("  %5.0f %5.2f  |    %5.3f    |     %5.3f      |  %s"
                  % (fv, sweep[mi].anisotropy, pred,
                     verdict_rows.get((0.0, mi), float("nan")), rec))
        print()

    # Verdict material: the fv-added plant phase at the two ends, and the span motion.
    print("  VERDICT MATERIAL")
    for fv in FV_VALUES:
        deltas = {}
        for mi in MEDIA_IX:
            ds = []
            for f in FREQS:
                g, b = fvagg.get((fv, mi, f)), base.get((mi, f))
                if g and b:
                    ds.append(_wrap(stage(g, "curv_p", "drive_p")
                                    - stage(b, "curv_p", "drive_p")))
            if ds:
                deltas[mi] = float(np.mean(ds))
        if len(deltas) == 3:
            print("    fv %4.0f: plant phase added at K 40 / 7.9 / 1.58: "
                  "%+.1f / %+.1f / %+.1f deg" % (fv, deltas[8], deltas[4], deltas[0]))
            spread = deltas[0] - deltas[8]
            print("             load-dependence of that phase (thin minus thick): %+.1f deg"
                  % spread)
            s0 = verdict_rows.get((0.0, 0), float("nan")) / verdict_rows.get((0.0, 8), 1.0)
            s1 = verdict_rows.get((fv, 0), float("nan")) / verdict_rows.get((fv, 8), 1.0)
            print("             predicted span: %.3f against %.3f at fv = 0" % (s1, s0))
    print()
    print("  Outcomes were fixed in the docstring before the run: load-scaled time if the")
    print("  added phase grows as K falls and the predicted span widens; flat if the added")
    print("  phase is K-independent (params.py's cancellation suspicion, confirmed); brake")
    print("  if there is no added phase at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
