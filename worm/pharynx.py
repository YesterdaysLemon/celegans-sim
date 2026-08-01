"""The pharynx: twenty neurons that until now drove nothing at all.

C. elegans has two nervous systems. The somatic one is the 282 cells everything else in
this model is about; the pharyngeal one is 20 more, and it is very nearly a separate
animal. Measured in this reconstruction it makes 203 chemical contacts and 86 gap junctions
*within itself*, exactly **zero** chemical contacts to or from the somatic nervous system,
and four gap junctions across -- which is the I1-RIP coupling, the single anatomical bridge
between the two, and the reason Albertson & Thomson called the pharyngeal system
autonomous. It also makes zero neuromuscular contacts in this dataset, because pharyngeal
muscle is not among the 95 body-wall cells the model carries. So the pharynx was simulated
in full and connected to nothing: it ate no food, moved nothing, and could be deleted
without changing a single number.

What it should do is pump. The pharynx is a muscular pump that grinds bacteria and moves
them to the intestine, and the rate it pumps at is the animal's feeding rate.

**The pump is myogenic and the neurons modulate it.** Avery & Horvitz (1989) killed every
pharyngeal neuron and the pharynx still pumped -- slowly, and the animal starved, but it
pumped. So the oscillator here is not built out of neurons: it is a relaxation cycle with
its own base rate, which the neurons speed up, slow down, shorten and gate.

Who does what, and where each one enters this model:

    MC      the pacemaker. Cholinergic onto pharyngeal muscle, and the fast pumping of a
            fed animal depends on it: eat-2 mutants, which lack the receptor MC acts on,
            pump several times more slowly and grow up starved. Sets the *rate*.
    M3      glutamatergic, and inhibitory onto the muscle. It repolarises the pump, so it
            sets the pump's *duration* -- M3-killed animals have long pumps.
    I2      inhibits pumping. Bhatla & Horvitz (2015) show it driving the feeding arrest
            that follows light or hydrogen peroxide.
    M4      drives isthmus peristalsis, which is what actually moves food from the lumen
            back to the intestine. M4-ablated animals pump normally and starve anyway,
            which is why transport is modelled separately from capture here.
    NSM     tastes food in the lumen and is the serotonergic arm of the response to it.
            It is already wired to the food field in senses.py, and it is the route by
            which the rest of the pharynx hears about food at all.

And the food signal really does travel that way in this model, through the reconstructed
wiring and nothing else. Dropped on a lawn, activation changes by

    NSM  0.390 -> 0.969      I2  0.446 -> 0.662      M3  0.487 -> 0.568
    MC   0.557 -> 0.599      M4  0.528 -> 0.573

so the pacemaker is food-responsive before anything here is fitted. What was missing was
not a signal. It was an effector.

Targets, all from freely-feeding animals on E. coli:

    pump rate on food        200-300 /min      Avery & Horvitz 1989, Croll 1978
    pump rate off food       far lower, sporadic
    pump duration            ~150-200 ms
    MC removed               pumping several-fold slower (the eat-2 phenotype)
    M4 removed               pumping continues, transport stops, the animal starves
"""

from __future__ import annotations

import numpy as np

from .dataset import Connectome
from .params import PharynxParams

REST = 0.5      # resting activation; every sigmoid midpoint sits at its own rest potential


class Pharynx:
    """A myogenic pump, its rate and duration set by the pharyngeal nervous system."""

    def __init__(self, conn: Connectome, p: PharynxParams, dt: float):
        self.p = p
        self.dt = dt
        self.mc = conn.group("MC")
        self.m3 = conn.group("M3")
        self.m4 = conn.group("M4")
        self.i2 = conn.group("I2")
        for name, idx in (("MC", self.mc), ("M3", self.m3),
                          ("M4", self.m4), ("I2", self.i2)):
            if len(idx) == 0:
                raise RuntimeError("no %s neurons in this connectome" % name)

        self.phase = 0.0          # progress towards the next pump, 0..1
        self.open_for = 0.0       # s remaining in the pump currently under way
        self.pumping = False
        self.rate = 0.0           # Hz, the instantaneous pump rate
        self.duration = 0.0       # s, the length of the pump last triggered
        self.pumps = 0            # pumps since the run began
        self.lumen = 0.0          # food captured but not yet moved to the intestine
        self.ingested = 0.0       # total transported, in patch density units
        self.captured = 0.0       # what the last pump took in, for the readout
        self._alive = None        # set each step; see _dev()

    # ------------------------------------------------------------------------- stepping
    def step(self, activation: np.ndarray, food_at_mouth: float, take, mods=None,
             alive: np.ndarray | None = None) -> float:
        """Advance one step. Returns how much food reached the intestine this step.

        `take(amount) -> obtained` withdraws from the world where the mouth is *now*, and
        is called at the moment of capture. It is not optional, and the reason is a bug it
        closes. Capture used to be free: the lumen gained whatever the pump asked for, and
        the world was debited later, when M4 transported it, at wherever the head had
        drifted to by then. An animal could therefore feed on a lawn, walk away, and
        transport food the plate never lost -- measured, 0.0045 into the lumen against
        0.00000000 removed from the world, with the uterus credited for all of it.

        Food leaves the plate when the pharynx grinds it, not when the isthmus moves it
        on, so debiting at capture is also the physically honest order. What the animal
        gets to keep is still `ingested`, which is what makes the M4 phenotype work: an
        M4-ablated animal captures until its lumen is full, stops, and starves with food
        in its mouth.

        `alive` masks ablated cells out of every drive term. It matters more here than it
        looks: activation is read as a deviation from a resting 0.5, and an ablated cell
        reads 0.0, so without the mask killing a neuron does not remove its drive -- it
        reverses it. Ablating MC that way drove the rate to a hard zero rather than to the
        several-fold slowdown eat-2 animals actually show.
        """
        p = self.p
        a = activation
        self._alive = alive

        # -- rate ----------------------------------------------------------------------
        # Myogenic base, sped by the pacemaker and slowed by the inhibitory interneuron.
        # Serotonin is the other half of the food signal and the reason a starved animal
        # given exogenous 5-HT pumps as though it were fed (Horvitz et al. 1982).
        # Serotonin acts *through* the pacemaker rather than beside it. SER-7 is expressed
        # in MC and is where serotonin's stimulation of pumping acts (Song & Avery 2012),
        # which makes the pacemaker epistatic to the food signal: an animal without MC
        # does not pump fast no matter how much serotonin it has. Modelled as a separate
        # additive term it was not -- ablating MC cost only 5% of the rate, because the
        # serotonergic drive simply carried on without it.
        mc = self._dev(a, self.mc)
        if len(self._live(self.mc)) and mods is not None:
            mc += (p.serotonin_to_mc * mods.level["serotonin"]
                   - p.octopamine_to_mc * mods.level["octopamine"])
        i2 = self._dev(a, self.i2)
        rate = p.myogenic_rate + p.mc_rate_gain * mc - p.i2_rate_gain * i2
        self.rate = float(np.clip(rate, 0.0, p.max_rate))

        # -- the pump itself -------------------------------------------------------------
        # The cycle runs during the pump as well as between pumps, so `rate` is the rate
        # the animal actually achieves rather than the rate it would achieve if pumping
        # were instantaneous. A fed animal at 4 Hz with 150 ms pumps spends most of its
        # time mid-pump, and stalling the clock during that would have capped it near 2.
        # What remains is a refractory period: a pump cannot begin while one is running,
        # so the achieved rate saturates at 1 / pump_duration.
        self.captured = 0.0
        self.phase += self.rate * self.dt
        if self.pumping:
            self.open_for -= self.dt
            if self.open_for <= 0.0:
                self.pumping = False
        if not self.pumping and self.phase >= 1.0:
            self.phase = 0.0
            self._fire(a, food_at_mouth, take)

        # -- isthmus peristalsis ---------------------------------------------------------
        # M4 is what moves the lumen's contents back to the intestine. Without it the
        # animal pumps normally and starves, so transport is its own step rather than a
        # property of the pump: capture fills the lumen, M4 empties it, and a full lumen
        # stops further capture.
        m4 = self._dev(a, self.m4)
        drive = max(0.0, p.m4_transport + p.m4_gain * max(m4, 0.0))
        moved = min(self.lumen, self.lumen * drive * self.dt)
        self.lumen -= moved
        self.ingested += moved
        return moved

    def _live(self, idx: np.ndarray) -> np.ndarray:
        return idx[self._alive[idx]] if self._alive is not None else idx

    def _dev(self, a: np.ndarray, idx: np.ndarray) -> float:
        """Mean activation of the living members of a group, as a deviation from rest.

        An empty group contributes nothing rather than contributing -REST. See step().
        """
        idx = self._live(idx)
        return float(np.mean(a[idx])) - REST if len(idx) else 0.0

    def _fire(self, a: np.ndarray, food_at_mouth: float, take) -> None:
        p = self.p
        # M3 repolarises the muscle and so ends the pump; more M3 means a shorter one.
        m3 = self._dev(a, self.m3)
        self.duration = p.pump_duration / (1.0 + p.m3_duration_gain * max(m3, 0.0))
        self.open_for = self.duration
        self.pumping = True
        self.pumps += 1
        # A longer pump takes in more, and a full lumen cannot take in anything.
        room = max(0.0, 1.0 - self.lumen / p.lumen_capacity)
        want = (p.volume_per_pump * max(food_at_mouth, 0.0)
                * (self.duration / p.pump_duration) * room)
        # What the pump asks for and what the plate has are two different numbers. The
        # lumen gains the second one, so the animal cannot ingest food that was never
        # there -- which is the whole of the conservation invariant the tests assert.
        self.captured = float(take(want)) if want > 0.0 else 0.0
        self.lumen += self.captured

    # -------------------------------------------------------------------------- readout
    def readout(self) -> dict:
        return {"pump_rate": self.rate, "pumping": float(self.pumping),
                "pump_duration": self.duration, "lumen": self.lumen,
                "pumps": float(self.pumps)}
