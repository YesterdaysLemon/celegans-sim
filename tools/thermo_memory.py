"""Thermotaxis memory: does the learned setpoint steer the animal? (#198)

Two questions, two parts.

LEARNING -- the rule itself, watched: an animal feeding on the dense lawn (which
sits at ~21 C on the default plate's 17->25 gradient) should walk its setpoint
from the declared 20 C toward the temperature it actually experiences, at the
dopamine-gated rate, and freeze it off food.

MIGRATION -- the gain decision: on the gradient plate with no food, an animal
whose setpoint is preset to T* (the cultivation endpoint -- the learning rule's
convergence makes the preset equivalent to having been cultivated there) should
migrate toward T*'s isotherm when thermo_setpoint_gain is nonzero, and the two
presets must SEPARATE: cultivated-cold animals end colder than cultivated-warm
ones on the same plate from the same starts. That separation is the memory's
behavioural signature and no fixed mechanism can fake it.

Run:  PYTHONPATH=. .venv/bin/python tools/thermo_memory.py [gains...]
      (default gains 0 2 5; 2 presets x 6 seeds x 200 s per gain)
      PYTHONPATH=. .venv/bin/python tools/thermo_memory.py transfer
      (the primitive: constant current held into AFD, 6 levels x 8 seeds)

THE RECORD (2026-08-27, all on the shipped model):

  LEARNING works exactly as built: on the dense lawn the setpoint walked
  20.000 -> 19.729 C in 180 s (with the fed threshold in place), tracking the
  temperature the animal actually experienced (19.4-19.75 C where it roamed),
  rate gated by dopamine 0.27-0.44. And the off-state test EARNED ITS KEEP the
  day it was written: the first cut learned on any positive dopamine, and a
  fasting animal on bare agar -- where the mechanosensory dopamine level idles
  at 0.029 mean / 0.045 max, never zero -- quietly wrote its own memory
  (drifted to 19.973 in a minute). "Fed" is now a threshold (0.08, above the
  off-food ceiling with margin, below the sparsest lawn's 0.10), and below it
  the setpoint is frozen to the bit. Every pin held.

  MIGRATION refused every tonic routing. Signed (T - setpoint) into AFD, gain
  +5: the histories separate -1.18 C -- robustly, and AWAY from home (drive AFD
  and this connectome runs warm-ward; its own baseline does the same, cold
  starts moving warmer while AFD fires on warming transients). Gains -2/-5:
  +0.33/-0.34 C, noise. Rectified cold-side, gains 2/5/10: -0.22/-0.63/+0.14 C,
  noise (and the cold-cultivated arm is bit-identical to control by
  construction -- the term never fires above the preset).

  THE PRIMITIVE closed the route: a constant current held into AFD for 200 s
  on the gradient leaves end temperature FLAT --

      -20 pA: 20.51 +- 1.72    +10 pA: 20.40 +- 1.75
      -10 pA: 21.11 +- 1.67    +20 pA: 20.53 +- 1.46
       +0 pA: 20.89 +- 1.67    +40 pA: 20.81 +- 1.14   (n=8 each)

  AFD steers through its TRANSIENT -- the adapting differential, phase-locked
  with the animal's own movement -- and a standing offset carries no phase
  information for a klinotaxis to use. Which is the biology's own answer: the
  setpoint conditions the response to dT (warming is good below home, bad
  above), it is not a second current. That redesign -- a setpoint-conditional
  differential -- is the recorded follow-up and wants its own paired gate.
  Until it wins one, thermo_setpoint_gain ships at 0.0 and the memory itself
  ships live: learning, costing nothing, waiting for a route that works.
"""
import dataclasses
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from worm.engine import Simulation
from worm.errors import DivergentSimulation
from worm.params import Params
from worm.world import World

T_RUN = 200.0
SEEDS = range(6)
PRESETS = (18.5, 23.0)     # the two cultivation histories; isotherms at x -23.1, +11.3


def learning_demo():
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(p, seed=0, world=w)
    print("LEARNING -- dense lawn (plate ~21 C at centre), setpoint every 30 s:")
    for k in range(6):
        sim.run(30.0)
        s = sim.senses
        print("  t=%3.0f s  setpoint %.3f C  (T here %.2f, dopamine %.2f)"
              % (sim.t, s.t_setpoint,
                 float(sim.world.temperature(*sim.body.nodes()[0])),
                 float(sim.modulators.level["dopamine"])))


def _job(job):
    seed, preset, gain = job
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, thermo_setpoint_gain=float(gain)))
    w = World(p.world, np.random.default_rng(0))          # bare gradient plate
    ang = (seed % 8) * (2 * np.pi / 8)
    sim = Simulation(p, seed=seed, world=w, placement=(-6.0, 0.0, float(ang)))
    sim.senses.t_setpoint = float(preset)                 # the cultivation endpoint
    n = len(sim.body.nodes())
    try:
        sim.run(T_RUN)
    except DivergentSimulation:
        return None
    mid = sim.body.nodes()[n // 2]
    return dict(seed=seed, preset=preset, gain=gain, x_end=float(mid[0]),
                t_end=float(sim.world.temperature(mid[0], mid[1])))


def _transfer_job(job):
    seed, pA = job
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    ang = (seed % 8) * (2 * np.pi / 8)
    sim = Simulation(p, seed=seed, world=w, placement=(-6.0, 0.0, float(ang)))
    s = sim.senses
    afd, base = s.afd, s.sense

    def wrapped(world, nodes, *a, **k):
        I = base(world, nodes, *a, **k)
        I[afd] += pA
        return I

    s.sense = wrapped
    n = len(sim.body.nodes())
    try:
        sim.run(T_RUN)
    except DivergentSimulation:
        return None
    mid = sim.body.nodes()[n // 2]
    return (pA, float(sim.world.temperature(mid[0], mid[1])))


def transfer():
    levels = (-20.0, -10.0, 0.0, 10.0, 20.0, 40.0)
    jobs = [(s, pA) for pA in levels for s in range(8)]
    with ProcessPoolExecutor(max_workers=2) as ex:
        rows = [r for r in ex.map(_transfer_job, jobs) if r is not None]
    print("AFD TRANSFER -- constant current held into AFD, end T (start 20 C):")
    for pA in levels:
        t = [r[1] for r in rows if r[0] == pA]
        print("  %+5.0f pA  end T %.2f +- %.2f  (n=%d)"
              % (pA, np.mean(t), np.std(t), len(t)))
    print("\n  Flat means a tonic cannot steer; see THE RECORD in the docstring.")
    return 0


def main(argv):
    if argv and argv[0] == "transfer":
        return transfer()
    gains = [float(g) for g in argv] or [0.0, 2.0, 5.0]
    learning_demo()
    jobs = [(s, pre, g) for g in gains for pre in PRESETS for s in SEEDS]
    with ProcessPoolExecutor(max_workers=4) as ex:
        rows = [r for r in ex.map(_job, jobs) if r is not None]
    print("\nMIGRATION -- start x = -6 mm (20 C), 200 s, end temperature by history:")
    print("  %-6s %14s %14s %12s" % ("gain", "@%.1f C" % PRESETS[0],
                                     "@%.1f C" % PRESETS[1], "separation"))
    for g in gains:
        ends = {}
        for pre in PRESETS:
            got = [r["t_end"] for r in rows if r["gain"] == g and r["preset"] == pre]
            ends[pre] = (np.mean(got), np.std(got), len(got))
        sep = ends[PRESETS[1]][0] - ends[PRESETS[0]][0]
        print("  %-6.1f %8.2f +- %.2f %8.2f +- %.2f %+9.2f C"
              % (g, ends[PRESETS[0]][0], ends[PRESETS[0]][1],
                 ends[PRESETS[1]][0], ends[PRESETS[1]][1], sep))
    print("\n  gain 0 is the control: identical presets-blind animals, separation ~0.")
    print("  A working memory separates the histories on the same plate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
