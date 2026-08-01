"""Reference trajectories for the WebAssembly port to be checked against.

The two implementations read their setup out of the same file (tools/export_model.py), so
anything they disagree about is in the stepping. This dumps what the Python does, step by
step, with the noise switched off -- see the header of wasm/assembly/index.ts for why that
is the only honest way to compare them.

Run:  PYTHONPATH=. .venv/bin/python tools/conform.py > web/conform.json
      node wasm/conform.mjs
"""

from __future__ import annotations

import json
import sys

import numpy as np

from worm.body import Body
from worm.params import MEDIA, Params

STEPS = 2000          # one simulated second at the shipped step
SAMPLE = 100


def body_case():
    """The mechanics alone: a prescribed bending moment, no biology, no noise.

    This is the piece most likely to be got wrong in a port -- it assembles a 50x50 drag
    metric out of masked matrix products and then solves it -- and the piece where an
    error is least visible downstream, because a slightly wrong drag still produces a
    worm-shaped thing that wriggles.
    """
    p = Params()
    body = Body(p.body, MEDIA["agar"], position=(0.0, 0.0), heading=0.0)
    dt = p.neural.dt
    n_joint = p.body.n_links - 1
    # A fixed, asymmetric moment: exercises every joint and both signs, and is trivially
    # reproducible on the other side.
    moment = np.array([0.06 * np.sin(3.0 * j / n_joint) for j in range(n_joint)])

    out = {"dt": dt, "steps": STEPS, "sample": SAMPLE,
           "moment": moment.tolist(), "frames": []}
    for i in range(STEPS):
        body.step(moment, dt=dt)
        if (i + 1) % SAMPLE == 0:
            nodes = body.nodes()
            out["frames"].append({
                "step": i + 1,
                "x": [round(float(v), 12) for v in nodes[:, 0]],
                "y": [round(float(v), 12) for v in nodes[:, 1]],
                "kappa": [round(float(v), 12) for v in body.curvature()],
            })
    return out


def full_case(serotonin_mod1=0.0):
    """The whole loop -- neurons, muscle, senses, body -- with the noise switched off.

    Noise is the one thing that cannot match: it is numpy's PCG64 through a ziggurat
    sampler, and reproducing that bit-for-bit in the port would buy nothing, because the
    noise is meant to be noise. With it off both sides are deterministic and must agree to
    floating point.
    """
    import dataclasses
    from worm.engine import Simulation
    from worm.world import World

    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, noise_sigma=0.0))
    # MOD-1 ships at zero, and a term multiplied by zero is not being checked -- which is
    # exactly how the whole serotonin-gated chloride path reached the runtime unported and
    # stayed that way, passing every conformance run because absent and zero agree to every
    # decimal place. The second case below runs it at the coefficient params.py documents.
    if serotonin_mod1:
        p = dataclasses.replace(
            p, modulator=dataclasses.replace(p.modulator, serotonin_mod1=serotonin_mod1))
    # A plate with something on it. A bare world leaves most of the sensory layer reading
    # zero -- and a term that is only ever multiplied by zero is not being checked. The
    # lawn exercises the attractant, odour, food and oxygen paths and the drop exercises
    # the repellent one, including its adapting baseline.
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(-6.0, 4.0, 5.0, density=1.0, attractant=1.0, length_scale=9.0)
    w.add_repellent_source(7.0, -3.0, strength=0.9, length_scale=5.0)
    # Food under the animal from the first step, and this is the third time the same
    # lesson has had to be learned here. The plate above gives the animal gradients to
    # sense but nothing to *eat*: starting seven millimetres off the lawn it never pumps,
    # never ingests, never fills its uterus and never lays, so three of egg-laying's four
    # state variables were constant for the whole run and the comparison covered one. Same
    # shape as the empty dish that hid the missing field diffusion, and as the lawn-less
    # plate that hid the food skirt. A term that never moves is not being checked.
    w.add_food_patch(0.0, 0.0, 3.0, density=1.0, attractant=0.6, length_scale=6.0)
    sim = Simulation(p, seed=0, world=w, placement=(0.0, 0.0, 0.0))
    steps = 4000
    out = {"steps": steps, "sample": 200, "frames": []}
    for i in range(steps):
        sim.step()
        if (i + 1) % 200 == 0:
            nodes = sim.body.nodes()
            out["frames"].append({
                "step": i + 1,
                "x": [round(float(v), 12) for v in nodes[:, 0]],
                "y": [round(float(v), 12) for v in nodes[:, 1]],
                "V": [round(float(v), 10) for v in sim.nervous.V],
                "tension": [round(float(v), 12) for v in sim.muscles.tension],
                "gate": 1.0 if sim.senses.going_forward else 0.0,
                # Egg-laying carries four pieces of state and three of them are slow, so a
                # port that got the vulval muscle right and the resource wrong would look
                # correct for minutes. All four are compared.
                # Feeding. `lumen` is what the pharynx holds, `ingested` what reached
                # the intestine, `eaten` what the plate lost -- three quantities that are
                # equal only when the animal is standing still on food, which is exactly
                # the case that hid a conservation bug for the whole of this model's life.
                # Comparing all three pins capture, transport and the world debit
                # separately rather than letting one stand in for the others.
                "ph": [round(float(sim.pharynx.lumen), 12),
                       round(float(sim.pharynx.ingested), 12),
                       round(float(sim.food_eaten), 12)],
                "egl": [round(float(sim.egglaying.vm), 10),
                        round(float(sim.egglaying.eggs), 10),
                        round(float(sim.egglaying.resource), 10),
                        float(sim.egglaying.laid)],
            })
    return out


def ablated_case():
    """The same loop again, with cells removed.

    Ablation is the largest piece of either implementation that no check has ever looked
    at. It has its own branch almost everywhere -- the gap-junction accumulation skips dead
    neighbours, `gap_total` is rebuilt, synaptic release is zeroed, the dead cell's voltage
    is pinned at its leak potential after the solve, and `activation` reports zero so that a
    cell which is not present does not vote in the direction gate. Eleven separate `anyDead`
    branches in the runtime, plus `rebuildGap`, none of them exercised.

    It is also the piece where being wrong is quietest. An ablation that is only *mostly*
    applied still produces a worm-shaped thing that wriggles; it just answers a different
    question than the one the experiment asked. The comment on
    `NervousSystem.set_ablated` records what that already cost once: ablating AVB without
    also cutting its external drive drove it to +34.8 mV and made silencing the forward
    command look like maximally activating it.

    The set is chosen to hit every branch rather than to mean anything biologically: two
    command interneurons, so the direction gate loses inputs; two motor neurons, so a
    muscle loses drive; two cells with heavy gap coupling, so `rebuildGap` has something to
    do; and one pharyngeal cell, which is coupled to the rest of the animal by a single
    gap junction and nothing else.
    """
    import dataclasses
    from worm.engine import Simulation
    from worm.world import World

    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, noise_sigma=0.0))
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(-6.0, 4.0, 5.0, density=1.0, attractant=1.0, length_scale=9.0)
    w.add_repellent_source(7.0, -3.0, strength=0.9, length_scale=5.0)
    sim = Simulation(p, seed=0, world=w, placement=(0.0, 0.0, 0.0))

    names = ["AVBL", "AVAL", "DB03", "VB05", "AVEL", "RIML", "I2L"]
    idx = [sim.conn.index[n] for n in names]
    # Ablate MID-RUN, not at t=0, and that distinction is the whole point of this case.
    # Ablating before the first step silences cells whose state is still at its initial
    # value, so every line that exists to *clear* live state -- the release variable, the
    # voltage, the adaptation -- is a no-op and cannot be got wrong. Deleting those lines
    # one at a time changed nothing and no check noticed, which is exactly what the viewer
    # does not do: its Ablate button kills a cell in an animal that has been swimming for
    # minutes, with a live release variable and a live voltage to clear.
    warm = 800
    for _ in range(warm):
        sim.step()
    sim.set_ablated(names)

    steps = 3000
    out = {"steps": steps, "sample": 200, "ablated": idx, "names": names,
           "warm": warm, "frames": []}
    for i in range(steps):
        # Captured *before* the step, not after. Both implementations compute the
        # activation at the top of a step, from the voltage the previous step left behind,
        # so that the wireless layer runs one step behind the wired one. The port's stored
        # `act` after N steps is therefore f(V after N-1 steps). Sampling it after
        # `sim.step()` here instead compares f(V_N) against f(V_{N-1}) and reports a 3e-3
        # disagreement that is entirely this harness's -- which is what it did first time.
        act = sim.nervous.activation()
        sim.step()
        if (i + 1) % 200 == 0:
            nodes = sim.body.nodes()
            out["frames"].append({
                "step": i + 1,
                "x": [round(float(v), 12) for v in nodes[:, 0]],
                "y": [round(float(v), 12) for v in nodes[:, 1]],
                "V": [round(float(v), 10) for v in sim.nervous.V],
                "act": [round(float(v), 10) for v in act],
                "tension": [round(float(v), 12) for v in sim.muscles.tension],
                "gate": 1.0 if sim.senses.going_forward else 0.0,
            })
    return out


def main():
    json.dump({"body": body_case(), "full": full_case(), "ablated": ablated_case(),
               # 0.30 is the coefficient ModulatorParams.serotonin_mod1 documents as
               # adopted-then-shipped-at-zero. Running the reference there is the only way
               # this path gets compared at all.
               "mod1": full_case(serotonin_mod1=0.30)},
              sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
