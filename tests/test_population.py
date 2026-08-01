"""Safety and shared-world invariants needed before evaluating populations."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from worm.engine import Population, Simulation
from worm.errors import DivergentSimulation, InvalidGenome
from worm.params import Params
from worm.world import World


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("body", "EI", -1.0e-3),
        ("body", "EI", np.nan),
        ("body", "internal_damping", -1.0e-4),
        ("neural", "C_m", 0.0),
        ("neural", "C_m", False),
        ("sensory", "tonic_forward", np.inf),
        ("sensory", "omega_tau", 0.0),
        ("sensory", "chemo_tau_adapt", 0.0),
        ("medium", "c_tangential", 0.0),
        ("world", "grid", 1.0),
    ],
)
def test_invalid_genomes_are_rejected_before_construction(section, field, value):
    base = Params()
    mutant_section = replace(getattr(base, section), **{field: value})
    mutant = replace(base, **{section: mutant_section})

    with pytest.raises(InvalidGenome, match=section + r"\." + field) as caught:
        Simulation(mutant)
    assert caught.value.lethal is True


def test_drag_anisotropy_must_remain_physical():
    base = Params()
    mutant = replace(
        base,
        medium=replace(base.medium, c_tangential=2.0, c_normal=1.0),
    )
    with pytest.raises(InvalidGenome, match=r"c_normal must be >= medium\.c_tangential"):
        Simulation(mutant)


def test_runtime_invariant_detects_divergent_curvature():
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    sim = Simulation(p, seed=0, world=world, placement=(0.0, 0.0, 0.0))
    sim.body.theta[1] = sim.body.theta[0] + 1.01 * np.pi

    with pytest.raises(DivergentSimulation, match="curvature") as caught:
        sim.check_invariants()
    assert caught.value.lethal is True


def test_run_checks_state_before_spending_an_evaluation_budget():
    p = Params()
    sim = Simulation(p, seed=0, world=World(p.world, np.random.default_rng(0)))
    sim.nervous.V[0] = np.nan

    with pytest.raises(DivergentSimulation, match="membrane potentials"):
        sim.run(1.0)


def test_world_rejects_nonfinite_and_out_of_dish_samples():
    p = Params()
    world = World(p.world, np.random.default_rng(0))

    with pytest.raises(DivergentSimulation, match="not finite"):
        world.sample(world.food, np.inf, 0.0)
    with pytest.raises(DivergentSimulation, match="left the dish"):
        world.sample(world.food, world.extent + 0.01, 0.0)


def test_population_advances_a_shared_world_once_per_tick():
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    animals = [
        Simulation(p, seed=seed, world=world, placement=(float(seed), 0.0, 0.0))
        for seed in range(3)
    ]
    population = Population(animals, check_every=None)

    for _ in range(4):
        population.step()

    assert world.t == pytest.approx(4 * animals[0].dt)
    assert all(sim.t == pytest.approx(world.t) for sim in animals)
    assert all(sim.steps == 4 for sim in animals)


def test_population_rejects_the_same_animal_twice():
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    sim = Simulation(p, seed=0, world=world)

    with pytest.raises(ValueError, match="only once"):
        Population([sim, sim])


def test_single_animal_step_still_advances_its_world():
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    sim = Simulation(p, seed=0, world=world)

    sim.step()

    assert sim.t == pytest.approx(sim.dt)
    assert world.t == pytest.approx(sim.dt)


def _contended_feeding_tick(order):
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    world.food[world.inside] = 0.01
    animals = {}
    sampled = {}
    for name, amount, seed in (("high", 0.09, 1), ("low", 0.03, 2)):
        sim = Simulation(p, seed=seed, world=world, placement=(0.1, 0.1, 0.0))

        pharynx = sim.pharynx

        def prepare(_activation, food_here, _modulators, alive=None,
                    request=amount, animal=name):
            sampled[animal] = food_here
            return request

        def finish(captured, target=pharynx):
            target.captured = float(captured)
            target.lumen += target.captured
            return 0.0

        sim.pharynx.prepare_step = prepare
        sim.pharynx.finish_step = finish
        sim.egglaying.step = lambda *_args, **_kwargs: 0.0
        animals[name] = sim

    initial_food = float(world.food.sum())
    Population([animals[name] for name in order], check_every=None).step()
    return (
        {name: animals[name].food_eaten for name in animals},
        sampled,
        world.food.copy(),
        initial_food - float(world.food.sum()),
        {name: animals[name].pharynx.captured for name in animals},
        {name: animals[name].pharynx.ingested + animals[name].pharynx.lumen
         for name in animals},
    )


def test_contended_feeding_is_proportional_and_iteration_order_safe():
    forward = _contended_feeding_tick(("high", "low"))
    reverse = _contended_feeding_tick(("low", "high"))
    eaten, sampled, food, removed, captured, held = forward

    assert sampled == pytest.approx({"high": 0.01, "low": 0.01})
    assert eaten == pytest.approx({"high": 0.0675, "low": 0.0225})
    assert captured == pytest.approx(eaten)
    assert held == pytest.approx(eaten)
    assert removed == pytest.approx(sum(eaten.values()))
    assert reverse[0] == pytest.approx(eaten)
    assert reverse[1] == pytest.approx(sampled)
    assert np.array_equal(reverse[2], food)
    assert reverse[3] == pytest.approx(removed)
    assert reverse[4] == pytest.approx(captured)
    assert reverse[5] == pytest.approx(held)


def test_real_population_capture_accounts_for_every_unit_removed_from_the_plate():
    p = Params()
    world = World(p.world, np.random.default_rng(0))
    world.food[world.inside] = 1.0
    animals = [
        Simulation(p, seed=seed, world=world, placement=(0.0, 0.0, 0.0))
        for seed in range(2)
    ]
    for sim in animals:
        sim.pharynx.phase = 1.0       # force a capture on this one focused tick

    initial_food = float(world.food.sum())
    Population(animals, check_every=None).step()

    removed = initial_food - float(world.food.sum())
    credited = sum(sim.food_eaten for sim in animals)
    held = sum(sim.pharynx.ingested + sim.pharynx.lumen for sim in animals)
    assert removed > 0.0
    assert removed == pytest.approx(credited)
    assert held == pytest.approx(credited)


def test_batch_feeding_reserves_shared_food_for_the_constrained_request():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))

    def settle(requests):
        world = World(p.world, np.random.default_rng(0))
        world.food[4, 4] = 1.0       # both requests can reach this cell
        world.food[4, 5] = 1.0       # only the request at x=0 can reach this one
        return world.eat_batch(requests), world.food

    forward, food_forward = settle([(0.0, 0.0, 1.0), (-1.0, 0.0, 1.0)])
    reverse, food_reverse = settle([(-1.0, 0.0, 1.0), (0.0, 0.0, 1.0)])

    assert forward == pytest.approx([1.0, 1.0])
    assert reverse == pytest.approx([1.0, 1.0])
    assert float(food_forward.sum()) == pytest.approx(0.0)
    assert np.array_equal(food_reverse, food_forward)


def test_partially_overlapping_batch_feeding_is_order_safe_when_food_is_short():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))

    def settle(requests):
        world = World(p.world, np.random.default_rng(0))
        world.food[4, 4] = 1.0       # shared by both requests
        world.food[4, 5] = 0.25      # reachable only from x=0
        return world.eat_batch(requests), world.food

    forward, food_forward = settle([(0.0, 0.0, 1.0), (-1.0, 0.0, 1.0)])
    reverse, food_reverse = settle([(-1.0, 0.0, 1.0), (0.0, 0.0, 1.0)])

    assert forward == pytest.approx([0.25, 1.0])
    assert reverse == pytest.approx([1.0, 0.25])
    assert float(food_forward.sum()) == pytest.approx(0.0)
    assert np.array_equal(food_reverse, food_forward)
