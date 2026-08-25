"""Sleep: RIS-gated quiescence, driven by a satiety homeostat.

C. elegans genuinely sleeps, and the state has an owner: **RIS**, a single GABAergic
interneuron whose activation is necessary and sufficient for movement quiescence --
optogenetically driving it stops the animal, ablating it removes almost all sleep
(Turek, Lewandrowski & Bringmann 2013, Curr Biol 23:2215). RIS acts two ways at once,
and so does this module:

* **Through the wiring.** RIS is GABAergic in the reconstruction already -- its synapses
  carry the inhibitory reversal -- and they land where a sleep switch should: AVE (14
  contacts here), RIB, RIM, and the RMD/SMD head motors. Depolarising RIS quiets the
  command and head circuits through nothing but the connectome.
* **Through FLP-11.** RIS's quiescence effect survives cutting its synaptic output;
  the missing route is the neuropeptide FLP-11, released from RIS and required for
  normal sleep (Turek et al. 2016, eLife 5:e12499). Modelled the way the wireless layer
  models everything: one slow scalar, released above a depolarisation RIS only reaches
  when driven, acting as a gain on defined targets -- the motor cords, the head
  oscillator, and the pharyngeal pump (sleeping animals stop pumping).

The *timing* is a homeostat. The adult sleep this always-adult model can honestly have
is satiety quiescence: a well-fed animal becomes quiescent, food withdrawal suppresses
it (You et al. 2008, Cell Metab 7:249; Trojanowski & Raizen 2016 for the taxonomy).
Pressure builds while the animal is awake -- much faster on food, read off the
dopamine level the basal-slowing machinery already keeps -- and discharges during a
bout. A Schmitt trigger (threshold_on / threshold_off) turns that into discrete bouts
rather than flicker.

Arousal is the touch pathway, deliberately left at full gain: a strong enough
mechanical stimulus both fires the ordinary escape circuit *through* the sleeping
animal and interrupts the bout here (sleep is rapidly reversible -- the property that
separates it from paralysis). Pressure is *not* cleared by an arousal, so a poked
animal goes back to sleep after the refractory: that is sleep rebound, and it comes
free from the bookkeeping.

The clock is compressed. Real satiety quiescence follows hours of feeding with
minutes-long bouts; this dish runs its whole ecology on a compressed clock (eggs,
lifecycle), and sleep keeps to it: pressure crosses threshold after minutes on food,
a bout lasts tens of seconds. The *structure* -- who drives it, what it gates, what
wakes it, what ablation abolishes -- is the biology; the rates are the dish's.

Below `threshold_on` nothing here touches the animal at all: the drive is exactly
zero, FLP-11 is exactly zero (RIS never reaches the release threshold un-driven), and
every gain multiplier is exactly 1.0 -- so an animal that has not yet slept is
bit-identical to the animal before this module existed.
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import SleepParams


class Sleep:
    """The homeostat, the RIS drive, and the FLP-11 level."""

    def __init__(self, conn: Connectome, p: SleepParams, dt: float):
        self.p = p
        self.dt = dt
        self.ris = conn.select("RIS")
        if len(self.ris) == 0:
            raise RuntimeError("RIS is not in the connectome")
        self._flp_rate = -np.expm1(-dt / p.flp11_tau)
        self._sleep_decay = float(np.exp(-dt / p.tau_sleep))
        self.pressure = 0.0
        self.bout = False
        self.flp11 = 0.0
        self.refractory = 0.0

    def step(self, activation: np.ndarray, touch: float, dopamine: float,
             alive: np.ndarray | None = None) -> float:
        """Advance one tick; returns the current (pA) to inject into RIS.

        `touch` is the summed smoothed contact the mechanosensors carry
        (Senses.touch_state.sum(), one step behind like every sensory quantity),
        `dopamine` the wireless level the basal-slowing response reads -- so "fed"
        here means exactly what it means everywhere else in the model.
        """
        p = self.p

        # FLP-11 follows RIS's own activation -- the peptide is released by the *cell*,
        # which is what makes ablating the cell abolish sleep rather than merely
        # rerouting it: a dead RIS reads activation 0 and releases nothing however hard
        # the homeostat drives it. Release is additionally gated on the bout, because
        # RIS's wiring-driven activation swings through 0.26-0.85 with the gait
        # (measured on-lawn before shipping) and no fixed threshold sits above that
        # with margin; dense-core release here accompanies the driven plateau, and the
        # gate is what keeps an animal that has never slept bit-identical to the
        # animal before this module existed.
        act = float(activation[self.ris].mean())
        if alive is not None and not bool(alive[self.ris].all()):
            act = 0.0
        target = 0.0
        if self.bout:
            target = max(0.0, act - p.release_threshold) / (1.0 - p.release_threshold)
        self.flp11 += (target - self.flp11) * self._flp_rate

        # Arousal: a strong mechanical stimulus interrupts the bout and holds sleep off
        # for the refractory. Pressure is deliberately untouched -- see the module
        # docstring on rebound.
        if self.refractory > 0.0:
            self.refractory = max(0.0, self.refractory - self.dt)
        if self.bout and touch > p.arousal_touch:
            self.bout = False
            self.refractory = p.arousal_refractory
            # Waking is fast where falling asleep is slow: an arousal actively clears
            # most of the standing peptide effect rather than waiting out its decay,
            # so a poked animal moves within a second -- rapid reversibility is the
            # property that separates sleep from paralysis.
            self.flp11 *= (1.0 - p.arousal_clear)

        # The homeostat. Builds while awake -- fast on food, read off dopamine's
        # positive deviation -- and discharges exponentially during a bout.
        if self.bout:
            self.pressure *= self._sleep_decay
            if self.pressure < p.threshold_off:
                self.bout = False
        else:
            rate = p.build_base + p.build_fed * max(0.0, dopamine)
            self.pressure = min(1.0, self.pressure + rate * self.dt)
            if self.pressure > p.threshold_on and self.refractory <= 0.0:
                self.bout = True

        return p.ris_drive if self.bout else 0.0

    def quiescence(self) -> float:
        """0 awake to 1 fully quiescent: the FLP-11 gain on the module's targets."""
        return float(np.clip(self.p.quiescence_gain * self.flp11, 0.0, 1.0))

    def readout(self) -> dict:
        return {"sleep_pressure": self.pressure, "flp11": self.flp11,
                "asleep": float(self.bout)}
