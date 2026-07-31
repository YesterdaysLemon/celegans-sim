"""The wireless connectome: slow monoamine and neuropeptide state.

Everything else in this model is the *wired* connectome -- 2279 chemical synapses and 552
gap junctions, all fast, all ionotropic, every one of them collapsed to one of two reversal
potentials. That is half the animal. C. elegans also runs a monoamine and neuropeptide
network over the same 302 cells, and Bentley et al. (2016) showed it is comparably dense
and largely *non-overlapping* with the synaptic wiring: a neuron's modulatory targets are
mostly not the cells it synapses onto. Ours had none of it, which is the structural reason
the animal has no behavioural flexibility -- nothing in the model integrated anything, and
the only state variables that outlived a timestep were adaptation filters whose entire
purpose is to forget.

Each modulator here is one slow scalar. It is produced by named neurons in proportion to
their activity, it decays with its own time constant, and it acts by scaling gains over
defined target sets rather than by injecting current. That is deliberately how the
pharmacology is described, and it keeps the wired model untouched: with every coefficient
at zero this file changes nothing.

    dopamine     CEP/ADE/PDE, which are mechanosensory and fire on the texture of a
                 bacterial lawn. Mediates the *basal slowing response*: a well-fed animal
                 slows down on food. Sawin, Ranganathan & Horvitz (2000) -- cat-2 mutants,
                 which cannot make dopamine, fail to slow.

    serotonin    NSM, which tastes food in the pharynx, plus ADF and HSN. Drives dwelling
                 (Flavell et al. 2013) and the *enhanced* slowing response of a starved
                 animal returning to food -- the same paper, and a separate pathway from
                 dopamine's.

    octopamine   RIC. The starvation signal, and serotonin's antagonist throughout.

    PDF          AVB and PVT. Drives roaming, opposing serotonin's dwelling. The
                 roaming/dwelling pair is the best-characterised persistent behavioural
                 state in this animal, and it is a two-modulator competition.
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import ModulatorParams


class Modulators:
    """Slow scalar state, one per modulator, driven by its source neurons' activity."""

    NAMES = ("dopamine", "serotonin", "octopamine", "pdf")

    def __init__(self, conn: Connectome, p: ModulatorParams, dt: float,
                 g_rest: np.ndarray | None = None):
        self.p = p
        self.dt = dt
        self.n = conn.n
        self.sources = {
            "dopamine": conn.group(*p.dopamine_sources),
            "serotonin": conn.group(*p.serotonin_sources),
            "octopamine": conn.group(*p.octopamine_sources),
            "pdf": conn.group(*p.pdf_sources),
        }
        for name, idx in self.sources.items():
            if len(idx) == 0:
                raise RuntimeError("no neurons matched the %s sources" % name)
        self.tau = {"dopamine": p.dopamine_tau, "serotonin": p.serotonin_tau,
                    "octopamine": p.octopamine_tau, "pdf": p.pdf_tau}
        self._rate = {n: 1.0 - np.exp(-dt / self.tau[n]) for n in self.NAMES}

        # Levels are deviations from resting release, and resting release is exactly 0.5:
        # every neuron's sigmoid midpoint is solved to sit at its own resting potential
        # (NeuralParams.v_th_from_rest), so phi(V_rest) = 1/2 by construction. Using that
        # fixed reference matters more than it looks. An earlier version took the baseline
        # from the first step of each run, which silently adapted away the entire signal:
        # an animal dropped onto a lawn recorded its on-food dopamine as "normal" and then
        # measured zero change, so the basal slowing response came out at a ratio of 1.00
        # for every coefficient tested. A modulator that subtracts its own initial
        # condition cannot report a standing state, which is most of what modulators do.
        self.baseline = 0.5
        self.level = {n: 0.0 for n in self.NAMES}

        # MOD-1, the serotonin-gated chloride channel on AIB. Peak conductance is a
        # fraction of each target's own resting conductance, so the coefficient means the
        # same thing whatever the cell's size. See ModulatorParams.serotonin_mod1.
        idx = conn.group(*p.mod1_targets)
        if p.serotonin_mod1 != 0.0 and len(idx) == 0:
            raise RuntimeError("no neurons matched the MOD-1 targets %r"
                               % (p.mod1_targets,))
        self._mod1_peak = np.zeros(conn.n)
        if len(idx):
            g = np.ones(len(idx)) if g_rest is None else g_rest[idx]
            self._mod1_peak[idx] = p.serotonin_mod1 * g
        self._any_mod1 = bool(np.any(self._mod1_peak != 0.0))

    def step(self, activation: np.ndarray, alive: np.ndarray | None = None) -> None:
        """Advance every level. `alive` masks out ablated source cells.

        Without that mask an ablated source does not fall silent -- it signals the
        *opposite*. Levels are deviations from a resting release of 0.5, and an ablated
        neuron reads 0.0, so killing NSM used to drive serotonin to -0.133 where it should
        have gone to zero, and flipped the serotonergic turn bias from +0.090 to -0.080.
        Every ablation experiment touching a modulator source was reading a sign error.
        """
        for name in self.NAMES:
            idx = self.sources[name]
            if len(idx) == 0:
                continue
            if alive is None:
                target = float(np.mean(activation[idx])) - self.baseline
            else:
                # A dead source contributes its *resting* release -- a deviation of zero --
                # and stays in the denominator. It is not dropped from the average.
                #
                # Dropping it makes the level a mean over the survivors, and that is not a
                # quantity a neuron can affect by dying: removing a source whose activation
                # sits below its siblings' *raises* the mean. Killing HSN, whose activation
                # is 0.521 against a serotonin source mean of 0.62, drove serotonin from
                # 0.120 to 0.219 -- up, on removing one of the cells that makes it. Every
                # ablation of a modulator source had an effect whose sign depended on where
                # that cell happened to sit relative to its siblings.
                #
                # Keeping it in the denominator at zero deviation makes the level scale with
                # the fraction of sources still alive, so removal can only ever shrink the
                # signal. With nothing ablated this is arithmetically identical to the line
                # it replaces, so no existing result moves; only ablations change, and only
                # in the direction they should have been going.
                dev = np.where(alive[idx], activation[idx] - self.baseline, 0.0)
                target = float(np.mean(dev))
            self.level[name] += (target - self.level[name]) * self._rate[name]

    # ------------------------------------------------------------------------- effects
    def locomotor_scale(self) -> float:
        """Multiplier on the descending drive to the motor cords.

        Dopamine and serotonin both slow the animal; octopamine, the starvation signal,
        opposes them. Clipped below at 0.25 so that no combination can silence the cords
        outright -- a real worm on food slows to about half speed, it does not stop.
        """
        p = self.p
        s = (1.0
             - p.dopamine_slowing * self.level["dopamine"]
             - p.serotonin_slowing * self.level["serotonin"]
             + p.octopamine_speeding * self.level["octopamine"])
        return float(np.clip(s, 0.25, 1.6))

    def gated_conductance(self) -> np.ndarray | None:
        """Ligand-gated conductance the modulators are currently opening, per neuron.

        Only MOD-1 so far: serotonin opening a chloride channel on AIB, which is how food
        suppresses reversals. Returns None when nothing is switched on, so the wired model
        is untouched. See ModulatorParams.serotonin_mod1.
        """
        if not self._any_mod1:
            return None
        # Only the depolarising half. Serotonin below its resting release means *less*
        # food than baseline, which should not prise a channel open backwards.
        return self._mod1_peak * max(self.level["serotonin"], 0.0)

    def wavelength_shortening(self) -> float:
        """How far to shorten the proprioceptive reach: 0 = not at all, 1 = fully.

        The basal slowing response, by the only route this model has. Its undulation
        frequency is set by the body's mechanics and does not move under any neural
        parameter tried, so a slower animal has to make a shorter wave. See
        ModulatorParams.dopamine_wavelength and SensoryParams.proprio_reach_food.
        """
        return float(np.clip(self.p.dopamine_wavelength * self.level["dopamine"],
                             0.0, 1.0))

    def turn_bias(self) -> float:
        """Added to the direction gate's 50/50 point.

        Positive makes reversals easier, which is what dwelling is: a worm that turns
        often stays where it is. Serotonin pushes that way and PDF pushes back, which is
        the roaming/dwelling competition stated as one number.
        """
        p = self.p
        return float(p.serotonin_turning * self.level["serotonin"]
                     - p.pdf_roaming * self.level["pdf"])

    def readout(self) -> dict:
        return dict(self.level)
