"""Does the browser run the same animal as the Python, once the noise is switched on?

`wasm/conform.mjs` answers a narrower question very well: with the noise off, the two
implementations agree to 5e-11 mV over 4000 steps. That check is what caught a missing
field-diffusion step and a food skirt that did not exist on the Python side, and it should
stay exactly as it is.

But nothing runs with the noise off. The browser runs noisy, every assay runs noisy, and
the model's own behavioural claims are all noisy-path claims. Conformance covers a mode
neither deployment uses, and `wasm/README.md` said the noisy case was "checked on gait
statistics instead", which was not true of any code in this repository. This is that check.

With noise on the two cannot agree sample for sample, and should not be asked to: one
draws from numpy's PCG64 through a ziggurat sampler, the other from xoshiro256++ through
Box-Muller. Both are correct standard normals driving the same Ornstein-Uhlenbeck process
with the same constants out of the same model file, so the claim available is statistical
-- the same animal, not the same trajectory.

**Both arms are measured by the code in this file.** The WebAssembly side dumps raw
curvature, centroid and gate state and computes nothing; every number below is produced by
one implementation reading two sets of arrays. That is the same reasoning the model file
rests on: if each side computed its own frequency, a disagreement would be ambiguous
between the model and the metric, and the metric is much the easier of the two to get
wrong.

Run:

    node wasm/trajectories.mjs 8 60           # the browser's animal
    PYTHONPATH=. .venv/bin/python tools/parity.py 8 60
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.diagnose_loop import travelling_index, _dominant          # noqa: E402
from tools.stats import bootstrap_ci, two_sample_ci, mde, fmt, clears_zero  # noqa: E402
from worm.params import Params                                        # noqa: E402

STRIDE = 40          # must match wasm/trajectories.mjs
WARMUP = 4.0


# --------------------------------------------------------------------------- metrics ---

def metrics(kappa, cx, cy, fwd, dt):
    """Every number this tool reports, from raw arrays and nothing else.

    kappa  (samples, joints)   body curvature, 1/mm
    cx, cy (samples,)          centroid, mm
    fwd    (samples,)          1 while the direction gate says forward
    dt                         seconds between samples
    """
    fs = 1.0 / dt
    out = {}

    mid = kappa[:, kappa.shape[1] // 2]
    freq, power = _dominant(mid - mid.mean(), fs)
    out["freq"] = freq
    out["power"] = power

    # Phase gradient along the body at the dominant frequency: wavelength and direction.
    # joint_s is arange(1, n+1)/(n+1) on both sides -- it comes from the body discretisation,
    # not from either implementation's choices.
    n_j = kappa.shape[1]
    s = np.arange(1, n_j + 1) / (n_j + 1)
    w = np.exp(-2j * np.pi * freq * np.arange(len(kappa)) / fs)
    comp = (kappa - kappa.mean(axis=0)).T @ w
    phase = np.unwrap(np.angle(comp))
    keep = (s > 0.15) & (s < 0.85)
    slope = np.polyfit(s[keep], phase[keep], 1)[0]
    out["wavelength"] = 2 * np.pi / abs(slope) if abs(slope) > 1e-9 else np.inf
    out["head_to_tail"] = 1.0 if slope < 0 else 0.0

    out["twi"] = travelling_index(kappa)
    out["kappa_rms"] = float(np.sqrt((kappa ** 2).mean()))
    out["kappa_max"] = float(np.abs(kappa).max())

    # Speed over the whole window rather than a rolling estimate, so it is a property of
    # the trajectory and not of either implementation's smoothing.
    span = (len(cx) - 1) * dt
    steps = np.hypot(np.diff(cx), np.diff(cy))
    out["path_speed"] = float(steps.sum() / span)
    out["net_speed"] = float(np.hypot(cx[-1] - cx[0], cy[-1] - cy[0]) / span)
    out["net_over_path"] = out["net_speed"] / max(out["path_speed"], 1e-12)

    # Behaviour, not gait. The reversal rate is the thing the whole command layer exists to
    # set, and it is downstream of the noise in a way the wave is not -- so if the two
    # generators differ in any way that matters, this is where it should show first.
    f = np.asarray(fwd, dtype=float)
    out["frac_forward"] = float(f.mean())
    out["reversals_per_min"] = float((np.diff(f) < 0).sum() / (span / 60.0))
    return out


METRICS = [
    ("undulation frequency", "freq", "Hz", "%.3f"),
    ("wavelength", "wavelength", "L", "%.3f"),
    ("travelling-wave index", "twi", "", "%.3f"),
    ("curvature rms", "kappa_rms", "1/mm", "%.3f"),
    ("curvature peak", "kappa_max", "1/mm", "%.3f"),
    ("path speed", "path_speed", "mm/s", "%.4f"),
    ("net speed", "net_speed", "mm/s", "%.4f"),
    ("net / path", "net_over_path", "", "%.3f"),
    ("fraction forward", "frac_forward", "", "%.3f"),
    ("reversals", "reversals_per_min", "/min", "%.2f"),
]


# ---------------------------------------------------------------------- the two arms ---

def python_arm(seed_seconds):
    """One Python animal, noisy, on a bare plate. Runs in its own process via pooled()."""
    seed, seconds = seed_seconds["seed"], seed_seconds["seconds"]
    from worm.engine import Simulation
    from worm.world import World

    p = Params()
    world = World(p.world, np.random.default_rng(0))
    sim = Simulation(p, seed=seed, world=world, placement=(0.0, 0.0, 0.0))
    sim.run(WARMUP)

    n = int(seconds / sim.dt / STRIDE)
    kappa = np.empty((n, sim.body.curvature().size))
    cx = np.empty(n)
    cy = np.empty(n)
    fwd = np.empty(n)
    for i in range(n):
        for _ in range(STRIDE):
            sim.step()
        kappa[i] = sim.body.curvature()
        nodes = sim.body.nodes()
        cx[i] = nodes[:, 0].mean()
        cy[i] = nodes[:, 1].mean()
        fwd[i] = 1.0 if sim.senses.going_forward else 0.0

    # Through float32 and back, because that is what the WebAssembly arm's arrays went
    # through on their way to disk. The quantisation is far below anything these sample
    # sizes can resolve, but making the two arms symmetric costs one line and removes an
    # entire category of "is that the model or is that the dump format?".
    m = metrics(kappa.astype(np.float32).astype(float),
                cx.astype(np.float32).astype(float),
                cy.astype(np.float32).astype(float),
                fwd, sim.dt * STRIDE)
    m["seed"] = seed
    return m


def wasm_arm(web="web"):
    """Read what wasm/trajectories.mjs dumped, and measure it with the same function."""
    meta_path = os.path.join(web, "traj-wasm.json")
    bin_path = os.path.join(web, "traj-wasm.bin")
    if not os.path.exists(meta_path) or not os.path.exists(bin_path):
        print("no WebAssembly trajectories. Run:\n"
              "  node wasm/trajectories.mjs %d %g" % (SEEDS, SECONDS), file=sys.stderr)
        return None
    meta = json.load(open(meta_path))
    raw = np.fromfile(bin_path, dtype=np.uint8)
    ns, nsamp, nj = meta["seeds"], meta["samples"], meta["joints"]

    off = 0
    k = np.frombuffer(raw, np.float32, ns * nsamp * nj, off).reshape(ns, nsamp, nj)
    off += ns * nsamp * nj * 4
    cx = np.frombuffer(raw, np.float32, ns * nsamp, off).reshape(ns, nsamp); off += ns * nsamp * 4
    cy = np.frombuffer(raw, np.float32, ns * nsamp, off).reshape(ns, nsamp); off += ns * nsamp * 4
    fwd = np.frombuffer(raw, np.uint8, ns * nsamp, off).reshape(ns, nsamp)

    rows = []
    for s in range(ns):
        m = metrics(k[s].astype(float), cx[s].astype(float), cy[s].astype(float),
                    fwd[s].astype(float), meta["dt"])
        m["seed"] = s
        rows.append(m)
    return rows, meta


# ------------------------------------------------------------------------- reporting ---

def report(py, wa, meta):
    print("GAIT PARITY -- the Python model against the WebAssembly port, noise ON\n")
    print("  %d Python animals and %d browser animals, %g s each after a %g s warm-up,"
          % (len(py), len(wa), meta["seconds"], meta["warmup"]))
    print("  on a bare plate. The arms are NOT paired: seed 3 does not name the same")
    print("  animal on both sides, because the two draw noise from different generators.")
    print("  Every number below is computed by tools/parity.py from raw arrays, for both")
    print("  arms, so a disagreement cannot be a disagreement about the measure.\n")

    print("  %-22s %14s %14s   %-26s" % ("", "python", "wasm", "difference (wasm - python)"))
    disagreements = []
    for label, key, unit, spec in METRICS:
        a = np.array([r[key] for r in py], dtype=float)
        b = np.array([r[key] for r in wa], dtype=float)
        am, alo, ahi = bootstrap_ci(a)
        bm, blo, bhi = bootstrap_ci(b)
        d, dlo, dhi = two_sample_ci(a, b)
        flag = ""
        if clears_zero(dlo, dhi):
            # Relative to the Python arm's own mean, so "different" means different at a
            # scale that matters rather than different in the tenth decimal.
            rel = abs(d) / max(abs(am), 1e-12)
            flag = "  <-- differs" + (" (%.0f%%)" % (100 * rel) if rel > 0.005 else " (tiny)")
            disagreements.append((label, d, dlo, dhi, rel))
        print("  %-22s %14s %14s   %-26s%s"
              % (label + (" " + unit if unit else ""),
                 spec % am, spec % bm, fmt(d, dlo, dhi, spec), flag))

    print("\n  smallest difference these sample sizes could resolve, per metric:")
    for label, key, unit, spec in METRICS:
        a = np.array([r[key] for r in py], dtype=float)
        b = np.array([r[key] for r in wa], dtype=float)
        print("    %-22s %s" % (label, spec % float(np.hypot(mde(a), mde(b)))))

    print()
    if not disagreements:
        print("  No metric separates the two arms. The browser is running the same animal")
        print("  as the Python, to within what this many seeds can see -- which is the")
        print("  strongest claim available once the two draw from different generators.")
        return 0
    print("  %d metric(s) separate the two arms:" % len(disagreements))
    for label, d, lo, hi, rel in disagreements:
        print("    %-22s %s   (%.1f%% of the Python mean)"
              % (label, fmt(d, lo, hi, "%+.4f"), 100 * rel))
    print("\n  A difference here is not automatically a bug -- with unpaired arms and few")
    print("  seeds, a metric can separate by chance. But it is not nothing either: the two")
    print("  implementations are supposed to be the same model, and the noise is supposed")
    print("  to be noise. Re-run with more seeds before concluding either way.")
    return 1


SEEDS, SECONDS = 8, 60.0


def main(argv):
    global SEEDS, SECONDS
    if len(argv) > 0:
        SEEDS = int(argv[0])
    if len(argv) > 1:
        SECONDS = float(argv[1])

    got = wasm_arm()
    if got is None:
        return 2
    wa, meta = got
    if meta["seeds"] != SEEDS or abs(meta["seconds"] - SECONDS) > 1e-9:
        print("the dumped trajectories are %d seeds x %g s, not %d x %g. Re-run:\n"
              "  node wasm/trajectories.mjs %d %g"
              % (meta["seeds"], meta["seconds"], SEEDS, SECONDS, SEEDS, SECONDS),
              file=sys.stderr)
        return 2
    if meta["stride"] != STRIDE:
        print("stride mismatch: dump %d, this tool %d" % (meta["stride"], STRIDE),
              file=sys.stderr)
        return 2

    from tools.assays import pooled
    print("running %d Python animals for %g s each..." % (SEEDS, SECONDS), file=sys.stderr)
    py = pooled(python_arm, [{"seed": s, "seconds": SECONDS} for s in range(SEEDS)])
    py = [r for r in py if r]
    if len(py) < 2:
        print("too few Python trials finished", file=sys.stderr)
        return 2
    return report(py, wa, meta)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
