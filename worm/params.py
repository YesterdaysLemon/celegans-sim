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
    # These default to zero, and that is a result rather than an omission. An intrinsic
    # oscillator in the motor neurons does produce a rhythm -- but the dorsal and ventral
    # members of a class have identical intrinsic dynamics and are coupled by gap junctions
    # and reciprocal synapses, so they phase-lock *to each other*. The animal then contracts
    # both sides of its body in time with itself and does not bend at all. The rhythm has to
    # come from somewhere that is dorsoventrally antisymmetric, and the head proprioceptive
    # reflex (see SensoryParams.head_proprio_gain) is exactly that. Non-zero values here are
    # kept because they are the right biology for RMD and AWA and are useful to experiment
    # with, but the working model does not need them.
    ca_g: float = 0.0            # nS   regenerative calcium conductance
    ca_beta: float = 0.125       # 1/mV activation steepness, instantaneous
    E_Ca: float = 120.0          # mV   calcium reversal
    adapt_g: float = 0.0         # nS   slow calcium-activated potassium conductance
    adapt_tau: float = 0.70      # s    its time constant
    E_K: float = -80.0           # mV   potassium reversal
    # Physiological rail, set at the potassium and calcium reversals. Motor neurons under
    # strong proprioceptive drive do reach the lower rail at the extremes of each cycle.
    # That is saturation rather than instability, and it is consistent with how the
    # reference neuromechanical models treat these cells -- Boyle et al. (2012) make their
    # B-type motor neurons frankly binary. Interneurons and sensory neurons stay well
    # inside the range.
    v_clamp: tuple = (-80.0, 45.0)    # mV
    oscillator_classes: tuple = ("RMD", "SMD")

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
    peak_moment: float = 1.6        # uN*mm

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
    ingestion_rate: float = 0.9      # patch density units per second while pumping
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
    proprio_gain: float = 90.0       # pA per unit normalised curvature
    # Wen et al. (2012) Neuron 76:750 showed by localised body restraint that B-type motor
    # neurons transduce the curvature of the region *anterior* to them, over roughly
    # 200 um -- a fifth of the body. Boyle et al.'s 2012 model, which predates that result,
    # integrates posteriorly over half the body instead; we follow the experiment.
    proprio_reach: float = 0.20      # fraction of body length sampled anteriorly

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

    # Forward is the default state. AVB is tonically active in a freely moving animal
    # and reversals are triggered events; a weak drive here leaves the command layer
    # bistable, and which way it settles depends on the noise seed rather than on anything
    # meaningful.
    tonic_forward: float = 90.0      # pA  tonic drive to the forward command interneurons


@dataclass(frozen=True)
class Params:
    neural: NeuralParams = field(default_factory=NeuralParams)
    muscle: MuscleParams = field(default_factory=MuscleParams)
    body: BodyParams = field(default_factory=BodyParams)
    world: WorldParams = field(default_factory=WorldParams)
    sensory: SensoryParams = field(default_factory=SensoryParams)
    medium: MediumParams = field(default_factory=lambda: MEDIA["agar"])

    def with_medium(self, name: str) -> "Params":
        if name not in MEDIA:
            raise ValueError("unknown medium %r (have %s)" % (name, sorted(MEDIA)))
        return replace(self, medium=MEDIA[name])
