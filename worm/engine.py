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

import numpy as np

from . import dataset
from .body import Body
from .modulators import Modulators
from .muscle import Muscles
from .nervous import NervousSystem
from .params import MEDIA, Params
from .senses import Senses
from .world import World, default_world


class Simulation:
    def __init__(self, params: Params | None = None, seed: int = 0,
                 world: World | None = None,
                 placement: tuple[float, float, float] | None = None):
        self.p = params or Params()
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

        self.dt = self.p.neural.dt
        self.t = 0.0
        self.steps = 0
        self.food_eaten = 0.0

        self._contact = np.zeros((self.p.body.n_links + 1, 2))
        self._nodes = self.body.nodes()
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

    # ------------------------------------------------------------------------- stepping
    def step(self) -> None:
        p = self.p
        nodes = self._nodes

        curvature = self.body.curvature()
        activation = self.nervous.activation()
        # The modulators read the same activation the senses do and are updated first, so
        # that within a step the wireless layer is one step behind the wired one -- the
        # same consistent unit delay used everywhere else in this model.
        self.modulators.step(activation)
        I_ext = self.senses.sense(self.world, nodes, self._contact, curvature, activation,
                                  self.modulators)

        self.nervous.step(I_ext, g_mod=self.modulators.gated_conductance())
        self.muscles.step(self.nervous.s)

        self._contact = self.world.contact_force(nodes)
        # The mechanics may be substepped: the body is far stiffer than the nervous
        # system and its fast bending modes are what make the gait depend on dt. The
        # muscle moment and the contact forces are held constant across the substeps,
        # which is right -- they are outputs of the slow subsystem.
        moment = self.muscles.joint_moment()
        n_sub = self.p.body.substeps
        if n_sub > 1:
            sub = self.dt / n_sub
            for _ in range(n_sub):
                self.body.step(moment, dt=sub, node_forces=self._contact)
        else:
            self.body.step(moment, node_forces=self._contact)
        self._nodes = self.body.nodes()

        # Feeding. The worm pumps when its head is on a lawn; what it eats disappears.
        head = self._nodes[0]
        food_here = float(self.world.sample(self.world.food, head[0], head[1]))
        if food_here > 0.01:
            self.food_eaten += self.world.eat(
                head[0], head[1], p.world.ingestion_rate * self.dt)

        self.world.step(self.dt)
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

    def run(self, seconds: float) -> None:
        for _ in range(int(round(seconds / self.dt))):
            self.step()

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
            "senses": {k: round(float(v), 5) for k, v in self.senses.readout.items()},
        }
