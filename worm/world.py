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

        Each request is ``(x, y, amount)``. Requests with the same neighbourhood are grouped
        and split in proportion to demand. Distinct overlapping neighbourhoods are settled
        with weighted max-min fairness: every group receives the same fraction of its demand
        until a real reachability bottleneck stops it, then less-constrained groups continue.
        The final routing minimises the largest fractional depletion of any food cell.

        This retains the proportional spatial withdrawal of :meth:`eat` for a single
        neighbourhood, maximises feasible ingestion, conserves food, and is independent of
        animal iteration order; results correspond one-for-one with the input requests.
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
        received_by_group = np.zeros(len(group_items), dtype=float)
        withdrawn = np.zeros(len(cells), dtype=float)

        # Solve disconnected patches independently. Otherwise a crowded component can set
        # a high global depletion ceiling and leave an unrelated under-demand patch free to
        # inherit the max-flow traversal order.
        for group_ids, cell_ids in _feeding_components(reachable, len(cells)):
            local_cell = {cell_i: local_i for local_i, cell_i in enumerate(cell_ids)}
            local_reachable = [tuple(local_cell[cell_i] for cell_i in reachable[group_i])
                               for group_i in group_ids]
            local_demands = demands[group_ids]
            local_capacities = capacities[cell_ids]

            if len(group_ids) == 1:
                # Exactly preserve World.eat's proportional field update. Besides avoiding
                # a directional grid bias, this makes Population([sim]).step
                # observationally equivalent to Simulation.step for feeding.
                available = float(local_capacities.sum())
                local_received = np.asarray([min(float(local_demands[0]), available)])
                local_withdrawn = (local_capacities * (local_received[0] / available)
                                   if available > 0.0
                                   else np.zeros_like(local_capacities))
            else:
                local_received = _fair_group_allocations(
                    local_reachable, local_demands, local_capacities)
                local_withdrawn = _balanced_cell_withdrawals(
                    local_reachable, local_received, local_capacities)

            received_by_group[group_ids] = local_received
            withdrawn[cell_ids] = local_withdrawn

        for (_group_cells, members), demand, received in zip(
                group_items, demands, received_by_group):
            for request_i, amount in members:
                allocations[request_i] = received * amount / demand

        for cell, amount in zip(cells, withdrawn):
            self.food[cell] = max(0.0, float(self.food[cell]) - float(amount))
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


def _add_flow_edge(graph, source: int, target: int, capacity: float):
    """Add a residual-network edge and return its mutable forward record."""
    forward = [target, len(graph[target]), float(capacity)]
    reverse = [source, len(graph[source]), 0.0]
    graph[source].append(forward)
    graph[target].append(reverse)
    return forward


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


def _route_feeding(reachable, targets: np.ndarray, capacities: np.ndarray):
    """Route exact group targets to cells, returning feasibility and cell withdrawals."""
    n_groups = len(reachable)
    n_cells = len(capacities)
    source = 0
    group0 = 1
    cell0 = group0 + n_groups
    sink = cell0 + n_cells
    graph = [[] for _ in range(sink + 1)]
    source_edges = []
    sink_edges = []

    for group_i, (group_cells, target) in enumerate(zip(reachable, targets)):
        source_edges.append(_add_flow_edge(graph, source, group0 + group_i, target))
        for cell_i in group_cells:
            _add_flow_edge(graph, group0 + group_i, cell0 + cell_i, target)
    for cell_i, capacity in enumerate(capacities):
        sink_edges.append(_add_flow_edge(graph, cell0 + cell_i, sink, capacity))

    _max_flow(graph, source, sink)
    requested = math.fsum(float(target) for target in targets)
    delivered = math.fsum(float(target) - edge[2]
                          for target, edge in zip(targets, source_edges))
    tolerance = 1e-13 * max(requested, 1e-9)
    feasible = requested - delivered <= tolerance
    withdrawn = np.asarray([
        float(capacity) - edge[2] for capacity, edge in zip(capacities, sink_edges)
    ])
    return feasible, withdrawn


def _fair_group_allocations(reachable, demands: np.ndarray,
                            capacities: np.ndarray) -> np.ndarray:
    """Return weighted max-min fair, maximum-throughput group allocations.

    Satisfaction fractions rise together. When a reachability cut prevents one or more
    groups from rising further, those groups freeze at that fraction and the remaining
    groups continue. Feasibility is a tiny bipartite max-flow problem, so this works for
    partially overlapping 3x3 feeding neighbourhoods without privileging grid order.
    """
    targets = np.zeros_like(demands)
    active = [i for i, demand in enumerate(demands) if demand > 0.0]

    while active:
        base = max(float(targets[i] / demands[i]) for i in active)

        full = targets.copy()
        full[active] = demands[active]
        if _route_feeding(reachable, full, capacities)[0]:
            targets = full
            break

        low, high = base, 1.0
        for _ in range(52):
            middle = 0.5 * (low + high)
            trial = targets.copy()
            trial[active] = demands[active] * middle
            if _route_feeding(reachable, trial, capacities)[0]:
                low = middle
            else:
                high = middle

        # Keep a tiny feasible-side margin when a floating-point cut is exactly tight. A
        # target accepted only by the feasibility tolerance can otherwise poison the next
        # progressive-filling stage and strand real capacity behind a 1e-13 over-allocation.
        fair_ratio = max(base, low - 1e-12)
        stage = targets.copy()
        stage[active] = demands[active] * fair_ratio
        targets = stage

        capacity_total = math.fsum(float(capacity) for capacity in capacities)
        if math.isclose(math.fsum(float(target) for target in stage), capacity_total,
                        rel_tol=1e-10, abs_tol=1e-14):
            # The component is completely consumed at this common ratio. No group can
            # rise. Remove the feasible-side numerical margin so allocation and withdrawal
            # close exactly, then avoid one redundant feasibility solve per active group.
            frozen_total = math.fsum(float(stage[i]) for i in range(len(stage))
                                     if i not in active)
            exact_ratio = ((capacity_total - frozen_total)
                           / math.fsum(float(demands[i]) for i in active))
            stage[active] = demands[active] * exact_ratio
            targets = stage
            break

        # A group belongs to the newly saturated cut when even a small individual increase
        # is infeasible while every peer remains at the common satisfaction fraction.
        blocked = []
        for group_i in active:
            probe = stage.copy()
            increment = max(float(demands[group_i]) * 1e-7, 1e-13)
            probe[group_i] = min(float(demands[group_i]),
                                 float(probe[group_i]) + increment)
            if probe[group_i] == stage[group_i] or not _route_feeding(
                    reachable, probe, capacities)[0]:
                blocked.append(group_i)

        if not blocked:
            # Numerical fallback: the binary search is already at the boundary, so freeze
            # the group with the least individually feasible headroom and continue.
            headroom = []
            for group_i in active:
                lo = float(stage[group_i])
                hi = float(demands[group_i])
                for _ in range(40):
                    middle = 0.5 * (lo + hi)
                    probe = stage.copy()
                    probe[group_i] = middle
                    if _route_feeding(reachable, probe, capacities)[0]:
                        lo = middle
                    else:
                        hi = middle
                headroom.append(((lo - float(stage[group_i])) / float(demands[group_i]),
                                 group_i))
            least = min(extra for extra, _group_i in headroom)
            blocked = [group_i for extra, group_i in headroom
                       if extra <= least + 1e-10]

        active = [group_i for group_i in active if group_i not in blocked]

    return targets


def _balanced_cell_withdrawals(reachable, targets: np.ndarray,
                               capacities: np.ndarray) -> np.ndarray:
    """Route targets with lexicographically minimal fractional cell depletion."""
    if math.fsum(float(target) for target in targets) <= 0.0:
        return np.zeros_like(capacities)
    if math.isclose(math.fsum(float(target) for target in targets),
                    math.fsum(float(capacity) for capacity in capacities),
                    rel_tol=1e-10, abs_tol=1e-14):
        return capacities.copy()

    ratios = np.ones_like(capacities)
    active = list(range(len(capacities)))
    ceiling = 1.0

    while active:
        zeroed = ratios.copy()
        zeroed[active] = 0.0
        if _route_feeding(reachable, targets, capacities * zeroed)[0]:
            ratios = zeroed
            break

        low, high = 0.0, ceiling
        for _ in range(52):
            middle = 0.5 * (low + high)
            trial = ratios.copy()
            trial[active] = middle
            if _route_feeding(reachable, targets, capacities * trial)[0]:
                high = middle
            else:
                low = middle

        depletion_ratio = min(ceiling, high + 1e-12)
        stage = ratios.copy()
        stage[active] = depletion_ratio
        ratios = stage

        # Freeze every cell whose individual cap cannot be lowered from this level. The
        # remaining cells then descend to the next utilization tier.
        blocked = []
        for cell_i in active:
            probe = stage.copy()
            decrement = max(float(stage[cell_i]) * 1e-7, 1e-13)
            probe[cell_i] = max(0.0, float(probe[cell_i]) - decrement)
            if probe[cell_i] == stage[cell_i] or not _route_feeding(
                    reachable, targets, capacities * probe)[0]:
                blocked.append(cell_i)

        if not blocked:
            # Numerical fallback matching the group allocator: freeze the least reducible
            # cell rather than allowing traversal order to choose a spatial winner.
            reducibility = []
            for cell_i in active:
                lo, hi = 0.0, float(stage[cell_i])
                for _ in range(40):
                    middle = 0.5 * (lo + hi)
                    probe = stage.copy()
                    probe[cell_i] = middle
                    if _route_feeding(reachable, targets, capacities * probe)[0]:
                        hi = middle
                    else:
                        lo = middle
                reducibility.append((float(stage[cell_i]) - hi, cell_i))
            least = min(reduction for reduction, _cell_i in reducibility)
            blocked = [cell_i for reduction, cell_i in reducibility
                       if reduction <= least + 1e-10]

        active = [cell_i for cell_i in active if cell_i not in blocked]
        ceiling = high

    feasible, withdrawn = _route_feeding(reachable, targets, capacities * ratios)
    if not feasible:  # defensive: full capacities were feasible when targets were chosen
        raise RuntimeError("feeding settlement became infeasible")
    return np.minimum(withdrawn, capacities)


def _max_flow(graph, source: int, sink: int) -> None:
    """Dinic max flow for the tiny (at most nine cells/animal) feeding graph."""
    eps = 1e-15
    while True:
        level = [-1] * len(graph)
        level[source] = 0
        queue = [source]
        for node in queue:
            for target, _reverse, capacity in graph[node]:
                if capacity > eps and level[target] < 0:
                    level[target] = level[node] + 1
                    queue.append(target)
        if level[sink] < 0:
            return

        next_edge = [0] * len(graph)

        def send(node: int, limit: float) -> float:
            if node == sink:
                return limit
            while next_edge[node] < len(graph[node]):
                edge = graph[node][next_edge[node]]
                target, reverse, capacity = edge
                if capacity > eps and level[target] == level[node] + 1:
                    pushed = send(target, min(limit, capacity))
                    if pushed > eps:
                        edge[2] -= pushed
                        graph[target][reverse][2] += pushed
                        return pushed
                next_edge[node] += 1
            return 0.0

        while send(source, math.inf) > eps:
            pass


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
