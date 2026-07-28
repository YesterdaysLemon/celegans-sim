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

`pytest tests/` — 33 tests, of which these are the load-bearing ones. Reference values are
measurements on live animals.

| Quantity | Model | Measured | Source |
|---|---|---|---|
| Curvature, r.m.s. | **2.4 /mm** | 4.3 ± 0.3 /mm | Krajacic et al. 2012 |
| Curvature, peak | **12–14 /mm** | 9.8 ± 1.1 /mm | Krajacic et al. 2012 |
| Wave direction | **head → tail** | head → tail | — |
| Muscle resting potential | **−31 to −24 mV** | −25.0 ± 1.0 mV | Gao & Zhen 2011 |
| Resting potentials | **−62 to −12 mV** | −75 to −25 mV | several, see `params.py` |
| Swimming efficiency U/c | **0.076** | 0.08 ± 0.01 | Shen et al. 2012 |
| Neuron count / classes | **302 / 118** | 302 / 118 | canonical |
| GABAergic neurons | **26** | 26 | McIntire et al. 1993 |
| Crawling speed (net) | **0.095–0.106 mm/s** | 0.219 ± 0.029 mm/s | Ramot et al. 2008 |
| Net displacement / path | **0.66–0.72** | well above 0.5 | — |
| Travelling-wave index | **+0.48–0.57** | +1 for a pure travelling wave | — |
| Undulation frequency, agar | **1.2 Hz** *(fast)* | 0.30 ± 0.02 Hz | Fang-Yen et al. 2010 |
| Wavelength, agar | **1.4 L** *(long)* | 0.65 ± 0.03 L | Fang-Yen et al. 2010 |

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

### What it does not get right

Stated plainly, because a simulation that oversells itself is worse than useless.

- **The animal does not spontaneously reverse, so it has no sensory behaviour at all.**
  Zero reversals across six animals in sixty seconds each, against 3.2–3.5 per minute for a
  real worm off food. That is not a missing flourish, it is the substrate every orienting
  behaviour here is built from: C. elegans chemotaxis is a biased random walk, in which the
  animal does not steer up a gradient but suppresses turns while conditions improve
  (Pierce-Shimomura, Morse & Lockery 1999). A worm that never turns cannot chemotax however
  good its nose is, and the measured chemotaxis index is −0.014 against +0.5 or better.

  The cause is now a number rather than a suspicion. The forward/backward decision reads
  the difference between two command pools, and that difference sits **3.81 standard
  deviations** from its own decision boundary while a physiological chemosensory signal
  moves it by **0.008 of one standard deviation** (`tools/command_probe.py`). No gain
  multiplies the second into the first. The reason is structural: every command interneuron
  here is cholinergic or glutamatergic and the model collapses both to a 0 mV reversal, so
  the two pools *excite* each other — 70 reconstructed contacts one way, 33 the other, plus
  10 gap junctions — and they correlate at +0.76. Driving one drags the other along, and
  the decision reads the one component common drive cannot move. Four candidate fixes have
  been tried and refuted; the measurements are in `NEXT.md`.

- **The gait is not converged at the timestep the model ships at**, and two of the numbers
  in the table above change meaning because of it. Halving the step from 0.25 to 0.125 ms
  still moves the undulation frequency by 15% and the net speed by 17%, against a
  seed-to-seed spread of 0.03 Hz, and the trend is monotonic across a sixteen-fold range
  (`tools/timestep_convergence.py`):

  ```
     dt ms  |   freq Hz    wavelen L      TWI     k_rms   speed mm/s
     0.125  |   1.622        0.61       +0.729    2.68     0.3245
     0.250  |   1.411        0.58       +0.771    2.64     0.2770
     0.500  |   1.233        0.54       +0.764    2.30     0.1918   <- shipped
     1.000  |   1.028        0.50       +0.708    1.80     0.0899
     2.000  |   0.717        0.49       +0.524    1.42     0.0203
  ```

  Curvature amplitude is nearly converged; frequency, wavelength and speed are not. So the
  frequency discrepancy below is **worse** than stated — refine the integrator and it moves
  further from the animal, not closer — and the crawling speed agreeing with the measured
  0.219 mm/s is partly an accident of this step size, since at 0.125 ms the animal does
  0.3245 mm/s. Both are the same fact: an undulation that is too fast drives a body that
  travels too fast.

  The neurons are integrated with exponential Euler, exact for the linear part of the
  membrane equation. The body is where the error is: `Body.step` puts backward Euler on the
  constant elastic and damping matrices but evaluates the configuration-dependent drag
  metric explicitly and then takes `pos + qdot*dt`, so the mechanics are first-order, and
  the gait is a limit cycle closed through that integrator.

- **On agar it undulates at about 1.2 Hz with a 0.52-body-length wavelength.** A real worm
  crawling on agar does 0.30-0.50 Hz and 0.65 L. This is now the largest single discrepancy
  in the model, and it is mechanical rather than neural: sweeping the motor neurons'
  potassium time constant over an eighteen-fold range moves the frequency by under 5%, so
  it is set by the body and the reflex loop. Drag, internal damping and muscle activation
  kinetics are where to look.

- **Backward locomotion is known-poor and should not be cited as working.** Clamping AVB
  hyperpolarised correctly hands the cord to the A-class backward generator and the wave
  does reverse, but curvature r.m.s. goes to 7.5 and net speed to 0.018 mm/s. The intrinsic
  gate offsets are placed relative to a resting potential solved with AVB intact and do not
  follow it down when the drive is removed.

  This is one fault, not two, and it is diagnostic. The wavelength barely moves when the
  proprioceptive reach is varied over its entire plausible range (1.11 → 1.20 L as reach
  goes 0.10 → 0.20 L), and driving the head externally while measuring the body's response
  gives a per-segment reflex gain near 1.4. Together those say the body wave here is
  largely the **passive mechanical response** to the head's bending rather than a wave
  regenerated segment by segment by proprioception. The reflex loop is present, measurable
  and correctly signed — it just is not carrying as much of the wave as the animal's does,
  so the head's own timing dominates and the body strings out behind it.
- **Gait modulation runs backwards.** The medium does change the gait — 1.25 Hz on agar
  against 0.55 Hz in buffer — but the animal goes the other way, 0.30 Hz on agar and
  1.76 Hz swimming. Same root cause: with the wave set by the head's own loop rather than
  regenerated along the body, what the medium mostly changes is the mechanical load on the
  *head*, and a heavier load there shifts that loop's crossover rather than slowing the
  body's wave. `test_medium_changes_the_gait` therefore asserts that the medium matters,
  and deliberately does not assert which way, because asserting the real direction would
  be asserting something this model does not do.
- **The worm crawls at 0.172 mm/s against the animal's 0.219**, with a net-to-path ratio of
  0.86 and a travelling-wave index of +0.75. That is essentially the ceiling for this body:
  driving the identical mechanics with a *prescribed* perfect travelling wave reaches
  0.174 mm/s. Any further speed has to come from the mechanics, not the circuit.

  That index is the measure worth watching, and it is what unlocked this. Decomposing the
  body's curvature over (time, arclength) separates the travelling component from the
  standing one; a standing wave produces *exactly zero* net thrust however large its
  amplitude, because its drag forces cancel over a cycle. The model shipped at **+0.33 and
  5 µm/s** -- two thirds standing, undulating almost on the spot -- while the identical body
  driven by a clean prescribed travelling wave reaches **+0.996 and 0.174 mm/s**. So the
  mechanics were never at fault; the nervous system was producing a wave that stood still.

  Tracing the travelling index stage by stage put the fault at the motor neurons, whose
  output was a *pure* standing wave (index -0.006) — and then the phase profile showed the
  phase gradient was actually fine at every stage. The problem was amplitude: the B-type
  motor neurons were barely modulating at all, because the stretch receptor did not adapt.
  A static body bend sat on its input at six to eleven times the size of the oscillation
  riding on it, burying the signal and eating half the receptor's remaining gain — and that
  is also why the gain could never be raised before, since turning it up amplified the
  static bend into a permanent curl. High-passing the receptor, which is what every other
  sensory channel here already did, raised net displacement twenty-fold.

  Three plausible explanations were tested and refuted along the way, all recorded in
  `NEXT.md`: backing off the head reflex (makes it worse), bending stiffness (a shallow
  25% effect over a 1600-fold range, in the wrong direction), and a common oscillating
  drive broadcast by AVB through its gap junctions (that neuron swings 4 mV, and clamping
  it changes nothing).

  That left one thing the reflex model could not do at all. Xu et al. (2018) solve this
  model class analytically: in a chain where motor neurons *passively* relay proprioceptive
  input, bending amplitude must decay exponentially towards the tail, with a length constant
  that head reflex gain, muscle moment and bending stiffness can only trade against one
  another. Measured here, amplitude fell 2.5-fold head to tail and the tail's coherence —
  the fraction of its motion that belongs to the undulation at all — was 0.03. The tail was
  not undulating; it was being dragged.

  The fix was to stop the segments being passive. Each B-type motor neuron gained a
  Morris-Lecar pair (regenerative calcium, delayed potassium) sized as a fraction of its own
  resting conductance, which the descending AVB gap junctions — already in the connectome,
  55 contacts, resting at −21 mV — hold at a Hopf bifurcation. Amplitude is then regenerated
  segment by segment and proprioception carries only phase. Coherence rose in every region
  (head 0.4→0.90, mid 0.4→0.84, tail 0.03→0.35), the amplitude profile flattened from
  2.5/1.3/1.0 to 2.6/1.9/1.9, and net speed went 0.105 → 0.172 mm/s.

  **The interesting part is where the optimum sits.** Sweeping the calcium conductance and
  scoring on net displacement peaks where the Hopf margin is 0.94 — the units are poised
  *at* the bifurcation, not past it. Push them past and each segment free-runs, locks to
  itself, the tail reaches four times the head's amplitude, and the wave travels
  **backwards**. The useful regime is a critically-poised regenerative amplifier, which has
  the gain to cancel the relay's decay while still following its input, rather than an
  autonomous oscillator, which does not follow anything. A second change landed alongside
  it and is separated by its own control sweep (`tools/osc_control.py`): sensory input is
  now scaled by each target's resting conductance, because a fixed current across an
  eightfold spread of input conductance was hitting the small posterior units five times
  harder than the large anterior ones. That was worth +14%, the oscillator a further +31%.

- **The curvature amplitude is too low** — 2.3 /mm r.m.s. against a measured 4.3, so the
  worm undulates more shallowly than a real one.
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
- **The stretch-receptor gain is fitted**, not measured, and is the main free parameter in
  the model. So is Boyle et al.'s, and theirs differs by a factor of 1.86 between their own
  paper and their own code.
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
