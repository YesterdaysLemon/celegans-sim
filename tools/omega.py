"""The omega turn: what did not work, what did, and what it bought.

The omega turn was the missing half of this model's steering. Three taxis assays reported
a correct mechanism and a null outcome -- the pirouette ratio moved the right way, the
turning bias pointed the right way -- while nociception, the one behaviour needing no
reorientation, worked. A biased random walk needs a decision to reverse *and* a reversal
that points the animal somewhere new. The model had the first and not the second: median
reorientation 21 degrees, nothing above 120, against a real animal ending roughly 35% of
its reversals in a 160-170 degree turn.

## What did not work: amplifying RIV

RIV is the obvious candidate. It innervates ventral body muscle and nothing else -- nine
neuromuscular contacts, all ventral -- it is reached through RIA and SMDV rather than the
command pool, and it is 25% more active during reversals. It was given authority in all
three places a gain can go, and all three fail:

    conductance, after the muscle balance    gain 5: reorientation 18 -> 72 deg, but net
                                             speed 0.301 -> 0.027 mm/s. The balance
                                             cancels resting tone, so scaling after it
                                             amplifies RIV's tonic release and bends the
                                             animal permanently.
    conductance, before the balance          gain 8: 18.1 -> 14.6 deg. Nearly a no-op; the
                                             balance equalises each cell's total drive and
                                             divides the change back out.
    deviation from resting release           18 -> 55 deg, never once above 120, while net
                                             speed falls 81% and TWI +0.84 -> +0.74.

The third is the principled one and it fails too, which makes this a result about RIV
rather than about where a constant was multiplied. Why: over a 180 s run, **0.5% of RIV's
release variance is explained by the direction state and 99.5% is the undulation it rides
on**. A gain on RIV amplifies the gait two hundred times harder than the turn signal.

## What did work: an edge-locked differential

That diagnosis names the replacement. The driver must have reversal-locked variance, and
in the animal the turn is not part of the reversal -- it *follows* it, firing as forward
locomotion resumes. So the signal is an edge, not a level: on the backward-to-forward
transition a transient is injected and decays over omega_tau, and the undulation carries
the resulting bias down the body as a turn.

Two further things had to be right.

**It has to be a differential.** Driving the ventral pool alone saturates it without
bending the animal: 400 pA pins RIV and SMDV at an activation of 0.9999 and reaches a mean
head curvature of -0.56 /mm against an undulation of 4.5 rms. Driving the ventral pool
*and releasing its dorsal antagonist* reaches -6.4. The head is a set of antagonistic pairs
(SMDD/SMDV, RMDD/RMDV, SMBD/SMBV) that reads a difference -- the same lesson the ASE pair
and the command pools each taught in turn.

**And it has to be a transient, not a level.** Held on continuously, 150 pA and above
freezes the animal in a bent posture: the travelling index falls to +0.19 and path speed
to 0.03 mm/s, because saturating one side of the head motor pool stops it oscillating. A
decaying transient passes back through that region instead of sitting in it, which is why
300 pA works here and would not as a sustained drive.

## What it bought

Read the two speed columns in the table below together. *Path* speed barely moves while
*net* speed halves: that is not the animal slowing, it is its track becoming tortuous,
which is what turning means. The travelling index and curvature are untouched at 300 pA.

The fraction of reversals exceeding 120 degrees was never fitted. Amplitude is set by the
reversal's own duration against omega_ref_reversal, so short reversals earn shallow turns
and typical ones earn full-scale, and the *distribution* falls out: 32% of reversals past
120 degrees against roughly 35% of a real animal's ending in an omega turn.

Downstream, on the assays this was for:

    chemotaxis index      +0.002 -> +0.070      (real animal +0.5 or better)
    thermotaxis           the warm group now turns round, -2.96 mm towards cooler,
                          where before it did not turn at all
    aerotaxis             now descends the oxygen gradient, 16.5% -> 14.2% and reaching
                          9.8%, where before it ascended it
    ethogram, off food    median reorientation 21.1 -> 55.5 deg, 0% -> 24% above 120

All four now point the right way. None of them is yet at the animal's magnitude, and the
chemotaxis index in particular is seven times short, so this opens the problem rather than
closing it.

Run:  PYTHONPATH=. .venv/bin/python tools/omega.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 120.0
SEEDS = (0, 3, 7)
SETTLE = 2.0             # s each side of a reversal, to average out the head's own swing
# (current pA, decay s). The first row is the model with the turn switched off.
GRID = [(0.0, 1.5)] + [(c, t) for c in (80.0, 200.0, 300.0, 450.0) for t in (1.5, 2.0, 3.0)]


def _job(job):
    cur, tau, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, omega_current=cur, omega_tau=tau))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)

    heading, events, durs = [], [], []
    every = max(1, int(round(0.05 / sim.dt)))
    start, t0 = sim.body.centroid().copy(), sim.t
    prev, path = start.copy(), 0.0
    was, rev_n = True, 0
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            d = sim.body.body_direction()
            heading.append(float(np.arctan2(d[1], d[0])))
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
        fw = sim.senses.going_forward
        if not fw:
            rev_n += 1
        elif rev_n:                       # the reversal just ended: the turn happens here
            events.append(len(heading) - 1)
            durs.append(rev_n * sim.dt)
            rev_n = 0
        was = fw

    span = sim.t - t0
    speed = float(np.linalg.norm(sim.body.centroid() - start)) / span

    # Heading change across each reversal, averaged either side: the head of an undulating
    # worm swings far enough each cycle to swamp the reorientation being measured.
    h = np.unwrap(np.array(heading))
    w = int(SETTLE / 0.05)
    turns, tdur = [], []
    for i, d in zip(events, durs):
        if i - w >= 0 and i + w < len(h):
            turns.append(abs(float(np.degrees(h[i + w] - h[i - w]))))
            tdur.append(d)

    r = analyse(sim, seconds=30.0)
    return dict(cur=cur, tau=tau, seed=seed, turns=turns, durs=tdur,
                speed=speed, path_speed=path / span, twi=r["twi"], k_rms=r["kappa_rms"],
                rate=len(events) * 60.0 / MEASURE)


def main():
    jobs = [(c, t, s) for c, t in GRID for s in SEEDS]
    print("OMEGA TURNS -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  a transient on the reversal-to-forward edge: ventral head pool up, dorsal")
    print("  pool down, decaying over tau. Amplitude scales with the reversal's length.\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    p = Params().sensory
    print("    pA  tau | turns/min | reorientation deg (median / >120%) |"
          "  net   path    TWI   k_rms")
    for cur, tau in GRID:
        g = [r for r in rows if r["cur"] == cur and r["tau"] == tau]
        if not g:
            continue
        t = np.array([x for r in g for x in r["turns"]] or [0.0])
        f = lambda k: float(np.mean([r[k] for r in g]))            # noqa: E731
        mark = "  <- shipped" if (cur == p.omega_current and tau == p.omega_tau) else ""
        print("  %4.0f %4.1f |   %5.2f   |     %5.1f  / %3.0f%%  (n=%3d)       |"
              "  %.3f  %.3f  %+.2f  %5.2f%s"
              % (cur, tau, f("rate"), float(np.median(t)),
                 100 * float(np.mean(t > 120)), len(t),
                 f("speed"), f("path_speed"), f("twi"), f("k_rms"), mark))

    print()
    print("  Read the two speed columns together. Path speed barely moves while net speed")
    print("  halves: the animal is not slowing, its track is becoming tortuous, which is")
    print("  what turning means. A real animal ends ~35% of its reversals in an omega")
    print("  turn of 160-170 deg; the shipped row reaches 120+ on about a third of them.")

    print()
    print("  DOES A LONGER REVERSAL GIVE A DEEPER TURN?")
    print("  The amplitude is scaled by reversal duration, so this relationship is built")
    print("  in rather than fitted -- but it only survives into the *behaviour* over part")
    print("  of the grid. At tau 3.0 it inverts, because a turn that long is still running")
    print("  when the next reversal begins and the two overlap. That is a real limit on")
    print("  how long the transient can usefully be, and it is why the shipped tau is 1.5.")
    for cur, tau in GRID:
        g = [r for r in rows if r["cur"] == cur and r["tau"] == tau]
        T = np.array([x for r in g for x in r["turns"]])
        D = np.array([x for r in g for x in r["durs"]])
        if len(T) > 4 and D.std() > 0 and T.std() > 0:
            print("    %4.0f pA tau %.1f   corr = %+.2f   n=%d"
                  % (cur, tau, float(np.corrcoef(D, T)[0, 1]), len(T)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
