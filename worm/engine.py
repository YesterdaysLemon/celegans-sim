"""The simulation engine: one worm, one world, one closed loop.

Each step runs the same cycle the animal does:

    world  ->  sensory neurons  ->  connectome  ->  motor neurons
       ^                                                   |
       |                                                   v
    body position <-  mechanics  <-  bending moment  <-  muscles
       |                                                   ^
       +----------------- proprioception ------------------+

Nothing in the middle is scripted. The undulatory wave is not a pattern generator; it
emerges because each B-type motor neuron senses the curvature of the body just in front of
it and contracts the muscle on the same side, so a bend started at the head propagates
backwards down the body and pushes the animal forward against an anisotropic drag.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from . import dataset
from .body import Body
from .errors import DivergentSimulation
from .modulators import Modulators
from .egglaying import EggLaying
from .pharynx import Pharynx
from .muscle import Muscles
from .nervous import NervousSystem
from .params import MEDIA, Params
from .senses import Senses
from .world import World, default_world


@dataclass(frozen=True)
class FeedingRequest:
    """Food an animal wants withdrawn after every animal has sampled this tick."""

    x: float
    y: float
    amount: float


class Simulation:
    def __init__(self, params: Params | None = None, seed: int = 0,
                 world: World | None = None,
                 placement: tuple[float, float, float] | None = None):
        self.p = params or Params()
        self.p.validate()
        self.rng = np.random.default_rng(seed)
        self.conn = dataset.load(e_exc=self.p.neural.E_exc, e_inh=self.p.neural.E_inh)

        self.world = world if world is not None else default_world(self.p.world, self.rng)
        self.nervous = NervousSystem(self.conn, self.p.neural, self.rng)
        self.muscles = Muscles(self.conn, self.p.muscle, self.p.body, self.p.neural.dt,
                               s_eq=float(self.nervous.s[0]),
                               omega_gain=self.p.sensory.omega_gain)
        # Where the animal is put down. Behavioural assays need to control this -- a
        # chemotaxis index means nothing without a defined starting distance and bearing --
        # so it is a parameter, defaulting to the viewer's usual corner of the dish.
        px, py, phi = placement if placement is not None else (-14.0, -2.0, 0.35)
        self.body = Body(self.p.body, self.p.medium, position=(px, py), heading=phi)
        # The body keeps its own timestep so the mechanics tools can drive it standalone,
        # but inside the closed loop it must run at the neural step. It did not: BodyParams
        # .dt said "shared with the neural step" and was not shared with anything, so
        # changing NeuralParams.dt left the body advancing 0.5 ms per call while the rest
        # of the animal believed it had advanced by the neural step. At dt = 0.125 ms the
        # body therefore ran four times fast relative to its own nervous system, and every
        # timestep-convergence result in this project measured that desynchronisation
        # rather than any numerical error.
        self.body.dt = self.p.neural.dt
        self.senses = Senses(self.conn, self.p.sensory, self.p.world,
                             self.p.body.n_links, self.p.sensory.proprio_reach,
                             self.p.neural.dt, g_rest=self.nervous.g_rest,
                             rng=self.rng)
        self.modulators = Modulators(self.conn, self.p.modulator, self.p.neural.dt,
                                     g_rest=self.nervous.g_rest)
        self.pharynx = Pharynx(self.conn, self.p.pharynx, self.p.neural.dt)
        self.egglaying = EggLaying(self.conn, self.p.egglaying, self.p.neural.dt)

        self.dt = self.p.neural.dt
        self.t = 0.0
        self.steps = 0
        self.food_eaten = 0.0

        self._contact = np.zeros((self.p.body.n_links + 1, 2))
        self._nodes = self.body.nodes()
        # Previous joint curvature, for the force-velocity term's shortening rate. None
        # until the second step, where a rate first exists; the first step therefore runs
        # with no derating at all, which is right -- a muscle that has not moved yet has no
        # shortening velocity to be derated by.
        self._kappa_prev = None
        self._kappa_rate = np.zeros(self.p.body.n_links - 1)
        self.ablated: list[str] = []
        self._nmj0 = None

        # Rolling history for the viewer and for the behavioural measurements.
        self.trail = deque(maxlen=4000)
        self.history = {
            "t": deque(maxlen=3000),
            "speed": deque(maxlen=3000),
            "curvature_mid": deque(maxlen=3000),
            "attractant": deque(maxlen=3000),
        }
        self._last_centroid = self.body.centroid().copy()
        self._velocity_smooth = np.zeros(2)
        self.path_speed = 0.0        # distance travelled per second, including sloshing
        self.speed = 0.0             # net progress per second -- the honest one

        # A worm tracker measures how far the animal actually got over a window, not how
        # fast its centroid was instantaneously moving. The difference is not cosmetic: an
        # undulating body slews its centroid from side to side once per cycle, and
        # smoothing the *magnitude* of that counts every slosh as progress. Measured on
        # this model it inflated the number by a factor of twenty.
        self._speed_window = 2.0     # s
        self._centroid_history = deque()
        self._pending_step = None

    # ------------------------------------------------------------------------- stepping
    def step(self) -> None:
        """Advance one animal and its private/single-animal world by one tick.

        This remains the backwards-compatible entry point.  Shared-world callers must use
        :class:`Population`, which settles feeding simultaneously and advances the world
        once after every animal has taken its turn.
        """
        request = self.prepare_step()
        captured = (self.world.eat(request.x, request.y, request.amount)
                    if request is not None else 0.0)
        self.finish_step(captured)
        self.world.step(self.dt)

    def prepare_step(self) -> FeedingRequest | None:
        """Advance through capture demand and return an unsettled feeding request.

        The world time and food field are deliberately not mutated here.  ``Population``
        calls this for every animal against one shared snapshot, settles the returned
        requests in a batch, and passes each actual allocation to :meth:`finish_step`.
        """
        if self._pending_step is not None:
            raise RuntimeError("finish_step must complete the pending animal step")

        nodes = self._nodes

        curvature = self.body.curvature()
        activation = self.nervous.activation()
        # The modulators read the same activation the senses do and are updated first, so
        # that within a step the wireless layer is one step behind the wired one -- the
        # same consistent unit delay used everywhere else in this model.
        self.modulators.step(activation, alive=self.nervous.alive)
        # The amine load-sensing path reads the drag force the cuticle bore on the
        # previous step -- the same unit delay as every other sensory quantity. Only
        # computed when the path is on, so the shipped animal pays nothing.
        load = (self.body.drag_load() if self.p.sensory.load_gain != 0.0 else 0.0)
        I_ext = self.senses.sense(self.world, nodes, self._contact, curvature, activation,
                                  self.modulators, load=load)

        self.nervous.step(I_ext, g_mod=self.modulators.gated_conductance(),
                          g_exc=self.senses.prop_g, E_exc=self.p.sensory.proprio_E_rev,
                          g_inh=self.senses.prop_g_inh)
        self.muscles.step(self.nervous.s,
                          rate_scale=self.modulators.muscle_rate_scale())

        # The dish pushes back, and so does the body's own far side. Both are node forces
        # in the same units and at the same stiffness, so they simply add.
        self._contact = (self.world.contact_force(nodes)
                         + self.body.self_contact_force(nodes))
        # The mechanics may be substepped: the body is far stiffer than the nervous
        # system and its fast bending modes are what make the gait depend on dt. The
        # muscle moment and the contact forces are held constant across the substeps,
        # which is right -- they are outputs of the slow subsystem.
        # Force-velocity, when it is on, needs the rate at which each joint is bending --
        # that is what a body-wall muscle's shortening velocity *is* here. It is
        # finite-differenced from the curvature this step against the curvature last step,
        # both of which are read before the body moves, so the rate is the one the muscle
        # has just experienced rather than the one it is about to cause. With the term off
        # nothing here is computed and the call is exactly what it was.
        kappa_rate = None
        if self.p.muscle.fv_vmax > 0.0:
            if self._kappa_prev is not None:
                raw = (curvature - self._kappa_prev) / self.dt
                # Low-passed, and see MuscleParams.fv_tau for why that is required. The raw
                # difference is the body's fastest bending modes, not the gait's shortening
                # velocity, and feeding it back explicitly diverges in a light medium.
                a = 1.0 - np.exp(-self.dt / self.p.muscle.fv_tau)
                self._kappa_rate += (raw - self._kappa_rate) * a
                kappa_rate = self._kappa_rate
            self._kappa_prev = curvature.copy()
        moment = self.muscles.joint_moment(kappa_rate)
        n_sub = self.p.body.substeps
        if n_sub > 1:
            sub = self.dt / n_sub
            for _ in range(n_sub):
                self.body.step(moment, dt=sub, node_forces=self._contact)
        else:
            self.body.step(moment, node_forces=self._contact)
        self._nodes = self.body.nodes()

        # Feeding. The pharynx decides when to pump and how much that moves; the world
        # only has to lose it. See worm/pharynx.py -- this used to be a flat rate applied
        # whenever the head was over food, with the twenty pharyngeal neurons driving
        # nothing at all.
        head = self._nodes[0]
        food_here = float(self.world.sample(self.world.food, head[0], head[1]))
        wanted = self.pharynx.prepare_step(
            activation, food_here, self.modulators, alive=self.nervous.alive)
        request = (FeedingRequest(float(head[0]), float(head[1]), float(wanted))
                   if wanted > 0.0 else None)
        self._pending_step = (activation, food_here, curvature)
        return request

    def finish_step(self, captured: float = 0.0) -> None:
        """Commit actual captured food and complete the animal-owned half of a tick."""
        if self._pending_step is None:
            raise RuntimeError("prepare_step must run before finish_step")

        activation, food_here, curvature = self._pending_step
        moved = self.pharynx.finish_step(captured)
        # Food is credited when captured, not when M4 transports it.  Consequently plate
        # loss and ``food_eaten`` agree, while intestine + lumen accounts for the same food.
        self.food_eaten += self.pharynx.captured

        # Egg-laying. Fed by what the pharynx actually transported, so the two systems are
        # coupled the way they are in the animal: eggs are made out of food. The vulva is
        # halfway down the body, which is where the egg is put -- an egg trail is a record
        # of where the animal was while it was laying, and that is worth being able to see.
        laid = self.egglaying.step(activation, moved,
                                   self.modulators.level["serotonin"], food_here,
                                   alive=self.nervous.alive)
        if laid > 0.0:
            vulva = self._nodes[len(self._nodes) // 2]
            self.world.lay_egg(vulva[0], vulva[1])

        self.t += self.dt
        self.steps += 1

        centroid = self.body.centroid()
        velocity = (centroid - self._last_centroid) / self.dt
        self._last_centroid = centroid.copy()
        blend = min(1.0, self.dt / 0.6)
        self._velocity_smooth += (velocity - self._velocity_smooth) * blend
        inst = float(np.hypot(*velocity))
        self.path_speed += (inst - self.path_speed) * min(1.0, self.dt / 0.25)

        hist = self._centroid_history
        hist.append((self.t, centroid.copy()))
        while len(hist) > 1 and self.t - hist[0][0] > self._speed_window:
            hist.popleft()
        span = self.t - hist[0][0]
        if span > 0.5 * self._speed_window:
            self.speed = float(np.hypot(*(centroid - hist[0][1]))) / span

        if self.steps % 20 == 0:
            self.trail.append((float(centroid[0]), float(centroid[1])))
            h = self.history
            h["t"].append(self.t)
            h["speed"].append(self.speed)
            h["curvature_mid"].append(float(curvature[len(curvature) // 2]))
            h["attractant"].append(self.senses.readout.get("attractant", 0.0))
        self._pending_step = None

    def run(self, seconds: float, check_every: int | None = 1000) -> None:
        """Run a single-animal simulation, periodically rejecting divergent states."""
        _validate_check_interval(check_every)
        if check_every is not None:
            self.check_invariants()
        for _ in range(int(round(seconds / self.dt))):
            self.step()
            if check_every is not None and self.steps % check_every == 0:
                self.check_invariants()
        if check_every is not None:
            self.check_invariants()

    def check_invariants(self, max_path_speed: float = 5.0) -> None:
        """Raise ``DivergentSimulation`` when the animal is no longer physical.

        This is intentionally a harness-level check rather than work in the 2 kHz hot
        loop.  ``run`` and ``Population`` call it every 1000 steps by default; evolutionary
        evaluators may choose another interval and treat the exception as fitness zero.
        """
        arrays = {
            "body angles": self.body.theta,
            "body velocity": self.body.qdot,
            "membrane potentials": self.nervous.V,
        }
        for name, values in arrays.items():
            if not np.isfinite(values).all():
                raise DivergentSimulation("%s are not finite" % name)

        curvature = self.body.curvature()
        curvature_limit = np.pi / self.body.l
        peak_curvature = float(np.max(np.abs(curvature)))
        if not np.isfinite(peak_curvature) or peak_curvature >= curvature_limit:
            raise DivergentSimulation(
                "curvature %.6g /mm exceeds the %.6g /mm link limit"
                % (peak_curvature, curvature_limit))

        for name, value in (("path speed", self.path_speed), ("net speed", self.speed)):
            if not np.isfinite(value):
                raise DivergentSimulation("%s is not finite" % name)
        if self.path_speed >= max_path_speed:
            raise DivergentSimulation(
                "path speed %.6g mm/s exceeds %.6g mm/s" % (self.path_speed, max_path_speed))

        nodes = self.body.nodes()
        if not np.isfinite(nodes).all():
            raise DivergentSimulation("body coordinates are not finite")
        radius = np.hypot(nodes[:, 0], nodes[:, 1])
        if float(radius.max()) > self.world.extent:
            raise DivergentSimulation(
                "animal left the dish (radius %.6g mm > %.6g mm)"
                % (float(radius.max()), self.world.extent))

    # -------------------------------------------------------------------------- control
    def set_medium(self, name: str) -> None:
        self.p = self.p.with_medium(name)
        self.body.medium = MEDIA[name]

    def set_ablated(self, names) -> None:
        """Remove the named neurons from the animal. Replaces the set; empty restores.

        Coordinates the two halves of the removal: the nervous system drops the cell from
        the network and stops it responding to anything (see NervousSystem.set_ablated for
        why zeroing conductances alone is not enough), and the neuromuscular map drops
        whatever it drove directly.
        """
        idx = [self.conn.index[n] for n in names if n in self.conn.index]
        self.nervous.set_ablated(idx)
        if self._nmj0 is None:
            self._nmj0 = self.muscles.G.copy()
        self.muscles.G = self._nmj0.copy()
        if idx:
            self.muscles.G[:, idx] = 0.0
        self.ablated = [self.conn.names[i] for i in idx]

    def poke(self, where: str = "anterior", strength: float = 1.0) -> None:
        """Deliver an eyebrow-hair touch, as in the classic gentle-touch assay."""
        if where == "anterior":
            self.senses.poke[0] += strength
        else:
            self.senses.poke[1] += strength

    # ------------------------------------------------------------------------- readouts
    def direction(self) -> str:
        """Whether the animal is going forwards or backwards, from the body frame.

        Projected from the *smoothed centroid* velocity, not the head node's. The head of
        an undulating worm swings from side to side faster than the animal travels, so its
        instantaneous velocity points backwards for a good part of every cycle even during
        steady forward locomotion.
        """
        if self.speed < 2e-3:                    # under 2 um/s is not going anywhere
            return "still"
        v = self._velocity_smooth
        if float(np.hypot(*v)) < 1e-6:
            return "still"
        return "forward" if float(v @ self.body.body_direction()) > 0 else "backward"

    def snapshot(self) -> dict:
        nodes = self._nodes
        d, v = self.muscles.row_tension()
        return {
            "t": round(self.t, 4),
            "nodes": np.round(nodes, 4).tolist(),
            "radius": np.round(self.body.radius, 4).tolist(),
            "V": np.round(self.nervous.V, 2).tolist(),
            "activation": np.round(self.nervous.activation(), 4).tolist(),
            "muscle_dorsal": np.round(d, 4).tolist(),
            "muscle_ventral": np.round(v, 4).tolist(),
            "curvature": np.round(self.body.curvature(), 4).tolist(),
            "speed": round(self.speed, 6),
            "path_speed": round(self.path_speed, 6),
            "direction": self.direction(),
            "food_eaten": round(self.food_eaten, 4),
            "pharynx": {k: round(float(v), 5) for k, v in self.pharynx.readout().items()},
            "egglaying": {k: round(float(v), 5) for k, v in self.egglaying.readout().items()},
            "senses": {k: round(float(v), 5) for k, v in self.senses.readout.items()},
        }


class Population:
    """A collection of animals sharing one world and one explicit world timebase."""

    def __init__(self, simulations, check_every: int | None = 1000):
        simulations = tuple(simulations)
        if not simulations:
            raise ValueError("a population needs at least one simulation")
        if len({id(sim) for sim in simulations}) != len(simulations):
            raise ValueError("a simulation may appear only once in a population")
        world = simulations[0].world
        dt = simulations[0].dt
        if any(sim.world is not world for sim in simulations):
            raise ValueError("every animal in a population must share the same World instance")
        if any(sim.dt != dt for sim in simulations):
            raise ValueError("every animal in a population must use the same timestep")
        if any(sim.t != simulations[0].t for sim in simulations):
            raise ValueError("population animals must start at the same simulation time")
        if not np.isclose(world.t, simulations[0].t, rtol=0.0, atol=1e-12):
            raise ValueError("shared world time must match animal simulation time")
        _validate_check_interval(check_every)

        self.simulations = simulations
        self.world = world
        self.dt = dt
        self.check_every = check_every
        self.steps = 0
        if check_every is not None:
            for sim in self.simulations:
                sim.check_invariants()

    def step(self) -> None:
        """Advance every animal, settle food simultaneously, then age the world once."""
        requests = [sim.prepare_step() for sim in self.simulations]
        allocations = np.zeros(len(self.simulations), dtype=float)
        active = [(i, request) for i, request in enumerate(requests) if request is not None]
        if active:
            captured = self.world.eat_batch(
                [(request.x, request.y, request.amount) for _, request in active])
            for (sim_i, _), eaten in zip(active, captured):
                allocations[sim_i] = float(eaten)

        for sim, eaten in zip(self.simulations, allocations):
            sim.finish_step(float(eaten))

        self.world.step(self.dt)
        self.steps += 1
        if self.check_every is not None and self.steps % self.check_every == 0:
            for sim in self.simulations:
                sim.check_invariants()

    def run(self, seconds: float) -> None:
        for _ in range(int(round(seconds / self.dt))):
            self.step()
        if self.check_every is not None:
            for sim in self.simulations:
                sim.check_invariants()


def _validate_check_interval(check_every: int | None) -> None:
    if check_every is not None and (
            isinstance(check_every, bool) or not isinstance(check_every, int)
            or check_every <= 0):
        raise ValueError("check_every must be a positive integer or None")
