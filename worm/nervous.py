"""The nervous system: 302 graded-potential neurons on the reconstructed connectome."""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import NeuralParams


class NervousSystem:
    """Conductance-based graded-potential network (Wicks 1996 / Kunert 2014).

    State is the membrane potential of every neuron and the synaptic activation of every
    presynaptic terminal. Integration is exponential Euler on both, which is exact for the
    linear part of each equation and therefore stable at step sizes where forward Euler
    would ring: the effective membrane time constant of a heavily-connected neuron such as
    AVAL drops to a couple of milliseconds once its synaptic conductance is included.
    """

    def __init__(self, conn: Connectome, p: NeuralParams, rng: np.random.Generator):
        self.conn = conn
        self.p = p
        self.rng = rng
        n = conn.n

        # Contact counts scaled to conductances once, up front.
        self.G_gap = conn.gap * p.g_gap                     # (N,N) symmetric, nS
        self.G_syn = conn.syn * p.g_syn                     # (N,N) [post, pre], nS
        self.gap_total = self.G_gap.sum(axis=1)             # (N,)
        self.E_pre = conn.syn_reversal.copy()               # (N,) mV, reversal per presyn

        self.g_leak = p.g_leak
        self.E_leak = p.E_leak

        # Slow calcium-activated potassium conductance, present only in the motor classes
        # that are known to oscillate intrinsically. Everything else is purely passive.
        self.g_adapt = np.zeros(n)
        self.g_ca = np.zeros(n)
        self.oscillators = conn.group(*p.oscillator_classes)
        if len(self.oscillators) == 0:
            raise RuntimeError("no neurons matched oscillator_classes=%r"
                               % (p.oscillator_classes,))
        self.g_adapt[self.oscillators] = p.adapt_g
        self.g_ca[self.oscillators] = p.ca_g

        # Steady-state synaptic activation when a presynaptic neuron sits exactly at its
        # own half-activation voltage (phi = 1/2). Used to place the thresholds.
        s_half = 0.5 * p.a_rise / (0.5 * p.a_rise + p.a_decay)

        self.V_th = self._resting_potentials(s_half)
        self.V = self.V_th.copy()
        self.s = np.full(n, s_half)
        self.a = np.full(n, 0.5)
        self.I_noise = np.zeros(n)
        self.I_ext = np.zeros(n)

        # Working in nS / nF / mV / pA / s makes every equation second-based:
        # nF * mV/s == pA and nS * mV == pA.
        self.dt = p.dt
        self._C_nF = p.C_m * 1e-3

        self._noise_decay = np.exp(-p.dt / p.noise_tau)
        self._noise_kick = p.noise_sigma * np.sqrt(1.0 - self._noise_decay ** 2)
        self.gap_iters = 3
        self._adapt_decay = np.exp(-p.dt / p.adapt_tau)

        self.t = 0.0

    # ------------------------------------------------------------------ initialisation
    def _resting_potentials(self, s_half: float) -> np.ndarray:
        """Solve for the network's resting state with every release curve half-activated.

        Kunert et al. (2014) set each neuron's sigmoid midpoint to the potential the
        neuron actually rests at, which leaves the whole network poised on the steep part
        of its transfer function. Without this, most of the connectome sits either silent
        or saturated and the animal has no dynamic range.
        """
        # Chemical synapses contribute a conductance to E_pre, not a coupling to V_pre, so
        # only the gap junctions appear off the diagonal. The matrix is a strictly
        # diagonally dominant M-matrix (g_leak > 0 on every row), hence nonsingular.
        n = self.conn.n
        # The slow potassium conductance is half-activated at rest too, so it belongs in
        # the solve; leaving it out would put the oscillating classes' thresholds tens of
        # millivolts away from where they actually sit.
        # Both intrinsic conductances are half-activated at rest, because their activation
        # curves are centred on the very threshold we are solving for. Including them here
        # is what keeps the fixed point exact.
        A = -self.G_gap.copy()
        A[np.diag_indices(n)] += (self.g_leak
                                  + self.gap_total
                                  + s_half * self.G_syn.sum(axis=1)
                                  + 0.5 * self.g_adapt
                                  + 0.5 * self.g_ca)
        b = (self.g_leak * self.E_leak
             + s_half * (self.G_syn @ self.E_pre)
             + 0.5 * self.g_adapt * self.p.E_K
             + 0.5 * self.g_ca * self.p.E_Ca)
        V = np.linalg.solve(A, b)
        if not np.all(np.isfinite(V)):
            raise RuntimeError("resting-potential solve did not converge")
        return V

    # ------------------------------------------------------------------------- stepping
    def step(self, I_ext: np.ndarray | None = None) -> None:
        p = self.p
        V, s = self.V, self.s

        # Ornstein-Uhlenbeck background current: exact update, so its variance does not
        # depend on dt.
        self.I_noise *= self._noise_decay
        self.I_noise += self._noise_kick * self.rng.standard_normal(V.shape)

        I = self.I_noise
        if I_ext is not None:
            I = I + I_ext

        # Conductances and their driving potentials.
        gs = self.G_syn @ s                       # (N,) total synaptic conductance
        Es = self.G_syn @ (s * self.E_pre)        # (N,) conductance-weighted reversal sum
        g_ad = self.g_adapt * self.a              # (N,) slow K conductance
        # Regenerative calcium conductance, activating instantaneously with voltage. This
        # is the positive-feedback limb: depolarising opens it, and it pulls towards
        # +120 mV, which opens it further.
        g_c = self.g_ca * _sigmoid(p.ca_beta * (V - self.V_th))
        g_tot = self.g_leak + self.gap_total + gs + g_ad + g_c
        fixed = (self.g_leak * self.E_leak + Es
                 + g_ad * p.E_K + g_c * p.E_Ca + I)
        decay = np.exp(-g_tot * self.dt / self._C_nF)

        # Embedded membrane time constants span 0.1 ms to 150 ms across the connectome, so
        # a strongly gap-coupled neuron such as AVAL equilibrates several times within one
        # step. Exponential Euler handles that exactly on the diagonal; the gap-junction
        # coupling is then refined by a few fixed-point passes, which converge because the
        # conductance matrix is diagonally dominant. This buys implicit-solver accuracy for
        # the cost of two extra matrix-vector products, instead of an N^3 solve per step.
        V_new = V
        for _ in range(self.gap_iters):
            V_inf = (fixed + self.G_gap @ V_new) / g_tot
            V_new = V_inf + (V - V_inf) * decay
        self.V = np.clip(V_new, p.v_clamp[0], p.v_clamp[1])

        # Presynaptic release, driven by the *pre-update* voltage so that the network has
        # a consistent one-step delay everywhere rather than an index-order dependence.
        phi = _sigmoid(p.beta * (V - self.V_th))

        # The slow conductance tracks the same sigmoid, but lags it by adapt_tau. That lag
        # is the whole oscillator: by the time the conductance has built up enough to shut
        # the neuron off, the neuron has been depolarised for most of a half-cycle.
        self.a = phi + (self.a - phi) * self._adapt_decay

        rise = p.a_rise * phi
        rate = rise + p.a_decay
        s_inf = rise / rate
        self.s = s_inf + (s - s_inf) * np.exp(-rate * self.dt)

        self.t += self.dt

    # -------------------------------------------------------------------------- readout
    def activation(self) -> np.ndarray:
        """Normalised 0..1 activity, using each neuron's own release curve."""
        return _sigmoid(self.p.beta * (self.V - self.V_th))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    # Numerically stable logistic: avoids overflow warnings on strongly hyperpolarised
    # neurons, which do occur transiently after a mechanosensory hit.
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    e = np.exp(x[~pos])
    out[~pos] = e / (1.0 + e)
    return out
