# The model, in full

The landing README is the porch; this is the house. Everything below moved here
byte-for-byte from the README when the repository went public — same claims, same
numbers, same corrections kept in place — so a reader who wants the whole argument
still gets it in one document. The two-track rule applies throughout:
[`docs/project-architecture.md`](project-architecture.md) says which claims may touch
the animal, and [`../web/museum.md`](../web/museum.md) catalogues where the
reconstruction measurably falls short.

---

## The loop

Every timestep runs the same cycle the animal does. Nothing in the middle is scripted.

```
    world  ->  sensory neurons  ->  connectome  ->  motor neurons
       ^                                                   |
       |                                                   v
    body position <-  mechanics  <-  bending moment  <-  muscles
       |                                                   ^
       +----------------- proprioception ------------------+
```

### Nervous system

C. elegans neurons are, with a handful of exceptions, non-spiking — the animal has no
voltage-gated sodium channels at all. They signal by graded changes in membrane potential
and release transmitter continuously as a sigmoidal function of presynaptic voltage. The
model is the standard one (Wicks, Roehrig & Rankin 1996; Kunert, Shlizerman & Kutz 2014):

```
C dV_i/dt = -g_leak (V_i - E_leak)
            - Σ_j g_gap n_gap(i,j) (V_i - V_j)
            - Σ_j g_syn n_syn(j→i) s_j (V_i - E_j)  + I_i
ds_j/dt   = a_r φ(V_j)(1 - s_j) - a_d s_j
φ(V)      = 1 / (1 + exp(-β(V - V_th_j)))
```

`n_gap` and `n_syn` are reconstructed contact counts, so connection strength is anatomical
rather than fitted. Each neuron's release threshold `V_th` is solved self-consistently so
that it sits at the steepest point of its own sigmoid at rest — this removes 302 free
parameters and keeps the whole network responsive rather than silent or saturated.
Integration is exponential Euler with three fixed-point passes over the gap-junction
coupling, which buys implicit-solver accuracy at the cost of two matrix-vector products;
embedded membrane time constants span 0.1 ms to 6 ms across the connectome, so this matters.

**Where this departs from the reference implementations, deliberately.** Kunert et al. use
`g_leak = 0.01 nS`, an input resistance of 100 GΩ. Whole-cell recordings say 1.6–2.2 GΩ
(ASEL/ASER), and the AWA model that Liu et al. (2018) fitted to real recordings uses
`g_leak = 0.25 nS`, `E_leak = -65 mV`, `C = 1.5 pF`. With the published values the entire
network rests near −4 mV, some 55 mV depolarised from every recording ever made. We use the
measured electrophysiology. The network here rests between −62 and −12 mV, median −40 mV.

**AVL and DVB are excitatory.** Every standard model marks all 26 GABAergic neurons
inhibitory because they stain for GABA. AVL and DVB release GABA onto EXP-1, a GABA-gated
*cation* channel (Beg & Jorgensen 2003), so their synapses depolarise their targets. We
keep them GABAergic and make their synapses excitatory.

**And three glutamatergic synapse sets are inhibitory**, the same correction run the other
way: the sign of a synapse belongs to the receptor, not the transmitter, and named cells
answer the ON chemosensors' and the phasmids' glutamate with chloride —
`NeuralParams.glucl_pre/post` carries ASEL/AWA/PHB onto AIY/AVA/AIB, each pairing adopted
on its own measurement (that list is why PHB → AVA is a brake on reversal rather than a
reversal driver, and why "things improving" no longer commands one).

### Muscle

All 95 body-wall muscle cells are simulated individually, in their four quadrants, with
their own reversal potentials (E_ACh ≈ +20 mV, E_Cl ≈ −30 mV, rest ≈ −25 mV — measured
values, quite different from the neurons'). The excitation-contraction cascade is three
first-order stages — membrane potential, calcium, tension — with a combined lag of about
100 ms, matching the single lumped constant Boyle et al. fitted to real muscle.

Two calibrations are applied to the neuromuscular map, both documented in
`worm/params.py`. Reconstructed contact count per muscle cell ranges from 5 to 47, a spread
owing as much to how completely each region of the original animal was sectioned as to real
anatomy; and the model is two-dimensional, so left and right members of each quadrant merge.
Left uncorrected, the heavier ventral innervation holds the worm in a permanent C. So total
drive is equalised across the 95 cells, and each cell's excitatory conductance is scaled so
it rests at the midpoint of its own tension curve. The *relative* weighting among any one
cell's presynaptic partners stays exactly as reconstructed.

### Memory

Two things here remember. Everything else forgets on purpose: the sensory adaptation
filters exist to discard the past, and the modulators integrate over tens of seconds and
then decay. The second memory is sleep's — the satiety homeostat (`worm/sleep.py`) builds
pressure over minutes and deliberately keeps it across an arousal, which is what makes a
poked sleeper go back to sleep. The first: the mechanoreceptor carries a depleting resource — repeated taps
consume it, rest refills it with its own time constant — which reproduces the three things
Rankin, Beck & Chiba (1990) measured in tap habituation from one equation rather than
three fits: the response decrements, it recovers with rest, and a shorter interval
habituates deeper than a longer one. That last is what distinguishes habituation from
fatigue, and it holds here — 0.25 resource remaining at a 10 s interval against 0.45 at
30 s, for the same rate and the same number of taps.

It sits in the receptor rather than at the synapse, and that is a measured result rather
than a preference: Rose and Rankin place the change presynaptically, but this connectome
routes the tap response through gap junctions — cutting ALM and AVM's entire chemical
output leaves the response unchanged, while cutting their gap junctions halves it — and no
presynaptic depression can habituate an ohmic junction. The presynaptic machinery is
present and switched off.

The memory is currently invisible in behaviour, for the reason given under *what it does
not get right*: there is no tap-withdrawal reversal to decrement.

### Body

An inextensible active elastica at zero Reynolds number. A swimming C. elegans has Re ≈
10⁻³: inertia is not small, it is irrelevant. So rather than integrating F = ma with stiff
springs, the dynamics are written in the form they actually take,

```
D(q) q̇ = Q(q)
```

with `q` the head position plus the angle of each of 48 rigid segments, `D` the
configuration-dependent viscous drag metric from resistive force theory, and `Q` the
elastic and muscular generalised forces. The body is *exactly* inextensible by
construction. Assembling `D` looks like an O(n³) triple sum and collapses to three n×n
matrix products, which is what makes it cheap enough to run at 2 kHz.

Bending modulus is Fang-Yen et al.'s measured 9.5×10⁻¹⁴ N·m². Drag coefficients are the
Boyle/Berri/Cohen values (agar C∥ = 3.2, C⊥ = 128; buffer 3.3×10⁻³, 5.2×10⁻³, in
µN·s/mm²). The ratio C⊥/C∥ is the entire story of gait modulation: at a ratio of 1 an
undulating body goes nowhere at all, whatever its waveform.

### Where the rhythm comes from

This is the part that took the longest and is worth being precise about.

A passive graded network **cannot oscillate** — it is a contraction mapping onto a fixed
point. And proprioception alone cannot either: it is a transport rule, it copies a bend
backwards but never starts one. Something has to oscillate.

Making the motor neurons into free-running intrinsic oscillators (Morris-Lecar; the right
biology, since every regenerative event in this animal is calcium-carried) *does* produce a
rhythm — and it does not work. The dorsal and ventral members of a class have identical
intrinsic dynamics and are coupled by gap junctions and reciprocal synapses, so they
phase-lock **to each other**: the animal contracts both sides of its body in time with
itself and does not bend at all. Measured directly, the presynaptic inputs to a single
muscle had a pairwise correlation of 0.97. Pushed hard enough to free-run they fail a
second way as well — each segment locks to itself, the tail reaches four times the head's
amplitude, and the wave travels backwards. The rhythm has to come from somewhere
dorsoventrally *anti*symmetric.

So it comes from the head, as it does in the animal (Wen et al. 2012 showed the body wave
is initiated at the neck and propagated posteriorly by proprioceptive coupling). The head
motor neurons RMD, SMD and SMB are themselves proprioceptive (Yeon et al. 2018), and their
reflex is **negative**: a dorsal head bend excites the ventral head motor pool and inhibits
the dorsal one. Negative feedback through the ~100 ms muscle delay is an oscillator, and
because dorsal and ventral get opposite signs it is antisymmetric by construction.

The body reflex is the opposite sign — **positive**, copying the anterior bend rearwards,
which is what makes the wave travel instead of stand. Each B-type motor neuron reads
curvature over the 20% of body length in front of the muscles it drives, and contracts the
muscle on the same side, which is what Wen et al. measured. A-type motor neurons read
*behind* themselves, which drives the wave the other way for backward locomotion; which
system is engaged is gated by AVB versus AVA, through gap junctions that are in the
connectome.

One subtlety that cost real debugging time: the receptive field must be referenced to the
muscles a neuron drives, not to its cell body. DB and VB somas are interleaved along the
ventral cord in a way that does not line up dorsoventrally, so referencing to the soma
silently gives the two halves of the circuit different views of the same bend and they stop
working as an antagonistic pair.

Those two paragraphs describe where the rhythm is *born*. They do not explain how it
survives the trip down the body, and it turns out that is a separate problem with a separate
answer. A chain of passive relays must attenuate — Xu et al. (2018) show the decay is
exponential and that head gain, muscle moment and bending stiffness can only trade against
one another — and measured here the amplitude fell 2.5-fold from head to tail, with the
tail's coherence at 0.03. So the B-type motor neurons are not passive relays. Each carries
a Morris-Lecar pair sized as a fraction of its own resting conductance, and the descending
AVB gap junctions already present in the connectome hold it **at** a Hopf bifurcation:
enough regenerative gain to restore the amplitude the relay loses, not so much that it
free-runs and stops listening. The head still sets the phase and the sign; each segment
now pays for its own amplitude.

---

---

## Does it behave like a worm?

`pytest tests/` includes the load-bearing checks below. Reference values are
measurements on live animals; the model column is the mean and spread over five seeds from
a single run of `tools/scorecard.py`, so every row describes the same animal. It has not
always: this table once quoted a crawling speed from day two beside a frequency from day
nine.

| Quantity | Model | Measured | Source |
|---|---|---|---|
| Curvature, r.m.s. | **4.53 ± 0.05 /mm** | 4.3 ± 0.3 /mm | Krajacic et al. 2012 |
| Curvature, peak | **13.2 ± 1.2 /mm** *(sharp)* | 9.8 ± 1.1 /mm | Krajacic et al. 2012 |
| Wave direction | **head → tail** | head → tail | — |
| Muscle resting potential | **−22.0 mV** *(a point, not a range)* | −25.0 ± 1.0 mV | Gao & Zhen 2011 |
| Resting potentials | **−62 to −12 mV**, median −39 | −75 to −25 mV | several, see `params.py` |
| Swimming efficiency U/c | **0.051 ± 0.002** *(low)* | 0.08 ± 0.01 | Shen et al. 2012 |
| Neuron count / classes | **302 / 118** | 302 / 118 | canonical |
| GABAergic neurons | **26** | 26 | McIntire et al. 1993 |
| Crawling speed (net) | **0.309 ± 0.051 mm/s** | 0.219 ± 0.029 mm/s | Ramot et al. 2008 |
| Net displacement / path | **0.82 ± 0.11** | well above 0.5 | — |
| Travelling-wave index | **+0.87 ± 0.04** | +1 for a pure travelling wave | — |
| Undulation frequency, agar | **0.66 ± 0.01 Hz** | 0.30 ± 0.02 Hz *(see below)* | Fang-Yen et al. 2010 |
| Wavelength, agar | **0.86 ± 0.02 L** *(long)* | 0.65 ± 0.03 L | Fang-Yen et al. 2010 |

Curvature, wave direction and the neuron resting potentials land on the measured values.
The muscle rest and the swimming efficiency do not, and the gait's *timing* does not: see
below.

Three of these rows carry a published correction. The muscle rest, the resting-potential
span and U/c were written by hand on day one and never produced by `tools/scorecard.py`
at all — the very commit that added "every row describes the same animal" stepped over
them. The tool's `v_lo`/`v_hi` also read the membrane once after ~90 s of crawling, which
is a phase lottery, not a rest: across five seeds some head motor neuron sits on the
**+45 mV clamp for 76%** of the window and on the **−80 mV clamp for 86%** — `v_clamp` is
in the loop, not a numerical backstop (the cause is H2's proprioceptive current
injection; see *what it does not get right*). `scorecard.py` now measures rest where a
resting state exists — deterministically, before the animal moves — and reports the
crawling span separately under its own name, with the clamp occupancy printed beside it.
The muscle "rest" is exactly `v_half` by construction (`_balance` solves every cell to
`rest_tension = 0.5`), so it is a point, and how near Gao & Zhen it lands is a
coincidence of two independently chosen numbers.

The mechanics are verified independently of the biology: the assembled drag metric matches
direct Gauss-Legendre quadrature of the integral it stands for to 2×10⁻¹⁶ relative, it is
positive definite, body length is conserved to 10⁻¹² over the full closed loop, a passive
bent worm relaxes straight with monotonically decreasing bending energy, and driving the
body with a prescribed travelling wave reproduces the Gray-Hancock slip law to within 3.3%
across a 25-fold range of drag anisotropy.

The nervous system's noiseless fixed point holds to 4×10⁻¹⁴ mV over two simulated seconds,
which is a sharp check that the self-consistent threshold solve and the integrator agree.

### What works

**Nociception.** Dropped at the centre of a noxious drop the animal ends **34.0 mm** out
against **19.4 mm** for the same animal, same seed, on plain agar — a paired difference of
+14.7 mm [+8.0, +21.1]. That is avoidance measured against its own control, which is the
only way the claim means anything; the first version of this assay had none and reported
the opposite of the truth. See [the correction](#the-correction-nociception-never-worked-either--and-then-the-fix-for-it).

**Habituation.** Repeated taps deplete a mechanoreceptor resource, rest refills it, and a
shorter interval habituates deeper — three properties of Rankin's tap habituation out of
one equation rather than three fits, and integrated exactly so how much the animal learns
does not depend on the timestep.

**Spontaneous reversals**, at 3.3 a minute against the animal's 3.2–3.5 off food, in
episodes long enough to be reversals rather than threshold flicker.

**Sleep, and it wakes to a poke.** A satiety homeostat builds pressure while the animal
feeds — about a minute to threshold on a dense lawn, measured the day it landed when the
pharynx assay's animal fell asleep mid-measurement — and above threshold it drives RIS,
the one neuron whose activation the biology calls sufficient for quiescence (Turek 2013).
RIS quiets the command and head circuits through its own GABAergic wiring and releases
FLP-11, which stands down the cords, the head oscillator and the pharyngeal pump: the
animal stops moving and stops pumping, keeps full touch sensitivity, and a strong poke
wakes it within a second (arousal clears most of the standing peptide — rapid
reversibility is what separates sleep from paralysis). Pressure survives the arousal, so
a poked sleeper naps again: rebound for free. Ablate RIS and sleep is abolished, FLP-11
exactly zero — the Turek experiment, reproduced. An animal that has never slept is
bit-identical to the pre-sleep model, which is what kept every conformance case standing.

**Egg-laying, and it is clustered.** HSN and the VCs drive vulval muscle; the uterus fills
from what the pharynx actually transported, so an animal that does not eat does not make
eggs. Five animals for an hour each give **11.0 eggs/hour with an interval CV of 1.79** —
60% of intervals under a minute and 20% over two. Both tails populated is bimodality, and
it is the one shape a timer cannot produce; nothing in the model schedules a phase, so the
gaps are a depleting resource behind a Schmitt trigger. Off food the animal retains its
eggs, and a serotonin bath rescues laying in an HSN-ablated animal, which is what places
serotonin downstream of HSN rather than through it.

One caveat kept in front rather than buried: the *median* interval is 6.0 s, which is
exactly the refractory period, so the fast half of that bimodality is a parameter. What
emerges is the slow half.

### The omega turn, and what it unlocked

For most of this model's life the animal reversed but did not **reorient**: median heading
change across a reversal was 21°, and not one measured exceeded 120°, against a real animal
ending about 35% of its reversals in an omega turn of 160–170°.

A biased random walk steers by choosing *when* to change direction, so if changing direction
does not change the direction there is nothing to bias. That was why three separate assays
reported a correct mechanism and a null outcome. Nociception looked like the exception —
the one behaviour needing no reorientation — but it was not; see below.

**RIV was the obvious candidate and it is the wrong cell.** It innervates ventral body
muscle and nothing else (9 contacts ventral, 0 dorsal) and is 25% more active during
reversals, so it was given authority in all three places a gain can go. All three fail, and
`tools/omega.py` measures why: over 180 s, **0.5% of RIV's output variance is explained by
the direction state and 99.5% is the undulation it rides on**. A gain on RIV amplifies the
gait two hundred times harder than the turn signal.

That diagnosis named the replacement. The driver must have reversal-locked variance, and in
the animal the turn is not part of the reversal — it *follows* it, firing as forward
locomotion resumes. So the signal is **an edge, not a level**: on the backward-to-forward
transition a transient is injected into the head motor pool and decays over ~1.5 s, and the
undulation carries the resulting bias down the body as a turn.

Two further things had to be right, and both are lessons this codebase keeps relearning.

- **It has to be a differential.** Driving the ventral pool alone saturates it without
  bending the animal — 400 pA pins RIV and SMDV at an activation of 0.9999 and reaches a
  mean head curvature of −0.56 /mm against an undulation of 4.5. Driving ventral *and
  releasing the dorsal antagonist* reaches −6.4. The head is antagonistic pairs
  (SMDD/SMDV, RMDD/RMDV, SMBD/SMBV) that read a difference — as the ASE pair and the
  command pools each turned out to.
- **It has to be a transient.** Held on continuously, 150 pA and above freezes the animal
  in a bent posture: the travelling index falls to +0.19 and path speed to 0.03 mm/s,
  because saturating one side of the head pool stops it oscillating. A decaying transient
  passes back through that region instead of sitting in it.

What it buys, off food: median reorientation **21° → 55°**, and **0% → 24%** of reversals
past 120°. Path speed is essentially unchanged (0.373 → 0.351 mm/s) while net speed halves
— the animal is not slowing, its track is becoming tortuous, which is what turning means.
The travelling-wave index and curvature are untouched.

The fraction of turns exceeding 120° was never fitted. Amplitude is set by the reversal's
own duration, so short reversals earn shallow turns and typical ones earn full-scale, and
the distribution falls out: about a third of reversals past 120° against the animal's ~35%.

**Downstream, all four assays now point the right way:**

| assay | before | after |
|---|---|---|
| chemotaxis index | +0.002 | **+0.070** (animal: +0.5 or better) |
| thermotaxis | warm group did not turn round | **−2.96 mm towards cooler**, correctly |
| aerotaxis | ascended the gradient | **descends it**, 16.5% → 14.2%, reaching 9.8% |
| nociception | *appeared* to work; in fact trapped the animal | **+14.7 mm further out than its own control** — see below |

None is yet at the animal's magnitude — the chemotaxis index is seven times short — so this
opens the problem rather than closing it.

### The turn that flew in circles

The omega turn described above bent the animal **the same way every time** — every turn was
ventral by construction, so heading changes accumulated instead of cancelling. On a lawn,
where reversals are most frequent, the animal rotated at **+17.4 deg/s, a full circle every
twenty seconds**, with net-to-path 0.18. It hid off food, where reversals are half as
frequent and the drift reads as noise.

The bias is not what is wrong — the turns are too shallow for it. A real omega turn is
160–170°, and at that depth it hardly matters which way the animal bends: it ends up
reversed either way. Ours are 50–100°, where ventral and dorsal differ by a hundred degrees.

Making the direction ventrally-biased-but-not-exclusive is a clean win:

| | before | after |
|---|---|---|
| on-food net/path | 0.149 | **0.332** |
| chemotaxis index | +0.070 | **+0.083** |
| nociception, exposed/clear | 5.15 / 0.34 | **7.25 / 0.46** |

**A correction to the section above:** the reorientation figures first reported for the
omega turn — 55.5° median, 24% above 120° — were inflated by this circling, because the
measure compares mean heading two seconds either side of a reversal and the spiral lands
inside that window. The honest figure is 37.7° off food against a pre-omega baseline of
21.1°. The turn still nearly doubles reorientation; it reaches 120° much less often than
first claimed.

### The sensory route for food, built and switched off

Food should suppress reversals, and doing it by shifting the shared decision boundary costs
every other behaviour (below). The requirement is a signal that exists *only* on food.
Serotonin already is one — +0.013 off food against +0.160 on it, since NSM is driven by
bacteria at the nose rather than the diffusible attractant. What was missing was a route to
the command layer, and there is no synaptic one: **CEP, ADE, PDE and NSM make zero contacts
onto AIY, AIB or AVA** in this reconstruction.

So it goes through the wireless layer as a **MOD-1-style serotonin-gated chloride
conductance** — a conductance, not a current, so it shunts and saturates like the real
channel. AIB, where MOD-1 actually is, does not carry: the channel silences AIB perfectly
(−20 → −45 mV) and reaches RIM, but AVA moves 0.584 → 0.572 and the command difference not
at all. On the command pool itself it works — on-food reversals 6.45 → 2.85/min, and a
**pirouette ratio of 1.58**, the best this model has produced; every other configuration
measured before the GluCl opponency work sat within noise of 1 (the shipped wiring now
reads 0.87 paired — see *What it does not get right*).

It ships at zero anyway, because the chemotaxis index falls +0.083 → +0.014 with it on. A
better mechanism and a worse outcome: the reversals being suppressed are the same ones
carrying the taxis. Until the omega turn reorients as deeply as the animal's, spending
reversals costs more than biasing them gains — which says exactly what to do next.

### The correction: nociception never worked either — and then the fix for it

Nociception was the one behaviour this project claimed was sound, and it was not. The assay
scored the **mechanism** — more reversals while exposed than while clear, and a lower
concentration at the end than at the start — and both were comfortably true. Neither is
avoidance. An animal wanders away from anywhere given two minutes, so "ended up further out
than it started" is diffusion unless you run the control, and there was no control.

With one — the same animal, same seed, on plain agar:

| | plain agar | with the drop | |
|---|---|---|---|
| final distance | 19.35 mm | **9.83 mm** | worse |
| furthest reached | 22.50 mm | **11.25 mm** | worse |
| time to clear 8 mm | 22.3 s | **438 s** | worse |
| cleared 8 mm at all | 12/12 | **7/12** | |

The drop did not repel the animal. **It trapped it.** ASH raised the reversal rate, a
reversal reorients by 38°, so the animal retraced the path it came in on. A stimulus that
raises the reversal rate is a stimulus that pins the animal in place — reversals are a
brake, not an escape.

**What fixed it was not turn depth.** The repellent was sensed **tonically**, on absolute
concentration, while every other chemical sense here adapts. This repo had already learned
that lesson once, with oxygen, where a purely tonic sense made the taxis point backwards.
Giving ASH the same treatment — an adapting baseline, a tonic term plus a derivative term
on the deviation, structurally identical to the oxygen path — turns the sign of the result
over. Same 12 paired seeds:

| | plain agar | with the drop | paired difference | |
|---|---|---|---|---|
| final distance | 19.35 mm | **34.02 mm** | +14.67 [+8.04, +21.06] | better |
| furthest reached | 22.50 mm | **34.38 mm** | +11.88 [+6.14, +17.43] | better |
| time to clear 8 mm | 22.3 s | 20.2 s | −2.0 [−5.5, +1.4] | no effect |
| cleared 8 mm at all | 12/12 | **12/12** | | |

Read that carefully, because it is not the result the old assay was reaching for. The
animal does not get out **faster** — time-to-clear is unchanged, and the interval says so.
It gets out **further, and stays out**. Heading into the drop, the derivative term is
positive and drives ASH; heading out of it, the same term is negative and *suppresses*
ASH, so the animal does not turn round and wander back in. That asymmetry was the whole
mechanism when it was measured; the escape has a second half now — the phasmids sense the
same repellent at the tail on their own baseline, with PHB's synapses onto AVA answering
in chloride, so danger *behind* the animal no longer out-commands danger ahead of it
(a +0.714 mV wrong-way dAVA before the correction, +0.070 after; the provenance is at
`NeuralParams.glucl_pre`). Both halves are invisible to a tonic sense, which by
construction cannot tell the two directions apart.

It also inverts the mechanism panel the old assay was proud of: reversals while exposed are
now 0.22/min against 0.58/min while clear, a difference whose interval spans zero. Fewer
reversals while exposed is what a working differential sense looks like, because most of
the exposed time is now spent leaving. The behaviour got better as the number the old assay
scored got worse, which is the argument for scoring outcomes against a control rather than
scoring mechanisms.

This is the first sensory behaviour in the model to clear its own control. The other three
are still waiting on turn depth.

### On food, and a bound that was missing

On a lawn the animal used to spend **57% of its time reversing** — 10 commanded reversals a
minute against the animal's 0.7–1.25, net-to-path 0.05. It thrashed in place, and no gait
metric showed it, because the wave was fine the whole time.

The direction gate is a Schmitt trigger, and a modulator adds to its 50/50 point with
nothing bounding how much. On a dense lawn the serotonergic turn bias reached **+0.103
against a hysteresis of 0.09**, lifting *both* thresholds above the resting command
difference: the trigger became a one-way latch the animal could not climb out of. Keeping
the shift inside the hysteresis is exactly the condition for the window to keep straddling
the operating point — a structural invariant, now asserted in a test on the lawn that broke
it. Time reversing falls 57% → 17%, net/path 0.052 → 0.149.

**But one number is serving two masters**, and that is the more interesting finding:

| bound | chemotaxis CI | aerotaxis end | nociception /min | on-food rev/min |
|---|---|---|---|---|
| 0.05 | −0.021 | 20.6% wrong | 1.32 | 2.22 |
| **0.30** | **+0.070** | **14.5% right** | **5.15** | 7.79 |
| unbounded | +0.070 | 14.2% right | 5.46 | 10.21 |

The reversals every taxis behaviour runs on are the same reversals that make the on-food
ethogram look wrong. Tighten the bound and the animal stops thrashing but chemotaxis
inverts, aerotaxis climbs the gradient again, nociception nearly stops. Fixing it properly
needs food to suppress reversals by a route that does not also suppress them off food — a
sensory pathway, not a global shift of a decision boundary every behaviour shares.

**And the basal slowing response was never real.** It was the thrashing, measured as lost
displacement. Searching for an honest lever found none: across descending cord drive,
proprioceptive gain, head reflex gain, motor adaptation time constant and both Morris-Lecar
ratios, the undulation frequency sits at 0.650 Hz in *every one*, and path speed varies by
at most 13% — consistent with the animal already being at 100% of its mechanical ceiling.
Since speed is f × λ × (U/V) and f is pinned, the only route is a shorter wave, which does
work (79% of off-food speed) but halves the chemotaxis index. It is implemented, measured,
and left at zero.

### What it does not get right

Stated plainly, because a simulation that oversells itself is worse than useless.

- **The animal crawls at 0.309 mm/s where the table says 0.219, and the frequency target
  it is also scored against is not reachable with either.** A travelling wave of frequency
  *f* and wavelength *L* runs along the body at *V = f·L*, and an inextensible body in a
  viscous medium cannot advance faster than its own wave — *U/V* < 1 strictly. The 0.219 is
  Ramot et al.'s; the 0.30 Hz and 0.65 L are Fang-Yen et al.'s; together they need
  *U/V* = 1.12, above the bound. They are different experiments under different conditions
  and no animal satisfies all three.

  Measured at the agar anisotropy of 40 that Berri et al. report, the mechanics here cap
  *U/V* near **0.50**. So 0.30 Hz with a 0.65 L wavelength implies at most 0.099 mm/s, and
  0.219 mm/s implies about 0.66 Hz.

  The model is at *U/V* ≈ 0.54 — that is, **it now extracts essentially all the thrust a
  sinusoidal wave of its own kinematics allows**, so speed is no longer a waveform problem.
  It overshoots 0.219 because its wave is a little fast and a little long: at *U/V* ≈ 0.5,
  0.219 mm/s wants *f·L* ≈ 0.44 and the model sits at 0.57.
- **The tap-withdrawal reflex does not work, so the memory below has nothing to act on.**
  Forward progress over the three seconds after a tap is +0.739 mm against +0.786 with no
  tap. The animal now reverses spontaneously — 4.67 times a minute in episodes of 0.69 s,
  against 3.2–3.5 a minute lasting 1–4 s in a real worm — but a tap is not enough to
  trigger one: it moves the command difference about 0.53 of a standard deviation against
  the 1.33 it would need.

  The remaining gap is the touch pathway rather than the decision. In this reconstruction
  anterior touch makes 12 chemical and 2 gap contacts onto the entire backward command
  pool, against 27 chemical contacts onto the *forward* one — ALM and AVM drive AVB harder
  than they drive AVA. That is a wiring fact and it deserves checking against a newer
  reconstruction before anything is tuned around it.

- **Chemotaxis is biased the right way and still gets nowhere.** The pirouette ratio —
  reversals while conditions worsen over reversals while they improve, the quantity
  Pierce-Shimomura's mechanism is made of — sits at 1.24, above the 1 that separates
  chemotaxis from its absence. The index is +0.002 and no animal in sixteen approached the
  source. The animal covers plenty of ground now (24 mm in 200 s); it simply has no net
  bias about where.

  The reason was measured, and the correction ships. `Senses` gives ASEL +dC/dt and ASER
  −dC/dt, a genuine opponent pair, but both projected onto AIY — 19 contacts against
  16 — with the same sign, so AIY received (+dC/dt) + (−dC/dt) and the opponency died at
  the first synapse. The shipped model now answers the ON cells' glutamate with chloride
  (`NeuralParams.glucl_pre`: ASEL/AWA/PHB onto AIY/AVA/AIB, adopted in two measured
  steps), which turned the sign right at AIY and then killed the second wrong-way route,
  ASE → AIB → RIM: with ASEL → AIB inhibitory, both conditional rates move correctly at
  once and the paired ratio reads 0.52 → 0.87. Still the wrong side of 1, and the
  outcome — index, approach — is unmoved against ±20 mm of per-seed wander: the
  mechanism is right and roughly a hundredfold short of biasing the walk, the same
  magnitude gap as everywhere in the second tier.

- **Aerotaxis still underperforms its wiring.** The first reading was "does not work at
  all" — 20.9% oxygen occupied against an ambient 21%, where N2 prefers 5–12% — despite
  URX/AQR/PQR making 44 contacts onto the backward command pool. Oxygen sensing has both
  its edges now (URX the level and upshift, BAG the downshift), and the border behaviour
  is real but thin: at a lawn's oxygen dent the routed animal turns nearly twice as often
  and wanders less far, but the dwell gain is carried by 2 of 8 seeds
  (`tools/bag_border.py`). The turn the circuit asks for is shallower than the animal's;
  the ceiling is turn depth, not the sensor.

- **The gait's step dependence was a coupling bug, not a numerical one, and the previous
  entry here was wrong.** `BodyParams.dt` was documented as "shared with the neural step"
  and was shared with nothing: `Body` kept its own timestep, `Simulation` used
  `NeuralParams.dt`, and changing the latter left the body advancing 0.5 ms per call while
  the rest of the animal believed otherwise. At dt = 0.125 ms the body ran four times fast
  relative to its own nervous system, and every convergence measurement made here was
  measuring that.

  With the two synchronised, the frequency sits at 0.44–0.45 Hz across a sixteen-fold range
  of step size, curvature r.m.s. at 4.3–4.8 and the travelling index at 0.59–0.68 — where
  before, every fine-step run collapsed to 0.13–0.20 Hz with a 2–6 L wavelength. The claim
  that "integrated accurately this reflex chain does not produce C. elegans locomotion" is
  withdrawn.

  What remains is real and smaller: the frequency's seed-to-seed spread is 0.008 Hz at most
  step sizes and 0.14 Hz at two of them. That is the gait bistability this project has
  documented since day two, it is a property of the model rather than of the integrator,
  and characterising it wants more than the three seeds used here.

- **Ablating AVB halves forward locomotion rather than abolishing it.** In a real worm
  losing the forward command interneurons ends forward movement; here it removes about
  half of it, because the head reflex propels the animal on its own and is untouched by
  the ablation. That share grew when the head delay went in. It is a fair measure of how
  much of the gait the command layer actually commands, and it is guarded by a test.

- **Backward locomotion is known-poor and should not be cited as working.** Clamping AVB
  hyperpolarised correctly hands the cord to the A-class backward generator and the wave
  does reverse, but curvature r.m.s. goes to 7.5 and net speed to 0.018 mm/s. The intrinsic
  gate offsets are placed relative to a resting potential solved with AVB intact and do not
  follow it down when the drive is removed.

  The reading that used to accompany this — that the wavelength is insensitive to the
  proprioceptive reach, and therefore that the body wave is a passive mechanical response
  to the head's bending — was measured when the wave was mostly standing and does not
  survive. With a travelling wave, reach is the one thing that *does* set the wavelength:
  0.49 to 0.64 L as reach goes 0.08 to 0.30, with the frequency flat to within 1% across
  the same range.
- **Gait modulation points the right way now, and is far too small.** 0.66 Hz on agar
  against 0.85 Hz in buffer, where the animal goes 0.30 Hz crawling to 1.76 Hz swimming.
  The *sign* had been wrong since day two and is now right; the magnitude is a 29% change
  where the animal manages sixfold. What fixed the sign was removing a reversal flicker in
  the command layer, not any change to the mechanics — which is worth knowing, because the
  mechanics had been the suspect for eight days.
- **The travelling-wave index is +0.87, against +0.996 for the same body driven by a
  prescribed perfect wave.** That control is the useful one: it says the mechanics can
  carry a wave the nervous system is not yet producing, and the gap between +0.87 and
  +0.996 is what the circuit still owes. Decomposing curvature over (time, arclength)
  separates the travelling component from the standing one, and a standing wave produces
  *exactly zero* net thrust however large its amplitude, which is why this is the measure
  worth watching rather than the amplitude.

- **The speed figure in this file was once twenty times too high**, and the reason is
  worth keeping. `sim.speed` used to smooth the *magnitude* of instantaneous centroid
  velocity, which counts the side-to-side slosh of the centroid within each undulation
  cycle as though it were forward progress. The two quantities are now kept separately --
  `sim.speed` is net displacement over a two-second window, the way a worm tracker
  measures it, and `sim.path_speed` is the old path-length one -- and the tests assert on
  the honest one. Credit where due: this was caught by someone simply watching the
  animation and saying it looked like it was wiggling in place.
- **The head reflex loop has two stable limit cycles**, near 0.3 Hz and near 2.2 Hz, and
  before the stretch receptor was given its own kinetics, which one the animal fell into
  depended on the random seed — two thirds of seeds took the fast one. The receptor filter
  removes the fast attractor and makes the gait reproducible (1.17–1.28 Hz across seeds,
  which `test_gait_is_reproducible_across_seeds` now enforces). It is worth knowing that
  the slow attractor, when it was reachable, sat at 0.31 Hz with a 0.70 L wavelength —
  almost exactly the real crawling gait. Making *that* one the robust attractor is the
  obvious next thing to try.
- **Motor neurons saturate** at the extremes of each cycle under proprioceptive drive.
  This is arguably correct — Boyle et al. make their B-type neurons frankly binary — but
  it means their voltages are not quantitatively meaningful at the extremes.
- **Two parameters are fitted rather than measured**, and they are the model's largest
  free quantities. The stretch-receptor gain, which Boyle et al. also fit — theirs differs
  by a factor of 1.86 between their own paper and their own code — and `head_delay`, a
  0.60 s transport delay in the head reflex which is what brings the undulation frequency
  into the animal's band. Nothing that slow exists in a real stretch receptor; see the note
  on it in `params.py` for what it is standing in for and why it has not been earned yet.
- **No defecation cycle.** Pharyngeal pumping and egg laying now work — see below — but
  the defecation motor programme, which is one of the animal's other two rhythms, is absent.
- **Egg-laying overshoots its own ablation phenotype.** HSN-ablated animals here lay
  *nothing*; the real ones are egg-laying defective but not incapable. Retention and
  bloating are right, the residual rate is not, and it is structural rather than a bad
  constant: with HSN gone the vulval muscle spans four hundredths above its median and
  never comes within 0.05 of threshold, so no value produces a graded regime. It needs
  stochastic vulval-muscle calcium, which the model does not have.
- **Two dimensions.** Left and right muscle quadrants merge, so no roll and no true
  three-dimensional omega turn.
- **The connectome is one animal.** White et al. sectioned a single hermaphrodite in 1986;
  contact counts vary several-fold along the body partly for reconstruction reasons.


---


## The dish

A 50 mm plate with bacterial lawns, each the centre of both a diffusible attractant
gradient and an oxygen depression, because bacteria respire. A linear thermal gradient runs
across it. There are obstacles, and a drop of something noxious. The worm eats what it
walks over, which slowly erases the gradient that led it there.

That last sentence was aspirational until #48. Eating moved the food array and nothing
else, so a lawn grazed to bare agar went on smelling and respiring exactly like a full one
— an animal could chemotax towards food that was not there, indefinitely. Both fields are
the steady state of `D ∇²c = λc` away from a finite source, and that equation is *linear in
the source strength*, so a lawn with fraction `f` of its bacteria left sources `f` of the
field with an unchanged shape. Each patch now caches its shape and is scaled by `f`.
Oxygen is not transported here: the depression is solved from the standing mass rather than
stepped, because `o2_length_scale` already *is* oxygen's diffusion length — 5 mm is how far
it spreads in before respiration consumes it. `WorldParams` has no `diffusion_oxygen` for
that reason; it named the same physics twice and was read by nothing. The attractant does
diffuse, so it is relaxed towards what the standing bacteria emit; an intact lawn sources
exactly what decays and is left alone to the bit, which is what keeps every result measured
on a full plate meaning what it did.

Sensory transduction is routed to the neurons that actually carry it, and where the biology
is asymmetric so is the model: ASEL and ASER are a matched ON/OFF pair (ASEL depolarises
when attractant concentration rises, ASER when it falls); AWC is an OFF cell, silenced by
odour and firing on its removal, beside AWA, the ON cell; ASH/ADL/ASK carry the repellent
at the nose and PHA/PHB — the phasmids — carry the same repellent at the tail, so escape
*direction* is a head-versus-tail comparison (Hilliard 2002); AFD is a warm receptor above
the cultivation temperature; URX/AQR/PQR report the oxygen level and its upshift and BAG
the downshift (Zimmer 2009 — the two edges of one signal, split between carriers as the
biology has it); ALM/AVM and PLM carry anterior and posterior touch, OLQ/FLP/CEP the nose
touch; the eight dopaminergic neurons sense the bacterial lawn mechanically and NSM tastes
it in the pharynx; and RIS, driven by the satiety homeostat, puts the animal to sleep
through its own GABAergic wiring and FLP-11 (`worm/sleep.py`). Most channels adapt,
because sensation is largely differential — a worm sitting in a uniform concentration
stops responding to it within seconds — with deliberate tonic exceptions the parameters
document (the repellents, oxygen, touch, food).

---

## Performance, threading and genomes

It runs at roughly real time on one core — 0.57 ms of wall time per 0.5 ms step. Measured
by subsystem, that is 27% sensory, 26% body mechanics, 19% nervous system, 7% muscle; of
the sensory share, more than half is sampling the world's chemical fields. Eight concurrent
trials is where this machine stops scaling (8 cores at 84% efficiency, 12 at 62%), so a
long sweep is bounded by about 11,800 steps per second in aggregate however many workers
it is given.

Population and parameter-sweep drivers should pin BLAS before importing NumPy. The
302-by-302 resting-potential solve is too small to repay a large BLAS thread team's startup
cost, and some OpenBLAS builds make each `Simulation(...)` hundreds of milliseconds slower:

```python
from worm.threads import pin_blas_threads
pin_blas_threads(1)

import numpy as np
from worm.engine import Simulation
```

This is opt-in so importing `worm` never changes an application's threading policy.

Python genomes live in `worm/genome.py`. `flatten(params, mutable_only=True)` returns the
ordered, bounded genes; `unflatten(values, base=params, mutable_only=True)` validates them
and returns a new frozen parameter tree. Reconstruct a `Simulation` from that tree: existing
simulations have already captured their subsystem parameters and are not updated by
assigning `sim.p`.

---

## Evolved animals are not C. elegans

`wasm/evolve.mjs` runs populations under selection, and everything that comes out of it
sits on the other side of a line from everything else in this document.

The rest of the project is a reconstruction. The wiring is anatomy — 7,000 synapses traced
out of electron micrographs — and the constants that have been measured are treated as
facts: membrane capacitance, reversal potentials, bending modulus, drag. `tools/optimise.py`
opens by saying that fitting the connectome would throw away the entire point of building
the model on it, and that is the project's founding constraint rather than a preference.

Selection does not respect that constraint. It optimises the model, and the model includes
its own defects — a unit conversion in front of the fitness measure was worth nine times the
score at an unchanged trajectory (#37), and an animal with a legal-but-tiny bending stiffness
folds itself past what the discretisation can represent. So an evolved lineage is a statement
about *this simulator*, and about what its scoring function rewards. It is not evidence about
the animal, and it cannot become evidence about the animal by being interesting.

Three things follow, and they are the whole convention:

1. **Results from an evolved population never feed a claim about *C. elegans*.** Not in
   `README.md`, not in `NEXT.md`'s measurements, not in an issue. If a number is quoted
   about the worm, it came from the unevolved baseline.
2. **Conformance and the assay suite guard that baseline, and nothing guards an evolved
   one.** `tools/conform.py` checks the port reproduces the Python; the assays check the
   Python reproduces measurements on live animals. Neither has any purchase on a genome
   that has been selected away from the reconstruction.
3. **The label travels with the numbers, not with the document.** `evolve.mjs` prints it
   above its own results, because results get pasted and documents do not.

None of this is an argument against doing it. A population that finds an exploit has found
a real defect, and that is worth knowing — `EVO_FITNESS=eaten` is kept for exactly that,
as an adversarial probe rather than a default. It is an argument for keeping the two kinds
of claim in separate boxes, which is cheap now and impossible to do retroactively.

**Three measures exist, and two of them are there to be argued with.**

| `EVO_FITNESS` | what it scores | what it is for |
|---|---|---|
| `energy` (default) | intake in pump-volumes, less a locomotion cost | the honest one; #37's exploit costs fitness under it rather than paying |
| `eaten` | raw intake | adversarial probe. Exploitable on purpose, kept to find defects |
| `eggs` | eggs produced, normalised by `eggs_per_food` | **measured to be intake in different units** — see below |

That last row is the useful kind of negative result. `laid + held` is *conserved* across a
laying event, so eggs produced is blind to the egg-laying circuit by construction and tracks
feeding alone: score divided by intake is 5.000000e-3 across three seeds, a relative spread
of 4.2e-11. `wasm/eggs-fitness.test.mjs` keeps that attached to the measure and prints the
verdict, so nobody quotes a number out of it without it.

The probe has been run, and it found nothing — which is not the same as there being nothing.
Selection minus control over three seeds was 0.032 ± 0.022, which does not clear twice its
own standard error, so the run could not detect selection at all and therefore had no
sensitivity with which to detect an exploit either. A probe that cannot see the thing it is
a control for is not evidence of absence. What it bought is a price for the real experiment,
which `NEXT.md` records.
