"""Sleep's behavioural surface: bout statistics on an undisturbed lawn (#197).

The circuit shipped with its own gates (worm/sleep.py; drive, peptide, arousal,
ablation) and now a depth curve, but nobody had watched the animal simply LIVE
with the homeostat: how often it sleeps, for how long, and how regularly, when
nothing pokes it. That surface is what You et al. 2008 measured for satiety
quiescence -- quiescent bouts appearing after feeding, lengthening with
satiety -- and it is the part of the model a visitor to the dish actually sees.

The clock context matters and is printed with the numbers: this dish runs a
compressed ecology (SleepParams' docstring), so the claim under test is the
STRUCTURE -- discrete bouts with a refractory-free rhythm set by build rate
against discharge rate, bout length set by tau_sleep and the Schmitt gap,
sleep starting only once feeding has built pressure -- not the absolute
minutes of You's adults.

For each seed: T seconds on the default plate (dense central lawn), nothing
touched. Recorded per bout: start, duration, the pressure at entry and exit,
peak FLP-11, mean depth. Between bouts: the interval. Plus totals -- fraction
of time asleep after first sleep onset, pump rate asleep vs awake, mid-body
speed asleep vs awake -- the quiescence phenotype's two effectors, measured on
the same run.

Run:  PYTHONPATH=. .venv/bin/python tools/sleep_surface.py [T] [default|dense] [seeds...]
      (default 600 s, both plates, seeds 0 1 2; ~2.6x wall per sim-second each)

Two plates on purpose. The DEFAULT plate is the ecology: sparse lawns the animal
roams between, so pressure builds only while it happens to feed and sleep is
rare and event-like (an 8-minute first onset was measured before this line was
written). The DENSE plate is the pharynx fixture's wall-to-wall lawn: dopamine
runs ~0.44, the homeostat cycles in minutes, and bout STATISTICS accumulate --
the metronome question (is the rhythm too regular?) can only be asked there.

THE RECORD (2026-08-27, 600 s x seeds 0/1/2 per plate, shipped params):

  dense   seed 0: onset 121 s, 6 bouts, 46.5 +- 0.5 s, interval 32.8 +- 0.4 s
          seed 1: onset  98 s, 3 bouts, 46.0 +- 0.0 s, interval 43.5 +- 10.5 s
          seed 2: onset  85 s, 4 bouts, 39.8 +- 11.4 s, interval 114 +- 114 s
          pump 1.3-2.6 Hz awake / 0.4-0.5 asleep; speed 0.27-0.33 / 0.11-0.14 mm/s
  default seed 0: onset 483 s, one 46 s bout      seed 2: onset 448 s, one 46 s bout
          seed 1: LEFT THE DISH at 118 s (the rim's 0.05 mm repulsion zone lost a
          head-on roamer -- filed as its own issue; a plate finding, not sleep's)

Reading: bout DURATION belongs to the circuit -- 46 s is tau_sleep * ln(0.69/0.25)
almost exactly, deterministic, the discharge is the bout -- while bout TIMING belongs
to the ecology: even on the wall-to-wall lawn the intervals run from metronomic
(seed 0, parked on food) to 114 +- 114 s (seed 2, wandering off the lawn edge and
stalling its own pressure build). The variance is the animal's foraging, not an
injected noise term, which is the lifelike way to get it. On the default plate sleep
is a rare late event (~7-8 min to first onset) because dopamine only builds while the
roamer happens to feed. Both quiescence effectors show on every bout: pump 1.3-2.6 Hz
awake against ~0.4 asleep, speed roughly a third (residual "asleep" motion is
bout-edge transitions inside the 1 s bins). Depth (#204) rides each bout, peak FLP-11
0.86-0.89. What the model still lacks against You 2008: bout durations barely vary --
the discharge constant fixes them -- where real quiescence bouts spread; if that gap
ever matters, the variance should come from the ecology reaching tau_sleep (satiety
level scaling discharge), not from a noise dial.
"""
import sys

import numpy as np

from worm.engine import Simulation
from worm.errors import DivergentSimulation
from worm.params import Params
from worm.world import World


def run(seed, T, plate):
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    if plate == "dense":
        # The pharynx fixture's wall-to-wall lawn: dopamine high enough that the
        # homeostat cycles inside minutes -- where bout STATISTICS accumulate. The
        # default plate is the ecology; this is the incubator.
        w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(p, seed=seed, world=w)
    n = len(sim.body.nodes())
    bouts = []          # dicts: start, end, p_in, p_out, flp_peak, depth_sum, depth_n
    cur = None
    awake_speed = []
    asleep_speed = []
    awake_pump = []
    asleep_pump = []
    last_mid = sim.body.nodes()[n // 2].copy()
    step_per = int(round(1.0 / sim.dt))
    left_at = None
    for k in range(int(T)):
        was = sim.sleep.bout
        try:
            for _ in range(step_per):
                sim.step()
                if sim.sleep.bout and cur is not None:
                    cur["flp_peak"] = max(cur["flp_peak"], sim.sleep.flp11)
                    cur["depth_sum"] += sim.sleep.depth()
                    cur["depth_n"] += 1
        except DivergentSimulation:
            # A long undisturbed roam can genuinely reach the dish rim; that is a
            # finding about the plate, not a crash of the instrument.
            left_at = float(k)
            break
        mid = sim.body.nodes()[n // 2]
        v = float(np.hypot(*(mid - last_mid)))
        last_mid = mid.copy()
        (asleep_speed if sim.sleep.bout else awake_speed).append(v)
        (asleep_pump if sim.sleep.bout else awake_pump).append(sim.pharynx.rate)
        if sim.sleep.bout and not was and cur is None:
            cur = dict(start=k + 1.0, p_in=sim.sleep.pressure, flp_peak=0.0,
                       depth_sum=0.0, depth_n=0)
        elif not sim.sleep.bout and was and cur is not None:
            cur["end"] = k + 1.0
            cur["p_out"] = sim.sleep.pressure
            bouts.append(cur)
            cur = None
    return bouts, awake_speed, asleep_speed, awake_pump, asleep_pump, left_at


def main(argv):
    T = float(argv[0]) if argv else 600.0
    rest = argv[1:]
    plates = [p for p in rest if p in ("default", "dense")] or ["default", "dense"]
    seeds = [int(s) for s in rest if s not in ("default", "dense")] or [0, 1, 2]
    for plate in plates:
        print("SLEEP SURFACE -- %.0f s undisturbed, %s plate\n" % (T, plate))
        for seed in seeds:
            bouts, aw_v, sl_v, aw_p, sl_p, left_at = run(seed, T, plate)
            span = left_at if left_at is not None else T
            note = "" if left_at is None else "  (left the dish at %.0f s)" % left_at
            if not bouts:
                print("seed %d: never slept in %.0f s%s" % (seed, span, note))
                continue
            durs = np.array([b["end"] - b["start"] for b in bouts])
            starts = np.array([b["start"] for b in bouts])
            gaps = np.diff(starts) - durs[:-1]
            post = span - starts[0]
            frac = durs.sum() / post if post > 0 else 0.0
            print("seed %d: onset %.0f s, %d bouts, duration %.1f +- %.1f s, "
                  "interval %.1f +- %.1f s, asleep %.0f%% of post-onset time%s"
                  % (seed, starts[0], len(bouts), durs.mean(), durs.std(),
                     gaps.mean() if len(gaps) else float("nan"),
                     gaps.std() if len(gaps) else float("nan"), 100 * frac, note))
            print("        pressure in/out %.2f -> %.2f, FLP-11 peak %.2f, "
                  "mean depth %.2f"
                  % (np.mean([b["p_in"] for b in bouts]),
                     np.mean([b["p_out"] for b in bouts]),
                     np.mean([b["flp_peak"] for b in bouts]),
                     np.mean([b["depth_sum"] / max(b["depth_n"], 1) for b in bouts])))
            print("        pump %.1f Hz awake / %.1f Hz asleep, speed %.3f / %.3f mm/s"
                  % (np.mean(aw_p), np.mean(sl_p) if sl_p else float("nan"),
                     np.mean(aw_v), np.mean(sl_v) if sl_v else float("nan")))
        print("")
    print("Structure, not minutes: the compressed clock is the dish's"
          " (SleepParams docstring); You 2008 is the shape reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
