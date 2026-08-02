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
"""

from __future__ import annotations

import math

import numpy as np

from .errors import DivergentSimulation
from .params import WorldParams


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
        # How far the local oxygen is drawn below ambient by respiring bacteria. Held as
        # its own field rather than derived from the food, for the reason in `oxygen`.
        self.o2_deficit = np.zeros((g, g))
        self.food_initial_total = 0.0

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
        d = np.hypot(self.gx - x, self.gy - y)
        # Full density out to three quarters of the nominal radius, then a smooth edge.
        # The arguments to _smoothstep were transposed here, which inverted every lawn in
        # the dish: food density was 0 at the centre of a patch and 1 everywhere *outside*
        # it, out to the dish wall. A 9 mm lawn sampled 0.002 at its own centre while the
        # dish held 26,000 units of food. Oxygen is derived from this field, so the O2
        # depression was inverted too, and the aerotaxis assay was scoring an animal
        # against a gradient that pointed the wrong way.
        lawn = density * _smoothstep(radius * 0.75, radius, d)
        self.food += lawn
        # Steady state of D grad^2 c = lambda c away from a finite source, which decays
        # exponentially with a length sqrt(D/lambda). Written directly rather than relaxed
        # numerically, because relaxing it would take hours of simulated time.
        self.attractant += attractant * np.exp(-np.maximum(d - radius, 0.0) / length_scale)
        # Oxygen gets the same treatment, and for the same reason. Bacteria consume it and
        # it diffuses back in from the air, so a lawn sits at the centre of an oxygen
        # depression with a skirt, exactly as it sits at the centre of a chemical gradient.
        # Deriving it pointwise from the food density instead -- which is what this did --
        # makes it a step function at the lawn edge: ambient everywhere outside, with no
        # gradient anywhere for an animal to follow. Measured, that left aerotaxis with
        # nothing to work on: the oxygen circuit biases turning correctly, 3.67 reversals a
        # minute at ambient against 2.67 in a lawn, and never got the chance to.
        self.o2_deficit += (self.p.o2_depth * density
                            * np.exp(-np.maximum(d - radius, 0.0) / self.p.o2_length_scale))
        self.o2_deficit *= self.inside
        self.patches.append({"x": x, "y": y, "r": radius, "kind": "food"})
        self.food *= self.inside
        self.attractant *= self.inside
        self.food_initial_total = float(self.food.sum())

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
        """Bilinear sample of a grid field at world coordinates."""
        self._validate_coordinates(x, y)
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

    def _validate_coordinates(self, x, y) -> None:
        """Fail rather than laundering a divergent animal into a rim-cell reading."""
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise DivergentSimulation("world coordinates are not finite")
        radius = np.hypot(x, y)
        if np.any(radius > self.extent):
            raise DivergentSimulation(
                "animal left the dish (radius %.6g mm > %.6g mm)"
                % (float(np.max(radius)), self.extent))

    def step(self, dt: float) -> None:
        """Advance the diffusing fields, in chunks of the field timestep."""
        self.t += dt
        self._acc += dt
        while self._acc >= self.p.field_dt:
            self._acc -= self.p.field_dt
            fdt = self.p.field_dt
            self.attractant = self._diffuse(
                self.attractant, self.p.diffusion_attractant, self.p.decay_attractant, fdt)
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
