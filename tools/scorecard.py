"""Every headline number in one place, across seeds, next to what a real animal does.

The README carries a table of what this model gets right and wrong. Its rows have
historically been filled in at different times from different runs, which is how it came
to quote a crawling speed from day two beside a frequency from day nine -- numbers that
were never true of the same animal. This measures them all at once, from the same
configuration, and reports the seed-to-seed spread rather than one run's luck.

The spread matters more than usual here. The gait has been bistable across seeds since
day two, and a single-seed number can be a full standard deviation from the mean, so any
row quoted without one is a claim the model does not support.

Run:  PYTHONPATH=. .venv/bin/python tools/scorecard.py
"""

from __future__ import annotations

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import MEDIA, Params

MEASURE = 40.0
SEEDS = (0, 1, 3, 5, 7)


def _job(seed):
    p = Params()
    sim = Simulation(p, seed=seed, world=bare_world(p))

    sim.run(6.0)
    start = sim.body.centroid().copy()
    t0 = sim.t
    prev, path = start.copy(), 0.0
    n = int(MEASURE / sim.dt)
    every = max(1, int(round(0.05 / sim.dt)))
    for i in range(n):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    net = float(np.linalg.norm(sim.body.centroid() - start))
    span = sim.t - t0

    # Gait metrics from a second stretch, so the two do not share a window.
    r = analyse(sim, seconds=MEASURE)
    return dict(seed=seed, freq=r["freq"], wavelength=r["wavelength"], twi=r["twi"],
                k_rms=r["kappa_rms"], k_max=r["kappa_max"], dv_corr=r["dv_corr"],
                direction=r["direction"], speed=net / span,
                net_path=net / max(path, 1e-9),
                v_lo=float(np.min(sim.nervous.V)), v_hi=float(np.max(sim.nervous.V)),
                m_lo=float(np.min(sim.muscles.V)), m_hi=float(np.max(sim.muscles.V)))


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


def main():
    print("SCORECARD -- %d seeds x %.0f s, one configuration, one run\n" % (len(SEEDS), MEASURE))
    rows = pooled(_job, list(SEEDS), procs=8)
    if not rows:
        print("  no trials completed")
        return 1

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
    print("  %-27s %13s %-4s   %s"
          % ("Resting potentials", "%.0f to %.0f" % (np.mean([r["v_lo"] for r in rows]),
                                                     np.mean([r["v_hi"] for r in rows])),
             "mV", "-75 to -25"))
    print("  %-27s %13s %-4s   %s"
          % ("Muscle potentials", "%.0f to %.0f" % (np.mean([r["m_lo"] for r in rows]),
                                                    np.mean([r["m_hi"] for r in rows])),
             "mV", "-25.0 +- 1.0"))

    print()
    print("  per-seed frequency: %s Hz"
          % " ".join("%.2f" % r["freq"] for r in sorted(rows, key=lambda x: x["seed"])))
    print("  the spread is the point. This gait has been bistable across seeds since day")
    print("  two, so any row quoted from a single run is a claim the model does not make.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
