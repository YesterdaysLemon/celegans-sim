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


def full_case():
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
    sim = Simulation(p, seed=0, world=World(p.world, np.random.default_rng(0)),
                     placement=(0.0, 0.0, 0.0))
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
            })
    return out


def main():
    json.dump({"body": body_case(), "full": full_case()}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
