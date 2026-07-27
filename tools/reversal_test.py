"""Does the animal reverse properly now that both cords are regenerative?

Forward locomotion must not regress, and backward locomotion must actually translate
rather than thrash. Both are measured the same way, with the sign of progress taken along
the body axis so that a good reversal scores positively.
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import estimate, pooled
from tools.diagnose_loop import travelling_index
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

WARMUP, MEASURE = 8.0, 26.0


def _bare(p):
    return World(p.world, np.random.default_rng(0))


def _job(job):
    mode, scale, seed = job
    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, a_class_scale=scale))
    sim = Simulation(p, seed=seed, world=_bare(p), placement=(0.0, 0.0, 0.0))
    names = list(sim.conn.names)
    ava = [i for i, n in enumerate(names) if n.startswith("AVA")]
    avb = [i for i, n in enumerate(names) if n.startswith("AVB")]
    dt = p.neural.dt

    def drive():
        # A reversal in this model is commanded by swapping which command interneuron is
        # held up. Clamping is blunt but unambiguous, which is what a test wants.
        if mode == "backward":
            sim.nervous.V[avb] = -60.0
            sim.nervous.I_ext[ava] = 0.0

    for _ in range(int(WARMUP / dt)):
        drive()
        sim.step()
    start = sim.body.centroid().copy()
    axis0 = sim.body.body_direction().copy()
    ks, path, prev = [], 0.0, start.copy()
    for i in range(int(MEASURE / dt)):
        drive()
        sim.step()
        if i % 20 == 0:
            ks.append(sim.body.curvature().copy())
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    K = np.array(ks)
    disp = sim.body.centroid() - start
    # Signed progress along the body axis: positive is nose-first, negative tail-first.
    along = float(np.dot(disp, axis0))
    return dict(mode=mode, scale=scale, seed=seed,
                speed=float(np.linalg.norm(disp)) / MEASURE,
                along=along / MEASURE,
                ratio=float(np.linalg.norm(disp)) / max(path, 1e-9),
                twi=travelling_index(K), k_rms=float(np.sqrt((K ** 2).mean())))


def main():
    scales = [0.0, 0.25, 0.5, 0.75, 1.0]
    jobs = [(m, sc, s) for m in ("forward", "backward")
            for sc in scales for s in (0, 3, 7)]
    print("estimated %.0f s for %d trials" % (estimate(len(jobs), WARMUP + MEASURE), len(jobs)))
    rows = pooled(_job, jobs)
    agg = {}
    for r in rows:
        agg.setdefault((r["mode"], r["scale"]), []).append(r)
    print("\n  mode       A-scale   speed mm/s   along-axis mm/s   net/path    TWI    k_rms")
    for (mode, sc), g in sorted(agg.items()):
        f = lambda k: np.mean([x[k] for x in g])              # noqa: E731
        note = "   <- B class only" if sc == 0.0 else ""
        print("  %-9s   %.2f      %.4f       %+.4f         %.3f    %+.3f   %5.2f%s"
              % (mode, sc, f("speed"), f("along"), f("ratio"), f("twi"), f("k_rms"), note))
    print("\n  want: forward held at ~0.175 mm/s and net/path ~0.83, backward net/path")
    print("  as far above its 0.199 baseline as we can get without paying for it forward.")


if __name__ == "__main__":
    main()
