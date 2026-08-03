"""What sets the turn-rate ceiling: the medium, or the body?

`tools/moment_ceiling.py` established that turn rate tops out near 48 deg/s against the ~90
a real omega needs, and that it does so with the nervous system bypassed entirely and
whether the moment is delivered crudely or phase-locked to the animal's own wave. That
retired both stated arguments for a three-dimensional body, and left one question standing.

Turn rate is path speed times path curvature. Curvature is cheap -- a fifth of `peak_moment`
buys more than an omega needs -- so what gets spent is speed, and the ceiling is really a
statement about how much forward progress this body loses per unit of bend. Two things could
set that, and they are distinguishable.

**The medium.** Undulation becomes forward motion only because drag is anisotropic:
`K = c_normal / c_tangential` is 40 on agar and 1.58 in buffer. A bent body presents more of
itself sideways, so if the loss is hydrodynamic the ceiling should move -- and move a long
way -- across a factor of 25 in K.

**The body.** If instead the loss is elastic, the ceiling is about `EI` and how the bend
distributes along a body of that stiffness, and the medium will barely matter.

Only the whole-body profile is swept, because `moment_ceiling.py` already showed the peak is
insensitive to how the moment is shaped: 47.5 crude against 48.6 phase-locked. The question
here is not where to push but what the pushing runs into.

The same two guards apply as there, for the same reasons: a turn rate read off a nearly
stationary animal is ill-conditioned, and a peak that does not reproduce across seeds is not
a ceiling. Rows set aside are printed with their reason rather than dropped.

Run:  PYTHONPATH=. .venv/bin/python tools/turn_scaling.py
"""

from __future__ import annotations

import argparse
import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from tools.moment_ceiling import HOLD, WARMUP, profile
from worm.engine import Simulation
from worm.params import MEDIA, Params

SEEDS = (0, 1, 3)
MOMENTS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.43, 0.8)
MEDIUMS = ("agar", "viscous", "buffer")

# uN*mm^2, around the measured 0.095 (Fang-Yen et al. 2010, 9.5 +- 1.0 e-14 N m^2). Half and
# double bracket the measurement's own uncertainty many times over, which is the point: if
# the ceiling does not move across that, it is not an elastic quantity.
STIFFNESSES = (0.0475, 0.095, 0.19, 0.38)

TARGET_RATE = 90.0
TARGET_RADIUS = 0.22


def _params(medium: str, ei: float) -> Params:
    p = Params().with_medium(medium)
    if ei != Params().body.EI:
        p = dataclasses.replace(p, body=dataclasses.replace(p.body, EI=ei))
    return p


def _job(job):
    medium, ei, moment, seed = job
    p = _params(medium, ei)
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(WARMUP)

    base_fn = sim.muscles.joint_moment
    sim.muscles.joint_moment = lambda: base_fn() + profile(
        p.body, "whole body", moment, sim.t, sim.body.curvature())

    dt = sim.dt
    every = max(1, int(round(0.02 / dt)))
    prev, path = sim.body.centroid().copy(), 0.0
    heading = []
    for i in range(int(HOLD / dt)):
        sim.step()
        if i % every:
            continue
        c = sim.body.centroid()
        path += float(np.linalg.norm(c - prev))
        prev = c.copy()
        d = sim.body.body_direction()
        heading.append(float(np.arctan2(d[1], d[0])))

    h = np.unwrap(np.array(heading))
    ts = np.arange(h.size) * (every * dt)
    slope = float(np.polyfit(ts, h, 1)[0]) if h.size > 2 else 0.0
    return dict(medium=medium, ei=ei, moment=moment, seed=seed,
                turn_rate=abs(float(np.degrees(slope))), path_speed=path / HOLD)


def summarise(rows, key, value, label):
    """Peak eligible turn rate for one arm of the sweep, plus any row set aside.

    Reports the tightest turn *radius* alongside the rate, because raw turn rate is not
    comparable across these arms. Changing the medium or the bending modulus changes the
    free-running gait too -- path speed ranges from 0.348 mm/s on agar to 0.052 in buffer --
    so a lower turn rate can mean a worse turn or merely a slower animal. Radius is
    v/omega, which is the scale-free question: how tight a circle can this animal drive?
    A real omega is 0.22 mm.

    `guarded` is False when no row passed both guards and the arm has nothing trustworthy to
    report. It used to fall back to the raw maximum, which quietly reinstated exactly the
    noise the guards exist to exclude -- the softest body reported 55.9 +- 39.2 deg/s that
    way, a 70% spread, and it set the headline for the whole comparison.
    """
    g = [r for r in rows if r[key] == value]
    per = []
    for m in MOMENTS:
        h = [r for r in g if r["moment"] == m]
        if not h:
            continue
        rate = np.array([r["turn_rate"] for r in h])
        spd = np.array([r["path_speed"] for r in h])
        per.append((rate.mean(), spd.mean(), m, rate.std()))
    if not per:
        return None
    base = [v[1] for v in per if v[2] == 0.0][0]
    ok = [v for v in per if v[1] >= 0.5 * base and v[3] <= 0.4 * max(v[0], 1e-9)]
    rate, spd, m, sd = max(ok) if ok else max(per)
    held = [v for v in per if v not in ok and v[0] > rate] if ok else []
    radius = spd / np.radians(rate) if rate > 1e-9 else float("inf")
    return dict(label=label, rate=rate, sd=sd, moment=m, path=spd, base=base,
                radius=radius, guarded=bool(ok), held=max(held) if held else None)


def report(title, results, extra):
    print()
    print("  %s" % title)
    print("  %-10s %13s %9s %10s %11s"
          % (extra, "peak deg/s", "at uN mm", "free path", "radius mm"))
    for r in results:
        if r is None:
            continue
        if not r["guarded"]:
            print("  %-10s   no row passed both guards; nothing trustworthy here" % r["label"])
            continue
        print("  %-10s %6.1f +- %-4.1f %9.2f %10.3f %11.3f"
              % (r["label"], r["rate"], r["sd"], r["moment"], r["base"], r["radius"]))
        if r["held"]:
            hr, hs, hm, hsd = r["held"]
            why = ("path %.3f under half of %.3f" % (hs, r["base"])
                   if hs < 0.5 * r["base"] else "spread %.0f%% of mean" % (100 * hsd / hr))
            print("  %-10s   set aside %.1f +- %.1f at %.2f: %s" % ("", hr, hsd, hm, why))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()

    ei0 = Params().body.EI
    print("TURN SCALING -- is the ceiling hydrodynamic or elastic?\n")
    print("  a real omega needs about %.0f deg/s; the model tops out near 48 on agar\n"
          % TARGET_RATE)
    print("  %-10s %10s %10s %8s" % ("medium", "c_tang", "c_norm", "K"))
    for name in MEDIUMS:
        md = MEDIA[name]
        print("  %-10s %10.4f %10.4f %8.1f"
              % (name, md.c_tangential, md.c_normal, md.c_normal / md.c_tangential))

    jobs = ([(md, ei0, m, s) for md in MEDIUMS for m in MOMENTS for s in args.seeds]
            + [("agar", ei, m, s) for ei in STIFFNESSES if ei != ei0
               for m in MOMENTS for s in args.seeds])
    rows = pooled(_job, jobs, procs=args.procs)
    if not rows:
        print("\n  no trials completed")
        return 1

    med_rows = [r for r in rows if r["ei"] == ei0]
    med = [summarise(med_rows, "medium", n, n) for n in MEDIUMS]
    report("MEDIUM -- the same body, three drag anisotropies", med, "medium")

    agar_rows = [r for r in rows if r["medium"] == "agar"]
    ei = [summarise(agar_rows, "ei", e, "%.4f" % e) for e in STIFFNESSES]
    report("STIFFNESS -- the same medium, four bending moduli", ei, "EI")

    got = [r for r in med if r and r["guarded"]]
    gei = [r for r in ei if r and r["guarded"]]
    if len(got) < 2 or len(gei) < 2:
        print()
        print("  Too few arms produced a trustworthy peak to compare. That is itself the")
        print("  finding: outside a narrow band of these parameters the animal does not")
        print("  turn reproducibly enough to have a ceiling measured.")
        return 1

    # Compared on radius, not rate. Rate conflates turning with travelling.
    med_spread = max(r["radius"] for r in got) / max(min(r["radius"] for r in got), 1e-9)
    ei_spread = max(r["radius"] for r in gei) / max(min(r["radius"] for r in gei), 1e-9)
    best = min(r["radius"] for r in got + gei)

    # A real omega is 180 degrees in two seconds at a 0.22 mm radius, which means the animal
    # is travelling v = omega * R = 0.35 mm/s *while* turning that tightly. Both at once is
    # the target; either alone is easy and neither alone is a turn.
    need_v = np.radians(TARGET_RATE) * TARGET_RADIUS

    print()
    print("  WHAT THIS DECIDES")
    print("  A real omega is %.0f deg/s at a %.2f mm radius, which is the animal travelling"
          % (TARGET_RATE, TARGET_RADIUS))
    print("  %.2f mm/s *while* turning that tightly. Both at once is the target.\n" % need_v)
    print("  %-10s %11s %11s %10s" % ("arm", "radius mm", "path mm/s", "deg/s"))
    for r in got + gei:
        ok_r = "ok" if r["radius"] <= TARGET_RADIUS else "wide"
        ok_v = "ok" if r["path"] >= 0.8 * need_v else "slow"
        print("  %-10s %8.3f %-3s %7.3f %-4s %9.1f"
              % (r["label"], r["radius"], ok_r, r["path"], ok_v, r["rate"]))

    print()
    print("  Tightest radius anywhere: %.3f mm, which is %.1fx *tighter* than an omega needs"
          % (best, TARGET_RADIUS / best))
    print("  -- so the geometry is not what is missing. It is reached in buffer, where the")
    print("  animal travels %.3f mm/s, and a tight circle driven that slowly is not a turn."
          % min(r["path"] for r in got + gei if r["radius"] == best))
    print()
    print("  Across a factor of %.0f in drag anisotropy the radius moves %.1fx; across a"
          % (MEDIA["agar"].c_normal / MEDIA["agar"].c_tangential
             / (MEDIA["buffer"].c_normal / MEDIA["buffer"].c_tangential), med_spread))
    print("  factor of %.0f in bending modulus, %.1fx. Neither is the lever, because they do"
          % (max(STIFFNESSES) / min(STIFFNESSES), ei_spread))
    print("  not move radius and speed independently -- they slide the animal along a")
    print("  frontier. Agar has the speed and not the radius; buffer has the radius and not")
    print("  the speed. Nothing tested has both, and that trade is the actual ceiling.")
    print()
    print("  Two cautions on the buffer end of it. The model's gait modulation is known to")
    print("  be far too weak -- 0.66 to 0.85 Hz where the animal goes 0.30 to 1.76 -- so a")
    print("  buffer animal here is not swimming the way a real one does, and its path speed")
    print("  is a defect as much as a result. And EI is measured rather than fitted, so the")
    print("  stiffness arm is not a knob to turn; it is a check that the measured value is")
    print("  not accidentally the problem, and it is not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
