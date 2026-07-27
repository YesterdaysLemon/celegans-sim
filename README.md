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

It runs at roughly real time on one core (the nervous system alone is ~8× real time; the
body mechanics are the expensive part).

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

Giving the motor neurons intrinsic oscillator currents (Morris-Lecar; the right biology,
since every regenerative event in this animal is calcium-carried) *does* produce a rhythm —
and it does not work. The dorsal and ventral members of a class have identical intrinsic
dynamics and are coupled by gap junctions and reciprocal synapses, so they phase-lock **to
each other**: the animal contracts both sides of its body in time with itself and does not
bend at all. Measured directly, the presynaptic inputs to a single muscle had a pairwise
correlation of 0.97. The rhythm has to come from somewhere dorsoventrally *anti*symmetric.

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

---

## Does it behave like a worm?

`pytest tests/` — 30 tests, of which these are the load-bearing ones. Reference values are
measurements on live animals.

| Quantity | Model | Measured | Source |
|---|---|---|---|
| Curvature, r.m.s. | **4.1 /mm** | 4.3 ± 0.3 /mm | Krajacic et al. 2012 |
| Curvature, peak | **9.9–10.1 /mm** | 9.8 ± 1.1 /mm | Krajacic et al. 2012 |
| Wave direction | **head → tail** | head → tail | — |
| Muscle resting potential | **−31 to −24 mV** | −25.0 ± 1.0 mV | Gao & Zhen 2011 |
| Resting potentials | **−62 to −12 mV** | −75 to −25 mV | several, see `params.py` |
| Swimming efficiency U/c | **0.076** | 0.08 ± 0.01 | Shen et al. 2012 |
| Neuron count / classes | **302 / 118** | 302 / 118 | canonical |
| GABAergic neurons | **26** | 26 | McIntire et al. 1993 |
| Crawling speed (net) | **0.005 mm/s** | 0.219 ± 0.029 mm/s | Ramot et al. 2008 |
| Net displacement / path | **0.07** | well above 0.5 | — |
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

- **On agar it undulates at about 1.2 Hz with a 1.4-body-length wavelength.** A real worm
  crawling on agar does 0.30 Hz and 0.65 L; a real worm *swimming* does 1.76 Hz and 1.54 L.
  So the model's default gait, whatever the medium, resembles swimming. It gets the shape
  of the animal's undulation right and the timing of it wrong.

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
- **The worm undulates almost on the spot.** Over 120 simulated seconds it travels 8.4 mm
  of path and ends up 0.54 mm from where it started — a net-to-path ratio of 0.07, where a
  real animal keeps well over half of the distance it covers. Net speed is about 5 µm/s
  against a measured 219 µm/s. It is a beautifully behaved undulation that does not
  translate.

  I originally reported this as "0.03–0.11 mm/s, about half the measured value", **and that
  was wrong.** The metric was smoothing the *magnitude* of instantaneous centroid velocity,
  which counts the side-to-side slosh of the centroid within each undulation cycle as if it
  were forward progress, and read roughly twenty times high. Both numbers are now kept
  separately — `sim.speed` is net displacement over a two-second window, the way a worm
  tracker measures it, and `sim.path_speed` is the old path-length quantity — and the tests
  assert on the honest one. Credit where due: this was caught by someone simply watching
  the animation and saying it looked like it was wiggling in place.
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
tools/calibrate_body.py mechanics checks, independent of the biology
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
