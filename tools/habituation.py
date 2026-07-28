"""Tap habituation: the first thing in this model that remembers anything.

Rankin, Beck & Chiba (1990) Behav. Brain Res. 37:89 tap the side of a plate at a fixed
interval and score the reversal each tap evokes. Three things happen, and a model that
reproduces one of them by construction has not reproduced habituation:

  decrement            the response falls away over roughly thirty taps, to somewhere
                       around half its initial size.
  interval dependence  a shorter interval habituates faster and deeper. This is the one
                       that separates habituation from fatigue or sensor saturation,
                       because both of those would care about the number of taps rather
                       than about their spacing.
  spontaneous recovery a rest restores the response, on the timescale of minutes.

All three follow from one depleting-resource equation in `SensoryParams`, so none of them
is fitted separately -- which is the point. What is fitted is a single rate constant.

The response is scored two ways from the same run, because they can disagree and the
disagreement is informative: the depolarisation of the backward command pool, which is
what the tap is supposed to cause, and the distance the animal actually reverses, which
is what Rankin could see. A model whose interneuron responds while its body does not has
a motor problem rather than a sensory one.

What it measures, and where it stops.

The receptor half works and is worth having. The resource depletes as taps accumulate and
refills between them, and it does so with the right *interval* dependence, which is the
part that could have failed and is a prediction of the equation rather than a fit:

   condition            resource after tap1   tap10   tap20
   use 6.0, ISI 10 s           0.667          0.251   0.248
   use 6.0, ISI 30 s           0.667          0.446   0.446

Same rate, same number of taps, and the animal tapped every ten seconds ends at half the
sensitivity of the one tapped every thirty. That is habituation rather than fatigue.

The behavioural half does not work, and the reason is not in this file. **A tap does not
reverse this animal at all.** Forward progress over the three seconds after a tap:

   no tap             +0.686 mm
   tap strength 1.4   +0.675 mm
   tap strength 4.2   +0.654 mm

A stimulus at three times the standard strength costs the animal 5% of its forward
progress and never reverses it. So there is no tap-withdrawal response for habituation to
decrement, and the reversal column in the table below is measuring ordinary forward
crawling through a sign convention rather than any response.

This is the same wall every other behaviour in this project has hit, and it is worth
stating in one place. The direction gate sits 3.81 standard deviations from its own
decision boundary (tools/command_probe.py); a tap moves the backward command pool by about
0.02 in activation, against the 0.107 it would need. Chemotaxis, aerotaxis, nociception,
tap withdrawal and now learning all fail at the same junction, for the same measured
reason, and none of them will work until the command layer has somewhere to move.

So: the memory is real, exact, dt-independent, and currently unobservable in behaviour.

Run:  PYTHONPATH=. .venv/bin/python tools/habituation.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP = 8.0
TAP_S = 0.05           # a tap is brief; given as a duration so it is step-size independent
TAP_STRENGTH = 1.4
SETTLE = 2.0           # window after each tap in which the response is scored
N_TAPS = 20


def _one_tap(sim, ava, tap=True):
    """Deliver one tap and score what it produced. Returns (AVA rise, reversal mm).

    The rise is a difference of *means* over matched windows either side of the tap, not
    a peak. A peak over a window is a biased estimator of a fluctuating signal -- it is
    positive with no stimulus at all -- and on this animal that bias is +0.070 against a
    real tap response of +0.020, so the first version of this assay was measuring almost
    entirely noise and reported habituation as absent when it was merely swamped.
    """
    before, after = [], []
    for _ in range(int(SETTLE / sim.dt)):
        sim.step()
        before.append(float(np.mean(sim.nervous.activation()[ava])))
    start = sim.body.centroid().copy()
    axis = sim.body.body_direction().copy()
    for _ in range(int(TAP_S / sim.dt)):
        if tap:
            sim.poke("anterior", strength=TAP_STRENGTH)
        sim.step()
    for _ in range(int(SETTLE / sim.dt)):
        sim.step()
        after.append(float(np.mean(sim.nervous.activation()[ava])))
    # Negative displacement along the body axis is backward, which is the response.
    backward = -float(np.dot(sim.body.centroid() - start, axis))
    return float(np.mean(after) - np.mean(before)), backward


def _job(job):
    use, tau, isi, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, touch_habituation_use=use, touch_habituation_tau=tau))
    sim = Simulation(p, seed=seed, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
    sim.run(WARMUP)
    ava = sim.senses.ava

    rises, backs, avail = [], [], []
    for _ in range(N_TAPS):
        r, b = _one_tap(sim, ava)
        rises.append(r)
        backs.append(b)
        avail.append(float(sim.senses.touch_avail[0]))
        rest = isi - TAP_S - 2 * SETTLE
        if rest > 0:
            sim.run(rest)

    # Spontaneous recovery: rest for five interval-lengths, then tap once more.
    sim.run(max(60.0, 5 * isi))
    rec_rise, rec_back = _one_tap(sim, ava)

    return dict(use=use, tau=tau, isi=isi, seed=seed,
                rises=rises, backs=backs, avail=avail,
                rec_rise=rec_rise, rec_back=rec_back)


def _mean(rows, key):
    return np.mean([r[key] for r in rows], axis=0)


def main():
    # One rate, two intervals: the comparison between them is the load-bearing one.
    jobs = [(use, 60.0, isi, seed)
            for use, isi in ((0.0, 10.0), (2.0, 10.0), (6.0, 10.0),
                             (15.0, 10.0), (6.0, 30.0))
            for seed in (1, 2, 3)]
    print("HABITUATION -- %d animals, %d taps each" % (len(jobs), N_TAPS))
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    groups = {}
    for r in rows:
        groups.setdefault((r["use"], r["isi"]), []).append(r)

    print()
    print("  AVA response to each tap (mean over animals)")
    print("  condition            tap1   tap2   tap5   tap10  tap20  | last/first | recovered")
    for key in sorted(groups):
        g = groups[key]
        m = _mean(g, "rises")
        lbl = ("no habituation" if key[0] == 0 else "use %.1f, ISI %2.0f s" % key)
        rec = np.mean([r["rec_rise"] for r in g])
        print("  %-19s %6.3f %6.3f %6.3f %6.3f %6.3f |   %5.2f    |  %6.3f"
              % (lbl, m[0], m[1], m[4], m[9], m[19],
                 m[19] / m[0] if abs(m[0]) > 1e-9 else float("nan"), rec))

    print()
    print("  reversal distance per tap, mm (what Rankin could actually see)")
    print("  condition            tap1   tap2   tap5   tap10  tap20  | last/first | recovered")
    for key in sorted(groups):
        g = groups[key]
        m = _mean(g, "backs")
        lbl = ("no habituation" if key[0] == 0 else "use %.1f, ISI %2.0f s" % key)
        rec = np.mean([r["rec_back"] for r in g])
        print("  %-19s %6.3f %6.3f %6.3f %6.3f %6.3f |   %5.2f    |  %6.3f"
              % (lbl, m[0], m[1], m[4], m[9], m[19],
                 m[19] / m[0] if abs(m[0]) > 1e-9 else float("nan"), rec))

    print()
    print("  receptor resource remaining")
    for key in sorted(groups):
        m = _mean(groups[key], "avail")
        lbl = ("no habituation" if key[0] == 0 else "use %.1f, ISI %2.0f s" % key)
        print("  %-19s  after tap1 %.3f   tap10 %.3f   tap20 %.3f"
              % (lbl, m[0], m[9], m[19]))

    print()
    print("  want: the response about halved by tap 20, the 10 s interval habituating")
    print("  deeper than the 30 s one, and a rest restoring most of it. The first is a")
    print("  fitted rate; the other two are predictions of the same equation and are the")
    print("  ones that would falsify it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
