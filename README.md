# celegans-sim

> Not affiliated with the [OpenWorm](https://openworm.org) project. It uses connectome data
> that OpenWorm publishes, and owes a lot to the modelling literature they have gathered,
> but none of the code here is theirs and none of the results are their responsibility.

A *Caenorhabditis elegans* simulated from its connectome down: 302 graded-potential
neurons wired by the reconstructed synapse-by-synapse anatomy, driving 95 individually
simulated body-wall muscle cells, driving an inextensible body in a viscous medium at
zero Reynolds number, inside a petri dish with food, chemical gradients, a thermal
gradient and obstacles. Plus a browser front end to watch it in.

The worm is the project. The web app is a media player for it.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sh tools/fetch_raw.sh                      # downloads the anatomy, ~600 kB
.venv/bin/python tools/build_dataset.py    # -> data/celegans.json
.venv/bin/python run.py
```

Then open <http://127.0.0.1:8080>. Also useful:

```bash
.venv/bin/python run.py --headless 60      # 60 simulated seconds, no viewer
PYTHONPATH=. .venv/bin/python tools/kymo.py            # ASCII kymograph
PYTHONPATH=. .venv/bin/python tools/diagnose_loop.py   # gait metrics
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

It runs at roughly real time on one core — 0.57 ms of wall time per 0.5 ms step. Measured
by subsystem, that is 27% sensory, 26% body mechanics, 19% nervous system, 7% muscle; of
the sensory share, more than half is sampling the world's chemical fields. Eight concurrent
trials is where this machine stops scaling (8 cores at 84% efficiency, 12 at 62%), so a
long sweep is bounded by about 11,800 steps per second in aggregate however many workers
it is given.

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

One thing here remembers. Every other state variable forgets on purpose: the sensory
adaptation filters exist to discard the past, and the modulators integrate over tens of
seconds and then decay. The mechanoreceptor carries a depleting resource — repeated taps
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

## Does it behave like a worm?

`pytest tests/` — 38 tests, of which these are the load-bearing ones. Reference values are
measurements on live animals; the model column is the mean and spread over five seeds from
a single run of `tools/scorecard.py`, so every row describes the same animal. It has not
always: this table once quoted a crawling speed from day two beside a frequency from day
nine.

| Quantity | Model | Measured | Source |
|---|---|---|---|
| Curvature, r.m.s. | **4.51 ± 0.11 /mm** | 4.3 ± 0.3 /mm | Krajacic et al. 2012 |
| Curvature, peak | **12.2 ± 0.1 /mm** *(sharp)* | 9.8 ± 1.1 /mm | Krajacic et al. 2012 |
| Wave direction | **head → tail** | head → tail | — |
| Muscle resting potential | **−31 to −24 mV** | −25.0 ± 1.0 mV | Gao & Zhen 2011 |
| Resting potentials | **−62 to −12 mV** | −75 to −25 mV | several, see `params.py` |
| Swimming efficiency U/c | **0.076** | 0.08 ± 0.01 | Shen et al. 2012 |
| Neuron count / classes | **302 / 118** | 302 / 118 | canonical |
| GABAergic neurons | **26** | 26 | McIntire et al. 1993 |
| Crawling speed (net) | **0.275 ± 0.047 mm/s** | 0.219 ± 0.029 mm/s | Ramot et al. 2008 |
| Net displacement / path | **0.75 ± 0.10** | well above 0.5 | — |
| Travelling-wave index | **+0.85 ± 0.03** | +1 for a pure travelling wave | — |
| Undulation frequency, agar | **0.67 ± 0.01 Hz** | 0.30 ± 0.02 Hz *(see below)* | Fang-Yen et al. 2010 |
| Wavelength, agar | **0.83 ± 0.01 L** *(long)* | 0.65 ± 0.03 L | Fang-Yen et al. 2010 |

Curvature, wave direction and the membrane potentials land on the measured values. The
gait's *timing* does not: see below.

The mechanics are verified independently of the biology: the assembled drag metric matches
direct Gauss-Legendre quadrature of the integral it stands for to 2×10⁻¹⁶ relative, it is
positive definite, body length is conserved to 10⁻¹² over the full closed loop, a passive
bent worm relaxes straight with monotonically decreasing bending energy, and driving the
body with a prescribed travelling wave reproduces the Gray-Hancock slip law to within 3.3%
across a 25-fold range of drag anisotropy.

The nervous system's noiseless fixed point holds to 4×10⁻¹⁴ mV over two simulated seconds,
which is a sharp check that the self-consistent threshold solve and the integrator agree.

### What works

**Nociception.** Dropped near a repellent the animal reverses 3.81 times a minute while
exposed against 1.72 while clear, and leaves: the concentration it sits in falls from 0.264
to 0.027 over two minutes. That is avoidance — a sensory signal changing behaviour in the
right direction, with no part of it scripted.

**Habituation.** Repeated taps deplete a mechanoreceptor resource, rest refills it, and a
shorter interval habituates deeper — three properties of Rankin's tap habituation out of
one equation rather than three fits, and integrated exactly so how much the animal learns
does not depend on the timestep.

**Spontaneous reversals**, at 3.3 a minute against the animal's 3.2–3.5 off food, in
episodes long enough to be reversals rather than threshold flicker.

### The one thing missing that explains most of the rest

**The animal reverses but does not reorient.** Median heading change across a reversal is
23°, and not one of 53 measured exceeded 120°; a real animal ends about 35% of its
reversals in an omega turn of 160–170°.

A biased random walk steers by choosing *when* to change direction, so if changing
direction does not change the direction there is nothing to bias. The animal reverses along
the axis it arrived on and retraces its path. That is why three separate assays report a
correct mechanism and a null outcome — chemotaxis with a pirouette ratio of 1.24, aerotaxis
with the turning bias measurably the right way round, thermotaxis moving the cold group
correctly — while nociception, the one behaviour that needs no reorientation, works.

Omega turns are therefore not a refinement to add later; they are the missing half of the
steering. Whether they are achievable at all in a two-dimensional model is the first
question, since the real turn is a deep ventral coil.

**RIV was the obvious candidate and it is the wrong cell.** It innervates ventral body
muscle and nothing else — 9 contacts ventral, 0 dorsal — and it is 25% more active during
reversals, so it was given authority in all three places a gain can go. All three fail, and
`tools/omega.py` measures why: over 180 s, **0.5% of RIV's output variance is explained by
the direction state and 99.5% is the undulation it rides on**. A gain on RIV therefore
amplifies the gait two hundred times harder than the turn signal, which is exactly the
observed trade — median reorientation climbs 18° → 55° without ever reaching 120°, while
net speed falls by four fifths and the travelling-wave index goes +0.84 → +0.74.

The driver has to be something whose variance *is* reversal-locked, and in the animal the
turn fires at the reversal-to-forward *transition* rather than during the reversal — an
edge-locked transient, not a gain on a tonically oscillating motor neuron. That version
makes two predictions the animal also makes: the turn follows the reversal, and longer
reversals end in deeper turns.

### What it does not get right

Stated plainly, because a simulation that oversells itself is worse than useless.

- **The animal crawls at 0.275 mm/s where the table says 0.219, and the frequency target
  it is also scored against is not reachable with either.** A travelling wave of frequency
  *f* and wavelength *L* runs along the body at *V = f·L*, and an inextensible body in a
  viscous medium cannot advance faster than its own wave — *U/V* < 1 strictly. The 0.219 is
  Ramot et al.'s; the 0.30 Hz and 0.65 L are Fang-Yen et al.'s; together they need
  *U/V* = 1.12, above the bound. They are different experiments under different conditions
  and no animal satisfies all three.

  Measured at the agar anisotropy of 40 that Berri et al. report, the mechanics here cap
  *U/V* near **0.50**. So 0.30 Hz with a 0.65 L wavelength implies at most 0.099 mm/s, and
  0.219 mm/s implies about 0.66 Hz.

  The model is at *U/V* = 0.49 — that is, **it now extracts essentially all the thrust a
  sinusoidal wave of its own kinematics allows**, so speed is no longer a waveform problem.
  It overshoots 0.219 because its wave is a little fast and a little long: at *U/V* ≈ 0.5,
  0.219 mm/s wants *f·L* ≈ 0.44 and the model sits at 0.56.
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

  The reason is measured. `Senses` gives ASEL +dC/dt and ASER −dC/dt, a genuine opponent
  pair, but both project onto AIY with the same sign — 19 contacts against 16 — so AIY
  receives (+dC/dt) + (−dC/dt) and the opponency dies at the first synapse. Giving the ON
  cell a glutamate-gated chloride channel and the OFF cell not makes them push the same
  way and the sign comes right, but the effect is 0.009 σ of the command difference where
  biasing the walk wants of order 0.1 — a hundredfold short, and not through attenuation,
  since the chain is strong at every stage.

- **Aerotaxis does not work at all**: 20.9% oxygen occupied against an ambient 21%, where
  N2 prefers 5–12%. URX/AQR/PQR make 44 contacts onto the backward command pool, more than
  any other sensory pathway, so this one should be reachable and is not.

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
- **Gait modulation points the right way now, and is far too small.** 0.67 Hz on agar
  against 0.85 Hz in buffer, where the animal goes 0.30 Hz crawling to 1.76 Hz swimming.
  The *sign* had been wrong since day two and is now right; the magnitude is a 27% change
  where the animal manages sixfold. What fixed the sign was removing a reversal flicker in
  the command layer, not any change to the mechanics — which is worth knowing, because the
  mechanics had been the suspect for eight days.
- **The travelling-wave index is +0.61, against +0.996 for the same body driven by a
  prescribed perfect wave.** That control is the useful one: it says the mechanics can
  carry a wave the nervous system is not yet producing, and the gap between +0.61 and
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
- **No pharyngeal pumping, no egg laying, no defecation cycle.** The 20 pharyngeal neurons
  are simulated but drive nothing.
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

Sensory transduction is routed to the neurons that actually carry it, and where the biology
is asymmetric so is the model: ASEL and ASER are a matched ON/OFF pair (ASEL depolarises
when attractant concentration rises, ASER when it falls); AWC is an OFF cell, silenced by
odour and firing on its removal; AFD is a warm receptor above the cultivation temperature;
URX/AQR/PQR report oxygen; ALM/AVM and PLM carry anterior and posterior touch; the eight
dopaminergic neurons sense the bacterial lawn mechanically. Every channel adapts, because
sensation is differential — a worm sitting in a uniform concentration, however high, stops
responding to it within seconds.

## The viewer

`web/` is a single page with no build step and no dependencies. Telemetry is packed
float32 over a WebSocket at 30 Hz — 302 voltages, 302 activations, 95 muscle tensions, the
body outline and the curvature profile, about 3 kB a frame. The chemical fields are larger
and change slowly, so they go separately as downsampled 8-bit images every two seconds.

Four views: the dish, with the worm coloured by local curvature and a minimap; all 302
neurons ordered head to tail and coloured by activation, hover for identity and click to
plot; the four muscle quadrants; and a scrolling curvature kymograph. Transport controls
change the medium under the animal live, poke it at either end, and drop new food where you
click.

Colour follows a validated data-visualisation palette: one sequential hue for magnitudes
(activation, tension), and the diverging blue-red pair with a neutral grey midpoint for
signed curvature, so "straight" reads as nothing rather than as a colour.

## Layout

```
worm/params.py      every tunable constant, with its provenance and its unit
worm/dataset.py     loads the built connectome into numpy
worm/nervous.py     302 graded neurons
worm/muscle.py      95 body-wall muscle cells and their bending moment
worm/body.py        the elastica and resistive force theory
worm/world.py       dish, food, chemical fields, obstacles
worm/senses.py      sensory transduction and proprioception
worm/engine.py      the closed loop
worm/server.py      WebSocket telemetry and static file serving
tools/build_dataset.py  raw anatomy -> validated dataset, assertion-heavy
tools/kymo.py           ASCII kymograph — the fastest way to see what the body is doing
tools/diagnose_loop.py  frequency, wavelength, phase and antagonism metrics
tools/command_probe.py  what each input is worth to the forward/backward decision
tools/command_sweep.py  behavioural and locomotor scores side by side, for the command layer
tools/ethogram.py       reversal rate, run lengths and reorientation, off food and on
tools/assays.py         chemotaxis, aerotaxis, thermotaxis, nociception
tools/calibrate_body.py mechanics checks, independent of the biology
tools/timestep_convergence.py  is the gait converged at the step size it runs at?
tools/head_mode.py      which of the head loop's limit cycles the animal lands in, and why
tools/habituation.py    tap habituation — decrement, interval dependence, recovery
tools/loop_phase.py     open the head loop and measure each stage's gain and phase
tools/wave_speed.py     what sets the wavelength and the frequency
tools/body_oscillator.py  can the body carry the rhythm instead of the head?
tools/head_circuit.py   lumped against distributed head reflex, scored on the wave
tools/thrust.py         what speed the mechanics allow, and what the circuit collects
tools/ase_opponency.py  which way round the ON and OFF chemosensors should push
tools/omega.py          can the omega turn be bought by amplifying RIV? (no, and why)
tools/scorecard.py      every headline number at once, across seeds, in three media
```

## Data and licensing

The code is MIT (see `LICENSE`). The anatomical data is not mine and is not redistributed
here: `tools/fetch_raw.sh` downloads it from the original hosts, and `data/raw/` is
gitignored. What *is* committed is `data/celegans.json`, the derived dataset, which records
the SHA-256 of every input it was built from so you can check that your download matches
the one these results came from. Re-derive it yourself with `tools/build_dataset.py` if you
would rather not take my word for it.

If you use the anatomy, cite the people who spent years producing it — White, Southgate,
Thomson & Brenner (1986), Chen, Hall & Chklovskii (2006), Cook et al. (2019), and WormAtlas
— not this repository.

## Sources

Connectome and anatomy: White et al. 1986 and Chen, Hall & Chklovskii 2006, via the
OpenWorm c302 distribution; WormAtlas soma positions; Cook et al. 2019 (used to
cross-validate the muscle roster). Neuron model: Wicks et al. 1996; Kunert et al. 2014;
Liu et al. 2018. Mechanics: Boyle, Berri & Cohen 2012; Fang-Yen et al. 2010; Berri et al.
2009; Gray & Hancock 1955. Proprioception: Wen et al. 2012; Yeon et al. 2018. Transmitters:
McIntire et al. 1993; Beg & Jorgensen 2003; Gendrel, Atlas & Hobert 2016. Full citations
are inline at the point each number is used, in `worm/params.py`.
