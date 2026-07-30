"""Does this change help? Two configurations, identical seeds, paired intervals.

The question this project asks most often is "is the model better with X than without it",
and until now the only way to answer it was to edit worm/, run the assays for half an hour,
edit worm/ back, run them again, and compare two numbers by eye. That is slow, it is the
one workflow this project has a standing rule against -- pooled() imports the model from
disk per trial, so an edit mid-run mixes two code versions into one result -- and worst of
all it is *underpowered*, because the two runs share no noise and the difference between
them carries the variance of both.

This runs both arms in one queue, with a per-trial parameter override rather than an edit,
on the same seeds. Same seed means the same plate, the same starting bearing and the same
noise realisation, so the animal-to-animal variance -- which is most of the variance -- is
common to both arms and cancels in the difference. What is left is the treatment effect.

    PYTHONPATH=. .venv/bin/python tools/compare.py chemotaxis modulator.serotonin_mod1=0.3
    PYTHONPATH=. .venv/bin/python tools/compare.py all sensory.omega_current=450

Every argument after the assay name is a dotted parameter path and a value. The baseline
arm is the shipped model; the treatment arm is the shipped model with those fields replaced.
Values are parsed as Python literals, so numbers, tuples and strings all work:

    sensory.omega_ventral_fraction=1.0
    modulator.mod1_targets=('AVA','AVD','AVE')

What it prints, per metric, is the paired difference and its 95% interval, and a verdict
that is "no effect detected" unless the interval clears zero. That last part is the point:
a difference whose interval spans zero is not a result, and this project has repeatedly
treated one as though it were.
"""

from __future__ import annotations

import ast
import sys

import numpy as np

from tools.assays import ASSAYS, DURATIONS, ORDER, THROUGHPUT, WORKERS, _dispatch, pooled
from tools.stats import bootstrap_ci, fmt, mde, paired_ci, ratio_ci, verdict
from worm.params import Params

# Per-animal metrics, keyed by assay. Each is (label, extractor, format, higher_is_better).
# Only per-animal quantities go here -- anything pooled across animals cannot be paired,
# and is reported separately below.
METRICS = {
    "chemotaxis": [
        ("chemotaxis index", lambda r: r["ci"], "%+.3f", True),
        ("approach mm", lambda r: r["approach"], "%+.2f", True),
        ("reversals per animal", lambda r: r["n_rev"], "%+.1f", None),
        ("weathervane slope", lambda r: r["slope"], "%+.3f", True),
    ],
    "aerotaxis": [
        ("O2 at end %", lambda r: 100 * r["o2_end"], "%+.2f", False),
        ("O2 lowest reached %", lambda r: 100 * r["o2_min"], "%+.2f", False),
    ],
    "thermotaxis": [
        ("displacement mm", lambda r: r["dx"], "%+.2f", None),
    ],
    "nociception": [
        ("reversals/min exposed", lambda r: r["rate_in"], "%+.2f", True),
        ("reversals/min clear", lambda r: r["rate_out"], "%+.2f", False),
        ("repellent at end", lambda r: r["r_end"], "%+.3f", False),
    ],
    "triage": [
        ("reversals in 60 s", lambda r: r["n_rev"], "%+.1f", None),
    ],
}


def parse_spec(args):
    spec = {}
    for a in args:
        if "=" not in a:
            raise SystemExit("expected key=value, got %r" % a)
        key, _, raw = a.partition("=")
        try:
            spec[key.strip()] = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            spec[key.strip()] = raw
    return spec


def _key(row):
    """Identify an animal so the two arms can be lined up. Seed alone is not enough:
    thermotaxis runs each seed from two starting positions."""
    return (row.get("seed"), round(float(row.get("start_x", 0.0)), 3))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    which = sys.argv[1]
    if which != "all" and which not in ASSAYS:
        print("unknown assay %r; choose from %s or 'all'" % (which, ", ".join(ASSAYS)))
        return 1
    spec = parse_spec(sys.argv[2:])

    # Validate against a real Params before spending half an hour on a typo.
    from tools.assays import apply_overrides
    apply_overrides(Params(), spec)

    names = ORDER if which == "all" else [which]
    jobs = []
    for name in names:
        for payload in ASSAYS[name][1]():
            jobs.append([name, payload, {}, 0])          # baseline arm
            jobs.append([name, payload, spec, 1])        # treatment arm

    sim_s = 2 * sum(DURATIONS[n] * len(ASSAYS[n][1]()) for n in names)
    print("PAIRED COMPARISON -- %d trials (two arms on identical seeds)" % len(jobs))
    for k, v in sorted(spec.items()):
        print("  %s = %r" % (k, v))
    print("  estimated %.0f s\n" % (sim_s / Params().neural.dt / THROUGHPUT))

    rows = pooled(_dispatch, jobs, procs=WORKERS,
                  timeout=max(2400.0, 3.0 * sim_s / Params().neural.dt / THROUGHPUT))
    if not rows:
        print("  no trials completed")
        return 1

    for i, name in enumerate(names):
        got = [r for r in rows if r.get("_assay") == name]
        base = {_key(r): r for r in got if r.get("_arm") == 0}
        treat = {_key(r): r for r in got if r.get("_arm") == 1}
        shared = sorted(set(base) & set(treat), key=lambda k: (k[0] is None, k))
        if i:
            print()
        print("=" * 78)
        print("%s -- %d paired animals (%d baseline, %d treatment completed)"
              % (name.upper(), len(shared), len(base), len(treat)))
        if not shared:
            print("  no animal completed both arms")
            continue

        print()
        print("  metric                    baseline   treatment   paired difference"
              "            verdict")
        for label, get, spec_fmt, better in METRICS.get(name, []):
            a = np.array([float(get(base[k])) for k in shared])
            b = np.array([float(get(treat[k])) for k in shared])
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() < 2:
                print("  %-24s  (too few finite values)" % label)
                continue
            d, lo, hi = paired_ci(a[ok], b[ok])
            v = verdict(d, lo, hi)
            if v in ("better", "worse"):
                if better is None:
                    # No direction is "good" for this metric -- reversal counts, for one --
                    # so report which way it moved and let the reader decide.
                    v = "higher" if d > 0 else "lower"
                elif not better:
                    v = "better" if v == "worse" else "worse"
            print("  %-24s %8.3f   %8.3f   %-28s %s"
                  % (label, a[ok].mean(), b[ok].mean(), fmt(d, lo, hi, spec_fmt), v))

        # Pooled statistics: not paired, because they are not per-animal. Reported with
        # their own intervals so they are at least not read as exact.
        if name == "chemotaxis":
            print()
            print("  pooled (not paired -- these are ratios over the whole group)")
            for lab, src in (("baseline ", base), ("treatment", treat)):
                g = [src[k] for k in shared]
                print("    %s pirouette ratio  %s" % (lab, fmt(
                    *ratio_ci([r["rate_down"] for r in g], [r["rate_up"] for r in g]),
                    spec="%.2f")))

        # And what the sample could not have seen, so a null is readable.
        nulls = [lab for lab, get, _, _ in METRICS.get(name, [])
                 if not _clears(base, treat, shared, get)]
        if nulls:
            a0 = np.array([float(METRICS[name][0][1](base[k])) for k in shared])
            print()
            print("  no effect detected on: %s" % ", ".join(nulls))
            print("  at %d paired animals the smallest resolvable change in %s is %.3f"
                  % (len(shared), METRICS[name][0][0], mde(a0)))
    return 0


def _clears(base, treat, shared, get):
    a = np.array([float(get(base[k])) for k in shared])
    b = np.array([float(get(treat[k])) for k in shared])
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 2:
        return False
    d, lo, hi = paired_ci(a[ok], b[ok])
    return verdict(d, lo, hi) != "no effect detected"


if __name__ == "__main__":
    raise SystemExit(main())
