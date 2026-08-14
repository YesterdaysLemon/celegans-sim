"""The dish: a two-dimensional world with food, chemical gradients, heat and obstacles.

This is a standard chemotaxis plate rendered as a simulation. A 50 mm agar dish holds one
or more lawns of E. coli; the bacteria emit a diffusible attractant and consume oxygen, so
each lawn sits at the centre of both a chemical gradient and an oxygen depression. A linear
thermal gradient runs across the plate. The worm eats what it walks over, which slowly
erases the very gradient that led it there -- the reason a real animal's behaviour on a
depleting patch changes over tens of minutes.

Diffusion of a small molecule through agar is slow: a few 1e-3 mm^2/s, so a gradient takes
hours to establish over centimetres. Rather than pretend otherwise, the fields are
initialised to the steady-state profile of the diffusion-decay equation -- what the plate
looks like some hours after it was poured -- and then evolved forward with the true, slow
transport coefficients.

WHAT THE STANDING BACTERIA SOURCE, AND WHY IT SHRINKS AS THEY ARE EATEN
----------------------------------------------------------------------

`add_food_patch` writes the attractant as the steady state of ``D grad^2 c = lambda c``
away from a finite source, and the oxygen depression as the same solution with oxygen's own
length scale. **That equation is linear in the source strength.** A lawn with half its
bacteria left is half the source, so it establishes half the attractant and half the oxygen
depression with an unchanged spatial shape. That is not a new model bolted on; it is the
linearity of the solution these two fields already are.

So each patch keeps its fixed spatial *shape* -- the same ``exp(-max(d-r,0)/ls)`` skirt for
the attractant and ``o2_depth * density * exp(-max(d-r,0)/o2_length_scale)`` for oxygen
that used to be written straight into the fields and then never touched again -- and that
shape is scaled by ``f_p``, the fraction of patch p's own bacteria still on the plate.

Oxygen is not transported at all here (see `oxygen`), so it is simply rebuilt as
``sum_p f_p * shape_p`` whenever some ``f_p`` moves. The attractant diffuses and decays, so
it is *relaxed* towards the currently sourced profile rather than overwritten::

    c += field_dt * (D * lap(c) + decay * (sum_p f_p * shape_p - c))

which is the old ``c += field_dt * (D * lap(c) - decay * c)`` with a source term that puts
back exactly what the standing bacteria emit. Two properties follow, and they are the
reason for relaxing rather than overwriting:

  * with an intact lawn (every ``f_p == 1``) the source equals the field, the bracket's two
    decay terms cancel to a *bitwise* zero, and the step reduces to precisely the diffusion
    term that was there before any of this existed. Measured in
    ``tests/test_world_depletion.py``: residual 0.0e+00 over all 65,536 cells, so an
    uneaten plate behaves as it always did to the last bit.
  * on a plate with no food there are no patches, the source is all zeros, and
    ``decay * (0 - c)`` is bit-identical to ``-decay * c`` in IEEE arithmetic, so an empty
    dish steps to the same bits it did before. That is what leaves the mechanics
    conformance case and every bare-agar result untouched.

The arithmetic is written as ``decay * (source - c)`` rather than the algebraically equal
``- decay * c + decay * source``. The latter evaluates left to right as
``(D*lap - decay*c) + decay*source``, which subtracts a quantity comparable to ``D*lap``
(measured: max ``|D*lap|`` 2.281e-03 against max ``|decay*c|`` 1.280e-03 on the
conformance plate) and then adds it back. On this plate the two forms happen to agree to
0.0 -- the operands are close enough that the subtraction is exact -- but that is a
property of these numbers and not of the expression, and it stops being true as soon as a
lawn is authored with a length scale that makes the skirt flat. Factoring the two decay
terms together makes the cancellation exact by construction rather than by luck."""

from __future__ import annotations

import math

import numpy as np

from .errors import DivergentSimulation
from .params import WorldParams

# How many bacterial lawns one plate may hold. Kept in step with MAX_FOOD_PATCHES in
# wasm/assembly/index.ts, where the argument for having a ceiling at all is written out: a
# patch caches two 65,536-cell field shapes, 1,048,576 bytes, and the viewer's drop-food
# button is a caller that can be pressed arbitrarily often.
MAX_FOOD_PATCHES = 16


class World:
    def __init__(self, p: WorldParams, rng: np.random.Generator):
        self.p = p
        self.rng = rng
        g = p.grid
        self.g = g
        self.extent = p.radius
        # Cell centres, from -radius to +radius.
        self.h = 2.0 * p.radius / g
        ax = (np.arange(g) + 0.5) * self.h - p.radius
        self.ax = ax
        self.gx, self.gy = np.meshgrid(ax, ax, indexing="xy")
        self.rr = np.hypot(self.gx, self.gy)
        self.inside = self.rr <= p.radius

        self.attractant = np.zeros((g, g))
        self.repellent = np.zeros((g, g))
        self.food = np.zeros((g, g))
        # How far the local oxygen is drawn below ambient by respiring bacteria. Rebuilt
        # from the standing bacterial mass every time that mass changes -- see the module
        # docstring and `_refresh_sources` -- rather than derived pointwise from the food
        # density, for the reason in `oxygen`.
        self.o2_deficit = np.zeros((g, g))
        self.food_initial_total = 0.0
        # The sampling fast paths -- see `sample` and `_field_is_zero`.
        self._field_epoch = 0
        self._zero_memo: dict = {}
        self._zero_memo_epoch = 0
        self._valid_memo = None

        # What the standing bacteria are emitting right now: sum_p f_p * shape_p. Zero
        # until a lawn is added, which is what makes an empty dish step to the same bits it
        # did before this field existed.
        self._att_source = np.zeros((g, g))
        # Per patch, in the order the patches were added. See `add_food_patch` for what
        # each of these is and `_refresh_sources` for the update.
        self._patch_att = []     # (g, g) attractant shape, dish-masked, cached once
        self._patch_o2 = []      # (g, g) oxygen-deficit shape, dish-masked, cached once
        self._patch_box = []     # (i0, i1, j0, j1) index box bounding this patch's lawn
        self._patch_weight = []  # this patch's own deposited density over that box
        self._patch_food0 = []   # weighted food in the box when the plate was built
        self._patch_frac = []    # f_p as of the last source rebuild
        # Lawns the plate turned away, because it is already carrying MAX_FOOD_PATCHES.
        # Counted rather than assumed to be zero, on the same argument as `eggs_dropped` in
        # the runtime: the number that matters is whether any were refused, not how likely
        # it was that one would be.
        self.food_patches_refused = 0

        self.patches = []        # bookkeeping for the viewer
        self.obstacles = []      # (x, y, radius)
        # Eggs, as (x, y, t). The first thing this animal does that leaves something
        # behind: every other state in the dish is either a field or the worm itself, and
        # both forget. These do not, which is what makes them worth having on the plate
        # rather than in a counter.
        self.eggs = []

        self.t = 0.0
        self._acc = 0.0

    # ------------------------------------------------------------------------ authoring
    def add_food_patch(self, x: float, y: float, radius: float,
                       density: float = 1.0, attractant: float = 1.0,
                       length_scale: float = 9.0) -> None:
        """A bacterial lawn, with the chemical gradient it has had time to establish."""
        self._field_epoch += 1   # writes fields; see _field_is_zero
        # The same ceiling the runtime enforces, for the same reason and by the same rule:
        # a patch now carries two cached field shapes, so lawns are not free and the plate
        # refuses rather than growing without bound. Refusing here as well is what keeps the
        # two implementations describing the same dish; a reference model that quietly
        # accepted a seventeenth lawn would diverge from the runtime and blame the runtime.
        if len(self._patch_att) >= MAX_FOOD_PATCHES:
            self.food_patches_refused += 1
            return
        d = np.hypot(self.gx - x, self.gy - y)
        # Full density out to three quarters of the nominal radius, then a smooth edge.
        # The arguments to _smoothstep were transposed here, which inverted every lawn in
        # the dish: food density was 0 at the centre of a patch and 1 everywhere *outside*
        # it, out to the dish wall. A 9 mm lawn sampled 0.002 at its own centre while the
        # dish held 26,000 units of food. Oxygen is derived from this field, so the O2
        # depression was inverted too, and the aerotaxis assay was scoring an animal
        # against a gradient that pointed the wrong way.
        lawn = density * _smoothstep(radius * 0.75, radius, d)
        # What every existing patch's weighted footprint holds *before* this lawn lands, so
        # that the new bacteria can be added to their denominators rather than silently
        # re-blessing a half-eaten plate as full. See the note on rebasing below.
        before = [self._patch_food(k) for k in range(len(self._patch_att))]
        self.food += lawn
        self.patches.append({"x": x, "y": y, "r": radius, "kind": "food"})
        self.food *= self.inside
        # Steady state of D grad^2 c = lambda c away from a finite source, which decays
        # exponentially with a length sqrt(D/lambda). Written directly rather than relaxed
        # numerically, because relaxing it would take hours of simulated time.
        #
        # Cached, not recomputed. The shape is fixed for the life of the patch and only its
        # scalar amplitude moves, so 65,536 `exp` calls per patch per field step -- 50 field
        # steps a second, for the life of the run -- would buy nothing. Two grids of 65,536
        # f64 is 1,048,576 bytes a patch, which is the price of this design and is stated
        # again at MAX_FOOD_PATCHES in the runtime.
        att_shape = (attractant
                     * np.exp(-np.maximum(d - radius, 0.0) / length_scale)) * self.inside
        # Oxygen gets the same treatment, and for the same reason. Bacteria consume it and
        # it diffuses back in from the air, so a lawn sits at the centre of an oxygen
        # depression with a skirt, exactly as it sits at the centre of a chemical gradient.
        # Deriving it pointwise from the food density instead -- which is what this did --
        # makes it a step function at the lawn edge: ambient everywhere outside, with no
        # gradient anywhere for an animal to follow. Measured, that left aerotaxis with
        # nothing to work on: the oxygen circuit biases turning correctly, 3.67 reversals a
        # minute at ambient against 2.67 in a lawn, and never got the chance to.
        o2_shape = (self.p.o2_depth * density
                    * np.exp(-np.maximum(d - radius, 0.0)
                             / self.p.o2_length_scale)) * self.inside
        self.attractant += att_shape
        self.attractant *= self.inside

        # ---- the patch's own footprint, and what "its own food" means where lawns overlap
        #
        # f_p is a weighted average of how much of this patch's footprint is left, with each
        # cell weighted by the density THIS patch deposited there:
        #
        #     f_p = sum_c lawn_p(c) * food(c) / sum_c lawn_p(c) * food_0(c)
        #
        # Two decisions are buried in that, and both matter.
        #
        # OVERLAP. `food` is one number per cell and the plate has no way to say which
        # lawn a gram of it came from, so where two patches overlap they share credit for
        # what is there: eating in the overlap lowers both patches' f_p, in proportion to
        # what each of them put in the cell. Attributing the cell to one patch would need a
        # third cached grid per patch and would still be a guess, because `eat` withdraws
        # from a cell proportionally and cannot distinguish them either. Sharing is also the
        # conservative direction for the bug this fixes -- a stripped cell dims every lawn
        # that claims it, so nothing keeps smelling of food that is not there.
        #
        # WEIGHTED, NOT A HARD DISC. The obvious footprint is "cells with d < radius", but
        # that is a boolean, and the Python and the runtime compute d as `np.hypot` and
        # `Math.sqrt(dx*dx+dy*dy)` respectively. Those can differ in the last bit, and a
        # boolean straddling the edge would then flip a whole cell in or out of one side's
        # denominator -- a 1e-3 divergence out of a 1e-16 difference. Weighting by the lawn
        # profile makes the same last-bit difference worth about 1e-32, because the profile
        # is already ~0 at the rim it would disagree about.
        box = _bounds_of(lawn > 0.0)
        self._patch_att.append(att_shape)
        self._patch_o2.append(o2_shape)
        self._patch_box.append(box)
        self._patch_weight.append(lawn[box[0]:box[1], box[2]:box[3]].copy())
        self._patch_food0.append(0.0)
        self._patch_frac.append(1.0)

        # Rebasing. Every earlier patch's denominator grows by exactly what this lawn added
        # to its weighted footprint -- measured as the difference of two identical sums, so
        # that on a plate where nothing has been eaten yet the numerator and denominator end
        # up bit-identical and f_p is exactly 1.0. (Setting the denominators to the current
        # weighted food instead is one line shorter and wrong: dropping a fresh lawn from
        # the viewer would reset every other patch to "full" and un-eat the plate.)
        for k, was in enumerate(before):
            self._patch_food0[k] += self._patch_food(k) - was
        self._patch_food0[-1] = self._patch_food(len(self._patch_att) - 1)

        for k in range(len(self._patch_att)):
            self._patch_frac[k] = self._patch_fraction(k)
        self._rebuild_sources()
        self.food_initial_total = float(self.food.sum())

    # ------------------------------------------------------- standing bacterial mass
    def _patch_food(self, k: int) -> float:
        """Food in patch k's footprint, weighted by what patch k deposited in each cell."""
        i0, i1, j0, j1 = self._patch_box[k]
        return float((self.food[i0:i1, j0:j1] * self._patch_weight[k]).sum())

    def _patch_fraction(self, k: int) -> float:
        """f_p: how much of patch k's own bacteria is left, clamped to [0, 1].

        Neither bound is reachable through `add_food_patch` and `eat` alone -- authoring a
        lawn grows numerator and denominator by the same amount, and eating only ever lowers
        the numerator. They are here for a caller that writes to `world.food` directly,
        which every assay in tools/ and half of tests/ is entitled to do: a lawn must not
        source twice what it was authored with because somebody doubled the food field, and
        a source term that went negative would pump the attractant down through zero rather
        than fail. ``tests/test_world_depletion.py`` drives the upper bound deliberately,
        because a clamp only tested where it cannot bite is not tested at all.
        """
        denominator = self._patch_food0[k]
        if denominator <= 0.0:
            # A patch whose footprint never held any food -- authored entirely outside the
            # dish, or at zero density. It sources nothing, which is what it is.
            return 0.0
        fraction = self._patch_food(k) / denominator
        return 0.0 if fraction < 0.0 else (1.0 if fraction > 1.0 else fraction)

    def _rebuild_sources(self) -> None:
        """Rebuild sum_p f_p * shape_p for the attractant source and the oxygen deficit.

        Accumulated in patch order, one array operation per patch, because the runtime
        accumulates the same two sums cell by cell in the same order and the two have to
        agree bit for bit.
        """
        self._field_epoch += 1   # writes fields; see _field_is_zero
        source = np.zeros((self.g, self.g))
        deficit = np.zeros((self.g, self.g))
        for fraction, att, o2 in zip(self._patch_frac, self._patch_att, self._patch_o2):
            source += fraction * att
            deficit += fraction * o2
        self._att_source = source
        self.o2_deficit = deficit

    def _refresh_sources(self) -> None:
        """Recompute every f_p, and rebuild the sourced fields only if one moved.

        The rebuild is two multiply-accumulates over 65,536 cells per patch and the f_p
        themselves are a weighted sum over the patch's bounding box, which for the 5 mm lawn
        in the conformance plate is 812 cells against the grid's 65,536. Recomputing f_p
        every field step is therefore cheap and, more to the point, is a pure function of
        the food field: no dirty flag to keep in step between the two implementations, and
        no way for one of them to notice a withdrawal the other missed. The expensive half
        is skipped when nothing was eaten, which is most field steps -- an animal pumping at
        4 Hz eats on 4 of the 50 field steps in a second. Measured in the runtime, where the
        cost actually matters: 0.24 ms a lawn per rebuild against 5.43 ms a lawn to
        recompute the shapes with `exp`, and sixteen lawns cost what none do once the guard
        is in. The figures and the method are in `refreshSources` in
        wasm/assembly/index.ts.
        """
        if not self._patch_att:
            return
        changed = False
        for k in range(len(self._patch_att)):
            fraction = self._patch_fraction(k)
            if fraction != self._patch_frac[k]:
                self._patch_frac[k] = fraction
                changed = True
        if changed:
            self._rebuild_sources()

    def add_repellent_source(self, x: float, y: float, strength: float = 1.0,
                             length_scale: float = 6.0) -> None:
        """A drop of a noxious chemical -- copper, SDS, high osmolarity."""
        d = np.hypot(self.gx - x, self.gy - y)
        self.repellent += strength * np.exp(-d / length_scale)
        self.repellent *= self.inside
        self.patches.append({"x": x, "y": y, "r": length_scale * 0.4, "kind": "repellent"})

    def lay_egg(self, x: float, y: float) -> None:
        """Deposit an egg where the vulva is. The dish keeps it; nothing removes it."""
        self.eggs.append((float(x), float(y), float(self.t)))

    def add_obstacle(self, x: float, y: float, radius: float) -> None:
        self.obstacles.append((float(x), float(y), float(radius)))

    # -------------------------------------------------------------------------- fields
    def temperature(self, x, y):
        """Linear thermal gradient across the plate, cold at -x and warm at +x."""
        self._validate_coordinates(x, y)
        f = (np.asarray(x) + self.extent) / (2.0 * self.extent)
        return self.p.temp_cold + (self.p.temp_warm - self.p.temp_cold) * np.clip(f, 0, 1)

    def oxygen(self, x, y):
        """Fractional O2. Ambient is 21%; a dense lawn respires it down towards 6%.

        C. elegans is not indifferent to this: it avoids 21% and prefers 5-12%, which is
        one of the reasons wild isolates gather at the thick border of a lawn rather than
        in the middle of it. The border is the point -- the animal has to be able to find
        it from outside, which needs a gradient rather than a cliff.
        """
        return self.p.o2_ambient - np.clip(
            self.sample(self.o2_deficit, x, y), 0.0, self.p.o2_ambient - 0.01)

    def sample(self, field: np.ndarray, x, y):
        """Bilinear sample of a grid field at world coordinates.

        Fast path: a field that is identically zero bilinearly interpolates to exactly
        0.0 at every point, so the interpolation is skipped for fields the zero-registry
        knows are empty (see `_field_is_zero`). Validation still runs -- a divergent
        animal must raise whether or not the dish is empty. In the bare worlds every
        gait sweep uses, this removes most of the sensory sampling cost; measured on the
        profile that motivated it, `sample` was a fifth of the whole step. The returned
        value and type are unchanged: a numpy float64 zero for scalar coordinates, a
        zero array of the broadcast shape otherwise -- both bit-identical to what the
        interpolation of a zero field returns.
        """
        self._validate_coordinates(x, y)
        if self._field_is_zero(field):
            xa = np.asarray(x, dtype=float)
            ya = np.asarray(y, dtype=float)
            shape = np.broadcast_shapes(xa.shape, ya.shape)
            return np.float64(0.0) if shape == () else np.zeros(shape)
        fx = (np.asarray(x, dtype=float) + self.extent) / self.h - 0.5
        fy = (np.asarray(y, dtype=float) + self.extent) / self.h - 0.5
        x0 = np.clip(np.floor(fx).astype(int), 0, self.g - 2)
        y0 = np.clip(np.floor(fy).astype(int), 0, self.g - 2)
        tx = np.clip(fx - x0, 0.0, 1.0)
        ty = np.clip(fy - y0, 0.0, 1.0)
        f00 = field[y0, x0]
        f10 = field[y0, x0 + 1]
        f01 = field[y0 + 1, x0]
        f11 = field[y0 + 1, x0 + 1]
        return ((f00 * (1 - tx) + f10 * tx) * (1 - ty)
                + (f01 * (1 - tx) + f11 * tx) * ty)

    def eat(self, x: float, y: float, amount: float) -> float:
        """Remove `amount` of food from around (x, y). Returns how much was actually there.

        The return value is the point of this, not a courtesy: it is what the caller is
        allowed to have. ``Pharynx.finish_step`` adds *this* to the lumen rather than what
        it asked for, which is what stops an animal ingesting food the plate never had.
        (Writes the food field; the epoch bump for `_field_is_zero` is below the
        docstring.)

        `amount` is a total, withdrawn proportionally to what is present in the
        neighbourhood. It used to be subtracted from every cell of the 3x3 patch
        independently, which removed up to nine times the requested amount and stripped
        the ground under the animal in about two seconds -- so "on food" was a condition
        that decayed away during any measurement longer than a few seconds, and since
        oxygen is derived from this field the animal was also eating its own O2 gradient.
        """
        amount = float(amount)
        if not np.isfinite(amount) or amount < 0.0:
            raise ValueError("feeding amount must be finite and >= 0 (got %r)" % amount)
        lo_i, hi_i, lo_j, hi_j = self._feeding_bounds(float(x), float(y))
        patch = self.food[lo_i:hi_i, lo_j:hi_j]
        available = float(patch.sum())
        if available <= 0.0:
            return 0.0
        self._field_epoch += 1   # about to write the food field; see _field_is_zero
        take = min(amount, available)
        patch *= 1.0 - take / available
        return take

    def eat_batch(self, requests) -> np.ndarray:
        """Settle simultaneous feeding requests against one food-field snapshot.

        Each request is ``(x, y, amount)``. Requests reaching exactly the same food cells
        are grouped; a group that shares no cell with any other group keeps the proportional
        withdrawal :meth:`eat` performs, which is what makes ``Population([sim]).step``
        observationally equivalent to ``Simulation.step``. Overlapping groups are settled by
        the iterated proportional claim in :func:`_settle_by_claim`.

        THIS RULE CHANGED, AND IT CHANGED TOWARDS THE RUNTIME. It used to be weighted
        max-min fairness over a max-flow, with the final routing chosen to minimise the
        largest fractional depletion of any cell. That maximised collective intake and
        equalised depletion, and the WebAssembly runtime -- which has to settle this at
        2 kHz in a browser and cannot run a linear program -- did something else: every
        animal grazes its own neighbourhood proportionally, all at once, and a cell reached
        by two animals is simply grazed twice. The two agreed on the allocations in every
        configuration #71 checked and disagreed about *which cells the food came out of*,
        by 7.456e-04 on the conformance plate, which the multi-animal conformance case
        found the first time it ran. See wasm/conform.mjs.

        The model moved rather than the runtime, so what is given up here is real and worth
        naming:

        * **maximum throughput.** Two animals over one shared cell and one private cell,
          each wanting 1.0 of the 2.0 present, used to take all 2.0; they now take
          1.666666667 and leave 0.333333333 in the private cell of an animal that is
          already full. No central planner routes one animal off the contested ground.
        * **weighted max-min fairness.** Same pair over 1.0 shared and 0.25 private used to
          split 0.625/0.625; they now take 0.694444444/0.555555556, in proportion to the
          claim each makes rather than to a fairness criterion.
        * **minimal largest fractional depletion.** Shared ground is now grazed harder than
          private ground -- 0.999068053 against 0.999534027 on the two-animal case -- which
          is what it means for two animals to be eating the same bacteria.

        What survives, and is tested: conservation, independence of request order,
        invariance to cell and group relabeling, per-request correspondence with the input,
        and single-neighbourhood equivalence with :meth:`eat`.
        """
        self._field_epoch += 1   # writes the food field; see _field_is_zero
        requests = list(requests)
        allocations = np.zeros(len(requests), dtype=float)
        groups = {}

        for request_i, (x, y, amount) in enumerate(requests):
            amount = float(amount)
            if not np.isfinite(amount) or amount < 0.0:
                raise ValueError("feeding amount must be finite and >= 0 (got %r)" % amount)
            lo_i, hi_i, lo_j, hi_j = self._feeding_bounds(float(x), float(y))
            patch = self.food[lo_i:hi_i, lo_j:hi_j]
            cells = tuple(
                (lo_i + int(local_i), lo_j + int(local_j))
                for local_i, local_j in np.argwhere(patch > 0.0)
            )
            if amount > 0.0 and cells:
                groups.setdefault(cells, []).append((request_i, amount))

        if not groups:
            return allocations

        group_items = sorted(groups.items(), key=lambda item: item[0])
        cells = sorted({cell for reachable, _ in group_items for cell in reachable})
        cell_index = {cell: i for i, cell in enumerate(cells)}
        reachable = [tuple(cell_index[cell] for cell in group_cells)
                     for group_cells, _members in group_items]
        demands = np.asarray([
            math.fsum(amount for _request_i, amount in members)
            for _group_cells, members in group_items
        ], dtype=float)
        capacities = np.asarray([float(self.food[cell]) for cell in cells], dtype=float)
        withdrawn = np.zeros(len(cells), dtype=float)
        # What the claim settlement leaves behind, written straight through rather than as a
        # withdrawal. `have - have * fraction` and `have * (1 - fraction)` are not the same
        # double, and this is the one place the change exists to remove a last-bit
        # difference, so the cell value the runtime computes is the cell value stored.
        settled = np.full(len(cells), np.nan)

        # Disconnected patches are solved independently. The runtime does not do this
        # explicitly and does not need to: its claim on a cell only counts animals that
        # reach the cell, so a component is already independent of every other. Here it
        # additionally selects the single-group path below.
        for group_ids, cell_ids in _feeding_components(reachable, len(cells)):
            local_cell = {cell_i: local_i for local_i, cell_i in enumerate(cell_ids)}
            local_capacities = capacities[cell_ids]

            if len(group_ids) == 1:
                # Exactly preserve World.eat's proportional field update. Besides avoiding
                # a directional grid bias, this makes Population([sim]).step
                # observationally equivalent to Simulation.step for feeding.
                #
                # For ONE request this is also exactly what _settle_by_claim computes: the
                # claim is min(1, want/avail) and the cell keeps have * (1 - claim), which
                # is the line above written the other way round. For several requests over
                # one neighbourhood the two differ only when their combined demand exceeds
                # what is there -- proportional-to-demand here, proportional-to-claim in the
                # runtime, measured 2.0e-02 apart on [0.4, 0.2] against 0.3 available. That
                # residue is left rather than removed because this path is what pins the
                # single-animal equivalence above.
                group_i = group_ids[0]
                available = float(local_capacities.sum())
                demand = float(demands[group_i])
                received = min(demand, available)
                withdrawn[cell_ids] = (local_capacities * (received / available)
                                       if available > 0.0
                                       else np.zeros_like(local_capacities))
                for request_i, amount in group_items[group_i][1]:
                    allocations[request_i] = min(float(amount), received * amount / demand)
                continue

            # Per REQUEST, not per group, and in the request order the runtime walks its
            # worms array in. An animal whose own demand exceeds its whole neighbourhood
            # claims all of it, and the claim rule notices that where a per-group demand
            # would have averaged it away.
            members = sorted(
                (request_i, float(amount),
                 tuple(local_cell[cell_i] for cell_i in reachable[group_i]))
                for group_i in group_ids
                for request_i, amount in group_items[group_i][1]
            )
            local_received, local_left = _settle_by_claim(
                [member_cells for _request_i, _amount, member_cells in members],
                [amount for _request_i, amount, _member_cells in members],
                local_capacities,
            )
            for (request_i, amount, _member_cells), received in zip(members, local_received):
                allocations[request_i] = min(amount, received)
            settled[cell_ids] = local_left

        for cell_i, cell in enumerate(cells):
            left = settled[cell_i]
            if math.isnan(left):
                left = float(self.food[cell]) - float(withdrawn[cell_i])
            self.food[cell] = max(0.0, float(left))
        return allocations

    def _feeding_bounds(self, x: float, y: float):
        self._validate_coordinates(x, y)
        i = int(np.clip((y + self.extent) / self.h, 0, self.g - 1))
        j = int(np.clip((x + self.extent) / self.h, 0, self.g - 1))
        return (max(0, i - 1), min(self.g, i + 2),
                max(0, j - 1), min(self.g, j + 2))

    def _field_is_zero(self, field: np.ndarray) -> bool:
        """Is this field identically zero right now? Cached per field per epoch.

        The epoch counter is bumped by every method that writes a field --
        `add_food_patch`, `_rebuild_sources`, `eat`, `eat_batch`, `step` -- so a stale
        answer is impossible as long as that list stays complete. **A new field-writing
        method must bump `_field_epoch`**; the failure mode of forgetting is an empty
        reading from a non-empty dish, which the sensory assays would not stay quiet
        about, but the rule is cheaper than the debugging. The memo holds a reference to
        the array it classified, both so `id()` cannot be recycled and so a rebound
        field (a fresh array at the same attribute) misses the memo and is re-tested.
        """
        if self._zero_memo_epoch != self._field_epoch:
            # Clear rather than filter: rebound fields would otherwise accumulate stale
            # array references (and their memory) for as long as the world lives.
            self._zero_memo.clear()
            self._zero_memo_epoch = self._field_epoch
        key = id(field)
        hit = self._zero_memo.get(key)
        if hit is not None and hit[1] is field:
            return hit[0]
        is_zero = not field.any()
        self._zero_memo[key] = (is_zero, field)
        return is_zero

    def _validate_coordinates(self, x, y) -> None:
        """Fail rather than laundering a divergent animal into a rim-cell reading.

        Scalar coordinates are memoised: the senses sample several fields at the same
        nose point within one step, and a point that was finite and inside the dish a
        microsecond ago still is. The memo is (x, y) of the last scalar pair validated,
        compared exactly, so it can never accept a point the full check would reject.
        """
        try:
            key = (float(x), float(y))
        except (TypeError, ValueError):
            key = None
        if key is not None and key == self._valid_memo:
            return
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise DivergentSimulation("world coordinates are not finite")
        radius = np.hypot(x, y)
        if np.any(radius > self.extent):
            raise DivergentSimulation(
                "animal left the dish (radius %.6g mm > %.6g mm)"
                % (float(np.max(radius)), self.extent))
        if key is not None:
            self._valid_memo = key

    def step(self, dt: float) -> None:
        """Advance the diffusing fields, in chunks of the field timestep."""
        self.t += dt
        self._acc += dt
        while self._acc >= self.p.field_dt:
            self._acc -= self.p.field_dt
            fdt = self.p.field_dt
            self._field_epoch += 1   # rebinding fields below; see _field_is_zero
            # What the standing bacteria are emitting *this* step, before anything reads
            # it. Rebuilding after the relaxation instead would leave the attractant one
            # field step behind the oxygen, for no reason anyone could defend.
            self._refresh_sources()
            self.attractant = self._relax(
                self.attractant, self.p.diffusion_attractant, self.p.decay_attractant, fdt,
                self._att_source)
            self.repellent = self._diffuse(
                self.repellent, self.p.diffusion_repellent, self.p.decay_attractant, fdt)

    def _diffuse(self, c: np.ndarray, D: float, decay: float, dt: float) -> np.ndarray:
        if D <= 0.0:
            return c * (1.0 - decay * dt)
        lap = (np.roll(c, 1, 0) + np.roll(c, -1, 0)
               + np.roll(c, 1, 1) + np.roll(c, -1, 1) - 4.0 * c) / (self.h * self.h)
        out = c + dt * (D * lap - decay * c)
        np.clip(out, 0.0, None, out=out)
        out *= self.inside
        return out

    def _relax(self, c: np.ndarray, D: float, decay: float, dt: float,
               source: np.ndarray) -> np.ndarray:
        """`_diffuse` with a standing source: relax c towards `source` as well as spread it.

        Deliberately without `_diffuse`'s `D <= 0` shortcut. That branch skips the clip and
        the dish mask as well as the Laplacian, which is defensible for a field with no
        source and not for one being driven towards a profile that is masked; and the
        runtime's diffusion coefficient is a compile-time constant that is not zero, so
        taking the branch here would be a divergence with nothing on the other side of it.
        At D == 0 this still does the right thing, one wasted Laplacian later.
        """
        lap = (np.roll(c, 1, 0) + np.roll(c, -1, 0)
               + np.roll(c, 1, 1) + np.roll(c, -1, 1) - 4.0 * c) / (self.h * self.h)
        # `decay * (source - c)`, not `- decay * c + decay * source`: see the module
        # docstring. With an intact lawn source is c, the term is a bitwise zero, and this
        # reduces to `c + dt * D * lap` -- the old expression's diffusion, unrounded.
        out = c + dt * (D * lap + decay * (source - c))
        np.clip(out, 0.0, None, out=out)
        out *= self.inside
        return out

    # ------------------------------------------------------------------------- contact
    def contact_force(self, nodes: np.ndarray, stiffness: float = 40.0) -> np.ndarray:
        """Repulsion from the dish wall and any obstacles, as a force on each body node."""
        f = np.zeros_like(nodes)
        r = np.hypot(nodes[:, 0], nodes[:, 1])
        over = r - (self.extent - 0.05)
        hit = over > 0
        if np.any(hit):
            direction = nodes[hit] / np.maximum(r[hit, None], 1e-9)
            f[hit] -= stiffness * over[hit, None] * direction
        for ox, oy, orad in self.obstacles:
            d = nodes - np.array([ox, oy])
            dist = np.hypot(d[:, 0], d[:, 1])
            pen = (orad + 0.03) - dist
            hit = pen > 0
            if np.any(hit):
                direction = d[hit] / np.maximum(dist[hit, None], 1e-9)
                f[hit] += stiffness * pen[hit, None] * direction
        return f


def _feeding_components(reachable, n_cells: int):
    """Return connected group/cell index components in deterministic order."""
    cell_groups = [[] for _ in range(n_cells)]
    for group_i, group_cells in enumerate(reachable):
        for cell_i in group_cells:
            cell_groups[cell_i].append(group_i)

    unseen = set(range(len(reachable)))
    components = []
    while unseen:
        seed = min(unseen)
        group_ids = set()
        cell_ids = set()
        pending_groups = [seed]
        while pending_groups:
            group_i = pending_groups.pop()
            if group_i in group_ids:
                continue
            group_ids.add(group_i)
            unseen.discard(group_i)
            for cell_i in reachable[group_i]:
                if cell_i in cell_ids:
                    continue
                cell_ids.add(cell_i)
                pending_groups.extend(cell_groups[cell_i])
        components.append((sorted(group_ids), sorted(cell_ids)))
    return components


def _settle_by_claim(reachable, demands, capacities, passes: int = 8):
    """Iterated proportional claim -- a transcription of the runtime's ``settleFeeding``.

    This is `wasm/assembly/index.ts::settleFeeding`, line for line, because that is the
    point of it: the model and the port settle contested feeding by running the same
    process rather than by two different processes being checked against each other and
    hoped to agree. They were not agreeing. See :meth:`World.eat_batch`.

    Per pass, an animal wanting ``want`` from a neighbourhood holding ``avail`` claims the
    fraction ``r = min(1, want / avail)`` of every cell it reaches. A cell's total claim is
    the sum of ``r`` over the animals reaching it; where that exceeds one every withdrawal
    from the cell is scaled by its reciprocal, so the cell loses ``have * min(1, claimed)``
    and never more than it has. An animal gains ``have * r / max(1, claimed)`` from each of
    its cells. One pass is order-independent and conservative but under-serves an animal
    blocked on a shared cell while it still has untouched cells of its own, so the pass
    repeats on the remainder until nothing moves.

    Conservation is exact rather than approximate: where ``claimed <= 1`` the animals' gains
    from a cell sum to ``have * claimed`` and the cell loses ``have * claimed``; where it
    exceeds one they sum to ``have`` and the cell loses ``have``.

    Eight passes is far more than any real configuration needs -- the loop leaves as soon as
    a pass moves nothing, and the bound only stops a pathological field spinning. Both the
    bound and the 1e-18 floor are the runtime's, and changing either here would silently
    reintroduce the divergence this replaced.

    ``reachable`` is per REQUEST, in the order the runtime walks its worms array, and the
    cells within each entry are in the row-major order the runtime scans a 3x3 window in.
    Both orders are load-bearing: they are what make the floating-point result identical
    rather than merely equal to twelve decimal places.

    Returns ``(received, left)`` -- what each request got, and what each cell has left.
    """
    n = len(demands)
    left = [float(capacity) for capacity in capacities]
    received = [0.0] * n
    remaining = [float(demand) for demand in demands]

    for _pass in range(passes):
        ratio = [0.0] * n
        for k in range(n):
            want = remaining[k]
            if want <= 0.0:
                continue
            available = 0.0
            for cell_i in reachable[k]:
                available += left[cell_i]
            if available > 0.0:
                ratio[k] = want / available if want < available else 1.0

        # Summed in animal order, which is the order the runtime's claimOn accumulates in.
        claimed = [0.0] * len(left)
        claimants = [False] * len(left)
        for k in range(n):
            if ratio[k] <= 0.0:
                continue
            for cell_i in reachable[k]:
                claimed[cell_i] += ratio[k]
                claimants[cell_i] = True

        moved = 0.0
        for k in range(n):
            if ratio[k] <= 0.0:
                continue
            got = 0.0
            for cell_i in reachable[k]:
                have = left[cell_i]
                if have <= 0.0:
                    continue
                share = claimed[cell_i]
                got += have * ratio[k] / (share if share > 1.0 else 1.0)
            received[k] += got
            remaining[k] -= got
            moved += got

        # Then take it off the plate. A cell loses `have * min(1, claimed)` however many
        # animals are on it, so the new value depends only on the cell -- but it must be
        # written exactly once, or the second writer would scale an already-reduced value.
        for cell_i, has_claimant in enumerate(claimants):
            if not has_claimant:
                continue
            have = left[cell_i]
            if have <= 0.0:
                continue
            share = claimed[cell_i]
            spare = have * (1.0 - (1.0 if share > 1.0 else share))
            left[cell_i] = spare if spare > 0.0 else 0.0

        if moved <= 1e-18:
            break

    return received, left


def _bounds_of(mask: np.ndarray) -> tuple:
    """Tightest (i0, i1, j0, j1) half-open index box containing every True cell.

    Empty in, empty out: a patch authored entirely outside the dish gets a zero-area box,
    a zero-length weight array, a denominator of 0 and therefore f_p = 0. It sources
    nothing, which is right, and it does it without a special case anywhere else.
    """
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return (0, 0, 0, 0)
    return (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """1 inside edge0, falling smoothly to 0 by edge1 (edge1 may be either side)."""
    t = np.clip((x - edge0) / (edge1 - edge0 + 1e-12), 0.0, 1.0)
    return 1.0 - t * t * (3.0 - 2.0 * t)


def default_world(p: WorldParams, rng: np.random.Generator) -> World:
    """A plate with a large lawn off to one side and two smaller ones, plus a few pillars.

    Enough structure that the animal has something to find, lose, and search for again.
    """
    w = World(p, rng)
    w.add_food_patch(9.0, 5.0, 4.5, density=1.0, attractant=1.0, length_scale=8.0)
    w.add_food_patch(-11.0, -8.0, 3.0, density=0.8, attractant=0.7, length_scale=6.5)
    w.add_food_patch(-6.0, 13.0, 2.0, density=0.6, attractant=0.5, length_scale=5.0)
    w.add_repellent_source(2.0, -14.0, strength=0.9, length_scale=5.0)
    for x, y, r in [(-2.0, 2.0, 1.1), (4.0, -6.0, 0.9), (-9.0, 6.0, 0.8), (13.0, -3.0, 1.0)]:
        w.add_obstacle(x, y, r)
    return w
