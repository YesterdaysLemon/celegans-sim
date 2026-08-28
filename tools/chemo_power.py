"""Powered paired chemotaxis: was turn depth the taxis bottleneck? No. (#196 epilogue)

The standing diagnosis said taxis outcomes were small because the turn was
shallow, and clearing the turn-depth ceiling (#215) was supposed to re-open
them. This runner measured that promise at power: the shipped deep-turn animal
(omega_tau 2.5) against the pre-#215 one (1.5), paired on seeds 0..15, every
trial completing -- no pooled batch timeout, every finished trial cached to a
JSONL beside this file so an interrupted run resumes instead of restarting
(this box loses long runs to container restarts; the compare.py batteries left
4 paired animals of 16 for the same reason).

Run:      PYTHONPATH=. .venv/bin/python tools/chemo_power.py
Summary:  PYTHONPATH=. .venv/bin/python tools/chemo_power.py report

THE RECORD (2026-08-28, 16/16 paired seeds, 200 s each):

  metric              shipped      old     paired difference
  chemotaxis index      0.026     0.072    -0.045 [-0.154, +0.034]   no effect
  approach mm         -14.57    -10.70     -3.87  [-9.45, +2.32]     no effect
  reversals             8.94      7.19     +1.75  [-2.75, +5.13]     no effect
  weathervane slope     1.06      1.61     -0.55  [-2.69, +1.31]     no effect
  pirouette ratio (down/up, pooled): shipped 0.79 -- old 1.41

The promise is REFUTED at n=16: the deep turn does not improve chemotaxis, and
the earlier n=4 "trending better" was the noise its own MDE line warned about.
Turn depth was real (the animal's ~35% over 120 degrees, adopted on its own
fit-maintenance grounds, which stand) -- but it was NOT the taxis bottleneck.

The pirouette rows say where the bottleneck lives. The old animal's
conditioning was already weak (ratio 1.41 against the strong modulation of
Pierce-Shimomura's worms); the deep-turn animal's UP-gradient reversal rate
doubled (1.82 -> 3.44/min) while the down rate barely moved, flipping the
pooled ratio to 0.79 -- either deep omega excursions contaminate the
mechanical reversal detector (the ethogram estimator lesson, a third time), or
the deeper turn genuinely dilutes conditioning by adding sensory-independent
reorientation. Distinguish those first; then the chemotaxis-magnitude hunt is
about the SENSORY-TO-TURN COUPLING -- how strongly dC/dt gates the pirouette
machinery -- not about the turn itself.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".chemo_power_cache.jsonl")
ARMS = {0: {}, 1: {"sensory.omega_tau": 1.5}}
SEEDS = range(16)


def load():
    rows = []
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def run():
    from tools.assays import _dispatch
    done = {(r["seed"], r["_arm"]) for r in load()}
    jobs = [["chemotaxis", seed, ARMS[arm], arm]
            for arm in (0, 1) for seed in SEEDS if (seed, arm) not in done]
    print("%d of 32 trials cached; running %d" % (len(done), len(jobs)))
    if not jobs:
        return report()
    with ProcessPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(_dispatch, j): j for j in jobs}
        for fut in as_completed(futs):
            j = futs[fut]
            try:
                row = fut.result()
            except Exception as e:                      # a dead trial is a note, not a stop
                print("  trial (seed %s, arm %s) failed: %s" % (j[1], j[3], e))
                continue
            with open(CACHE, "a") as f:
                f.write(json.dumps(row) + "\n")
            print("  done seed %2d arm %d  (ci %+0.3f)" % (row["seed"], row["_arm"],
                                                           row["ci"]))
    return report()


def _boot(diffs, n=4000, seed=0):
    rng = np.random.default_rng(seed)
    d = np.asarray(diffs, dtype=float)
    means = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def report():
    rows = load()
    by = {}
    for r in rows:
        by[(r["seed"], r["_arm"])] = r
    paired = [s for s in SEEDS if (s, 0) in by and (s, 1) in by]
    print("\nPOWERED PAIRED CHEMOTAXIS -- shipped (tau 2.5) vs pre-#215 (tau 1.5)")
    print("%d paired seeds of %d\n" % (len(paired), len(list(SEEDS))))
    for key, label in (("ci", "chemotaxis index"), ("approach", "approach mm"),
                       ("n_rev", "reversals"), ("slope", "weathervane slope"),
                       ("drift", "drift mm/min")):
        a = np.array([by[(s, 0)].get(key, np.nan) for s in paired], dtype=float)
        b = np.array([by[(s, 1)].get(key, np.nan) for s in paired], dtype=float)
        ok = ~(np.isnan(a) | np.isnan(b))
        d = a[ok] - b[ok]
        lo, hi = _boot(d)
        verdict = "no effect"
        if lo > 0:
            verdict = "DEEP TURN BETTER" if key != "n_rev" else "more"
        elif hi < 0:
            verdict = "deep turn worse" if key != "n_rev" else "fewer"
        print("  %-18s shipped %8.3f  old %8.3f  paired %+8.3f [%+.3f, %+.3f]  %s"
              % (label, a[ok].mean(), b[ok].mean(), d.mean(), lo, hi, verdict))
    for arm, label in ((0, "shipped"), (1, "old   ")):
        up = np.array([by[(s, arm)]["rate_up"] for s in paired])
        dn = np.array([by[(s, arm)]["rate_down"] for s in paired])
        ratio = dn.mean() / max(up.mean(), 1e-9)
        print("  pirouette ratio (down/up rates, pooled) %s: %.2f  (up %.2f/min, "
              "down %.2f/min)" % (label, ratio, up.mean(), dn.mean()))
    return 0


if __name__ == "__main__":
    sys.exit(report() if (len(sys.argv) > 1 and sys.argv[1] == "report") else run())
