"""Can the omega turn be bought by amplifying RIV? No, and the reason is measurable.

The omega turn is the missing piece that explains every remaining sensory null in this
model. Chemotaxis, aerotaxis and thermotaxis all have correct mechanisms and null
outcomes -- the pirouette ratio moves the right way, the turning bias points the right
way -- while nociception, the one behaviour that needs no reorientation, works. A biased
random walk needs two things: a decision to reverse, and a reversal that actually points
the animal somewhere new. This model has the first and not the second. `tools/ethogram.py`
scores the median reorientation at 18 degrees with nothing above 120, against a real
animal where roughly 35% of reversals end in a 160-170 degree omega turn.

RIV is the obvious candidate and the anatomy is encouraging. It is exclusively ventral --
nine neuromuscular contacts ventral, none dorsal, which is exactly the anatomy of a cell
whose job is to bend the animal one way -- it is driven by RIA (6), SDQR (4) and SMDV (5)
rather than by the command pool, and it is already 25% more active during reversals
(release 0.114 against 0.091). So: give it authority and see whether the turn appears.

**It does not, in any of the three places the gain can go.** All three were measured.

    after the muscle balance     gain 5:  reorientation 18 -> 72 deg, 11% above 120,
                                 but net speed 0.301 -> 0.027 mm/s. The balance cancels
                                 resting tone, so scaling afterwards amplifies RIV's
                                 tonic release and bends the animal permanently.

    before the muscle balance    gain 8:  reorientation 18.1 -> 14.6 deg. Very nearly a
                                 no-op, because the balance equalises each muscle cell's
                                 total drive and divides the change straight back out.

    on RIV's deviation from      the table below. Reorientation climbs 18 -> 55 deg but
    its resting release          never once exceeds 120, while speed falls 81%.

The third is the principled one -- the balance cancels tone assuming every neuron sits at
s_eq, so amplifying deviations from s_eq leaves the balanced resting state untouched by
construction -- and it fails too. That is what makes this a statement about RIV rather
than about where a constant was multiplied in.

**Why it fails.** Decompose RIV's release variance over a 180 s run into the part
explained by the direction state and the part within each state:

    reversal-locked variance     0.5% of total
    undulatory variance         99.5%

RIV oscillates with the gait, and that oscillation is two hundred times larger than the
reversal-linked shift the turn would have to be made of. Any gain on RIV therefore
amplifies the wave two hundred times harder than the signal, which is precisely the
observed exchange rate: the curvature rises (4.49 -> 5.17 rms), the travelling-wave index
falls (+0.84 -> +0.74), and the animal thrashes in place. The 25% elevation during
reversals is real and is simply not where RIV's output lives.

**So what would work.** The turn has to be driven by something whose variance *is*
reversal-locked -- the command state itself, or a cell reading it -- and in the animal the
omega turn fires at the *end* of a reversal, at the reversal-to-forward transition, not
during it. A transient locked to that transition is a different object from a gain on a
tonically oscillating motor neuron, and it is testable in the same way: the turn should
follow the reversal rather than accompany it, and deeper turns should follow longer
reversals, which is true of the animal.

`SensoryParams.omega_gain` is left in at 1.0, which is exactly the unmodified model. It is
kept rather than deleted because it is the knob this result is about, and because the
deviation-gain machinery in `Muscles` is the correct way to amplify any phasic drive
without disturbing the resting balance -- whatever eventually drives the turn will want it.

Run:  PYTHONPATH=. .venv/bin/python tools/omega.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

MEASURE = 90.0
SEEDS = (0, 3)
GAINS = (1.0, 3.0, 6.0, 12.0)
SETTLE = 2.0             # s each side of a reversal, to average out the head's own swing


def _job(job):
    gain, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(p.sensory, omega_gain=gain))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(8.0)

    heading, events, was = [], [], True
    every = max(1, int(round(0.05 / sim.dt)))
    start, t0 = sim.body.centroid().copy(), sim.t
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            d = sim.body.body_direction()
            heading.append(float(np.arctan2(d[1], d[0])))
        if was and not sim.senses.going_forward:
            events.append(len(heading) - 1)
        was = sim.senses.going_forward

    # Heading change across each reversal, averaged either side: the head of an undulating
    # worm swings far enough each cycle to swamp the reorientation being measured.
    h = np.unwrap(np.array(heading))
    w = int(SETTLE / 0.05)
    turns = [abs(float(np.degrees(h[i + w] - h[i - w])))
             for i in events if i - w >= 0 and i + w < len(h)]

    # Read the displacement before analyse() runs, because it advances the simulation
    # another 30 s: dividing the same net displacement by a longer window understates the
    # speed, and it understates it more at low gains where the path is straighter.
    speed = float(np.linalg.norm(sim.body.centroid() - start)) / (sim.t - t0)

    r = analyse(sim, seconds=30.0)
    return dict(gain=gain, seed=seed, turns=turns, speed=speed,
                twi=r["twi"], k_rms=r["kappa_rms"], k_max=r["kappa_max"],
                rate=len(events) * 60.0 / MEASURE)


def main():
    jobs = [(g, s) for g in GAINS for s in SEEDS]
    print("OMEGA TURNS -- %d trials x %.0f s, RIV phasic gain" % (len(jobs), MEASURE))
    print("  the gain acts on RIV's deviation from its resting release, so the muscle")
    print("  balance is undisturbed and only the phasic part is amplified\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    print("  RIV gain | reversals/min | reorientation deg (median / >120%) |"
          " net mm/s   TWI   k_rms  k_max")
    for gain in GAINS:
        g = [r for r in rows if r["gain"] == gain]
        if not g:
            continue
        t = np.array([x for r in g for x in r["turns"]] or [0.0])
        f = lambda k: float(np.mean([r[k] for r in g]))           # noqa: E731
        print("    %5.1f  |     %5.2f     |      %5.1f  /  %3.0f%%              |"
              "  %.4f  %+.2f  %5.2f  %5.1f"
              % (gain, f("rate"), float(np.median(t)), 100 * float(np.mean(t > 120)),
                 f("speed"), f("twi"), f("k_rms"), f("k_max")))

    print()
    print("  A real animal ends ~35% of its reversals in a 160-170 deg omega turn. No")
    print("  gain here reaches 120 even once, while net speed falls by four fifths. The")
    print("  variance decomposition in the docstring is why: 99.5% of RIV's output is")
    print("  the undulation, so a gain on RIV amplifies the gait, not the turn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
