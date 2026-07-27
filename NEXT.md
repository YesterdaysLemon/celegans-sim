# Where this is, and what to do next

Written at the end of the first build. The model runs, is tested, and is honest about what
it gets wrong. This is the plan for making it get less wrong, in priority order, with the
reasoning and the measurements each item rests on so none of it has to be rediscovered.

Read the README's *What it does not get right* section first — this file assumes it.

---

## The one problem worth solving first

**The body wave is mostly passive.** The head oscillates, the body follows because it is
mechanically attached, and the proprioceptive reflex adds only a modest amount on top.
Everything else that is wrong follows from this:

| Symptom | Model | Real |
|---|---|---|
| Undulation frequency, agar | 1.2 Hz | 0.30 Hz |
| Wavelength | 1.4 L | 0.65 L |
| Crawling speed | 0.03–0.11 mm/s | 0.219 mm/s |
| Gait modulation direction | backwards | agar slow, water fast |

Three independent measurements say the same thing:

1. Wavelength is **insensitive to proprioceptive reach** — 1.11 → 1.20 L as the reach goes
   from 0.10 to 0.20 body lengths. If the reflex set the wavelength, this would be the
   single most sensitive knob in the model. It is nearly flat.
2. Driving the head externally and toggling the body reflex changes mid-body amplitude
   from 0.17 to 0.25 — a per-segment gain near **1.4**, where regenerating a wave needs
   something closer to a sustained 1.0 *per segment* over many segments.
3. If the wave were regenerated along the body, the medium would act on every segment and
   gait modulation would work. It acts mostly on the head, and gait modulation is inverted.

`tools/reflex_gain.py` measures (2) directly and sweeps it over gain, reach and muscle
strength. **Start there.** A first sweep was left running; if `scratch/reflex_gain.json`
exists, it has the results.

### Hypotheses for why the reflex gain is low, roughly in order of my confidence

- **H1 — the synaptic dynamic range is the ceiling.** With each neuron's release threshold
  placed at its own resting potential, `phi = 0.5` at rest, so `s_rest` is always ≥ 50% of
  `s_max` and **no graded synapse can more than double its conductance**. That is a
  structural consequence of the Kunert threshold trick, not a parameter. It caps how much
  a motor neuron can swing its muscle, which caps the moment, which caps the regenerated
  bend. Worth testing by biasing the thresholds a few mV *above* rest so the resting
  release is lower and the upward range larger — at the cost of the network being less
  responsive to hyperpolarisation. This is the deepest of the hypotheses and the one I
  would try first.
- **H2 — proprioceptive input should be a conductance, not a current.** Real stretch
  receptors are ion channels; opening one moves the cell towards a reversal potential and
  never past it. Injecting current instead is why motor neurons hit the voltage rail under
  strong drive, and why the drive has to be tuned so carefully to avoid a static bend.
  Switching to a rectified excitatory conductance (`g ∝ relu(stretch)`, reversal 0 mV) is
  more faithful, self-limiting, removes the clamp entirely, and makes the dorsal/ventral
  pair genuinely alternate rather than push-pull through one shared signed current.
  Moderate work: `Senses.sense` returns a conductance vector, `NervousSystem.step` accepts
  it. Sketch already in `worm/senses.py`'s structure.
- **H3 — the muscle is still leak-dominated.** After the per-cell balance, NMJ conductance
  is 1.45 nS against a 2.2 nS leak. Lowering muscle `g_leak` (keeping `tau_m` sensible by
  also lowering `C_m`) would give the motor neurons more authority per unit release. Cheap
  to test: it is two numbers in `MuscleParams`.
- **H4 — 48 segments coupled through a dense drag metric is too stiff.** The mechanical
  coupling between neighbouring segments may be washing out the local reflex. Test by
  running at `n_links = 96` and seeing whether the reflex gain per unit *length* holds up.
- **H5 — the B-type receptive fields are too wide.** A reach of 0.20 L is 10 joints; each
  neuron averages over a fifth of the body, which low-passes the very spatial structure it
  is meant to propagate. Wen et al.'s 200 µm is a *dendrite length*, not necessarily a
  flat averaging window. Try a weighted kernel peaked at the near end.

### The prize

The slow attractor is still in there. Before the head stretch receptor was given its own
kinetics, the head loop had two limit cycles and the slow one sat at **0.31 Hz with a
0.70 L wavelength** — almost exactly the real crawling gait. It was only reachable from
about a third of random seeds, which is why the filter is there. If the body reflex gets
strong enough to dominate, that attractor should become the robust one and four of the
table's five rows fix themselves at once.

---

## Second tier

- **Gait modulation direction.** Falls out of the above if the wave becomes reflex-driven.
  Do not tune it directly — it is a symptom.
- **Reversals and omega turns.** The machinery exists (A-type proprioception with a
  posterior field, AVA/AVB gating, touch → ALM/AVM → AVA) and `test_anterior_touch_drives_a_reversal`
  passes, but spontaneous reversal *statistics* have never been measured against the
  literature. Targets: 3.2–3.5 reversals/min off food and 0.7–1.25 on food (Zhao et al.
  2003); 35% of reversals terminate in an omega turn; omega reorientation ~160–170°.
  Needs a behavioural-statistics harness — count reversals over a 10-minute run and
  histogram the turn angles. This is a good self-contained next task.
- **Chemotaxis index.** The sensory circuitry is wired and adapting, and the animal does
  eat, but nothing yet measures whether it actually climbs a gradient better than chance.
  Standard assay: fraction of time within some radius of the peak, or the classic
  chemotaxis index over a fixed run. Should be easy and would be a strong validation of
  the whole sensory path. **Probably the highest value-per-hour item in this file.**
- **Speed on vs off food.** Real worms slow ~7× on a lawn (219 → 31 µm/s, Ramot et al.
  2008) via the dopaminergic basal slowing response. CEP/ADE/PDE already sense the lawn;
  check whether the connectome alone produces the slowing.

## Third tier / nice to have

- Pharyngeal pumping. The 20 pharyngeal neurons are simulated and drive nothing.
- Three dimensions, so left/right muscle quadrants separate and omega turns are real.
- A recorded-playback mode in the viewer — the transport bar has no scrubber because there
  is no history buffer on the server. A ring buffer of a few thousand frames would let the
  media-player metaphor actually be one.
- Neuron ablation is implemented in `Runner._ablate` and reachable over the WebSocket, but
  there is no UI for it. Clicking a neuron and killing it would be a good demo, and would
  reproduce classic ablation experiments (kill AVB → no forward locomotion).
- Multi-worm. The engine is one `Simulation` object; nothing prevents several.

---

## Things that will bite whoever picks this up

- **Do not trust a single seed.** The gait was bistable across seeds until very late, and
  two thirds of seeds went the wrong way. `test_gait_is_reproducible_across_seeds` guards
  it now. Any change to the head loop should be checked against at least three seeds.
- **Do not add intrinsic oscillators to the motor neurons.** It was tried. Dorsal and
  ventral members have identical dynamics and are gap-coupled, so they phase-lock to each
  other, and the animal contracts both sides at once with a measured input correlation of
  0.97. The rhythm has to come from something dorsoventrally antisymmetric. See the long
  comment in `NeuralParams`.
- **Reference receptive fields to the muscles a neuron drives, not to its soma.** DB and VB
  somas are interleaved along the cord in a way that does not line up dorsoventrally.
  `_output_position` in `worm/senses.py` handles this; do not "simplify" it back.
- **The muscle balance step is load-bearing.** Without it the heavier ventral innervation
  in the connectome holds the worm in a permanent C. Without the *per-cell* version, head
  muscles rest on the flat end of their tension curve and go deaf.
- **Watch the summary statistics.** A lot of time went into inferring behaviour from
  frequency/wavelength numbers that were hiding a statically bent worm. `tools/kymo.py`
  prints an ASCII kymograph in a few seconds and would have caught it immediately. Look at
  the picture first.
- **The server's simulation thread must yield.** It holds the GIL through a batch of steps;
  without the small unconditional sleep, new WebSocket connections time out during the
  opening handshake. Already fixed, but it is the kind of thing that gets "optimised" back.

---

## Useful commands

```bash
PYTHONPATH=. .venv/bin/python tools/kymo.py                 # look at the body, first
PYTHONPATH=. .venv/bin/python tools/diagnose_loop.py        # gait metrics
PYTHONPATH=. .venv/bin/python tools/reflex_gain.py          # the key measurement
PYTHONPATH=. .venv/bin/python tools/calibrate_body.py       # mechanics only, no biology
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q           # 31 tests, ~2.5 min
.venv/bin/python run.py --headless 60
```

Every tool takes `key=value` overrides for the parameters it cares about, e.g.
`tools/kymo.py pg=180 moment=3.0 medium=buffer`.

A full-suite run takes about two and a half minutes and each closed-loop probe is 30–50
seconds of wall time, so batch parameter sweeps and run them in the background rather than
one at a time.
