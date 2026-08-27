"""Turn depth, measured at the animal's own reversals (#196).

Three measured-correct mechanisms (ASE opponency, BAG border turning, tail
nociception) all pressed against the same ceiling: the turn the circuit asks
for is shallower than the animal's. This instrument finds where the depth goes.

Every commanded reversal (the direction gate's own state, not a mechanical
track detector) is logged with its duration, the omega amplitude it earned
(min(1, duration / omega_ref_reversal)), and the reorientation achieved --
heading of the new run (2.5-3.5 s after the reversal ends, when the transient
has spent itself) against the old (measured over the second before it began).
Off-food bare world, 6 seeds x 180 s per arm.

Run:  PYTHONPATH=. .venv/bin/python tools/turn_depth.py [pA:tau ...]
      (default: the shipped 300:1.5; e.g. `turn_depth.py 300:1.5 300:2.5`)

THE RECORD (2026-08-27, shipped model unless noted):

  arm            n    median deg   mean    >120
  300 pA  1.5 s  59       82.1     77.6    13.6%   <- shipped
  600 pA  1.5 s  75       60.2     67.3    10.7%
  300 pA  2.0 s  69       65.0     73.9    20.3%
  300 pA  2.5 s  66       91.1     87.7    34.8%   <- the animal's ~35%
  300 pA  3.0 s  57      133.2    115.0    56.1%
  600 pA  3.0 s  44      144.6    145.9    93.2%

  And the diagnosis that ordered the sweep: reversal durations are healthy
  (median 0.36 s against omega_ref_reversal = 0.4; amplitude fraction earned
  0.84 mean, 36% at full), and corr(amplitude, reorientation) = 0.04 -- the
  amplitude delivered does not predict the turn achieved. More current makes
  turns SHALLOWER (600 pA rows; saturating one side of the head pool disrupts
  the oscillation, exactly as the omega dossier's held-drive table warned).
  More TIME makes them deeper: at tau 1.5 s the ventral bias decays within one
  undulation period (0.67 Hz) and the wave overwrites it before it has carried
  down the body. The ceiling every taxis magnitude was pressing against is the
  bias LIFETIME, not the drive.

  The dossier's own fit (2026-08-2x) read 106 deg / 32% at (300, 1.5); the
  shipped animal today reads 82 / 13.6 by this instrument -- the mechanisms
  that landed since the fit shortened what a turn completes to, and the fitted
  triple silently slid off its own target. Retuning tau toward the animal's
  ~35% is maintenance of the original fit, not a new mechanism.

  Estimator lesson, paid for twice: a post-event window flush against the
  reversal reads the turn's INTERIOR (a still-rotating heading) and underreads
  it -- at tau 2.5 it inverted the sign of a paired comparison. The ethogram's
  _reorientation now skips 5 s past the event for the same reason; this
  instrument reads 2.5-3.5 s because commanded-edge events do not fragment the
  way mechanical detections do. Trajectory guards (net/path, drift, speed) are
  the ethogram's job and stay there -- at tau 2.5 all three were clean, drift
  numerically improving (2.87 -> 0.87 deg/s).
"""
import sys

import numpy as np

from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.errors import DivergentSimulation
from worm.params import Params

T = 180.0
SEEDS = range(6)


def _heading(track, i0, i1):
    a = track[min(len(track) - 1, max(0, i0))]
    b = track[min(len(track) - 1, max(0, i1))]
    d = b - a
    if np.hypot(d[0], d[1]) < 1e-9:
        return None
    return float(np.arctan2(d[1], d[0]))


def probe(seed, current, tau):
    import dataclasses
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, omega_current=float(current), omega_tau=float(tau)))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    sim.run(6.0)
    s = sim.senses
    n = len(sim.body.nodes())
    track, events = [], []
    per = int(round(0.1 / sim.dt))
    rev_start = None
    prev = 0
    for k in range(int(T / sim.dt)):
        try:
            sim.step()
        except DivergentSimulation:
            break                        # pre-#211 rims dropped roamers; now unreachable
        steps = s._rev_steps
        if steps > 0 and prev == 0:
            rev_start = len(track)
        if steps == 0 and prev > 0 and rev_start is not None:
            events.append((rev_start, len(track), prev * sim.dt,
                           min(1.0, prev / s._omega_ref_n)))
            rev_start = None
        prev = steps
        if k % per == 0:
            track.append(sim.body.nodes()[n // 2].copy())
    out = []
    for start, end, dur, amp in events:
        if end + 35 >= len(track):
            continue
        h0 = _heading(track, start - 12, start - 2)
        h1 = _heading(track, end + 25, end + 35)
        if h0 is None or h1 is None:
            continue
        reo = abs((h1 - h0 + np.pi) % (2 * np.pi) - np.pi) * 180.0 / np.pi
        out.append((dur, amp, reo))
    return out


def main(argv):
    arms = [(float(a.split(":")[0]), float(a.split(":")[1])) for a in argv] \
        or [(300.0, 1.5)]
    print("TURN DEPTH -- %d seeds x %.0f s off food per arm\n" % (len(SEEDS), T))
    print("  %-14s %4s %10s %7s %7s" % ("arm", "n", "median", "mean", ">120"))
    for current, tau in arms:
        ev = []
        for seed in SEEDS:
            ev.extend(probe(seed, current, tau))
        durs = np.array([e[0] for e in ev])
        amps = np.array([e[1] for e in ev])
        reos = np.array([e[2] for e in ev])
        print("  %4.0f pA %4.1f s %4d %9.1f %7.1f %6.1f%%"
              % (current, tau, len(ev), np.median(reos), reos.mean(),
                 100 * np.mean(reos > 120)))
        print("      reversal dur median %.2f s; amp earned %.2f mean; "
              "corr(amp, reo) %+.2f"
              % (np.median(durs), amps.mean(),
                 np.corrcoef(amps, reos)[0, 1] if len(ev) > 4 else float("nan")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
