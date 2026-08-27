"""Safety and shared-world invariants needed before evaluating populations."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from worm.engine import Population, Simulation
from worm.errors import DivergentSimulation, InvalidGenome
from worm.params import Params
from worm.world import World, _settle_by_claim


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
    # The failure line sits 0.5 mm beyond the rim (the wall zone's working margin --
    # see World._validate_coordinates); just past the rim is a wall-contained nose
    # reading the rim cell, past the margin is an escape.
    world.sample(world.food, world.extent + 0.49, 0.0)   # contained: must not raise
    with pytest.raises(DivergentSimulation, match="left the dish"):
        world.sample(world.food, world.extent + 0.51, 0.0)


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


def test_shared_food_is_grazed_twice_rather_than_routed_around():
    """No central planner moves an animal off contested ground, and that costs throughput.

    This test used to be `test_batch_feeding_reserves_shared_food_for_the_constrained_
    request` and used to assert [1.0, 1.0] with the plate emptied: the max-flow rule routed
    the animal that could reach both cells onto the private one and left the shared cell
    entirely to the animal that could only reach that. It maximised collective intake.

    The rule is now the runtime's -- see World.eat_batch for why the model moved rather than
    the port -- and the runtime does not plan. Each animal grazes its own neighbourhood
    proportionally, so the animal at x=0 takes half its claim from the contested cell even
    though the other animal has nowhere else to go. Measured, the pair now takes
    1.666666667 of the 2.0 present and leaves 0.333333333 in a cell only an already-full
    animal could reach.

    That is a real loss and it is written down here rather than in a commit message. What
    is kept is order-independence and conservation.
    """
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))

    def settle(requests):
        world = World(p.world, np.random.default_rng(0))
        world.food[4, 4] = 1.0       # both requests can reach this cell
        world.food[4, 5] = 1.0       # only the request at x=0 can reach this one
        return world.eat_batch(requests), world.food

    forward, food_forward = settle([(0.0, 0.0, 1.0), (-1.0, 0.0, 1.0)])
    reverse, food_reverse = settle([(-1.0, 0.0, 1.0), (0.0, 0.0, 1.0)])

    assert forward == pytest.approx([1.0, 2.0 / 3.0])
    assert reverse == pytest.approx([2.0 / 3.0, 1.0])
    assert float(forward.sum()) == pytest.approx(2.0 - float(food_forward.sum()))
    assert float(food_forward.sum()) == pytest.approx(1.0 / 3.0)
    assert np.array_equal(food_reverse, food_forward)


def test_partially_overlapping_batch_feeding_is_order_safe_when_food_is_short():
    """Short food is split by claim, not by a fairness criterion, and order cannot matter.

    The split used to be 0.625/0.625 -- weighted max-min fairness, every group raised to the
    same fraction of its demand until a reachability cut stopped it. It is now
    0.694444444/0.555555556: the animal that can reach 1.25 units claims 0.8 of each of its
    cells and the animal that can reach only 1.0 claims all of its one cell, so the shared
    cell is split 0.8 : 1.0 and the private cell goes entirely to the animal that can reach
    it. Both totals are 1.25, because the change is to who gets it and not to how much
    leaves the plate.

    Order-independence is the property this test is named for and it survives unchanged.
    """
    base = Params()
    p = replace(base, world=replace(base.world, radius=4.0, grid=8))

    def settle(requests):
        world = World(p.world, np.random.default_rng(0))
        world.food[4, 4] = 1.0       # shared by both requests
        world.food[4, 5] = 0.25      # reachable only from x=0
        return world.eat_batch(requests), world.food

    forward, food_forward = settle([(0.0, 0.0, 1.0), (-1.0, 0.0, 1.0)])
    reverse, food_reverse = settle([(-1.0, 0.0, 1.0), (0.0, 0.0, 1.0)])

    assert forward == pytest.approx([0.6944444444444444, 0.5555555555555556])
    assert reverse == pytest.approx([0.5555555555555556, 0.6944444444444444])
    assert float(forward.sum()) == pytest.approx(1.25)
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


def test_saturated_cut_conserves_what_it_does_take():
    """A hard configuration, kept for conservation now that throughput is not guaranteed.

    This was `test_tiny_saturated_cut_does_not_strand_unrelated_food` and asserted a total
    of 15.20886796528907 -- every unit any animal could reach. The claim rule takes
    15.107720018824944 from the same plate and strands 0.101147946464126 of it, because the
    animal that could have cleared the small cell spends part of its claim on ground it
    shares. Not stranding food was a property of the max-flow routing and it is gone; see
    World.eat_batch.

    What this configuration is still worth testing is the part that must never go: whatever
    is credited to the animals is exactly what left the plate, on a field whose cells span
    five orders of magnitude and where a settlement can saturate.
    """
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

    assert float(allocated.sum()) == pytest.approx(15.107720018824944, abs=1e-10)
    assert float(allocated.sum()) == pytest.approx(removed, abs=1e-12)
    assert np.all(allocated >= 0.0)
    assert np.all(allocated <= np.asarray([request[2] for request in requests]))
    assert np.all(world.food >= 0.0)


# --------------------------------------------------------------------- the claim rule ---
# Four tests used to live here, written directly against `_fair_group_allocations` and
# `_balanced_cell_withdrawals`: cell-relabeling invariance of the balanced spatial
# depletion, label independence at a tight cut, feasibility of frozen cell tiers, and
# solver-scale slack in the tier probe. All four were about one property --
#
#     the settlement minimises the largest fractional depletion of any food cell,
#
# and that property is deliberately gone. It was produced by a linear program over a
# max-flow, and the WebAssembly runtime settles this at 2 kHz inside a browser tab and
# cannot run a linear program; it grazes each animal's neighbourhood proportionally and
# lets shared ground be grazed twice. Given a model and a port that disagreed, the model
# moved: two animals eating the same bacteria really do take more out of the ground they
# share than out of the ground only one of them is standing on. The multi-animal
# conformance case in wasm/conform.mjs is what found the disagreement, at 7.456e-04 on the
# plate; worm/world.py's `eat_batch` has the full account of what was traded away.
#
# The properties that had to survive are below, now asserted against the rule that replaced
# it: conservation, request-order independence, cell-relabeling invariance, and reduction to
# World.eat for a single neighbourhood.

_CLAIM_REACHABLE = [(0, 2, 5), (0, 1, 2, 5), (1, 4, 5), (0, 3, 4, 5)]
_CLAIM_DEMANDS = [
    0.00019525214344666251,
    0.03095259673736658,
    0.00015524092663456965,
    2.5216084935527756,
]
_CLAIM_CAPACITIES = np.asarray([
    0.06945656551923883,
    28.124970700268701,
    15.448616194258246,
    0.010053538338569234,
    11.495222571716887,
    0.00013811797330998043,
])


def test_claim_settlement_conserves_and_never_overdraws():
    received, left = _settle_by_claim(
        _CLAIM_REACHABLE, _CLAIM_DEMANDS, _CLAIM_CAPACITIES)

    assert np.all(np.asarray(left) >= 0.0)
    assert np.all(np.asarray(left) <= _CLAIM_CAPACITIES)
    assert np.all(np.asarray(received) >= 0.0)
    assert np.all(np.asarray(received) <= np.asarray(_CLAIM_DEMANDS) + 1e-15)
    assert float(np.sum(received)) == pytest.approx(
        float(_CLAIM_CAPACITIES.sum() - np.sum(left)), abs=1e-12)


def test_claim_settlement_does_not_depend_on_request_order():
    """Which animal is worm 0 must not decide what worm 0 eats.

    This is the invariant #63 was filed for and the one the runtime broke before #71: the
    old runtime captured and debited inside each animal's own step, so a contested lawn paid
    a bonus for a low array index. The rule here reads every claim against one snapshot
    before any of it is withdrawn, which makes the result a function of the configuration
    and not of the iteration.
    """
    order = [2, 0, 3, 1]
    received, left = _settle_by_claim(
        _CLAIM_REACHABLE, _CLAIM_DEMANDS, _CLAIM_CAPACITIES)
    shuffled_received, shuffled_left = _settle_by_claim(
        [_CLAIM_REACHABLE[i] for i in order],
        [_CLAIM_DEMANDS[i] for i in order],
        _CLAIM_CAPACITIES,
    )

    mapped = np.empty(len(received))
    mapped[order] = shuffled_received
    assert mapped == pytest.approx(np.asarray(received), abs=1e-12)
    assert np.asarray(shuffled_left) == pytest.approx(np.asarray(left), abs=1e-12)


def test_claim_settlement_is_cell_relabeling_invariant():
    """Renumbering the cells must not move the food.

    The grid gives cells an order and nothing about feeding should inherit it. The old
    max-flow settlement could: its traversal order chose among equivalent routings, which is
    why the tests this replaces existed at all.
    """
    received, left = _settle_by_claim(
        _CLAIM_REACHABLE, _CLAIM_DEMANDS, _CLAIM_CAPACITIES)

    cell_order = np.asarray([5, 2, 0, 1, 3, 4])
    inverse = np.empty_like(cell_order)
    inverse[cell_order] = np.arange(len(cell_order))
    relabeled_reachable = [tuple(sorted(int(inverse[cell]) for cell in group))
                           for group in _CLAIM_REACHABLE]
    relabeled_received, relabeled_left = _settle_by_claim(
        relabeled_reachable, _CLAIM_DEMANDS, _CLAIM_CAPACITIES[cell_order])
    mapped_left = np.empty(len(left))
    mapped_left[cell_order] = relabeled_left

    assert np.asarray(relabeled_received) == pytest.approx(
        np.asarray(received), abs=1e-12)
    assert mapped_left == pytest.approx(np.asarray(left), abs=1e-12)


def test_claim_settlement_reduces_to_eat_for_one_neighbourhood():
    """One animal alone is `World.eat`, exactly, and that is what keeps the two paths one.

    `eat_batch` keeps a separate proportional branch for a group nothing else reaches,
    because that branch is what makes `Population([sim]).step` observationally equivalent to
    `Simulation.step`. It is only safe to keep because the claim rule computes the same
    thing for a single request: the claim is min(1, want/avail) and the cell keeps
    have * (1 - claim), which is the proportional withdrawal written the other way round.
    Checked here to the last bit, over-demand as well as under.
    """
    capacities = np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    cells = tuple(range(len(capacities)))
    available = float(capacities.sum())

    for want in (7.5, available, available * 2.0, 0.0):
        received, left = _settle_by_claim([cells], [want], capacities)
        taken = min(want, available)
        assert received[0] == taken
        assert np.asarray(left) == pytest.approx(
            capacities * (1.0 - taken / available), abs=0.0, rel=1e-15)
