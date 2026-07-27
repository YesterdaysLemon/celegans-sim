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

    def curvature(self) -> np.ndarray:
        """(n-1,) signed curvature at each joint, in 1/mm.

        Positive curvature bends the body towards its dorsal side, which we take to be the
        left-hand side of the direction of travel.
        """
        return (self.theta[1:] - self.theta[:-1]) / self.l

    def heading(self) -> float:
        """Direction the head is pointing."""
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
    def speed(self) -> float:
        """Instantaneous speed of the body centroid, mm/s."""
        u = np.stack([np.cos(self.theta), np.sin(self.theta)], axis=1)
        nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)
        # d(centroid)/dt from qdot, averaged over nodes
        w = (self.n + 1 - np.arange(1, self.n + 1)) / (self.n + 1)
        v = self.qdot[:2] + self.l * (w[:, None] * nvec * self.qdot[2:, None]).sum(axis=0)
        return float(np.hypot(*v))
