"""How much of the available thrust is the nervous system actually getting?

Is the animal getting the speed its own kinematics allow, or is the circuit producing a
shape that wastes thrust? Either the same body driven with a *clean* wave at the same
frequency, wavelength and curvature manages what the model manages -- in which case the
waveform is fine and the kinematics are the limit -- or it manages considerably more, in
which case the wave is the problem and the kinematics are a red herring.

`tools/calibrate_body.py` already drives the body with a prescribed travelling moment and
no biology at all. This uses it as the ceiling: at each wavelength, sweep the moment
amplitude, and read off the speed at the amplitude that reproduces the animal's curvature.
Everything here is mechanics -- no neurons, no muscles, no feedback -- so whatever it says
is what the body can do if something drives it properly.

Two numbers to keep in view while reading it.

**The wave speed.** A travelling wave of frequency f and wavelength L moves along the body
at V = f*L, and the animal cannot advance faster than that: U/V is bounded above by 1 and
is well under it for any real gait. The model is at f = 0.67, L = 0.83, so V = 0.56 mm/s
and its 0.275 mm/s is U/V = 0.49.

**And the targets may not be mutually reachable.** The frequency target here is Fang-Yen
et al.'s 0.30 Hz and the speed target is Ramot et al.'s 0.219 mm/s, from different
experiments. Together with a 0.65 L wavelength they imply U/V = 0.219 / (0.30 * 0.65) =
1.12, which is above the bound -- so no animal and no model can satisfy all three at once.
One of them is measured under conditions the others were not. That is worth knowing before
anyone tunes towards all three.

What it found, in two passes, and the first pass got one of them wrong.

**The speed target cannot be met at the frequency target.** A travelling wave of frequency
f and wavelength L moves along the body at V = f*L, and an inextensible body in a viscous
medium cannot advance faster than its own wave: U/V < 1 strictly, approaching 1 only as the
drag anisotropy goes to infinity. The README quotes 0.219 mm/s (Ramot et al.) beside
0.30 Hz and 0.65 L (Fang-Yen et al.), and

    U/V  =  0.219 / (0.30 * 0.65)  =  1.12

which is above the bound. No animal and no model can satisfy all three, because they come
from different experiments under different conditions. Measured here, at the agar
anisotropy of 40 that Berri et al. report and at the animal's own curvature, the mechanics
cap U/V at about **0.50** across every wavelength tried -- so 0.30 Hz and 0.65 L imply at
most 0.099 mm/s, and 0.219 mm/s implies a frequency near 0.66 Hz. That stands.

**And "thrust = ceiling x travelling index" does not.** The first pass measured the model
at 0.105 mm/s against a ceiling of 0.169 with a travelling index of 0.61, noted that
0.169 * 0.61 = 0.103, and concluded that the fraction of the oscillation that travels is
the fraction of the ceiling collected. It was a coincidence. Re-measured at the model's
current kinematics -- 0.67 Hz, 0.83 L, curvature 4.51 -- the ceiling is 0.274 mm/s and the
model reaches **0.275**, which is 100% of it, at a travelling index of 0.85. The
relationship is withdrawn.

What replaces it is more useful anyway. The model is now extracting essentially all the
thrust a sinusoidal wave of its own kinematics can produce -- U/V = 0.49 against a ceiling
of 0.50 -- so **speed is no longer a waveform problem**. Going faster now means different
kinematics rather than a cleaner wave, and going slower, which is what matching the
animal's 0.219 would take, means a lower frequency or a shorter wavelength: at U/V near
0.5, 0.219 mm/s wants f*L close to 0.44, where the model sits at 0.56.

(The ceiling here is the ceiling for a *sinusoidal* prescribed moment, which is not the
optimal waveform. A reflex-generated wave reaching 100% of it is not a paradox; it means
the circuit's waveform is at least as good as a sinusoid, which is worth knowing on its
own.)

Run:  PYTHONPATH=. .venv/bin/python tools/thrust.py
"""

from __future__ import annotations

import numpy as np

from tools.calibrate_body import prescribed_wave
from worm.params import Params

FREQ = 0.67              # the model's own, measured over five seeds
TARGET_KAPPA = 4.51      # likewise, and within error of the animal's 4.3
WAVELENGTHS = (0.65, 0.73, 0.83, 0.95)
# Amplitude in uN*mm of prescribed joint moment. The first pass used 1 to 8 and was
# useless: even 1.0 bends the body to a curvature of 17 /mm against the 4.35 wanted,
# and past about 3 the animal coils, the speed goes non-monotonic and then negative.
# The physiological range for this body is an order of magnitude below that.
AMPLITUDES = (0.05, 0.10, 0.16, 0.22, 0.30, 0.45)


def main():
    p = Params()
    print("THRUST CEILING -- body alone, prescribed moment wave, no biology")
    print("  frequency %.2f Hz throughout; the model itself reaches 0.275 mm/s at"
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
        lam0 = min(best, key=lambda k: abs(k - 0.83))
        print()
        print("  at the model's own %.2f L the mechanics give %.4f mm/s for the same"
              % (lam0, best[lam0]))
        print("  curvature. The model gets 0.275, which is %.0f%% of it, against a"
              % (100 * 0.275 / best[lam0]))
        print("  travelling index of 0.85 -- the prediction being that those two match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
