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
                 body_n_links: int, proprio_reach: float, dt: float,
                 g_rest: np.ndarray | None = None, rng: np.random.Generator | None = None):
        self.conn = conn
        self.p = p
        self.dt = dt
        self.rng = np.random.default_rng(0) if rng is None else rng

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
        self.nsm = idx("NSML", "NSMR")

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
        # A second pair at the shorter on-food reach. The animal is blended between the
        # two rather than having its fields rebuilt each step, which is an approximation
        # to a continuously varying reach and is smooth in the same direction.
        self.W_b_food = _receptive_fields(conn, self.db, self.vb, joint_s,
                                          p.proprio_reach_food, +1)
        self.W_a_food = _receptive_fields(conn, self.da, self.va, joint_s,
                                          p.proprio_reach_food, -1)

        # The head oscillator. Dorsal and ventral head motor neurons, wired as a
        # resistance reflex against the curvature of the head itself.
        head_d = idx("RMDDL", "RMDDR", "SMDDL", "SMDDR", "SMBDL", "SMBDR")
        head_v = idx("RMDVL", "RMDVR", "SMDVL", "SMDVR", "SMBVL", "SMBVR")
        head_win = (joint_s <= p.head_reach).astype(float)
        if head_win.sum() == 0:
            head_win[0] = 1.0
        self._head_window = head_win / head_win.sum()
        # Sign only, for the lumped reflex: negative for the dorsal pool, positive for the
        # ventral one, so one filtered scalar can drive both.
        self.W_head_sign = np.zeros(conn.n)
        self.W_head_sign[head_d] = -1.0        # a dorsal bend inhibits the dorsal benders
        self.W_head_sign[head_v] = +1.0
        # And the distributed version: each head motor neuron reads the curvature of the
        # piece of body *it* moves, rather than all of them sharing one average. See
        # SensoryParams.head_distributed.
        self.W_head = _head_fields(conn, head_d, head_v, joint_s, p.head_field)

        # Proprioceptive drive is delivered as a current, but what a motor neuron actually
        # responds to is the voltage that current produces, and that is the current divided
        # by the cell's input conductance. Across the B class that conductance spans 0.63
        # to 3.20 nS, so a uniform current hits the small posterior units five times harder
        # than the large anterior ones. Left uncorrected it tilts the whole wave: measured
        # here, tail bending amplitude ran 3.5x the head's at equal bending stiffness, and
        # the posterior segments free-ran and dragged the wave backwards.
        #
        # Scaling the current by each target's own resting conductance says that a stretch
        # receptor makes proportionally more synapses onto a larger cell, which is both the
        # ordinary assumption and the same normalisation the intrinsic channels use. Each
        # channel is normalised over its own targets so that proprio_gain and
        # head_proprio_gain keep the magnitudes they were calibrated at.
        if g_rest is None:
            self.g_scale_prop = np.ones(conn.n)
            self.g_scale_head = np.ones(conn.n)
        else:
            self.g_scale_prop = _normalise(g_rest, np.abs(self.W_b).sum(axis=1)
                                           + np.abs(self.W_a).sum(axis=1))
            self.g_scale_head = _normalise(g_rest, np.abs(self.W_head_sign))

        # --- adapting baselines ---------------------------------------------------------
        self.c_adapt = None
        self.odour_adapt = None
        self.t_adapt = None
        self.o2_adapt = None
        self.rep_adapt = None
        self.touch_state = np.zeros(2)
        self.poke = np.zeros(2)          # (anterior, posterior) externally driven touch
        # Habituation. One resource per touch field, full at 1.0. See SensoryParams.
        self.touch_avail = np.ones(2)
        self._hab_use = float(p.touch_habituation_use)
        self._hab_recover = 1.0 / p.touch_habituation_tau
        self._habituates = self._hab_use > 0.0

        # Which way the animal is currently committed to going. Only read when the gate
        # is latched; see SensoryParams.gate_latched.
        self.going_forward = True

        # The omega turn. Amplitude of the transient currently being delivered, the number
        # of steps the reversal that earned it lasted, and the ventral head pool it goes
        # to. See SensoryParams.omega_current.
        self.omega = 0.0
        self.omega_sign = 1.0        # +1 ventral, -1 dorsal; see omega_ventral_fraction
        self._rev_steps = 0
        self._omega_decay = np.exp(-dt / p.omega_tau)
        self._omega_v = conn.select(*p.omega_ventral)
        self._omega_d = conn.select(*p.omega_dorsal)
        self._omega_ref_n = max(1.0, p.omega_ref_reversal / dt)
        if p.omega_current > 0.0 and not (len(self._omega_v) and len(self._omega_d)):
            raise ValueError("omega pools matched nothing in this connectome: %r / %r"
                             % (p.omega_ventral, p.omega_dorsal))
        # The body part whose wave is quieted during a turn is defined by anatomy rather
        # than a second fitted extent: every A/B proprioceptive motor neuron whose existing
        # receptive-field reach overlaps the most posterior member of the omega pool. The
        # head reflex is handled separately below because it is a different map.
        omega_cells = np.unique(np.concatenate((self._omega_v, self._omega_d)))
        omega_extent = max((_output_position(conn, int(i)) for i in omega_cells), default=0.0)
        prop_targets = (np.abs(self.W_b).sum(axis=1) + np.abs(self.W_a).sum(axis=1)) > 0
        output_pos = np.array([_output_position(conn, i) for i in range(conn.n)])
        self._omega_wave_body = prop_targets & (
            output_pos <= omega_extent + p.proprio_reach + 1e-12)

        # Scalar for the lumped reflex, one per neuron for the distributed one.
        self.head_signal = np.zeros(conn.n) if p.head_distributed else 0.0
        self._head_decay = np.exp(-dt / p.head_tau)
        # The cascade. `head_stages` first-order lags in series, each carrying
        # `head_tau / stages`, so that at one stage this is precisely the filter above and
        # the arithmetic below reduces to the single line it replaces. See
        # SensoryParams.head_stages for why series and not parallel.
        self._head_stages = max(1, int(p.head_stages))
        # Zero means subdivide head_tau, whose ceiling is a pure delay of head_tau and is
        # measured to be too small; a positive value gives the cascade its own lag budget.
        stage_tau = p.head_stage_tau if p.head_stage_tau > 0.0 else p.head_tau / self._head_stages
        self._head_stage_decay = np.exp(-dt / stage_tau)
        # One row per stage. Only allocated past the first when there is a cascade, so the
        # shipped configuration carries no extra state at all.
        self._head_chain = (
            np.zeros((self._head_stages - 1, conn.n) if p.head_distributed
                     else (self._head_stages - 1,))
            if self._head_stages > 1 else None
        )
        # Ring buffer for the head reflex's transport delay. Sized in steps from a delay
        # in seconds, so the delay the loop actually sees does not depend on dt. Length
        # zero means no buffer and the previous behaviour exactly.
        self._head_delay_n = max(0, int(round(p.head_delay / dt)))
        # Buffers the *curvature*, not the reduced signal, so the delay applies whichever
        # reflex form is in use and sits where a transduction delay physically would --
        # between the strain and the receptor, ahead of any spatial pooling. The first
        # version buffered the lumped scalar only, which silently made head_delay a no-op
        # in distributed mode and turned a whole sweep into noise.
        self._head_hist = np.zeros((self._head_delay_n + 1, body_n_links - 1))
        self._head_hist_i = 0
        self.prop_adapt = np.zeros(conn.n)
        # Every one-minus-a-decay below is `-expm1(-x)` rather than `1 - exp(-x)`, and the
        # reason is reproducibility rather than accuracy.
        #
        # These x are dt/tau, which at dt = 0.5 ms runs from 5.6e-07 to 1.4e-03. So
        # exp(-x) is a hair under 1, and subtracting it from 1 throws away most of the
        # mantissa: the result keeps roughly 12 good digits instead of 16, and *any*
        # last-ulp difference in the platform's exp -- a different numpy, a different
        # libm, a different CPU -- lands squarely in the gap that leaves.
        #
        # It has already happened. Re-exporting an unmodified checkout on a different
        # machine moved MOD_RATE_DOPAMINE from ...751507e-05 to ...762609e-05 with nothing
        # in the repository changed (#58). The tolerance is not the issue -- 1e-12 on an
        # adaptation rate changes no result -- but the exported model is supposed to be a
        # function of the repository, and while these are computed this way it is a
        # function of the repository *and* the machine that last ran the exporter. That
        # undermines the port's central claim: whatever the two implementations disagree
        # about, it cannot be the setup, because both read the same numbers out of one
        # file.
        #
        # Measured over the ten exported rates, the relative error of `1 - exp` against
        # `expm1` runs 3.7e-14 (touch_rate) to 6.5e-12 (the egg-laying resource recovery,
        # whose tau is by far the longest). expm1 is exact for small x and identical for
        # large, so there is no trade being made here.
        #
        # `_odour_rate` and `_touch_rate` used to be `1.0 - self._odour_decay` and
        # `1.0 - self._touch_decay`, which is the same cancellation wearing a different
        # shape. Deriving them from the decay made the pair sum to exactly 1, which looks
        # like a conservation property and is not one: both are used as `x += (target - x)
        # * rate`, where the decay never appears, so nothing was relying on it.
        self._prop_adapt_rate = -np.expm1(-dt / p.proprio_tau_adapt)
        self._chem_decay = np.exp(-dt / p.chemo_tau_adapt)
        self._odour_decay = np.exp(-dt / (2.0 * p.chemo_tau_adapt))
        self._odour_rate = -np.expm1(-dt / (2.0 * p.chemo_tau_adapt))
        self._therm_decay = np.exp(-dt / p.thermo_tau_adapt)
        self._o2_rate = -np.expm1(-dt / p.oxygen_tau_adapt)
        self._rep_rate = -np.expm1(-dt / p.repellent_tau_adapt)
        self._touch_decay = np.exp(-dt / p.touch_tau)
        self._touch_rate = -np.expm1(-dt / p.touch_tau)

        self.readout = {}

    def sense(self, world: World, nodes: np.ndarray, contact: np.ndarray,
              curvature: np.ndarray, activation: np.ndarray,
              mods=None) -> np.ndarray:
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
        # "A little more slowly" means twice the time constant. It used to read
        #     odour_adapt += (o - odour_adapt) * (1 - chem_decay * 0.5)
        # where chem_decay is exp(-dt/tau) and so is very close to 1: the bracket is
        # therefore about 0.5 *per step* whatever the step is, giving an adaptation time
        # constant of roughly 2 dt -- one millisecond at the shipped step, not seven
        # seconds. AWA and AWC were adapting out any odour within two timesteps, so the
        # entire volatile pathway was deaf, and how deaf depended on dt. AWC is the OFF
        # cell whose job is to fire when an attractant is *removed*, which is one of the
        # better characterised reversal triggers in the animal, so this was not a small
        # thing to have switched off.
        self.odour_adapt += (o - self.odour_adapt) * self._odour_rate
        I[self.awa] += p.chemo_gain * 0.6 * do
        I[self.awc] -= p.chemo_gain * 0.6 * do      # OFF cell: excited by odour removal

        rep = float(world.sample(world.repellent, nose[0], nose[1]))
        if self.rep_adapt is None:
            self.rep_adapt = rep
        drep = rep - self.rep_adapt
        self.rep_adapt += (rep - self.rep_adapt) * self._rep_rate
        # Tonic and differential, as for oxygen. The tonic part sets how much the animal
        # reverses near a drop at all; the differential part is what makes those reversals
        # happen while it is heading *into* the drop rather than out of it, which is the
        # only version that gets it anywhere. See SensoryParams.repellent_d_gain.
        I[self.ash] += p.chemo_gain * 1.6 * rep + p.repellent_d_gain * drep
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
        if self.o2_adapt is None:
            self.o2_adapt = o2
        do2 = o2 - self.o2_adapt
        self.o2_adapt += (o2 - self.o2_adapt) * self._o2_rate
        # Tonic and differential, and the differential is what makes the taxis point the
        # right way -- see SensoryParams.oxygen_d_gain.
        I[self.urx] += p.oxygen_gain * (o2 - p.oxygen_preferred) + p.oxygen_d_gain * do2

        # ----------------------------------------------------------------- mechanosensation
        mag = np.hypot(contact[:, 0], contact[:, 1])
        half = len(mag) // 2
        ant = float(mag[:half].sum()) + self.poke[0]
        post = float(mag[half:].sum()) + self.poke[1]
        # Smoothed contact, not accumulated contact. This used to be
        #     touch_state = touch_state * decay + force
        # which adds a whole force every step regardless of how long a step is, so its
        # steady state was force / (1 - exp(-dt/tau)) -- proportional to 1/dt. Touch was
        # therefore four times more sensitive at dt = 0.125 ms than at 0.5 ms, and sixteen
        # times more than at 2 ms, which makes every mechanosensory result a statement
        # about the step size as much as about the animal. As an exponential moving average
        # the steady state is the force itself and the units mean what they say.
        self.touch_state += (np.array([ant, post]) - self.touch_state) * self._touch_rate
        self.poke *= 0.0
        if self._habituates:
            # Exact for a frozen stimulus, like every other first-order state here, so how
            # much the animal habituates does not depend on how finely it is stepped.
            rate = self._hab_recover + self._hab_use * self.touch_state
            inf = self._hab_recover / rate
            self.touch_avail = inf + (self.touch_avail - inf) * np.exp(-rate * self.dt)
        drive = p.touch_gain * self.touch_state * self.touch_avail
        I[self.touch_anterior] += drive[0]
        I[self.touch_posterior] += drive[1]
        I[self.nose_touch] += p.touch_gain * 0.5 * float(mag[0] + mag[1])

        # --------------------------------------------------------------------------- food
        f = float(world.sample(world.food, nose[0], nose[1]))
        I[self.dopaminergic] += p.food_gain * f
        # NSM tastes food in the pharynx, and is the serotonergic arm of the response to
        # it (Flavell et al. 2013). It was not previously given any food input at all,
        # which left the serotonergic system with nothing to respond to.
        I[self.nsm] += p.food_gain * f

        # --------------------------------------------------------- locomotory command bias
        # A bias, not a clamp. See SensoryParams for why these are now separate.
        I[self.avb] += p.tonic_forward
        I[self.ava] += p.tonic_backward

        # ------------------------------------------------------- the direction decision
        # Read the *difference* between the two command pools. Absolute activity has no
        # dynamic range here -- AVB saturates and stays saturated -- but the difference
        # between the pools moves whenever either one is driven, which is what lets a
        # sensory neuron have any say in where the animal goes.
        fwd_act = float(np.mean(activation[self.avb]))
        bwd_act = float(np.mean(activation[self.ava]))
        # Serotonin shifts the 50/50 point towards reversal and PDF shifts it back: this
        # one number is the roaming/dwelling competition, and it is the slow term the
        # command layer previously had no way of receiving.
        # Bounded, so that no modulator can shift the latch window clear of the operating
        # point and turn the Schmitt trigger into a one-way latch. See
        # SensoryParams.turn_bias_limit for what happened without this.
        lim = p.turn_bias_limit * p.gate_hysteresis
        shift = float(np.clip(mods.turn_bias(), -lim, lim)) if mods is not None else 0.0
        bias = p.gate_bias + shift
        diff = fwd_act - bwd_act
        if p.gate_latched:
            # Which cord, decided separately from how much. See SensoryParams.gate_latched.
            # A Schmitt trigger: the animal commits to a direction and holds it until the
            # difference crosses the *far* threshold, so a reversal is a state it stays in
            # rather than a level it hovers at.
            if self.going_forward:
                if diff < bias - p.gate_hysteresis:
                    self.going_forward = False
            elif diff > bias + p.gate_hysteresis:
                self.going_forward = True
            fwd_frac = 1.0 if self.going_forward else 0.0
            bwd_frac = 1.0 - fwd_frac
        else:
            fwd_frac = 1.0 / (1.0 + np.exp(-p.gate_slope * (diff - bias)))
            bwd_frac = 1.0 - fwd_frac

        # ----------------------------------------------------------------- the omega turn
        # Fires on the backward-to-forward *edge*, not while reversing. Read from fwd_frac
        # rather than from going_forward so it behaves the same whether or not the gate is
        # latched. See SensoryParams.omega_current for why an edge is the right object.
        forward_now = fwd_frac >= 0.5
        if forward_now:
            if self._rev_steps:
                # A reversal just ended. Its length sets the depth of the turn, which is
                # the animal's own relationship rather than a second fitted constant.
                self.omega = min(1.0, self._rev_steps / self._omega_ref_n)
                # Which way this one goes. Ventrally biased, not exclusively ventral --
                # turns that all bend the same way accumulate into a circle rather than
                # cancelling. See SensoryParams.omega_ventral_fraction.
                self.omega_sign = (
                    1.0 if self.rng.random() < p.omega_ventral_fraction else -1.0)
                self._rev_steps = 0
        else:
            self._rev_steps += 1
            self.omega = 0.0        # no turn while still reversing
        self.omega *= self._omega_decay
        wave_gain = max(0.0, 1.0 - p.omega_wave_suppression * abs(self.omega))
        if p.omega_current > 0.0 and self.omega > 1e-4:
            # A differential, not a push: releasing the dorsal antagonist is worth an
            # order of magnitude more than driving the ventral side harder, which
            # saturates. See SensoryParams.omega_current for the measurement.
            drive_om = p.omega_current * self.omega * self.omega_sign
            I[self._omega_v] += drive_om
            I[self._omega_d] -= drive_om

        # Descending drive to the selected cord. This is the gait, and it is deliberately
        # no longer carried by AVB's own membrane potential: the B and A motor neurons only
        # oscillate when their command interneuron is engaged (Kawano et al. 2011; Fouad et
        # al. 2018), so the drive that holds them at their bifurcation follows the gate.
        # The unselected cord goes passive and stops competing for the same muscles.
        # Dopamine and serotonin scale the descending drive itself. This is the basal and
        # enhanced slowing responses: an animal that finds food turns its motor drive down.
        drive = p.cord_drive * (mods.locomotor_scale() if mods is not None else 1.0)
        I[self.db] += drive * fwd_frac
        I[self.vb] += drive * fwd_frac
        I[self.da] += drive * bwd_frac
        I[self.va] += drive * bwd_frac

        # ------------------------------------------------------------------ proprioception
        # Normalised curvature: 5 rad/mm is roughly the peak a crawling worm reaches.
        k = np.clip(curvature / 5.0, -2.0, 2.0)
        gate_fwd, gate_bwd = fwd_frac, bwd_frac
        # Stretch receptors saturate, and saying so here matters: without it a sharp body
        # bend delivers enough current to drive a motor neuron straight through the bottom
        # of its physiological range and pin it there.
        # Adapt out the static component before the receptor saturates on it, so the whole
        # dynamic range is spent on the part of the bend that is actually changing.
        short = mods.wavelength_shortening() if mods is not None else 0.0
        if short > 1e-6:
            # Basal slowing: shorten the wave rather than weaken the drive, because the
            # frequency is mechanics-set and will not move. See ModulatorParams.
            wb = (1.0 - short) * (self.W_b @ k) + short * (self.W_b_food @ k)
            wa = (1.0 - short) * (self.W_a @ k) + short * (self.W_a_food @ k)
        else:
            wb, wa = self.W_b @ k, self.W_a @ k
        raw = wb * gate_fwd + wa * gate_bwd
        self.prop_adapt += (raw - self.prop_adapt) * self._prop_adapt_rate
        prop_I = np.tanh(raw - self.prop_adapt) * p.proprio_gain * self.g_scale_prop
        if wave_gain < 1.0:
            prop_I[self._omega_wave_body] *= wave_gain
        I += prop_I
        # The head reflex runs whichever way the animal is going -- it is what keeps the
        # nose sweeping, and the sweep is what steering acts on. It is low-pass filtered by
        # the receptor's own kinetics, which is what keeps the loop out of its fast mode.
        k_head = k
        if self._head_delay_n:
            # Write now, then step on: the slot just vacated holds the oldest sample,
            # which is exactly _head_delay_n steps back.
            self._head_hist[self._head_hist_i] = k
            self._head_hist_i = (self._head_hist_i + 1) % len(self._head_hist)
            k_head = self._head_hist[self._head_hist_i]
        if p.head_distributed:
            # Each head motor neuron reads its own patch of body rather than all of them
            # sharing one average over the front of the animal.
            raw = self.W_head @ k_head
        else:
            raw = float(np.dot(self._head_window, k_head))
        if self._head_chain is None:
            self.head_signal += (raw - self.head_signal) * (1.0 - self._head_decay)
        else:
            # Each stage sees the previous stage's output, which is what makes the phase
            # add rather than average. The last stage is `head_signal`, so everything
            # downstream -- the tanh, the gain, the omega suppression -- is untouched.
            a = 1.0 - self._head_stage_decay
            for s in range(self._head_stages - 1):
                self._head_chain[s] += (raw - self._head_chain[s]) * a
                raw = self._head_chain[s]
            self.head_signal += (raw - self.head_signal) * a
        # Stand the reflex down while the turn runs. It regulates head curvature, which is
        # the quantity the turn is displacing, so left at full gain it opposes the turn
        # until the oscillator stalls. See SensoryParams.omega_reflex_suppression.
        head_gain = p.head_proprio_gain
        if p.omega_reflex_suppression and abs(self.omega) > 1e-4:
            head_gain *= max(0.0, 1.0 - p.omega_reflex_suppression * abs(self.omega))
        head_gain *= wave_gain
        if p.head_distributed:
            I += (np.tanh(self.head_signal) * head_gain * self.g_scale_head)
        else:
            I += (self.W_head_sign * self.g_scale_head
                  * (np.tanh(self.head_signal) * head_gain))

        self.readout = {
            "attractant": c, "d_attractant": dc, "repellent": rep,
            "temperature": T, "oxygen": o2, "d_oxygen": do2, "food": f,
            "touch": float(self.touch_state.sum()),
            "habituation": float(self.touch_avail.mean()),
            "gate_forward": gate_fwd, "gate_backward": gate_bwd,
            "gate_shift": shift,
            "omega": float(self.omega * self.omega_sign),
            "omega_wave_gain": float(wave_gain),
            **({} if mods is None else mods.readout()),
        }
        return I


def _normalise(g_rest: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Per-neuron input scale, normalised to mean 1 over the cells a channel drives.

    Multiplying an input current by this makes the *voltage* it produces uniform across
    targets of differing input conductance, while leaving the channel's overall gain --
    and therefore its calibration -- untouched.
    """
    hit = targets > 0
    if not hit.any():
        return np.ones_like(g_rest)
    return g_rest / g_rest[hit].mean()


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


def _head_fields(conn: Connectome, dorsal: np.ndarray, ventral: np.ndarray,
                 joint_s: np.ndarray, field: float) -> np.ndarray:
    """(N, n_joints) map from curvature to head-reflex current, one row per head neuron.

    The head reflex is a *resistance* reflex -- a dorsal bend excites the ventral benders
    and inhibits the dorsal ones -- which is what makes it oscillate rather than propagate,
    and it keeps that sign here. What changes is that each cell reads the curvature around
    the piece of body it actually moves instead of every cell sharing one head-wide
    average.

    That matters because those pieces are not the same piece. Weighted by their own
    neuromuscular maps, RMD, SMD and SMB act between s = 0.135 and s = 0.229 -- a spread of
    about a tenth of the body, which the travelling wave takes a fair fraction of a cycle to
    cross. A lumped reflex throws that away and then needs an invented transport delay to
    get the phase back; a distributed one has it for free, and has it as a consequence of
    the anatomy rather than of a fitted constant.
    """
    W = np.zeros((conn.n, len(joint_s)))
    half = 0.5 * field
    for group, sign in ((dorsal, -1.0), (ventral, +1.0)):
        for i in group:
            s0 = _output_position(conn, int(i))
            w = ((joint_s >= s0 - half) & (joint_s <= s0 + half)).astype(float)
            if w.sum() == 0:
                w[np.argmin(np.abs(joint_s - np.clip(s0, 0, 1)))] = 1.0
            W[i] = sign * w / w.sum()
    return W


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
