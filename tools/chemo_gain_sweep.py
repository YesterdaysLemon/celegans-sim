"""Can chemosensory gain alone produce chemotaxis?

The wiring is fine -- ASE reaches AVA and AVB in two hops via AIY/AIB, which is the real
circuit. The problem is signal-to-noise. Measured on a standard plate:

    dC/dt reaching the nose      0.013 per s rms
    chemo_gain 26 pA/unit   ->   0.48 pA rms of drive
    background current noise     2.2 pA        (NeuralParams.noise_sigma)

so the chemical signal sits about five times *below* the noise the neuron already has.
Correlation of dC/dt with membrane potential, measured along the whole pathway, is
+0.010 at ASE and never exceeds +0.074 anywhere downstream -- and those downstream values
are the locomotor rhythm modulating both, not ASE driving anything.

This sweeps gain over a range wide enough to cross the noise floor. Two caveats worth
holding onto while reading the output:

  * The reversal detector compares centroid velocity to body axis, which is only
    meaningful when the animal is actually translating. Rows with net/path below ~0.3
    are a worm sloshing in place, and their reversal counts are artefacts, not turns.
    That is why the gate sweep's apparent 25 reversals at tonic 22 were not real.
  * Wicks et al. injected 10-250 pA experimentally. Gains beyond that are off the end of
    what anyone has done to a real neuron, and should be read as telling us something is
    wrong elsewhere rather than as a value to adopt.
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import _clean_plate, estimate, pooled, reversals, run_trial, SAMPLE_DT
from worm.params import Params

DURATION = 90.0
SEEDS = (0, 3, 7)
SRC = np.array([12.0, 0.0])


def _job(job):
    gain, tau, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, chemo_gain=gain, chemo_tau_adapt=tau))
    ang = (seed % 6) * (2 * np.pi / 6)
    tr = run_trial(_clean_plate(), (0.0, 0.0, float(ang)), DURATION, seed, params=p)

    d0 = np.hypot(tr["x"][0] - SRC[0], tr["y"][0] - SRC[1])
    d1 = np.hypot(tr["x"][-1] - SRC[0], tr["y"][-1] - SRC[1])
    path = float(np.hypot(np.diff(tr["x"]), np.diff(tr["y"])).sum())
    net = float(np.hypot(tr["x"][-1] - tr["x"][0], tr["y"][-1] - tr["y"][0]))

    rev = reversals(tr)
    ev = np.diff(rev.astype(int)) > 0
    dc = tr["d_attractant"][1:]
    up, down = dc > 0, dc < 0
    rate_up = ev[up].sum() / max(up.sum() * SAMPLE_DT, 1e-9) * 60.0
    rate_down = ev[down].sum() / max(down.sum() * SAMPLE_DT, 1e-9) * 60.0

    # Weathervaning: does the forward run curve towards the source?
    hd = np.unwrap(np.arctan2(tr["dir_y"], tr["dir_x"]))
    wn = max(3, int(round(2.0 / SAMPLE_DT)))
    hd = np.convolve(hd, np.ones(wn) / wn, mode="same")
    turn = np.gradient(hd, tr["t"]) * 180 / np.pi
    bearing = (np.arctan2(SRC[1] - tr["y"], SRC[0] - tr["x"])
               - np.arctan2(tr["dir_y"], tr["dir_x"]))
    bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
    ok = ~rev & (np.abs(bearing) < np.pi / 2)
    slope = float(np.polyfit(bearing[ok], turn[ok], 1)[0]) if ok.sum() >= 20 else np.nan

    return dict(gain=gain, tau=tau, seed=seed, approach=d0 - d1,
                drive=float(gain * np.sqrt((dc ** 2).mean())),
                rate_up=rate_up, rate_down=rate_down, n_rev=int(ev.sum()),
                slope=slope, netpath=net / max(path, 1e-9),
                speed=net / (tr["t"][-1] - tr["t"][0]))


def main():
    jobs = list(itertools.product([26.0, 130.0, 400.0, 1200.0], [3.5, 12.0], SEEDS))
    print("estimated %.0f s for %d trials" % (estimate(len(jobs), DURATION), len(jobs)))
    rows = pooled(_job, jobs)

    agg = {}
    for r in rows:
        agg.setdefault((r["gain"], r["tau"]), []).append(r)
    print("\n  gain  tau_ad   drive pA   approach mm    rev/min up|down   weathervane"
          "   net/path")
    for (gain, tau), g in sorted(agg.items()):
        f = lambda k: np.nanmean([x[k] for x in g])            # noqa: E731
        sd = np.std([x["approach"] for x in g])
        flag = "" if f("netpath") > 0.3 else "   <- not translating, turns unreliable"
        print("  %4.0f   %4.1f     %6.2f     %+5.2f+-%4.2f    %5.2f | %5.2f      %+6.2f"
              "      %.2f%s"
              % (gain, tau, f("drive"), f("approach"), sd, f("rate_up"), f("rate_down"),
                 f("slope"), f("netpath"), flag))
    print("\n  noise floor is 2.2 pA. Wicks et al. injected 10-250 pA experimentally.")
    print("  chemotaxis would show as: approach > 0 consistently, 'down' rate above")
    print("  'up' rate, and/or a positive weathervaning slope.")


if __name__ == "__main__":
    main()
