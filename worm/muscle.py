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
        scale = np.where(g_exc > 1e-9, scale, 1.0)
        self.G[:, exc] *= scale[:, None]

    def step(self, s_pre: np.ndarray, dt: float | None = None) -> None:
        """Advance the muscles given the presynaptic activation of every neuron."""
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
        self.calcium = target + (self.calcium - target) * self._decay_ca
        self.tension = self.calcium + (self.tension - self.calcium) * self._decay_te

    # ------------------------------------------------------------------------- coupling
    def row_tension(self) -> tuple:
        """Mean tension of the dorsal and ventral muscles of each of the 24 rows."""
        d = (self._row_mask_d @ self.tension) / self._row_n_d
        v = (self._row_mask_v @ self.tension) / self._row_n_v
        return d, v

    def joint_moment(self) -> np.ndarray:
        """(n_links-1,) active bending moment at each mechanical joint, uN*mm.

        Positive is a dorsal bend. Muscle can only pull, so the moment is the *difference*
        of two one-sided tensions rather than a signed quantity in its own right -- a worm
        with both sides fully contracted is rigid and straight, not bent.
        """
        d, v = self.row_tension()
        dj = np.interp(self.joint_s, self.row_pos, d)
        vj = np.interp(self.joint_s, self.row_pos, v)
        return self.joint_gain * (dj - vj)
