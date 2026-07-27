"""How much of the body's motion is actually part of the wave, position by position.

The travelling-wave index says whether the wave travels; it does not say how much of the
body's movement belongs to the wave at all. Those came apart in this model: the amplitude
*at the wave frequency* decays about sevenfold from head to tail, while the total curvature
variance is roughly equal head and tail. The posterior is moving as much as the anterior --
it is simply not moving in time with it.

This measures that directly. For each point along the body:

    coherence(s) = variance within a narrow band around the wave frequency
                   -----------------------------------------------------
                                    total variance

Coherence near 1 means everything that point does is part of the undulation. Near 0 means
it is thrashing independently. A real worm should be strongly coherent along its whole
length; anything that fixes this model has to raise the posterior numbers.

    PYTHONPATH=. python tools/coherence.py
    PYTHONPATH=. python tools/coherence.py --seconds 40
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from tools.diagnose_loop import bare_world, travelling_index
from worm.engine import Simulation
from worm.params import Params

BANDS = ((0.00, 0.20, "head"),
         (0.20, 0.40, "neck"),
         (0.40, 0.60, "midbody"),
         (0.60, 0.80, "posterior"),
         (0.80, 1.00, "tail"))


def profile(kappa: np.ndarray, fs: float, band_frac: float = 0.35) -> tuple:
    """Per-position coherence with the dominant frequency, and that frequency."""
    k = kappa - kappa.mean(axis=0)
    win = np.hanning(k.shape[0])[:, None]
    spec = np.abs(np.fft.rfft(k * win, axis=0)) ** 2
    fr = np.fft.rfftfreq(k.shape[0], 1.0 / fs)

    # Dominant frequency taken from the midbody, where the undulation is cleanest.
    mid = spec[:, k.shape[1] // 2]
    usable = (fr > 0.1) & (fr < 4.0)
    f0 = float(fr[usable][np.argmax(mid[usable])])

    band = (fr > f0 * (1 - band_frac)) & (fr < f0 * (1 + band_frac))
    total = spec.sum(axis=0)
    inband = spec[band].sum(axis=0)
    return inband / np.maximum(total, 1e-12), f0, np.sqrt(total)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=35.0)
    ap.add_argument("--seeds", type=int, nargs="*", default=[0, 3])
    args = ap.parse_args(argv)

    p = Params()
    for seed in args.seeds:
        sim = Simulation(p, seed=seed, world=bare_world(p))
        sim.run(8.0)
        stride = 40
        kap = []
        for i in range(int(args.seconds / sim.dt)):
            sim.step()
            if i % stride == 0:
                kap.append(sim.body.curvature().copy())
        kap = np.array(kap)
        fs = 1.0 / (sim.dt * stride)
        coh, f0, amp = profile(kap, fs)
        s = sim.muscles.joint_s

        print("seed %d -- undulating at %.2f Hz, whole-body travelling index %+.3f"
              % (seed, f0, travelling_index(kap)))
        print("   %-11s %10s %12s %10s" % ("region", "coherence", "amplitude", "TWI"))
        for lo, hi, label in BANDS:
            m = (s >= lo) & (s < hi)
            if not m.any():
                continue
            print("   %-11s %10.2f %12.2f %+10.3f"
                  % (label, float(coh[m].mean()), float(amp[m].mean()),
                     travelling_index(kap[:, m])))
        print()
    print("coherence = fraction of that point's motion that sits at the wave frequency.")
    print("1.0 means everything it does is part of the undulation; 0 means it is thrashing")
    print("independently. Whatever fixes this model has to raise the posterior numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
