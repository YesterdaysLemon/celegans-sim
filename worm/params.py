"""Every tunable constant in the simulator, in one place, with its provenance.

Unit convention (used consistently everywhere):

    length      mm          adult C. elegans is ~1 mm long
    time        s
    voltage     mV
    current     pA
    capacitance pF
    conductance nS          (1 nS * 1 mV = 1 pA, so the electrical units are consistent)
    force       uN
    torque      uN*mm
    viscosity   uN*s/mm^2   (== Pa*s, since 1 Pa*s = 1 N*s/m^2 = 1 uN*s/mm^2)

Two of these deserve a note. Electrical quantities are in the pF/nS/mV/pA family, which
is self-consistent: C dV/dt = I with C in pF, V in mV and I in pA gives dV/dt in mV/ms,
so every rate constant in the neural model is per millisecond and is converted once, at
the point of use, by NervousSystem. Mechanical quantities are in the mm/s/uN family
because at C. elegans scale SI numbers are all 1e-9 and unreadable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass, replace
from numbers import Integral, Real

from .errors import InvalidGenome


@dataclass(frozen=True)
class NeuralParams:
    """Graded-potential (non-spiking) conductance model of the C. elegans nervous system.

    C. elegans neurons are, with few exceptions, non-spiking: they signal by graded
    changes in membrane potential and release transmitter continuously as a sigmoidal
    function of presynaptic voltage. The model below is the standard one from
    Wicks, Roehrig & Rankin (1996) J. Neurosci 16:4017, as scaled up to the whole
    connectome by Kunert, Shlizerman & Kevrekidis (2014) Phys. Rev. E 89:052805.

        C dV_i/dt = -g_leak (V_i - E_leak)
                    - sum_j  g_gap  n^gap_ij  (V_i - V_j)
                    - sum_j  g_syn  n^syn_ij  s_j  (V_i - E_j)
                    + I_ext_i

        ds_j/dt   = a_r phi(V_j) (1 - s_j) - a_d s_j
        phi(V)    = 1 / (1 + exp(-beta (V - V_th_j)))

    n^gap_ij and n^syn_ij are the reconstructed contact counts from the connectome, so
    connection strength is anatomical, not fitted. E_j is 0 mV for excitatory (cholinergic
    or glutamatergic) presynaptic neurons and -48 mV for GABAergic ones.
    """

    # -- passive membrane ---------------------------------------------------------------
    # Kunert et al. use C = 1.5 pF with g_leak = 0.01 nS, i.e. an input resistance of
    # 100 GOhm and tau_m = 150 ms. Whole-cell recordings disagree by two orders of
    # magnitude: ASEL 2.2 GOhm and ASER 1.6 GOhm (Sci. Rep. 2019), and the AWA model fitted
    # to real recordings by Liu et al. (2018) Cell uses C = 1.5 pF with g_leak = 0.25 nS
    # and E_leak = -65 mV, giving tau_m = 6 ms. We take the measured values: the capacitance
    # is Kunert's, the leak is real electrophysiology. This is the one place we knowingly
    # depart from the reference implementations, and it is the place where they are known
    # to be wrong -- with g_leak = 0.01 nS the whole network rests near -4 mV, some 55 mV
    # depolarised from every published recording.
    C_m: float = 1.5             # pF   Kunert et al. 2014; Liu et al. 2018 (AWA)
    g_leak: float = 0.25         # nS   Liu et al. 2018 (AWA); ASEL/ASER input resistance
    E_leak: float = -62.0        # mV   measured resting potentials span -56 to -75 mV

    # -- synapses -----------------------------------------------------------------------
    g_gap: float = 0.1           # nS per reconstructed gap-junction contact (Kunert 2014)
    g_syn: float = 0.1           # nS per reconstructed chemical-synapse contact
    E_exc: float = 0.0           # mV   cholinergic / glutamatergic reversal
    E_inh: float = -48.0         # mV   GABA-A (Cl-) reversal; Wicks et al. 1996 Table 1
    beta: float = 0.125          # 1/mV sigmoid steepness == Wicks' |K|/V_RANGE = 4.394/35
    # Kunert et al. give a_r = 1/s, a_d = 5/s, so tau_syn ~ 180 ms -- far too slow for an
    # animal that undulates at 2 Hz, and Wicks' own simulations used instantaneous synapses
    # instead. We keep Kunert's ratio exactly (s_eq = a_r/(a_r + 2 a_d) = 1/11) but set the
    # absolute timescale to tau_syn ~ 45 ms, in line with c302's graded-synapse set C0
    # (a_d = 20/s) and with measured graded synaptic currents.
    a_rise: float = 4.0          # 1/s  synaptic activation rate
    a_decay: float = 20.0        # 1/s  synaptic deactivation rate

    # The half-activation voltage of each neuron's release curve is set so that the neuron
    # sits at the steepest part of its own sigmoid when the network is at rest. Solving for
    # it self-consistently (Kunert et al. 2014, eq. 6) keeps every neuron responsive
    # instead of silent or saturated, and removes 302 free parameters.
    v_th_from_rest: bool = True

    # Fixed-point passes over the gap-junction coupling, per step.
    #
    # The step solves the gap coupling by iterating
    #     V_inf = (fixed + G_gap @ V_new) / g_tot ;  V_new = V_inf + (V - V_inf) * decay
    # whose contraction factor per pass is (1 - decay) * ||G_gap / g_tot||, with
    # decay = exp(-g_tot dt / C). That factor *grows with dt*, so a coarser step converges
    # this iteration more slowly and ends up with a different effective gap conductance.
    #
    # Measured, largest voltage error against the fully converged fixed point of the same
    # step, mid-gait:
    #
    #   passes |  dt = 0.5 ms   dt = 0.125 ms
    #      3   |   1.37e-01       6.79e-03
    #      6   |   8.32e-03       3.46e-05
    #     10   |   2.37e-04       4.15e-08
    #
    # Three passes leave the shipped step twenty times less converged than the fine one, so
    # the two are not literally solving the same equations -- and AVB's gap junctions onto
    # the B class set the bifurcation point of the entire motor cord, which is the most
    # step-sensitive thing in the model. That made this a good candidate for the gait's
    # step dependence, and a cheap one to rule out.
    #
    # **It is not the cause.** Raising the count from 3 to 24 changes the gait by nothing
    # at either step size. (The drift figures in the table below were measured before the
    # body was synchronised to the neural step, so the 54% is an artefact -- but the point
    # this table makes, that the iteration count changes nothing, is unaffected by that.)
    #
    #   passes |  freq @0.5   freq @0.125   drift |  TWI @0.5   k_rms @0.5   net mm/s
    #      3   |    0.433       0.200        54%  |   +0.655      4.44        0.1860
    #      6   |    0.433       0.200        54%  |   +0.659      4.48        0.1822
    #     12   |    0.433       0.200        54%  |   +0.659      4.48        0.1821
    #     24   |    0.433       0.200        54%  |   +0.659      4.48        0.1821
    #
    # So the residual is real, measurable, twenty times worse at the shipped step, and
    # behaviourally irrelevant: 0.137 mV in the worst neuron does not move a gait. Left at
    # 3, which is now a measured choice rather than an assumed one, and the step dependence
    # has one fewer suspect.
    gap_iters: int = 3

    # -- intrinsic oscillation ------------------------------------------------------------
    # A purely passive graded network cannot oscillate: it is a contraction mapping onto a
    # fixed point, and proprioception alone only copies a bend backwards, it does not start
    # one. Real worms do not have that problem, because the motor neurons are not passive.
    # Fouad et al. (2018) eLife 7:e29913 and Xu et al. (2018) PNAS 115:E4493 showed that
    # the ventral cord contains multiple distributed oscillators and that the B-type motor
    # neurons oscillate intrinsically; Mellem et al. (2008) showed the head neuron RMD is
    # frankly bistable, sitting at either -73 or -10 mV.
    #
    # We give those classes one extra current: a slow calcium-activated potassium
    # conductance, which C. elegans expresses (SLO-1/SLO-2). A cell with fast excitation
    # and slow self-inhibition is a relaxation oscillator -- it depolarises, the slow
    # conductance accumulates and shuts it off, the conductance decays, and it starts
    # again. The period is set by adapt_tau, which is why that number lands the undulation
    # frequency in the right band.
    # A slow conductance on its own is not enough: a fast pole plus a slow pole in
    # negative feedback is overdamped and simply relaxes. A relaxation oscillator needs a
    # *regenerative* fast inward current as well, so that the voltage nullcline folds and
    # the cell has two quasi-stable branches for the slow current to alternate between.
    # This is the Morris-Lecar structure, and it is also the right biology: C. elegans has
    # no voltage-gated sodium channels at all, and every regenerative event in the animal
    # is carried by calcium (EGL-19, UNC-2) and terminated by potassium (SHK-1, SLO-1/2).
    # It is the same construction c302's graded parameter set C0 uses.
    # An earlier version of this model set these to zero, on the following argument: the
    # dorsal and ventral members of a class have identical intrinsic dynamics and are
    # coupled by gap junctions and reciprocal synapses, so they phase-lock *to each other*,
    # the animal contracts both sides in time with itself, and it does not bend at all.
    # That observation is correct but the conclusion drawn from it was wrong. It argues
    # that an intrinsic oscillator cannot be the source of dorsoventral *antisymmetry* --
    # which the head proprioceptive reflex supplies (SensoryParams.head_proprio_gain) --
    # not that it cannot be the source of amplitude down the body, which is a separate job
    # and the one the analysis below shows nothing else can do.
    # Xu, Kawano et al. (2018) PNAS 115:E4493 solved this model class analytically and the
    # result is why none of the parameter sweeps above could ever have worked. For a chain
    # in which motor neurons are *passive* recipients of proprioceptive input, bending
    # amplitude decays exponentially towards the tail with a length constant
    #
    #     xi  ~  l / (1 - c * alpha_max / b)        subject to  c*alpha_max/b <= 1
    #
    # where l is the proprioceptive reach, c its gain, alpha_max the muscle torque and b the
    # bending modulus. Head reflex gain, muscle moment, bending stiffness and the muscle
    # taper are all just different ways of moving that one lumped quantity, which is capped
    # at 1 -- so a flat wave demands sitting within a few percent of an instability bound.
    # Measured here: 7-fold decay over one body length, i.e. c*alpha_max/b = 0.61. Not a
    # local optimum with a better peak elsewhere; a razor's edge with no viable peak.
    #
    # Their resolution, and the one implemented here: each B-type motor neuron is a
    # Morris-Lecar unit held at a Hopf bifurcation by tonic gap-junction current from AVB.
    # Amplitude is then regenerated locally, segment by segment, and proprioception carries
    # only *phase*. A regenerative segment restores amplitude; a passive filter cannot.
    # Measured effect: bending amplitude head/mid/tail went from 2.5/1.3/1.0 to 2.6/1.9/1.9,
    # and net speed from 0.105 to 0.172 mm/s against 0.219 for the animal.
    #
    # This also explains why clamping AVB earlier did nothing: in a *linear* chain, AVB
    # coupling can only shunt, replacing c with c*g_m/(g_m+g), which makes the decay worse.
    # That null result was evidence the units were linear, not evidence AVB is irrelevant.
    #
    # Xu et al.'s absolute conductances are not transplantable here, and the reason is
    # worth recording. Their B-type unit is isolated: g_L = 100 pS is the whole of its
    # resting conductance. In the reconstructed connectome a B neuron also carries its gap
    # junctions and its synaptic load, which measure 0.38 to 2.95 nS -- a factor of eight
    # between VB09 and DB07, and 1.5 to 12 times g_leak. Fixed conductances tuned for any
    # one of those units leave the rest either silent or saturated, which is exactly what
    # a first transplant attempt produced: every unit sat quiescent at -56 mV with the
    # potassium gate 47% open at rest, holding the calcium gate shut at 0.5%.
    #
    # So the intrinsic conductances are specified as fractions of each neuron's *own*
    # total resting conductance, and the half-activations as offsets from its *own*
    # resting potential. Every B unit then sits at the same relative operating point
    # regardless of how heavily the connectome loads it. This is also the more defensible
    # biology -- channel count scales with membrane area, and so does leak -- and it has a
    # useful side effect: because the gates take known constant values at rest, the
    # release-threshold solve stays linear and stays exact.
    #
    # Instability of the fixed point (the Hopf condition) is then a pure ratio statement,
    # independent of the individual neuron:
    #
    #     ca_ratio * [ m0' * (E_Ca - V_rest) - m0 ]  -  adapt_ratio * n0  >  1
    #
    # with m0, n0 the gate values at rest and m0' = 1/(2*ca_slope) * sech^2(ca_offset/
    # ca_slope). At the values below it evaluates to 0.94 -- which is to say the working
    # model sits *at* the bifurcation rather than past it, and that is a measured result,
    # not a target. Sweeping ca_ratio over 0.00 to 0.45 and scoring on net displacement
    # (tools/osc_control.py, tools/tau_sweep.py, three seeds each) peaks at 0.20:
    #
    #   ca_ratio   margin   free-running without proprioception?   net mm/s
    #     0.00      0.00    no                                      0.120
    #     0.13      0.64    no                                      0.145
    #     0.20      0.94    marginal (4.0 mV sd)                    0.172   <-- best
    #     0.26      1.17    yes      (7.4 mV sd)                    0.155
    #     0.32      1.40    yes     (10.9 mV sd)                    0.139
    #
    # The peak is exactly where the units stop being entrainable and start free-running,
    # and the reason is the one that makes critically-poised systems useful generally: the
    # regenerative gain that cancels the relay's exponential decay is largest right at the
    # bifurcation, while the cell still follows its input instead of ignoring it. Pushed
    # past it -- ca_ratio 0.55, the first thing tried here -- each segment locks to itself,
    # tail bending amplitude runs 4x the head's, and the wave runs *backwards* (travelling
    # index -0.45): 18 autonomous oscillators with the posterior ones leading.
    #
    # So these are conditional oscillators in the sense that matters -- the descending AVB
    # drive is what puts them near the bifurcation, and removing it drops them back to
    # passive -- but in normal forward locomotion they are better described as critically
    # poised regenerative amplifiers than as autonomous oscillators.
    ca_ratio: float = 0.20       # g_Ca as a fraction of the neuron's resting conductance
    adapt_ratio: float = 0.40    # g_K  as a fraction of the neuron's resting conductance
    ca_offset: float = 0.0       # mV   Ca half-activation, relative to that neuron's rest
    ca_slope: float = 8.0        # mV
    k_offset: float = 10.0       # mV   K half-activation, relative to that neuron's rest
    k_slope: float = 12.0        # mV
    adapt_tau: float = 0.30      # s    interior optimum; see below
    E_Ca: float = 60.0           # mV
    E_K: float = -70.0           # mV

    # The bifurcation parameter is the descending drive from AVB, and it needs no parameter
    # at all: the reconstructed connectome already contains 55 AVB gap-junction contacts
    # distributed over all 18 B-type units, and AVBL/AVBR rest at -21.2/-21.4 mV -- within
    # 1.4 mV of the V_AVB = -20 mV Xu et al. had to assume. The drive is therefore real,
    # already correctly placed, and correctly signed, and adding a synthetic conductance
    # on top of it would double-count.
    #
    # Clamping AVB to -70 mV was expected to quiet the units and does not: their voltage
    # swing nearly doubles (8.4 -> 15.7 mV sd), curvature rms goes from 2.1 to 7.5, the
    # wave reverses to -0.69 and net speed collapses to 0.018 mm/s. Two things are mixed
    # together there. The reversal is correct -- the proprioceptive command gate reads AVB
    # activity, so silencing it hands the cord to the A-class backward generator, and a
    # backward wave *should* travel tail to head. The rest is not: hyperpolarising past the
    # potassium half-activation closes the restoring conductance faster than it closes the
    # calcium one, so the unit gets less stable rather than more. The gate offsets are
    # placed relative to a resting potential solved with AVB intact and do not follow it
    # down. Backward locomotion is therefore known-poor in this model and is an open item,
    # not a validated behaviour.
    #
    # adapt_tau is set by measurement, and it is a genuine interior optimum rather than a
    # boundary: net displacement over 0.08/0.12/0.18/0.25/0.30/0.60/0.90/1.40 s runs
    # 0.149/0.157/0.167/0.171/0.172/0.164/0.158/0.151 mm/s. Below the peak the potassium
    # gate tracks the voltage too closely and cancels the calcium current; above it, the
    # gate barely moves within a cycle and the amplifier stops being phasic.
    #
    # One thing this does NOT fix, and the honest place to record it: the model still
    # undulates at 1.17 Hz against 0.4-0.5 Hz for a real animal on agar (Gray & Lissmann
    # 1964; Berri et al. 2009). The frequency is set by the reflex loop and the body's
    # mechanics, not by this time constant -- sweeping adapt_tau over an eighteen-fold
    # range moves it by less than 5%. Correcting it means going after the mechanics
    # (drag, internal damping, muscle activation kinetics), which is the next thread.
    # Physiological rail, set at the potassium and calcium reversals. Motor neurons under
    # strong proprioceptive drive do reach the lower rail at the extremes of each cycle.
    # That is saturation rather than instability, and it is consistent with how the
    # reference neuromechanical models treat these cells -- Boyle et al. (2012) make their
    # B-type motor neurons frankly binary. Interneurons and sensory neurons stay well
    # inside the range.
    v_clamp: tuple = (-80.0, 45.0)    # mV
    # Both cords, not just the forward one. The B class got this treatment first because
    # forward locomotion was what was being measured, and that asymmetry turned out to be
    # the reason the animal could not reverse: dropping the descending forward drive took
    # the B units off their bifurcation, and the A units waiting to take over were still
    # passive relays with no way to regenerate a backward wave. The worm thrashed in place
    # (net/path 0.05) instead of reversing.
    #
    # The anatomy says they should be symmetric, and if anything favours the backward
    # cord: AVA makes 102 gap-junction contacts onto 20 of the 21 A-class units and rests
    # at -26.7 mV, against AVB's 55 contacts onto 18 B-class units at -24.4 mV. Same
    # architecture, same descending-drive-holds-it-at-the-bifurcation story.
    # -- synaptic depression, which is the only memory in this model -----------------------
    # Everything else here forgets. The adaptation filters in Senses exist precisely to
    # discard the past, the modulators integrate over tens of seconds and then decay, and
    # nothing at all outlives a minute. So the animal cannot learn, and the first learning
    # it should be able to do is the simplest kind there is: habituation.
    #
    # Rankin, Beck & Chiba (1990) Behav. Brain Res. 37:89 tap a plate every ten seconds and
    # watch the reversal response fall away over about thirty taps, recover over minutes of
    # rest, and habituate more deeply at shorter intervals. Rose & Rankin's later work
    # places the change presynaptically, as reduced glutamate release from the touch
    # receptors onto the interneurons, rather than in the interneurons themselves.
    #
    # That is a released-resource model, and it is the standard one (Tsodyks & Markram
    # 1997). Each depressing terminal carries a resource D in [0, 1] which is consumed in
    # proportion to how hard the cell is releasing and refills with its own time constant:
    #
    #     dD/dt = (1 - D) / depression_tau  -  depression_use * phi(V_pre) * D
    #
    # and the postsynaptic conductance sees s * D instead of s. Integrated exactly, the
    # same way as everything else here, so it does not depend on the step size.
    #
    # Three properties fall out of that one equation rather than being fitted separately,
    # which is the reason to prefer it to a decay term bolted onto the touch pathway:
    # repeated stimulation depresses, rest recovers with depression_tau, and a shorter
    # interval habituates more deeply because less refilling happens in between.
    #
    # Zero-safe: at depression_use = 0 the resource sits at 1 and the model is untouched.
    depression_classes: tuple = ("ALM", "AVM", "PLM", "PVM")
    depression_use: float = 0.0      # 1/s  consumption per unit release
    depression_tau: float = 20.0     # s    refilling time constant

    # -- the command layer's own dynamics --------------------------------------------------
    # Two knobs, both zero by default, aimed at one measured failure: the animal does not
    # spontaneously reverse. Measured with tools/assays.py triage, six animals for sixty
    # seconds each: zero reversals, with the direction gate sitting at 0.95 forward in
    # every animal for the whole run. That is not a small discrepancy against 3.2-3.5
    # reversals per minute off food (Zhao et al. 2003), and it is not a cosmetic one
    # either, because C. elegans chemotaxis *is* reversals: Pierce-Shimomura, Morse &
    # Lockery (1999) showed the animal does not steer up a gradient, it suppresses sharp
    # turns while conditions improve. A worm that never turns cannot chemotax however good
    # its nose is, which is the most likely reading of the chemotaxis null in NEXT.md.
    #
    # There are two separate reasons the reversal never happens, and they need separate
    # fixes.
    #
    # 1. The pools have no antagonism. Every command interneuron here is cholinergic or
    #    glutamatergic and the model collapses both to a 0 mV reversal, so the forward
    #    pool and the backward pool *excite each other*: 70 reconstructed contacts from
    #    forward onto backward, 33 the other way, plus 10 gap junctions. Two pools that
    #    excite each other rise and fall together, and the direction decision reads the one
    #    quantity common drive cannot move -- their difference. This is a wiring statement,
    #    not a gain one; it is why sweeping chemo_gain 46x moved the chemotaxis outcome by
    #    less than the seed-to-seed spread. command_cross_inhibition retargets those
    #    cross-pool synapses onto an inhibitory receptor, blending E_exc to E_inh, which
    #    makes the pair a winner-take-all instead of a mutual amplifier.
    #
    #    The licence for that is the same one this model already uses in the other
    #    direction. AVL and DVB stain for GABA and are inhibitory in every standard model,
    #    and here they are excitatory, because their GABA lands on the cation channel
    #    EXP-1. The mirror case is that C. elegans glutamate opens glutamate-gated chloride
    #    channels (AVR-14, AVR-15, GLC-1/2/3) as well as the AMPA-type GLR-1, so a
    #    glutamatergic synapse in this animal is inhibitory or excitatory according to the
    #    receptor the postsynaptic cell expresses. Reversal potential is therefore a
    #    property of the synapse, which is why NervousSystem now carries a (post, pre)
    #    matrix rather than a per-neuron vector.
    #
    # 2. Nothing ends a forward run. Even a perfect winner-take-all is a latch: it picks a
    #    side and holds it. Spontaneous alternation needs the winning side to tire, which
    #    is the half-centre construction (Brown 1911) that CPG models have used ever since,
    #    and which whole-brain imaging supports here -- Kato et al. (2015) find the motor
    #    command state traversing a cyclic trajectory rather than resting in a stable
    #    fixed point. command_adapt_ratio gives the command interneurons a potassium
    #    conductance of their own, sized as a fraction of each cell's resting conductance
    #    like every other intrinsic current in this model, and command_adapt_tau sets how
    #    long a run lasts before it gives out.
    #
    # Neither is calibrated yet. Both are zero, which reproduces the current model exactly,
    # and the measurement that will set them is tools/ethogram.py.
    # -- glutamate-gated chloride, and the sign of chemotaxis -------------------------------
    # The chemotaxis assay reproduces Pierce-Shimomura's biased random walk with the bias
    # pointing the wrong way: the animal reverses 13.4 times a minute while conditions
    # improve and 9.0 while they worsen, a ratio of 0.68 where the animal is about 2 and
    # anything above 1 is chemotaxis. It turns *more* when things are getting better.
    #
    # The route is short and the sign error is in it. ASEL and ASER both project onto AIY
    # (19 and 16 contacts), AIY projects onto AIZ (21), and AIZ makes 10 contacts onto the
    # backward command pool -- AIY itself makes none. So rising attractant depolarises
    # ASEL, which excites AIY, which excites AIZ, which drives a reversal. Measured
    # directly: 3 pA into AIY takes the reversal rate from 4.7 to 6.0 per minute, and the
    # same current into AIZ does the same thing.
    #
    # In the animal AIY does the opposite -- it sustains forward runs and suppresses
    # turning -- and the reason this model has it backwards is the same simplification
    # that made the command pools mutually excitatory: glutamate collapsed to a single
    # excitatory reversal. Chalasani et al. (2007) Nature 450:63 showed that the same
    # glutamate release inhibits AIY through the glutamate-gated chloride channel GLC-3
    # while exciting AIB through the AMPA-type GLR-1. One transmitter, two receptors,
    # opposite signs -- which is the whole mechanism, and none of it survives a model that
    # decides a synapse's sign from the transmitter alone.
    #
    # So the correction is the same one already made for AVL and DVB, run the other way,
    # and it uses the same per-synapse reversal machinery: name the glutamatergic senders
    # and the cells that answer them with a chloride channel. AIB is deliberately not in
    # the list -- it holds GLR-1 and should stay excited.
    # Named per *cell*, not per class, and that is the whole point. ASEL and ASER are one
    # anatomical class and a genuine opponent pair -- Senses gives ASEL +dC/dt and ASER
    # -dC/dt -- but they project onto the same first-layer interneurons with the same sign,
    # 19 contacts onto AIY against 16. So AIY receives (+dC/dt) + (-dC/dt) and **the
    # opponency cancels itself at the first synapse**. Giving them the same receptor, as
    # ("ASE",) did, cancels it exactly:
    #
    #   chloride on        improving   worsening   opponency
    #   neither             +0.15409    +0.15435    -0.00026
    #   both                +0.15412    +0.15412    -0.00000    exactly nothing
    #   ASEL only (ON)      +0.15457    +0.15379    +0.00078    correct sign
    #   ASER only (OFF)     +0.15376    +0.15465    -0.00089    inverted
    #
    # (shift in the forward-minus-backward command difference under a held 3 pA gradient.)
    # So the ON cell answers glutamate with chloride and the OFF cell does not, and the two
    # then push AIY the same way instead of against each other. AWA and AWC are the
    # equivalent pair for volatile odour and get the same treatment by analogy, which is
    # not separately measured.
    #
    # The sign is now right and **the magnitude is still about a hundredfold short**:
    # +0.00078 against a difference whose standard deviation is 0.0885, so 0.009 sigma
    # where biasing the walk wants of order 0.1. That is not attenuation along the way --
    # the chain is strong at every stage, ASE->AIY being 206% of AIY's own conductance,
    # AIY->AIZ 91%, AIZ->AVE 25% -- so where it goes is a separate question and an open one.
    # PHB -> AVA joined the chloride list with the phasmid route (2026-08-24). Hilliard
    # et al. 2002 is the functional evidence: a repellent at the tail drives forward
    # acceleration, so the phasmids must *antagonise* the reversal command, and PHB's
    # glutamatergic synapses land directly on AVA (29 contacts here). As reconstructed --
    # every synapse excitatory -- the route is not merely weak but inverted, measured two
    # ways with the phasmids routed:
    #
    #   escape, paired per seed (40 s, drop 2 mm beyond the nose / behind the tail;
    #   final distance from the drop, phasmids routed minus deaf-tailed):
    #     head arm  -1.37 mm      tail arm  -0.74 mm     -- routing the tail HURT
    #   command, dAVA under a 2 s, 25 pA step into each pool (noise off, paired):
    #     into ASH  +0.566 mV     into PHA/PHB  +0.714 mV -- tail outranks head, backwards
    #
    # With chloride on PHB -> AVA the same two measures read: escape -0.21/-0.33 mm
    # (the harm gone, within seed noise of zero) and dAVA +0.572 into ASH against
    # +0.070 into the phasmids -- the same stimulus, an eightfold smaller backward
    # command when it arrives at the tail, with PHB -> PVC (22 contacts) left excitatory
    # to carry the forward half. The cross-product below adds exactly those four
    # synapses: ASEL/AWA -> AVA and PHB -> AIY have no contacts in this reconstruction,
    # which was checked before widening the lists.
    glucl_pre: tuple = ("ASEL", "AWA", "PHB")   # ON cells, plus the tail's repellent line
    glucl_post: tuple = ("AIY", "AVA")          # targets expressing the chloride receptor
    # Adopted at 1.0. Measured directly, as reversals per minute under a steady 3 pA into
    # ASEL -- which is what "the attractant is rising" looks like to the circuit:
    #
    #   glucl   baseline   ASEL driven   effect of things improving
    #    0.0      4.67        5.00        +0.33   promotes reversal  (wrong way)
    #    1.0      5.00        4.67        -0.33   suppresses reversal (right way)
    #
    # The sign is now the animal's. The magnitude is small because the route is thin --
    # see the note above on how few contacts carry it -- so this changes which way the
    # bias points without yet making it strong. Locomotion is untouched: on a bare plate
    # ASE is not driven at all, and speed, travelling index and reversal rate are the same
    # to three decimal places at 0.0 and 1.0.
    #
    # On the plate it moves the bias without yet winning the argument. The chemotaxis
    # assay's pirouette ratio -- reversals while worsening over reversals while improving,
    # which is above 1 for any animal that chemotaxes and about 2 for a real one -- goes
    # from 0.68 to 0.88. Better, and still the wrong side of 1.
    #
    # Raising chemo_gain does not close it and makes it worse: at 150 pA/unit, six times
    # the calibrated value, the ratio falls back to 0.66. So there is a second route from
    # ASE to the backward pool that promotes reversals as the attractant rises, and it
    # outruns the AIY arm when both are driven hard. The likely one is ASE onto AIB onto
    # RIM, which reaches the backward pool through 16 gap junctions, and it is not
    # correctable the same way -- AIB holds GLR-1 and is *supposed* to be excited.
    #
    # What is missing is the opponency itself. ASEL should be the cell that says "better"
    # and ASER the cell that says "worse", and in this reconstruction they are wired almost
    # identically: ASEL makes 19 contacts onto AIY and 9 onto AIB, ASER makes 16 and 12.
    # Their separation in the animal is functional -- different receptors and neuropeptides
    # downstream -- rather than anatomical, so contact counts alone cannot produce it and
    # no amount of gain on a symmetric pair will either.
    glucl_strength: float = 1.0           # 0 = as reconstructed, 1 = fully inhibitory

    command_forward: tuple = ("AVB", "PVC")
    command_backward: tuple = ("AVA", "AVD", "AVE")
    # Measured, in the order the sweeps ran, and the order matters because the second
    # result overturns the reasoning behind the first:
    #
    #   cross  adapt |  corr   difference   margin   rev/min   dur s |  speed   net/path
    #    0.00   0.00 | +0.744   +0.2128      3.83     1.67     0.06  |  0.1853   0.783
    #    1.00   0.00 | +0.737   +0.2316      4.30     1.00     0.02  |  0.2077   0.853
    #    0.00   0.05 | +0.694   +0.1957      2.95    12.00     0.06  |  0.1839   0.798
    #    0.00   0.10 | +0.611   +0.1808      2.18    30.00     0.07  |  0.1752   0.783
    #    1.00   0.10 | +0.608   +0.1959      2.52    18.33     0.08  |  0.1954   0.843
    #    0.00   0.30 | +0.473   +0.1220      0.42    82.33     0.22  |  0.0974   0.518
    #
    # Cross-inhibition alone does nothing: the correlation will not move and the margin
    # gets worse, because the forward pool's 70 contacts outweigh the 33 coming back and
    # because the pools are correlated by shared input rather than by the synapses between
    # them. Adaptation alone moves the margin exactly as intended, 3.83 -> 2.18, and buys
    # nothing behavioural, which the duration column gives away: **every episode lasts
    # 0.06-0.08 s at every setting**, one fifteenth of an undulation cycle. That is the
    # difference dipping below a threshold it still sits above, not an animal reversing.
    # Pushed until the rate looks biological the margin collapses to 0.42 sigma and
    # locomotion halves, which is the same failure with the threshold now inside the noise.
    #
    # So fatigue is not sufficient, and the missing property is *persistence*: a reversal
    # is a state the animal stays in for seconds. command_ca_ratio adds the regenerative
    # limb that makes the far side of the threshold somewhere it can stay -- see
    # NervousSystem for why that is the right reading and where the biology comes from.
    command_cross_inhibition: float = 0.0   # 0 = as reconstructed, 1 = fully inhibitory
    # Adopted once the gate was latched, which is the whole story of this parameter.
    # Under the graded gate it was worthless: it moved the margin exactly as intended and
    # produced only 0.07 s flickers, because the drive to the cords was proportional to
    # the very difference it was moving, so any dynamics in the command layer came
    # straight out of the gait. With the drive constant and the choice latched, the same
    # conductance does what it was always meant to -- it makes the winning side tire, so a
    # reversal is something the animal falls into and climbs out of rather than a threshold
    # crossing. Measured (tools/command_sweep.py, three seeds, gate_hysteresis 0.04):
    #
    #   adapt  gate_bias | rev/min   dur s   %rev |  speed   net/path    TWI
    #    0.00     0.16       2.67     0.44    1.8 |  0.2079   0.823    +0.781
    #    0.05     0.14       2.67     0.48    2.1 |  0.2182   0.849    +0.785
    #    0.10     0.12       2.67     0.44    1.8 |  0.2190   0.842    +0.789
    #    0.10     0.13       4.67     0.69    5.3 |  0.2077   0.813    +0.769   <- adopted
    #    0.10     0.14      12.00     0.77   15.9 |  0.1556   0.640    +0.580
    #
    # 4.67 reversals per minute against the animal's 3.2-3.5 off food, and episodes of
    # 0.69 s against the 0.06 s the graded gate produced -- eleven times longer, and within
    # sight of the one to four seconds a real reversal lasts. Adaptation raises the mean
    # difference as well as lengthening the episodes, so gate_bias comes down with it;
    # rows at fixed bias are not comparable across this parameter.
    command_adapt_ratio: float = 0.10       # g_K as a fraction of resting conductance
    command_adapt_tau: float = 15.0         # s   the timescale of a forward run
    command_ca_ratio: float = 0.0           # g_Ca as a fraction of resting conductance
    # Which command cells carry it, and this is the parameter the measurements care about.
    # Regenerative calcium on the *forward* pool costs half the locomotion whatever else is
    # done with it -- with the gate held so that the animal never reversed once, net/path
    # still fell 0.783 -> 0.400, and closing the calcium gate at rest (command_ca_offset
    # 8 and 16 mV) made it slightly worse rather than better, which rules out the resting
    # depolarisation as the cause. The remaining explanation is structural and is the same
    # conflation day five only half removed: AVB's membrane potential is the bifurcation
    # parameter for the entire B cord, delivered through 58 gap-junction contacts that the
    # connectome already contains. Giving AVB dynamics of its own is therefore not a change
    # to the decision, it is a change to the gait.
    #
    # AVA has no such conflict. Its 102 gap contacts land on the A class, which carries no
    # regenerative conductance at all (a_class_scale is 0), so it is poising nothing. It is
    # also where the biology puts the bistability in the first place: AVA is the cell with
    # the documented all-or-none depolarised plateaus.
    command_ca_classes: tuple = ("AVA", "AVD", "AVE", "AVB", "PVC")
    # Calcium half-activation for the command layer, relative to each cell's own rest.
    # The motor classes use 0, which leaves the gate half open at rest; that is a standing
    # depolarising load, and on these cells it costs the gait directly -- with reversals
    # switched off entirely, ca 0.35 still took net/path from 0.783 to 0.400, because
    # AVB's resting potential is what poises the whole B cord. Placing this above rest
    # keeps the conductance shut until the cell is driven. 0.0 reproduces the motor-class
    # placement, and is the default only because it is the one already measured.
    command_ca_offset: float = 0.0          # mV above each command cell's rest

    oscillator_classes: tuple = ("DB", "VB", "DA", "VA")
    # ...but scaled down, because the command circuit does not currently separate the two
    # cords enough to do it for us. Measured during forward locomotion: the B class sits
    # at calcium gate 0.780 and the A class at 0.670, both above the 0.5 bifurcation, only
    # 2.2 mV apart. Held at equal strength both cords amplify at once and fight over the
    # same muscles -- forward speed fell 23%, from 0.175 to 0.136 mm/s. This factor is the
    # stopgap; the real fix is to give the AVA/AVB state some dynamic range, which is the
    # same missing piece that blocks chemotaxis.
    #
    # It is zero, and that is a measured result rather than an omission. Sweeping it over
    # 0 / 0.25 / 0.5 / 0.75 / 1.0, three seeds each (tools/reversal_test.py):
    #
    #   scale   forward mm/s   forward net/path   backward net/path   backward along-axis
    #    0.00      0.1753           0.832               0.199              -0.0138
    #    0.25      0.1713           0.828               0.253              -0.0111
    #    0.50      0.1649           0.815               0.248              +0.0075
    #    0.75      0.1532           0.786               0.221              +0.0133
    #    1.00      0.1357           0.738               0.289              -0.0275
    #
    # Forward degrades monotonically and backward never reaches working locomotion at any
    # value -- 0.289 against forward's 0.832, and the along-axis column changes sign, which
    # means at the middle settings the animal is still creeping nose-first while being told
    # to reverse. Those backward differences are within the seed spread. So there is no
    # setting that buys anything, and the machinery stays switched off until the thing that
    # actually blocks it is fixed.
    #
    # One caveat on that conclusion: the backward test commands a reversal by clamping AVB
    # to -60 mV, which also strips the B class of its own Hopf drive. That is blunter than
    # a real reversal and makes the backward numbers a lower bound rather than a verdict.
    a_class_scale: float = 0.0   # multiplies ca_ratio/adapt_ratio for the DA/VA units

    # -- noise --------------------------------------------------------------------------
    # Real neurons are noisy, and a deterministic network settles into a fixed point and
    # stops behaving. This is Ornstein-Uhlenbeck current noise, not white noise, so its
    # amplitude does not depend on the integration step.
    noise_sigma: float = 2.2     # pA  standard deviation of the background current
    noise_tau: float = 0.15      # s   correlation time

    # -- integration --------------------------------------------------------------------
    dt: float = 0.0005           # s   0.5 ms; tau_m/dt = 50


@dataclass(frozen=True)
class MuscleParams:
    """Body-wall muscle: NMJ input -> intracellular calcium -> active tension.

    C. elegans body-wall muscle cells are also non-spiking. They integrate graded
    cholinergic (excitatory) and GABAergic (inhibitory) input from the motor neurons,
    and their tension follows intracellular calcium with a time constant of a few tens
    of milliseconds (Boyle & Cohen 2008, "C. elegans body wall muscles are simple
    actuators"). We keep all 95 muscle cells as separate state variables.
    """

    # Boyle et al. (2012) lump the whole excitation-contraction cascade into a single
    # 100 ms first-order lag. We keep the two physical stages separate -- membrane
    # potential, then calcium-dependent tension -- but hold their combined time constant
    # at the same 100 ms.
    tau_calcium: float = 0.060      # s   membrane potential -> intracellular calcium
    tau_tension: float = 0.035      # s   calcium -> active tension

    # -- force-velocity, off by default ---------------------------------------------------
    #
    # Muscle here produces a tension that depends on calcium and on nothing else. Real muscle
    # produces less force the faster it is shortening and more while being stretched -- Hill
    # (1938), and the single most-cited property of the tissue after its length-tension curve.
    # This model has no term for it, and `MediumParams` records why that became interesting:
    #
    #   the loop's frequency is set by its total lag, every element of which is a fixed
    #   constant except the body's drag response, and by K = 9 that one has become small
    #   against the rest. So the frequency saturates and gait modulation stops at 1.29x
    #   where the animal manages 5.87x.
    #
    # Force-velocity is a *second* load-dependent element and therefore the obvious candidate.
    # It is stated here as a candidate rather than as a fix, because there is a real argument
    # against it that the measurement has to settle: the shortening rate depends on the gait,
    # and the gait is currently similar in both media -- kappa_rms 4.45 on agar and 4.39 in
    # buffer at 0.66 and 0.83 Hz -- so the derating may simply apply about equally at both
    # ends and cancel out of the span. If it does, the load-dependence has to come from
    # proprioception instead, and that is a different change.
    #
    # `fv_vmax` is the characteristic shortening rate, in the units of d(kappa)/dt that the
    # joints actually see: 1/(mm*s). **Zero disables the whole term**, which is the shipped
    # state and is bit-identical to having no force-velocity code at all.
    #
    # For scale, and this is worth stating carefully because getting it wrong wasted a sweep:
    # the concentric factor is (1 - x)/(1 + fv_curvature*x) with x = v/vmax, which at
    # fv_curvature = 4 is 0.46 at x = 0.19 and 0.01 at x = 0.95. It bites near x ~ 0.05, not
    # near x ~ 1. An animal at kappa_rms 4.4 and 0.7 Hz sweeps about 19 /(mm*s), so vmax of
    # 1000 is a 9% derating, 500 is 17%, and anything at 100 or below is not a force-velocity
    # curve, it is a switch.
    #
    # MEASURED, AND IT IS NOT THE GAIT-MODULATION MECHANISM. tools/force_velocity.py, both
    # media, three seeds, no failures:
    #
    #   vmax   agar Hz   buffer Hz   span    wavelength span
    #   off     0.656      0.833     1.27x       1.10x
    #   1000    0.622      0.767     1.23x       1.10x
    #   700     0.600      0.733     1.22x       1.16x
    #   500     0.600      0.700     1.17x       1.17x
    #
    # The span does not widen; it narrows, monotonically, 1.27x to 1.17x. That is the failure
    # the sweep's own header predicted: the derating acts on shortening rate, shortening rate
    # is a property of the gait rather than of the medium, this model's gait is similar at
    # both ends, so the derating applies about equally at both and cancels out of the ratio --
    # while adding lag, which narrows it. The animal spans 5.87x.
    #
    # Two things in that table are worth keeping anyway. It makes the animal *better* in
    # buffer -- travelling index +0.657 to +0.682, net speed 0.0380 to 0.0413 mm/s -- and
    # worse on agar, +0.846 to +0.769 and 0.295 to 0.218 mm/s, with kappa_rms falling 4.45 to
    # 2.75. And the **wavelength span moves for the first time**, 1.10x to 1.17x. Trivial
    # against the animal's 2.37x, but nothing else tried has moved it at all.
    #
    # Not adopted. It is more faithful muscle than none and it costs the crawl, which is where
    # this model is calibrated; adopting it would mean re-fitting the gait to buy a property
    # that has just been measured not to arrive.
    #
    # And the candidacy itself is now settled (tools/fv_phase.py, 2026-08-13, open-loop
    # lock-in per medium): force-velocity IS a load-scaled time, backwards -- it adds
    # -16.8 deg of loop phase on agar and -34.9 in buffer, braking hardest where the animal
    # accelerates, which is why the closed-loop span narrowed -- and its load-dependence
    # saturates at the same K ~ 8 knee as the body's, because it reads the body's motion
    # and below the knee the bending dynamics carry no information about the medium at all.
    # The cancellation suspicion above was close but generous: the derating does not cancel
    # out of the span, it narrows it. Retired as a gait-modulation mechanism; remains what
    # this note always said it was, more faithful muscle at a cost to the calibrated crawl.
    fv_vmax: float = 0.0            # 1/(mm*s), 0 = off

    # Hill's curvature constant, the `a/F0` of the classic hyperbola. 4 is the usual value
    # for vertebrate skeletal muscle; the concentric branch is (1 - x)/(1 + fv_curvature*x)
    # with x = v/vmax, which is 1 at rest and 0 at vmax.
    fv_curvature: float = 4.0

    # How much more force the muscle makes while being lengthened, as a fraction above F0.
    # Real muscle plateaus around 1.4-1.8 F0; 0.5 puts the plateau at 1.5. This limb matters
    # here because half of every undulation is a muscle being stretched by its antagonist.
    fv_eccentric: float = 0.5

    # Time constant of the low-pass on the shortening rate, and it is required rather than
    # decorative.
    #
    # The first implementation fed back the raw finite difference of joint curvature, one
    # step apart. That quantity is not the gait's shortening velocity; it is dominated by the
    # body's fastest bending modes, which relax in about 6e-6 s in buffer against a 0.5 ms
    # step -- eighty times faster than the integrator resolves. Feeding it back explicitly
    # diverged in buffer at *every* strength tried, including a 9% derating: path speeds of
    # 150 to 300 mm/s against a 5 mm/s guard, at every seed.
    #
    # So this is not a fudge factor for a stability problem, it is the statement that a
    # muscle responds to how fast the animal is bending and not to how fast the discretisation
    # is ringing. 20 ms sits between `tau_tension` (35 ms) and the step, which is the band
    # where a real shortening velocity lives.
    fv_tau: float = 0.020           # s   low-pass on d(kappa)/dt before the Hill factor
    # Body-wall muscle has its own reversal potentials, and they are not the neuronal ones.
    # It rests at -25.0 +- 1.0 mV (Gao & Zhen 2011 PNAS), sits between E_ACh ~ +20 mV and
    # E_Cl ~ -30 mV, and its capacitance is an order of magnitude larger than a neuron's.
    # The narrow gap between rest and E_Cl is exactly why GABAergic inhibition of muscle
    # works mostly by shunting rather than by hyperpolarising.
    g_nmj: float = 1.30             # nS per NMJ contact
    E_exc: float = 20.0             # mV  nicotinic ACh receptor (cation)
    E_inh: float = -30.0            # mV  UNC-49 GABA-A (chloride)
    C_m: float = 50.0               # pF  Goodman et al. 2012: muscle is 50-70 pF
    g_leak: float = 2.2             # nS  -> tau_m ~ 23 ms
    E_leak: float = -32.0           # mV
    v_half: float = -22.0           # mV  half-activation of the tension curve
    beta: float = 0.22              # 1/mV steepness of the tension curve

    # Peak bending moment one side of the body can exert at midbody, at full activation.
    # Calibrated so the animal reaches the curvature amplitude real worms show on agar
    # (about 4-5 rad/mm); for scale, bending the body to that curvature against its own
    # elasticity alone costs EI*kappa ~ 0.45 uN mm.
    peak_moment: float = 2.6        # uN*mm

    # Resting tension each muscle sheet is calibrated to, and the fact that both sheets are
    # calibrated to the *same* value, which is what makes the resting posture straight.
    # Two things make that calibration necessary. The model is two-dimensional, so the left
    # and right members of each quadrant are merged; and the reconstructed contact count per
    # muscle cell ranges from 5 to 47, a spread that owes as much to how completely each
    # region of the original animal was sectioned as to real anatomy. Left uncorrected, the
    # heavier ventral innervation holds the worm in a permanent C. The relative weighting
    # among a given muscle's presynaptic partners stays exactly as reconstructed.
    rest_tension: float = 0.50
    normalise_nmj: bool = True

    # Body-wall muscle cells are electrically coupled to their neighbours. Boyle & Cohen
    # (2008) Biosystems 94:170 measure 370 pS between adjacent cells within a quadrant and
    # about 15 pS between quadrants, and this model omitted them entirely.
    #
    # That omission had a specific and measurable consequence. The tail muscle rows have
    # seven presynaptic motor neurons where the head has twenty-five, and the per-cell
    # conductance normalisation above then gives each of those few neurons roughly three
    # times the weight of its counterpart at the head. With no coupling between muscle
    # cells there is nothing to average across, so background noise in a single posterior
    # motor neuron passed straight through to the body: the tail ended up with the largest
    # oscillation amplitude anywhere on the animal and a coherence with the undulation of
    # 0.05, thrashing hard and completely out of time with the wave it was supposed to be
    # carrying. Coupling neighbouring cells low-passes the drive along the body, which is
    # what the real tissue does.
    g_muscle_gap: float = 0.37       # nS between adjacent cells in a quadrant
    g_quadrant_gap: float = 0.015    # nS between quadrants at the same body position

    # Body-wall muscle is stronger at the head than the tail. Boyle et al. (2012) use a
    # linear efficacy ramp from 0.70 to 0.29 head-to-tail and report that without it the
    # model produces a standing wave rather than a travelling one.
    efficacy_head: float = 1.0
    efficacy_tail: float = 0.41


@dataclass(frozen=True)
class BodyParams:
    """Inextensible active elastica at zero Reynolds number.

    The body is an inextensible chain of `n_links` rigid segments. Because the Reynolds
    number of a swimming C. elegans is ~1e-3, inertia is entirely negligible: viscous
    drag balances internal elastic and muscular torques at every instant, so the dynamics
    are first-order in the configuration and there is no inertial stiffness to destabilise
    the integration.

    Drag follows resistive force theory: the force per unit length on a segment moving
    with velocity v is -(C_T t t^T + C_N n n^T) v, with C_N > C_T. That anisotropy is the
    entire reason an undulating worm moves forwards at all, and its magnitude is what
    distinguishes swimming in buffer from crawling on agar.
    """

    length: float = 1.0             # mm  adult hermaphrodite
    n_links: int = 48               # two per body-wall muscle row, as in Boyle et al. 2012
    radius_max: float = 0.035       # mm  Fang-Yen measured ~60 um diameter, Boyle used 80

    # Bending modulus, measured directly by Fang-Yen et al. (2010): EI = 9.5 (+- 1.0)
    # e-14 N m^2, which is 9.5e-2 uN mm^2 in our units.
    EI: float = 0.095               # uN*mm^2
    # Fang-Yen et al. bound the internal (tissue) viscosity at < 5e-16 N m^2 s = 5e-4
    # uN mm^2 s, i.e. negligible against the external medium. We keep a small nonzero
    # value inside that bound; it damps the highest bending modes and buys nothing else.
    #
    # "Negligible against the external medium" was checked, because it is a claim made on
    # agar and the external drag falls four and a half orders of magnitude by the time the
    # animal is in buffer. It holds anyway. tools/damping_sweep.py, four values from this one
    # down to zero, both media, three seeds:
    #
    #   damping   agar Hz    buffer Hz
    #   2.0e-04    0.656       0.833     <- shipped
    #   5.0e-05    0.667       0.867
    #   1.0e-05    0.678       0.867
    #   0.0e+00    0.667       0.867
    #
    # Switching it off entirely moves buffer by 1.04x and agar by 1.02x. So this term is not
    # what pins the swimming end, and the documented claim survives in the regime it was
    # never tested in. The value stands.
    #
    # One incidental observation, recorded rather than acted on: at zero the buffer travelling
    # index is +0.756 against the shipped +0.657, while agar's falls +0.846 to +0.809. Mixed,
    # small, and not obviously worth a change -- but if this parameter is ever revisited for
    # its own sake, that is the trade to look at.
    internal_damping: float = 2.0e-4   # uN*mm^2*s

    # Moment arm of the body-wall muscles about the centreline, as a fraction of the
    # local body radius. The muscle sheets lie just under the cuticle.
    muscle_moment_arm: float = 0.85

    # Substeps of the mechanics per neural step.
    #
    # The body is stiff and the step does not resolve it. Measured on the linearised
    # bending problem, 33 of 48 modes relax faster than one 0.5 ms step, the fastest in
    # 0.0055 ms -- ninety times faster than the step. The semi-implicit scheme is stable
    # there, but its treatment of a mode with dt/tau of order one is neither resolved nor
    # fully damped, and it therefore depends on dt.
    #
    # It is nonetheless *not* where the gait's step dependence lived. Substepping the
    # mechanics sixteen-fold at dt = 0.5 ms reproduces dt = 0.5 exactly, which is what
    # first showed the body's own integration was already converged and sent the search
    # towards the coupling instead -- see BodyParams.dt. Kept at 1, and kept at all because
    # it is the control that rules the mechanics out.
    substeps: int = 1

    dt: float = 0.0005              # s   standalone default; Simulation
                                    #     overrides this with NeuralParams.dt


@dataclass(frozen=True)
class MediumParams:
    """The physical medium the worm is in.

    Drag coefficients per unit body length, in uN*s/mm^2. These are the values used by
    Boyle, Berri & Cohen (2012) Front. Comput. Neurosci. 6:10, converted from their
    whole-body totals (kg/s over a 1 mm body):

        buffer   C_par = 3.3e-6 kg/s,  C_perp = 5.2e-6 kg/s   -> K = 1.58
        agar     C_par = 3.2e-3 kg/s,  C_perp = 128e-3 kg/s   -> K = 40

    The buffer numbers come from Lighthill slender-body theory; the agar tangential value
    is Niebur & Erdos' (1991) direct force measurement and the anisotropy K = 32-40 was
    measured by Berri et al. (2009).

    K is the whole story of gait modulation. It is the ratio of the drag resisting sideways
    motion to the drag resisting motion along the body, and it sets how much of each
    undulation is converted to forward progress rather than lost to slip: at K = 1 an
    undulating body goes nowhere at all, whatever its waveform. Fang-Yen et al. (2010)
    PNAS 107:20323 walked a real worm through the entire continuum by thickening the fluid
    around it, and the animal's gait changed continuously from a 1.76 Hz, 1.54-body-length
    swim to a 0.30 Hz, 0.65-body-length crawl. In this model, as in theirs, nothing about
    the nervous system changes between the two -- only these two numbers.

    WHERE THIS MODEL'S MODULATION ACTUALLY FAILS, measured across all three media rather
    than at the two ends (tools/head_medium.py, three seeds):

        arm      agar K=40   viscous K=9   buffer K=1.58
        shipped   0.656 Hz     0.844 Hz      0.833 Hz
        cascade   0.644 Hz     0.833 Hz      0.833 Hz

    **It saturates by K = 9.** Every bit of the response happens between K = 40 and K = 9 --
    1.29x -- and from K = 9 to K = 1.58 there is nothing at all: 0.99x and 1.00x. The animal
    does not saturate; it keeps accelerating the whole way down, which is how it reaches
    1.76 Hz. So the shortfall is not a uniformly weak response that wants a bigger gain. It
    is a response that stops existing exactly where swimming begins.

    And the frequency was never the only half of it. **Wavelength is flat**, and it is the
    variable that was not being watched: the animal goes 0.65 L to 1.54 L, a factor of 2.37,
    while this model goes 0.83 to 0.91 -- 1.10x, and the cascade 1.06x. At low K, where an
    undulating body converts almost nothing to forward progress, waveform is what is left to
    change, and this animal does not change it. Net speed in buffer is 0.038 mm/s against a
    real swim of roughly 0.4: it undulates at a plausible frequency and goes nowhere.

    AND THE REASON IT SATURATES IS STRUCTURAL, WHICH IS WORTH STATING PLAINLY BECAUSE IT
    MEANS NO AMOUNT OF TUNING FIXES IT.

    The undulation frequency is set by where the loop's total lag reaches half a period, and
    in this model that total is a sum of fixed constants plus exactly one term that depends
    on the medium -- the body's own drag response. Measured against the head reflex's lag
    budget, which is the largest single contributor (tools/head_cascade.py, on agar):

        head lag    frequency    product
        0.22 s       1.300 Hz     0.286
        0.50 s       0.644 Hz     0.322     (four stages, no transport delay)
        0.50 s       0.656 Hz     0.328     (head_tau plus head_delay, as shipped)

    Frequency goes as roughly 1/lag, and -- the part that matters -- **two structurally
    different implementations of the same 0.50 s land within 0.012 Hz of each other.** The
    ceiling is set by the lag's magnitude, not its shape. That is the same result the
    cascade's failure reported from the other direction.

    Everything else in the chain is a constant too: `head_tau` 0.22 s, `head_delay` 0.28 s,
    `tau_calcium` 0.060 s, `tau_tension` 0.035 s, the synapses. The muscle is
    `calcium -> tension` through two first-order lags with **no dependence on shortening
    velocity at all** -- no Hill force-velocity term, nothing that knows how fast it is being
    asked to contract.

    So the body's drag response is the only load-dependent element in the entire loop, and by
    K = 9 it has already become small compared with the fixed remainder. Below that the
    frequency is pinned by constants the medium cannot reach, and the wavelength -- set by a
    fixed proprioceptive reach -- has nothing to scale it either. The animal saturates
    because the model gave it exactly one way to feel the medium and it runs out.

    RETRACTION. The paragraph above is half right and its conclusion does not follow, and
    the refuting measurement is `tools/lag_span.py`. Cutting the head reflex's lag budget by
    four -- 0.500 s to 0.125 s, four stages throughout, no transport delay -- gives:

        head lag   agar Hz   buffer Hz   span
        0.500       0.644      0.833     1.29x
        0.250       0.967      1.300     1.34x
        0.125       1.356      1.900     1.40x

    The first claim survives: frequency really is set by the loop's total lag, and cutting it
    fourfold roughly doubles the frequency in both media. **The second does not.** If the
    media differed by an *additive* lag -- a large one on agar where the body resists, a
    negligible one in buffer where it does not -- then shrinking the fixed part would expose
    that difference and the span would open up sharply. It barely moves: 1.29x to 1.40x
    across a fourfold cut. Fitting the additive model to those two points puts the buffer-end
    body lag at about 0.8 s, larger than the head reflex's entire budget, which is not a
    thing a body with almost no drag on it can be doing.

    So the medium's 1.3x is **not** an additive lag difference, and "the body's drag response
    is the one load-dependent term" was the wrong reading of the saturation. What produces the
    1.3x that does exist is not identified, and neither is what would produce the animal's
    5.87x; two hypotheses have been eliminated rather than one confirmed.

    Two facts worth carrying forward from that sweep, both independent of the retraction:

      * **wavelength never modulates at all.** Its span is 1.06x, 1.01x and 1.03x at the three
        lag budgets, against the animal's 2.37x. Whatever is missing is missing at every lag,
        and the wavelength is set by a fixed proprioceptive reach with nothing scaling it;
      * **the shipped lag budget is near-optimal for the wave.** Cutting it degrades
        everything else -- travelling index 0.880 to 0.753 on agar and 0.761 to 0.434 in
        buffer, buffer net speed 0.039 to 0.016 mm/s, wavelength collapsing 0.86 to 0.48 L.
        A shorter loop is a faster, worse animal, so the cascade should keep its 0.50 s.

    Muscle force-velocity remains worth measuring -- it is a genuinely load-dependent element
    and `MuscleParams` now has one, off by default -- but it is a candidate on its own merits
    now rather than the conclusion of an argument, because the argument has been withdrawn.

    THE SHAPE OF WHAT DOES EXIST (tools/flambda_locus.py, 2026-08-12: nine media,
    K = 1.58-40 geometric, three seeds). In the (f, lambda) plane the model's points do not
    slide off the animal's crawl->swim chord -- the perpendicular offset never exceeds
    0.10 L -- they are *bunched* on it: 11% of the chord traversed, 89% of the frequency
    motion above K = 9, wave speed f*lambda spanning 1.37x against the animal's 13.9x. So
    under load, f and lambda ride one coupling together, in roughly the animal's proportion
    (log-log exponent ~0.22 against the chord's 0.49, coarse at this traversal), and it is
    that one coupling which is ~10x too small and saturating -- the flat wavelength is not a
    separate failure, and a fix aimed at lambda alone is aimed at a symptom. Whatever moves
    the operating point between K = 40 and K = 9 is the thing to localise; below K = 9
    nothing does.

    AND WHERE IT LIVES (tools/loop_medium.py, 2026-08-13: per-medium lock-in on the open
    head loop, five media, both body-reflex arms). The coupling is the passive body's
    bending relaxation and nothing else. From K = 40 to 7.9 the tension->curvature stage's
    phase moves +40 degrees while neuron, release and muscle move at most 0.2; below
    K = 7.9 nothing moves anywhere; the two arms are the same table, so the body reflex
    contributes nothing to the saturation. The form is tau = c_n / (EI k^4) -- committed
    as a prediction mid-run, knee landing where it was put -- which is why the saturation
    is immovable by tuning: every other element in the loop is load-independent by
    construction, and in buffer the body's relaxation is five orders of magnitude faster
    than the undulation period. The account closes quantitatively: measured plant phase
    plus the analytic receptor phase predicts the closed-loop frequency at every medium to
    within 1.5%. A gait-modulation mechanism must keep a *time* in the loop scaled to the
    load below K ~ 9, and candidates can now be screened open-loop -- see NEXT.md.

    One consequence sharp enough to state on its own (tools/fv_phase.py, the screen's
    first use): below the knee the whole plant -- gain and phase, current to curvature at
    matched drive -- is K-independent, so *no observer of the body's bending, linear or
    not, can distinguish media there*. What still differs below K ~ 8 is translation, not
    bending: thrust collapses with the anisotropy while the waveform stays put. Slip is
    the signal that survives.
    """

    name: str = "agar"
    c_tangential: float = 3.2       # uN*s/mm^2 per unit length
    c_normal: float = 128.0         # uN*s/mm^2 per unit length

    @property
    def anisotropy(self) -> float:
        return self.c_normal / self.c_tangential


MEDIA = {
    "buffer": MediumParams(name="buffer", c_tangential=3.3e-3, c_normal=5.2e-3),
    "viscous": MediumParams(name="viscous", c_tangential=0.10, c_normal=0.90),
    "agar": MediumParams(name="agar", c_tangential=3.2, c_normal=128.0),
}


@dataclass(frozen=True)
class WorldParams:
    """The dish."""

    # A 9 cm plate, which is what chemotaxis and thermotaxis assays are actually run on.
    # It was 25 mm -- a 5 cm dish -- and that was harmless while the animal crawled at
    # 0.10 mm/s and covered 20 mm in a 200 s assay. It is not harmless now: at 0.275 mm/s
    # the same assay covers 55 mm, further than the old dish was wide, so every trial
    # ended up pressed against the wall. That showed up first as a habituation test
    # failing -- sustained wall contact re-depletes the mechanoreceptor -- and it would
    # have quietly corrupted every taxis assay too.
    radius: float = 45.0            # mm  a 50 mm petri dish
    grid: int = 256          # 0.35 mm cells across a 9 cm plate

    # Oxygen. Ambient air is 21%; a dense lawn respires it down, and the depression has a
    # skirt because oxygen diffuses back in -- the same reason the attractant has one.
    # 5 mm is the shorter of the two because oxygen is also resupplied from the air above
    # the agar, not only laterally.
    #
    # THE OXYGEN MODEL IS STATIC, AND THERE IS NO `diffusion_oxygen`. There used to be one,
    # 0.02 mm^2/s, declared here and read by nothing, in either implementation. It is
    # deleted rather than implemented, and the reason is that the transport it named is
    # already in this file under another name: `o2_length_scale` IS the diffusion length.
    # 5 mm is how far oxygen spreads in from the air and through the agar before respiration
    # consumes it, which is sqrt(D/k) for the balance `D grad^2 c = k c` -- the same
    # steady-state equation the attractant skirt is written from, with oxygen's own numbers.
    # Declaring the coefficient as well is the same physics written twice with nothing to
    # reconcile the two when they disagree, and they did disagree: taken literally,
    # 0.02 mm^2/s over a 5 mm skirt is t ~ L^2/D = 1250 s, the same order as the tens of
    # minutes a lawn takes to deplete, so it is not even the fast field a quasi-static
    # approximation would want.
    #
    # What the model does instead is treat the depression as the equilibrium of the
    # *current* bacterial mass: `World` rebuilds it as sum_p f_p * shape_p whenever some
    # f_p moves, and never integrates it. See worm/world.py. Stepping it would need a
    # consumption term, a boundary condition for the resupply through the agar surface, and
    # a second stepped field in both implementations with its own conformance surface -- a
    # different model, not a parameter that was waiting to be plugged in.
    o2_ambient: float = 0.21
    o2_depth: float = 0.15          # how far a full-density lawn draws it down
    o2_length_scale: float = 5.0    # mm  skirt outside the lawn edge
    diffusion_attractant: float = 0.004   # mm^2/s   small molecules through agar
    diffusion_repellent: float = 0.004
    decay_attractant: float = 0.0008      # 1/s
    food_diffusion_scale: float = 1.0
    # Bacteria are eaten, and eating is what makes a food patch a gradient source that
    # slowly disappears.
    # Calibrated to this file's own stated intent -- that depletion should change the
    # animal's behaviour "over tens of minutes". At 0.02 units/s the 3x3 neighbourhood the
    # animal feeds from (9 units at full density) halves in about four minutes of continuous
    # occupancy and is stripped in eight, so a foraging worm thins its patch over tens of
    # minutes rather than instantly. The previous 0.9 was both 45x too fast and applied per
    # cell rather than as a total, which together removed 8.1 units/s and cleared the ground
    # under the animal in roughly two seconds.
    ingestion_rate: float = 0.02     # patch density units per second while pumping
    field_dt: float = 0.02           # s  chemical fields are updated at 50 Hz, not 2 kHz
    temp_cold: float = 17.0          # degC at one edge of the dish
    temp_warm: float = 25.0          # degC at the other


@dataclass(frozen=True)
class SensoryParams:
    """Gain and adaptation of the sensory neurons.

    C. elegans chemotaxis is driven far more by the *time derivative* of concentration
    than by its absolute value: the animal performs a biased random walk, suppressing
    reversals while conditions improve. ASE, AWC and AWA are therefore modelled as
    adapting sensors whose output tracks c - c_adapted.
    """

    # Gains are in pA. For scale, a sensory neuron's total conductance is a fraction of a
    # nanosiemens, so 10 pA is already a swing of tens of millivolts -- the same order as
    # the currents Wicks et al. injected experimentally (10-250 pA), and about a hundredth
    # of what the reference whole-connectome implementations use.
    chemo_gain: float = 26.0         # pA per unit normalised concentration
    chemo_tau_adapt: float = 3.5     # s   adaptation time constant
    thermo_gain: float = 9.0         # pA per degC deviation from the cultivation temperature
    thermo_tau_adapt: float = 12.0   # s
    cultivation_temp: float = 20.0   # degC
    oxygen_gain: float = 60.0        # pA per unit fractional O2 (so ~8 pA over the range)
    oxygen_preferred: float = 0.07   # fractional O2 that URX/AQR/PQR prefer

    # Oxygen sensed as a *change* as well as a level, and the reason is mechanical rather
    # than anatomical. A run-and-tumble walker with a position-dependent turning rate
    # settles at a density proportional to that rate -- it lingers where it turns often --
    # so an animal that turns more at high oxygen accumulates at high oxygen, which is
    # backwards. Measured before this went in: the oxygen circuit biases turning in the
    # right direction, 3.67 reversals a minute at ambient against 2.67 in a lawn, and the
    # animal still climbed the gradient, starting at 16.5% and ending at 20.8%.
    #
    # What actually produces accumulation is Pierce-Shimomura's mechanism, the same one
    # chemotaxis uses: suppress turning while conditions *improve*. That needs a derivative,
    # and every other channel in this file already has one -- chemosensation, odour and
    # thermosensation all adapt and report deviation from their own baseline. Oxygen was
    # the only purely tonic channel, and it is the only one whose taxis pointed the wrong
    # way.
    #
    # Both terms are kept because both are real: URX is a genuinely tonic receptor, and the
    # tonic part is what sets how much the animal turns at all, while the differential part
    # is what decides where it ends up.
    oxygen_d_gain: float = 900.0     # pA per unit O2 per second, on the adapted deviation
    oxygen_tau_adapt: float = 3.0    # s   baseline the differential part is measured from

    # The noxious drop, and the same lesson a second time.
    #
    # Every chemical sense in senses.py adapts and reports a deviation -- except this one,
    # which was read straight off the absolute concentration. That is exactly the shape
    # oxygen had before oxygen_d_gain, and it fails the same way for the same reason: a
    # tonic sense says "you are somewhere bad", never "you are heading somewhere worse",
    # and a biased random walk can only steer on the second.
    #
    # What it cost is worth writing down, because the tonic version did not merely fail to
    # repel. Dropped at the centre of a drop and paired against the same animal on plain
    # agar, the tonic model ended up *closer* to the drop than to nothing at all -- 9.83 mm
    # against 19.35 -- and took 438 s to clear 8 mm against 22. Five animals in twelve
    # never cleared it at all.
    #
    # The mechanism is not subtle once the differential is missing. ASH raises the reversal
    # rate (2.83 -> 10.00 a minute across the concentration range, measured), and a reversal
    # backs the animal along its own body. Reversing while heading *into* the drop moves it
    # out; reversing while heading *out* moves it back in. A tonic drive cannot tell those
    # apart, so it fires on both and the net effect is a brake -- the animal that reverses
    # most travels least, and it stays where the concentration is highest.
    #
    # Both terms are kept, as with oxygen: ASH is a genuinely tonic receptor and the tonic
    # part is what makes the animal reverse at all near a drop, while the differential part
    # is what decides which way it ends up going.
    # Calibrated on escape rather than on reversal counts, because reversal counts were
    # what hid the problem in the first place. Dropped at the centre and paired against
    # the same animal on plain agar, final distance from the drop:
    #
    #   d_gain |  plain / drop  | paired difference        | never escaped
    #        0 |  26.20 /  8.03 | -18.18 [-27.22, -10.45]  |  3/8
    #      200 |  26.20 / 10.96 | -15.24 [-24.05,  -3.44]  |  3/8
    #      600 |  26.20 / 29.43 |  +3.23 [ -5.11, +11.36]  |  0/8
    #     1500 |  26.20 / 30.30 |  +4.10 [ -6.40, +15.63]  |  0/8
    #     4000 |  26.20 / 35.97 |  +9.77 [ +3.28, +18.27]  |  0/8   <- adopted
    #
    # 600 is enough to stop the drop trapping anyone; 4000 is where the drop actually
    # drives the animal further out than empty agar does, which is the only version that
    # deserves to be called avoidance. It is a large number next to oxygen_d_gain's 900,
    # and it is large for a reason that is visible in the same table: the deviation it
    # multiplies is small and short-lived, because an animal crossing a 5 mm length scale
    # at a third of a millimetre a second is only in a *changing* concentration briefly.
    #
    # It cannot disturb anything else. drep is identically zero wherever there is no drop,
    # and the only assay plate carrying one is nociception's.
    repellent_d_gain: float = 4000.0  # pA per unit repellent per second, on the deviation
    repellent_tau_adapt: float = 2.0  # s  baseline the differential part is measured from

    # The tail's copy of the repellent sense: PHA/PHB, the phasmid neurons, sampling the
    # same field at nodes[-1] with the same transduction shape and the same adaptation tau
    # as ASH, but their own baseline. Hilliard et al. 2002 (Curr Biol 12:730) is the
    # provenance for both the modality and the reason it matters: a repellent applied to
    # the tail drives forward acceleration where the same repellent at the head drives
    # reversal, so escape *direction* is a head-versus-tail comparison, and an animal with
    # only ASH cannot make it. The wiring is asked, not scripted: PHB synapses onto both
    # PVC (forward) and AVA (backward) in this reconstruction, and which way the animal
    # actually goes is measured in tests/test_behaviour.py's escape-direction assay.
    phasmid_gain: float = 42.0        # pA per unit repellent at the tail (tonic)
    phasmid_d_gain: float = 4000.0    # pA per unit repellent per second, adapted deviation

    # BAG: the oxygen downshift sensor (Zimmer et al. 2009, Neuron 61:865). URX carries
    # the tonic level and the rising edge above; BAG takes the falling edge -- the
    # rectified negative deviation from the same adapting baseline, so the pair splits
    # the derivative between them and no new state is added.
    bag_gain: float = 900.0           # pA per unit O2 on the rectified downshift
    # Per uN of smoothed indentation force.
    #
    # This was 34 pA/uN against a receptor state that accumulated one whole force per step
    # and leaked with touch_tau, so the steady state was 700.5 x force at the shipped
    # timestep and the effective sensitivity was 34 x 700.5 = 23817. That accumulation also
    # made it proportional to 1/dt; Senses now keeps a plain exponential moving average and
    # the factor is written here instead of hidden in an integrator.
    #
    # Which made it obvious that it was two hundred times too big. A standard tap at that
    # sensitivity implies a **8745 mV** depolarisation of ALM, clamped by v_clamp to +45.
    # The mechanosensory channel was therefore not a sensor at all but a binary switch, and
    # anything graded downstream of it was invisible: the first attempt at habituation
    # depleted the receptor resource to 52% and changed the response by 2%, because 48% of
    # a stimulus two hundred times past the rail is still past the rail.
    #
    # Calibrated instead so that the receptor stays off the clamp and responds gradedly.
    # Measured, tap response of the backward command pool against a no-tap control:
    #
    #   touch_gain   ALM peak V   response      note
    #      23817        +45.0      +0.105       clamped: any two stimuli look identical
    #        300        +45.0      +0.054       clamped
    #        150        +29.3      +0.037       off the clamp
    #         75         -7.6      +0.020       <- adopted
    #         40        -23.1      +0.010
    #
    # 75 gives a receptor potential of about 39 mV for a strong tap, which is still larger
    # than the 10-20 mV whole-cell recordings show, and leaves headroom for a harder
    # stimulus -- a dish wall pushes far harder than an eyebrow hair -- before anything
    # clamps. The mechanoreceptor current is the better constrained quantity and it lands
    # in the tens of pA that O'Hagan, Chalfie & Goodman (2005) measured.
    # The omega turn, or the beginning of one.
    #
    # A reversal in this animal reorients it by 23 degrees; a real one ends in an omega
    # turn of 160-170 about a third of the time, and without that a biased random walk has
    # nothing to bias -- which is why three assays here report a correct mechanism and a
    # null outcome (see the README).
    #
    # The substrate is present and already engaged. RIV innervates ventral body muscle and
    # nothing else -- 9 contacts ventral, 0 dorsal, which is exactly the anatomy of a cell
    # whose job is to bend the animal one way -- and it is measurably more active during
    # reversals than during forward runs, 0.594 against 0.524, reached through RIA and SMDV
    # rather than from the command pool directly. What it lacks is authority: those 9
    # contacts are 1.8% of the ventral innervation, and the per-cell muscle balance then
    # puts RIV on equal footing with every other input.
    #
    # omega_gain scales RIV's neuromuscular output alone, acting on its deviation from its
    # resting release rather than on its conductance, so that the muscle balance is left
    # undisturbed and only the phasic part is amplified (see Muscles.phasic_gain).
    #
    # It stays at 1.0, which is exactly the unmodified model, because the experiment was
    # run and RIV is the wrong cell for this. Over a 180 s run, 0.5% of RIV's release
    # variance is explained by the direction state and 99.5% is the undulation it rides
    # on -- so any gain amplifies the gait two hundred times harder than the turn signal,
    # and the measurement says exactly that: at gain 12 the median reorientation reaches
    # 55 degrees and never once exceeds 120, while net speed falls 0.301 -> 0.058 mm/s and
    # the travelling-wave index +0.84 -> +0.74. Scaling the conductance instead fails in
    # both available positions, for two different reasons. tools/omega.py has the table.
    #
    # The knob is kept rather than deleted because the deviation-gain machinery is the
    # right way to amplify any phasic drive without disturbing the resting balance, and
    # whatever eventually drives the omega turn will want it. That driver has to be
    # something whose variance *is* reversal-locked; in the animal the turn fires at the
    # reversal-to-forward transition rather than during the reversal.
    omega_gain: float = 1.0

    # The omega turn proper: a transient locked to the reversal-to-forward *edge*.
    #
    # The RIV result above says what the driver cannot be -- anything whose output is
    # dominated by the undulation, because a gain on that amplifies the gait rather than
    # the turn. It also says what it must be: something whose variance is reversal-locked.
    # In the animal the omega turn is not part of the reversal, it *follows* it. Gray, Hill
    # & Bargmann (2005) score the pirouette as a reversal followed by a deep ventral turn,
    # and the turn fires as forward locomotion resumes.
    #
    # So the signal is an edge, not a level. On the backward-to-forward transition a
    # transient is injected into the ventral head and neck motor pool and decays over
    # omega_tau; the animal resumes forward locomotion with a held ventral bias, and the
    # undulation carries that bias down the body as a turn instead of a straight run.
    #
    # Two things follow from this shape rather than being fitted into it, and both are
    # properties the animal has:
    #
    #   * the turn follows the reversal rather than accompanying it;
    #   * longer reversals produce deeper turns, because the amplitude is set by the
    #     reversal's own duration against omega_ref_reversal.
    #
    # The drive is a *differential*: the ventral head pool is depolarised and its dorsal
    # partners are hyperpolarised by the same amount. Driving ventral alone does almost
    # nothing, and the measurement is stark. Held on continuously, mean head curvature is
    #
    #     RIV + SMDV, ventral drive only          -0.39 /mm at 100 pA, -0.61 at 200
    #     all 8 ventral cells, drive only         -0.31            "   -0.29     "
    #     8 ventral driven, 6 dorsal inhibited    -3.07            "   -6.37     "
    #
    # against an undulation of 4.5 rms and the ~9 an omega turn needs. Ventral excitation
    # alone saturates the cells long before it bends the animal -- 400 pA pins RIV and SMDV
    # at an activation of 0.9999 and still only reaches -0.56 -- because their 19 ventral
    # contacts are diluted by the per-cell muscle balance. Releasing the dorsal antagonist
    # is worth an order of magnitude more than pushing the ventral one harder.
    #
    # That is the same lesson this file has now learned three times: the ASE pair cancelled
    # itself until the two cells pushed AIY in opposite directions, the command pools move
    # together so only their difference steers, and the head is a set of antagonistic pairs
    # (SMDD/SMDV, RMDD/RMDV, SMBD/SMBV) that reads a difference. A turn is a differential,
    # not a push. It is also what the animal does -- the dorsal head muscles relax as the
    # ventral ones contract -- and the reciprocal inhibition it stands in for is present in
    # the connectome between RMDD and RMDV, at a strength this model does not resolve.
    #
    # The pools are every cell in the reconstruction whose neuromuscular output is
    # unambiguously one-sided, covering s = 0.08-0.35: the neck.
    #
    # The three constants were fitted together over current x duration, and the result is
    # the strongest behavioural change in this model's history:
    #
    #     pA   tau | reorientation deg (median / >120%) | net   path   TWI   k_rms
    #      0   1.5 |      25.3  /   0%                  | 0.273 0.373  +0.88  4.55
    #    200   2.0 |      93.3  /  21%                  | 0.135 0.351  +0.88  4.50
    #    300   1.5 |     106.1  /  32%                  | 0.102 0.351  +0.86  4.60
    #    450   2.0 |     101.3  /  33%                  | 0.168 0.299  +0.74  4.98
    #
    # Read the two speed columns together. *Path* speed barely moves -- 0.373 to 0.351, six
    # per cent -- while *net* speed halves. That is not the animal slowing down, it is the
    # animal's track becoming tortuous, which is what turning means and is the whole point.
    # The travelling-wave index and the curvature are untouched at 300 pA, so the gait
    # itself is intact; by 450 the wave starts to suffer (+0.74) and that is the ceiling.
    #
    # omega_ref_reversal is 0.4 s because the model's own reversals have a median duration
    # of 0.41 s. Setting it there means a typical reversal earns roughly full amplitude and
    # a short one earns less, which is what produces the *distribution*: 32% of reversals
    # exceed 120 degrees against roughly 35% of a real animal's ending in an omega turn.
    # That fraction was never fitted -- it falls out of the duration scaling.
    #
    # A transient can also use amplitudes a sustained drive cannot. Held on continuously,
    # 150 pA and above freezes the animal in a bent posture: the travelling index goes to
    # +0.19 and path speed to 0.03 mm/s, because saturating one side of the head motor pool
    # stops it oscillating. The transient decays back through that region instead of
    # sitting in it, which is why 300 pA is usable here and would not be as a level.
    #
    # omega_current is fitted, and openly, and it is the largest injected current in this
    # model -- an order of magnitude above cord_drive. Nothing measures what the turn
    # circuit delivers. What is *not* fitted is the mechanism, which is why this is worth
    # more than the gain it replaces. 0.0 disables it and reproduces the previous model.
    omega_current: float = 300.0     # pA, ventral pool up and dorsal pool down by this
    omega_tau: float = 1.5           # s   how long the bend is held after the edge
    omega_ref_reversal: float = 0.4  # s   reversal length earning a full-amplitude turn
    omega_ventral: tuple = ("RIVL", "RIVR", "SMDVL", "SMDVR",
                            "RMDVL", "RMDVR", "SMBVL", "SMBVR")
    omega_dorsal: tuple = ("SMDDL", "SMDDR", "RMDDL", "RMDDR", "SMBDL", "SMBDR")

    # How often the turn goes ventral rather than dorsal.
    #
    # The animal's omega turns are ventrally *biased*, not exclusively ventral, and the
    # difference is not cosmetic. Shipped exclusively ventral, every turn bent the same
    # way, so the heading changes accumulated instead of cancelling and the animal flew in
    # circles. Measured on a lawn, where the reversal rate is highest: a net rotation of
    # +17.4 deg/s -- a full circle every twenty seconds -- and net-to-path of 0.18. With
    # the turn switched off entirely the same animal drifts -0.02 deg/s and reaches 0.83.
    #
    # It was invisible off food, where reversals are half as frequent and the drift is
    # small enough to read as noise. It only showed up when the on-food behaviour was
    # examined, and it had been mistaken for a reversal-rate problem: killing reversals
    # outright did *not* fix the net-to-path, which is what pointed here instead.
    #
    # Swept, and the drift scales straight with the bias:
    #
    #   ventral | off-food |rotation| | on-food |rotation| | on-food net/path
    #     0.50  |       1.8 deg/s     |       5.8 deg/s    |      0.277
    #     0.65  |       2.6           |       8.4          |      0.183
    #     0.80  |       4.6           |      13.5          |      0.142
    #     1.00  |       5.8           |      17.0          |      0.084
    #
    # The honest reading is that the bias is not what is wrong -- *the turns are too
    # shallow for it*. A real omega turn is 160-170 degrees, and at that depth it barely
    # matters which way the animal bends: it ends up reversed either way. Ours are 50-100
    # degrees, where a ventral turn and a dorsal turn differ by a hundred degrees, so a
    # bias the animal carries harmlessly becomes a spiral here.
    #
    # So this sits at 0.5 -- no bias -- and it is a stand-in, not a claim about the
    # animal. When the turns reach the animal's depth this is the parameter to put back.
    omega_ventral_fraction: float = 0.5

    # How much of the head proprioceptive reflex to switch off while the turn is running.
    #
    # The turn saturates. Held on, 150 pA and above freezes the animal in a bent posture
    # -- travelling index +0.19, path speed 0.03 mm/s -- and even the decaying transient
    # tops out near 22 deg/s, where 180 degrees in the two seconds a real omega takes
    # would need about 90. Pushing harder does not help, which is the signature of
    # fighting something rather than being short of drive.
    #
    # What it is fighting is the head reflex. head_proprio_gain is 150, and that reflex is
    # a high-gain regulator *on head curvature*: the exact quantity the turn is trying to
    # displace. Every pA of turn drive is opposed by a controller whose job is to give the
    # head back its sweep, so the two fight until the oscillator stalls -- which is why the
    # cost shows up as a collapsed travelling index rather than as a shallower bend.
    #
    # Gating the reflex down while the transient runs is the standard motif for this in
    # motor control: a descending command suppresses the local reflex it would otherwise
    # have to overpower. It also predicts something specific and falsifiable -- turn depth
    # should rise *without* the travelling index collapsing, because the turn stops
    # fighting rather than pushing harder.
    #
    # Scaled by the live turn amplitude, so it is exactly zero between turns and the gait
    # is untouched.
    #
    # It was tried, and it does nothing. Over 60-69 turns per condition:
    #
    #   suppression |  median turn deg      | %>120         | TWI
    #      0.00     |  67.2 [48.5, 89.8]    | 13% [6, 22]   | +0.88
    #      0.40     |  54.9 [39.3, 93.0]    | 12% [4, 19]   | +0.78
    #      0.70     |  65.3 [48.2, 93.2]    | 13% [5, 23]   | +0.86
    #      1.00     |  42.5 [28.0, 72.1]    |  3% [0, 8]    | +0.82
    #
    # Every interval overlaps every other. Worth recording how close this came to being
    # believed: a first look at four seeds showed the median going 59 -> 89 degrees at
    # half suppression, which reads as a clear win, and it was tools/stats.py -- on its
    # first real use -- that turned it back into noise.
    #
    # Left in at 0.0 rather than deleted, because the refutation is the useful part and a
    # future attempt should not have to rediscover it.
    omega_reflex_suppression: float = 0.0

    # WHAT ACTUALLY LIMITS THE TURN, as far as this has been measured.
    #
    # Turn rate is path speed times path curvature, and path speed is pinned near 0.35
    # mm/s by the mechanics. A 180 degree turn in the two seconds a real omega takes needs
    # a turn radius of 0.22 mm -- a one-millimetre animal curled into a circle a fifth of
    # its own length. That is a whole-body coil, not a neck bend.
    #
    # Driving the body's own B-class motor neurons to make one does not work either.
    # Held on, with the head pools:
    #
    #   pool               pA  | turn deg/s | path mm/s |  TWI
    #   head + neck        60  |   19.7     |   0.346   | +0.91
    #   head + neck       120  |    1.8     |   0.060   | +0.58
    #   + body B-class     60  |   20.6     |   0.100   | +0.52
    #   + body B-class    120  |    9.4     |   0.014   | +0.43
    #
    # Both candidates fail the same way, and it is not opposition and not lack of drive:
    # **it is dynamic range**. A sustained bend has to be carried by the same motor neurons
    # that are already spending their range on the travelling wave, so a DC offset through
    # them collapses the wave -- and without the wave there is no forward motion, and turn
    # rate is speed times curvature. Head-only saturates near 20 deg/s; whole-body trades
    # the propulsion away to buy nothing.
    #
    # So the next attempt should not be another target set or another gain. It needs the
    # bend to cost the wave less: more headroom in the motor units, or the static component
    # applied where it does not compete with the oscillation for the same range.
    #
    # omega_wave_suppression tests the first of those routes. A real deep omega is not a
    # bend superimposed on an otherwise normal gait: anterior undulation stands down for
    # the turn. While the transient is live, this attenuates the head oscillator and the
    # anterior B/A proprioceptive propagators whose receptive fields overlap the turn
    # pool. It does not change omega_current, the tonic cord drive, or posterior
    # propagation. Scaled by live turn amplitude, it is exactly inert between turns.
    #
    # Tested at 1.0 with six paired animals per condition, 200 s each (2026-07-30).
    # It makes the turn shallower, not deeper. Off food the median reorientation fell
    # 37.75 -> 15.62 deg (paired difference -22.1, 95% CI -34.4 to -12.4); on food it
    # fell 42.63 -> 29.05 deg (-13.6, CI -22.3 to -9.6). The fraction over 120 deg
    # fell to zero in both conditions. Net/path, absolute heading drift, and path speed
    # did not move detectably. The travelling wave is helping carry the turn down the
    # body rather than consuming headroom the static bend could use, so leave this off.
    omega_wave_suppression: float = 0.0

    touch_gain: float = 75.0         # pA per uN of smoothed indentation force
    touch_tau: float = 0.35          # s   mechanoreceptor adaptation

    # Habituation, and the only thing in this model that remembers anything.
    #
    # Rankin, Beck & Chiba (1990) tap a plate every ten seconds; the reversal response
    # falls away over about thirty taps, recovers over minutes of rest, and habituates
    # more deeply at shorter intervals. All three come out of one depleting-resource
    # equation rather than being fitted separately, which is the reason to prefer it to a
    # decay bolted onto the response:
    #
    #     dA/dt = (1 - A) / tau  -  use * stimulus * A
    #
    # with the touch drive scaled by A. Repeated stimulation depletes it, rest refills it
    # with tau, and a short interval habituates more deeply because less refilling happens
    # in between. Integrated exactly, so the amount of learning does not depend on dt.
    #
    # This sits in the receptor rather than at the synapse, and that placement is a
    # measured result rather than a preference. Rose and Rankin place the change
    # presynaptically, as reduced glutamate release onto the interneurons, so that is what
    # was built first (NeuralParams.depression_use, still present and still zero). It does
    # nothing here, and the reason is this connectome: cutting ALM and AVM's entire
    # chemical output leaves the AVA response to a tap unchanged at +0.18, while cutting
    # their gap junctions halves it. The tap response in this model is carried
    # electrically, and no amount of presynaptic depression can habituate an ohmic
    # junction. Receptor fatigue is the locus that works here, and it is defensible on its
    # own -- mechanoreceptors adapt -- but it is the second choice and it is recorded as
    # such.
    touch_habituation_use: float = 0.0    # 1/s per unit stimulus
    touch_habituation_tau: float = 60.0   # s   recovery from habituation
    food_gain: float = 11.0          # pA  dopaminergic mechanosensation of the bacterial lawn
    proprio_gain: float = 30.0       # pA per unit normalised curvature
    # THE CLAMP EXPERIMENT (H2 in the research log's reflex-gain hypotheses). Real
    # stretch receptors are ion channels: opening one moves the cell towards a reversal
    # potential and never past it, where injected current drives motor neurons onto the
    # v_clamp rail at the extremes of every cycle (the saturation v_clamp's own comment
    # accepts). With proprio_conductance > 0 the body A/B proprioceptive drive becomes a
    # pair of saturating conductances REPLACING the current injection for those pools:
    # the preferred bend opens g = tanh(relu(drive)) * this towards proprio_E_rev, the
    # anti-preferred bend opens the mirror conductance towards E_inh -- reciprocal
    # inhibition through channels. The first cut rectified away the inhibitory half and
    # the sweep said what that costs (dv_corr -0.73 -> -0.06, a third of the speed):
    # the signed current's hyperpolarising half was real push-pull, so the channel
    # translation keeps it, self-limiting at BOTH reversals. The drive no longer needs
    # to be tuned to avoid pinning. 0 = off, the shipped current path untouched. The
    # head reflex keeps its own current path either way -- it is a different map,
    # calibrated separately, and one experiment changes one thing.
    proprio_conductance: float = 0.0  # nS per unit saturated drive; 0 = current mode
    proprio_E_rev: float = 0.0        # mV  stretch-receptor reversal (non-selective cation)
    # Wen et al. (2012) Neuron 76:750 showed by localised body restraint that B-type motor
    # neurons transduce the curvature of the region *anterior* to them, over roughly
    # 200 um -- a fifth of the body. Boyle et al.'s 2012 model, which predates that result,
    # integrates posteriorly over half the body instead; we follow the experiment.
    # 0.30, raised from 0.20, and this is the one knob that turned out to do what the
    # notes always assumed it did. Measured (tools/wave_speed.py, three seeds):
    #
    #   reach |  freq Hz   wavelength L   TWI     k_rms   net mm/s
    #    0.08 |   1.167       0.49      +0.489    2.27     0.108
    #    0.12 |   1.167       0.48      +0.588    2.26     0.125
    #    0.16 |   1.167       0.50      +0.735    2.38     0.159
    #    0.20 |   1.178       0.55      +0.796    2.45     0.210
    #    0.30 |   1.178       0.64      +0.746    2.40     0.218
    #
    # Two things in that table, and the second is the more important one.
    #
    # Reach sets the wavelength -- 0.64 L against the animal's 0.65, where 0.20 gave 0.55
    # -- and costs nothing to do it: net speed goes 0.210 to 0.218 against a measured
    # 0.219, and the travelling index only slips from +0.80 to +0.75.
    #
    # And **reach does nothing whatever to the frequency**, which is flat at 1.167-1.178 Hz
    # across a 3.75-fold range. Wavelength and frequency are not two views of one quantity
    # in this model; they are independent, the wavelength is now right, and the frequency
    # is set entirely by the head loop. Everything in the day-two notes that treats them as
    # a single problem is wrong on this evidence.
    # Re-fitted to 0.16 once head_delay went in, because the delay raises the wavelength
    # and reach is what trades against it. At delay 0.60 the pair runs:
    #
    #   reach |  wavelength L    TWI    k_rms   net mm/s
    #    0.13 |     0.66       +0.575   4.40     0.131
    #    0.16 |     0.75       +0.655   4.44     0.186   <- adopted
    #    0.22 |     0.81       +0.684   4.44     0.213
    #    0.30 |     0.87       +0.736   4.34     0.185
    #
    # A clean trade: shorter reach buys wavelength and costs speed. 0.13 lands the
    # wavelength exactly on the animal's 0.65 and gives up 40% of the speed; 0.22 nearly
    # lands the speed and misses the wavelength by a quarter. 0.16 is the middle, and puts
    # all four gait numbers within 15% of the animal at once, which no configuration in
    # this project has managed before.
    proprio_reach: float = 0.16      # fraction of body length sampled anteriorly

    # The reach the animal falls back to on food, for the basal slowing response.
    #
    # This model's undulation frequency does not move. Measured across every neural
    # parameter that could plausibly carry a slowing signal -- descending cord drive,
    # proprioceptive gain, head reflex gain, the motor neurons' own adaptation time
    # constant and both Morris-Lecar ratios -- it sits at 0.650 Hz in all of them, and
    # path speed varies by at most 13%. That is consistent with tools/thrust.py finding
    # the animal already at 100% of the mechanical ceiling for its own kinematics: speed
    # here is set by the body and the medium, not by how hard the circuit drives it.
    #
    # Since speed is frequency x wavelength x (U/V) and the frequency is pinned, the only
    # route left is a shorter wave -- which is exactly the trade proprio_reach already
    # controls (see the table above). Measured:
    #
    #   reach | wavelength   path mm/s   ratio    TWI    k_rms
    #    0.16 |    0.85        0.378     1.00   +0.89    4.68
    #    0.10 |    0.62        0.249     0.66   +0.77    3.89
    #
    # so a third of the animal's speed is available this way, at some cost to the
    # travelling index. 0.10 is the floor; how far towards it the animal actually goes is
    # set by ModulatorParams.dopamine_wavelength and by how much dopamine it has.
    proprio_reach_food: float = 0.10

    # --- the amine load-sensing path (Python-only research path, all defaults 0 = off) --
    #
    # Motivated by the 2026-08-13 measurement chain: gait modulation saturates because
    # below K ~ 8 the bending dynamics carry no information about the medium at all
    # (tools/loop_medium.py, tools/fv_phase.py) -- but the drag *force* on the cuticle
    # keeps scaling with the drag coefficients all the way down the continuum, because it
    # is c x v and c keeps falling. Slip is the signal that survives, and the animal's own
    # literature says it uses it through the amines: dopamine is necessary and sufficient
    # to initiate and hold crawling and serotonin to enter swimming (Vidal-Gadea et al.
    # 2011, PNAS 108:17504, doi 10.1073/pnas.1108673108), and mechanical load modulates
    # the swimming gait through mechanosensation (Korta et al. 2007, J Exp Biol, PMID
    # 17575043). The cells that carry the dopamine signal here -- CEP/ADE/PDE -- are the
    # same mechanoreceptors this model already gives the lawn-texture modality.
    #
    # `load_gain` is pA of drive into the dopaminergic mechanoreceptors per unit of
    # saturated load signal. The signal is the body-mean drag force per unit length
    # (Body.drag_load, uN/mm), compressed through F / (F + load_half) because real
    # mechanoreceptors saturate and the raw quantity spans four decades between agar and
    # buffer. Both numbers are TUNED; the cell identity and the sign are the reconstructed
    # part, exactly as for every other channel in this class.
    #
    # KNOWN CONFOUND, stated before anyone trips on it: dopamine here also carries the
    # lawn-texture signal for the basal slowing response, so with `load_gain` on, bare
    # agar already drives dopamine toward saturation and food adds almost nothing on top.
    # The two modalities share cells in the animal too, but the basal-slowing calibration
    # in ModulatorParams assumed food was the only source. Resolving that -- separate
    # transduction, recalibration, or the measurement that says it does not matter -- is
    # required before any of these five constants moves off zero by default.
    load_gain: float = 0.0           # pA per unit saturated load
    load_half: float = 1.0           # uN/mm half-saturation of the transduction

    # The reach the receptive fields blend toward as dopamine falls -- the swim-end
    # counterpart of proprio_reach_food, built as a third precomputed matrix pair and
    # blended by ModulatorParams.dopamine_reach_swim. Zero disables construction
    # entirely. The animal's swimming wavelength is 1.54 L against this model's 0.86 at
    # reach 0.16 (Fang-Yen et al. 2010); what reach reaches it in the cascade
    # configuration is unmeasured, so this is a search knob, not a claim.
    proprio_reach_swim: float = 0.0  # fraction of body length; 0 = off

    # Stretch receptors adapt, like every other mechanoreceptor -- and unlike the version
    # of this model that shipped first, where proprioception was the one sensory channel
    # left responding to absolute value rather than to change.
    #
    # It matters more than it sounds. A worm holding any static bend puts a large constant
    # offset on the receptor, six to eleven times the size of the oscillation riding on it,
    # which both buries the signal and pushes the receptor's saturation far enough up its
    # curve that only about half the remaining gain is available to the oscillation. It is
    # also why the gain could never be raised: turning it up drove the animal into a
    # permanent curl instead of a bigger undulation, because the static component was being
    # amplified along with the dynamic one. High-passing the signal removes the curl as a
    # failure mode and lets the gain go where it needs to.
    proprio_tau_adapt: float = 2.5   # s   set well above the undulation period

    # The head is where the rhythm comes from. Proprioception alone cannot generate an
    # undulation -- it is a transport rule, it copies a bend backwards but never starts
    # one -- so something has to oscillate. In the animal that something is the head:
    # Wen et al. (2012) showed the body wave is initiated at the neck and propagated
    # posteriorly by proprioceptive coupling, and the head motor neurons SMD and RMD are
    # themselves proprioceptive (Yeon et al. 2018, PLoS Biol 16:e2004929).
    #
    # Here the head reflex is *negative*: a dorsal head bend excites the ventral head
    # motor neurons and inhibits the dorsal ones. Negative feedback through the ~100 ms
    # muscle delay is an oscillator. The body reflex, by contrast, is positive -- it
    # copies the anterior bend rearwards -- which is what makes the wave travel instead
    # of standing.
    head_proprio_gain: float = 150.0  # pA per unit normalised curvature
    head_reach: float = 0.17          # fraction of body length the lumped circuit reads

    # The head reflex, distributed over its own neurons instead of lumped into one scalar.
    #
    # The lumped version gives every head motor neuron the same number -- the mean
    # curvature of the front 17% of the body -- so twelve cells that act on different
    # pieces of body all see the same thing and fire together. That is the reason it needed
    # `head_delay`: with no spatial spread there is no phase spread, and the loop's
    # crossover had to be dragged down by an invented 0.6 s transport delay instead.
    #
    # Weighted by their own neuromuscular maps, RMD, SMD and SMB act between s = 0.135 and
    # s = 0.229. That tenth of a body length takes the travelling wave a real fraction of a
    # cycle to cross, so letting each cell read the curvature around the piece it moves
    # supplies phase from the anatomy rather than from a fitted constant -- and it should
    # follow the mechanical load, which a fixed delay provably cannot (see head_delay).
    #
    # head_field is the width of each cell's window, centred on where it acts.
    # Measured against the lumped reflex it replaces (tools/head_circuit.py, three seeds).
    # The delay sets the frequency in both forms; what distributing buys is the wave:
    #
    #   reflex       field gain delay | freq Hz wavelen  TWI    k_rms  net mm/s
    #   lumped       0.10  150  0.60  |  0.450   0.72   +0.583   4.32   0.1239
    #   distributed  0.10  150  0.15  |  0.833   0.61   +0.391   2.98   0.2066
    #   distributed  0.10  150  0.20  |  0.750   0.59   +0.681   3.43   0.1755
    #   distributed  0.08  150  0.28  |  0.650   0.61   +0.684   3.78   0.1363   <- adopted
    #
    # The travelling index is the thing to read: it is the fraction of the mechanical
    # thrust ceiling the animal actually collects (tools/thrust.py), so +0.68 against
    # +0.58 is 17% more speed for the same body. And it comes with **less than half the
    # invented delay** -- 0.28 s against 0.60 -- because a reflex whose cells read
    # different pieces of body needs less help to find its phase.
    #
    # 0.65 Hz is also the frequency a self-consistent animal has. The 0.30 Hz this project
    # used to target cannot coexist with the 0.219 mm/s it also targets: they need
    # U/V = 1.12, above the physical bound of 1. At the animal's own curvature the
    # mechanics cap U/V near 0.51, so 0.219 mm/s implies 0.66 Hz. See tools/thrust.py.
    head_distributed: bool = True
    head_field: float = 0.08

    # The head reflex loop has two stable limit cycles: a slow one near 0.3 Hz, which is
    # the crawling gait, and a fast one near 2.2 Hz set by the loop's own phase-crossover
    # frequency. Without this filter the fast mode wins from most initial conditions, and
    # the animal buzzes on agar at roughly its swimming frequency.
    #
    # Mechanoreceptor currents have their own kinetics -- they are not instantaneous
    # functions of strain -- and a first-order lag here cuts the loop gain at 2 Hz by
    # several fold while leaving 0.3 Hz almost untouched, which removes the fast attractor
    # and leaves the slow one.
    head_tau: float = 0.22            # s   stretch-receptor adaptation of the head reflex

    # How many first-order stages that lag is split into, in *series*.
    #
    # 1 is exactly the filter above and is the shipped behaviour; this parameter is inert
    # at its default and exists to be swept. What it is for needs the negative result in
    # tools/head_circuit.py stated first, because it is the reason the obvious version of
    # this idea does not work:
    #
    #   "a spread of delays low-passes the loop rather than adding phase to it, and this
    #    crossover is phase-limited, so the anatomical spread cannot substitute for the
    #    invented one."
    #
    # That was measured on the *spatial* spread -- letting each head cell read its own
    # patch of body. Cells in parallel, each with the same first-order filter, still only
    # ever supply one lag's worth of phase, because parallel paths average rather than
    # compose. Distributing bought a better wave (+0.68 TWI against +0.58) and cut the
    # delay from 0.60 s to 0.28, but it did not remove it, and this is why.
    #
    # Stages in series are the other thing, and the arithmetic is the whole argument. One
    # lag contributes at most 90 degrees of phase however hard it is driven, so a loop
    # needing 180 cannot get there from one filter and a pure delay had to supply the rest.
    # N stages of `head_tau / N` each contribute arctan(w*tau/N), so together they give
    # N*arctan(w*tau/N) -- which is about w*tau at low frequency, identical to the single
    # lag, and rises to N*90 degrees instead of 90. As N grows that expression converges on
    # exp(-i*w*tau), a pure transport delay of `head_tau`. So a cascade is not an
    # approximation *of* something else here: it is what a transport delay is made of when
    # you build it out of cells instead of out of a ring buffer.
    #
    # Which is what `head_delay`'s own note asks for -- "a distributed multi-stage circuit
    # accumulates phase that a single first-order lag cannot. Replacing this number with
    # that circuit is the way to earn it back." RMD, SMD and SMB are three cell classes
    # with their own kinetics, and three stages is what three classes in series look like.
    #
    # Two things ride on it beyond honesty about the constant. A cascade's phase is
    # frequency-dependent through arctan rather than the pure delay's exactly-linear
    # 2*pi*f*tau, so its crossover moves with loop gain, and loop gain moves with
    # mechanical load -- which is the mechanism gait modulation needs and a fixed delay
    # cannot offer. And `headHist` is 210,936 B, 89% of an animal (node wasm/memory.mjs);
    # a cascade is `head_stages` scalars per joint instead of a 560-sample ring, so a
    # configuration that reaches the right frequency with `head_delay = 0` makes a
    # population an order of magnitude cheaper.
    #
    # Not adopted, and deliberately not ported to the runtime: at 1 this changes nothing,
    # which is the state a thing should be measured in before it is believed. Same order
    # self-avoidance was built in (#86).
    #
    # MEASURED, and the answer is half yes and decisively not enough. tools/head_cascade.py,
    # three seeds, 30 s, no delay at all except in the shipped row:
    #
    #   stages delay | freq Hz  wavelen   TWI    k_rms  net mm/s
    #     1    0.00  |  1.300    0.48   +0.754   2.22    0.190
    #     2    0.00  |  1.100    0.53   +0.804   2.78    0.258
    #     3    0.00  |  1.067    0.54   +0.811   2.95    0.278
    #     4    0.00  |  1.033    0.55   +0.815   3.00    0.292
    #     6    0.00  |  1.033    0.55   +0.820   3.05    0.291
    #     1    0.28  |  0.656    0.83   +0.846   4.45    0.295   <- shipped
    #
    # The mechanism is real: unlike the spatial spread, which did nothing to the frequency
    # at all, stages in series do lower it -- and they *improve* the wave while doing so,
    # TWI +0.754 to +0.820 and net speed 0.190 to 0.291, which is the opposite of the trade
    # the delay made. But it plateaus at 1.03 Hz and never approaches the shipped 0.656.
    #
    # One caveat on reading that plateau: a 30 s window gives 1/30 Hz of frequency
    # resolution, and 1.033, 1.067 and 1.100 are 31, 32 and 33 bins. So 3, 4 and 6 stages
    # differ by a single bin and are **not resolved** by this run. What is resolved is 1 to 2
    # stages (6 bins) and the gap from the plateau to the shipped row (11 bins).
    #
    # The ceiling is arithmetic and was there to be predicted. N stages of `head_tau / N`
    # converge on a pure delay of `head_tau` -- that is the whole point of the construction --
    # so the most phase they can ever supply is the phase of a 0.22 s delay. At 0.656 Hz:
    #
    #   N = 1   42.20 deg      N = 4   51.09 deg
    #   N = 2   48.78 deg      N = 6   51.56 deg
    #   N -> inf   51.96 deg   (a pure delay of head_tau = 0.22 s)
    #
    # So the entire cascade is worth 9.8 degrees more than the single lag it replaces, while
    # the shipped configuration carries `head_delay = 0.28 s` on *top* of head_tau, which is
    # another 66.12 degrees. The cascade is short by that, permanently, at any stage count.
    # It was never subdividing the right budget: it redistributes head_tau's existing lag
    # into more phase, and cannot manufacture lag the model did not already have.
    #
    # Which makes the next experiment obvious and cheap: give the cascade its own total lag
    # rather than subdividing head_tau. See `head_stage_tau`.
    head_stages: int = 1              #     first-order stages in series, 1 = shipped

    # Per-stage time constant, when the cascade should not simply subdivide `head_tau`.
    #
    # Zero means `head_tau / head_stages`, which is the construction measured above and the
    # one whose ceiling is a pure delay of head_tau. Any positive value is used directly, so
    # N stages carry N * head_stage_tau of total lag and the cascade converges on a pure
    # delay of *that* instead.
    #
    # The prediction this exists to test: the shipped loop's phase comes from head_tau plus
    # head_delay, 0.22 + 0.28 = 0.50 s, so a cascade carrying 0.50 s in total should reach
    # the shipped frequency with `head_delay = 0` and no ring buffer at all. At four stages
    # that is 0.125 s each. If it lands, `headHist` -- 210,936 B, 89% of an animal -- goes
    # away, and the phase becomes frequency-dependent through arctan rather than exactly
    # linear, which is the property gait modulation needs and a fixed delay cannot offer.
    #
    # IT LANDED. tools/head_cascade.py phase two, three seeds, 30 s:
    #
    #   stages delay stage_tau | freq Hz        wavelen   TWI    k_rms  net mm/s  n/p
    #     1     0.28    --     | 0.656 +-0.031    0.83   +0.846   4.45   0.2949   0.80  <- shipped
    #     4     0.00   0.1250  | 0.644 +-0.016    0.86   +0.880   4.58   0.3688   0.94
    #     6     0.00   0.0833  | 0.611 +-0.016    0.84   +0.799   4.52   0.2718   0.75
    #
    # Four stages of 0.125 s, with **no transport delay at all**, match the shipped
    # frequency to well inside the seed scatter and are better on everything else that was
    # measured: travelling index +0.880 against +0.846, net speed 0.369 against 0.295, and
    # net-to-path 0.94 against 0.80. The delay bought its frequency by giving away the wave;
    # this does not.
    #
    # Six stages at the same total lag is *worse* -- 0.611 Hz, TWI +0.799 -- and that is the
    # result worth thinking about rather than the headline. More stages is nearer a pure
    # delay, and nearer a pure delay is nearer what the shipped model already had. The
    # cascade is not better because it approximates the delay well; it is better because at
    # four stages it approximates it *badly*, in the specific way that makes the loop's phase
    # depend on frequency. That is the same property the note above wants for gait
    # modulation, and it is now measured rather than argued.
    #
    # THE MEDIUM SWEEP RAN, AND THE ARGUMENT FOR THE CASCADE DID NOT SURVIVE IT.
    #
    # The reason to want a cascade was never the frequency on agar. It was the shape of the
    # phase: a pure delay contributes 2*pi*f*tau, exactly linear, so it pins the loop's
    # crossover wherever it was fitted whatever the medium does to the load; a cascade
    # contributes N*arctan(w*tau/N), which saturates, so its phase should depend on where
    # the loop is running. That was supposed to be the mechanism gait modulation needs.
    # tools/head_medium.py tested it, three media, three seeds, both arms paired:
    #
    #   arm      medium   K     | freq Hz        wavelen   TWI    net mm/s
    #   shipped  agar    40.00  | 0.656 +-0.031    0.83   +0.846   0.2949
    #   shipped  viscous  9.00  | 0.844 +-0.016    0.87   +0.724   0.2330
    #   shipped  buffer   1.58  | 0.833 +-0.027    0.91   +0.657   0.0380
    #   cascade  agar    40.00  | 0.644 +-0.016    0.86   +0.880   0.3688
    #   cascade  viscous  9.00  | 0.833 +-0.000    0.90   +0.742   0.2386
    #   cascade  buffer   1.58  | 0.833 +-0.000    0.91   +0.761   0.0394
    #
    # Span across the continuum: shipped 1.27x, cascade 1.29x, against the animal's 5.87x.
    # A difference of 0.02x is nothing. **The frequency-dependent-phase argument is retired**
    # -- do not re-run it as a stage count or a lag budget, the two arms are the same shape
    # of animal in every medium and the difference between a saturating phase and a linear
    # one does not reach the gait.
    #
    # ADOPT IT ANYWAY, for the reasons that did survive. At matched frequency the cascade is
    # better or equal in every medium -- travelling index +0.880 against +0.846 on agar and
    # +0.761 against +0.657 in buffer, net speed 0.369 against 0.295, net-to-path 0.94
    # against 0.80 -- and it does that with `head_delay = 0`, which retires the largest
    # fitted number in the model and takes `headHist` with it: 210,936 B, 89% of an animal.
    # That is a good change. It is simply not the gait-modulation change.
    #
    # What still stands between it and adoption is the standing comparison for any change to
    # the shared gait: tools/scorecard.py and tools/ethogram.py against the frozen baseline
    # on identical seeds with the trajectory guards reported, then the port to the runtime.
    head_stage_tau: float = 0.0       # s   0 = head_tau / head_stages

    # A transport delay in the head reflex, and the reason it exists is numerical as much
    # as biological.
    #
    # The head loop oscillates because negative feedback with enough lag must, and its
    # frequency is therefore wherever the loop's phase happens to cross 180 degrees. Almost
    # all of that lag currently comes from continuous dynamics -- head_tau, the synapses,
    # the muscle cascade, the body -- and the fastest of those live at the edge of what the
    # timestep resolves: RMD, SMD and SMB have membrane time constants of 0.93 to 2.34 ms
    # against a 0.5 ms step. So the crossover frequency is partly a property of the
    # integrator, and it moves by 44 to 86% when the step is refined, in every one of the
    # nineteen configurations swept in tools/wave_speed.py.
    #
    # A pure delay is the one kind of lag that cannot be an artefact. It contributes phase
    # 2*pi*f*delay, exactly, at every frequency, and it is defined in seconds rather than
    # in steps -- so whatever crossover it sets is the same at any dt, and it dominates the
    # loop's phase at high frequency, which is where the fast mode lives.
    #
    # It is also real. The reflex here reads curvature and acts on it within one step;
    # mechanotransduction, graded transmission and the neuromuscular junction each take
    # milliseconds to tens of milliseconds, none of which this model represents anywhere.
    #
    # Zero by default until measured.
    # 0.28 s, and this is the largest fitted number in the model. It is what finally moved
    # the two headline discrepancies, and the honesty about where it comes from matters
    # more than the result. Measured at reach 0.16, three seeds:
    #
    #   delay s |  freq Hz   wavelength L    TWI    k_rms   net mm/s
    #     0.00  |   1.178       0.64       +0.746   2.40     0.218
    #     0.15  |   0.811       0.73       +0.707   3.29     0.180
    #     0.40  |   0.544       0.68       +0.700   4.12     0.166
    #     0.60  |   0.433       0.75       +0.655   4.44     0.186   <- adopted
    #     0.80  |   0.367       0.76       +0.653   4.63     0.149
    #
    # Against the animal: 0.30-0.50 Hz, 0.65 L, curvature rms 4.3 /mm, 0.219 mm/s. The
    # frequency was the largest single error in this project -- 1.18 Hz, near four times
    # the crawling gait -- and it is now 0.43. Curvature was 43% low at 2.40 and is now 3%
    # high at 4.44. Nothing else tried in eight days moved either without destroying the
    # wave, and every other route was tried: head_tau, head gain, body gain, reach, the
    # segmental oscillators, and head_tau paired with a compensating gain.
    #
    # **It is not a measured delay.** Mechanotransduction takes milliseconds, not six
    # hundred of them, and no single element of the real head circuit is this slow. What
    # the number actually says is arithmetic about the loop: an oscillation at 0.43 Hz
    # needs about 1.15 s of lag around the loop to reach its half-period, the modelled
    # components -- head_tau, the synapses, the muscle cascade, the body -- supply about
    # 0.42 s of it, and the remaining 0.7 s has to exist somewhere or the animal would
    # undulate at 1.18 Hz, which it does not. So this parameter is the size of what the
    # model is missing, stated plainly, rather than a claim about a receptor.
    #
    # The obvious candidate for what it stands in for is the head circuit itself. RMD,
    # SMD and SMB are lumped here into one reflex with one gain and one filter; the real
    # thing is several cell classes with their own dynamics, and RMD is frankly bistable
    # (Mellem et al. 2008). A distributed multi-stage circuit accumulates phase that a
    # single first-order lag cannot. Replacing this number with that circuit is the way to
    # earn it back.
    #
    # One argument that was made for this parameter has since been withdrawn, and it is
    # worth striking out rather than quietly deleting. It was claimed that the coarse
    # timestep supplied phase and damping for free and that the delay was replacing them.
    # That rested on convergence measurements taken while the body ran at its own timestep
    # (see BodyParams.dt), and they meant nothing. The value stands -- it was fitted at
    # dt = 0.5 ms, where the coupling was correct -- but it is now unsupported by anything
    # except that it lands the frequency, which makes it a fit and not an explanation.
    #
    # It was once argued here that a fixed delay must kill gait modulation outright, since
    # it contributes fixed phase at every frequency and so pins the loop's crossover
    # whatever the medium does to the load. The evidence for that was 0.45 Hz on agar
    # against 0.18 in buffer -- backwards, where the animal speeds up. **That argument was
    # wrong, or at least not the binding one.** With the reflex distributed and the command
    # layer re-fitted, the same delay now gives 0.67 Hz on agar and 0.85 in buffer: the
    # right direction, for the first time in this project. What had been killing modulation
    # was a reversal flicker in the command layer, not this parameter.
    #
    # The delay is still unearned and still the largest fitted number here. But the case
    # against it is now one count shorter, and honest bookkeeping says so.
    head_delay: float = 0.28          # s   transport delay in the head stretch reflex

    # -- the command layer ----------------------------------------------------------------
    # These three parameters used to be one, and separating them is what makes any
    # sensory-driven behaviour possible.
    #
    # A single 90 pA tonic current into AVB was doing two incompatible jobs. It decided
    # *which way the animal goes*, through a winner-take-all on absolute AVA/AVB activity;
    # and, once the B-type motor neurons became Morris-Lecar units held at a Hopf
    # bifurcation by AVB's gap junctions, it also decided *whether the animal can walk at
    # all*. Those two roles have opposite requirements. The decision wants AVB unsaturated
    # so that sensory input can move it; the gait wants AVB pinned high so the B cord stays
    # regenerative. Pinned won, and the measured consequence was that the gate read 98%
    # forward in every animal for an entire run, no reversal ever occurred, and chemotaxis
    # and aerotaxis were both flat. Turning the drive down to release the decision killed
    # the gait first: at 22 pA the gate had moved only 98% -> 90% while net-to-path
    # collapsed from 0.76 to 0.05.
    #
    # So the gait drive is now delivered directly to whichever motor cord is selected
    # (cord_drive), and the command interneurons are left to do nothing but choose. AVB
    # keeps a forward bias, because forward is the default state in a freely moving animal
    # and reversals are triggered events -- but it is a bias now, not a clamp.
    #
    # Calibrated together (tools/gate_calibrate.py, 3 seeds each). The old configuration
    # is the last row of the middle block -- same 90 pA, no cord drive -- and every number
    # below it is better:
    #
    #   tonic  cord_drive   gate (sd)      speed    net/path    TWI
    #     22        0      0.763 (0.218)   0.1142     0.559    +0.294   gate too loose
    #     22        8      0.961 (0.038)   0.2187     0.905    +0.778   <- adopted
    #     45        0      0.994 (0.006)   0.2651     0.934    +0.839   faster, gate stiff
    #     90        0      0.999 (0.001)   0.2356     0.854    +0.836
    #     90       20      0.999 (0.001)   0.1325     0.751    +0.611
    #
    # Two things fall out of that table. The difference-based gate is worth about 23% of
    # speed on its own, before any decoupling -- compare 90/0 at 0.2356 against the old
    # absolute-activity gate's 0.191 -- so the cubed winner-take-all was costing
    # locomotion as well as blocking behaviour. And 45/0 is faster still at 0.265, but its
    # gate barely moves (sd 0.006); it is a worm that crawls beautifully and cannot change
    # its mind. 22/8 is chosen for the standard deviation, not the mean: 0.038 is the
    # dynamic range every sensory behaviour has to act through, and the speed it comes with
    # (0.2187 mm/s) already matches the animal's 0.219.
    tonic_forward: float = 22.0      # pA  forward bias on the command interneurons
    tonic_backward: float = 0.0      # pA  matching bias on AVA, for experiments
    # Descending drive to the selected cord: what actually holds those motor neurons at
    # their bifurcation. Split between the two cords by the direction gate below, so the
    # cord that is not selected goes passive -- which is the "conditional" in conditional
    # oscillator, and is what stops the two cords fighting over the same muscles.
    cord_drive: float = 8.0          # pA
    # The direction gate reads the *difference* between the forward and backward command
    # pools rather than their absolute activities. A difference has dynamic range where a
    # saturated absolute value has none: AVB sat at 0.91 and AVA at 0.25 in every animal,
    # and cubing those gave 98/2 no matter what the senses did. gate_bias is the difference
    # at which the animal is evenly poised, and gate_slope how sharply it commits.
    gate_slope: float = 30.0         # per unit of activation difference
    gate_bias: float = 0.04          # activation difference at the switch point

    # Which cord, decided separately from how much drive it gets.
    #
    # The graded gate above does two jobs with one number, and that is the same conflation
    # day five only half removed. `tonic_forward` was split into a decision bias and a cord
    # drive, but the *fraction* still both chooses the direction and scales the descending
    # current: at fwd_frac 0.5 both cords are driven at half strength, both proprioceptive
    # fields are half engaged, and the two fight over the same muscles. So the decision
    # cannot move without moving the gait, which is why every attempt to give the command
    # layer dynamic range cost locomotion (see NeuralParams.command_ca_ratio), and why the
    # reversals that did occur lasted 0.07 s -- a level hovering at a threshold rather than
    # a state.
    #
    # Latched, the two jobs come apart. A Schmitt trigger picks a cord and commits: the
    # selected cord gets the *whole* drive, the other goes passive, and the difference has
    # to cross the far threshold to change anything. The difference is then free to wander
    # as widely as the circuit wants without touching the gait, and a reversal is something
    # the animal stays in until the command actually recovers -- which is what hysteresis
    # buys, and what the 0.07 s flicker was missing.
    #
    # gate_hysteresis is the half-width of the dead zone, in the same activation-difference
    # units as gate_bias.
    #
    # Measured (tools/command_sweep.py, three seeds, 60 s each). The first row is the
    # graded gate this replaces; note that latching *improves* locomotion before it does
    # anything else, because the two cords stop sharing the descending drive:
    #
    #   configuration        rev/min   dur s   %rev |  speed   net/path    TWI
    #   graded (shipped)       1.67    0.06     0.2 |  0.1853   0.783    +0.767
    #   latch b=0.12 h=0.02    0.33    0.34     0.2 |  0.2102   0.825    +0.785
    #   latch b=0.14 h=0.02    2.67    0.27     1.2 |  0.2058   0.814    +0.782
    #   latch b=0.15 h=0.02    7.33    0.37     4.2 |  0.1916   0.769    +0.768
    #   latch b=0.16 h=0.02   11.67    0.41     7.9 |  0.1911   0.793    +0.751
    #   latch b=0.16 h=0.04    2.67    0.44     1.8 |  0.2079   0.823    +0.781   <- adopted
    #   latch b=0.16 h=0.01   23.00    0.35    13.4 |  0.1712   0.743    +0.718
    #
    # The column that matters is **dur**. The graded gate's "reversals" lasted 0.06 s, one
    # fifteenth of an undulation cycle, which is a difference dipping below a threshold and
    # bouncing straight back rather than an animal reversing. Every latched row is five to
    # seven times longer, because that is what hysteresis is for: once committed, the
    # animal stays committed until the command actually recovers.
    #
    # 2.67 reversals per minute against the animal's 3.2-3.5 off food (Zhao et al. 2003).
    # Slightly low, and chosen over the rows nearer the target because those cost
    # locomotion, while this one leaves it better than the graded gate on every measure:
    # speed 0.208 against 0.185, net-to-path 0.823 against 0.783, travelling index +0.781
    # against +0.767.
    gate_latched: bool = True
    # Re-fitted after the head reflex was distributed, and the size of the change is the
    # point: the new head circuit more than doubled the spread of the command difference,
    # from about 0.04 to 0.0885, so the old threshold of 0.13 sat 0.29 sigma from the mean
    # instead of 1.33 and the animal flickered at 40 reversals a minute. Nothing about the
    # command layer was wrong; it was calibrated against a gait that no longer existed.
    #
    #   bias  hyst | rev/min  dur s |  speed   net/path    TWI    k_rms
    #   0.02  0.09 |   1.00    0.23 |  0.3325   0.847    +0.896   4.59
    #   0.04  0.09 |   3.33    0.35 |  0.3373   0.881    +0.872   4.56   <- adopted
    #   0.06  0.09 |   9.67    0.44 |  0.1907   0.536    +0.806   4.50
    #   0.08  0.06 |  24.67    0.38 |  0.1881   0.600    +0.781   4.18
    #   0.13  0.04 |  40.00    ----  |  0.1370   0.530    +0.680   3.76   the stale one
    #
    # 3.33 reversals a minute against the animal's 3.2-3.5 off food, and the travelling
    # index and net-to-path ratio come with it: an animal that is not constantly changing
    # its mind travels, and thrust is the travelling index (tools/thrust.py).
    gate_hysteresis: float = 0.09

    # How far a modulator is allowed to move the gate's 50/50 point, as a fraction of the
    # hysteresis. This is a bound, not a fitted number, and it exists because the model
    # spent a long time with the wrong on-food behaviour for want of it.
    #
    # ModulatorParams.turn_bias grows linearly with serotonin and had no ceiling. On a
    # dense lawn it reached +0.103, which is *larger than gate_hysteresis*, and at that
    # point the Schmitt trigger stops being a trigger. The forward-to-backward threshold
    # (bias - hysteresis) rose to +0.050 while the backward-to-forward threshold rose to
    # +0.230, so the whole latch window sat above the resting command difference: the
    # animal fell into reversal and could not climb back out. Measured, it spent 57% of
    # its time reversing on food at 10-16 commanded reversals a minute against the
    # animal's 0.7-1.25, with net-to-path 0.05 -- it thrashed in place.
    #
    # Keeping |turn_bias| below the hysteresis is exactly the condition for the window to
    # keep straddling the operating point, so a modulator can bias the decision without
    # swallowing it.
    #
    # How tight the bound should be is not free, and the sweep says something the model
    # had not shown before. One number is serving two masters:
    #
    #   limit | chemo CI | aerotaxis end | noci /min | on-food rev/min | on-food net/path
    #    0.05 |  -0.021  |  20.6%  wrong |   1.32    |      2.22       |     0.268
    #    0.30 |  +0.070  |  14.5%  right |   5.15    |      7.79       |     0.149
    #   1.0+  |  +0.070  |  14.2%  right |   5.46    |     10.21       |     0.052
    #
    # The reversals the taxis assays run on are the *same* reversals that make the on-food
    # ethogram look wrong. Tighten the bound and the animal stops thrashing on a lawn, but
    # chemotaxis inverts, aerotaxis climbs the gradient again and nociception nearly stops
    # -- because a biased random walk with no reversals has nothing to bias. There is no
    # setting of this one number that satisfies both, and 0.3 is the corner: every taxis
    # number identical to the unbounded model, and the latch bug gone.
    #
    # Deleting the turning term outright is worse still, and was measured: chemotaxis
    # +0.070 -> -0.015, the pirouette ratio inverting to 0.38, nociception 5.46 -> 0.14.
    #
    # What that leaves is a real open problem rather than a tuning one. On food the animal
    # still reverses 7.8 times a minute against 0.7-1.25, and fixing it needs food to
    # suppress reversals by a route that does not also suppress them off food -- a sensory
    # pathway, not a global shift of the decision boundary that every behaviour shares.
    turn_bias_limit: float = 0.3     # fraction of gate_hysteresis


@dataclass(frozen=True)
class ModulatorParams:
    """The monoamine and neuropeptide layer. See worm/modulators.py for the biology.

    Sources are matched by name prefix against the connectome. Time constants are the slow
    end of what these systems do -- seconds to tens of seconds -- because that is the whole
    point: they are the only thing in this model that integrates rather than differentiates.
    """

    dopamine_sources: tuple = ("CEP", "ADE", "PDE")
    dopamine_tau: float = 6.0        # s
    serotonin_sources: tuple = ("NSM", "ADF", "HSN")
    serotonin_tau: float = 10.0      # s
    octopamine_sources: tuple = ("RIC",)
    octopamine_tau: float = 20.0     # s
    pdf_sources: tuple = ("AVB", "PVT")
    pdf_tau: float = 25.0            # s

    # Coefficients. Every one is zero-safe: set them all to zero and the wired model
    # behaves exactly as it did before this layer existed, which is the control row of
    # tools/modulator_sweep.py and is how these were calibrated.
    #
    # The assay is the basal slowing response (Sawin, Ranganathan & Horvitz 2000): drop a
    # well-fed animal on a lawn and it halves its speed. Scored as speed-on-food over
    # speed-off-food, two seeds, 55 s each. Recalibrated after the food field was fixed --
    # the first attempt was fitted against lawns the animal ate away beneath itself in two
    # seconds, so the on-food dopamine signal it saw was four times too small.
    #
    #   da_slow  5ht_turn   off food   on food   ratio   gate sd off/on
    #     0.0      0.0       0.1989    0.1926    0.97     0.04 / 0.04   inert control
    #     0.0      0.6       0.1886    0.0935    0.50     0.07 / 0.29   <- adopted
    #     2.0      0.6       0.1935    0.0460    0.24     0.07 / 0.24
    #     6.0      0.0       0.2158    0.1830    0.85     0.06 / 0.13
    #    10.0      0.0       0.2189    0.1694    0.77     0.08 / 0.17
    #
    # Two things in that table are worth stating plainly, because neither is what was
    # expected.
    #
    # First, dopamine acting on the descending cord drive is a *weak* lever here. At
    # da_slow = 10 with [DA] near +0.3 the scale term is driven past its 0.25 floor and
    # pinned there, and the animal still only slows by 23%. Locomotor speed in this model
    # is set mostly by the proprioceptive loop and the motor neurons' own regenerative
    # dynamics, not by how hard the cord is driven, so turning that knob down does much
    # less than it looks like it should.
    #
    # Second, the response we do reproduce is carried entirely by the serotonergic arm:
    # more turning on food, which cuts net displacement in half and also drops path speed
    # by 30%. That is dwelling (Flavell et al. 2013) and it is real biology, but it is not
    # the same mechanism the assay is usually taken to measure -- in the animal, cat-2
    # mutants that cannot make dopamine fail to slow, so dopamine is *necessary*. Ours does
    # not need it. That is a genuine discrepancy and it is recorded rather than papered
    # over: the honest reading is that we reproduce the behaviour by the wrong route.
    dopamine_slowing: float = 0.0
    serotonin_slowing: float = 0.0
    # Shortens the proprioceptive reach towards SensoryParams.proprio_reach_food, which is
    # the only lever in this model that moves locomotor speed. See both of those.
    #
    # Implemented, measured, and left at zero. It does work -- at 2.3 the animal slows to
    # 79% of its off-food path speed, which is the only genuine basal slowing this model
    # has ever produced -- but it is not free: a slower animal covers less ground in a
    # 200 s assay, and the chemotaxis index halves from +0.070 to +0.034 with it on. Since
    # the taxis behaviours are what the sensory model is *for*, it is off by default and
    # kept for whoever wants to study the slowing response on its own.
    #
    #  da_wave | cond     | rev/min | path  ratio | net/path | wavelen  TWI  k_rms
    #    0.0   | off food |   2.13  | 0.374  1.00 |  0.438   |  0.82  +0.86  4.52
    #    0.0   | on food  |   1.73  | 0.374  1.00 |  0.569   |  0.84  +0.90  4.57
    #    2.3   | off food |   1.47  | 0.377  1.00 |  0.512   |  0.84  +0.89  4.51
    #    2.3   | on food  |   1.07  | 0.298  0.79 |  0.707   |  0.80  +0.86  4.42  <- adopted
    #    5.0   | on food  |   0.13  | 0.292  0.79 |  0.886   |  0.78  +0.84  4.49
    #
    # The slowing saturates near 0.79 however hard this is driven -- at 8.0 the reach is
    # 77% of the way to its floor and the ratio is still 0.78 -- because blending two
    # field matrices is not the same as one short reach and the long-range component
    # survives the blend. So the animal slows by a fifth where the animal halves. Past 2.3
    # the on-food reversal rate falls out of its band as well (0.27 /min at 3.5), so this
    # is the corner: the most slowing available without spending the behaviour to get it.
    dopamine_wavelength: float = 0.0

    # --- the amine load-sensing path's two effects (Python-only, defaults 0 = off) ------
    #
    # Both read the same dopamine level the basal slowing response does, driven through
    # SensoryParams.load_gain (see the provenance and the stated confound there). Both are
    # written so that a well-fed crawler on agar -- dopamine near its ceiling -- is the
    # SHIPPED animal, and the effect only engages as dopamine falls below that ceiling,
    # i.e. as the substrate stops pushing back. Vidal-Gadea et al. 2011: dopamine holds
    # the crawl; its absence permits the swim.
    #
    # `dopamine_head_lag` shortens the head reflex's lag budget as dopamine falls:
    # lag scale = clip(1 - coeff * max(0.5 - DA, 0), 0.4, 1). At coeff = 1 a fully
    # unloaded animal runs the reflex at half its shipped latency, which by the
    # tools/lag_span.py measurements roughly doubles the frequency -- the size of effect
    # the swim needs and the only load-scaled *time* in this model that survives below
    # K ~ 8, because its input is the drag force, not the bending. The 0.4 floor keeps
    # the loop out of the regime lag_span measured as fast-but-degraded. Applied to
    # head_tau and to the cascade stage taus; NOT to the head_delay ring buffer, whose
    # length is fixed at construction -- so the research configuration runs the cascade
    # (head_stages = 4, head_delay = 0), where the whole budget is stage taus and all of
    # it scales.
    dopamine_head_lag: float = 0.0
    # `dopamine_reach_swim` blends the proprioceptive fields toward the longer
    # SensoryParams.proprio_reach_swim as dopamine falls: blend = clip(coeff *
    # max(0.5 - DA, 0), 0, 1). The swim is a longer wave, not only a faster one -- 1.54 L
    # against 0.65 crawling (Fang-Yen et al. 2010) -- and reach is the one knob measured
    # to move wavelength without moving frequency (tools/wave_speed.py).
    dopamine_reach_swim: float = 0.0
    # `dopamine_muscle_rate` speeds the muscle excitation-contraction cascade as dopamine
    # falls: rate scale = clip(1 - coeff * max(0.5 - DA, 0), 0.5, 1), applied to
    # tau_calcium and tau_tension. **This is where the serotonin arm of Vidal-Gadea et
    # al. 2011 points** -- serotonin is necessary and sufficient to enter the swim -- and
    # why it is implemented off the dopamine withdrawal instead is stated so nobody
    # repeats the dead end: driving the serotonin *scalar* from low load would fire its
    # live food effects backwards (serotonin_turning = 0.6 ships hot, so a swimming
    # animal would gain a dwelling turn bias), entangling a second amine in the same
    # food/load confound already named at SensoryParams.load_gain. Separating the
    # serotonin scalar's roles is part of that same adoption precondition; until then the
    # swim-side muscle effect rides the one load signal the path already has. The
    # *target* is a modelling choice, made because the crossover measurements left the
    # EC cascade as the largest remaining fixed time once the head lag floors: measured
    # at the swim end, scaling it 0.6x moves the gait 1.500 -> 1.667 Hz and 1.30 ->
    # 1.44 L with the travelling index improving, +0.723 -> +0.794. The 0.5 floor keeps
    # the cascade's lag from vanishing outright.
    dopamine_muscle_rate: float = 0.0
    serotonin_turning: float = 0.6
    # Implemented, wired, and left at zero: not calibrated against anything. PDF in
    # particular is sourced from AVB, so a non-zero coefficient closes a positive feedback
    # loop (forward drive raises PDF raises forward drive) that is probably how
    # roaming/dwelling hysteresis works and deserves its own measurement.
    octopamine_speeding: float = 0.0
    pdf_roaming: float = 0.0

    # MOD-1: the sensory route by which food suppresses reversals.
    #
    # The problem this solves is that on a lawn the animal reverses far too often, and the
    # obvious fixes are all global. Shifting the direction gate's decision boundary moves
    # it for every behaviour at once, and the measurement in SensoryParams.turn_bias_limit
    # shows what that costs: tighten it enough to calm the animal on food and chemotaxis
    # inverts, aerotaxis climbs the wrong way and nociception stops, because the reversals
    # the taxis behaviours run on are the same ones being removed.
    #
    # What is wanted is a signal that exists *only* on food. The model has one already --
    # serotonin sits at +0.013 off food and +0.160 on it, a thirteenfold difference, since
    # NSM is driven by bacteria sampled at the nose rather than by the diffusible
    # attractant. What it lacked was any route from there to the command layer.
    #
    # There is no synaptic route. Measured in this reconstruction, CEP, ADE, PDE and NSM
    # make *zero* chemical or electrical contacts onto AIY, AIB or AVA, which is why
    # raising food_gain elevenfold moves the forward/backward command difference by 0.1
    # of its own standard deviation and then stops. The food sensors are anatomically
    # disconnected from the decision they ought to inform.
    #
    # That is exactly the case this layer exists for. Bentley et al. (2016), quoted at the
    # top of worm/modulators.py, found the monoamine network comparably dense to the
    # synaptic one and largely non-overlapping with it -- a neuron's modulatory targets
    # are mostly not the cells it synapses onto. And the receptor here is a documented
    # one: MOD-1 is a serotonin-gated *chloride* channel expressed on AIB (Ranganathan,
    # Cannon & Horvitz 2000), and mod-1 mutants are defective in exactly the food-related
    # behaviours this is about.
    #
    # AIB was tried first, because that is where MOD-1 actually is, and it does not work.
    # The channel itself behaves perfectly -- at a large coefficient AIB's activation goes
    # 0.65 -> 0.08 and its membrane potential -20 -> -45 mV, fully silenced -- and the
    # signal does reach RIM, whose activation falls 0.573 -> 0.455 through those 32
    # contacts. But AVA barely notices: 0.584 -> 0.572, and the forward/backward command
    # difference moves from +0.1451 to +0.1412, which is nothing. Across coefficients from
    # 0 to 50 the on-food reversal rate stays flat at about 8 a minute. The AIB->RIM->AVA
    # path is three chemical contacts and six gap junctions wide, against a command pool
    # that is heavily gap-coupled to everything else, and it cannot move the decision.
    #
    # So the channel is placed on the backward command pool itself. That is a coarser
    # claim than the receptor biology supports -- MOD-1 is documented on AIB and AIY, not
    # on AVA -- and it is recorded as a shortcut rather than dressed up: the anatomically
    # correct target was tried, measured, and found not to carry. What the shortcut keeps
    # is the part that matters, which is that the signal is *sensory and food-specific*
    # rather than a global shift of a decision boundary every behaviour shares. Serotonin
    # sits at +0.013 off food and +0.160 on it, and the selectivity follows: at the
    # adopted coefficient the command difference rises by 0.155 on food and 0.014 off it.
    #
    # Expressed as a conductance rather than a current, because that is what a ligand-gated
    # channel is: it saturates, it shunts, and it cannot drive the cell past its own
    # reversal potential however much serotonin arrives. Given as a fraction of the
    # target's resting conductance, the same convention as ca_ratio and adapt_ratio.
    #   mod1 | cond     | rev/min | net/path | net mm/s
    #   0.00  | off food |  4.27   |  0.341   |  0.1177
    #   0.00  | on food  |  6.45   |  0.277   |  0.0880
    #   0.30  | off food |  3.67   |  0.350   |  0.1250   <- adopted
    #   0.30  | on food  |  2.85   |  0.377   |  0.1374
    #   0.60  | on food  |  0.68   |  0.153   |  0.0583
    #
    # At 0.30 the off-food rate lands in the animal's 3.2-3.5 band and the on-food rate
    # more than halves, while net-to-path *rises* on food -- the animal now travels better
    # on a lawn than off one, which is the first time that has been true. 0.60 reaches the
    # on-food reversal target outright but costs the locomotion to get there, so it is
    # past the corner. On food the animal still reverses 2.9 times a minute against
    # 0.7-1.25, so this closes most of the gap rather than all of it.
    serotonin_mod1: float = 0.0
    mod1_targets: tuple = ("AVA", "AVD", "AVE")


@dataclass(frozen=True)
class PharynxParams:
    """Feeding. See worm/pharynx.py for who does what and why it is myogenic."""

    # The pump with no neural drive at all. Avery & Horvitz (1989) killed every pharyngeal
    # neuron and the pharynx still pumped, slowly, so the oscillator is not built out of
    # neurons and this is not zero. It is the floor an animal falls to, not its resting
    # rate: off food the model lands near this, on food the neurons carry it up.
    myogenic_rate: float = 0.5       # Hz

    # MC is the pacemaker, and it is the eat-2 phenotype that says how much it is worth:
    # animals lacking the receptor MC acts on pump several-fold slower and grow up
    # starved. The gain is large because the *signal* is small -- MC's activation moves
    # only 0.557 -> 0.599 between a bare plate and a lawn, since the food signal reaches
    # it second-hand through NSM and the pharynx's own wiring rather than directly.
    mc_rate_gain: float = 1.30       # Hz per unit MC drive

    # I2 inhibits pumping (Bhatla & Horvitz 2015, where it drives the feeding arrest that
    # follows light or peroxide). Small here, because in this model I2 is *excited* by
    # food -- see glucl_pre below for why that is probably wrong and what it costs.
    i2_rate_gain: float = 1.0        # Hz per unit I2 activation above rest

    # Serotonin is the other half of the food response and the better-attested half: a
    # starved animal given exogenous 5-HT pumps as though it were fed (Horvitz et al.
    # 1982), and NSM is the cell that releases it on tasting food. In this model serotonin
    # sits at +0.013 off food and +0.160 on it, so this coefficient carries most of the
    # on-food increase and MC carries the rest.
    serotonin_to_mc: float = 20.0    # added to MC's drive per unit serotonin
    octopamine_to_mc: float = 4.0    # subtracted per unit octopamine, the starvation signal

    max_rate: float = 6.0            # Hz  a hard ceiling; the animal tops out near 5

    # M3 repolarises the pharyngeal muscle and so terminates the pump. M3-killed animals
    # have measurably longer pumps, which is the whole reason duration is separate from
    # rate here.
    pump_duration: float = 0.18      # s   ~150-200 ms in a fed animal
    m3_duration_gain: float = 3.0    # per unit M3 activation above rest

    # What one pump takes in, at full lawn density. Chosen so that the animal feeding at
    # its target rate ingests what WorldParams.ingestion_rate was calibrated to deliver:
    # 0.02 units/s at 4 Hz is 0.005 per pump. That keeps every foraging number this
    # project has already measured, while making the rate a consequence of the circuit
    # rather than a constant.
    volume_per_pump: float = 0.005   # patch density units per pump on full food

    # Isthmus peristalsis: M4 is what moves the lumen's contents to the intestine. An
    # M4-ablated animal pumps normally and starves anyway, so this is modelled as its own
    # step -- capture fills the lumen, M4 empties it, and a full lumen stops capture. The
    # base rate is non-zero because grinding is not entirely neurogenic; the gain is what
    # M4 adds.
    # The base is deliberately almost nothing. An M4-ablated animal pumps normally and
    # starves, so transport without M4 has to be nearly absent -- a generous base rate
    # reproduced the pumping half of the phenotype and none of the starving half, which
    # is the whole reason capture and transport are separate steps here.
    m4_transport: float = 0.05       # 1/s  lumen emptied per second with M4 gone
    m4_gain: float = 27.0            # 1/s per unit M4 activation above rest
    lumen_capacity: float = 0.05     # units; about ten pumps' worth


@dataclass(frozen=True)
class EggLayingParams:
    """Egg-laying. See worm/egglaying.py for the circuit and what each term is for.

    The behaviour these numbers exist to produce is *clustered*, not merely paced.
    Waggoner et al. (1998) timed it: active phases of roughly two minutes containing
    several events about twenty seconds apart, separated by inactive phases of roughly
    twenty minutes. A mean rate of four or five eggs an hour is trivial to hit and says
    nothing about whether there is a circuit; the interval distribution is the claim.
    """

    # --- who drives ------------------------------------------------------------------
    # The floor: what the vulval muscle does with no drive at all. An HSN-ablated animal
    # is egg-laying *defective*, not incapable, so this cannot be zero -- the same role,
    # for the same reason, that myogenic_rate plays for the pharyngeal pump.
    #
    # KNOWN OVERSHOOT, and the reason is structural rather than a bad value here.
    #
    # An HSN-ablated animal in this model lays *nothing*: five animals, sixty simulated
    # minutes each, zero eggs, uterus pinned at capacity in all five. The real phenotype is
    # egg-laying *defective* -- retention and bloating, which this does reproduce, plus a
    # much reduced but nonzero rate, which it does not.
    #
    # Raising this floor from 0.25 to 0.33 did not help, and measuring the drive explains
    # why. With HSN gone the vulval muscle activation over ten minutes runs
    #
    #     min 0.081   p50 0.458   p90 0.474   p99 0.485   max 0.494
    #
    # against a vm_threshold of 0.55. That distribution is almost flat: above the median it
    # spans four hundredths, and its maximum over ten minutes never comes within 0.05 of
    # firing. vm is a low-pass filter of the drive with a 0.35 s constant, and the surviving
    # inputs -- the myogenic floor and a serotonin level averaged over its own 20 s tau --
    # have no fast structure left to pass. So there is nothing for a threshold to catch
    # intermittently: any value of this parameter flips the ablated animal from never to
    # often, with no graded regime between.
    #
    # A graded ablation phenotype therefore needs a mechanism this model does not have, not
    # a better constant. The candidate is the right one biologically: vulval muscle calcium
    # transients are themselves stochastic, so the decision to lay is not a deterministic
    # function of the network state the way it is here. Adding that is a real change and
    # should be made for that reason, not to rescue a number. Left at the original 0.25.
    myogenic: float = 0.25
    # HSN is the driver, and it enters as its ABSOLUTE activation rather than as a
    # deviation from its own resting level. That distinction is the phenotype: written as
    # a deviation -- the way the pharynx's modulators are written, which is correct for a
    # modulator of a myogenic rate -- HSN contributes zero mean drive and ablating it
    # changes nothing. The first run of tools/egglaying.py had HSN-ablated animals laying
    # *more* than intact ones, which is how this was found.
    # 0.55 x a resting activation near 0.53 puts the intact animal comfortably over
    # vm_threshold and the ablated one under it, where laying waits on a fluctuation.
    hsn_gain: float = 0.55           # per unit HSN activation
    # The humoral arm. HSN is serotonergic, and exogenous serotonin induces laying *in
    # HSN-ablated animals*, which places its action downstream of HSN rather than through
    # it. Modelled as a separate term for exactly that reason: with hsn_gain removed this
    # one still reaches the muscle. HSN has been in ModulatorParams.serotonin_sources
    # since the modulator layer was built, so the loop closes through machinery that was
    # already here.
    # Sized for the BATH, not for the endogenous level. Exogenous serotonin is applied at
    # a concentration that saturates the response; the pool an intact animal maintains is
    # around 0.1 and should contribute a nudge, not the whole drive. Set at 6.0 first,
    # against a level of 0.018 read off a twelve-minute probe, which turned out to be
    # unrepresentative -- over two minutes on a lawn the level is 0.12, and 6.0 x 0.12
    # saturated the muscle on its own and swamped every other term including HSN's.
    serotonin_gain: float = 0.80     # per unit serotonin level
    # The VCs are a brake, not a driver: VC-ablated animals lay slightly *more*. Small,
    # because the effect is small -- and smaller than it first looks, for a reason visible
    # in the wiring rather than in the pharmacology. HSN synapses onto the VCs (HSNR onto
    # VC02 and VC03, HSNL onto VC05), so ablating HSN also silences its own brake. At a
    # gain of 1.0 that disinhibition very nearly cancelled the drive HSN had just stopped
    # supplying, and HSN-ablated animals came out laying *more* than intact ones -- the
    # second time this circuit produced that result, by a completely different route from
    # the first.
    vc_gain: float = 0.15            # per unit VC activation above rest
    # VC06 is excluded in worm/egglaying.py by name rather than by weight. It has zero
    # synapses and zero gap junctions in this reconstruction, and measured on food its
    # activation swing is 0.88 -- the largest of the eight, and entirely background noise.

    # --- the muscle ------------------------------------------------------------------
    vm_tau: float = 0.35             # s    vulval muscle activation time constant
    vm_threshold: float = 0.55       # activation at which the vulva opens

    # --- food ------------------------------------------------------------------------
    # Off food the animal retains eggs. Multiplicative rather than additive because no
    # amount of HSN drive makes a starved animal lay freely; not zero, because retention
    # is not abolition and a starved animal eventually lays.
    off_food_floor: float = 0.12     # fraction of the drive that survives with no food

    # --- the uterus ------------------------------------------------------------------
    # Eggs are made out of food, which is the entire coupling to the pharynx: an animal
    # that does not eat does not make eggs. `ingested` is in patch-density units and a fed
    # animal moves about 4.4 of them per 12 minutes, measured, so this is a conversion
    # rather than anything from the literature. Set so production modestly exceeds laying
    # -- a laying hermaphrodite carries ten to fifteen eggs in utero, so the uterus sitting
    # near capacity on food is the correct state and not a symptom. What distinguishes the
    # arms is what happens to that stock: off food it neither fills nor drains, and with
    # HSN gone it fills and stays full, which is the retention half of the Egl phenotype.
    eggs_per_food: float = 0.70      # eggs per unit ingested (~15/hour on a lawn)
    uterus_capacity: float = 15.0    # eggs; a blocked animal becomes bloated, not infinite
    # KNOWN SIMPLIFICATION: there is no brood limit. A self-fertilising hermaphrodite makes
    # about 300 sperm during L4 and then switches its germline to oocytes permanently, so
    # its ~300-egg brood is *sperm*-limited -- it runs out of sperm, not of food or of
    # oocytes. Here eggs are made from food without end, so an animal kept on a lawn lays
    # forever. That is wrong on any run longer than a few hours of simulated time, and it
    # is the first thing to fix if this is ever used for a population: a lifetime brood cap
    # is what makes generations finite. (Mated with a male the real animal exceeds 1000,
    # because male sperm outcompete self sperm and are not limiting -- but modelling that
    # needs males, and males need a tail, spicules and their own motor program.)
    eggs_initial: float = 3.0        # a young adult starts with some ready to go

    # --- what makes phases -----------------------------------------------------------
    # A depleting resource with its own recovery constant -- the same Tsodyks-Markram
    # idiom worm/senses.py uses for tap habituation, and for the same reason: it produces
    # history-dependence from one equation instead of from a schedule. An active phase
    # spends the resource; recovery takes minutes; the phase ends when what is left cannot
    # support another event. Nothing here counts events or times a phase.
    # Two thresholds, not one: a Schmitt trigger, the same shape the direction gate uses.
    # With a single threshold there is no inactive phase worth the name -- the phase ends
    # the instant the resource dips below it, leaving the resource *at* the threshold, so
    # it climbs back over within a step or two and laying resumes. The quiet period is
    # produced by having to recover all the way to `resource_on` before another phase can
    # begin. From 0.44, that climb takes about -tau*ln((1-on)/(1-0.44)) seconds.
    resource_tau: float = 900.0      # s    recovery time constant; quiet phase ~20 min
    resource_cost: float = 0.14      # spent per egg; (on - off)/cost sets events per phase
    resource_off: float = 0.45       # the active phase ends below this
    resource_on: float = 0.85        # and cannot begin again until back above this
    refractory: float = 6.0          # s    minimum spacing between events

    # Seconds, not steps. This was `rest_samples: int = 4000`, counted in timesteps, so
    # the averaging window was 2 s at dt = 0.5 ms and 8 s at dt = 2 ms -- the same
    # dt-dependence this project has already had to fix three times, most expensively in
    # BodyParams.dt, where NEXT.md day ten withdrew three days of conclusions over it. The
    # window is a property of the animal's settling time, not of how finely it is being
    # integrated. 2.0 s reproduces the old default exactly at the shipped dt.
    rest_seconds: float = 2.0        # s    averaged to find each pool's resting level


@dataclass(frozen=True)
class SleepParams:
    """RIS-gated quiescence: the homeostat, the drive, and FLP-11's targets.

    The circuit and its provenance live in worm/sleep.py (Turek et al. 2013 for RIS;
    Turek et al. 2016 for FLP-11; You et al. 2008 for satiety quiescence in the adult).
    What belongs here is what the numbers mean and why they are what they are.

    The clock is the dish's, not the animal's: real satiety quiescence follows hours of
    feeding; here pressure crosses threshold after ~3-4 minutes on a lawn (dopamine's
    positive deviation on food runs ~0.10-0.15, so build_fed * 0.12 ~ 0.0036/s reaches
    0.7 in ~200 s) and a bout discharges 0.7 -> 0.25 in about one tau_sleep. The
    *structure* is the biology; the rates are watchable.

    Below threshold_on the whole module is provably inert: drive exactly 0, FLP-11
    exactly 0 (release gated on the driven bout -- worm/sleep.py has the measured
    reason), every gain multiplier exactly 1.0. An animal that has not yet slept is
    bit-identical to the animal before sleep existed, which is what keeps every pinned
    trajectory and conformance case standing.

    An assay that feeds the animal on a dense lawn for longer than about a minute now
    contains sleep, and that is the model, not a confound to tune away: the pharynx
    fixture's animal fell asleep mid-measurement the day this landed and its mean pump
    rate dropped from 250 to 194 a minute. When the claim under test is about the
    AWAKE animal, run the sleepless control: `ris_drive = 0.0` disables the drive, and
    with it this module touches nothing (tests/test_pharynx.py does exactly this).
    """
    ris_drive: float = 30.0          # pA into RIS while the homeostat says sleep
    release_threshold: float = 0.75  # RIS activation where FLP-11 release begins
    flp11_tau: float = 8.0           # s   peptide level's time constant
    quiescence_gain: float = 1.4     # FLP-11 -> motor/pump gate, clipped to [0, 1]
    build_fed: float = 0.030         # /s  pressure per unit positive dopamine deviation
    build_base: float = 0.0005       # /s  the trickle off food (starved animals barely sleep)
    threshold_on: float = 0.7        # pressure where a bout begins
    threshold_off: float = 0.25      # pressure where it ends -- the Schmitt gap
    tau_sleep: float = 45.0          # s   pressure discharge during a bout
    arousal_touch: float = 0.5       # summed touch_state that interrupts a bout
    arousal_refractory: float = 15.0  # s  sleep held off after an arousal
    arousal_clear: float = 0.8       # fraction of standing FLP-11 an arousal clears


@dataclass(frozen=True)
class Params:
    neural: NeuralParams = field(default_factory=NeuralParams)
    muscle: MuscleParams = field(default_factory=MuscleParams)
    body: BodyParams = field(default_factory=BodyParams)
    world: WorldParams = field(default_factory=WorldParams)
    sensory: SensoryParams = field(default_factory=SensoryParams)
    modulator: ModulatorParams = field(default_factory=ModulatorParams)
    pharynx: PharynxParams = field(default_factory=PharynxParams)
    egglaying: EggLayingParams = field(default_factory=EggLayingParams)
    sleep: SleepParams = field(default_factory=SleepParams)
    medium: MediumParams = field(default_factory=lambda: MEDIA["agar"])

    def validate(self) -> "Params":
        """Reject parameter sets that make the equations singular or nonphysical.

        Optimisers are expected to construct instances with ``dataclasses.replace``.
        Dataclasses intentionally do not validate on assignment, so the complete tree is
        checked at the boundary where it becomes a simulation.  The exception type lets
        an evaluator score a bad candidate as lethal without losing a worker process.
        """
        values = dict(_param_values(self))
        problems = []

        for path, value in values.items():
            if (isinstance(value, Real) and not isinstance(value, bool)
                    and not math.isfinite(value)):
                problems.append("%s must be finite (got %r)" % (path, value))

        def positive(path: str) -> None:
            value = values[path]
            if isinstance(value, bool) or not isinstance(value, Real):
                problems.append("%s must be a real number (got %r)" % (path, value))
            elif math.isfinite(value) and value <= 0.0:
                problems.append("%s must be > 0 (got %r)" % (path, value))

        def nonnegative(path: str) -> None:
            value = values[path]
            if isinstance(value, bool) or not isinstance(value, Real):
                problems.append("%s must be a real number (got %r)" % (path, value))
            elif math.isfinite(value) and value < 0.0:
                problems.append("%s must be >= 0 (got %r)" % (path, value))

        # Direct divisors and the physical coefficients whose sign defines the model.
        for path in (
            "neural.C_m", "neural.g_leak", "neural.a_rise", "neural.a_decay",
            "neural.ca_slope", "neural.k_slope", "neural.dt",
            "muscle.C_m", "muscle.g_leak",
            "body.length", "body.radius_max", "body.EI", "body.dt",
            "medium.c_tangential", "medium.c_normal",
            "world.radius", "world.field_dt", "world.o2_length_scale",
            "pharynx.pump_duration", "pharynx.lumen_capacity",
        ):
            positive(path)

        # Every first-order time constant appears in a denominator or exponential rate.
        #
        # `sensory.head_stage_tau` is the one exception and it is exempted here rather than
        # renamed out of the pattern, because the pattern is worth more than the name. Zero
        # is its "derive it" sentinel and never reaches a denominator: `worm/senses.py`
        # substitutes `head_tau / head_stages`, which is positive because `head_tau` is and
        # is checked by this same loop. The effective value is asserted below, so the
        # guarantee the rule exists for still holds -- it is the sentinel that is exempt,
        # not the quantity.
        for path in values:
            leaf = path.rsplit(".", 1)[-1]
            if path == "sensory.head_stage_tau":
                continue
            if leaf.startswith("tau_") or "_tau" in leaf:
                positive(path)
        nonnegative("sensory.head_stage_tau")

        # The cascade must have at least one stage, and whichever lag each stage ends up
        # carrying has to be a real positive time. This is the check the exemption above
        # hands off to, written against the value senses.py will actually use.
        stages = values["sensory.head_stages"]
        if not isinstance(stages, Real) or isinstance(stages, bool) or stages < 1:
            problems.append("sensory.head_stages must be >= 1 (got %r)" % (stages,))
        else:
            declared = values["sensory.head_stage_tau"]
            head_tau = values["sensory.head_tau"]
            if (isinstance(declared, Real) and isinstance(head_tau, Real)
                    and math.isfinite(declared) and math.isfinite(head_tau)):
                effective = declared if declared > 0.0 else head_tau / int(stages)
                if effective <= 0.0:
                    problems.append(
                        "the head cascade's per-stage time constant works out at %r, which "
                        "is a denominator; set sensory.head_stage_tau > 0 or give "
                        "sensory.head_tau a positive value" % (effective,))

        nonnegative("body.internal_damping")
        if (isinstance(values["medium.c_normal"], Real)
                and not isinstance(values["medium.c_normal"], bool)
                and isinstance(values["medium.c_tangential"], Real)
                and not isinstance(values["medium.c_tangential"], bool)
                and math.isfinite(values["medium.c_normal"])
                and math.isfinite(values["medium.c_tangential"])
                and values["medium.c_normal"] < values["medium.c_tangential"]):
            problems.append("medium.c_normal must be >= medium.c_tangential")

        for path in (
            "world.diffusion_attractant", "world.diffusion_repellent",
            "world.decay_attractant",
            "world.food_diffusion_scale", "world.ingestion_rate",
        ):
            nonnegative(path)

        for path, minimum in (
            ("neural.gap_iters", 1), ("body.n_links", 2), ("body.substeps", 1),
            ("world.grid", 2),
        ):
            value = values[path]
            if not isinstance(value, Integral) or isinstance(value, bool) or value < minimum:
                problems.append("%s must be an integer >= %d (got %r)"
                                % (path, minimum, value))

        if problems:
            raise InvalidGenome("invalid simulation parameters: " + "; ".join(problems))
        return self

    def with_medium(self, name: str) -> "Params":
        if name not in MEDIA:
            raise ValueError("unknown medium %r (have %s)" % (name, sorted(MEDIA)))
        return replace(self, medium=MEDIA[name])


def _param_values(value, prefix: str = ""):
    """Yield dotted paths and leaf values from the nested parameter dataclasses."""
    for item in fields(value):
        child = getattr(value, item.name)
        path = "%s.%s" % (prefix, item.name) if prefix else item.name
        if is_dataclass(child):
            yield from _param_values(child, path)
        else:
            yield path, child
