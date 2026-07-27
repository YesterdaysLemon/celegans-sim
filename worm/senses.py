"""Sensory transduction: turning the state of the world into currents in real neurons.

Every modality here is routed to the neurons that actually carry it in C. elegans, and
where the biology is asymmetric the model is too. Three cases are worth calling out:

* ASEL and ASER are a matched ON/OFF pair. ASEL depolarises when the concentration of a
  water-soluble attractant rises, ASER when it falls (Suzuki et al. 2008, Nature 454:114).
  That single opponent pair is most of what makes salt chemotaxis work.
* AWC is an OFF cell: it is *silenced* by odour and fires on its removal, which is why
  removing an attractant triggers a reversal.
* Sensation is differential, not absolute. Each channel keeps an adapting baseline and
  reports the deviation from it, so the animal responds to change. A worm sitting in a
  uniform concentration, however high, stops responding to it within seconds.
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import SensoryParams, WorldParams
from .world import World


class Senses:
    def __init__(self, conn: Connectome, p: SensoryParams, world_p: WorldParams,
                 body_n_links: int, proprio_reach: float, dt: float):
        self.conn = conn
        self.p = p
        self.dt = dt

        idx = conn.select
        # --- chemosensation -------------------------------------------------------------
        self.ase_on = idx("ASEL")                      # rising attractant
        self.ase_off = idx("ASER")                     # falling attractant
        self.awc = idx("AWCL", "AWCR")                 # volatile odour, OFF cell
        self.awa = idx("AWAL", "AWAR")                 # volatile odour, ON cell
        self.ash = idx("ASHL", "ASHR")                 # nociception, osmotic, nose touch
        self.adl = idx("ADLL", "ADLR")                 # volatile repellent
        self.ask = idx("ASKL", "ASKR")

        # --- thermosensation ------------------------------------------------------------
        self.afd = idx("AFDL", "AFDR")

        # --- oxygen ---------------------------------------------------------------------
        self.urx = idx("URXL", "URXR", "AQR", "PQR")

        # --- mechanosensation -----------------------------------------------------------
        self.touch_anterior = idx("ALML", "ALMR", "AVM")
        self.touch_posterior = idx("PLML", "PLMR", "PVM")
        self.nose_touch = idx("OLQDL", "OLQDR", "OLQVL", "OLQVR",
                              "FLPL", "FLPR", "CEPDL", "CEPDR", "CEPVL", "CEPVR")

        # --- food, sensed by the dopaminergic mechanoreceptors --------------------------
        self.dopaminergic = idx("CEPDL", "CEPDR", "CEPVL", "CEPVR",
                                "ADEL", "ADER", "PDEL", "PDER")

        # --- locomotory command ---------------------------------------------------------
        self.avb = idx("AVBL", "AVBR", "PVCL", "PVCR")   # forward
        self.ava = idx("AVAL", "AVAR", "AVDL", "AVDR", "AVEL", "AVER")   # backward

        # --- proprioception -------------------------------------------------------------
        self.db = idx(*["DB%02d" % i for i in range(1, 8)])
        self.vb = idx(*["VB%02d" % i for i in range(1, 12)])
        self.da = idx(*["DA%02d" % i for i in range(1, 10)])
        self.va = idx(*["VA%02d" % i for i in range(1, 13)])
        joint_s = np.arange(1, body_n_links) / body_n_links
        self.W_b = _receptive_fields(conn, self.db, self.vb, joint_s, proprio_reach, +1)
        self.W_a = _receptive_fields(conn, self.da, self.va, joint_s, proprio_reach, -1)

        # The head oscillator. Dorsal and ventral head motor neurons, wired as a
        # resistance reflex against the curvature of the head itself.
        head_d = idx("RMDDL", "RMDDR", "SMDDL", "SMDDR", "SMBDL", "SMBDR")
        head_v = idx("RMDVL", "RMDVR", "SMDVL", "SMDVR", "SMBVL", "SMBVR")
        head_win = (joint_s <= p.head_reach).astype(float)
        if head_win.sum() == 0:
            head_win[0] = 1.0
        self._head_window = head_win / head_win.sum()
        # The head reflex reads one scalar -- the mean curvature of the head -- so the
        # per-neuron part is just its sign: negative for the dorsal pool, positive for the
        # ventral one. Keeping them separate lets the scalar be filtered in time once.
        self.W_head_sign = np.zeros(conn.n)
        self.W_head_sign[head_d] = -1.0        # a dorsal bend inhibits the dorsal benders
        self.W_head_sign[head_v] = +1.0

        # --- adapting baselines ---------------------------------------------------------
        self.c_adapt = None
        self.odour_adapt = None
        self.t_adapt = None
        self.touch_state = np.zeros(2)
        self.poke = np.zeros(2)          # (anterior, posterior) externally driven touch

        self.head_signal = 0.0
        self._head_decay = np.exp(-dt / p.head_tau)
        self.prop_adapt = np.zeros(conn.n)
        self._prop_adapt_rate = 1.0 - np.exp(-dt / p.proprio_tau_adapt)
        self._chem_decay = np.exp(-dt / p.chemo_tau_adapt)
        self._therm_decay = np.exp(-dt / p.thermo_tau_adapt)
        self._touch_decay = np.exp(-dt / p.touch_tau)

        self.readout = {}

    def sense(self, world: World, nodes: np.ndarray, contact: np.ndarray,
              curvature: np.ndarray, activation: np.ndarray) -> np.ndarray:
        """Build the (N,) external current vector for this step."""
        p = self.p
        n = self.conn.n
        I = np.zeros(n)

        nose = nodes[0]
        mid = nodes[len(nodes) // 2]

        # ---------------------------------------------------------------- chemosensation
        c = float(world.sample(world.attractant, nose[0], nose[1]))
        if self.c_adapt is None:
            self.c_adapt = c
        dc = c - self.c_adapt
        self.c_adapt += (c - self.c_adapt) * (1.0 - self._chem_decay)

        I[self.ase_on] += p.chemo_gain * dc
        I[self.ase_off] -= p.chemo_gain * dc
        # Volatile odour is taken from the same lawn, sensed a little more slowly.
        o = c
        if self.odour_adapt is None:
            self.odour_adapt = o
        do = o - self.odour_adapt
        self.odour_adapt += (o - self.odour_adapt) * (1.0 - self._chem_decay * 0.5)
        I[self.awa] += p.chemo_gain * 0.6 * do
        I[self.awc] -= p.chemo_gain * 0.6 * do      # OFF cell: excited by odour removal

        rep = float(world.sample(world.repellent, nose[0], nose[1]))
        I[self.ash] += p.chemo_gain * 1.6 * rep
        I[self.adl] += p.chemo_gain * 0.8 * rep
        I[self.ask] -= p.chemo_gain * 0.3 * rep

        # ---------------------------------------------------------------- thermosensation
        T = float(world.temperature(nose[0], nose[1]))
        if self.t_adapt is None:
            self.t_adapt = p.cultivation_temp
        dT = T - self.t_adapt
        self.t_adapt += (T - self.t_adapt) * (1.0 - self._therm_decay)
        # AFD is a warm receptor above the cultivation temperature and silent below it.
        I[self.afd] += p.thermo_gain * np.clip(dT, -0.5, None)

        # ------------------------------------------------------------------------- oxygen
        o2 = float(world.oxygen(nose[0], nose[1]))
        I[self.urx] += p.oxygen_gain * (o2 - p.oxygen_preferred)

        # ----------------------------------------------------------------- mechanosensation
        mag = np.hypot(contact[:, 0], contact[:, 1])
        half = len(mag) // 2
        ant = float(mag[:half].sum()) + self.poke[0]
        post = float(mag[half:].sum()) + self.poke[1]
        self.touch_state *= self._touch_decay
        self.touch_state += np.array([ant, post])
        self.poke *= 0.0
        I[self.touch_anterior] += p.touch_gain * self.touch_state[0]
        I[self.touch_posterior] += p.touch_gain * self.touch_state[1]
        I[self.nose_touch] += p.touch_gain * 0.5 * float(mag[0] + mag[1])

        # --------------------------------------------------------------------------- food
        f = float(world.sample(world.food, nose[0], nose[1]))
        I[self.dopaminergic] += p.food_gain * f

        # --------------------------------------------------------- locomotory command bias
        I[self.avb] += p.tonic_forward

        # ------------------------------------------------------------------ proprioception
        # Normalised curvature: 5 rad/mm is roughly the peak a crawling worm reaches.
        k = np.clip(curvature / 5.0, -2.0, 2.0)
        gate_fwd = float(np.mean(activation[self.avb]))
        gate_bwd = float(np.mean(activation[self.ava]))
        # The B and A motor classes only oscillate when their command interneuron is
        # engaged (Kawano et al. 2011; Fouad et al. 2018), so the proprioceptive drive is
        # gated by AVB and AVA respectively. Without that gate the forward and backward
        # wave generators fight each other continuously.
        # Forward and backward are alternatives, not a blend: a real animal committed to a
        # reversal is not also running the forward wave generator at half strength. Cubing
        # the command-interneuron activities before normalising turns a modest difference
        # in AVB-vs-AVA drive into a near-exclusive choice, which is what the mutually
        # inhibitory command circuit does in the animal.
        gate_fwd, gate_bwd = gate_fwd ** 3, gate_bwd ** 3
        gate_sum = gate_fwd + gate_bwd + 1e-9
        # Stretch receptors saturate, and saying so here matters: without it a sharp body
        # bend delivers enough current to drive a motor neuron straight through the bottom
        # of its physiological range and pin it there.
        # Adapt out the static component before the receptor saturates on it, so the whole
        # dynamic range is spent on the part of the bend that is actually changing.
        raw = (self.W_b @ k) * (gate_fwd / gate_sum) + (self.W_a @ k) * (gate_bwd / gate_sum)
        self.prop_adapt += (raw - self.prop_adapt) * self._prop_adapt_rate
        I += np.tanh(raw - self.prop_adapt) * p.proprio_gain
        # The head reflex runs whichever way the animal is going -- it is what keeps the
        # nose sweeping, and the sweep is what steering acts on. It is low-pass filtered by
        # the receptor's own kinetics, which is what keeps the loop out of its fast mode.
        raw = float(np.dot(self._head_window, k))
        self.head_signal += (raw - self.head_signal) * (1.0 - self._head_decay)
        I += self.W_head_sign * (np.tanh(self.head_signal) * p.head_proprio_gain)

        self.readout = {
            "attractant": c, "d_attractant": dc, "repellent": rep,
            "temperature": T, "oxygen": o2, "food": f,
            "touch": float(self.touch_state.sum()),
            "gate_forward": gate_fwd, "gate_backward": gate_bwd,
        }
        return I


def _output_position(conn: Connectome, i: int) -> float:
    """Where along the body a motor neuron actually acts, from its own neuromuscular map.

    The reflex has to be referenced to the piece of body the neuron moves, not to where
    its cell body happens to sit. Those are different: DB and VB somas are interleaved
    along the ventral cord in a way that does not line up dorsoventrally, so referencing
    the receptive field to the soma silently gives the dorsal and ventral halves of the
    circuit different views of the same bend, and they stop working as an antagonistic
    pair. Weighting by NMJ contacts fixes that, and is what the anatomy means anyway.
    """
    w = conn.nmj[:, i]
    total = w.sum()
    if total <= 0:
        return float(conn.soma_pos[i])
    return float((w * conn.muscle_pos).sum() / total)


def _receptive_fields(conn: Connectome, dorsal: np.ndarray, ventral: np.ndarray,
                      joint_s: np.ndarray, reach: float, direction: int) -> np.ndarray:
    """(N, n_joints) matrix mapping body curvature to proprioceptive current.

    `direction` is +1 for a field anterior to the neuron's output region and -1 for
    posterior. B-type motor neurons read the region in front of them, which is what makes
    the undulatory wave travel head-to-tail; A-type motor neurons read behind them, and
    drive the wave the other way for backward locomotion.

    Sign convention: positive curvature is a dorsal bend. A dorsal bend anterior to a DB
    neuron excites it, and DB contracts dorsal muscle, so the bend is copied posteriorly
    in the same direction -- which is precisely what Wen et al. (2012) measured.
    """
    W = np.zeros((conn.n, len(joint_s)))
    for group, sign in ((dorsal, +1.0), (ventral, -1.0)):
        for i in group:
            s0 = _output_position(conn, int(i))
            if direction > 0:
                lo, hi = s0 - reach, s0
            else:
                lo, hi = s0, s0 + reach
            w = ((joint_s >= lo) & (joint_s <= hi)).astype(float)
            if w.sum() == 0:
                # A neuron whose field runs off the end of the body reads the nearest
                # joint instead, rather than going deaf.
                w[np.argmin(np.abs(joint_s - np.clip(s0, 0, 1)))] = 1.0
            W[i] = sign * w / w.sum()
    return W
