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


def folded_case():
    """The body driven into itself, because nothing else here reaches the self-contact force.

    `body_case` and every other case run an animal that never touches itself -- measured,
    in `tools/self_contact.py`: no overlap at any scale, across seeds and both food
    conditions. So they exercise exactly zero lines of `Body.self_contact_force`, and a
    port of it could be arbitrarily wrong while the whole suite stayed green. That is the
    egg-laying conformance bug from #26 in a new place: a check that compares nothing and
    reports a perfect score.

    A uniform 1.0 uN mm coils the body until its far side meets itself -- contact fires on
    1941 of 2000 steps and 36 node pairs are touching at the end -- which is a state the
    animal never reaches on its own and the runtime must nonetheless reproduce. Below about
    0.6 nothing touches at all and this case would silently go back to covering nothing, so
    `contact_steps` is recorded and the comparison fails if it is zero.

    Contact is computed from the current nodes and then handed to `step`, matching
    `stepBodyOnly`'s `contact(); stepBody(dt)` ordering on the other side. The wall force
    is identically zero here -- the animal is at the origin of a 45 mm dish -- so the two
    sides are comparing self-contact alone.
    """
    p = Params()
    body = Body(p.body, MEDIA["agar"], position=(0.0, 0.0), heading=0.0)
    dt = p.neural.dt
    moment = np.full(p.body.n_links - 1, 1.0)

    out = {"dt": dt, "steps": STEPS, "sample": SAMPLE,
           "moment": moment.tolist(), "frames": [], "contact_steps": 0}
    for i in range(STEPS):
        forces = body.self_contact_force(body.nodes())
        if np.abs(forces).max() > 0.0:
            out["contact_steps"] += 1
        body.step(moment, dt=dt, node_forces=forces)
        if (i + 1) % SAMPLE == 0:
            nodes = body.nodes()
            out["frames"].append({
                "step": i + 1,
                "x": [round(float(v), 12) for v in nodes[:, 0]],
                "y": [round(float(v), 12) for v in nodes[:, 1]],
                "kappa": [round(float(v), 12) for v in body.curvature()],
            })
    return out


def full_case(serotonin_mod1=0.0, head_stages=0, head_delay=None, head_stage_tau=0.0,
              amine=False, sleep=False):
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
    # The head cascade, same argument as MOD-1 above: at the shipped stages = 1 the chain
    # code in the runtime is a branch never taken, and a branch never taken is not being
    # checked. The cascade case runs the configuration head_cascade.py measured
    # (4 x 0.125 s, no transport delay) so every stage of the chain moves.
    if head_stages:
        p = dataclasses.replace(p, sensory=dataclasses.replace(
            p.sensory, head_stages=head_stages, head_stage_tau=head_stage_tau,
            **({"head_delay": head_delay} if head_delay is not None else {})))
    # The amine load-sensing path at its third-calibration configuration
    # (tools/amine_gait.py) -- which runs on the cascade, so this case exercises both,
    # end to end: drag-force transduction, dopamine integration, the lag, reach and
    # muscle-rate effects, and the swim fields the payload carries as wbs/was.
    if amine:
        p = dataclasses.replace(
            p,
            sensory=dataclasses.replace(
                p.sensory, head_stages=4, head_delay=0.0, head_stage_tau=0.125,
                load_gain=60.0, load_half=1.0, proprio_reach_swim=0.48),
            modulator=dataclasses.replace(
                p.modulator, dopamine_head_lag=1.30, dopamine_reach_swim=2.0,
                dopamine_muscle_rate=0.5))
    # Sleep, on a compressed clock so one 2 s window holds the whole life of a bout:
    # entry (pressure seeded above threshold), FLP-11 release and the three gain gates,
    # an arousal (the poke window below), the refractory, re-entry, discharge and exit.
    # At the shipped clock none of those branches fire inside any conformance window,
    # and a branch never taken is not being checked -- the MOD-1 lesson a third time.
    if sleep:
        p = dataclasses.replace(p, sleep=dataclasses.replace(
            p.sleep, tau_sleep=0.35, threshold_on=0.4, threshold_off=0.3,
            build_fed=3.0, flp11_tau=0.15, arousal_refractory=0.4))
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
    if sleep:
        # Pressure seeded above threshold so the bout fires at once, and the exact
        # Python-computed per-step rates handed over so the runtime is configured with
        # the same floats -- the cascade's contract. The poke window is the arousal.
        sim.sleep.pressure = 0.95
        out["sleep_cfg"] = {
            "pressure0": 0.95,
            "flp_rate": float(sim.sleep._flp_rate),
            "sleep_decay": float(sim.sleep._sleep_decay),
            "build_fed": float(p.sleep.build_fed),
            "build_base": float(p.sleep.build_base),
            "threshold_on": float(p.sleep.threshold_on),
            "threshold_off": float(p.sleep.threshold_off),
            "arousal_refractory": float(p.sleep.arousal_refractory),
            "poke_from": 600, "poke_to": 700, "poke_strength": 8.0,
        }
    if sim.senses._head_stages > 1:
        # The exact constants the Python side computed, so the runtime is configured with
        # the same floats rather than recomputing them and eating a rounding difference.
        out["cascade"] = {"head_stages": int(sim.senses._head_stages),
                          "head_stage_decay": float(sim.senses._head_stage_decay),
                          "head_stage_tau": float(sim.senses._head_stage_tau),
                          "head_delay_n": int(sim.senses._head_delay_n)}
    if amine:
        s, mo = sim.p.sensory, sim.p.modulator
        out["amine"] = {"load_gain": s.load_gain, "load_half": s.load_half,
                        "head_lag": mo.dopamine_head_lag,
                        "reach_blend": mo.dopamine_reach_swim,
                        "muscle_rate": mo.dopamine_muscle_rate}
    for i in range(steps):
        if sleep and 600 <= i < 700:
            sim.poke("anterior", strength=8.0)
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
                # The homeostat, the peptide, and the bout flag -- only for the sleep
                # case, so every other case's frames stay byte-for-byte what they were.
                **({"sleep": [round(float(sim.sleep.pressure), 12),
                              round(float(sim.sleep.flp11), 12),
                              1.0 if sim.sleep.bout else 0.0]} if sleep else {}),
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


# The contested plate, stated once and emitted into the reference so that wasm/conform.mjs
# can assert it is running the same experiment rather than merely believing it is.
#
# One small lawn, four animals on top of it. The radius is 1.5 mm and the animals start
# within half a millimetre of the middle, which is what makes the case a *contest*: the
# world grid is 256 cells across a 90 mm dish, so a cell is 0.352 mm and the 3x3
# neighbourhood an animal feeds from is about 1.05 mm wide. Animals half a millimetre
# apart are therefore drawing from cells the others are also drawing from. Measured over
# the run below, every one of the 16 capture events happened while at least one other
# animal's feeding neighbourhood overlapped the feeder's.
#
# The placement is deliberately NOT a rotation of one animal: the first version of this
# case put four animals on a ring at equal angles with headings 2*pi*k/4, which is
# symmetric, and over this run the four then ate 0.016039393, 0.016039394, 0.016039396 and
# 0.016039394 -- a spread of 2.9e-09 on quantities of 1.6e-02, four copies of the same
# number. Such a case passes against a runtime that hands every animal the population
# average. The offsets and headings here are uneven, and the four eat 0.016047229,
# 0.016042801, 0.016033364 and 0.016036963: a spread of 1.4e-05, which is four orders of
# magnitude wider than the ring and 1400x the tolerance those quantities are compared to.
MULTI_LAWN = (0.0, 0.0, 1.5, 1.0, 1.0, 4.0)   # x, y, radius, density, attractant, scale
MULTI_PLACEMENT = ((0.05, 0.05, 0.0),
                   (0.12, 0.10, 1.3),
                   (-0.20, 0.15, 2.9),
                   (0.10, -0.25, 4.4))
# 8000 steps is 4.0 s. See multi_case: the first pump lands at step 2881 and the fourth at
# 7207, so a shorter run would be comparing four animals that had never eaten.
MULTI_STEPS = 8000
MULTI_SAMPLE = 400


def _feeding_cell(world, x, y):
    """The cell whose 3x3 neighbourhood an animal at (x, y) feeds from.

    Same arithmetic as World._feeding_bounds and as the runtime's settleFeeding, and it is
    emitted per frame so that a disagreement about *which* cells were contested fails as
    itself rather than as an inexplicable difference in what was eaten.
    """
    return (int(np.clip((y + world.extent) / world.h, 0, world.g - 1)),
            int(np.clip((x + world.extent) / world.h, 0, world.g - 1)))


def _feeding_sum(world, i, j):
    """What is left in that 3x3 neighbourhood -- the food the animals are contesting."""
    return float(world.food[max(0, i - 1):min(world.g, i + 2),
                            max(0, j - 1):min(world.g, j + 2)].sum())


def multi_case():
    """Four animals on one lawn, advanced as a Population -- the path one animal cannot reach.

    Every other case in this file runs a single Simulation, and a Simulation is one animal:
    `World.eat_batch` never runs, the shared world is advanced by the animal that owns it,
    and no allocation is ever split. So the entire multi-animal half of the model sat
    outside the guarantee the conformance pair exists to provide.

    That is not a hypothetical gap, it is a divergence that had already shipped. #63 made
    contested feeding order-independent in Python -- demands batched, settled
    proportionally against one snapshot, the world aged once -- while the runtime kept
    capturing and debiting inside each animal's own step. Reproducing that defect here, on
    this plate, gives 0.016047241, 0.016038848, 0.016025892, 0.016025215 units eaten in
    array order -- monotonically decreasing, worm 3 measurably worse off for being worm 3
    -- against 0.016047229, 0.016042801, 0.016033364, 0.016036963 when the demands are
    settled together. #71 fixed the runtime. Nothing kept it fixed, because conformance ran
    one animal and wasm/population.mjs, which runs four, has no Python to compare against.

    AND THIS CASE FOUND A SECOND DIVERGENCE THE FIRST TIME IT RAN, which is the reason to
    write checks rather than arguments. The two settled contested feeding onto identical
    allocations and then took the food out of *different cells*: `World.eat_batch` spread
    each withdrawal so every cell in the union lost the same fraction, the runtime grazed
    each animal's own neighbourhood proportionally and let shared cells be grazed twice, and
    the plate came out 7.456e-04 apart at the first contested pump. The model moved rather
    than the port -- the runtime settles this at 2 kHz inside a browser tab and cannot run
    the linear program the old rule needed -- so `World.eat_batch` runs the runtime's rule
    now and this case is exact. worm/world.py has the account of what that traded away.

    THE PLATE HAS TO BE CONTESTED OR THE CASE TESTS NOTHING. Animals on separate lawns
    settle independently and agree whatever the batching does. Measured, not assumed: the
    same four animals moved 22.6 mm out from the middle, one private lawn each and 32 mm
    between the nearest pair, eat 0.016066596,
    0.016066239, 0.016058615, 0.016058423 with the correct settlement and the same numbers
    to 3.5e-18 with the per-animal defect above applied -- the case would pass, cheerfully,
    against the exact bug it exists to catch. That is the same trap as the empty dish that
    hid the missing field diffusion and the lawn-less plate that hid the food skirt, so the
    reference records what actually happened -- how many capture events there were and how
    many of them were contested -- and wasm/conform.mjs recounts both from the runtime's
    own state and refuses a run in which the animals never met. On this plate all 16
    capture events are contested.

    8000 steps is 4.0 s, which is not arbitrary either: the pharynx starts at its myogenic
    0.5 Hz and is carried up by serotonin as the animals taste the lawn, so the first pump
    lands at step 2881 and the fourth at 7207. A shorter run would compare four animals
    that had never eaten.
    """
    import dataclasses
    from worm.engine import Population, Simulation
    from worm.world import World

    p = Params()
    p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, noise_sigma=0.0))
    w = World(p.world, np.random.default_rng(0))
    x, y, r, density, attractant, length_scale = MULTI_LAWN
    w.add_food_patch(x, y, r, density=density, attractant=attractant,
                     length_scale=length_scale)
    sims = [Simulation(p, seed=0, world=w, placement=place) for place in MULTI_PLACEMENT]
    # check_every=None: the invariant sweep is the Python model's own check and belongs to
    # tests/test_population.py. Running it here would only slow the reference down, and a
    # state divergent enough to trip it would fail the comparison first and louder.
    pop = Population(sims, check_every=None)

    steps, sample = MULTI_STEPS, MULTI_SAMPLE
    out = {"steps": steps, "sample": sample, "n": len(sims),
           "lawn": list(MULTI_LAWN),
           "placement": [list(place) for place in MULTI_PLACEMENT],
           "food_start": round(float(w.food.sum()), 12),
           "frames": []}
    eaten_before = [0.0] * len(sims)
    captures = 0
    contested = 0
    for i in range(steps):
        pop.step()
        nodes = [sim.body.nodes() for sim in sims]
        # Contention, counted where it happens rather than inferred afterwards. A capture
        # event is a step on which an animal took food off the plate; it is contested when
        # some other animal's 3x3 neighbourhood overlaps the feeder's, because that is
        # exactly the condition under which the order of settlement can change what either
        # of them gets -- or what either of them senses on the next step, since the food
        # field is also a sensory field.
        cells = [_feeding_cell(w, node[0][0], node[0][1]) for node in nodes]
        for k, sim in enumerate(sims):
            if sim.food_eaten <= eaten_before[k]:
                continue
            captures += 1
            if any(o != k and abs(cells[k][0] - cells[o][0]) <= 2
                   and abs(cells[k][1] - cells[o][1]) <= 2 for o in range(len(sims))):
                contested += 1
        eaten_before = [sim.food_eaten for sim in sims]

        if (i + 1) % sample == 0:
            out["frames"].append({
                "step": i + 1,
                # The plate as a whole, so that "the lawn was actually drawn down" is a
                # number both sides compute rather than an assumption. The two sides sum
                # 65,536 cells in different orders, so this is compared loosely; what it
                # is for is the drawdown, which is 6.4e-02 by the end.
                "food": round(float(w.food.sum()), 12),
                "a": [{
                    "x": [round(float(v), 12) for v in nodes[k][:, 0]],
                    "y": [round(float(v), 12) for v in nodes[k][:, 1]],
                    "V": [round(float(v), 10) for v in sim.nervous.V],
                    "gate": 1.0 if sim.senses.going_forward else 0.0,
                    # lumen, ingested, eaten: what the pharynx holds, what reached the
                    # intestine, and what the plate lost. Only the third is settled by the
                    # batch, and comparing all three separates a wrong allocation from a
                    # wrong transport.
                    "ph": [round(float(sim.pharynx.lumen), 12),
                           round(float(sim.pharynx.ingested), 12),
                           round(float(sim.food_eaten), 12)],
                    # Which cells this animal was feeding from. Emitted so that a
                    # disagreement about *where* the 3x3 window sits fails as itself rather
                    # than as an inexplicable difference in what was eaten.
                    "cell": list(cells[k]),
                    # And what is left in that window. The plate total moves by 6.4e-02 out
                    # of 44, which a sum over 65,536 cells resolves poorly; nine cells
                    # resolve the contested food exactly.
                    "food9": round(_feeding_sum(w, *cells[k]), 12),
                } for k, sim in enumerate(sims)],
            })
    out["captures"] = captures
    out["contested"] = contested
    out["food_end"] = round(float(w.food.sum()), 12)
    out["eaten"] = [round(float(sim.food_eaten), 12) for sim in sims]
    return out


def main():
    json.dump({"body": body_case(), "folded": folded_case(),
               "full": full_case(), "ablated": ablated_case(),
               # 0.30 is the coefficient ModulatorParams.serotonin_mod1 documents as
               # adopted-then-shipped-at-zero. Running the reference there is the only way
               # this path gets compared at all.
               "mod1": full_case(serotonin_mod1=0.30),
               # The cascade at head_cascade.py's configuration -- 4 stages of 0.125 s,
               # no transport delay -- so the ported chain is exercised stage by stage
               # rather than sitting behind a branch the default never takes.
               "cascade": full_case(head_stages=4, head_delay=0.0, head_stage_tau=0.125),
               # The amine path, which is also the deepest exercise the modulator layer
               # gets: dopamine must integrate the transduced load and move three
               # effects for this to agree.
               "amine": full_case(amine=True),
               # Sleep on a compressed clock: bout entry, the FLP-11 gates, an arousal
               # by poke, the refractory, re-entry, discharge and exit -- all inside
               # one 2 s window. See the sleep block in full_case.
               "sleeping": full_case(sleep=True),
               # Several animals on one plate. Everything above is one animal, and one
               # animal cannot reach the batch settlement or the shared world advance.
               "multi": multi_case()},
              sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
