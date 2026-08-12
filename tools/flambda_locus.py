"""Does the model's (f, lambda) locus lie on the animal's crawl-to-swim line, or off it?

THE QUESTION, AND WHY IT IS THE ONE THAT GOES FIRST.

Every gait-modulation measurement in this repository so far has reported frequency and
wavelength as two columns, at two or three media. An external review pointed out that the
animal does not open up two numbers, it opens up their product -- wave speed v = f*lambda,
13.9x between crawling and swimming -- and that f and lambda are projections of a locus,
not two independent failures. NEXT.md turned that into a sharper structural question:

    This model carries a fixed temporal head lag *and* a fixed spatial proprioceptive
    reach -- two independent knobs, where a single per-segment propagation time would set
    both. Sweep the medium and plot the model's (f, lambda) points against the animal's
    crawl->swim line. If the model's locus slides *off* that line, the two knobs are
    genuinely independent here and are not in the animal -- one mechanism to find, not two.

The single-medium sweeps cannot answer this: `tools/wave_speed.py` established that reach
moves lambda with f flat to 1%, but that is a sweep of a *parameter* at fixed load. What
the animal sweeps is the *load*. Whether the model's f and lambda move together or apart
under a load sweep is unmeasured, and it is the axis the animal is actually measured on.

THE ANIMAL'S LINE.

Fang-Yen et al. (2010) PNAS 107:20323, the two ends of the continuum this repository
already quotes everywhere:

    crawl (agar, K = 40)      0.30 Hz   0.65 L    v = 0.195 L/s
    swim  (buffer, K = 1.58)  1.76 Hz   1.54 L    v = 2.71 L/s

The chord between them in the (f, lambda) plane has slope 0.61 L/Hz; in log-log it is
lambda proportional to f^0.49. The animal traverses it continuously as the fluid thins,
nothing about its nervous system changing on the way. "On the line" below always means
this chord, extended; the animal's intermediate points are a monotone curve near it, but
this repository pins only the two ends, so the chord is what the model is held against.

THE SWEEP.

Nine media, geometric interpolation of both drag coefficients between the shipped buffer
and agar endpoints (`worm/params.py::MEDIA`), so K runs 1.58 -> 40 geometrically. The
shipped "viscous" medium (K = 9) sits close to the midpoint of this continuum by
construction -- it was chosen the same way. Three seeds, default `Params()` throughout:
the medium is the only thing swept, exactly as in the animal's experiment.

WHAT EACH OUTCOME WOULD MEAN, fixed before the run.

  * **The locus tracks the chord** -- the perpendicular offset from the animal's line
    stays within seed noise while the along-chord coordinate advances. Then the model
    couples f and lambda the way the animal does and the failure is magnitude alone: one
    mechanism, too weak, and the two-independent-knobs suspicion is wrong.
  * **The locus leaves the chord** -- the perpendicular offset grows systematically as K
    falls, the log-log exponent sits well under the animal's 0.49. Then the medium
    reaches the frequency but not the wavelength, which is what a lag-set f and a fixed
    spatial reach would produce: two independent knobs here where the animal has one.
    The thing to look for is one mechanism that sets both -- a per-segment propagation
    time is the standing candidate -- not a frequency fix plus a wavelength fix.
  * **The locus is a point cloud, not a curve** -- all of the motion happens between
    K = 40 and K ~ 9 and nothing below, the saturation `MediumParams` documents in the
    frequency column reproduced in both coordinates. Then the locus question is moot
    below K = 9 and the saturation itself is the object: whatever couples the loop to
    the medium runs out exactly where swimming begins.

The second and third are not exclusive -- a locus can leave the chord *and* stop moving --
and the verdict below reports them separately for that reason.

What this run cannot say: *why* the wavelength does whatever it does. It measures the
shape of the locus, not the mechanism under it.

A wide point bought by a broken gait is not data, so TWI, curvature, net speed and
net/path are reported per medium, and any medium whose TWI falls below +0.4 is flagged
rather than silently averaged into the fits.

Run:  PYTHONPATH=. .venv/bin/python tools/flambda_locus.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import MEDIA, MediumParams, Params

MEASURE = 30.0
SEEDS = (0, 3, 7)
N_MEDIA = 9

# The animal's two ends (Fang-Yen et al. 2010): (freq Hz, wavelength L).
CRAWL = (0.30, 0.65)
SWIM = (1.76, 1.54)

# TWI below this and the point is a thrash, not a gait; it is shown but kept out of fits.
TWI_FLOOR = 0.4


def media_sweep(n: int = N_MEDIA) -> list[MediumParams]:
    """Geometric interpolation from buffer to agar, both coefficients, endpoints exact."""
    lo, hi = MEDIA["buffer"], MEDIA["agar"]
    out = []
    for u in np.linspace(0.0, 1.0, n):
        ct = float(lo.c_tangential * (hi.c_tangential / lo.c_tangential) ** u)
        cn = float(lo.c_normal * (hi.c_normal / lo.c_normal) ** u)
        out.append(MediumParams(name="sweep_u%.3f" % u, c_tangential=ct, c_normal=cn))
    return out


def _job(job):
    u_index, seed = job
    med = media_sweep()[u_index]
    p = dataclasses.replace(Params(), medium=med)
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)                       # settle onto whichever cycle the loop picks
    start = sim.body.centroid().copy()
    t0 = sim.t
    prev, path = start.copy(), 0.0
    every = max(1, int(round(0.05 / sim.dt)))
    for i in range(int(MEASURE / sim.dt)):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    net = float(np.linalg.norm(sim.body.centroid() - start))
    span = sim.t - t0

    r = analyse(sim, seconds=MEASURE)
    lam = r["wavelength"]
    return dict(u_index=u_index, K=med.anisotropy, seed=seed,
                freq=r["freq"], wavelength=lam,
                phase_v=lam * r["freq"] if np.isfinite(lam) else float("nan"),
                twi=r["twi"], k_rms=r["kappa_rms"], speed=net / span,
                net_path=net / max(path, 1e-9))


def _chord_coords(f: float, lam: float):
    """(along, perp) coordinates of a point against the animal's chord.

    `along` is the position along the crawl->swim chord as a fraction of its length --
    0 at the crawl end, 1 at the swim end. `perp` is the signed offset from the chord in
    L, positive above the line (longer wavelength than the animal at that frequency).
    """
    a = np.array(CRAWL)
    d = np.array(SWIM) - a
    length = float(np.linalg.norm(d))
    d_hat = d / length
    n_hat = np.array([-d_hat[1], d_hat[0]])
    rel = np.array([f, lam]) - a
    return float(rel @ d_hat) / length, float(rel @ n_hat)


def _plot(points):
    """ASCII (f, lambda) plane: the animal's chord and the model's locus on it.

    `points` is a list of (letter, f, lambda).
    """
    f_lo, f_hi, l_lo, l_hi = 0.2, 2.0, 0.5, 1.7
    W, H = 66, 22
    grid = [[" "] * W for _ in range(H)]

    def put(f, lam, ch):
        if not (np.isfinite(f) and np.isfinite(lam)):
            return
        x = int(round((f - f_lo) / (f_hi - f_lo) * (W - 1)))
        y = int(round((lam - l_lo) / (l_hi - l_lo) * (H - 1)))
        if 0 <= x < W and 0 <= y < H:
            grid[H - 1 - y][x] = ch

    for t in np.linspace(0.0, 1.0, 200):
        put(CRAWL[0] + t * (SWIM[0] - CRAWL[0]),
            CRAWL[1] + t * (SWIM[1] - CRAWL[1]), ".")
    put(*CRAWL, "C")
    put(*SWIM, "S")
    for ch, f, lam in points:
        put(f, lam, ch)

    print("  wavelength L")
    for row_i, row in enumerate(grid):
        lam_here = l_hi - row_i * (l_hi - l_lo) / (H - 1)
        label = "%4.2f |" % lam_here if row_i % 4 == 0 else "     |"
        print("  %s%s" % (label, "".join(row)))
    print("       +" + "-" * W)
    ticks = "        "
    for f in (0.25, 0.75, 1.25, 1.75):
        x = int(round((f - f_lo) / (f_hi - f_lo) * (W - 1)))
        ticks = ticks.ljust(8 + x) + ("%.2f" % f)
    print(ticks + "   freq Hz")
    print("  C = animal crawl (0.30 Hz, 0.65 L)   S = animal swim (1.76 Hz, 1.54 L)")
    print("  . = the chord between them, the line the animal traverses as the fluid thins")


def main():
    sweep = media_sweep()
    jobs = [(i, s) for s in SEEDS for i in range(len(sweep))]
    print("F-LAMBDA LOCUS -- %d media x %d seeds, %.0f s each" %
          (len(sweep), len(SEEDS), MEASURE))
    print("  does the model's locus lie on the animal's crawl->swim line, or off it?\n")
    rows = pooled(_job, jobs, procs=8, timeout=7200)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault(r["u_index"], []).append(r)
    mean = lambda g, k: float(np.nanmean([x[k] for x in g]))       # noqa: E731
    sd = lambda g, k: float(np.nanstd([x[k] for x in g]))          # noqa: E731

    print("\n  medium (K falling = fluid thinning, agar first as the animal's line is read)")
    print("     K      c_tan     c_norm  n | freq Hz         wavelen L      v=f*lam  "
          "TWI     k_rms  net mm/s  n/p")
    letters = {}
    table = []
    for rank, i in enumerate(sorted(agg, key=lambda j: -sweep[j].anisotropy)):
        g = agg[i]
        med = sweep[i]
        ch = chr(ord("a") + rank)
        letters[ch] = med.anisotropy
        fq, wl = mean(g, "freq"), mean(g, "wavelength")
        table.append((ch, med.anisotropy, fq, wl, mean(g, "twi"), len(g)))
        note = ""
        if med.anisotropy in (MEDIA["agar"].anisotropy, MEDIA["buffer"].anisotropy):
            note = "  <- shipped %s" % ("agar" if med.anisotropy > 2 else "buffer")
        if mean(g, "twi") < TWI_FLOOR:
            note += "  ** TWI below %.1f, kept out of fits" % TWI_FLOOR
        print("  %s %6.2f  %8.4f  %8.3f  %d | %6.3f +-%.3f  %5.2f +-%.2f    %6.3f   "
              "%+.3f  %5.2f  %.4f  %.2f%s"
              % (ch, med.anisotropy, med.c_tangential, med.c_normal, len(g),
                 fq, sd(g, "freq"), wl, sd(g, "wavelength"), mean(g, "phase_v"),
                 mean(g, "twi"), mean(g, "k_rms"), mean(g, "speed"),
                 mean(g, "net_path"), note))

    missing = [i for i in range(len(sweep)) if i not in agg]
    short = [(i, len(agg[i])) for i in sorted(agg) if len(agg[i]) < len(SEEDS)]
    if missing or short:
        print("\n  NOT EVERY CELL WAS MEASURED, so the locus below is incomplete:")
        for i in missing:
            print("    K = %.2f: no trial returned" % sweep[i].anisotropy)
        for i, n in short:
            print("    K = %.2f: %d of %d seeds" % (sweep[i].anisotropy, n, len(SEEDS)))

    print()
    _plot([(ch, fq, wl) for ch, _K, fq, wl, _twi, _n in table])
    print("  letters a..%s: the model, K = %s"
          % (chr(ord("a") + len(table) - 1),
             ", ".join("%.2f" % letters[c] for c in sorted(letters))))

    # The locus against the chord. Points below the TWI floor are shown above but do not
    # enter the fits -- a thrash has a frequency and a wavelength and neither means much.
    good = [(K, fq, wl) for _ch, K, fq, wl, twi, _n in table
            if twi >= TWI_FLOOR and np.isfinite(fq) and np.isfinite(wl)]
    print("\n  THE LOCUS AGAINST THE ANIMAL'S LINE")
    print("  along = fraction of the way from C to S; perp = offset from the line in L,")
    print("  positive = wavelength longer than the animal's at that frequency.")
    coords = []
    for K, fq, wl in good:
        along, perp = _chord_coords(fq, wl)
        coords.append((K, along, perp))
        print("    K %6.2f:  along %+.3f   perp %+.4f L" % (K, along, perp))

    if len(good) >= 3:
        fs = np.array([fq for _K, fq, _wl in good])
        ls = np.array([wl for _K, _fq, wl in good])
        b = float(np.polyfit(np.log(fs), np.log(ls), 1)[0])
        animal_b = float(np.log(SWIM[1] / CRAWL[1]) / np.log(SWIM[0] / CRAWL[0]))
        along0, perp0 = coords[0][1], coords[0][2]
        along1, perp1 = coords[-1][1], coords[-1][2]
        d_along, d_perp = along1 - along0, perp1 - perp0
        # Where the motion actually happens along K, both coordinates.
        f_span = fs.max() / max(fs.min(), 1e-9)
        l_span = ls.max() / max(ls.min(), 1e-9)
        # Motion below K = 9, as a fraction of total motion in f: the saturation check.
        below = [(K, fq) for K, fq, _wl in good if K <= 9.0]
        f_below = (max(f for _K, f in below) - min(f for _K, f in below)) \
            if len(below) >= 2 else 0.0
        f_total = float(fs.max() - fs.min())

        print("\n  VERDICT MATERIAL, in the docstring's terms")
        print("    log-log exponent d(ln lambda)/d(ln f) along the locus: %+.3f" % b)
        print("    the animal's chord: %+.3f" % animal_b)
        print("    spans across the sweep: f %.2fx, lambda %.2fx, v %.2fx"
              % (f_span, l_span,
                 (fs.max() * ls[np.argmax(fs)]) / max(fs.min() * ls[np.argmin(fs)], 1e-9)))
        print("    chord motion agar-end -> buffer-end: along %+.3f, perp %+.4f L"
              % (d_along, d_perp))
        print("    frequency motion at K <= 9: %.4f Hz of %.4f Hz total (%.0f%%)"
              % (f_below, f_total, 100.0 * f_below / max(f_total, 1e-9)))

        print("\n  VERDICT")
        seed_noise = 0.02   # typical +-sd on wavelength above, in L
        if abs(d_perp) <= 2 * seed_noise and d_along > 0:
            print("  The locus tracks the chord: perpendicular drift %.4f L is within seed"
                  % d_perp)
            print("  noise while the along-chord coordinate advances %+.3f. The model" % d_along)
            print("  couples f and lambda the way the animal does, and the failure is")
            print("  magnitude alone -- one weak mechanism, not two independent knobs.")
        elif d_perp < -2 * seed_noise:
            print("  The locus leaves the chord downward: perp drifts %+.4f L while along" % d_perp)
            print("  advances %+.3f, exponent %+.3f against the animal's %+.3f. The medium"
                  % (d_along, b, animal_b))
            print("  reaches the frequency but not the wavelength -- what a lag-set f and a")
            print("  fixed spatial reach would produce. Two independent knobs here, one")
            print("  mechanism in the animal; look for the one that sets both.")
        else:
            print("  The locus leaves the chord upward, perp %+.4f L -- the wavelength" % d_perp)
            print("  outruns the animal's at matched frequency, which nothing predicted.")
        if f_total > 0 and f_below / f_total < 0.15:
            print("\n  And separately: the locus is bunched, not a curve. %.0f%% of the"
                  % (100.0 * (1 - f_below / f_total)))
            print("  frequency motion happens above K = 9 -- the saturation MediumParams")
            print("  documents holds for the locus as a whole. Below K = 9 there is no")
            print("  locus to be on or off any line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
