"""Every headline number in one place, across seeds, next to what a real animal does.

The README carries a table of what this model gets right and wrong. Its rows have
historically been filled in at different times from different runs, which is how it came
to quote a crawling speed from day two beside a frequency from day nine -- numbers that
were never true of the same animal. This measures them all at once, from the same
configuration, and reports the seed-to-seed spread rather than one run's luck.

The spread matters more than usual here. The gait has been bistable across seeds since
day two, and a single-seed number can be a full standard deviation from the mean, so any
row quoted without one is a claim the model does not support.

The two resting-potential rows are the exception, and were wrong for the opposite reason.
They used to read min and max of V off the animal at whatever instant the run ended on,
which is not a resting potential -- the head motor pool swings nearly clamp to clamp every
cycle, so the answer depended on the phase the sampling happened to land in and ranged
from +7 to +45 mV across five seeds. Rest is now measured before the animal moves, where
it exists, and is deterministic; the crawling span is reported separately under its own
name.

Run:  PYTHONPATH=. .venv/bin/python tools/scorecard.py
"""

from __future__ import annotations

import sys

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import MEDIA, Params

MEASURE = 40.0
SEEDS = (0, 1, 3, 5, 7)


def _job(job):
    medium, seed = job
    p = Params().with_medium(medium)
    sim = Simulation(p, seed=seed, world=bare_world(p))

    sim.run(6.0)
    start = sim.body.centroid().copy()
    t0 = sim.t
    prev, path = start.copy(), 0.0
    n = int(MEASURE / sim.dt)
    every = max(1, int(round(0.05 / sim.dt)))
    # Potentials over the whole window rather than at whichever instant the run happens to
    # end on. Read at one instant these are a lottery: the head motor pool swings most of
    # the clamp-to-clamp range every cycle, so the number you get is a statement about the
    # phase the sampling landed in and not about the animal. The two ends of the swing are
    # what mean something, and how often the upper one is the clamp itself.
    clamp_lo, clamp_hi = p.neural.v_clamp
    v_lo, v_hi, m_lo, m_hi = np.inf, -np.inf, np.inf, -np.inf
    rail_hi = rail_lo = samples = 0
    for i in range(n):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
            V, M = sim.nervous.V, sim.muscles.V
            v_lo, v_hi = min(v_lo, float(V.min())), max(v_hi, float(V.max()))
            m_lo, m_hi = min(m_lo, float(M.min())), max(m_hi, float(M.max()))
            rail_hi += int(V.max() >= clamp_hi - 1e-9)
            rail_lo += int(V.min() <= clamp_lo + 1e-9)
            samples += 1
    net = float(np.linalg.norm(sim.body.centroid() - start))
    span = sim.t - t0

    # Gait metrics from a second stretch, so the two do not share a window.
    r = analyse(sim, seconds=MEASURE)
    return dict(medium=medium, seed=seed, freq=r["freq"],
                wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], k_max=r["kappa_max"], dv_corr=r["dv_corr"],
                direction=r["direction"], speed=net / span,
                net_path=net / max(path, 1e-9),
                v_lo=v_lo, v_hi=v_hi, m_lo=m_lo, m_hi=m_hi,
                rail_hi=rail_hi / max(samples, 1), rail_lo=rail_lo / max(samples, 1))


def _rest() -> dict:
    """The resting state, measured where a resting state exists: before the animal moves.

    This is the row's whole point -- it is checked against the range whole-cell recordings
    give for *resting* neurons -- and it is not what reading V off a crawling animal gives.
    Both halves are deterministic. The neuron rest is a linear solve on the connectome
    (`_resting_potentials`) and the muscle rest comes from the per-cell balance, neither of
    which touches the rng, so this carries no seed spread and is measured once rather than
    five times. Quoting a spread it does not have would be its own kind of lie. Nor does
    the medium reach either one -- `with_medium` replaces drag coefficients and nothing
    else -- so the bare `Params()` here is the same animal the agar rows describe.
    """
    p = Params()
    sim = Simulation(p, seed=0)
    V = sim.nervous.V_th
    # Not muscle V at construction, which is still E_leak: the excitation-contraction
    # cascade starts empty and fills over a few hundred ms against the resting release, so
    # the cells have to settle before the number is a resting potential rather than a leak.
    for _ in range(int(3.0 / sim.dt)):
        sim.muscles.step(sim.nervous.s)
    M = sim.muscles.V
    return dict(v_lo=float(V.min()), v_med=float(np.median(V)), v_hi=float(V.max()),
                m_lo=float(M.min()), m_hi=float(M.max()))


ROWS = [
    ("Undulation frequency, agar", "freq", "Hz", "0.30 +- 0.02", "%.2f"),
    ("Wavelength, agar", "wavelength", "L", "0.65 +- 0.03", "%.2f"),
    ("Curvature, r.m.s.", "k_rms", "/mm", "4.3 +- 0.3", "%.2f"),
    ("Curvature, peak", "k_max", "/mm", "9.8 +- 1.1", "%.1f"),
    ("Crawling speed (net)", "speed", "mm/s", "0.219 +- 0.029", "%.3f"),
    ("Net displacement / path", "net_path", "", "well above 0.5", "%.2f"),
    ("Travelling-wave index", "twi", "", "+1 pure travelling", "%.2f"),
    ("Dorsoventral antagonism", "dv_corr", "", "strongly negative", "%.2f"),
]

# ------------------------------------------------------------------- the emitted table --
#
# `--emit` renders the measurement as markdown and writes it to BOTH places that carry
# it -- docs/scorecard.md wholesale, and the block between the scorecard markers in
# README.md -- from ONE aggregation of one run. That is the property the whole tool
# exists for ("numbers that were never true of the same animal"), now enforced for the
# documents too: tests/test_scorecard_doc.py asserts the two copies are identical, so a
# hand edit to either fails fast, and .github/workflows/scorecard.yml is the on-demand
# way to refresh the pair. The text printout and the markdown read the same dict, so
# they cannot drift from each other either.
BEGIN_MARK = "<!-- scorecard:begin (generated by tools/scorecard.py --emit; do not hand-edit) -->"
END_MARK = "<!-- scorecard:end -->"

# (README label, aggregate key, measured value, source) -- the rows whose numbers exist
# only as facts of the dataset are written here as constants with their provenance, so
# the emitted table carries them without pretending they were measured by this run.
MD_ROWS = [
    ("Curvature, r.m.s.", "k_rms", "4.3 ± 0.3 /mm", "Krajacic et al. 2012"),
    ("Curvature, peak", "k_max", "9.8 ± 1.1 /mm", "Krajacic et al. 2012"),
    ("Wave direction", "direction", "head → tail", "—"),
    ("Muscle resting potential", "m_rest", "−25.0 ± 1.0 mV", "Gao & Zhen 2011"),
    ("Resting potentials", "rest_span", "−75 to −25 mV", "several, see `params.py`"),
    ("Swimming efficiency U/c", "uc", "0.08 ± 0.01", "Shen et al. 2012"),
    ("Neuron count / classes", "const:302 / 118", "302 / 118", "canonical"),
    ("GABAergic neurons", "const:26", "26", "McIntire et al. 1993"),
    ("Crawling speed (net)", "speed", "0.219 ± 0.029 mm/s", "Ramot et al. 2008"),
    ("Net displacement / path", "net_path", "well above 0.5", "—"),
    ("Travelling-wave index", "twi", "+1 for a pure travelling wave", "—"),
    ("Undulation frequency, agar", "freq", "0.30 ± 0.02 Hz", "Fang-Yen et al. 2010"),
    ("Wavelength, agar", "wavelength", "0.65 ± 0.03 L", "Fang-Yen et al. 2010"),
]

# How each aggregate key renders in the table's Model column: (format for mean±sd rows,
# unit suffix, editorial aside kept from the hand-written table it replaces).
MD_STYLE = {
    "k_rms": ("%.2f ± %.2f", " /mm", ""),
    "k_max": ("%.1f ± %.1f", " /mm", " *(sharp)*"),
    "m_rest": (None, " mV", " *(a point, not a range)*"),
    "rest_span": (None, "", ""),
    "uc": ("%.3f ± %.3f", "", " *(low)*"),
    "speed": ("%.3f ± %.3f", " mm/s", ""),
    "net_path": ("%.2f ± %.2f", "", ""),
    "twi": ("+%.2f ± %.2f", "", ""),
    "freq": ("%.2f ± %.2f", " Hz", ""),
    "wavelength": ("%.2f ± %.2f", " L", " *(long)*"),
}


def _aggregate(allrows, rest):
    """One run's numbers, keyed for both renderers."""
    rows = [r for r in allrows if r["medium"] == "agar"]
    agg = {}
    for _, key, _, _, _ in ROWS:
        v = np.array([r[key] for r in rows], dtype=float)
        v = v[np.isfinite(v)]
        agg[key] = (float(v.mean()), float(v.std()))
    d = [r["direction"] for r in rows]
    agg["direction"] = (d.count("head->tail"), len(d))
    swim = [r for r in allrows if r["medium"] == "buffer"]
    L = Params().body.length
    uc = np.array([r["speed"] / (r["freq"] * r["wavelength"] * L) for r in swim])
    uc = uc[np.isfinite(uc)]
    agg["uc"] = (float(uc.mean()), float(uc.std())) if len(uc) else (float("nan"),) * 2
    agg["rest"] = rest
    agg["media"] = {}
    for med in ("agar", "viscous", "buffer"):
        g = [r for r in allrows if r["medium"] == med]
        if g:
            agg["media"][med] = {
                "freq": np.array([r["freq"] for r in g]),
                "wavelength": np.array([r["wavelength"] for r in g]),
                "speed": np.array([r["speed"] for r in g]),
            }
    agg["crawl"] = {
        "v_lo": float(np.mean([r["v_lo"] for r in rows])),
        "v_hi": float(np.mean([r["v_hi"] for r in rows])),
        "m_lo": float(np.mean([r["m_lo"] for r in rows])),
        "m_hi": float(np.mean([r["m_hi"] for r in rows])),
        "rail_hi": float(np.mean([r["rail_hi"] for r in rows])),
        "rail_lo": float(np.mean([r["rail_lo"] for r in rows])),
    }
    agg["agar_seed_freq"] = [(r["seed"], r["freq"])
                             for r in sorted(rows, key=lambda x: x["seed"])]
    return agg


def _model_cell(key, agg):
    """The Model column for one emitted row."""
    if key.startswith("const:"):
        return "**%s**" % key[6:]
    if key == "direction":
        ok, n = agg["direction"]
        return "**head → tail** (%d/%d seeds)" % (ok, n)
    if key == "m_rest":
        return "**%.1f mV** *(a point, not a range)*" % agg["rest"]["m_lo"]
    if key == "rest_span":
        r = agg["rest"]
        return "**%.0f to %.0f mV**, median %.0f" % (r["v_lo"], r["v_hi"], r["v_med"])
    fmt, unit, aside = MD_STYLE[key]
    mean, sd = agg[key]
    return "**%s%s**%s" % (fmt % (mean, sd), unit, aside)


def _markdown_table(agg):
    lines = ["| Quantity | Model | Measured | Source |", "|---|---|---|---|"]
    for label, key, measured, source in MD_ROWS:
        lines.append("| %s | %s | %s | %s |" % (label, _model_cell(key, agg),
                                                measured, source))
    return "\n".join(lines)


def _emit(agg):
    """Write docs/scorecard.md and rewrite README's marker block, from one aggregation."""
    import os
    import subprocess
    import time

    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True).stdout.strip() or "unknown"
    except OSError:
        sha = "unknown"
    stamp = time.strftime("%Y-%m-%d")
    table = _markdown_table(agg)
    block = "\n".join([
        BEGIN_MARK,
        table,
        "",
        "*(Measured %s at `%s` by `tools/scorecard.py`: %d seeds × %.0f s, three media,"
        % (stamp, sha, len(SEEDS), MEASURE),
        "every row from the same run. Regenerate with `tools/scorecard.py --emit`, or"
        " dispatch the `scorecard` workflow.)*",
        END_MARK,
    ])

    media_lines = []
    for med in ("agar", "viscous", "buffer"):
        m = agg["media"].get(med)
        if m is None:
            continue
        # `pooled` reports failed trials as absent rather than raising, so a medium can
        # quietly arrive with fewer seeds than were dispatched -- which happened on the
        # first emitted run (buffer, 4 of 5). No silent caps: say so in the row.
        short = ("" if len(m["freq"]) == len(SEEDS)
                 else " (n=%d of %d — a trial did not complete)"
                 % (len(m["freq"]), len(SEEDS)))
        media_lines.append(
            "| %s | %.2f ± %.2f | %.2f ± %.2f | %.3f ± %.3f | %s%s |"
            % (med, m["freq"].mean(), m["freq"].std(),
               m["wavelength"].mean(), m["wavelength"].std(),
               m["speed"].mean(), m["speed"].std(),
               " ".join("%.2f" % x for x in m["freq"]), short))
    doc = "\n".join([
        "# The scorecard",
        "",
        "GENERATED by `tools/scorecard.py --emit` — do not hand-edit. The table below is",
        "byte-identical to the block between the scorecard markers in `README.md`, and",
        "`tests/test_scorecard_doc.py` fails if the two ever disagree. To refresh both,",
        "run the tool with `--emit` (about 40 minutes) or dispatch the `scorecard`",
        "workflow from the Actions tab.",
        "",
        block,
        "",
        "## Gait modulation — the same animal in three media",
        "",
        "| medium | freq Hz | wavelength L | net mm/s | per-seed freq |",
        "|---|---|---|---|---|",
        *media_lines,
        "",
        "The per-seed column is load-bearing: buffer is bimodal at the shipped defaults",
        "(about one seed in five settles into a ~0.33 Hz whole-body standing flip by the",
        "gait window), and a mean ± sd cannot show that. A fallen seed is a visible",
        "outlier here rather than a mysterious spread.",
        "",
    ])
    with open(os.path.join(root, "docs", "scorecard.md"), "w") as f:
        f.write(doc)

    readme_path = os.path.join(root, "README.md")
    with open(readme_path) as f:
        readme = f.read()
    a, b = readme.find(BEGIN_MARK), readme.find(END_MARK)
    if a < 0 or b < 0:
        raise SystemExit("README.md is missing the scorecard markers; "
                         "the emitted table has nowhere to land")
    readme = readme[:a] + block + readme[b + len(END_MARK):]
    with open(readme_path, "w") as f:
        f.write(readme)
    print("\n  emitted docs/scorecard.md and the README block (%s, %s)" % (stamp, sha))


def main():
    jobs = [(m, s) for m in ("agar", "viscous", "buffer") for s in SEEDS]
    print("SCORECARD -- %d seeds x %.0f s, one configuration, one run\n" % (len(SEEDS), MEASURE))
    allrows = pooled(_job, jobs, procs=8)
    if not allrows:
        print("  no trials completed")
        return 1
    rows = [r for r in allrows if r["medium"] == "agar"]

    print("  %-27s %18s   %s" % ("quantity", "model (mean +- sd)", "animal"))
    for label, key, unit, target, fmt in ROWS:
        v = np.array([r[key] for r in rows], dtype=float)
        v = v[np.isfinite(v)]
        val = ("%s +- %s" % (fmt, fmt)) % (v.mean(), v.std())
        print("  %-27s %13s %-4s   %s" % (label, val, unit, target))

    d = [r["direction"] for r in rows]
    print("  %-27s %13s %-4s   %s"
          % ("Wave direction", "%d/%d head->tail" % (d.count("head->tail"), len(d)), "",
             "head -> tail"))
    # Swimming efficiency, which is a buffer measurement and so cannot come from the agar
    # rows above. It is forward speed over the speed of the wave that produces it, and it
    # needs no run of its own: the frequency and wavelength are already measured, and the
    # wavelength is in body lengths, so the wave speed is f * lambda * L. The README
    # carried this row for a year with no tool behind it at all.
    swim = [r for r in allrows if r["medium"] == "buffer"]
    if swim:
        L = Params().body.length
        uc = np.array([r["speed"] / (r["freq"] * r["wavelength"] * L) for r in swim])
        uc = uc[np.isfinite(uc)]
        print("  %-27s %13s %-4s   %s"
              % ("Swimming efficiency U/c", "%.3f +- %.3f" % (uc.mean(), uc.std()), "",
                 "0.08 +- 0.01, buffer"))

    rest = _rest()
    print("  %-27s %13s %-4s   %s"
          % ("Resting potentials", "%.0f to %.0f" % (rest["v_lo"], rest["v_hi"]),
             "mV", "-75 to -25"))
    # The extremes are two cells out of 302; where the population actually sits is the
    # median, and it is the number the README quotes when it says the published g_leak
    # would have put the whole network 55 mV above every recording ever made.
    print("  %-27s %13s %s" % ("  median of the 302", "%.0f" % rest["v_med"], "mV"))
    print("  %-27s %13s %-4s   %s"
          % ("Muscle resting potential", "%.1f" % rest["m_lo"], "mV", "-25.0 +- 1.0"))

    # The same two populations while the animal is actually crawling, which is a different
    # measurement and was for years reported under the resting rows' labels. It is kept
    # because it is the one place `v_clamp` becomes visible: the last line is the fraction
    # of the window in which some neuron is sitting on a clamp, and a graded,
    # sodium-channel-free network has no business being on one at all.
    print("  %-27s %13s %-4s   %s"
          % ("Neuron potentials, crawling",
             "%.0f to %.0f" % (np.mean([r["v_lo"] for r in rows]),
                               np.mean([r["v_hi"] for r in rows])),
             "mV", "span visited, not a rest"))
    print("  %-27s %13s %-4s   %s"
          % ("Muscle potentials, crawling",
             "%.0f to %.0f" % (np.mean([r["m_lo"] for r in rows]),
                               np.mean([r["m_hi"] for r in rows])),
             "mV", "span visited, not a rest"))
    clamp = Params().neural.v_clamp
    print("  %-27s %13s %-4s   %s"
          % ("  time on a clamp",
             "%.0f%% / %.0f%%" % (100 * float(np.mean([r["rail_hi"] for r in rows])),
                                  100 * float(np.mean([r["rail_lo"] for r in rows]))),
             "", "at %+.0f / %+.0f mV -- should be neither" % (clamp[1], clamp[0])))

    # Gait modulation. The medium is the whole story of it: a real animal crawls slowly
    # on agar and swims fast in water, and the *direction* of that change is what this
    # model has historically got backwards.
    print()
    print("  GAIT MODULATION -- the same animal in three media")
    print("  %-9s %14s %12s %12s   %s" % ("medium", "freq Hz", "wavelen L", "net mm/s", "animal"))
    ref = {"agar": "0.30 Hz crawling", "viscous": "intermediate",
           "buffer": "1.76 Hz swimming"}
    for med in ("agar", "viscous", "buffer"):
        g = [r for r in allrows if r["medium"] == med]
        if not g:
            continue
        f_ = np.array([r["freq"] for r in g])
        w_ = np.array([r["wavelength"] for r in g])
        v_ = np.array([r["speed"] for r in g])
        print("  %-9s %7.2f +- %.2f %7.2f +- %.2f %7.3f +- %.3f   %s"
              % (med, f_.mean(), f_.std(), w_.mean(), w_.std(), v_.mean(), v_.std(),
                 ref[med]))
        # A mean +- sd cannot show a bimodal medium, and buffer IS one: at the shipped
        # defaults about one seed in five settles into a slow near-standing mode by the
        # gait window (measured 2026-08-25: seed 0 at 0.325 Hz with the wavelength
        # estimator reading 6.4 L off a whole-body standing flip, the other four at 0.850 Hz / 0.88 L --
        # the same bistability the amine notes hit at muscle coefficients >= 0.7,
        # present at defaults given ~45 s of settling). Per-seed frequencies are
        # therefore printed for every medium, so a fallen seed is a visible outlier
        # rather than a mysterious +-.
        print("  %-9s   per-seed freq: %s" % ("", " ".join("%.2f" % x for x in f_)))
    fa = np.mean([r["freq"] for r in allrows if r["medium"] == "agar"])
    fb = np.mean([r["freq"] for r in allrows if r["medium"] == "buffer"])
    print()
    print("  agar -> buffer: %.2f -> %.2f Hz. The animal goes 0.30 -> 1.76, so the model" % (fa, fb))
    print("  has this %s." % ("the right way round" if fb > fa else
                              "BACKWARDS -- it slows down in water where the animal speeds up"))

    print()
    print("  per-seed frequency: %s Hz"
          % " ".join("%.2f" % r["freq"] for r in sorted(rows, key=lambda x: x["seed"])))
    print("  the spread is the point. This gait has been bistable across seeds since day")
    print("  two, so any row quoted from a single run is a claim the model does not make.")
    if "--emit" in sys.argv[1:]:
        _emit(_aggregate(allrows, rest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
