"""Egg-laying: eight neurons with somewhere to send their output at last.

The pharynx was simulated and connected to nothing because it was anatomically isolated --
zero chemical contacts to the rest of the animal. HSN and the VCs have the opposite
problem, and the opposite problem is the easier one. Measured in this reconstruction the
eight cells (HSNL/R, VC01-06) make **86 chemical contacts to the rest of the nervous
system** and receive 27, with 4 gap junctions out: HSN reaches AIA, AIZ, ASH, ASK, AVD and
AVF and hears back from AIY, ASJ, AVB and BDU; the VCs synapse onto DD01-04 and gap-couple
to VD01. They are already integrated, already responsive, and already influencing
locomotion. HSN is already a serotonin source -- `ModulatorParams.serotonin_sources` has
listed it since the modulator layer was built.

What was missing is the same thing the pharynx was missing: an effector. Vulval muscle
(vm1, vm2) is not among the 95 body-wall cells this model carries, so the one thing these
cells exist to do had nowhere to happen.

Measured on food before any of this was written, over 60 s:

    HSNL  V swing 33.9 mV, activation swing 0.78     VC01  24.5 mV, 0.64
    HSNR          23.3 mV,                 0.62      VC03  21.2 mV, 0.58

so they are alive and network-driven. With one exception, and it is a load-bearing one:

    VC06  V swing 46.5 mV, activation swing 0.88

**VC06 has zero synapses and zero gap junctions in this reconstruction.** Its swing is the
largest of the eight and every millivolt of it is the Ornstein-Uhlenbeck background
current. An unconnected cell is a noise generator, so it is excluded from the drive below
by name. Reading it would mean laying eggs at random and calling it a circuit.

What the animal actually does, and what this has to reproduce:

    egg-laying is CLUSTERED       Waggoner et al. 1998: active phases of roughly 2 min
                                  containing several events about 20 s apart, separated by
                                  inactive phases of roughly 20 min. This is the
                                  interesting claim -- a mean rate is easy and says
                                  nothing. The clustering has to *emerge*.
    on food                       ~4-6 eggs/hour freely feeding
    off food                      strongly suppressed; eggs are retained
    HSN killed                    egg-laying defective, and slow -- but NOT zero. The
                                  vulval muscles can still be driven without HSN.
                                  *This model overshoots it: ablated animals lay nothing
                                  at all. The retention and bloating are right, the
                                  residual rate is not. See EggLayingParams.myogenic for
                                  the measurement showing why it is structural rather than
                                  a bad constant.*
    exogenous serotonin           induces laying, including in HSN-ablated animals,
                                  because it acts downstream on the muscle
    VC killed                     a mild *increase*; the VCs are not the drivers

The two-state structure is built the way this repository builds persistent state
elsewhere: a depleting resource with its own recovery time constant, exactly the
Tsodyks-Markram idiom `worm/senses.py` uses for tap habituation, behind a two-threshold
Schmitt trigger like the direction gate's. An active phase runs the resource down;
recovery takes minutes; the next phase cannot begin until it is back above the upper
threshold. Nothing here schedules a phase, and nothing counts events.

Measured, five animals on a lawn for sixty simulated minutes each (55 events):

    rate                   11.0 eggs/hour
    interval CV            1.79        (0 = metronome, 1 = Poisson, >1 = clustered)
    intervals under 60 s   60%
    intervals over 2 min   20%

Both tails populated is what bimodal means, and it is the one of the three a timer cannot
produce. One caveat, stated because the CV alone would oversell it: **the median interval
is 6.0 s, which is exactly `refractory`** -- the fast mode is a parameter, not an emergent
spacing, and the animal's intra-bout interval is nearer 20 s. What genuinely emerges is the
slow mode: the fifth of intervals longer than two minutes, which is the resource behind the
Schmitt trigger and nothing else.
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import EggLayingParams


class EggLaying:
    """Vulval muscle, the egg pool that feeds it, and the resource that clusters it."""

    def __init__(self, conn: Connectome, p: EggLayingParams, dt: float):
        self.p = p
        self.dt = dt
        self.conn = conn

        # HSN drives; the VCs modulate. VC06 is excluded by name, not by weight: it is
        # unconnected in this reconstruction and would contribute pure noise.
        self.hsn = conn.group("HSN")
        vc = [conn.index[n] for n in ("VC01", "VC02", "VC03", "VC04", "VC05")
              if n in conn.index]
        self.vc = np.asarray(vc, dtype=np.intp)
        if self.hsn.size == 0:
            raise RuntimeError("no HSN in the connectome")

        # Resting activation of each pool, so the drive is a *deviation* and an unchanged
        # network produces an unchanged output. Same convention as the pharynx.
        self.hsn_rest = 0.0
        self.vc_rest = 0.0
        self._rest_n = 0

        self.vm = 0.0             # vulval muscle activation, 0..1
        self.eggs = float(p.eggs_initial)   # in the uterus, ready to lay
        self.resource = 1.0       # the thing that makes phases
        self.in_phase = True      # active or inactive; a Schmitt trigger on the resource
        self.refractory = 0.0     # seconds until the muscle can fire again
        self.laid = 0             # total events
        self.last_event = -1e9    # simulated time of the most recent one
        self.t = 0.0

        # -expm1, not 1 - exp: see the note in senses.py. This is the worst of the
        # ten, at dt/tau = 5.6e-07 -- six significant digits cancelled away.
        self._recover = -np.expm1(-dt / p.resource_tau)

    # ------------------------------------------------------------------------ helpers
    def _live(self, idx: np.ndarray, alive: np.ndarray | None) -> np.ndarray:
        return idx if alive is None else idx[alive[idx]]

    def _dev(self, a: np.ndarray, idx: np.ndarray, rest: float) -> float:
        """Mean activation of a pool, as a deviation from its own resting level."""
        if idx.size == 0:
            return 0.0
        return float(a[idx].mean() - rest)

    # -------------------------------------------------------------------------- update
    def step(self, activation: np.ndarray, ingested_delta: float, serotonin: float,
             on_food: float, alive: np.ndarray | None = None) -> float:
        """Advance one timestep. Returns how many eggs were laid this step (0 or 1).

        `ingested_delta` is what the pharynx moved to the intestine this step, which is
        what fills the uterus: an animal that does not eat does not make eggs. That is the
        whole coupling between the two systems, and it is the reason feeding had to work
        before this could.
        """
        p = self.p
        self.t += self.dt

        # Resting levels, averaged over the first stretch of the run rather than assumed.
        if self._rest_n < p.rest_samples:
            self._rest_n += 1
            k = 1.0 / self._rest_n
            self.hsn_rest += (float(activation[self.hsn].mean()) - self.hsn_rest) * k
            if self.vc.size:
                self.vc_rest += (float(activation[self.vc].mean()) - self.vc_rest) * k

        hsn = self._live(self.hsn, alive)
        vc = self._live(self.vc, alive)
        # HSN enters as its *absolute* activation, the VCs as a deviation from their own
        # resting level. That asymmetry is the whole phenotype and it was wrong first
        # time: written as a deviation, like the pharynx's modulators, HSN contributes
        # zero mean drive, so ablating it changed nothing -- the first run had HSN-ablated
        # animals laying *more* than intact ones. A modulator of a myogenic rate is
        # correctly a deviation; a driver is not.
        a_hsn = float(activation[hsn].mean()) if hsn.size else 0.0
        d_vc = self._dev(activation, vc, self.vc_rest)

        # Eggs are made from food. Capped: the uterus holds a finite number, and a worm
        # that cannot lay becomes bloated rather than infinitely pregnant.
        self.eggs = min(p.uterus_capacity, self.eggs + p.eggs_per_food * ingested_delta)

        # Vulval muscle drive. Four terms, and each one is a phenotype:
        #   myogenic       the floor. An HSN-ablated animal is egg-laying *defective*, not
        #                  incapable, so removing every driver cannot leave zero. Exactly
        #                  the role PharynxParams.myogenic_rate plays for the pump, and
        #                  for the same reason: Avery & Horvitz killed every pharyngeal
        #                  neuron and it still pumped.
        #   HSN            the driver, as absolute activation. Its removal has to cost the
        #                  animal something, which a deviation term cannot do.
        #   serotonin      the humoral arm, and the reason exogenous serotonin induces
        #                  laying in an HSN-ablated animal: it enters downstream of HSN.
        #   VC             a brake, as a deviation. VC-ablated animals lay slightly *more*.
        #
        # With HSN gone the mean drive falls below vm_threshold, so laying is not abolished
        # but has to wait for a fluctuation to carry it over -- which is what "defective
        # and slow" looks like as a mechanism rather than as a fitted rate.
        drive = (p.myogenic
                 + p.hsn_gain * a_hsn
                 + p.serotonin_gain * serotonin
                 - p.vc_gain * d_vc)
        # Food gates the whole thing. Off food the animal retains eggs; this is the term
        # that makes it do so, and it is multiplicative because no amount of HSN drive
        # makes a starved animal lay freely.
        gate = p.off_food_floor + (1.0 - p.off_food_floor) * float(np.clip(on_food, 0.0, 1.0))
        target = float(np.clip(drive, 0.0, 1.0)) * gate
        self.vm += (target - self.vm) * (self.dt / p.vm_tau)

        # The resource recovers towards 1 with a time constant of minutes. This is the
        # only slow state here and it is what turns a rate into phases.
        self.resource += (1.0 - self.resource) * self._recover
        self.refractory = max(0.0, self.refractory - self.dt)

        # Two thresholds, not one -- a Schmitt trigger, the same shape as the direction
        # gate. With a single threshold there is no inactive phase to speak of: the phase
        # ends the moment the resource dips below it, and the resource is then *at* the
        # threshold, so it climbs back over within a step or two and laying resumes. What
        # produces a twenty-minute quiet period is having to climb all the way back to a
        # higher bar before the next phase can start at all.
        if self.in_phase:
            if self.resource < p.resource_off:
                self.in_phase = False
        elif self.resource >= p.resource_on:
            self.in_phase = True

        if (self.refractory <= 0.0 and self.eggs >= 1.0
                and self.vm >= p.vm_threshold
                and self.in_phase):
            self.eggs -= 1.0
            self.laid += 1
            self.last_event = self.t
            self.refractory = p.refractory
            self.resource = max(0.0, self.resource - p.resource_cost)
            self.vm = 0.0
            return 1.0
        return 0.0

    # ------------------------------------------------------------------------- readout
    def readout(self) -> dict:
        return {"vm": self.vm, "eggs_held": self.eggs, "eggs_laid": float(self.laid),
                "egl_resource": self.resource, "egl_active": float(self.in_phase)}
