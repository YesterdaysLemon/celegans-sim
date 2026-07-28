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

        # Reversal potential per *synapse*, not per presynaptic neuron.
        #
        # Which way a synapse pushes is a property of the receptor, and receptors are
        # expressed by the postsynaptic cell -- so the same transmitter can excite one
        # target and inhibit another. C. elegans makes that unusually concrete: glutamate
        # opens the AMPA-type GLR-1 on some cells and the glutamate-gated *chloride*
        # channels AVR-14, AVR-15 and GLC-1/2/3 on others, which is why ivermectin works
        # on this animal at all. Collapsing every glutamatergic synapse to one reversal is
        # therefore a known simplification rather than a fact, and this model already
        # departs from transmitter identity in the other direction for AVL and DVB, whose
        # GABA lands on the cation channel EXP-1 and so depolarises its targets.
        #
        # The (post, pre) matrix costs 730 kB at N=302 and no arithmetic at all: the step
        # already formed G_syn @ (s * E_pre), which becomes (G_syn * E) @ s with the
        # product taken once here. With no overrides configured every row is its
        # presynaptic neuron's own reversal, and the two forms are the same sum with the
        # multiplications reassociated -- so the model is identical to within floating
        # point, not bit-for-bit. Measured over 20 s of the full closed loop against the
        # previous code: membrane potentials and synaptic activations agree exactly, body
        # node positions and net speed to 2e-15 relative. That is the same order as
        # changing BLAS, and well inside the 4e-14 mV the noiseless fixed point is held to.
        self.E_syn = np.broadcast_to(self.E_pre, (n, n)).copy()      # (N,N) [post, pre]
        self._apply_receptor_overrides(conn, p)
        self.GE_syn = self.G_syn * self.E_syn

        self.g_leak = p.g_leak
        self.E_leak = p.E_leak

        # Steady-state synaptic activation when a presynaptic neuron sits exactly at its
        # own half-activation voltage (phi = 1/2). Used to place the thresholds.
        s_half = 0.5 * p.a_rise / (0.5 * p.a_rise + p.a_decay)

        # Morris-Lecar conditional oscillator, in the motor classes known to oscillate.
        # Everything else is purely passive: g_ca and g_adapt stay zero there, so the rest
        # of the connectome is untouched by any of this.
        #
        # Both conductances scale with the neuron's own total resting conductance, so a
        # unit the connectome loads heavily gets proportionally more channel. Without this
        # the eightfold spread of resting conductance across the B class turns into the
        # difference between silence and saturation. See NeuralParams for the measurements.
        # g_rest is also read by the sensory system, which scales its input currents the
        # same way and for the same reason.
        self.g_rest = self.g_leak + self.gap_total + s_half * self.G_syn.sum(axis=1)
        g_rest = self.g_rest
        self.g_adapt = np.zeros(n)
        self.g_ca = np.zeros(n)
        self.oscillators = conn.group(*p.oscillator_classes)
        if len(self.oscillators) == 0:
            raise RuntimeError("no neurons matched oscillator_classes=%r"
                               % (p.oscillator_classes,))
        self.g_ca[self.oscillators] = p.ca_ratio * g_rest[self.oscillators]
        self.g_adapt[self.oscillators] = p.adapt_ratio * g_rest[self.oscillators]
        # The backward cord is scaled separately -- see NeuralParams.a_class_scale.
        a_class = conn.group("DA", "VA")
        a_class = np.intersect1d(a_class, self.oscillators)
        self.g_ca[a_class] *= p.a_class_scale
        self.g_adapt[a_class] *= p.a_class_scale

        # The command interneurons get a Morris-Lecar pair of their own, kept separate from
        # the motor classes' because the two do unrelated jobs on unrelated timescales: the
        # motor neurons' potassium gate is the recovery limb of a 1 Hz oscillator, while
        # this one has to time a forward run that lasts tens of seconds.
        #
        # The adaptation went in first, on its own, on the argument that these cells were
        # not being made into oscillators but only made to get tired. Measured, that was
        # wrong, and the number that says so is the duration of a reversal: adaptation
        # alone raised the crossing rate from 1.7 to 30 per minute but every episode lasted
        # 0.07 s, one fifteenth of an undulation cycle, at every setting tried. A body
        # cannot reverse in 0.07 s. Fatigue lowers the mean of a noisy signal towards a
        # threshold; it does not make the far side of that threshold a place the animal can
        # stay. Persistence needs the regenerative limb -- which is the same construction,
        # and the same justification, as the B-class motor neurons above, and is what the
        # recordings describe: Mellem et al. (2008) find RMD frankly bistable at -73 or
        # -10 mV, and AVA holds depolarised plateaus lasting seconds. Zero by default.
        self.command_fwd = conn.group(*p.command_forward)
        self.command_bwd = conn.group(*p.command_backward)
        self.command = np.union1d(self.command_fwd, self.command_bwd)
        self.g_adapt[self.command] += p.command_adapt_ratio * g_rest[self.command]
        # The regenerative half goes only where it is asked for, because which command
        # cell carries it turns out to matter more than how much. AVB and PVC gap-junction
        # onto the B cord with 58 contacts and AVA/AVD/AVE onto the A cord with 102, and
        # AVB's resting potential is the bifurcation parameter that poises the B units --
        # so a regenerative conductance on AVB is not a change to the decision, it is a
        # change to the gait's operating point, delivered through the connectome. Measured
        # both ways below; see NeuralParams.
        self.command_ca = np.intersect1d(self.command, conn.group(*p.command_ca_classes))
        self.g_ca[self.command_ca] += p.command_ca_ratio * g_rest[self.command_ca]

        # Where each cell's calcium activation sits relative to its own rest. Per-neuron,
        # because the command layer needs a different answer from the motor classes and
        # the reason is measured. At the motor neurons' ca_offset of 0 the gate is half
        # open at rest, so the conductance is a standing depolarising load -- fine there,
        # because the whole gait was tuned around it. On the command interneurons it is
        # not fine: AVB's resting potential is the bifurcation parameter for the entire
        # B-class cord (see the note below on why that needs no parameter of its own), so
        # depolarising AVB detunes the amplifier that carries the wave down the body.
        # Measured, with the direction gate held so that the animal never reversed at all:
        # net/path still fell from 0.783 to 0.400 and speed from 0.185 to 0.091. That
        # isolates it -- the cost is not the reversals, it is the resting load. Placing
        # the half-activation above rest closes the gate at rest, so the conductance
        # contributes nothing until the cell depolarises and the operating point is left
        # where it was.
        ca_offset = np.full(n, p.ca_offset)
        ca_offset[self.command_ca] = p.command_ca_offset

        # Gate values at rest. Because each half-activation is a fixed offset from that
        # neuron's own resting potential, these are constants -- which is what keeps the
        # threshold solve linear and its fixed point exact.
        self.m0 = 0.5 * (1.0 + np.tanh(-ca_offset / p.ca_slope))
        self.n0 = 0.5 * (1.0 + np.tanh(-p.k_offset / p.k_slope))

        self.V_th = self._resting_potentials(s_half)
        self.ca_vhalf = self.V_th + ca_offset
        self.k_vhalf = self.V_th + p.k_offset

        self.V = self.V_th.copy()
        self.s = np.full(n, s_half)
        self.a = np.full(n, self.n0)
        self.I_noise = np.zeros(n)
        self.I_ext = np.zeros(n)

        # Working in nS / nF / mV / pA / s makes every equation second-based:
        # nF * mV/s == pA and nS * mV == pA.
        self.dt = p.dt
        self._C_nF = p.C_m * 1e-3

        self._noise_decay = np.exp(-p.dt / p.noise_tau)
        self._noise_kick = p.noise_sigma * np.sqrt(1.0 - self._noise_decay ** 2)
        self.gap_iters = 3
        # Per-neuron, because the command layer's adaptation is fifty times slower than
        # the motor classes'. Broadcasting keeps `step` unchanged. Applied only when the
        # command conductance is actually present: with the ratio at zero those cells
        # carry no adaptation current, so retiming a gate that multiplies zero would
        # change nothing except the value this array reports, and leaving it alone keeps
        # "zero reproduces the previous model" true of every state variable rather than
        # only of the ones that matter.
        adapt_tau = np.full(n, p.adapt_tau)
        if p.command_adapt_ratio > 0.0:
            adapt_tau[self.command] = p.command_adapt_tau
        self._adapt_decay = np.exp(-p.dt / adapt_tau)

        self.t = 0.0

    # ------------------------------------------------------------------ initialisation
    def _apply_receptor_overrides(self, conn: Connectome, p: NeuralParams) -> None:
        """Retarget named synapses onto an inhibitory receptor. Default: none.

        Only one override is defined so far -- reciprocal inhibition between the forward
        and backward command pools -- and it is off unless `command_cross_inhibition` is
        raised. See NeuralParams for what it is for and what it is worth.
        """
        x = float(p.command_cross_inhibition)
        if x <= 0.0:
            return
        fwd = conn.group(*p.command_forward)
        bwd = conn.group(*p.command_backward)
        if len(fwd) == 0 or len(bwd) == 0:
            raise RuntimeError("command pools did not match the connectome: %r / %r"
                               % (p.command_forward, p.command_backward))
        # Blend rather than switch, so the coefficient is continuous and 0 is exactly the
        # unmodified model. Both directions of the reciprocal pair, and only the chemical
        # synapses -- the gap junctions between the pools are ohmic and have no reversal
        # to change.
        e = (1.0 - x) * p.E_exc + x * p.E_inh
        self.E_syn[np.ix_(fwd, bwd)] = e
        self.E_syn[np.ix_(bwd, fwd)] = e

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
        # The intrinsic gates are open by m0 and n0 at rest, by construction: their
        # activation curves are placed at fixed offsets from the very potential being
        # solved for. Including them at those constant values is what makes this fixed
        # point exact rather than approximate, and it is why the solve stays linear even
        # though the underlying currents are not.
        A = -self.G_gap.copy()
        A[np.diag_indices(n)] += (self.g_leak
                                  + self.gap_total
                                  + s_half * self.G_syn.sum(axis=1)
                                  + self.n0 * self.g_adapt
                                  + self.m0 * self.g_ca)
        b = (self.g_leak * self.E_leak
             + s_half * self.GE_syn.sum(axis=1)
             + self.n0 * self.g_adapt * self.p.E_K
             + self.m0 * self.g_ca * self.p.E_Ca)
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
        Es = self.GE_syn @ s                      # (N,) conductance-weighted reversal sum
        g_ad = self.g_adapt * self.a              # (N,) delayed-rectifier K conductance
        # Regenerative calcium conductance, activating instantaneously with voltage: the
        # positive-feedback limb that folds the voltage nullcline and makes a limit cycle
        # possible. Morris-Lecar form, m_inf = 0.5(1 + tanh((V - V_m)/theta_m)).
        g_c = self.g_ca * 0.5 * (1.0 + np.tanh((V - self.ca_vhalf) / p.ca_slope))
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

        # Potassium activation relaxes towards its own voltage-dependent steady state with
        # time constant tau_n. This is the slow, recovering limb of the Morris-Lecar pair.
        n_inf = 0.5 * (1.0 + np.tanh((V - self.k_vhalf) / p.k_slope))
        self.a = n_inf + (self.a - n_inf) * self._adapt_decay

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
