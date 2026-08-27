"""The ethogram: what the animal does with its time, scored against tracker data.

Locomotion in this model is well measured -- speed, wavelength, frequency, travelling-wave
index all have tests. What has never been measured is the thing a worm tracker actually
prints: how often the animal reverses, how long its forward runs last, how far it turns
when it does reverse, and how all of that changes on food. Those statistics *are* the
behaviour. C. elegans chemotaxis is a biased random walk (Pierce-Shimomura, Morse & Lockery
1999): the animal does not steer up a gradient, it suppresses reversals while things are
improving. So a worm that never reverses cannot chemotax no matter how good its nose is,
and the chemotaxis null in the day-four notes may be a statement about the ethogram rather
than about the senses.

Targets, from freely-moving trackers on plain agar and on a lawn:

    reversal rate, off food      3.2-3.5 /min      Zhao et al. 2003
    reversal rate, on food       0.7-1.25 /min     Zhao et al. 2003
    forward run duration         exponential-ish, CV near 1
    reorientation per reversal   large; omega turns reach 160-170 deg

Two independent definitions of "reversal" are reported, and the gap between them is
diagnostic:

    commanded   the direction gate in Senses.sense fell below 0.5 -- what the circuit
                decided.
    mechanical  the centroid travelled tail-first -- what the body did. This is the same
                detector the assays use, and per NEXT.md it is only meaningful when
                net/path is above ~0.3, which is reported alongside it.

A circuit that decides to reverse but a body that never does is a motor problem; neither
happening is a command problem. The last block separates them by measuring how far the
command sits from its own decision boundary, in units of its own fluctuation -- if that
margin is several sigma, reversals are rare for an entirely quantitative reason and no
amount of sensory gain will change it.

Run:  PYTHONPATH=. .venv/bin/python tools/ethogram.py
"""

from __future__ import annotations

import numpy as np

from tools.assays import SAMPLE_DT, estimate, pooled, reversals, run_trial
from worm.params import Params
from worm.world import World

DURATION = 200.0        # s per animal, after the 6 s settle the harness discards
SEEDS = (0, 1, 2, 3, 4, 5)


# ------------------------------------------------------------------------------- plates
def _bare(p):
    """Plain agar: no food, no attractant, no obstacles. The off-food condition."""
    return World(p.world, np.random.default_rng(0))


def _lawn(p):
    """A lawn large enough that the animal stays on it for the whole run.

    The on-food condition has to keep the animal on food, or it measures a mixture. A
    worm at 0.25 mm/s covers 50 mm in 200 s, so the lawn is sized well past that and the
    animal starts at its centre. Attractant is switched off: this assay is about the
    behavioural state food induces, not about chemotaxis towards it.

    Since the sleep homeostat (worm/sleep.py), "the state food induces" includes sleep:
    on a lawn this dense pressure crosses threshold at about a minute, so the on-food
    rows are the fed and SOMETIMES SLEEPING animal -- near-zero reversals and speed for
    part of the window is the model now, not noise. For the awake-only comparison run
    the sleepless control (SleepParams.ris_drive = 0).
    """
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    return w


PLATES = {"off food": _bare, "on food": _lawn}


# ------------------------------------------------------------------------------ scoring
def _events(mask):
    """(onset, offset) index pairs for each run of True in a boolean array."""
    m = np.concatenate(([False], mask.astype(bool), [False]))
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d > 0), np.flatnonzero(d < 0)))


def _reorientation(tr, spans, settle=2.0, skip=5.0):
    """Heading change across each event, in degrees: the new run against the old.

    Measured from the mean heading over a window before the event to the mean heading
    over a window after it, rather than instantaneously: the head of an undulating worm
    swings far enough each cycle to swamp the reorientation being measured.

    The post window starts `skip` seconds after the event ends, not flush against it.
    The omega bias decays over seconds (SensoryParams.omega_tau) and the heading keeps
    rotating until it has spent itself, so a flush window averages the turn's INTERIOR
    -- a rotating heading -- and underreads the result. Measured 2026-08-27 on
    identical trajectories: at the shipped tau the flush window read a 53 deg median
    where the finished turn reads ~82; at a candidate tau of 2.5 s it INVERTED the
    sign of a paired treatment effect (deeper turns scored as shallower, because more
    of each turn fell inside the window). Events whose post window would run into the
    next event are dropped rather than contaminated.
    """
    w = max(1, int(round(settle / SAMPLE_DT)))
    k = int(round(skip / SAMPLE_DT))
    ang = np.arctan2(tr["dir_y"], tr["dir_x"])
    starts = [i0 for i0, _ in spans]
    out = []
    for n, (i0, i1) in enumerate(spans):
        j0 = i1 + k
        nxt = starts[n + 1] if n + 1 < len(spans) else len(ang)
        if j0 + w > nxt:
            continue
        pre, post = ang[max(0, i0 - w):i0], ang[j0:j0 + w]
        if len(pre) < w // 2 or len(post) < w // 2:
            continue
        a = np.arctan2(np.sin(post).mean(), np.cos(post).mean()) - \
            np.arctan2(np.sin(pre).mean(), np.cos(pre).mean())
        out.append(abs(np.degrees((a + np.pi) % (2 * np.pi) - np.pi)))
    return out


def _job(job):
    condition, seed = job
    p = Params()
    tr = run_trial(PLATES[condition], (0.0, 0.0, float((seed % 8) * np.pi / 4)),
                   DURATION, seed)
    span = tr["t"][-1] - tr["t"][0]
    minutes = span / 60.0

    # -- mechanical: what the body did ------------------------------------------------
    mech = reversals(tr)
    mech_ev = _events(mech)
    # -- commanded: what the circuit decided -------------------------------------------
    cmd = tr["gate_forward"] < 0.5
    cmd_ev = _events(cmd)

    # -- forward run durations, between commanded reversals ----------------------------
    runs = [(b - a) * SAMPLE_DT for a, b in _events(~cmd)]

    # -- how far the command sits from its own decision boundary -----------------------
    # fwd_frac = sigmoid(slope * (activity difference - bias)), so logit(fwd_frac)/slope
    # is exactly the signed distance from the 50/50 point in activation units. Its mean
    # over its own standard deviation is a pure number: how many of its own fluctuations
    # the command would have to move to change its mind.
    f = np.clip(tr["gate_forward"], 1e-12, 1 - 1e-12)
    margin = np.log(f / (1 - f))
    m_sd = float(margin.std())

    # -- path geometry, so the mechanical detector can be trusted or not ---------------
    step = np.hypot(np.diff(tr["x"]), np.diff(tr["y"]))
    net = float(np.hypot(tr["x"][-1] - tr["x"][0], tr["y"][-1] - tr["y"][0]))
    path = float(step.sum())
    heading = np.unwrap(np.arctan2(tr["dir_y"], tr["dir_x"]))
    heading_drift = float(np.degrees(heading[-1] - heading[0]) / span)

    return dict(
        condition=condition, seed=seed, minutes=minutes,
        mech_rate=len(mech_ev) / minutes, cmd_rate=len(cmd_ev) / minutes,
        frac_mech=float(mech.mean()), frac_cmd=float(cmd.mean()),
        run_mean=float(np.mean(runs)) if runs else float("nan"),
        run_cv=float(np.std(runs) / np.mean(runs)) if len(runs) > 1 and np.mean(runs) > 0
        else float("nan"),
        n_runs=len(runs),
        turn_mech=_reorientation(tr, mech_ev),
        gate_mean=float(tr["gate_forward"].mean()),
        gate_sd=float(tr["gate_forward"].std()),
        margin_sigma=float(margin.mean() / m_sd) if m_sd > 0 else float("nan"),
        speed=net / span, path_speed=path / span, net_path=net / max(path, 1e-9),
        heading_drift=heading_drift,
        food=float(np.mean(tr["attractant"])),
    )


# ------------------------------------------------------------------------------- report
def main():
    jobs = [(c, s) for c in PLATES for s in SEEDS]
    print("ETHOGRAM -- %d animals x %.0f s, off food and on food  (estimated %.0f s)"
          % (len(jobs), DURATION, estimate(len(jobs), DURATION)))
    rows = pooled(_job, jobs)
    if not rows:
        print("  no trials completed")
        return 1

    print()
    print("  condition    reversals/min          run s          net mm/s   net/path")
    print("               commanded  mechanical   mean    CV")
    for c in PLATES:
        g = [r for r in rows if r["condition"] == c]
        if not g:
            continue
        f = lambda k: np.nanmean([r[k] for r in g])              # noqa: E731
        sd = lambda k: np.nanstd([r[k] for r in g])              # noqa: E731
        print("  %-11s  %4.2f+-%4.2f  %4.2f+-%4.2f  %6.1f  %4.2f    %.4f     %.3f"
              % (c, f("cmd_rate"), sd("cmd_rate"), f("mech_rate"), sd("mech_rate"),
                 f("run_mean"), f("run_cv"), f("speed"), f("net_path")))
    print()
    print("  real animal:  3.2-3.5 /min off food, 0.7-1.25 /min on food (Zhao et al. 2003)")

    print()
    print("  WHERE THE COMMAND SITS")
    print("  condition    gate fwd (sd)    margin to the 50/50 point   time reversing")
    for c in PLATES:
        g = [r for r in rows if r["condition"] == c]
        if not g:
            continue
        f = lambda k: np.nanmean([r[k] for r in g])              # noqa: E731
        print("  %-11s  %.3f (%.3f)      %5.2f sigma                 %4.1f%% cmd / %4.1f%% mech"
              % (c, f("gate_mean"), f("gate_sd"), f("margin_sigma"),
                 100 * f("frac_cmd"), 100 * f("frac_mech")))
    print()
    print("  A margin of n sigma means the command's own fluctuations must reach n standard")
    print("  deviations to reverse. Under 2 sigma reversals are common; past 3 they are")
    print("  rare for a reason no sensory gain can fix, because a sensory input has to move")
    print("  the operating point by that whole distance before the decision changes.")

    turns = {c: [a for r in rows if r["condition"] == c for a in r["turn_mech"]]
             for c in PLATES}
    print()
    print("  REORIENTATION per mechanical reversal")
    for c in PLATES:
        t = turns[c]
        if t:
            print("  %-11s  n=%3d   median %5.1f deg   mean %5.1f   >120 deg: %.0f%%"
                  % (c, len(t), float(np.median(t)), float(np.mean(t)),
                     100 * float(np.mean(np.asarray(t) > 120))))
        else:
            print("  %-11s  no events" % c)
    print()
    print("  a real reversal reorients substantially, and ~35%% end in an omega turn of")
    print("  160-170 deg. This model is two-dimensional and has no omega mechanism, so a")
    print("  low number here is expected; it is recorded to have the baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
