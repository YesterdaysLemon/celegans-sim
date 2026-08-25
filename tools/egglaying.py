"""Egg-laying: is it a circuit, or a counter with good manners?

A mean rate of four or five eggs an hour is easy to hit and proves nothing -- any timer
does that. The claims worth testing are the ones that would fail if the thing were a timer:

    CLUSTERING    Waggoner et al. (1998) timed the behaviour and found it is not paced.
                  Active phases of roughly two minutes hold several events about twenty
                  seconds apart, and are separated by inactive phases of roughly twenty
                  minutes. So the interval distribution is strongly bimodal, and the
                  coefficient of variation of the intervals is well above 1 -- a Poisson
                  process gives exactly 1, and a metronome gives 0. Nothing in
                  worm/egglaying.py schedules a phase or counts events; if the clustering
                  is there it is what the depleting resource does -- OR, since the sleep
                  homeostat (worm/sleep.py), what sleep does: a sleeping animal stops
                  pumping and laying on a bouts-of-tens-of-seconds, threshold-at-about-a-
                  minute-on-food clock, which produces exactly this bimodal shape. Before
                  reading the CV as the resource's signature, run the sleepless control
                  (SleepParams.ris_drive = 0) and compare.

    FOOD          On food an animal lays freely; off food it retains eggs. This is a
                  gate, not a bias -- the difference should be large.

    HSN           Ablated, the animal is egg-laying defective: much slower, but not
                  silent. If removing HSN abolishes laying here, the serotonin path is
                  not doing its job and the model has one route where the animal has two.

    SEROTONIN     Exogenous serotonin induces laying, and does so *in HSN-ablated
                  animals*, which is what places its action downstream of HSN. This assay
                  applies it the way the bench does -- by putting it in the dish -- by
                  clamping the modulator level rather than by changing a parameter.

    VC            Ablated, laying goes slightly *up*. The VCs are a brake. This one is a
                  small effect and is reported with its interval; it is the arm most
                  likely to come back null, and a null is a fine answer.

Run:  PYTHONPATH=. .venv/bin/python tools/egglaying.py [minutes] [seeds]
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.stats import bootstrap_ci, paired_ci, fmt, mde, verdict   # noqa: E402
from worm.params import Params                                       # noqa: E402

MINUTES = 8
SEEDS = 6


def _plate(p, on_food: bool):
    from worm.world import World
    w = World(p.world, np.random.default_rng(0))
    if on_food:
        # A lawn covering the whole dish, and that is not laziness -- it is the control.
        # Egg-laying is gated by food at the vulva, so on a lawn the animal can walk off,
        # and the rate becomes a joint function of the circuit and of where the animal
        # happened to wander. On a 12 mm lawn the intact animals sat at 0.63 mean food
        # density while the HSN-ablated ones sat at 0.99, and the gate difference cancelled
        # the drive difference exactly: the ablated animals appeared to lay MORE. Whether
        # the animal can find and hold a lawn is chemotaxis' question and tools/assays.py
        # asks it. This one is about what a fed animal does.
        w.add_food_patch(0.0, 0.0, float(p.world.radius) + 4.0,
                         density=1.0, attractant=1.0, length_scale=30.0)
    return w


def trial(job):
    """One animal. `arm` selects the manipulation; everything else is held identical."""
    from worm.engine import Simulation

    seed = job["seed"]
    arm = job["arm"]
    minutes = job.get("minutes", MINUTES)
    on_food = arm != "off_food"

    p = Params()
    sim = Simulation(p, seed=seed, world=_plate(p, on_food), placement=(0.0, 0.0, 0.0))

    if arm == "hsn":
        sim.set_ablated(["HSNL", "HSNR"])
    elif arm == "vc":
        sim.set_ablated(["VC01", "VC02", "VC03", "VC04", "VC05"])
    elif arm == "hsn_serotonin":
        sim.set_ablated(["HSNL", "HSNR"])

    # Exogenous serotonin: the bench version is to put the animal in a serotonin solution,
    # so the level is clamped rather than a parameter being changed. Held after the
    # modulator update each step, which is where an external bath would sit.
    bath = job.get("serotonin", None)

    n = int(minutes * 60 / sim.dt)
    for _ in range(n):
        sim.step()
        if bath is not None:
            sim.modulators.level["serotonin"] = bath

    times = [t for _, _, t in sim.world.eggs]
    return dict(seed=seed, arm=arm, minutes=minutes,
                laid=sim.egglaying.laid,
                per_hour=sim.egglaying.laid * 60.0 / minutes,
                held=float(sim.egglaying.eggs),
                ingested=float(sim.pharynx.ingested),
                serotonin=float(sim.modulators.level["serotonin"]),
                times=[round(t, 3) for t in times])


# ------------------------------------------------------------------------- clustering ---

def interval_stats(times_by_animal, gap: float = 120.0):
    """Bimodality of the inter-event intervals, without assuming where the split is.

    `gap` only classifies intervals for reporting -- the numbers that carry the claim are
    the coefficient of variation and the fraction of events that arrive within a minute of
    the last one, neither of which needs a threshold to be meaningful.
    """
    iv = []
    for t in times_by_animal:
        if len(t) > 1:
            iv.append(np.diff(np.asarray(t, dtype=float)))
    if not iv:
        return None
    iv = np.concatenate(iv)
    return {
        "n": int(iv.size),
        "median": float(np.median(iv)),
        "cv": float(iv.std() / max(iv.mean(), 1e-9)),
        "frac_within_60s": float((iv < 60.0).mean()),
        "frac_over_gap": float((iv >= gap).mean()),
        "intervals": iv,
    }


def report(rows, minutes):
    by = {}
    for r in rows:
        by.setdefault(r["arm"], []).append(r)

    print("EGG-LAYING -- %d animals per arm, %g simulated minutes each\n"
          % (len(by.get("on_food", [])), minutes))

    def rate(arm):
        g = by.get(arm, [])
        return np.array([r["per_hour"] for r in g], dtype=float) if g else np.array([])

    print("  RATE")
    print("    %-26s %-28s %s" % ("arm", "eggs/hour", "vs on food"))
    base = rate("on_food")
    for arm, label in (("on_food", "on food"), ("off_food", "off food"),
                       ("hsn", "HSN ablated"), ("vc", "VC ablated"),
                       ("serotonin", "serotonin bath"),
                       ("hsn_serotonin", "HSN ablated + serotonin")):
        v = rate(arm)
        if v.size == 0:
            continue
        m, lo, hi = bootstrap_ci(v)
        cell = fmt(m, lo, hi, "%.2f")
        cmp_ = ""
        if arm != "on_food" and base.size == v.size:
            d, dlo, dhi = paired_ci(base, v)
            cmp_ = "%s  %s" % (fmt(d, dlo, dhi, "%+.2f"), verdict(d, dlo, dhi))
        print("    %-26s %-28s %s" % (label, cell, cmp_))
    if base.size:
        print("    (the animal manages 4-6 an hour freely feeding)")

    print("\n  CLUSTERING -- the claim a timer would fail")
    for arm, label in (("on_food", "on food"), ("hsn", "HSN ablated")):
        g = by.get(arm, [])
        st = interval_stats([r["times"] for r in g])
        if not st:
            print("    %-26s too few events to say" % label)
            continue
        print("    %-26s n=%-4d median %6.1f s   CV %.2f   within 60 s %.0f%%   over 2 min %.0f%%"
              % (label, st["n"], st["median"], st["cv"],
                 100 * st["frac_within_60s"], 100 * st["frac_over_gap"]))
    print("    CV is 0 for a metronome and 1 for a Poisson process. Clustered means > 1.")

    print("\n  RETENTION")
    for arm, label in (("on_food", "on food"), ("off_food", "off food"), ("hsn", "HSN ablated")):
        g = by.get(arm, [])
        if not g:
            continue
        h = np.array([r["held"] for r in g], dtype=float)
        m, lo, hi = bootstrap_ci(h)
        print("    %-26s eggs held at the end  %s  (capacity %.0f)"
              % (label, fmt(m, lo, hi, "%.1f"), Params().egglaying.uterus_capacity))

    print("\n  What each arm is for is in the docstring of this file. The two that would")
    print("  most embarrass the model are HSN-ablated laying *nothing* -- which would mean")
    print("  one route where the animal has two -- and a CV near 1, which would mean the")
    print("  resource is not clustering anything and this is a Poisson process wearing a")
    print("  circuit's clothes.")
    return rows


def from_runtime(path="web/egg-events.json"):
    """Read event times produced by wasm/egglaying.mjs and measure them here.

    Same division of labour as tools/parity.py: the runtime produces raw event times and
    computes nothing, and every statistic below comes from the code in this file. If each
    side measured its own clustering, a disagreement would be ambiguous between the model
    and the metric, and the metric is much the easier of the two to get wrong.

    The runtime is used for exactly one reason. Clustering is a claim about several
    twenty-minute cycles, so the run has to be an hour long whichever implementation
    executes it; this one gets through an hour of animal in twenty-six minutes instead of
    sixty, and conform.mjs shows the two agree on every piece of egg-laying state to
    0.000e+0.
    """
    if not os.path.exists(path):
        print("no runtime events. Run:\n  node wasm/egglaying.mjs", file=sys.stderr)
        return 2
    rows = json.load(open(path))
    by = {}
    for r in rows:
        by.setdefault(r["arm"], []).append(r)

    mins = rows[0]["minutes"]
    print("EGG-LAYING, CLUSTERING -- %g simulated minutes per animal, on the WASM runtime\n"
          % mins)
    print("  Waggoner et al. 1998: active phases of ~2 min holding several events ~20 s")
    print("  apart, separated by inactive phases of ~20 min. Nothing in worm/egglaying.py")
    print("  schedules a phase or counts events -- if this structure is here it is what the")
    print("  depleting resource behind the Schmitt trigger does.\n")
    print("    %-14s %6s %7s %9s %8s %10s %10s"
          % ("arm", "worms", "events", "median s", "CV", "<60 s", ">2 min"))
    out = {}
    for arm in ("on_food", "hsn"):
        g = by.get(arm, [])
        if not g:
            continue
        st = interval_stats([r["times"] for r in g])
        n_eggs = sum(r["laid"] for r in g)
        if not st:
            print("    %-14s %6d %7d   too few events to say" % (arm, len(g), n_eggs))
            continue
        out[arm] = st
        print("    %-14s %6d %7d %9.1f %8.2f %9.0f%% %9.0f%%"
              % (arm, len(g), n_eggs, st["median"], st["cv"],
                 100 * st["frac_within_60s"], 100 * st["frac_over_gap"]))
        print("      rate %.1f eggs/hour" % (n_eggs * 60.0 / (mins * len(g))))

    print("\n  CV is 0 for a metronome and exactly 1 for a Poisson process. Above 1 means")
    print("  the events are clustered -- bunched into bouts with gaps between them -- which")
    print("  is the only one of the three a timer cannot produce.")
    st = out.get("on_food")
    if st:
        if st["cv"] > 1.2 and st["frac_within_60s"] > 0.4 and st["frac_over_gap"] > 0.15:
            print("\n  Clustered: %.0f%% of intervals under a minute and %.0f%% over two,"
                  % (100 * st["frac_within_60s"], 100 * st["frac_over_gap"]))
            print("  with CV %.2f. Both tails are populated, which is what bimodal means" % st["cv"])
            print("  and what a single rate cannot do.")
        elif st["cv"] < 1.2:
            print("\n  NOT clustered: CV %.2f is Poisson or tighter. The resource is not" % st["cv"])
            print("  structuring anything and this is a rate with extra steps. The honest")
            print("  reading is that the phase machinery earns nothing as tuned.")
        else:
            print("\n  Ambiguous: CV %.2f is above Poisson but the two tails are not both"
                  % st["cv"])
            print("  populated (%.0f%% under a minute, %.0f%% over two). More animals."
                  % (100 * st["frac_within_60s"], 100 * st["frac_over_gap"]))
    return 0


def main(argv):
    if argv and argv[0] == "clustering":
        return from_runtime()
    minutes = float(argv[0]) if argv else MINUTES
    seeds = int(argv[1]) if len(argv) > 1 else SEEDS

    from tools.assays import pooled
    jobs = []
    for s in range(seeds):
        jobs.append({"seed": s, "arm": "on_food", "minutes": minutes})
        jobs.append({"seed": s, "arm": "off_food", "minutes": minutes})
        jobs.append({"seed": s, "arm": "hsn", "minutes": minutes})
        jobs.append({"seed": s, "arm": "vc", "minutes": minutes})
        jobs.append({"seed": s, "arm": "serotonin", "minutes": minutes, "serotonin": 0.6})
        jobs.append({"seed": s, "arm": "hsn_serotonin", "minutes": minutes, "serotonin": 0.6})

    # Generous: a job runs `minutes` of simulated time at about real time, and pooled's
    # default deadline is forty minutes. A sweep that outlives it is killed with no output
    # at all, which is how one forty-five-minute run was lost.
    rows = [r for r in pooled(trial, jobs, timeout=int(minutes * 60 * 1.6) + 600) if r]
    if not rows:
        print("no trials completed", file=sys.stderr)
        return 2
    report(rows, minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
