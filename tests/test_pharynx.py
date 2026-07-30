"""Feeding: the pump rate, and the ablations that were not fitted to anything.

Three coefficients were fitted to put the pump rate on target, so the rate on its own is
weak evidence. The ablation *directions* are the real test -- none of them was tuned, each
predicts a direction from decades of laser-ablation and mutant work, and between them they
are the reason to believe the pharynx is doing something rather than merely producing a
number.
"""

from __future__ import annotations

import numpy as np

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


def test_pump_rate_matches_a_feeding_animal():
    """200-300 pumps a minute on E. coli, far lower off food (Avery & Horvitz 1989)."""
    on = _run(on_food=True)
    off = _run(on_food=False)
    assert 200.0 <= on["rate"] <= 300.0, (
        "on food the animal pumped %.0f times a minute, outside 200-300" % on["rate"])
    assert off["rate"] < on["rate"] / 3.0, (
        "off food %.0f /min against %.0f on food: food barely changes the feeding rate"
        % (off["rate"], on["rate"]))
    assert 0.10 <= on["duration"] <= 0.22, (
        "pump lasted %.0f ms, outside the animal's 150-200" % (1000 * on["duration"]))


def test_killing_the_pacemaker_reproduces_eat_2():
    """MC gone: pumping several-fold slower, and the animal ingests almost nothing.

    eat-2 encodes the receptor subunit MC acts on, and eat-2 animals pump slowly and grow
    up starved (Avery 1993). This is also the test that forced serotonin to act *through*
    MC rather than beside it: modelled as a parallel term, killing MC cost 5% of the rate,
    because the serotonergic drive simply carried on without a pacemaker to act on.
    """
    intact = _run(ablate=())
    eat2 = _run(ablate=("MCL", "MCR"))
    assert eat2["rate"] < intact["rate"] / 3.0, (
        "MC ablated pumped %.0f /min against %.0f intact: not a several-fold slowdown"
        % (eat2["rate"], intact["rate"]))
    assert eat2["ingest"] < intact["ingest"] / 3.0, "MC ablated did not go hungry"


def test_killing_m4_stops_feeding_without_stopping_pumping():
    """The phenotype that makes transport a separate step from capture.

    M4 drives isthmus peristalsis. Ablated animals pump at a normal rate and starve
    anyway (Avery & Horvitz 1987), so a model where ingestion is a property of the pump
    cannot express this at all -- it would have to slow the pumping to stop the feeding.
    """
    intact = _run(ablate=())
    m4 = _run(ablate=("M4",))
    assert m4["rate"] > 0.7 * intact["rate"], (
        "M4 ablated pumped %.0f /min against %.0f intact: pumping should be unaffected"
        % (m4["rate"], intact["rate"]))
    assert m4["ingest"] < intact["ingest"] / 3.0, (
        "M4 ablated still ingested %.5f against %.5f intact"
        % (m4["ingest"], intact["ingest"]))
    assert m4["lumen"] > 0.5 * Params().pharynx.lumen_capacity, (
        "food should back up in the lumen with no peristalsis to move it (%.4f)"
        % m4["lumen"])


def test_killing_m3_lengthens_the_pump():
    """M3 is inhibitory onto the muscle and repolarises it, so it ends the pump."""
    intact = _run(ablate=())
    m3 = _run(ablate=("M3L", "M3R"))
    assert m3["duration"] > 1.05 * intact["duration"], (
        "M3 ablated gave %.0f ms pumps against %.0f intact"
        % (1000 * m3["duration"], 1000 * intact["duration"]))


def test_the_pharynx_is_what_empties_the_lawn():
    """Whatever the pharynx transports is what the world loses, and nothing else is."""
    r = _run(on_food=True, seconds=40.0)
    sim = r["sim"]
    assert sim.food_eaten > 0.0, "the animal sat on a lawn and ate nothing"
    assert abs(sim.food_eaten - sim.pharynx.ingested) < 1e-9 * max(sim.food_eaten, 1.0), (
        "the world lost %.6f but the pharynx transported %.6f"
        % (sim.food_eaten, sim.pharynx.ingested))


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
