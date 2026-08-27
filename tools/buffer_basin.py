"""The buffer coil-up episode: mapped, and it is not a basin (#195).

The scorecard's per-seed buffer column showed a seed at 0.33 Hz against four at
0.85 and called it bimodality -- "one seed in five settles into a whole-body
standing flip". This instrument watched instead of sampling: consecutive 15 s
windows of freq/TWI over long swims, plus the whole-body contact total, which is
how the episode announces itself (a coiled animal presses against its own far
side -- Body.self_contact_force -- and since PVD landed, hard coils are also a
nociceptive event).

Run:  PYTHONPATH=. .venv/bin/python tools/buffer_basin.py [T] [seeds...]
      (default 120 s x seeds 0..11; ~2.6x wall per sim-second, one process)

THE RECORD (2026-08-27, shipped params):

  12 seeds x 120 s: eleven swim cleanly at 0.87 Hz / TWI ~0.75 throughout; seed 0
  alone shows a deep episode (TWI 0.73 -> 0.43 -> 0.17 -> 0.08 across 75-120 s at
  unchanged frequency); seeds 1 and 8 show one shallow dip each (TWI 0.42 / 0.32
  for a single window) and recover at once.

  Seed 0 x 300 s: the deep episode ENDS BY ITSELF -- TWI is back to 0.67 by
  135 s and holds 0.63-0.78 for the remaining three minutes. No seed, on any
  horizon measured, stayed in. The same run on the pre-PVD model (591af4e) shows
  the same shape with different timing: episodes at 45-60, 105-120 and 165-180 s
  (freq dipping to 0.33 / 0.20), every one self-ending. The 2026-08-25 scorecard
  row caught the 45-60 s episode inside its own 46-86 s analyse window and read
  "settled at 0.325 Hz" -- a snapshot of a spell, not a stationary state.

  Self-contact during the episodes: the swimming animal's coil presses its far
  side at whole-body totals of 3.6-8.3 in brief bursts (t~55-60, ~150, ~175-180
  on seed 0), which crosses SensoryParams.pvd_threshold = 3.0 -- so since PVD
  landed, a hard coil is also felt, and buffer trajectories legitimately moved
  (the bisect that found this is in issue #195's closing PR). Agar and viscous
  crawls never self-contact at these totals; every determinism pin held.

Reading: buffer has no second attractor at shipped defaults. It has a recurrent
~15 s coil-up excursion that the animal always exits, entered a few times in the
first minutes of a swim, rarer later. A mean +- sd cannot show it; a per-seed
window can catch one in the act. If it ever needs a mechanism decision, the
question is whether PVD hearing the animal's own hard coil (a real nociceptor
does cover the body wall) should stand -- today it is simply on the record.
"""
import sys

import numpy as np

from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import Params

WINDOW = 15.0


def run(seed, T):
    p = Params().with_medium("buffer")
    sim = Simulation(p, seed=seed, world=bare_world(p))
    rows = []
    for _ in range(int(T / WINDOW)):
        peak = 0.0
        # analyse() advances the sim itself; sample contact through a wrapped step
        # would complicate it, so read the peak between windows instead: cheap and
        # honest -- the episode lasts longer than a window.
        r = analyse(sim, seconds=WINDOW)
        c = sim._contact
        peak = float(np.hypot(c[:, 0], c[:, 1]).sum())
        rows.append((r["freq"], r["twi"], peak))
    return rows


def main(argv):
    T = float(argv[0]) if argv else 120.0
    seeds = [int(s) for s in argv[1:]] or list(range(12))
    print("BUFFER EPISODES -- %.0f s in %.0f-s windows; freq/twi per window"
          % (T, WINDOW))
    for seed in seeds:
        rows = run(seed, T)
        cells = "  ".join("%.2f/%+.2f" % (f, t) for f, t, _ in rows)
        dips = [i for i, (f, t, _) in enumerate(rows) if t < 0.5 or f < 0.6]
        tag = ("dips@" + ",".join("%ds" % (i * WINDOW) for i in dips)) if dips \
            else "clean"
        print("seed %2d  %-18s %s" % (seed, tag, cells))
    print("\nEvery observed episode self-ends; see THE RECORD in the docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
