"""Why the animal never reverses, and what it costs to let him.

Triage found three things at once, and they are one thing:

  * chemosensory drive reaching ASE is 0.48 pA rms against a 2.2 pA noise floor
  * one reversal across six animals in six minutes
  * the command gate reads forward 0.91 / backward 0.25 in *every* animal, to two
    decimals, for the whole run

The third explains the second. `tonic_forward` injects 90 pA into AVB continuously, which
pins it near saturation; the proprioceptive gate then cubes and normalises AVB against
AVA, giving the forward generator 98% of the drive permanently. There is no dynamic range
left for a reversal to win, so no sensory input of any size could produce one.

This sweeps the two knobs that could restore it and checks what each costs. Reducing the
tonic drive is not free: the same AVB activity gates the B-class proprioceptive loop that
produces forward locomotion, so net speed is measured alongside.
"""

from __future__ import annotations

import dataclasses
import itertools

import numpy as np

from tools.assays import _clean_plate, estimate, pooled, reversals, run_trial, SAMPLE_DT
from worm.params import Params

DURATION = 70.0
SEEDS = (0, 3, 7)


def _job(job):
    tonic, gain, seed = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, tonic_forward=tonic, chemo_gain=gain))
    ang = (seed % 6) * (2 * np.pi / 6)
    tr = run_trial(_clean_plate(), (0.0, 0.0, float(ang)), DURATION, seed, params=p)

    rev = reversals(tr)
    ev = np.diff(rev.astype(int)) > 0
    dc = tr["d_attractant"][1:]
    up, down = dc > 0, dc < 0
    rate_up = ev[up].sum() / max(up.sum() * SAMPLE_DT, 1e-9) * 60.0
    rate_down = ev[down].sum() / max(down.sum() * SAMPLE_DT, 1e-9) * 60.0

    # Locomotion has to survive whatever we do to the command drive.
    d = np.hypot(tr["x"][-1] - tr["x"][0], tr["y"][-1] - tr["y"][0])
    path = float(np.hypot(np.diff(tr["x"]), np.diff(tr["y"])).sum())
    return dict(tonic=tonic, gain=gain, seed=seed,
                n_rev=int(ev.sum()), frac_rev=float(rev.mean()),
                rate_up=rate_up, rate_down=rate_down,
                gate_f=float(tr["gate_forward"].mean()),
                gate_b=float(tr["gate_backward"].mean()),
                net=d / (tr["t"][-1] - tr["t"][0]),
                ratio=d / max(path, 1e-9))


def main():
    jobs = list(itertools.product([90.0, 45.0, 22.0, 10.0], [26.0, 120.0], SEEDS))
    print("estimated %.0f s for %d trials" % (estimate(len(jobs), DURATION), len(jobs)))
    rows = pooled(_job, jobs)

    print("\n tonic  chemo   reversals/animal  %rev   gate f/b     rev/min up|down"
          "   net mm/s  net/path")
    agg = {}
    for r in rows:
        agg.setdefault((r["tonic"], r["gain"]), []).append(r)
    for (tonic, gain), g in sorted(agg.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
        f = lambda k: np.mean([x[k] for x in g])       # noqa: E731
        print("  %4.0f   %4.0f       %5.1f        %4.1f%%  %.2f/%.2f    %5.2f | %5.2f"
              "     %.4f    %.3f"
              % (tonic, gain, f("n_rev"), 100 * f("frac_rev"), f("gate_f"), f("gate_b"),
                 f("rate_up"), f("rate_down"), f("net"), f("ratio")))
    print("\n  reference: unchanged model is tonic 90 / chemo 26, net ~0.17 mm/s.")
    print("  what we want: reversals present, 'down' rate above 'up' rate (turns")
    print("  suppressed while conditions improve), and net speed not collapsed.")


if __name__ == "__main__":
    main()
