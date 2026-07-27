# Where this is, and what to do next

> **Update, day two.** Two things below are now out of date and it is worth reading this
> first.
>
> **The speed numbers everywhere in this file were measured wrong.** The metric smoothed
> the magnitude of instantaneous centroid velocity, which counts the side-to-side slosh of
> an undulating body as forward progress, and read about twenty times high. Measured the
> way a tracker does — net displacement over a window — the model does **5 µm/s against a
> real 219**, with a net-to-path ratio of **0.07**. The worm undulates almost exactly on
> the spot. Every "speed" column in the tables below is the old, inflated quantity; treat
> them as ordinal, not absolute. `sim.speed` is now honest and `sim.path_speed` keeps the
> old one.
>
> **Question (a) is answered, and the answer was no.** Backing the head reflex off does
> *not* help. Measured on net speed: shipped default 0.005 mm/s (ratio 0.07); the candidate
> `moment=3.2, reach=0.30, pg=45` with the head left at 150 gives **0.013–0.018 mm/s (ratio
> 0.15–0.20)**, a genuine 3× improvement; the same thing with the head backed off to 60
> drops to 0.008 (ratio 0.16). So the candidate is real and worth keeping, but the head is
> not what is holding it back. Do not spend more time on (a).
>
> **The real diagnosis, and it is sharper than anything in the rest of this file.** The
> body's oscillation is **two thirds a standing wave**. Decomposing curvature over (time,
> arclength), the travelling-wave index is **+0.33**, where +1 is a pure travelling wave
> and 0 is a pure standing one. A standing wave produces exactly zero net thrust however
> large its amplitude — its drag forces cancel over the cycle — which is why a worm with
> textbook-correct curvature amplitude goes nowhere.
>
> The control is decisive: the **same body, same drag**, driven by a clean prescribed
> travelling wave instead of by the nervous system, gives **TWI +0.996 and 0.174 mm/s**,
> very nearly the real animal's 0.219. The mechanics were never the problem. The nervous
> system is producing a wave that stands still.
>
> And this unifies the open faults rather than adding to them: at 1.4 body lengths of
> wavelength, less than one full wave fits on the body, so there is almost no phase
> progression along it — which *is* a standing wave. **Wavelength and thrust are one
> problem.** Everything in the hypothesis list below should be judged on whether it raises
> the travelling-wave index, not on speed, which is slow and noisy to measure by comparison.
> `travelling_index` in `tools/diagnose_loop.py`; it is validated against synthetic
> travelling and standing waves.
>
> **What replaced it:** `tools/optimise.py` searches the seven unmeasured parameters
> against an objective built from the measured behaviour, with net speed and net/path
> weighted most heavily. Hand-tuning one parameter at a time was never going to work on a
> seven-dimensional interacting problem, and doing it against a broken metric was worse
> than useless. See the note on fitting versus training at the top of that file.

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
strength. **Start there.**

### A first sweep already ran, and it changes the plan

Partial results (each row is the gain at five positions from head to tail; a row that
*rises* left to right is a reflex regenerating the wave rather than merely passing it on):

```
gain   reach  moment   s=0.25  s=0.40  s=0.55  s=0.70  s=0.85
45     0.10   1.6        1.11    1.50    0.84    0.19    0.34
45     0.10   3.2        1.25    1.28    1.42    2.33    2.58
45     0.20   1.6        1.11    1.23    2.79    1.31    2.93
45     0.20   3.2        1.30    2.03    2.99    2.00    3.58
45     0.30   1.6        0.99    1.04    3.14    1.69    3.55
45     0.30   3.2        1.43    2.04    4.45    3.76    5.92   <-- strongly regenerating
90     0.10   1.6        1.21    1.27    1.47    1.55    1.51
90     0.10   3.2        1.26    1.28    1.96    1.81    0.90
90     0.20   1.6        1.24    1.96    2.00    1.08    1.69
```

Three things fall out of this, and the first two were not what I expected:

1. **`proprio_gain` is not the main lever.** Going from 45 to 90 pA does not reliably help
   and sometimes hurts. I had been treating it as the knob; it is not. Every hour spent
   sweeping it was largely wasted, which is worth knowing before repeating it.
2. **`proprio_reach` and `peak_moment` are the levers**, and they compound. The best row so
   far is the *lowest* proprioceptive gain with the longest reach and the strongest muscle:
   gain rising monotonically to 5.9 by the tail. That is the signature the model needs.
3. The current defaults (gain 90, reach 0.20, moment 1.6) sit in the weak-reflex corner of
   this table. That is precisely why the wave is passive.

**So the concrete first experiment tomorrow is:** set `peak_moment ≈ 3.2` and
`proprio_reach ≈ 0.30`, *drop* `proprio_gain` to ~45, and then **reduce
`head_proprio_gain`** so the head stops dominating — the body should now be able to carry
the wave itself. Then check with `tools/diagnose_loop.py` across at least three seeds
whether the 0.31 Hz / 0.70 L attractor has become the robust one.

Note that `peak_moment = 3.0` was rejected earlier in the build for producing twice the
real curvature, but that was measured with the *old, unfiltered* head reflex at full gain.
With the head backed off, the balance is different and it deserves re-testing rather than
being ruled out. Watch `kappa_max` — it must stay near 10 /mm.

The sweep was still running when this was written; re-run
`PYTHONPATH=. python tools/reflex_gain.py --out scratch/reflex_gain.json` for the full
24-row table (about 50 minutes; the `gain=180` and `gain=360` rows are the missing ones,
and on this evidence they are the least interesting).

### I then tried that configuration in the closed loop. It is the right direction.

`peak_moment=3.2, proprio_reach=0.30, proprio_gain=45`, head reflex left at its current
150, three seeds:

```
seed   freq   wavelen  direction    k_rms  k_max   speed   dv_corr
0     1.111    1.00   head->tail     5.15  22.42   0.118    -0.80
3     1.222    0.62   head->tail     8.32  23.88   0.118    -0.76
7     0.111    1.09   tail->head     8.34  23.28   0.099    -0.80
```

Compare against the shipped defaults (1.2 Hz, 1.4 L, k_max ~10, speed 0.03–0.11,
dv_corr −0.31). What improved, and it is not subtle:

- **Dorsoventral antagonism goes from −0.31 to −0.80.** The two muscle sheets are now
  genuinely alternating instead of half-heartedly. This is the single biggest jump I saw
  from any parameter change in the whole build.
- **Wavelength drops** from 1.4 L towards the measured 0.65 L (seed 3 hits 0.62 exactly).
- **Speed rises** and becomes consistent across seeds at ~0.10–0.12 mm/s.

What broke, and both look tractable:

- **Peak curvature is 22–24 /mm against a measured 9.8.** The body is being over-bent by
  roughly 2.3×. The obvious response is to back `peak_moment` down from 3.2 towards
  ~2.0–2.4 and see how much of the dv_corr and wavelength gain survives. There may be a
  sweet spot; there may not, and if not, that itself is informative about whether moment
  and reflex gain are separable.
- **Seed 7 runs backwards and very slow.** Reproducibility regressed, which is expected —
  the head reflex is still at 150 and is now fighting a much stronger body reflex for
  control of the wave. **Backing the head off is the untested half of this experiment**
  and is the first thing to run. I had `head_proprio_gain` at 60 and 25 queued and did not
  get to them.

So the ordered plan is: (a) re-run this with `head_proprio_gain` at 60 and 25 across the
same three seeds; (b) scale `peak_moment` down until `k_max` lands near 10; (c) confirm
with `test_gait_is_reproducible_across_seeds`; (d) if frequency is still high, *then* look
at H1 and H2 below. Do not touch H1/H2 before (a)–(c) — they are much more invasive and
this cheaper change may make them unnecessary.

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

## A ready-to-run first command for tomorrow

This is (a) from the plan above — the untested half of the promising experiment. Paste it
and go; it takes about six minutes.

```bash
PYTHONPATH=. .venv/bin/python -u - <<'EOF'
from dataclasses import replace
from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import analyse, bare_world
print("%-6s %5s %8s %9s %11s %7s %8s %8s %8s" % (
    "head","seed","freq","wavelen","direction","k_rms","k_max","speed","dvcorr"))
for hg in (60.0, 25.0):
    for seed in (0, 3, 7):
        p = Params()
        p = replace(p,
            muscle=replace(p.muscle, peak_moment=3.2),
            sensory=replace(p.sensory, proprio_gain=45.0, proprio_reach=0.30,
                            head_proprio_gain=hg))
        r = analyse(Simulation(p, seed=seed, world=bare_world(p)), seconds=18.0)
        print("%-6.0f %5d %8.3f %9.2f %11s %7.2f %8.2f %8.4f %8.2f" % (
            hg, seed, r["freq"], r["wavelength"], r["direction"],
            r["kappa_rms"], r["kappa_max"], r["speed"], r["dv_corr"]), flush=True)
EOF
```

Read it as: does backing the head off make all three seeds go head-to-tail again, and does
the wavelength stay near 0.65 L? If yes, move to scaling `peak_moment` down for `k_max`.
If the seeds still disagree, the head and body reflexes are competing for the wave and the
next question is whether the head reflex should be weakened much further or removed
entirely once the body can sustain itself.

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
