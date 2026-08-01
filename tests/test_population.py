"""Safety and shared-world invariants needed before evaluating populations."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from worm.engine import Population, Simulation
from worm.errors import DivergentSimulation, InvalidGenome
from worm.params import Params
from worm.world import World, _balanced_cell_withdrawals, _fair_group_allocations


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


def test_one_animal_population_step_matches_single_simulation_feeding():
    p = Params()
    direct_world = World(p.world, np.random.default_rng(0))
    population_world = World(p.world, np.random.default_rng(0))
    direct_world.food[direct_world.inside] = 1.0
    population_world.food[population_world.inside] = 1.0
    direct = Simulation(p, seed=3, world=direct_world, placement=(0.0, 0.0, 0.0))
    batched = Simulation(p, seed=3, world=population_world, placement=(0.0, 0.0, 0.0))
    direct.pharynx.phase = 1.0
    batched.pharynx.phase = 1.0

    direct.step()
    Population([batched], check_every=None).step()

    assert batched.food_eaten == pytest.approx(direct.food_eaten)
    assert batched.pharynx.lumen == pytest.approx(direct.pharynx.lumen)
    assert population_world.food == pytest.approx(direct_world.food)
    assert population_world.t == pytest.approx(direct_world.t)


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


def test_single_batch_request_matches_eat_allocation_and_food_field():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))
    direct = World(p.world, np.random.default_rng(0))
    batched = World(p.world, np.random.default_rng(0))
    patch = np.arange(1.0, 10.0).reshape(3, 3)
    direct.food[3:6, 3:6] = patch
    batched.food[3:6, 3:6] = patch

    expected = direct.eat(0.0, 0.0, 7.5)
    actual = batched.eat_batch([(0.0, 0.0, 7.5)])

    assert actual == pytest.approx([expected])
    assert batched.food == pytest.approx(direct.food)


def test_identical_under_demand_requests_share_and_deplete_proportionally():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))
    direct = World(p.world, np.random.default_rng(0))
    batched = World(p.world, np.random.default_rng(0))
    patch = np.arange(1.0, 10.0).reshape(3, 3)
    direct.food[3:6, 3:6] = patch
    batched.food[3:6, 3:6] = patch

    direct.eat(0.0, 0.0, 8.0)
    actual = batched.eat_batch([(0.0, 0.0, 2.0), (0.0, 0.0, 6.0)])

    assert actual == pytest.approx([2.0, 6.0])
    assert batched.food == pytest.approx(direct.food)


def test_disconnected_feeding_components_settle_like_separate_batches():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))
    combined = World(p.world, np.random.default_rng(0))
    separate = World(p.world, np.random.default_rng(0))
    combined.food[3:6, 0:3] = 0.05
    combined.food[3:6, 5:8] = np.arange(1.0, 10.0).reshape(3, 3)
    separate.food[:] = combined.food

    requests = [(-2.0, 0.0, 0.4), (-2.0, 0.0, 0.2), (2.0, 0.0, 4.0)]
    actual = combined.eat_batch(requests)
    expected = np.concatenate([
        separate.eat_batch(requests[:2]),
        separate.eat_batch(requests[2:]),
    ])

    assert actual == pytest.approx(expected)
    assert combined.food == pytest.approx(separate.food)


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

    assert forward == pytest.approx([0.625, 0.625])
    assert reverse == pytest.approx([0.625, 0.625])
    assert float(food_forward.sum()) == pytest.approx(0.0)
    assert np.array_equal(food_reverse, food_forward)


def test_symmetric_partial_overlap_has_no_grid_direction_winner():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))

    def settle(requests):
        world = World(p.world, np.random.default_rng(0))
        world.food[4, 3] = 0.1       # reachable only from the left
        world.food[4, 4] = 1.0       # shared
        world.food[4, 5] = 0.1       # reachable only from the right
        return world.eat_batch(requests), world.food

    forward, food_forward = settle([(-1.0, 0.0, 1.0), (1.0, 0.0, 1.0)])
    reverse, food_reverse = settle([(1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)])

    assert forward == pytest.approx([0.6, 0.6])
    assert reverse == pytest.approx([0.6, 0.6])
    assert float(food_forward.sum()) == pytest.approx(0.0)
    assert np.array_equal(food_reverse, food_forward)


def test_tight_floating_point_cut_does_not_make_batch_settlement_infeasible():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))
    world = World(p.world, np.random.default_rng(0))
    food = {
        (0, 0): 0.0001362244693329888, (0, 4): 0.00040197172232337954,
        (1, 3): 0.0014054929878358484, (1, 4): 10.152485164222277,
        (1, 5): 96.69595380308392, (1, 6): 0.0101279097854137,
        (2, 0): 73.16862389355865, (2, 1): 0.0007129847932643056,
        (2, 2): 0.0038068347781582443, (2, 3): 0.0001201276007603188,
        (2, 5): 9.17561151973112, (2, 6): 60.92521279143089,
        (3, 4): 49.548647323533935,
        (4, 4): 0.5262218582687361, (4, 5): 3.4492246854313233,
        (5, 0): 0.024870316683344357, (5, 1): 0.0007400278713197949,
        (5, 2): 27.68893153785075, (5, 7): 1.463765788317517,
        (6, 1): 2.2442208783474316, (6, 3): 0.018111704077300624,
        (6, 6): 46.77187026929906, (7, 6): 26.692213772158116,
    }
    for cell, amount in food.items():
        world.food[cell] = amount
    requests = [
        (1.5, 1.5, 16.964714191184136),
        (1.5, -1.5, 0.007200188048638822),
        (-0.5, -1.5, 0.23611436035767142),
        (-0.5, -0.5, 1.201273062556233),
        (-2.5, -1.5, 0.004203315317964025),
        (2.5, 0.5, 0.2746163049290664),
        (-1.5, 0.5, 0.08925461323159406),
        (-1.5, 2.5, 0.0003862869306268296),
    ]

    before = float(world.food.sum())
    allocated = world.eat_batch(requests)
    removed = before - float(world.food.sum())

    assert np.all(allocated >= 0.0)
    assert np.all(allocated <= np.asarray([request[2] for request in requests]))
    assert float(allocated.sum()) == pytest.approx(removed, abs=1e-12)


def test_tiny_saturated_cut_does_not_strand_unrelated_food():
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))
    world = World(p.world, np.random.default_rng(0))
    for cell, amount in {
        (4, 3): 0.0008563812547635219,
        (5, 1): 0.0002574031968079285,
        (5, 4): 0.10788040261546657,
        (6, 2): 15.096005643238989,
        (7, 5): 4.66322786948004,
    }.items():
        world.food[cell] = amount
    requests = [
        (-0.5, 1.5, 0.29259253942815083),
        (-0.5, 2.5, 0.00026363275749006267),
        (-2.5, 2.5, 37.89004653281265),
        (1.5, 2.5, 0.0038681349830417397),
    ]

    before = float(world.food.sum())
    allocated = world.eat_batch(requests)
    removed = before - float(world.food.sum())

    assert float(allocated.sum()) == pytest.approx(15.20886796528907, abs=1e-10)
    assert float(allocated.sum()) == pytest.approx(removed, abs=1e-12)


def test_cell_relabeling_does_not_bias_balanced_spatial_depletion():
    reachable = [(0, 2, 5), (0, 1, 2, 5), (1, 4, 5), (0, 3, 4, 5)]
    demands = np.asarray([
        0.00019525214344666251,
        0.03095259673736658,
        0.00015524092663456965,
        2.5216084935527756,
    ])
    capacities = np.asarray([
        0.06945656551923883,
        28.124970700268701,
        15.448616194258246,
        0.010053538338569234,
        11.495222571716887,
        0.00013811797330998043,
    ])
    targets = _fair_group_allocations(reachable, demands, capacities)
    allocated, withdrawn = _balanced_cell_withdrawals(
        reachable, targets, capacities)

    cell_order = np.asarray([5, 2, 0, 1, 3, 4])
    inverse = np.empty_like(cell_order)
    inverse[cell_order] = np.arange(len(cell_order))
    canonical = sorted(
        (tuple(sorted(int(inverse[cell]) for cell in group)), group_i)
        for group_i, group in enumerate(reachable)
    )
    relabeled_reachable = [group for group, _group_i in canonical]
    group_order = [group_i for _group, group_i in canonical]
    relabeled_targets = _fair_group_allocations(
        relabeled_reachable, demands[group_order], capacities[cell_order])
    relabeled_allocated, relabeled_withdrawn = _balanced_cell_withdrawals(
        relabeled_reachable, relabeled_targets, capacities[cell_order])
    mapped_allocated = np.empty_like(relabeled_allocated)
    mapped_allocated[group_order] = relabeled_allocated
    mapped_withdrawn = np.empty_like(relabeled_withdrawn)
    mapped_withdrawn[cell_order] = relabeled_withdrawn

    assert mapped_allocated == pytest.approx(allocated, abs=1e-10)
    assert mapped_withdrawn == pytest.approx(withdrawn, abs=1e-9)
    assert withdrawn[1] / capacities[1] == pytest.approx(
        withdrawn[2] / capacities[2], abs=1e-10)


def test_cell_leveling_remains_label_independent_at_a_tight_cut():
    reachable = [(1,), (0, 2), (1, 2), (0, 3), (0, 1, 3)]
    demands = np.asarray([
        99.86912174666736,
        0.50585984694991315,
        21.310871673875386,
        0.0032113329082032772,
        0.036428560017572997,
    ])
    capacities = np.asarray([
        43.632251711359771,
        71.446563232100118,
        0.00053802024288964725,
        7.9499753755333815,
    ])
    targets = _fair_group_allocations(reachable, demands, capacities)
    allocated, withdrawn = _balanced_cell_withdrawals(
        reachable, targets, capacities)

    cell_order = np.asarray([0, 3, 2, 1])
    inverse = np.empty_like(cell_order)
    inverse[cell_order] = np.arange(len(cell_order))
    canonical = sorted(
        (tuple(sorted(int(inverse[cell]) for cell in group)), group_i)
        for group_i, group in enumerate(reachable)
    )
    relabeled_reachable = [group for group, _group_i in canonical]
    group_order = [group_i for _group, group_i in canonical]
    relabeled_targets = _fair_group_allocations(
        relabeled_reachable, demands[group_order], capacities[cell_order])
    relabeled_allocated, relabeled_withdrawn = _balanced_cell_withdrawals(
        relabeled_reachable, relabeled_targets, capacities[cell_order])
    mapped_allocated = np.empty_like(relabeled_allocated)
    mapped_allocated[group_order] = relabeled_allocated
    mapped_withdrawn = np.empty_like(relabeled_withdrawn)
    mapped_withdrawn[cell_order] = relabeled_withdrawn

    assert mapped_allocated == pytest.approx(allocated, abs=1e-10)
    assert mapped_withdrawn == pytest.approx(withdrawn, abs=1e-9)
    assert float(allocated.sum()) == pytest.approx(float(withdrawn.sum()), abs=1e-12)


def test_frozen_cell_tiers_remain_feasible_after_relabeling():
    reachable = [
        (0,), (2,), (0, 2, 3), (0, 1, 2, 4), (3, 5), (0, 2, 4, 5, 6),
    ]
    targets = np.asarray([
        0.0074091873678323933,
        0.15732785745858727,
        7.3054720748202273,
        0.0029339322465515238,
        0.0770975747005367,
        0.08361935449248538,
    ])
    capacities = np.asarray([
        0.0091921682950217,
        0.10024243368771162,
        7.461016951381441,
        0.05772162750752929,
        1.2688877147264204,
        0.01937594719704408,
        0.03498121147904196,
    ])
    allocated, withdrawn = _balanced_cell_withdrawals(
        reachable, targets, capacities)

    cell_order = np.asarray([2, 4, 0, 6, 1, 3, 5])
    relabeled_reachable = [
        (0,), (0, 1, 2, 3, 6), (0, 1, 2, 4), (0, 2, 5), (2,), (5, 6),
    ]
    group_order = np.asarray([1, 5, 3, 2, 0, 4])
    relabeled_allocated, relabeled_withdrawn = _balanced_cell_withdrawals(
        relabeled_reachable, targets[group_order], capacities[cell_order])
    mapped_allocated = np.empty_like(relabeled_allocated)
    mapped_allocated[group_order] = relabeled_allocated
    mapped_withdrawn = np.empty_like(relabeled_withdrawn)
    mapped_withdrawn[cell_order] = relabeled_withdrawn

    assert mapped_allocated == pytest.approx(allocated, abs=1e-10)
    assert mapped_withdrawn == pytest.approx(withdrawn, abs=1e-9)
    assert float(allocated.sum()) == pytest.approx(float(withdrawn.sum()), abs=1e-12)


def test_cell_tier_probe_allows_solver_scale_slack():
    reachable = [(0,), (1,), (0, 1)]
    targets = np.asarray([
        0.20811164647933927,
        0.00689015494040061,
        0.00436362537898892,
    ])
    capacities = np.asarray([0.20811164649880284, 0.09342482249783483])

    allocated, withdrawn = _balanced_cell_withdrawals(
        reachable, targets, capacities)

    assert allocated == pytest.approx(targets, abs=1e-12)
    assert float(allocated.sum()) == pytest.approx(float(withdrawn.sum()), abs=1e-12)
    assert np.all(withdrawn <= capacities)
