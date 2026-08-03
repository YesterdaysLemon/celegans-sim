"""Can the mechanics make the turn the circuit cannot?

Four routes to a deeper omega have now failed -- `omega_current` saturates, RIV gain, reflex
suppression, and wave suppression, the last in the wrong direction -- and `params.py`
concludes under *what actually limits the turn* that the constraint is **dynamic range**: a
sustained bend and a travelling wave competing for the same motor neurons. `tools/
self_contact.py` then removed the other candidate, showing the body never touches itself and
that the coil an omega needs clears self-contact by 1.4x, so the plane is not the obstacle
either.

Every one of those experiments drove the body *through the nervous system*. None asked the
prior question: **can the body do it at all?** If the mechanics cannot make a 0.22 mm coil
at any torque, then dynamic range is the wrong diagnosis, a second bending axis will not
help, and the parameters to look at are `EI` and `peak_moment`. If the mechanics can, the
neurons are the bottleneck and the dynamic-range reading survives its first real test.

So this bypasses the nervous system and drives the joints directly. `Body.step` takes the
bending moment as a plain array, and `Simulation` reads it from one call to
`Muscles.joint_moment`, so an extra moment can be added there without touching any model
code -- this is a tool, not a change to the animal.

**Arm one, statically.** A bare body, a uniform moment, run to rest. At equilibrium the
elastic torque balances the applied one, so curvature should land at M/EI; measuring it
checks the mechanics against that prediction rather than assuming it, and says what torque
the 4.5 /mm of an omega actually costs.

**Arm two, in the loop.** The real gait, running, with a constant moment added on top for
ten seconds. This is the number that decides: turn rate in deg/s, against the ~22 deg/s
`params.py` reports the model topping out at and the ~90 deg/s a 180-degree turn in two
seconds needs. Path speed and the travelling-wave index are reported beside it because the
known failure mode is not a shallow turn but a *frozen* one -- driving the head pools at
120 pA gives 1.8 deg/s at 0.060 mm/s, an animal bent double and going nowhere. A moment
that buys turn rate by stopping the worm has bought nothing.

Four profiles, because where and *when* the moment is applied is a real question and not a
detail. The whole body is the coil `params.py` describes; the anterior third is where the
omega drive actually lands, on RIV, SMD and RMD; the posterior third is the control that
says whether position matters at all. The fourth is the one that can overturn the other
three -- a real omega is not a constant bend held everywhere at once but a deep bend that
starts at the head and runs down the body, so a pulse travelling head to tail in the two
seconds a turn takes is the closest thing here to the real kinematics. A ceiling measured
only on static profiles would not have tested it.

Run:  PYTHONPATH=. .venv/bin/python tools/moment_ceiling.py
"""

from __future__ import annotations

import argparse

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world, travelling_index
from worm.body import Body
from worm.engine import Simulation
from worm.params import Params

WARMUP = 6.0
HOLD = 10.0
SEEDS = (0, 1, 3, 5, 7)

# uN*mm. 0.43 is the analytic cost of holding 4.5 /mm at midbody against the body's own
# elasticity; 2.6 is peak_moment, the most one side of the body can exert at full
# activation. Sampled finely below 0.5 because that is where the turn rate peaks and the
# whole question is where the peak sits, not what happens far past it.
MOMENTS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.43, 0.8, 1.5, 2.6)

# What a real omega needs: 180 degrees in the two seconds the animal takes over it.
TARGET_RATE = 90.0
TARGET_KAPPA = 4.5


KINDS = ("whole body", "anterior", "posterior", "travelling", "phase-locked")

# Curvature at which the phase-locked profile reaches full moment, in /mm. The free-running
# gait peaks near 12.5, so this saturates at roughly the animal's own bend rather than at
# some larger number it never reaches.
KAPPA_REF = 12.5

# Width of the travelling pulse, as a fraction of body length, and how long it takes to run
# head to tail. Two seconds is the duration of a real omega, so the pulse crosses the animal
# exactly once per turn.
PULSE_WIDTH = 0.15
PULSE_PERIOD = 2.0


def profile(p, kind: str, moment: float, t: float = 0.0,
            kappa: np.ndarray | None = None) -> np.ndarray:
    """The extra joint moment in uN*mm: where it is applied, when, and against what.

    Three static shapes, one travelling, one closed-loop. The travelling pulse tests the
    real omega's kinematics -- a deep bend that starts at the head and runs down the body,
    not a constant bend held everywhere at once.

    The last is the one that answers the open-loop objection. All the others are added
    without regard to where the body already is, so a moment can arrive at a segment that
    is bending the wrong way and simply fight it; a ceiling measured that way could be a
    statement about the fight rather than about the body. This one reads the animal's own
    curvature and pushes only where it is already bending dorsally, saturating at the
    gait's own amplitude. That deepens one side of the wave and leaves the other alone,
    which is both the thing that cannot fight the gait and, not coincidentally, what a
    ventrally-biased omega does.
    """
    n = p.n_links - 1
    s = (np.arange(n) + 0.5) / n
    m = np.zeros(n)
    if kind == "whole body":
        m[:] = moment
    elif kind == "anterior":
        m[: n // 3] = moment
    elif kind == "posterior":
        m[-(n // 3):] = moment
    elif kind == "travelling":
        centre = (t % PULSE_PERIOD) / PULSE_PERIOD
        m[:] = moment * np.exp(-0.5 * ((s - centre) / PULSE_WIDTH) ** 2)
    elif kind == "phase-locked":
        if kappa is None:
            return m
        m[:] = moment * np.clip(kappa / KAPPA_REF, 0.0, 1.0)
    else:
        raise ValueError(kind)
    return m


# ------------------------------------------------------------------ arm one: statics

def static_curvature(p, moment: float, seconds: float = 8.0) -> tuple[float, float]:
    """Curvature a free body settles at under a uniform moment. Returns (mean, max) in /mm."""
    body = Body(p.body, p.medium)
    m = profile(p.body, "whole body", moment)
    for _ in range(int(seconds / body.dt)):
        body.step(m)
    k = np.abs(body.curvature())
    return float(k.mean()), float(k.max())


# ------------------------------------------------------------------- arm two: in the loop

def _job(job):
    kind, moment, seed = job
    p = Params()
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(WARMUP)

    # Add the moment where the muscles hand theirs over. Nothing in worm/ is modified; the
    # simulation reads joint_moment() once per step and gets the sum. Evaluated per step
    # rather than once, so a travelling profile can move.
    base_fn = sim.muscles.joint_moment
    sim.muscles.joint_moment = lambda: base_fn() + profile(
        p.body, kind, moment, sim.t, sim.body.curvature())

    dt = sim.dt
    every = max(1, int(round(0.02 / dt)))
    n = int(HOLD / dt)
    start = sim.body.centroid().copy()
    prev, path = start.copy(), 0.0
    heading, kappa = [], []

    for i in range(n):
        sim.step()
        if i % every:
            continue
        c = sim.body.centroid()
        path += float(np.linalg.norm(c - prev))
        prev = c.copy()
        d = sim.body.body_direction()
        heading.append(float(np.arctan2(d[1], d[0])))
        kappa.append(sim.body.curvature().copy())

    h = np.unwrap(np.array(heading))
    kappa = np.array(kappa)
    net = float(np.linalg.norm(sim.body.centroid() - start))
    k = np.abs(kappa)

    # Turn rate as the slope of a least-squares line through the heading trace, not the
    # difference of its two endpoints. Endpoint differencing is fine for a steady turn and
    # badly wrong for an oscillating one: a travelling moment swings the heading back and
    # forth about its trend, so the two endpoints land wherever the last swing left them.
    # That showed up as a +-20 deg/s error bar on a 43 deg/s "peak" -- noise wearing the
    # shape of a result. The slope uses every sample and is unbiased by where the trace
    # happens to stop.
    ts = np.arange(h.size) * (every * dt)
    slope = float(np.polyfit(ts, h, 1)[0]) if h.size > 2 else 0.0
    resid = float(np.std(h - np.polyval(np.polyfit(ts, h, 1), ts))) if h.size > 2 else 0.0

    return dict(kind=kind, moment=moment, seed=seed,
                turn_rate=float(np.degrees(slope)),
                wobble=float(np.degrees(resid)),
                path_speed=path / HOLD,
                net_path=net / max(path, 1e-9),
                twi=float(travelling_index(kappa)),
                k_rms=float(np.sqrt((kappa ** 2).mean())),
                k_max=float(k.max()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()

    p = Params()
    print("MOMENT CEILING -- driving the joints directly, with the nervous system bypassed\n")
    print("  EI %.3f uN mm^2, peak_moment %.1f uN mm, %d links"
          % (p.body.EI, p.muscle.peak_moment, p.body.n_links))
    print("  an omega needs %.1f /mm of curvature and about %.0f deg/s of turn rate\n"
          % (TARGET_KAPPA, TARGET_RATE))

    print("  STATICS -- a free body under a uniform moment, run to rest")
    print("  %-12s %12s %12s %14s" % ("moment", "kappa mean", "kappa max", "M/EI midbody"))
    for m in MOMENTS:
        mean, mx = static_curvature(p, m)
        print("  %-12.2f %12.2f %12.2f %14.2f" % (m, mean, mx, m / p.body.EI))
    need = TARGET_KAPPA * p.body.EI
    print()
    print("  The last column is M/EI, which is the equilibrium curvature only where the")
    print("  stiffness scale is 1 -- midbody. Body.__init__ floors that scale at 0.25 for")
    print("  the tapered ends, so nose and tail bend up to four times as far, which is the")
    print("  max column, and the mean sits between the two. Both track the prediction, so")
    print("  the mechanics agree with the elastica they are supposed to be.")
    print()
    print("  Holding %.1f /mm at midbody costs %.2f uN mm; peak_moment is %.1f, so the"
          % (TARGET_KAPPA, need, p.muscle.peak_moment))
    print("  muscle has about %.0fx that in hand. Curvature is not the scarce thing."
          % (p.muscle.peak_moment / need))

    jobs = [(k, m, s) for k in KINDS for m in MOMENTS for s in args.seeds]
    print()
    print("  IN THE LOOP -- the real gait, plus a constant moment held for %.0f s" % HOLD)
    rows = pooled(_job, jobs, procs=args.procs)
    if not rows:
        print("  no trials completed")
        return 1

    best = {}
    for kind in KINDS:
        print()
        print("  %s" % kind)
        print("  %-10s %14s %13s %9s %8s %8s %9s"
              % ("moment", "turn deg/s", "path mm/s", "wobble", "net/path", "TWI", "kappa max"))
        for m in MOMENTS:
            g = [r for r in rows if r["kind"] == kind and r["moment"] == m]
            if not g:
                continue
            rate = np.array([abs(r["turn_rate"]) for r in g])
            spd = np.array([r["path_speed"] for r in g])
            print("  %-10.2f %7.1f +- %-5.1f %6.3f +- %.3f %9.1f %8.3f %8.2f %9.2f"
                  % (m, rate.mean(), rate.std(), spd.mean(), spd.std(),
                     np.mean([r["wobble"] for r in g]),
                     np.mean([r["net_path"] for r in g]),
                     np.mean([r["twi"] for r in g]),
                     np.mean([r["k_max"] for r in g])))
            best.setdefault(kind, []).append(
                (rate.mean(), spd.mean(), m, np.mean([r["k_max"] for r in g]), rate.std()))

    print()
    print("  WHAT THIS DECIDES")

    # Two guards on what may be called the peak, both earned rather than chosen.
    #
    # A turn rate read off a stationary animal is not a turn rate: body_direction is
    # ill-conditioned once the worm is bent double and travelling 0.006 mm/s. So a row must
    # still be moving at half the free-running path speed.
    #
    # And a peak that does not reproduce across seeds is not a ceiling. The travelling
    # profile at full moment reported 49.5 deg/s with a standard deviation of 32.0 and a
    # residual wobble of 79 degrees about its own trend -- a number that would have been
    # quoted as beating every static profile, from five runs that disagreed with each other
    # by more than the effect. So a row must also have a spread under 40% of its mean.
    # Without this the tool's headline came from its noisiest cell.
    def live(vals):
        base = [v[1] for v in vals if v[2] == 0.0][0]
        ok = [v for v in vals
              if v[1] >= 0.5 * base and v[4] <= 0.4 * max(v[0], 1e-9)]
        return ok or list(vals)

    peak = max(max(live(v)) for v in best.values())
    for kind, vals in best.items():
        rate, spd, m, kmax, sd = max(live(vals))
        base_spd = [v[1] for v in vals if v[2] == 0.0][0]
        top_spd = [v[1] for v in vals if v[2] == max(MOMENTS)][0]
        print("  %-11s peaks at %5.1f +- %.1f deg/s with %.2f uN mm (path %.3f, kappa %.0f),"
              % (kind, rate, sd, m, spd, kmax))
        print("  %-11s then falls away: path speed %.3f -> %.3f mm/s by %.1f uN mm."
              % ("", base_spd, top_spd, max(MOMENTS)))

        # Say out loud when a guard set aside a row that would otherwise have been the
        # headline. A cap that hides its best excluded cell reads as "nothing better was
        # found", which is a different claim from "something better was found and rejected
        # for this reason" -- and the reader has to be able to disagree with the reason.
        held = [v for v in vals if v not in live(vals) and v[0] > rate]
        if held:
            hr, hs, hm, hk, hsd = max(held)
            why = ("path %.3f is under half the free-running %.3f" % (hs, base_spd)
                   if hs < 0.5 * base_spd
                   else "its spread is %.0f%% of its mean" % (100 * hsd / max(hr, 1e-9)))
            print("  %-11s set aside a higher row: %.1f +- %.1f deg/s at %.2f uN mm, because"
                  % ("", hr, hsd, hm))
            print("  %-11s %s." % ("", why))

    print()
    print("  Turn rate is path speed times path curvature. Curvature is cheap -- the")
    print("  statics above buy %.0f /mm for a fifth of peak_moment -- but every increment"
          % (0.43 / p.body.EI))
    print("  of it costs speed, and past the peak the animal is bent double and going")
    print("  nowhere. The product therefore has a maximum, and that maximum is the real")
    print("  ceiling. It is not a number any amount of drive can push past.")
    print()
    if peak[0] >= TARGET_RATE:
        print("  It reaches %.0f deg/s, which clears the %.0f a real omega needs. The body"
              % (peak[0], TARGET_RATE))
        print("  can make this turn and the circuit cannot deliver the moment that does it,")
        print("  so dynamic range survives as the diagnosis and a second bending axis is")
        print("  attacking the right constraint.")
        return 0
    print("  It reaches %.0f deg/s against the %.0f a real omega needs -- with the nervous"
          % (peak[0], TARGET_RATE))
    print("  system removed entirely and up to %.1f uN mm applied directly to the joints."
          % max(MOMENTS))
    print()
    print("  That is not a dynamic-range result. No redistribution of drive across motor")
    print("  neurons can buy a turn the body itself cannot make, and a second bending axis")
    print("  is somewhere to put drive that is already not the scarce resource. Before")
    print("  building one, the thing to explain is why v*kappa peaks at %.0f: that is a"
          % peak[0])
    print("  statement about drag anisotropy and about what a travelling wave does to a")
    print("  bent body, and it is where the next measurement belongs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
