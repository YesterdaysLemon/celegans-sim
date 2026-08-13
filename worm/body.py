"""The body: an inextensible active elastica in a viscous medium at zero Reynolds number.

Why this formulation
--------------------
A swimming C. elegans has a Reynolds number around 1e-3. Inertia is not small, it is
irrelevant: if the muscles stopped, the animal would coast for well under a nanometre.
So rather than integrating F = ma with stiff springs (which needs microsecond steps and
still lets the body stretch), we write the dynamics in the form they actually take at
zero Reynolds number,

    D(q) qdot = Q(q)

where q is the configuration, D is the configuration-dependent viscous drag metric from
resistive force theory, and Q collects the elastic and muscular generalised forces. This
is first order, unconditionally stable for the drag part, and -- because the generalised
coordinates are the head position plus the angle of each rigid segment -- the body is
*exactly* inextensible by construction rather than approximately so via stiff springs.

Coordinates
-----------
    q = (X, Y, theta_0 ... theta_{n-1})            dimension n+2

    node_0    = (X, Y)                             the tip of the nose
    node_k    = node_0 + l * sum_{m<k} u_m         u_m = (cos theta_m, sin theta_m)

with l = L/n the fixed segment length. A point on segment k at fraction s is

    p(k, s)   = node_0 + l * sum_{m<k} u_m + s l u_k

Resistive force theory
----------------------
The viscous force per unit length on a slender segment moving at velocity v is

    f = -( C_T t t^T + C_N n n^T ) v

with C_N > C_T. That anisotropy is the entire reason an undulating body makes forward
progress -- with C_N = C_T the net displacement over a cycle is zero, whatever the
waveform. Assembling D means integrating J^T Lambda_k J over every segment, which looks
like an O(n^3) triple sum but collapses to three n x n matrix products (see _drag_matrix).
"""

from __future__ import annotations

import numpy as np

from .params import BodyParams, MediumParams


# How much further apart along the body than their own combined width two nodes must be
# before they are allowed to register self-contact. See Body.__init__ -- at 1x, pairs that
# clear the rule by a rounding error fire during ordinary undulation.
SELF_CONTACT_MARGIN = 2.0


def radius_profile(s: np.ndarray, r_max: float) -> np.ndarray:
    """Body radius as a function of normalised arclength.

    C. elegans is widest just behind the midpoint, with a blunt head and a long tapering
    tail. The exponent 0.32 gives a body that stays near full width over the middle 60% of
    its length -- an ellipse (exponent 0.5) is far too pointed at the head to match the
    animal, whose nose is only about 45% thinner than its midbody.
    """
    x = np.clip(2.0 * s - 1.0, -1.0, 1.0)
    base = np.power(np.clip(1.0 - x * x, 1e-9, None), 0.32)
    taper = 1.0 - 0.25 * np.clip(s - 0.55, 0.0, None) / 0.45   # tail thinner than head
    return r_max * base * taper


class Body:
    """An inextensible active elastica, laid out nose-first from `position`.

    `heading` sets every link angle, and link angles run **nose to tail**: `position` is
    node 0, which is the nose, and `nodes()` walks the body out along `+heading` behind
    it. So `heading` is the direction the animal's body *trails*, and the animal faces --
    and travels -- at `heading + pi`.

    That is worth stating in the signature because the name invites the opposite reading
    and nothing used to contradict it. Measured, one animal at the origin with no food and
    no noise, after ten seconds: `heading=0` puts the nose at (-3.23, +0.10),
    `heading=pi/2` at (-0.10, -3.23), `heading=pi` at (+3.23, -0.10). Every bearing is its
    heading plus pi. Callers that meant "point this animal at X" and passed the bearing of
    X aimed it at the reflection of X, and two of them did: the foraging calibration in
    #69, whose conclusion had to be retracted, and the evolution assay's plate layout,
    which aimed every animal through the middle of the lawn it was supposed to be walking
    away from. See `body_direction`, which is the accessor to use for the travel axis, and
    `tests/test_physics.py::test_heading_argument_points_the_body_backwards`.
    """

    def __init__(self, p: BodyParams, medium: MediumParams,
                 position=(0.0, 0.0), heading: float = 0.0):
        self.p = p
        self.medium = medium
        n = p.n_links
        self.n = n
        self.l = p.length / n

        # Segment midpoints and joint locations in normalised arclength.
        self.seg_s = (np.arange(n) + 0.5) / n
        self.joint_s = (np.arange(1, n) * 1.0) / n

        r_seg = radius_profile(self.seg_s, p.radius_max)
        r_joint = radius_profile(self.joint_s, p.radius_max)
        self.radius = r_seg
        self.joint_radius = r_joint

        # Drag scales with the local perimeter. The dependence of the RFT coefficients on
        # radius is only logarithmic, so we use a gentle linear weighting rather than
        # pretending the thin tail feels the same drag as the midbody.
        self.rho = 0.55 + 0.45 * (r_seg / r_seg.max())

        # Self-contact geometry, precomputed because it is fixed by the radius profile.
        #
        # `node_radius` is the body's half-width at each node, so two nodes are touching
        # when their centres are closer than the sum of theirs. `_self_pairs` is which
        # pairs are allowed to say so, and the margin in it is load-bearing.
        #
        # Nodes a few segments apart sit inside each other's contact distance on a
        # perfectly straight worm -- that is the body being a continuous tube, not a
        # collision -- so a pair clearly has to be further apart along the body than it is
        # wide. But *just* further apart is not enough, and that was a real bug: nodes 31
        # and 34 are 0.0625 mm apart along the body against a contact distance of 0.06224,
        # a margin of three ten-thousandths of a millimetre, and ordinary undulation closed
        # it. The force fired on a normally-crawling animal and moved it 3 mm off its own
        # trajectory.
        #
        # So a pair must be at least SELF_CONTACT_MARGIN times its own width apart. At 2x,
        # a purely local kink has to reach about 27 /mm of curvature before it can register
        # -- roughly twice what the gait ever produces -- while any genuine fold, where two
        # distant stretches of body come alongside each other, is unaffected because those
        # pairs are far past the cut. Upper triangle only, so each pair resolves once.
        self.node_radius = radius_profile(np.arange(n + 1) / n, p.radius_max)
        contact = self.node_radius[:, None] + self.node_radius[None, :]
        along = np.abs(np.arange(n + 1)[:, None] - np.arange(n + 1)[None, :]) * self.l
        self._self_contact_dist = contact
        self._self_pairs = np.triu(along > SELF_CONTACT_MARGIN * contact, k=1)

        # Bending stiffness along the body. A solid rod would scale as r^4, but the worm is
        # a thin-walled cylinder held out by internal hydrostatic pressure, for which the
        # second moment goes as r^3 t -- and the pressure term does not taper at all. An
        # r^4 law makes the nose and tail into free hinges, which they visibly are not, so
        # we use r^3 with a floor.
        stiff = np.clip((r_joint / r_seg.max()) ** 3, 0.25, 1.0)
        self.K = p.EI * stiff / self.l                     # uN*mm per radian of joint angle
        self.gamma = p.internal_damping * stiff / self.l   # uN*mm*s per radian/s

        # Discrete difference operator: D[j] maps theta -> theta_{j+1} - theta_j.
        self.Dif = np.zeros((n - 1, n))
        rows = np.arange(n - 1)
        self.Dif[rows, rows] = -1.0
        self.Dif[rows, rows + 1] = 1.0
        self._K_mat = self.Dif.T @ (self.K[:, None] * self.Dif)
        self._B_mat = self.Dif.T @ (self.gamma[:, None] * self.Dif)

        self.pos = np.array(position, dtype=float)
        self.theta = np.full(n, float(heading))
        self.dt = p.dt

        self.qdot = np.zeros(n + 2)
        self._precompute_masks()

    # ------------------------------------------------------------------------ geometry
    def nodes(self) -> np.ndarray:
        """(n+1, 2) node positions from the nose backwards."""
        u = np.stack([np.cos(self.theta), np.sin(self.theta)], axis=1)
        out = np.empty((self.n + 1, 2))
        out[0] = self.pos
        np.cumsum(u * self.l, axis=0, out=out[1:])
        out[1:] += self.pos
        return out

    def centroid(self) -> np.ndarray:
        return self.nodes().mean(axis=0)

    def self_contact_force(self, nodes: np.ndarray,
                           stiffness: float = 40.0) -> np.ndarray:
        """Repulsion between parts of the body that are not neighbours, per node.

        The same linear penalty the dish wall and obstacles use, at the same stiffness, so
        there is one contact convention in the model rather than two. Returned in the shape
        `Body.step` takes as `node_forces`.

        This is inert on the animal as it stands, and verifiably so: a 60 s run is
        bit-identical with this term live and with it stubbed to zeros. It is installed
        *because* it is inert -- that is the only moment a constraint like this can be
        added and shown to change nothing. It stops being inert as soon as morphology is
        heritable, because a lineage scored on food alone would otherwise be free to evolve
        a body that folds through itself and be rewarded for it.

        The nose and tail have zero radius in `radius_profile`, so the outermost node of
        each cannot register contact at all. Its neighbours can, and they are 0.021 mm
        away, so nothing passes through the body -- but the very tip is not a collider.
        """
        f = np.zeros_like(nodes)
        d = nodes[:, None, :] - nodes[None, :, :]
        dist = np.sqrt((d * d).sum(axis=2))
        pen = self._self_contact_dist - dist
        hit = self._self_pairs & (pen > 0.0)
        if not hit.any():
            return f
        ii, jj = np.nonzero(hit)
        direction = d[ii, jj] / np.maximum(dist[ii, jj, None], 1e-9)
        push = stiffness * pen[ii, jj, None] * direction
        np.add.at(f, ii, push)
        np.add.at(f, jj, -push)
        return f

    def curvature(self) -> np.ndarray:
        """(n-1,) signed curvature at each joint, in 1/mm.

        Positive curvature bends the body towards its dorsal side, which we take to be the
        left-hand side of the direction of travel.
        """
        return (self.theta[1:] - self.theta[:-1]) / self.l

    def heading(self) -> float:
        """The first link's angle: the direction the body trails, *not* where it faces.

        The animal faces `heading() + pi`. This used to be documented as "direction the
        head is pointing", which is the opposite of what it returns, sitting twenty lines
        from `body_direction` -- documented as "the travel axis" and computing the other
        bearing. Both claimed to be forward and they disagreed by half a turn.

        Nothing ever failed on it because this accessor has no callers: every site that
        wants a direction uses `body_direction`. That is exactly why the wrong docstring
        survived, and exactly why it was still able to mislead anyone reading this file to
        learn the convention. Use `body_direction` for the travel axis.
        """
        return float(self.theta[0])

    def body_direction(self) -> np.ndarray:
        """Unit vector from the centre of the body towards the nose: the travel axis."""
        nodes = self.nodes()
        d = nodes[0] - nodes[self.n // 2]
        norm = np.hypot(*d)
        return d / norm if norm > 1e-12 else np.array([1.0, 0.0])

    # ------------------------------------------------------------------------- dynamics
    def _drag_matrix(self, u: np.ndarray, nvec: np.ndarray) -> np.ndarray:
        """Assemble the (n+2, n+2) viscous drag metric.

        The (theta, theta) block is

            D[m,p] = l^3 * sum_k rho_k c(k,m,p) * ( C_T P[m,k] P[p,k] + C_N Q[m,k] Q[p,k] )

        with P[m,k] = n_m . u_k, Q[m,k] = n_m . n_k, and c(k,m,p) the integral of the two
        lever arms along segment k: 1 when k is behind both joints, 1/2 when it is the
        rearmost of them, 1/3 when m = p = k, and 0 otherwise. Masking P and Q by k > m
        turns the "behind both" sum into a single matrix product A A^T, which is what makes
        this cheap enough to run at 2 kHz.
        """
        n = self.n
        C_T = self.medium.c_tangential
        C_N = self.medium.c_normal
        rho = self.rho

        P = nvec @ u.T                    # P[m, k] = n_m . u_k
        Q = nvec @ nvec.T                 # Q[m, k] = n_m . n_k
        # Two masked copies. The cross block is linear in rho_k, but the rotational block
        # is a product of two lever arms that must share a single factor of rho_k between
        # them, so it needs the square root -- (A A^T)[m,p] then sums rho_k, not rho_k^2.
        A = P * self._mask_rho
        B = Q * self._mask_rho
        A_s = P * self._mask_sqrt
        B_s = Q * self._mask_sqrt

        D = np.zeros((n + 2, n + 2))

        # translation / translation
        D[:2, :2] = self.l * (C_T * (u * rho[:, None]).T @ u
                              + C_N * (nvec * rho[:, None]).T @ nvec)

        # translation / rotation
        cross = (self.l ** 2) * (C_T * (A @ u) + C_N * (B @ nvec)
                                 + 0.5 * C_N * (rho[:, None] * nvec))
        D[:2, 2:] = cross.T
        D[2:, :2] = cross

        # rotation / rotation
        tt = C_T * (A_s @ A_s.T) + C_N * (B_s @ B_s.T)
        tt += C_N * 0.5 * Q * self._rho_max_off
        tt[np.diag_indices(n)] += C_N * rho / 3.0
        D[2:, 2:] = (self.l ** 3) * tt
        return D

    def _precompute_masks(self) -> None:
        n = self.n
        idx = np.arange(n)
        strict = (idx[None, :] > idx[:, None]).astype(float)
        self._mask_rho = self.rho[None, :] * strict
        self._mask_sqrt = np.sqrt(self.rho)[None, :] * strict
        # rho at the rearmost of the two joints, zero on the diagonal
        later = np.maximum(idx[:, None], idx[None, :])
        self._rho_max_off = self.rho[later] * (1.0 - np.eye(n))

    def step(self, muscle_torque: np.ndarray, dt: float | None = None,
             node_forces: np.ndarray | None = None) -> None:
        """Advance the body by one step.

        `muscle_torque` is the (n-1,) active bending moment at each joint, positive for a
        dorsal bend. `node_forces` is an optional (n+1, 2) array of external forces applied
        at the body nodes -- contact with the dish wall, or a poke from the user.
        """
        if dt is None:
            dt = self.dt
        n = self.n
        theta = self.theta
        u = np.stack([np.cos(theta), np.sin(theta)], axis=1)
        nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)

        D = self._drag_matrix(u, nvec)

        # Elastic restoring torque plus the active muscle moment, mapped to generalised
        # forces by the transpose of the joint-angle difference operator.
        joint = self.theta[1:] - self.theta[:-1]
        torque = -self.K * joint + muscle_torque
        Q = np.zeros(n + 2)
        Q[2:] = self.Dif.T @ torque
        if node_forces is not None:
            # A force F applied at node j moves the head coordinate directly and rotates
            # every joint anterior to it: dnode_j/dtheta_m = l * n_m for m < j.
            Q[:2] += node_forces.sum(axis=0)
            suffix = np.cumsum(node_forces[::-1], axis=0)[::-1][1:]   # sum over j > m
            Q[2:] += self.l * np.einsum("mi,mi->m", nvec, suffix)

        # Backward Euler on the linear elastic and internal-damping terms. Both are
        # constant matrices, so this costs nothing and removes the stiffest timescale in
        # the problem (the highest bending mode relaxes in well under a millisecond on
        # agar) from the stability condition entirely.
        lhs = D
        lhs[2:, 2:] += self._B_mat + dt * self._K_mat

        qdot = np.linalg.solve(lhs, Q)
        self.qdot = qdot
        self.pos = self.pos + qdot[:2] * dt
        self.theta = theta + qdot[2:] * dt

    # ---------------------------------------------------------------------- diagnostics
    def drag_load(self) -> float:
        """Mean drag force per unit length the cuticle currently bears, in uN/mm.

        The physical signal a cuticle mechanoreceptor has access to: c x v, per segment,
        magnitude, averaged along the body. Unlike the bending dynamics -- which are
        measured to become independent of the medium below K ~ 8, because the elastic
        response dominates the drag there -- this quantity keeps scaling with the drag
        coefficients all the way down the continuum, since the coefficients are in it as
        factors. It is a read-only diagnostic of the *previous* step's velocities, which
        is the same one-step lag every other sensory pathway carries.
        """
        qdot = getattr(self, "qdot", None)
        if qdot is None:
            return 0.0
        u = np.stack([np.cos(self.theta), np.sin(self.theta)], axis=1)
        nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)
        # Velocity at each segment midpoint: the head node's translation plus the
        # accumulated rotation of every link anterior to it, plus half its own.
        contrib = self.l * nvec * qdot[2:, None]
        csum = np.cumsum(contrib, axis=0)
        vmid = qdot[:2] + np.vstack([np.zeros((1, 2)), csum[:-1]]) + 0.5 * contrib
        v_t = np.einsum("mi,mi->m", vmid, u)
        v_n = np.einsum("mi,mi->m", vmid, nvec)
        f = np.hypot(self.medium.c_tangential * v_t, self.medium.c_normal * v_n)
        return float(f.mean())

    def speed(self) -> float:
        """Instantaneous speed of the body centroid, mm/s."""
        u = np.stack([np.cos(self.theta), np.sin(self.theta)], axis=1)
        nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)
        # d(centroid)/dt from qdot, averaged over nodes
        w = (self.n + 1 - np.arange(1, self.n + 1)) / (self.n + 1)
        v = self.qdot[:2] + self.l * (w[:, None] * nvec * self.qdot[2:, None]).sum(axis=0)
        return float(np.hypot(*v))
