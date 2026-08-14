"""The 95 body-wall muscle cells, and how their tension becomes a bending moment.

Each muscle cell is simulated individually. They are non-spiking like the neurons, and
receive graded cholinergic (excitatory) and GABAergic (inhibitory) input at the
neuromuscular junctions listed in the connectome. The excitation-contraction cascade is
three first-order stages -- membrane potential, then calcium, then tension -- whose
combined lag is about 100 ms, matching the single lumped time constant Boyle et al. (2012)
fitted to real muscle.

The four muscle quadrants (dorsal-left, dorsal-right, ventral-left, ventral-right) are kept
separate all the way through, because the two members of a dorsoventral pair genuinely do
receive different innervation. They are only combined at the final step, where the
difference between dorsal and ventral tension at a given point along the body becomes the
bending moment that the two-dimensional mechanical model can act on.
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import BodyParams, MuscleParams
from .nervous import _sigmoid


class Muscles:
    def __init__(self, conn: Connectome, p: MuscleParams, body: BodyParams, dt: float,
                 s_eq: float, omega_gain: float = 1.0):
        self.conn = conn
        self.p = p
        self.dt = dt
        self.s_eq = s_eq          # resting presynaptic activation, for the balance solve
        m = conn.n_muscles

        self.G = conn.nmj * p.g_nmj                    # (M, N) nS per unit activation
        # Muscle reversal potentials, not the neuronal ones: the postsynaptic receptor is
        # what sets the reversal, and at the NMJ that is nicotinic ACh and UNC-49 GABA-A.
        self.E_pre = np.where(conn.inhibitory, p.E_inh, p.E_exc)

        self.V = np.full(m, p.E_leak)
        self.calcium = np.zeros(m)
        self.tension = np.zeros(m)
        self._C_nF = p.C_m * 1e-3

        self.dorsal = conn.muscle_side > 0
        self.excitatory_pre = ~conn.inhibitory
        if p.normalise_nmj:
            self._balance(conn)

        # RIV's gain, applied to its *deviation* from rest rather than to its conductance.
        #
        # RIV is the omega-turn cell and it is exclusively ventral -- nine neuromuscular
        # contacts ventral, none dorsal -- but it is also tonically active: its release
        # sits at 0.075 against the 0.091 the balance assumes, and rises only to 0.114
        # during reversals. Scaling its conductance amplifies the tonic part along with
        # the phasic one, and neither position in the constructor gives the wanted one:
        # scaling after _balance amplifies the tonic release and bends the animal
        # permanently (gain 5 quadrupled reorientation and took net speed 0.301 -> 0.027
        # mm/s), while scaling before it is very nearly a no-op, because the balance
        # equalises each cell's total drive and divides the change straight back out
        # (gain 8 moved reorientation 18.1 -> 14.6 deg).
        #
        # The balance cancels resting tone on the assumption that every neuron sits at
        # s_eq, so amplifying deviations *from s_eq* leaves the balanced resting state
        # untouched by construction and acts only on the phasic, reversal-linked part.
        # A gain of 1 leaves s_pre exactly unchanged, so this is applied to the whole
        # vector rather than to an index set. See SensoryParams.omega_gain.
        self.phasic_gain = np.ones(conn.n)
        if omega_gain != 1.0:
            self.phasic_gain[conn.group("RIV")] = omega_gain
        self.G_gap = self._muscle_coupling(conn, p)
        self.gap_total = self.G_gap.sum(axis=1)
        # Row index 1..24 within each quadrant, and the normalised body position of each.
        self.row = np.array([int(name[3:]) for name in conn.muscle_names])
        self.pos = conn.muscle_pos

        self._any_phasic = bool(np.any(self.phasic_gain != 1.0))

        self._decay_ca = np.exp(-dt / p.tau_calcium)
        self._decay_te = np.exp(-dt / p.tau_tension)

        # Map muscle rows onto mechanical joints. Rows are sorted by body position so the
        # interpolation below is monotone.
        n_joint = body.n_links - 1
        self.joint_s = (np.arange(1, body.n_links)) / body.n_links
        rows = np.unique(self.row)
        self.row_pos = np.array([self.pos[self.row == r][0] for r in rows])
        order = np.argsort(self.row_pos)
        self._rows = rows[order]
        self.row_pos = self.row_pos[order]
        self._row_mask_d = np.stack([(self.row == r) & self.dorsal for r in self._rows])
        self._row_mask_v = np.stack([(self.row == r) & ~self.dorsal for r in self._rows])
        self._row_n_d = self._row_mask_d.sum(axis=1)
        self._row_n_v = self._row_mask_v.sum(axis=1)

        # Head-to-tail muscle efficacy gradient, and the moment arm, which follows the
        # local body radius.
        from .body import radius_profile
        eff = np.interp(self.joint_s, [0.0, 1.0], [p.efficacy_head, p.efficacy_tail])
        arm = radius_profile(self.joint_s, body.radius_max) / body.radius_max
        self.joint_gain = p.peak_moment * eff * arm * body.muscle_moment_arm

    def _muscle_coupling(self, conn: Connectome, p: MuscleParams) -> np.ndarray:
        """(M, M) symmetric electrical coupling between body-wall muscle cells.

        Neighbouring cells within a quadrant are strongly coupled; the four quadrants are
        only weakly coupled to each other at the same body position, which matters because
        strong coupling across quadrants would short out the dorsoventral difference the
        animal bends with.
        """
        m = conn.n_muscles
        G = np.zeros((m, m))
        quad = [n[:3] for n in conn.muscle_names]
        index = [int(n[3:]) for n in conn.muscle_names]
        for a in range(m):
            for b in range(a + 1, m):
                if quad[a] == quad[b] and abs(index[a] - index[b]) == 1:
                    G[a, b] = G[b, a] = p.g_muscle_gap
                elif quad[a] != quad[b] and index[a] == index[b]:
                    G[a, b] = G[b, a] = p.g_quadrant_gap
        return G

    def _balance(self, conn: Connectome) -> None:
        """Give every muscle cell the same total drive, and both sheets the same resting tone.

        Step one equalises the total neuromuscular conductance across the 95 cells, which
        removes the several-fold spread in reconstructed contact count without touching the
        relative weighting among any one cell's inputs. Step two scales the excitatory
        conductance of each sheet until both rest at the same tension, so that a worm with
        no sensory input and no wave stands straight instead of curled.
        """
        p = self.p
        total = self.G.sum(axis=1)
        self.G *= (total.mean() / np.maximum(total, 1e-9))[:, None]

        s_eq = self.s_eq
        exc = self.excitatory_pre
        g_inh = (self.G[:, ~exc] * s_eq).sum(axis=1)
        g_exc = (self.G[:, exc] * s_eq).sum(axis=1)

        def tension(alpha):
            ge = g_exc * alpha
            g_tot = p.g_leak + ge + g_inh
            V = (p.g_leak * p.E_leak + ge * p.E_exc + g_inh * p.E_inh) / g_tot
            return _sigmoid(p.beta * (V - p.v_half))

        # Solve per cell, not per sheet. Balancing the two sheets on average still leaves
        # individual cells resting far up or far down their tension curve, where the curve
        # is flat and the cell cannot respond to anything its motor neurons do -- which is
        # what silences the head muscles in particular, since the head receives a quite
        # different excitatory/inhibitory mix from the rest of the body. Solving cell by
        # cell puts all 95 of them on the steep part of their own curve. It is the same
        # move as setting each neuron's release threshold to its own resting potential.
        lo = np.full(self.G.shape[0], 1e-4)
        hi = np.full(self.G.shape[0], 5e3)
        for _ in range(70):
            mid = 0.5 * (lo + hi)
            below = tension(mid) < p.rest_tension
            lo = np.where(below, mid, lo)
            hi = np.where(below, hi, mid)
        scale = 0.5 * (lo + hi)
        # A cell with no excitatory input at all cannot be balanced; leave it alone.
        balanceable = g_exc > 1e-9
        scale = np.where(balanceable, scale, 1.0)

        # Bisection over a fixed bracket returns an endpoint when the target lies outside
        # it, and says nothing at all. That is not hypothetical: `rest_tension = 1.0` is
        # unattainable and produced a paralysed straight animal -- |kappa|max 0.0, speed
        # 0.0000 -- with no warning, and `rest_tension = 0.0` gives speed 0.0000 the same
        # way. Two different silent phenotypes out of one unsolved equation, each of which
        # reads as a modelling result.
        #
        # Checking the residual rather than the bracket, because landing on an endpoint
        # only matters if the answer there is wrong. The tolerance is deliberately loose:
        # 70 bisections of [1e-4, 5e3] leave an interval near 1e-17 relative, so anything
        # failing this is out of range rather than merely imprecise.
        residual = np.abs(tension(scale) - p.rest_tension)
        unreachable = balanceable & (residual > 1e-6)
        if np.any(unreachable):
            lo_t = tension(np.full_like(scale, 1e-4))
            hi_t = tension(np.full_like(scale, 5e3))
            raise ValueError(
                "rest_tension = %.6g is unreachable for %d of %d muscle cells. Over the "
                "bracket [1e-4, 5e3] those cells span tension %.6g..%.6g, so no scaling of "
                "their excitatory conductance reaches the target; the solve would have "
                "returned a bracket endpoint and left the animal silently paralysed."
                % (p.rest_tension, int(unreachable.sum()), int(balanceable.sum()),
                   float(lo_t[unreachable].min()), float(hi_t[unreachable].max())))
        self.G[:, exc] *= scale[:, None]

    def step(self, s_pre: np.ndarray, dt: float | None = None,
             rate_scale: float = 1.0) -> None:
        """Advance the muscles given the presynaptic activation of every neuron.

        `rate_scale` scales the EC cascade's two time constants -- the amine
        load-sensing path's third effect (ModulatorParams.dopamine_muscle_rate). At
        exactly 1.0 the precomputed decays are used unchanged, so the shipped
        configuration is bit-identical.
        """
        if dt is None:
            dt = self.dt
        p = self.p

        if self._any_phasic:
            s_pre = np.clip(self.s_eq + self.phasic_gain * (s_pre - self.s_eq), 0.0, 1.0)

        g = self.G @ s_pre                              # (M,) total NMJ conductance
        e = self.G @ (s_pre * self.E_pre)               # (M,) conductance-weighted reversal
        g_tot = p.g_leak + g + self.gap_total
        fixed = p.g_leak * p.E_leak + e
        decay = np.exp(-g_tot * dt / self._C_nF)
        # Same treatment as the neurons: exponential Euler on the diagonal, with the
        # electrical coupling between cells refined by a couple of fixed-point passes.
        V_new = self.V
        for _ in range(2):
            V_inf = (fixed + self.G_gap @ V_new) / g_tot
            V_new = V_inf + (self.V - V_inf) * decay
        self.V = V_new

        target = _sigmoid(p.beta * (self.V - p.v_half))
        if rate_scale == 1.0:
            decay_ca, decay_te = self._decay_ca, self._decay_te
        else:
            decay_ca = np.exp(-dt / (p.tau_calcium * rate_scale))
            decay_te = np.exp(-dt / (p.tau_tension * rate_scale))
        self.calcium = target + (self.calcium - target) * decay_ca
        self.tension = self.calcium + (self.tension - self.calcium) * decay_te

    # ------------------------------------------------------------------------- coupling
    def row_tension(self) -> tuple:
        """Mean tension of the dorsal and ventral muscles of each of the 24 rows."""
        d = (self._row_mask_d @ self.tension) / self._row_n_d
        v = (self._row_mask_v @ self.tension) / self._row_n_v
        return d, v

    def joint_moment(self, kappa_rate: np.ndarray | None = None) -> np.ndarray:
        """(n_links-1,) active bending moment at each mechanical joint, uN*mm.

        Positive is a dorsal bend. Muscle can only pull, so the moment is the *difference*
        of two one-sided tensions rather than a signed quantity in its own right -- a worm
        with both sides fully contracted is rigid and straight, not bent.

        `kappa_rate` is d(kappa)/dt at each joint, and is only read when force-velocity is
        switched on. It is an argument rather than state because the rate belongs to the
        body, not to the muscle: `Simulation` has both and is the honest place to join them.
        Passing nothing keeps the call exactly as it was, which is what every existing caller
        -- tools/moment_ceiling.py among them -- relies on.
        """
        d, v = self.row_tension()
        dj = np.interp(self.joint_s, self.row_pos, d)
        vj = np.interp(self.joint_s, self.row_pos, v)
        if self.p.fv_vmax > 0.0 and kappa_rate is not None:
            # A dorsal muscle shortens as the joint bends dorsally, so its shortening
            # velocity is +d(kappa)/dt and the ventral one's is the negative of that. One
            # array, used with both signs, which is also why the two sides cannot be folded
            # into the moment difference before this point.
            dj = dj * self._force_velocity(kappa_rate)
            vj = vj * self._force_velocity(-kappa_rate)
        return self.joint_gain * (dj - vj)

    def _force_velocity(self, v: np.ndarray) -> np.ndarray:
        """Hill's factor on active tension: < 1 while shortening, > 1 while lengthening.

        Positive `v` is shortening. The concentric branch is the classic hyperbola
        `(1 - x)/(1 + c*x)` in `x = v/vmax`, which is 1 at rest and reaches 0 at vmax; it is
        clipped at zero because a muscle shortening faster than vmax produces no force, not
        negative force, and letting it go negative would turn the antagonist into a driver.
        The eccentric branch saturates at `1 + fv_eccentric` rather than growing without
        bound, which is what real muscle does and what keeps a fast stretch from injecting
        arbitrary energy into the body.
        """
        p = self.p
        x = v / p.fv_vmax
        # Each branch is evaluated over the whole array -- that is what np.where does -- and
        # each has a pole inside the other's domain: the concentric denominator vanishes at
        # x = -1/fv_curvature and the eccentric one at x = +1. Clamping the *input* to each
        # branch's own side keeps both denominators >= 1 everywhere, so the unused half is
        # finite rather than an infinity that is quietly discarded. Nothing downstream would
        # have noticed the infinity, which is exactly the objection: see
        # tests/test_silent_numerics.py.
        xp = np.maximum(x, 0.0)
        xm = np.minimum(x, 0.0)
        short = np.clip((1.0 - xp) / (1.0 + p.fv_curvature * xp), 0.0, None)
        long = 1.0 + p.fv_eccentric * (-xm) / (1.0 - xm)
        return np.where(x >= 0.0, short, long)
