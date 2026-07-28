"""How much of the available thrust is the nervous system actually getting?

The animal crawls at 0.105 mm/s against a measured 0.219, with net-to-path at 0.53. Its
kinematics are close to right -- 0.45 Hz, 0.73 L, curvature rms 4.35 against a measured
4.3 -- so either the same body driven with a *clean* wave at those kinematics also manages
only 0.105, in which case the waveform is fine and the kinematics are the limit, or it
manages considerably more, in which case the circuit is producing a shape that wastes
thrust and the kinematics are a red herring.

`tools/calibrate_body.py` already drives the body with a prescribed travelling moment and
no biology at all. This uses it as the ceiling: at each wavelength, sweep the moment
amplitude, and read off the speed at the amplitude that reproduces the animal's curvature.
Everything here is mechanics -- no neurons, no muscles, no feedback -- so whatever it says
is what the body can do if something drives it properly.

Two numbers to keep in view while reading it.

**The wave speed.** A travelling wave of frequency f and wavelength L moves along the body
at V = f*L, and the animal cannot advance faster than that: U/V is bounded above by 1 and
is well under it for any real gait. The model is at f = 0.45, L = 0.73, so V = 0.33 mm/s
and its 0.105 mm/s is U/V = 0.32.

**And the targets may not be mutually reachable.** The frequency target here is Fang-Yen
et al.'s 0.30 Hz and the speed target is Ramot et al.'s 0.219 mm/s, from different
experiments. Together with a 0.65 L wavelength they imply U/V = 0.219 / (0.30 * 0.65) =
1.12, which is above the bound -- so no animal and no model can satisfy all three at once.
One of them is measured under conditions the others were not. That is worth knowing before
anyone tunes towards all three.

What it found. Two things, and the second is the more useful.

**The circuit gets 62% of the thrust its own kinematics allow**, and the missing 38% is
accounted for exactly by the travelling-wave index. At 0.45 Hz and 0.73 L, a clean
prescribed wave reproducing the animal's curvature reaches 0.169 mm/s. The model reaches
0.105. Its travelling index is +0.61, and 0.169 * 0.61 = 0.103. A standing wave produces
no net thrust at all, so the fraction of the oscillation that travels *is* the fraction of
the ceiling the animal collects:

    net speed  ~  (mechanical ceiling at these kinematics)  x  (travelling index)

That holds to 2% here, and it makes the thrust problem and the travelling-index problem the
same problem, which is worth knowing before anyone goes looking for a separate one.

**And the speed target cannot be met at the frequency target.** A travelling wave of
frequency f and wavelength L moves along the body at V = f*L, and an inextensible body in a
viscous medium cannot advance faster than its own wave: U/V < 1 strictly, approaching 1
only as the drag anisotropy goes to infinity. The README quotes 0.219 mm/s (Ramot et al.)
beside 0.30 Hz and 0.65 L (Fang-Yen et al.), and

    U/V  =  0.219 / (0.30 * 0.65)  =  1.12

which is above the bound. No animal and no model can satisfy all three, because they come
from different experiments under different conditions. Measured here, at the agar
anisotropy of 40 that Berri et al. report and at the animal's own curvature, the mechanics
cap U/V at about 0.51 -- so 0.30 Hz and 0.65 L imply at most **0.099 mm/s**, and 0.219 mm/s
implies a frequency of **0.66 Hz**.

The model is at 0.105 mm/s and 0.45 Hz. Against a self-consistent reading of the animal it
is much closer than the table suggests, and the honest statement is that this project has
been scoring itself against a target set that contradicts itself.

Run:  PYTHONPATH=. .venv/bin/python tools/thrust.py
"""

from __future__ import annotations

import numpy as np

from tools.calibrate_body import prescribed_wave
from worm.params import Params

FREQ = 0.45              # the model's own, measured over five seeds
TARGET_KAPPA = 4.35      # likewise, and within error of the animal's 4.3
WAVELENGTHS = (0.55, 0.65, 0.73, 0.90, 1.10)
# Amplitude in uN*mm of prescribed joint moment. The first pass used 1 to 8 and was
# useless: even 1.0 bends the body to a curvature of 17 /mm against the 4.35 wanted,
# and past about 3 the animal coils, the speed goes non-monotonic and then negative.
# The physiological range for this body is an order of magnitude below that.
AMPLITUDES = (0.05, 0.10, 0.16, 0.22, 0.30, 0.45)


def main():
    p = Params()
    print("THRUST CEILING -- body alone, prescribed moment wave, no biology")
    print("  frequency %.2f Hz throughout; the model itself reaches 0.105 mm/s at"
          " curvature %.2f\n" % (FREQ, TARGET_KAPPA))

    print("  wavelen |  amplitude   curvature rms   fwd mm/s   U/V")
    best = {}
    for lam in WAVELENGTHS:
        rows = []
        for amp in AMPLITUDES:
            r = prescribed_wave(p, "agar", FREQ, lam, amp, seconds=14.0)
            rows.append((amp, r["kappa_rms"], r["forward_speed"]))
        for amp, k, v in rows:
            mark = ""
            print("   %.2f   |   %5.2f       %7.2f       %+.4f    %.2f%s"
                  % (lam, amp, k, v, v / (FREQ * lam), mark))
        # Interpolate the speed at the amplitude that reproduces the target curvature.
        ks = np.array([r[1] for r in rows])
        vs = np.array([r[2] for r in rows])
        if ks.min() <= TARGET_KAPPA <= ks.max():
            best[lam] = float(np.interp(TARGET_KAPPA, ks, vs))
        print()

    print("  speed at matched curvature (%.2f /mm), by wavelength:" % TARGET_KAPPA)
    for lam, v in sorted(best.items()):
        print("    %.2f L  ->  %+.4f mm/s   (U/V %.2f)" % (lam, v, v / (FREQ * lam)))
    if best:
        lam0 = min(best, key=lambda k: abs(k - 0.73))
        print()
        print("  at the model's own 0.73 L the mechanics give %.4f mm/s for the same"
              % best[lam0])
        print("  curvature. The model gets 0.105. The ratio is what the circuit is losing:")
        print("    %.0f%% of the achievable thrust." % (100 * 0.105 / best[lam0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
