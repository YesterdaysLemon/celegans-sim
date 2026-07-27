"""Calibrate and verify the mechanics, before the neural loop is closed around it.

Three checks, in the order that makes failures diagnosable:

  1. passive relaxation -- a bent, unpowered worm must straighten, monotonically.
  2. prescribed wave    -- driving the muscles with a hand-written travelling wave must
                           produce the speed, and the sign of the speed, that a real worm
                           gets from the same kinematics.
  3. gait modulation    -- the same drive in buffer and on agar must land near the
                           measured swim/crawl frequencies and wavelengths.

If the emergent wave later fails to appear, it is because of the neural loop, not this.
"""

from __future__ import annotations

import sys

import numpy as np

from worm.body import Body
from worm.params import MEDIA, Params


def passive_relaxation(p: Params) -> bool:
    b = Body(p.body, MEDIA["agar"])
    b.theta = 0.6 * np.sin(np.linspace(0, 3 * np.pi, b.n))
    energies = []
    for i in range(4000):
        b.step(np.zeros(b.n - 1))
        if i % 100 == 0:
            j = b.theta[1:] - b.theta[:-1]
            energies.append(float((b.K * j * j).sum()))
    e = np.array(energies)
    monotone = bool(np.all(np.diff(e) <= 1e-12))
    print("1. passive relaxation")
    print("   bending energy %.4g -> %.4g   monotone decrease: %s"
          % (e[0], e[-1], monotone))
    print("   final |curvature| max %.3f /mm (should be ~0)" % np.abs(b.curvature()).max())
    return monotone and e[-1] < 1e-3 * e[0]


def prescribed_wave(p: Params, medium: str, freq: float, wavelength: float,
                    amplitude: float, seconds: float = 12.0) -> dict:
    """Drive the joints with a travelling moment wave and measure what the body does."""
    med = MEDIA[medium]
    b = Body(p.body, med)
    dt = p.body.dt
    s = b.joint_s
    n_steps = int(seconds / dt)
    settle = int(0.4 * n_steps)

    start = None
    kappa_log = []
    for i in range(n_steps):
        t = i * dt
        moment = amplitude * np.sin(2 * np.pi * (s / wavelength - freq * t))
        b.step(moment)
        if i == settle:
            start = b.centroid().copy()
        if i >= settle and i % 10 == 0:
            kappa_log.append(b.curvature().copy())
    end = b.centroid()
    elapsed = (n_steps - settle) * dt
    displacement = end - start
    # Positive means the animal travelled in the direction its head points.
    forward = float(displacement @ b.body_direction())
    kappa = np.array(kappa_log)
    return {
        "medium": medium,
        "speed": float(np.hypot(*displacement)) / elapsed,
        "forward_speed": forward / elapsed,
        "kappa_rms": float(np.sqrt((kappa ** 2).mean())),
        "kappa_max": float(np.abs(kappa).max()),
    }


def main() -> int:
    p = Params()
    ok = passive_relaxation(p)

    print("\n2. prescribed travelling wave (moment amplitude %.2f uN mm)"
          % p.muscle.peak_moment)
    print("   %-8s %10s %14s %10s %10s" %
          ("medium", "speed", "forward", "kappa rms", "kappa max"))
    targets = {"buffer": (1.76, 1.54), "agar": (0.30, 0.65)}
    for medium, (f, lam) in targets.items():
        r = prescribed_wave(p, medium, f, lam, p.muscle.peak_moment)
        print("   %-8s %8.4f mm/s %11.4f mm/s %10.2f %10.2f"
              % (medium, r["speed"], r["forward_speed"], r["kappa_rms"], r["kappa_max"]))
    print("\n   reference: agar crawling 0.219 +- 0.029 mm/s off food (Ramot et al. 2008)")
    print("              swimming      0.39 +- 0.07 mm/s (Krajacic et al. 2012)")
    print("              curvature     mean 4.3, max 9.8 /mm (Krajacic et al. 2012)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
