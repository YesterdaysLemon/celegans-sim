"""Fit the model's free parameters to measured worm behaviour.

Nothing here trains the connectome. The wiring is anatomy -- 7,000 synapses traced out of
electron micrographs of a real animal -- and fitting it would throw away the entire point
of building the model on it. The same goes for every constant that has actually been
measured: membrane capacitance, reversal potentials, bending modulus, drag coefficients.
Those are facts and they stay fixed.

What is left over is a handful of numbers nobody has measured: how strongly a stretch
receptor drives its motor neuron, how far along the body it reads, how much torque a fully
contracted muscle sheet exerts. Boyle et al. fitted theirs and disagree with their own
published value by a factor of 1.86; Izquierdo and Beer evolve theirs outright. Fitting
them is normal practice in this field, and it is not the same thing as training a network.

This searches those parameters against an objective built from measurements on live
animals. Each evaluation runs a real closed-loop simulation, so it is expensive -- about a
minute -- and the search is parallel across cores and checkpoints after every result so it
can be stopped and resumed.

    PYTHONPATH=. python tools/optimise.py --evals 120 --workers 8
    PYTHONPATH=. python tools/optimise.py --report        # read the checkpoint back
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from dataclasses import replace

import numpy as np

from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

CHECKPOINT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch", "optimise.json")

# The free parameters, with the range each is allowed to take. Every one of these is a
# number nobody has measured in a real animal; nothing measured appears in this list.
SPACE = {
    "proprio_gain":      (20.0, 300.0),   # pA per unit normalised curvature
    "proprio_reach":     (0.08, 0.40),    # fraction of body length read anteriorly
    "peak_moment":       (0.8, 5.0),      # uN mm at full unilateral contraction
    "head_proprio_gain": (0.0, 300.0),    # pA
    "head_tau":          (0.05, 0.60),    # s
    "head_reach":        (0.08, 0.30),    # fraction of body length
    "tonic_forward":     (20.0, 160.0),   # pA
}

# What a real worm does on agar, and how much each miss costs. Sources are in the README.
TARGETS = {
    "speed":      dict(target=0.219, tol=0.06,  weight=3.0, kind="value"),
    "net_ratio":  dict(target=0.60,  tol=0.15,  weight=2.0, kind="atleast"),
    # How much of the oscillation is a travelling wave rather than a standing one. This is
    # the term that matters most and the one that took longest to find. A standing wave
    # generates no net thrust at all, and the shipped model sits at +0.33 -- two thirds
    # standing -- while the same body driven by a clean prescribed travelling wave reaches
    # +0.996 and moves at 0.174 mm/s. It is also far better conditioned than net
    # displacement, which is slow and noisy to measure.
    "twi":        dict(target=0.90,  tol=0.15,  weight=4.0, kind="atleast"),
    "freq":       dict(target=0.40,  tol=0.15,  weight=1.5, kind="value"),
    "wavelength": dict(target=0.65,  tol=0.15,  weight=1.5, kind="value"),
    "kappa_max":  dict(target=9.8,   tol=2.5,   weight=1.0, kind="value"),
    "kappa_rms":  dict(target=4.3,   tol=1.0,   weight=1.0, kind="value"),
    "dv_corr":    dict(target=-0.5,  tol=0.3,   weight=1.5, kind="atmost"),
}

SEEDS = (0, 3, 7)


def cost_terms(m: dict) -> dict:
    """Per-target cost, in units of 'tolerances away from the measured value'."""
    out = {}
    for name, spec in TARGETS.items():
        v = m.get(name)
        if v is None or not np.isfinite(v):
            out[name] = 10.0
            continue
        d = v - spec["target"]
        if spec["kind"] == "atleast":
            d = min(d, 0.0)          # exceeding the target is free
        elif spec["kind"] == "atmost":
            d = max(d, 0.0)
        out[name] = spec["weight"] * abs(d) / spec["tol"]
    return out


def build(values: dict) -> Params:
    p = Params()
    return replace(
        p,
        muscle=replace(p.muscle, peak_moment=values["peak_moment"]),
        sensory=replace(
            p.sensory,
            proprio_gain=values["proprio_gain"],
            proprio_reach=values["proprio_reach"],
            head_proprio_gain=values["head_proprio_gain"],
            head_tau=values["head_tau"],
            head_reach=values["head_reach"],
            tonic_forward=values["tonic_forward"],
        ),
    )


def evaluate_one(args) -> dict:
    values, seed = args
    p = build(values)
    try:
        sim = Simulation(p, seed=seed, world=bare_world(p))
        r = analyse(sim, seconds=16.0)

        # Net progress, measured the way a tracker would: how far did it actually get.
        start = sim.body.centroid().copy()
        prev = start.copy()
        path = 0.0
        for i in range(int(40.0 / sim.dt)):
            sim.step()
            if i % 200 == 0:
                c = sim.body.centroid()
                path += float(np.hypot(*(c - prev)))
                prev = c.copy()
        net = float(np.hypot(*(sim.body.centroid() - start)))
        r["speed"] = net / 40.0
        r["net_ratio"] = net / max(path, 1e-9)
        r["backwards"] = r["direction"] != "head->tail"
        return r
    except Exception as exc:
        return {"failed": repr(exc), "backwards": True}


def score(results: list) -> tuple:
    """Combine the per-seed results into one number. Lower is better."""
    good = [r for r in results if "failed" not in r]
    if not good:
        return 1e6, {}
    agg = {}
    for key in ("speed", "net_ratio", "freq", "wavelength", "kappa_max", "kappa_rms",
                "dv_corr"):
        vals = [r[key] for r in good if key in r and np.isfinite(r[key])]
        agg[key] = float(np.mean(vals)) if vals else float("nan")
    terms = cost_terms(agg)
    total = sum(terms.values())

    # A worm that goes backwards, or whose gait depends on the seed, is not a solution
    # however well its averages score.
    backwards = sum(1 for r in good if r.get("backwards"))
    total += 4.0 * backwards
    freqs = [r["freq"] for r in good if np.isfinite(r.get("freq", np.nan)) and r["freq"] > 0]
    if len(freqs) > 1:
        spread = max(freqs) / max(min(freqs), 1e-9)
        total += 2.0 * max(0.0, spread - 1.4)
    agg["backwards"] = backwards
    agg["n_seeds"] = len(good)
    return float(total), agg


def sample(rng: np.random.Generator) -> dict:
    return {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in SPACE.items()}


def perturb(rng: np.random.Generator, base: dict, sigma: float) -> dict:
    out = {}
    for k, (lo, hi) in SPACE.items():
        span = hi - lo
        out[k] = float(np.clip(base[k] + rng.normal(0.0, sigma * span), lo, hi))
    return out


def load_checkpoint() -> list:
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as fh:
            return json.load(fh)
    return []


def save_checkpoint(rows: list) -> None:
    os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rows, fh, indent=1)
    os.replace(tmp, CHECKPOINT)


def report(rows: list, top: int = 10) -> None:
    if not rows:
        print("no results yet")
        return
    rows = sorted(rows, key=lambda r: r["score"])
    baseline = [r for r in rows if r.get("tag") == "baseline"]
    print("%d evaluations; best %d\n" % (len(rows), min(top, len(rows))))
    keys = ["speed", "net_ratio", "freq", "wavelength", "kappa_max", "dv_corr"]
    print("%6s  %8s %8s %6s %7s %8s %7s  %s"
          % ("score", "net mm/s", "net/path", "Hz", "lambda", "kappa_max", "dv", "parameters"))
    for r in rows[:top]:
        m = r["metrics"]
        params = " ".join("%s=%.3g" % (k[:6], r["values"][k]) for k in SPACE)
        print("%6.2f  %8.4f %8.3f %6.2f %7.2f %8.1f %7.2f  %s"
              % (r["score"], m.get("speed", float("nan")), m.get("net_ratio", float("nan")),
                 m.get("freq", float("nan")), m.get("wavelength", float("nan")),
                 m.get("kappa_max", float("nan")), m.get("dv_corr", float("nan")), params))
    if baseline:
        b = baseline[0]
        print("\nshipped defaults scored %.2f (rank %d of %d)"
              % (b["score"], rows.index(b) + 1, len(rows)))
    print("\ntargets: net 0.219 mm/s, net/path >0.60, 0.40 Hz, 0.65 L, kappa_max 9.8, dv <-0.5")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evals", type=int, default=120)
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 4))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--explore", type=float, default=0.55,
                    help="fraction of the budget spent sampling before refining")
    args = ap.parse_args(argv)

    rows = load_checkpoint()
    if args.report:
        report(rows, top=15)
        return 0

    rng = np.random.default_rng(args.seed)
    pool = mp.Pool(args.workers)
    started = time.time()

    # Evaluate several candidates at once. Each candidate needs one run per seed, so a
    # pool sized to the seed count alone would leave most of the machine idle.
    batch = max(1, args.workers // len(SEEDS))

    def run_batch(candidates):
        jobs = [(v, s) for v, _tag in candidates for s in SEEDS]
        flat = pool.map(evaluate_one, jobs)
        out = []
        for i, (values, tag) in enumerate(candidates):
            results = flat[i * len(SEEDS):(i + 1) * len(SEEDS)]
            total, agg = score(results)
            rows.append({"score": total, "values": values, "metrics": agg, "tag": tag})
            out.append(total)
        save_checkpoint(rows)
        return out

    try:
        if not any(r.get("tag") == "baseline" for r in rows):
            p = Params()
            base = {"proprio_gain": p.sensory.proprio_gain,
                    "proprio_reach": p.sensory.proprio_reach,
                    "peak_moment": p.muscle.peak_moment,
                    "head_proprio_gain": p.sensory.head_proprio_gain,
                    "head_tau": p.sensory.head_tau,
                    "head_reach": p.sensory.head_reach,
                    "tonic_forward": p.sensory.tonic_forward}
            s = run_batch([(base, "baseline")])[0]
            print("baseline (shipped defaults): score %.2f" % s, flush=True)

        n_explore = int(args.evals * args.explore)
        done = 0
        while done < args.evals:
            k = min(batch, args.evals - done)
            candidates = []
            for j in range(k):
                i = done + j
                if i < n_explore or not rows:
                    candidates.append((sample(rng), "explore"))
                else:
                    # Refine around the best few found so far, shrinking the step as we go.
                    best_rows = sorted(rows, key=lambda r: r["score"])[:4]
                    pick = best_rows[rng.integers(len(best_rows))]
                    frac = (i - n_explore) / max(1, args.evals - n_explore)
                    candidates.append(
                        (perturb(rng, pick["values"], 0.18 * (1 - 0.75 * frac)), "refine"))
            scores = run_batch(candidates)
            done += k
            best = min(r["score"] for r in rows)
            print("[%3d/%3d] %-7s batch %s   best %8.2f   %5.1f min elapsed"
                  % (done, args.evals, candidates[0][1],
                     " ".join("%.1f" % s for s in scores), best,
                     (time.time() - started) / 60.0), flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted; %d results saved" % len(rows))
    finally:
        pool.close()
        pool.join()

    print()
    report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
