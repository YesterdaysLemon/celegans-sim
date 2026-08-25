"""Eating a lawn has to dim the gradients that lawn sources.

Before #48 it did not. `World.eat` moved the `food` array and nothing else, so a plate that
had been grazed to nothing went on smelling and respiring exactly like a full one: in the
probe on the issue, food totals of 18.986935 against 0 with a maximum attractant difference
of 0, a maximum oxygen-deficit difference of 0, and 6% oxygen at the middle of both. An
animal could chemotax and aerotax towards a lawn that was not there, indefinitely.

What holds now is stated in worm/world.py's module docstring: both fields are the steady
state of a *linear* equation, so a lawn with fraction f_p of its bacteria left sources f_p
of the field with the same shape. These are the claims that follow from that -- plus the
one property the design was chosen for, which is that an intact lawn is left alone, bit for
bit.
"""

import numpy as np
import pytest

from worm.engine import Simulation
from worm.params import Params
from worm.world import MAX_FOOD_PATCHES, World


FIELD_STEPS_PER_SECOND = 50          # 1 / WorldParams.field_dt
# Long enough for the attractant to separate visibly. Its relaxation time is
# 1 / decay_attractant = 1250 s, so a horizon much shorter than this compares three fields
# that have barely left their shared starting point; 300 s is a quarter of the time
# constant and costs 15,000 field steps a world, which is what a test can afford.
HORIZON = 300.0


@pytest.fixture(scope="module")
def params():
    return Params()


def plate(params):
    """The conformance plate: two overlapping lawns and nothing else.

    Overlapping on purpose. Their centres are 7.21 mm apart and their radii sum to 8, so
    they share ground, which is the configuration the footprint rule has to be defensible
    about -- see the overlap note in `World.add_food_patch`.
    """
    w = World(params.world, np.random.default_rng(0))
    w.add_food_patch(-6.0, 4.0, 5.0, density=1.0, attractant=1.0, length_scale=9.0)
    w.add_food_patch(0.0, 0.0, 3.0, density=1.0, attractant=0.6, length_scale=6.0)
    return w


def run_fields(world, seconds):
    for _ in range(int(round(seconds * FIELD_STEPS_PER_SECOND))):
        world.step(1.0 / FIELD_STEPS_PER_SECOND)


# --------------------------------------------------------------------------------------
# The property the design was chosen for.

def test_intact_lawn_is_an_exact_fixed_point_of_the_decay_terms(params):
    """An uneaten lawn's attractant step is exactly what it was before #48 existed.

    The source term is `decay * (source - c)`, and with nothing eaten `source` IS `c`, so
    the two decay terms cancel to a bitwise zero and the step reduces to `c + dt*D*lap(c)`
    -- the diffusion that was always there. That is what keeps existing behaviour on a full
    plate intact, and it is why the field is relaxed towards the sourced profile rather than
    overwritten with it.

    Asserted as array equality, not `allclose`. A residual of 1e-17 would mean the
    cancellation was arithmetic luck rather than structure, and luck does not survive
    someone authoring a lawn with a different length scale.
    """
    w = plate(params)
    c = w.attractant.copy()

    assert np.array_equal(w._att_source, c), "an intact plate must source its own field"

    lap = (np.roll(c, 1, 0) + np.roll(c, -1, 0)
           + np.roll(c, 1, 1) + np.roll(c, -1, 1) - 4.0 * c) / (w.h * w.h)
    pure_diffusion = c + params.world.field_dt * (params.world.diffusion_attractant * lap)
    np.clip(pure_diffusion, 0.0, None, out=pure_diffusion)
    pure_diffusion *= w.inside

    stepped = w._relax(c, params.world.diffusion_attractant, params.world.decay_attractant,
                       params.world.field_dt, w._att_source)
    residual = float(np.abs(stepped - pure_diffusion).max())
    assert residual == 0.0, "decay terms left a residual of %.3e" % residual
    assert np.array_equal(stepped, pure_diffusion)

    # ...and the step is not itself a no-op, or the equality above would be vacuous: the
    # diffusion term moves the field by 4.562e-05 in a single 0.02 s tick.
    assert float(np.abs(stepped - c).max()) == pytest.approx(4.5615435588342024e-05,
                                                             rel=1e-9)


def test_a_plate_with_no_food_steps_to_the_same_bits_as_pure_decay(params):
    """No patches, no source, and `decay * (0 - c)` is `-decay * c` exactly.

    This is what leaves the mechanics conformance case and every bare-agar result alone: a
    dish with nothing on it cannot tell that any of this was added.
    """
    w = World(params.world, np.random.default_rng(0))
    w.add_repellent_source(7.0, -3.0, strength=0.9, length_scale=5.0)
    # Something non-trivial in the attractant field that no patch is sourcing, so the
    # comparison is over a field that is actually moving.
    w.attractant = np.exp(-((w.gx - 2.0) ** 2 + (w.gy + 1.0) ** 2) / 40.0) * w.inside
    c = w.attractant.copy()

    sourced = w._relax(c, params.world.diffusion_attractant, params.world.decay_attractant,
                       params.world.field_dt, w._att_source)
    unsourced = w._diffuse(c, params.world.diffusion_attractant,
                           params.world.decay_attractant, params.world.field_dt)
    assert np.array_equal(sourced, unsourced)
    assert float(np.abs(sourced - c).max()) > 0.0, "the field has to be moving to compare"


# --------------------------------------------------------------------------------------
# Intact, half depleted, fully depleted -- the comparison the issue asked for.

def test_intact_half_and_stripped_lawns_diverge_over_time(params):
    """Three copies of one plate at 100%, 50% and 0% food, run for five minutes.

    The two fields separate on completely different clocks and both are checked, because a
    port that wired up one and not the other would look half right for a long time:

      * oxygen is not transported, so it is the equilibrium of the standing mass and
        follows it exactly and immediately -- half the bacteria, half the deficit, to the
        bit;
      * the attractant is relaxed at `decay_attractant`, 1/0.0008 = 1250 s, so it separates
        slowly and monotonically. Over 300 s the plate total goes to 0.99618, 0.88976 and
        0.78334 of what it started at, and the attractant an animal at the origin smells
        goes to 98.90%, 88.28% and 77.65%.

    The last of those is the issue in one line: a stripped lawn used to smell like a full
    one forever, and now it smells like 78% of one after five minutes and keeps falling.
    """
    intact, half, gone = plate(params), plate(params), plate(params)
    half.food *= 0.5
    gone.food *= 0.0

    start_total = float(intact.attractant.sum())
    start_centre = float(intact.sample(intact.attractant, 0.0, 0.0))
    assert start_centre == pytest.approx(1.382137052975194, rel=1e-12)

    # ---- oxygen: exact, and immediate. One field step is enough.
    for world in (intact, half, gone):
        world.step(1.0 / FIELD_STEPS_PER_SECOND)
    assert np.array_equal(half.o2_deficit, 0.5 * intact.o2_deficit)
    assert float(gone.o2_deficit.max()) == 0.0
    assert float(intact.o2_deficit.max()) == pytest.approx(0.3, rel=1e-12)
    assert gone.oxygen(0.0, 0.0) == pytest.approx(params.world.o2_ambient)
    assert intact.oxygen(0.0, 0.0) < params.world.o2_ambient - 0.1

    # ---- the attractant: slow, ordered, and everywhere.
    for world in (intact, half, gone):
        run_fields(world, HORIZON - 1.0 / FIELD_STEPS_PER_SECOND)

    assert np.all(gone.attractant <= half.attractant)
    assert np.all(half.attractant <= intact.attractant)

    ratios = [float(w.attractant.sum() / start_total) for w in (intact, half, gone)]
    assert ratios == pytest.approx([0.9961807104, 0.8897601551, 0.7833395998], rel=1e-8)

    centres = [float(w.sample(w.attractant, 0.0, 0.0)) / start_centre
               for w in (intact, half, gone)]
    assert centres == pytest.approx([0.9890, 0.8828, 0.7765], abs=5e-4)

    # The separation is a third of the peak, not a rounding.
    assert float((intact.attractant - gone.attractant).max()) == pytest.approx(
        0.3290342228560479, rel=1e-8)
    assert float((intact.attractant - half.attractant).max()) == pytest.approx(
        0.1645171114280255, rel=1e-8)


def test_a_standing_lawn_keeps_the_field_an_unsourced_one_loses(params):
    """The other half of the fixed point, over a run rather than a step.

    An intact lawn emits exactly what decay removes, so after five minutes its field has
    only been rearranged by diffusion: the plate total is 99.618% of what it started at, and
    what is lost is what diffusion pushed over the dish rim. With no source at all -- which
    is what the model did on *every* plate before #48, eaten or not -- the same field falls
    to 78.334%. Both numbers are asserted, because "the intact one is higher" is also true
    of a model where the source is a rounding error.
    """
    intact = plate(params)
    gone = plate(params)
    gone.food *= 0.0
    start = float(intact.attractant.sum())

    run_fields(intact, HORIZON)
    run_fields(gone, HORIZON)

    assert float(intact.attractant.sum() / start) == pytest.approx(0.9961807104, rel=1e-8)
    assert float(gone.attractant.sum() / start) == pytest.approx(0.7833395998, rel=1e-8)


# --------------------------------------------------------------------------------------
# f_p itself: the footprint, the clamp, and what overlap does.

def test_patch_fractions_start_at_exactly_one_and_track_what_is_eaten(params):
    w = plate(params)
    assert w._patch_frac == [1.0, 1.0]

    # Strip the small lawn only, by zeroing the food inside its own bounding box.
    i0, i1, j0, j1 = w._patch_box[1]
    w.food[i0:i1, j0:j1] = 0.0
    w.step(1.0 / FIELD_STEPS_PER_SECOND)

    assert w._patch_frac[1] == 0.0
    # The big lawn overlaps the small one, so it loses the shared ground and only that.
    # Sharing the credit is the documented overlap rule, and the number is what pins it: a
    # patch that ignored its neighbour's ground would read exactly 1.0 here, and one that
    # claimed the whole overlap would read further from 1 than this.
    assert w._patch_frac[0] == pytest.approx(0.9651326441553544, rel=1e-12)


def _raw_fraction(world, k):
    """f_p before the clamp, so a test can tell the arithmetic from the guard."""
    return (world._patch_food(k) / world._patch_food0[k]
            if world._patch_food0[k] > 0.0 else 0.0)


def test_a_lawn_dropped_on_a_depleted_one_refills_it_without_overflowing(params):
    """Authoring a patch mid-run must not re-bless the rest of the plate as full.

    Every earlier patch's denominator grows by exactly what the new lawn adds to its
    weighted footprint, so a lawn dropped on ground that is three-quarters eaten moves that
    patch's f_p part of the way back towards 1 -- which is what putting more bacteria there
    means -- while a patch nowhere near it does not move at all. The one-line alternative,
    recomputing every denominator from the current food, would set both to exactly 1.0 and
    un-eat the plate; that is what these numbers are here to catch, and they are the raw
    ratios rather than the clamped ones so that the clamp cannot stand in for the
    arithmetic.
    """
    w = plate(params)
    w.food *= 0.25
    w.step(1.0 / FIELD_STEPS_PER_SECOND)
    assert w._patch_frac == [0.25, 0.25]

    w.add_food_patch(0.0, 0.0, 3.0, density=1.0, attractant=0.6, length_scale=6.0)
    raw = [_raw_fraction(w, k) for k in range(3)]
    assert raw == pytest.approx([0.2509175358132825, 0.6243635648649889, 1.0], rel=1e-12)
    assert w._patch_frac == pytest.approx(raw, rel=0, abs=0)


def test_food_added_behind_the_models_back_is_clamped_rather_than_amplified(params):
    """The clamp, tested where it actually bites.

    Through `add_food_patch` alone f_p cannot exceed 1 -- numerator and denominator grow by
    the same amount -- so asserting `f <= 1` after authoring a lawn is a test of nothing.
    Writing to `world.food` is a supported thing to do (every assay in tools/ and half these
    tests do it), and doubling it is the state that makes the guard load-bearing: the raw
    ratio is 2.0 and a lawn must not source twice the attractant it was authored with
    because somebody put a thumb on the food field.
    """
    w = plate(params)
    intact_o2 = w.o2_deficit.copy()
    intact_source = w._att_source.copy()

    w.food *= 2.0
    w.step(1.0 / FIELD_STEPS_PER_SECOND)

    assert [_raw_fraction(w, k) for k in range(2)] == pytest.approx([2.0, 2.0], rel=1e-12)
    assert w._patch_frac == [1.0, 1.0]
    assert np.array_equal(w.o2_deficit, intact_o2)
    assert np.array_equal(w._att_source, intact_source)


def test_a_patch_outside_the_dish_sources_nothing_rather_than_dividing_by_zero(params):
    w = World(params.world, np.random.default_rng(0))
    w.add_food_patch(200.0, 200.0, 3.0, density=1.0, attractant=1.0, length_scale=6.0)
    assert w._patch_food0 == [0.0]
    assert w._patch_frac == [0.0]
    assert float(np.abs(w.o2_deficit).max()) == 0.0
    w.step(1.0 / FIELD_STEPS_PER_SECOND)                  # and it does not raise


def test_the_plate_refuses_lawns_past_the_cap_and_counts_them(params):
    """The cap exists because a patch is a megabyte of cached field shape.

    Refused and counted rather than silently forgotten, which is the rule the runtime
    follows for eggs and now for lawns; the two implementations have to agree about how
    many lawns the dish is carrying or they are not describing the same dish.
    """
    w = World(params.world, np.random.default_rng(0))
    for k in range(MAX_FOOD_PATCHES + 3):
        w.add_food_patch(-20.0 + 3.0 * k, 0.0, 1.0, density=1.0, attractant=1.0,
                         length_scale=6.0)
    assert len(w._patch_att) == MAX_FOOD_PATCHES
    assert w.food_patches_refused == 3
    assert len([p for p in w.patches if p["kind"] == "food"]) == MAX_FOOD_PATCHES


# --------------------------------------------------------------------------------------
# End to end: an animal that eats changes what it can smell.

def test_an_animal_that_grazes_dims_its_own_lawn(params):
    """The whole loop, which is where the bug was reported from.

    One worm on a 1.2 mm lawn for 30 s. It takes 0.057295 units off the plate -- the lawn
    holds about 8.8, so f_p ends at 0.997968 -- and that has to show up in both fields.
    Small, and the smallness is the point: this is what a *tenth of a minute's* grazing does
    to the gradients, where before #48 an hour of it did exactly nothing.

    The pinned numbers are a determinism statement, not a biology one, and their history
    is worth keeping: 0.058956 until the phasmid + BAG routes went in (the lawn dents the
    oxygen field, and an animal crossing the dent feels its own downshifts through BAG);
    0.021996 until the ASE opponency was completed at AIB, whereupon eaten came nearly
    back -- an animal whose improvement signal no longer commands reversals stays over
    its own lawn. Same seed, same plate, a different animal each time. The claims below
    (the guard, and eaten showing up in every field's bookkeeping) are the test; these
    constants just pin the loop's determinism.

    The guard that it ate at all is load-bearing and was watched failing: placing the animal
    on bare agar leaves every field untouched, `assert eaten > 0.01` goes red, and without
    it every assertion below would be satisfied by an animal that never pumped.
    """
    w = World(params.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 1.2, density=1.0, attractant=1.0, length_scale=4.0)
    before_food = float(w.food.sum())
    before_o2 = w.o2_deficit.copy()

    sim = Simulation(params, seed=0, world=w, placement=(0.0, 0.0, 0.0))
    for _ in range(int(round(30.0 / params.neural.dt))):
        sim.step()

    eaten = before_food - float(w.food.sum())
    # THE GUARD. See the docstring.
    assert eaten > 0.01, "the animal ate %.6g; there is nothing to test" % eaten
    assert eaten == pytest.approx(0.057295, abs=1e-6)
    assert w._patch_frac[0] == pytest.approx(0.997968, abs=1e-6)

    # Oxygen: the deficit is shallower than it was, so the animal is standing in more
    # oxygen than a full lawn would leave it.
    assert float((before_o2 - w.o2_deficit).max()) == pytest.approx(3.0483e-04, rel=5e-3)
    assert w.oxygen(0.0, 0.0) > params.world.o2_ambient - params.world.o2_depth

    # The attractant is compared against an ungrazed control rather than against its own
    # starting value: over 30 s an intact lawn *holds* its field, so a grazed one has to sit
    # below an intact one -- which is not the same claim as sitting below where it started,
    # and it is the claim the old model failed.
    control = World(params.world, np.random.default_rng(0))
    control.add_food_patch(0.0, 0.0, 1.2, density=1.0, attractant=1.0, length_scale=4.0)
    run_fields(control, 30.0)
    assert np.all(w.attractant <= control.attractant)
    assert float((control.attractant - w.attractant).max()) > 1e-5
    assert control.oxygen(0.0, 0.0) < w.oxygen(0.0, 0.0)
