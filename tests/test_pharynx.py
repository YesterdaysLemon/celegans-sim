"""Feeding: the pump rate, and the ablations that were not fitted to anything.

Three coefficients were fitted to put the pump rate on target, so the rate on its own is
weak evidence. The ablation *directions* are the real test -- none of them was tuned, each
predicts a direction from decades of laser-ablation and mutant work, and between them they
are the reason to believe the pharynx is doing something rather than merely producing a
number.
"""

from __future__ import annotations

import numpy as np
import pytest

from worm.engine import Simulation
from worm.params import Params
from worm.world import World

SETTLE, MEASURE = 15.0, 60.0


def _run(on_food=True, ablate=(), seconds=MEASURE, seed=0):
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    if on_food:
        w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(p, seed=seed, world=w, placement=(0.0, 0.0, 0.0))
    if ablate:
        sim.set_ablated(list(ablate))
    sim.run(SETTLE)
    p0, e0 = sim.pharynx.pumps, sim.pharynx.ingested
    durations, was = [], sim.pharynx.pumping
    for _ in range(int(seconds / sim.dt)):
        sim.step()
        if sim.pharynx.pumping and not was:
            durations.append(sim.pharynx.duration)
        was = sim.pharynx.pumping
    return dict(sim=sim,
                rate=(sim.pharynx.pumps - p0) * 60.0 / seconds,
                ingest=(sim.pharynx.ingested - e0) / seconds,
                duration=float(np.mean(durations)) if durations else float("nan"),
                lumen=sim.pharynx.lumen)


@pytest.fixture(scope="module")
def intact():
    return _run(ablate=())


@pytest.fixture(scope="module")
def off_food():
    return _run(on_food=False)


@pytest.fixture(scope="module")
def eat2():
    return _run(ablate=("MCL", "MCR"))


@pytest.fixture(scope="module")
def m4():
    return _run(ablate=("M4",))


@pytest.fixture(scope="module")
def m3():
    return _run(ablate=("M3L", "M3R"))


def test_pump_rate_matches_a_feeding_animal(intact, off_food):
    """200-300 pumps a minute on E. coli, far lower off food (Avery & Horvitz 1989)."""
    on, off = intact, off_food
    assert 200.0 <= on["rate"] <= 300.0, (
        "on food the animal pumped %.0f times a minute, outside 200-300" % on["rate"])
    assert off["rate"] < on["rate"] / 3.0, (
        "off food %.0f /min against %.0f on food: food barely changes the feeding rate"
        % (off["rate"], on["rate"]))
    assert 0.10 <= on["duration"] <= 0.22, (
        "pump lasted %.0f ms, outside the animal's 150-200" % (1000 * on["duration"]))


def test_killing_the_pacemaker_reproduces_eat_2(intact, eat2):
    """MC gone: pumping several-fold slower, and the animal ingests almost nothing.

    eat-2 encodes the receptor subunit MC acts on, and eat-2 animals pump slowly and grow
    up starved (Avery 1993). This is also the test that forced serotonin to act *through*
    MC rather than beside it: modelled as a parallel term, killing MC cost 5% of the rate,
    because the serotonergic drive simply carried on without a pacemaker to act on.
    """
    assert eat2["rate"] < intact["rate"] / 3.0, (
        "MC ablated pumped %.0f /min against %.0f intact: not a several-fold slowdown"
        % (eat2["rate"], intact["rate"]))
    assert eat2["ingest"] < intact["ingest"] / 3.0, "MC ablated did not go hungry"


def test_killing_m4_stops_feeding_without_stopping_pumping(intact, m4):
    """The phenotype that makes transport a separate step from capture.

    M4 drives isthmus peristalsis. Ablated animals pump at a normal rate and starve
    anyway (Avery & Horvitz 1987), so a model where ingestion is a property of the pump
    cannot express this at all -- it would have to slow the pumping to stop the feeding.
    """
    assert m4["rate"] > 0.7 * intact["rate"], (
        "M4 ablated pumped %.0f /min against %.0f intact: pumping should be unaffected"
        % (m4["rate"], intact["rate"]))
    assert m4["ingest"] < intact["ingest"] / 3.0, (
        "M4 ablated still ingested %.5f against %.5f intact"
        % (m4["ingest"], intact["ingest"]))
    assert m4["lumen"] > 0.5 * Params().pharynx.lumen_capacity, (
        "food should back up in the lumen with no peristalsis to move it (%.4f)"
        % m4["lumen"])


def test_killing_m3_lengthens_the_pump(intact, m3):
    """M3 is inhibitory onto the muscle and repolarises it, so it ends the pump."""
    assert m3["duration"] > 1.05 * intact["duration"], (
        "M3 ablated gave %.0f ms pumps against %.0f intact"
        % (1000 * m3["duration"], 1000 * intact["duration"]))


def test_the_pharynx_is_what_empties_the_lawn():
    """What the plate loses is what the animal is holding, to the last decimal.

    The invariant is `food_eaten == ingested + lumen`, not `food_eaten == ingested`: food
    leaves the plate when the pharynx captures it, and only reaches the intestine when M4
    transports it, so the difference between the two is whatever is in the mouth. Asserting
    the stronger-looking equality is what let a conservation bug live here, because on a
    stationary animal in a uniform lawn the two are indistinguishable.
    """
    r = _run(on_food=True, seconds=40.0)
    sim = r["sim"]
    assert sim.food_eaten > 0.0, "the animal sat on a lawn and ate nothing"
    held = sim.pharynx.ingested + sim.pharynx.lumen
    assert abs(sim.food_eaten - held) < 1e-9 * max(sim.food_eaten, 1.0), (
        "the world lost %.9f but the animal holds %.9f (%.9f transported + %.9f in lumen)"
        % (sim.food_eaten, held, sim.pharynx.ingested, sim.pharynx.lumen))


def test_food_is_conserved_when_the_animal_moves_between_capture_and_transport():
    """Carrying a full mouth off the lawn must not create food, or destroy it.

    Capture and transport are separated by about a lumen's worth of time, and the animal
    keeps moving in between. Debiting the world at *transport* time therefore took the food
    from wherever the head had drifted to -- which for an animal that had left the lawn was
    nowhere at all. Measured before this was fixed: 0.00451 captured into the lumen on the
    lawn, 0.00000000 removed from the world, and the uterus credited for all of it.

    The check is deliberately end-to-end rather than on the pharynx alone, because the bug
    lived in the seam between the pharynx and the world.
    """
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 6.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(p, seed=5, world=w, placement=(0.0, 0.0, 0.35))
    start = float(sim.world.food.sum())

    sim.run(6.0)                                   # feed on the lawn
    sim.body.pos = np.array([30.0, 30.0])          # picked up, put down on bare agar
    sim._nodes = sim.body.nodes()
    carried = sim.pharynx.lumen
    assert carried > 0.0, "the animal left the lawn with an empty mouth; nothing to test"
    # This assay deliberately teleports the animal; disable the evolutionary divergence
    # gate so the tracker spike from that intervention does not obscure food accounting.
    sim.run(4.0, check_every=None)                 # long enough for M4 to empty it

    removed = start - float(sim.world.food.sum())
    held = sim.pharynx.ingested + sim.pharynx.lumen
    assert abs(held - removed) < 1e-9 * max(removed, 1.0), (
        "the animal holds %.9f but the plate only lost %.9f -- %.3e appeared from nowhere"
        % (held, removed, held - removed))
    assert abs(sim.food_eaten - removed) < 1e-9 * max(removed, 1.0), (
        "food_eaten %.9f disagrees with the plate's own loss %.9f"
        % (sim.food_eaten, removed))


def test_an_ablated_source_falls_silent_rather_than_reversing():
    """Killing a cell must remove its signal, not invert it.

    Modulator levels and pharyngeal drives are deviations from a resting activation of
    0.5, and an ablated neuron reads 0.0 -- so before this was masked, killing NSM drove
    serotonin to -0.133 where it should have gone to zero, and flipped the serotonergic
    turn bias from +0.090 to -0.080. Every ablation experiment that touched a modulator
    source was reading a sign error, and the pharynx made it visible by turning the
    pacemaker off entirely.
    """
    p = Params()
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)

    intact = Simulation(p, seed=0, world=w, placement=(0.0, 0.0, 0.0))
    intact.run(20.0)
    assert intact.modulators.level["serotonin"] > 0.05, "no food signal to begin with"

    killed = Simulation(p, seed=0, world=w, placement=(0.0, 0.0, 0.0))
    killed.set_ablated(["NSML", "NSMR"])
    killed.run(20.0)
    s = killed.modulators.level["serotonin"]
    assert abs(s) < 0.05, (
        "with its only source ablated serotonin sat at %+.4f; it should be near zero, "
        "and a negative value means the dead cell is signalling in reverse" % s)
