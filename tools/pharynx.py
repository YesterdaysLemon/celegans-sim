"""Does the pharynx feed the animal, and do the classic ablations do what they should?

The pharyngeal nervous system used to drive nothing -- twenty neurons simulated in full,
wired only to each other, with feeding modelled as a flat rate applied whenever the head
happened to be over food. worm/pharynx.py gives them a pump to run. This measures it.

The pump rate is the headline, because it is the animal's feeding rate and it is measured
to death in the literature: 200-300 a minute on E. coli, far lower and sporadic off food,
each pump 150-200 ms.

But a rate that lands on target is weak evidence on its own -- three coefficients were
fitted to put it there. The ablations are the real test, because none of them was fitted
to anything. Each one removes a cell and predicts a direction, from decades of laser
ablation and mutant work:

    MC gone     much slower pumping. This is the eat-2 phenotype: eat-2 encodes the
                receptor subunit MC acts on, and eat-2 animals pump several-fold slower
                and grow up small and starved (Avery 1993; McKay et al. 2004).
    M3 gone     longer pumps. M3 is inhibitory onto the muscle and repolarises it, so
                without it the pump does not get switched off on time (Avery 1993).
    M4 gone     pumping continues, transport stops, the animal starves. M4 drives isthmus
                peristalsis, and that is a separate job from pumping -- which is exactly
                why this model separates capture from transport (Avery & Horvitz 1987).
    I2 gone     faster pumping, by disinhibition. I2 is what arrests feeding under light
                or peroxide (Bhatla & Horvitz 2015).
    NSM gone    the pharynx stops hearing about food. NSM is the only cell in this model
                that senses the lawn on the pharyngeal side, so removing it should collapse
                the on-food rate towards the off-food one.

Run:  PYTHONPATH=. .venv/bin/python tools/pharynx.py
"""

from __future__ import annotations

import numpy as np

from tools.assays import pooled
from tools.stats import bootstrap_ci, fmt
from worm.engine import Simulation
from worm.params import Params
from worm.world import World

MEASURE = 90.0
SEEDS = (0, 1, 2, 3)
SETTLE = 15.0

ABLATIONS = [
    ("intact", ()),
    ("MC (eat-2)", ("MCL", "MCR")),
    ("M3", ("M3L", "M3R")),
    ("M4", ("M4",)),
    ("I2", ("I2L", "I2R")),
    ("NSM", ("NSML", "NSMR")),
]


def _plate(p, on_food):
    w = World(p.world, np.random.default_rng(0))
    if on_food:
        w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    return w


def _job(job):
    import dataclasses

    label, cells, on_food, seed = job
    # The awake animal, deliberately: on this wall-to-wall lawn the satiety homeostat
    # crosses its threshold at about a minute (worm/sleep.py -- the pharynx test fixture
    # was caught measuring a sleeping animal at 194 pumps/min against an awake 250), and
    # a sleeping animal stops pumping. The pins this tool reports against are Avery &
    # Horvitz's actively feeding animals, and the ablation arms shift dopamine and
    # therefore WHEN sleep lands, which would contaminate their directions too. So the
    # sleepless control is run here, same as tests/test_pharynx.py.
    p = Params()
    p = dataclasses.replace(p, sleep=dataclasses.replace(p.sleep, ris_drive=0.0))
    sim = Simulation(p, seed=seed, world=_plate(p, on_food), placement=(0.0, 0.0, 0.0))
    if cells:
        sim.set_ablated(list(cells))
    sim.run(SETTLE)

    p0, e0 = sim.pharynx.pumps, sim.pharynx.ingested
    durations, lumen, open_frac = [], [], 0
    was = sim.pharynx.pumping
    n = int(MEASURE / sim.dt)
    for _ in range(n):
        sim.step()
        if sim.pharynx.pumping:
            open_frac += 1
            if not was:
                durations.append(sim.pharynx.duration)
        was = sim.pharynx.pumping
        lumen.append(sim.pharynx.lumen)

    return dict(label=label, on_food=on_food, seed=seed,
                rate=(sim.pharynx.pumps - p0) * 60.0 / MEASURE,
                ingest=(sim.pharynx.ingested - e0) / MEASURE,
                duration=float(np.mean(durations)) if durations else float("nan"),
                lumen=float(np.mean(lumen)), duty=open_frac / n)


def main():
    jobs = [(lab, cells, food, s)
            for lab, cells in ABLATIONS for food in (False, True) for s in SEEDS]
    print("PHARYNX -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  the pump rate is fitted; the ablation *directions* are not\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    def pick(lab, food, key):
        return [r[key] for r in rows if r["label"] == lab and r["on_food"] == food]

    print("  condition    | off food pumps/min       | on food pumps/min        | on/off")
    for lab, _ in ABLATIONS:
        off, on = pick(lab, False, "rate"), pick(lab, True, "rate")
        if not off or not on:
            continue
        o, n = np.mean(off), np.mean(on)
        ratio = ("%5.1fx" % (n / o)) if o > 0.5 else "    --"
        print("  %-12s | %-24s | %-24s | %s"
              % (lab, fmt(*bootstrap_ci(off), spec="%.0f"),
                 fmt(*bootstrap_ci(on), spec="%.0f"), ratio))
    print()
    print("  real animal: 200-300 /min on food, far lower off it")

    print()
    print("  ON FOOD, in detail")
    print("  condition    | pump ms              | ingested units/s      | lumen  | duty")
    for lab, _ in ABLATIONS:
        g = [r for r in rows if r["label"] == lab and r["on_food"]]
        if not g:
            continue
        f = lambda k: float(np.nanmean([r[k] for r in g]))          # noqa: E731
        print("  %-12s | %-20s | %-21s | %.4f | %3.0f%%"
              % (lab, fmt(*bootstrap_ci([1000 * r["duration"] for r in g]), spec="%.0f"),
                 fmt(*bootstrap_ci([r["ingest"] for r in g]), spec="%.5f"),
                 f("lumen"), 100 * f("duty")))

    print()
    print("  DO THE ABLATIONS GO THE RIGHT WAY? (on food, against intact)")
    base_rate = np.mean(pick("intact", True, "rate"))
    base_dur = float(np.mean([x for x in pick("intact", True, "duration")
                              if np.isfinite(x)]))
    base_ing = np.mean(pick("intact", True, "ingest"))
    expected = {
        "MC (eat-2)": ("rate", "much lower", lambda r, d, i: r < 0.7 * base_rate),
        "M3": ("pump duration", "longer", lambda r, d, i: d > 1.1 * base_dur),
        "M4": ("ingestion", "near zero, pumping intact",
               lambda r, d, i: i < 0.3 * base_ing and r > 0.7 * base_rate),
        "I2": ("rate", "higher", lambda r, d, i: r > base_rate),
        "NSM": ("rate", "much lower", lambda r, d, i: r < 0.7 * base_rate),
    }
    for lab, _ in ABLATIONS:
        if lab not in expected:
            continue
        what, want, test = expected[lab]
        r = np.mean(pick(lab, True, "rate"))
        dur = [x for x in pick(lab, True, "duration") if np.isfinite(x)]
        d = float(np.mean(dur)) if dur else float("nan")
        i = np.mean(pick(lab, True, "ingest"))
        ok = "yes" if test(r, d, i) else "NO"
        print("    %-12s %-16s should be %-26s %s" % (lab, what, want, ok))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
