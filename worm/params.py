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

from dataclasses import dataclass, field, replace


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
    internal_damping: float = 2.0e-4   # uN*mm^2*s

    # Moment arm of the body-wall muscles about the centreline, as a fraction of the
    # local body radius. The muscle sheets lie just under the cuticle.
    muscle_moment_arm: float = 0.85

    dt: float = 0.0005              # s   shared with the neural step


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

    radius: float = 25.0            # mm  a 50 mm petri dish
    grid: int = 192                 # cells across the dish for the chemical fields
    diffusion_attractant: float = 0.004   # mm^2/s   small molecules through agar
    diffusion_repellent: float = 0.004
    diffusion_oxygen: float = 0.02
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
    touch_gain: float = 34.0         # pA per uN of indentation force
    touch_tau: float = 0.35          # s   mechanoreceptor adaptation
    food_gain: float = 11.0          # pA  dopaminergic mechanosensation of the bacterial lawn
    proprio_gain: float = 30.0       # pA per unit normalised curvature
    # Wen et al. (2012) Neuron 76:750 showed by localised body restraint that B-type motor
    # neurons transduce the curvature of the region *anterior* to them, over roughly
    # 200 um -- a fifth of the body. Boyle et al.'s 2012 model, which predates that result,
    # integrates posteriorly over half the body instead; we follow the experiment.
    proprio_reach: float = 0.20      # fraction of body length sampled anteriorly

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
    head_reach: float = 0.17          # fraction of body length the head circuit reads

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
    gate_bias: float = 0.09          # activation difference at the 50/50 point


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
    serotonin_turning: float = 0.6
    # Implemented, wired, and left at zero: not calibrated against anything. PDF in
    # particular is sourced from AVB, so a non-zero coefficient closes a positive feedback
    # loop (forward drive raises PDF raises forward drive) that is probably how
    # roaming/dwelling hysteresis works and deserves its own measurement.
    octopamine_speeding: float = 0.0
    pdf_roaming: float = 0.0


@dataclass(frozen=True)
class Params:
    neural: NeuralParams = field(default_factory=NeuralParams)
    muscle: MuscleParams = field(default_factory=MuscleParams)
    body: BodyParams = field(default_factory=BodyParams)
    world: WorldParams = field(default_factory=WorldParams)
    sensory: SensoryParams = field(default_factory=SensoryParams)
    modulator: ModulatorParams = field(default_factory=ModulatorParams)
    medium: MediumParams = field(default_factory=lambda: MEDIA["agar"])

    def with_medium(self, name: str) -> "Params":
        if name not in MEDIA:
            raise ValueError("unknown medium %r (have %s)" % (name, sorted(MEDIA)))
        return replace(self, medium=MEDIA[name])
