"""Measure the per-segment gain of the proprioceptive reflex.

This is the measurement that matters for the model's one big open problem. The body wave
currently runs too long and too fast because it is mostly the passive mechanical response
to the head's bending, rather than a wave regenerated segment by segment. That claim is
testable: drive the head with a prescribed travelling moment, switch the body reflex off
and on, and compare how the bend amplitude decays along the body.

    gain(s) = amplitude_with_reflex(s) / amplitude_without_reflex(s)

A gain that grows with distance from the head means the reflex is regenerating the wave.
A gain that plateaus near 1 means it is not. Everything else -- wavelength, frequency,
speed, gait modulation -- follows from which of those is true.

Usage:
    PYTHONPATH=. python tools/reflex_gain.py                 # default sweep
    PYTHONPATH=. python tools/reflex_gain.py --quick         # one configuration
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from dataclasses import replace

import numpy as np

from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.params import MEDIA, Params

PROBE_POSITIONS = (0.25, 0.40, 0.55, 0.70, 0.85)


def response(p: Params, medium: str, drive_amp: float, drive_f: float,
             seconds: float, seed: int) -> tuple:
    """Amplitude of the body's response at the drive frequency, along the body."""
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.body.medium = MEDIA[medium]
    base = sim.muscles.joint_moment
    js = sim.muscles.joint_s
    head = (js < 0.20).astype(float)
    sim.muscles.joint_moment = (
        lambda: base() + drive_amp * head * np.sin(2 * np.pi * drive_f * sim.t))

    sim.run(5.0)
    kappa = []
    stride = 50
    for i in range(int(seconds / sim.dt)):
        sim.step()
        if i % stride == 0:
            kappa.append(sim.body.curvature().copy())
    kappa = np.array(kappa)
    fs = 1.0 / (sim.dt * stride)
    w = np.exp(-2j * np.pi * drive_f * np.arange(len(kappa)) / fs)
    comp = (kappa - kappa.mean(axis=0)).T @ w
    amp = np.abs(comp) / len(kappa)
    return amp, js


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--medium", default="agar")
    ap.add_argument("--seconds", type=float, default=14.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    base = Params()
    if args.quick:
        grid = [(base.sensory.proprio_gain, base.sensory.proprio_reach,
                 base.muscle.peak_moment)]
    else:
        grid = list(itertools.product(
            (45.0, 90.0, 180.0, 360.0),      # proprio_gain, pA
            (0.10, 0.20, 0.30),              # proprio_reach, body lengths
            (1.6, 3.2),                      # peak_moment, uN mm
        ))

    print("per-segment reflex gain = amplitude(reflex on) / amplitude(reflex off)")
    print("a gain rising with distance from the head means the reflex regenerates the wave\n")
    header = "%-9s %-7s %-7s " % ("gain", "reach", "moment")
    header += " ".join("%7s" % ("s=%.2f" % s) for s in PROBE_POSITIONS)
    print(header)

    rows = []
    for pg, reach, moment in grid:
        p = replace(
            base,
            sensory=replace(base.sensory, proprio_gain=pg, proprio_reach=reach,
                            head_proprio_gain=0.0),
            muscle=replace(base.muscle, peak_moment=moment),
        )
        off = replace(p, sensory=replace(p.sensory, proprio_gain=0.0))
        a_on, js = response(p, args.medium, 0.9, 0.5, args.seconds, seed=3)
        a_off, _ = response(off, args.medium, 0.9, 0.5, args.seconds, seed=3)

        def at(arr, s):
            return float(arr[np.argmin(np.abs(js - s))])

        gains = [at(a_on, s) / max(at(a_off, s), 1e-9) for s in PROBE_POSITIONS]
        print("%-9.0f %-7.2f %-7.1f " % (pg, reach, moment)
              + " ".join("%7.2f" % g for g in gains))
        rows.append({"proprio_gain": pg, "reach": reach, "peak_moment": moment,
                     "positions": list(PROBE_POSITIONS), "gain": gains,
                     "amp_on": [at(a_on, s) for s in PROBE_POSITIONS],
                     "amp_off": [at(a_off, s) for s in PROBE_POSITIONS]})

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(rows, fh, indent=2)
        print("\nwrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
