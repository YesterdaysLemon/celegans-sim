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
        """Remove `amount` of food from around (x, y). Returns how much was ingested.

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

        Each request is ``(x, y, amount)``.  A small bipartite max-flow settlement lets a
        flexible animal use another cell before taking food that only a constrained animal
        can reach. Requests with the same neighbourhood are grouped and split in proportion
        to demand. This maximises feasible ingestion, conserves food, and is independent of
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
        source = 0
        group0 = 1
        cell0 = group0 + len(group_items)
        sink = cell0 + len(cells)
        graph = [[] for _ in range(sink + 1)]
        source_edges = []
        sink_edges = []

        for group_i, (reachable, members) in enumerate(group_items):
            demand = math.fsum(amount for _, amount in members)
            source_edges.append(_add_flow_edge(graph, source, group0 + group_i, demand))
            for cell in reachable:
                _add_flow_edge(graph, group0 + group_i, cell0 + cell_index[cell], demand)
        for cell_i, cell in enumerate(cells):
            sink_edges.append(_add_flow_edge(
                graph, cell0 + cell_i, sink, float(self.food[cell])))

        _max_flow(graph, source, sink)
        for (_, members), edge in zip(group_items, source_edges):
            demand = math.fsum(amount for _, amount in members)
            received = demand - edge[2]
            for request_i, amount in members:
                allocations[request_i] = received * amount / demand

        for cell, edge in zip(cells, sink_edges):
            withdrawn = float(self.food[cell]) - edge[2]
            self.food[cell] = max(0.0, float(self.food[cell]) - withdrawn)
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
