# The WebAssembly port

The browser runs the animal itself. There is no simulation server: the page loads a
`.wasm` and a `.model` file and steps the worm locally, so every visitor gets their own.

## How it is split

**Python is the compiler; WebAssembly is the runtime.**

Everything expensive and fiddly that happens once at construction stays in Python — the
resting-potential solve, the per-cell muscle balance, the proprioceptive receptive fields,
the drag masks, the receptor overrides — and `tools/export_model.py` writes the *results*
out as a block of plain arrays. The WASM side implements only the per-step arithmetic.

That is worth doing for two reasons, and the second matters more than the first:

1. It removes roughly two thirds of what would otherwise have to be ported, including
   every part most likely to drift — `_balance`, `_receptive_fields`,
   `_resting_potentials`, `radius_profile`, the connectome loader.
2. **Whatever the two implementations disagree about, it cannot be the setup**, because
   both are reading it out of the same file. Any mismatch is in the stepping, which is
   where a conformance test can actually localise it.

The exporter also emits `assembly/model_gen.ts`, so every offset and constant is a
compile-time literal. The `.wasm` and the `.model` are produced by the same command and
agree by construction; there is no runtime binding step to get out of order.

### It is not a transpiler, and that has a price

"Python is the compiler" is true of the *setup* and not of the maths. `tools/export_model.py`
really does compile — it runs the Python construction and emits the results — but
`assembly/index.ts` is **hand-written AssemblyScript** mirroring the Python step functions.
Nothing generates it. So the constants and the precomputed matrices are compiled, and the
per-step arithmetic is transcribed by a person.

The cost of that is exactly what it sounds like: **two implementations of the same
equations, and every change to a step function has to be made twice.** The modulator
ablation fix was written twice. The differential repellent was written twice.

What makes it survivable is that the duplicated surface is the small, mechanical third —
and that `wasm/conform.mjs` checks it to floating point. What makes it *dangerous* is that
the check only protects what it covers, which this repository has now learned three times:
the plate's chemistry did not diffuse in the browser for weeks because the conformance dish
was empty and a field of zeros diffuses to zeros; ablation had eleven branches and zero
coverage until someone went looking; and the noisy path — the only path anything actually
runs in — was asserted to be checked when it was not. Every one of those was invisible to a
passing test suite.

The alternatives were considered and are worse *for this project*. CPython in WebAssembly
removes the duplication and costs about ten megabytes plus a numpy that is not fast, which
would take away the thing the port exists for. Auto-transpiling numpy is brittle in the
places that matter. The honest right answer, from a standing start, is to write the model
once in a language that targets both — native for the Python side, wasm for the browser —
and that is a rewrite which would cost the readability that makes `worm/*.py` reviewable as
science rather than as code. The split here is a trade, not a solution.

## What cannot match, and why that is fine

The background noise is an Ornstein–Uhlenbeck current driven by numpy's PCG64 and its
ziggurat normal sampler. Reproducing that bit-for-bit would mean porting both, and would
buy nothing — the noise is meant to be noise. So conformance runs with **noise disabled**,
where the two must agree to floating point. Anything else would be measuring the random
number generator.

That leaves a hole, and this file used to paper over it by asserting that the noisy case
was "checked on gait statistics instead", which was not true of any code here. **Nothing
runs with the noise off.** The browser runs noisy, every assay runs noisy, and all of this
model's behavioural claims are noisy-path claims — so conformance, on its own, certifies a
mode neither deployment uses.

`tools/parity.py` is the missing check. It compares the two implementations statistically,
which is the strongest claim available once they draw from different generators: the same
animal, not the same trajectory. The WebAssembly side dumps raw curvature, centroid and
gate state and computes nothing; **both arms are then measured by the same code**, for the
same reason the model file exists — if each side computed its own frequency, a
disagreement would be ambiguous between the model and the metric, and the metric is much
the easier of the two to get wrong.

Twenty animals a side, 90 s each on a bare plate, unpaired:

```
                          python      wasm     difference (wasm - python)     resolvable to
  undulation frequency     0.670     0.665     -0.005 [-0.013, +0.003] Hz         0.008
  wavelength               0.839     0.846     +0.007 [-0.006, +0.019] L          0.013
  travelling-wave index    0.862     0.865     +0.002 [-0.014, +0.022]            0.019
  curvature rms            4.490     4.515     +0.025 [-0.010, +0.060] /mm        0.037
  path speed              0.3630    0.3603    -0.0028 [-0.0123, +0.0064] mm/s     0.0098
  net speed               0.1768    0.2065    +0.0297 [-0.0210, +0.0790] mm/s     0.0519
  net / path               0.484     0.570     +0.086 [-0.046, +0.216]            0.137
  fraction forward         0.980     0.976     -0.004 [-0.011, +0.004]            0.008
  reversals                 3.23      3.20     -0.03 [-0.80, +0.77] /min          0.82
```

No metric separates the arms. Two honest qualifications, both of which the tool prints
rather than leaving to the reader:

- **The last column is the point.** Unpaired arms cost a great deal of power — the
  between-animal variance that `paired_ci` cancels does not cancel here — so "they agree"
  means "they agree to within what twenty animals a side can see". Gait is pinned tightly:
  frequency to 1.2% of its own mean, path speed to 2.7%. **Net speed and net/path are
  resolved only to about 29%**, because they depend on where the animal actually ended up
  over 90 s, which one badly-timed reversal dominates. Those two rows are weak claims and
  should be read as such.
- The Python arm's 0.670 Hz is the README's headline 0.67 ± 0.01 Hz, measured
  independently here. A parity tool that agreed with itself but not with the rest of the
  repository would be measuring its own metric.

This is expensive to run — about fifteen minutes for the WebAssembly arm alone, single
threaded — so it is not in CI. It is the check to run after touching anything in
`stepNervous`, the noise, or the command layer.

## Status: complete and matching, one animal and four

Conformance, with noise off, comparing against the Python step for step:

```
MECHANICS -- prescribed moment, 2000 steps, no biology
  worst node disagreement       4.999e-13 mm   (body spans 0.997 mm)
  worst curvature disagreement  4.997e-13 /mm

WHOLE LOOP -- neurons, muscle, senses, body; 4000 steps
  worst node disagreement       4.999e-13 mm
  worst membrane potential      5.000e-11 mV
  worst muscle tension          4.999e-13
  direction gate disagreed on   0 of 20 samples

ABLATED -- AVBL, AVAL, DB03, VB05, AVEL, RIML, I2L; 3000 steps
  cells reported dead           7 of 7
  worst node disagreement       4.999e-13 mm
  worst membrane potential      5.000e-11 mV
  worst activation              4.999e-11
  worst muscle tension          5.000e-13
  direction gate disagreed on   0 of 15 samples
  ablated cells still active    0

MULTI-ANIMAL -- 4 animals on one 1.5 mm lawn, stepAll, 8000 steps
  worst node disagreement       5.092e-13 mm
  worst membrane potential      5.981e-11 mV
  worst feeding state           4.988e-13     (lumen, ingested, eaten)
  worst contested-cell food     4.956e-13     (the 3x3 each animal fed from)
  worst plate total             4.690e-13     (65536 cells, summed two ways)
  feeding window disagreed on   0 of 80 samples
  direction gate disagreed on   0 of 80 samples
  capture events                16, all 16 contested
  plate drawn down              6.416e-02     (what the animals were credited)
```

The third case exists because ablation was the largest piece of this runtime that nothing
had ever looked at: eleven separate `anyDead` branches plus `rebuildGap`, none of them
reached by a check, behind a button in the viewer and underneath every ablation phenotype
in the Python. It is also the quietest place to be wrong — an ablation that is only mostly
applied still produces a worm-shaped thing that wriggles, it just answers a different
question than the experiment asked. The set is chosen to hit every branch: command
interneurons so the direction gate loses inputs, motor neurons so a muscle loses drive,
heavily gap-coupled cells so `rebuildGap` has something to do, and one pharyngeal cell,
which reaches the rest of the animal through a single gap junction and nothing else.

Those figures are the rounding granularity of the reference file, so the two agree to at
least the precision the reference stores. Everything is ported: nervous system, muscle,
body, senses, modulators, pharynx, world — including the plate's chemistry, which
diffuses and decays on its own clock. That last one was missing for a while, and the way
it was missed is instructive: the conformance plate was an empty dish, and a field of
zeros diffuses to zeros, so nothing disagreed. It surfaced only once the plate had a lawn
and a drop on it, as an otherwise exact run that diverged on step 41 and nowhere else —
41 steps is 0.0205 s, and `field_dt` is 0.02.

**And that sentence was false when it was written, in exactly the way the sentence after it
describes.** The modulators were *not* all ported: MOD-1, the serotonin-gated chloride
conductance, existed in `worm/modulators.py`, was exported into the model file, was named
in the roadmap as a parameter worth evolving — and appeared nowhere in `index.ts`. Every
conformance run passed, because the shipped coefficient is `0.0` and a term multiplied by
zero is indistinguishable from a term that is not there. The empty dish, the lawn-less
plate, the egg comparison that compared nothing, and this are all one mistake, and this one
sat directly beneath a paragraph explaining it.

It is ported now, and the coefficient is no longer baked into the payload: `mod1_unit`
carries the target set's resting conductance and an individual scales it with its own gene,
so the conformance suite runs a fourth case at the 0.30 that `params.py` documents. The
rule that falls out is the same one as before and worth stating in general: **a parameter
whose shipped value is zero is not covered by a check that only ever runs the shipped
value.** Every remaining `if (G.ANY_*)` branch in this file is in that position.

### The sixth case, and what it found on its first run

Every case above runs **one animal**, because each compares against a Python `Simulation`
and a `Simulation` is one animal. So the batch settlement, the shared world advance and
every allocation that has to be split sat outside the guarantee entirely — the same shape
of hole as the empty dish and the coefficient of zero, and the third time this file has had
to write that sentence. `population.mjs` runs four animals and checks real invariants on
them, but it has no Python to compare against, so it can only ask whether the runtime is
self-consistent.

The sixth case closes that: four animals within half a millimetre of each other on a 1.5 mm
lawn, driven by `stepAll`, against a Python `Population` on the same plate. Contested on
purpose and *measured* to be contested — all 16 capture events in the run happen while
another animal's 3×3 feeding neighbourhood overlaps the feeder's — because four animals on
four private lawns agree to **3.5e-18** whether the settlement is batched or served one at
a time, so a spread-out version of this case would pass against the exact defect it exists
to catch.

**It failed on its first run.** The two implementations settled contested feeding onto
*identical allocations* — which is what #71 established and what this case confirms,
0.00e+00 on every configuration where one group of animals reaches one set of cells — and
then took that food out of **different cells**:

| configuration | worst allocation gap | worst cell gap |
|---|---|---|
| one animal | 0.00e+00 | 0.00e+00 |
| two animals, same cell (one group) | 0.00e+00 | 0.00e+00 |
| two animals, far apart (disjoint) | 0.00e+00 | 0.00e+00 |
| two animals, one cell apart | 0.00e+00 | **2.330e-04** over 12 cells |
| two animals, diagonal neighbours | 0.00e+00 | **3.351e-04** over 14 cells |
| the four on the conformance plate | 0.00e+00 | **7.456e-04** over 15 cells |

`World.eat_batch` routed the withdrawal to minimise the largest fractional depletion of any
cell, so every cell in the union ended at the same fraction (0.99930104 across the board on
the two-animal case). `settleFeeding` withdraws each animal's share proportionally from its
own neighbourhood, so a cell two animals reach loses more than one only one of them reaches
(0.999068053 against 0.999534027). Same totals, same allocations, different hole in the
plate — and the food field is also a *sensory* field, so it did not stay a cosmetic
difference: on the conformance plate it was 5.006e-11 through step 2800, appeared at the
first contested pump on step 2881, and reached 4.740e-02 mV on membrane potentials and
9.877e-06 units on what each animal had eaten by step 8000.

It was isolated rather than inferred: replacing Python's `eat_batch` with a transcription of
`settleFeeding` and regenerating the reference made the case pass at 5.1e-13 mm, 6.1e-11 mV
and 4.988e-13 on feeding, so the rest of the multi-animal path — shared world advance,
per-animal state, ordering — was exact and the disagreement was that one routing rule and
nothing else. That is what was then done.

### Which side moved, and what it cost

The runtime cannot adopt Python's rule: the balanced routing is a linear program over a
max-flow, and this runs at 2 kHz in a browser tab. So **the model moved**. `World.eat_batch`
now runs `_settle_by_claim`, a line-for-line transcription of `settleFeeding`, for every
group of animals that share cells with another group; a group nothing else reaches keeps the
proportional withdrawal `World.eat` performs, which is what pins `Population([sim]).step` to
`Simulation.step`.

That is a real change to the reference model and it is not free. Measured, on an 8-cell test
plate:

- **maximum throughput is gone.** Two animals over one shared and one private cell, each
  wanting 1.0 of the 2.0 present, used to take all 2.0 — the max-flow routed the animal that
  could reach both onto the private cell. They now take 1.666666667 and leave 0.333333333 in
  the private cell of an animal that is already full. Nothing plans, so nothing steps aside.
- **weighted max-min fairness is gone.** The same pair over 1.0 shared and 0.25 private used
  to split 0.625/0.625; they now split 0.694444444/0.555555556, in proportion to the claim
  each makes.
- **minimal largest fractional depletion is gone**, which is the point: shared ground is
  grazed harder than private ground, because two animals really are eating the same
  bacteria.

Conservation, order-independence, relabeling-invariance and single-neighbourhood equivalence
with `World.eat` all survive and are what `tests/test_population.py` now asserts. The
`scipy.optimize.linprog` machinery, the Dinic max-flow and the progressive-filling search —
about 340 lines — are deleted.

One corner is knowingly left: when several animals share **one** neighbourhood and their
combined demand exceeds it, the kept single-group branch splits proportionally to demand
while the runtime splits proportionally to claim, measured 2.0e-02 apart on demands
[0.4, 0.2] against 0.3 available. Reaching it needs a neighbourhood stripped to within
0.06% of empty — the conformance plate runs at `want/avail` ≈ 5.6e-04 — and closing it means
giving up the single-animal equivalence that branch exists for.

## What it costs

| worms | real time | (before sparse matrices) |
|---|---|---|
| 1 | **2.36×** | 0.87× |
| 2 | **1.20×** | 0.43× |
| 4 | 0.60× | 0.22× |
| 8 | 0.30× | — |

The browser is now faster than the Python it was ported from (numpy manages 1.01×).

**Sparse matrices are why.** Every connectome matrix is between 0.3% and 2.5% non-zero —
2279 chemical synapses in a 302×302 grid, 552 gap junctions, 45 non-zeros in the head
reflex map. Dense multiplication spent 556,000 mul-adds a step to accumulate about 4,500
that were not zero. In compressed sparse row form the same step is 2.7× faster and the
model file went from 3.08 MB to **0.31 MB**.

Over the wire the whole animal is now **~55 kB gzipped** — 36 kB model plus 19 kB wasm.

**In memory, an animal is 239,360 bytes -- 234 kB.** The 302² matrices are anatomy and
shared between animals, and so is the runtime's per-step scratch, so a second worm
duplicates only state. State is not small: 210,936 of those bytes are `headHist`, the
560-sample delay line behind `head_delay = 0.28 s`, and the other 28 kB is everything else
the animal remembers. A population of 100 is 22.8 MB, on top of a shared `World` whose six
256² f64 grids — food, attractant, repellent, oxygen, the diffusion scratch, and the
attractant source added by #48 — come to 3,145,728 bytes, plus 606,208 for the egg record.

**A bacterial lawn is 1,048,576 bytes**, which since #48 is not a rounding either. A patch
caches the attractant and oxygen shapes it sources, so that eating it can scale them
instead of recomputing 65,536 `Math.exp` calls per patch fifty times a second — see
`addPatch`. A lawn is therefore four animals. The plate is capped at
`MAX_FOOD_PATCHES = 16`; `addFood` refuses past that and counts the refusal, which
`foodPatchCount()` and `foodPatchesRefused()` report so the viewer does not paint a marker
for a lawn the plate declined.

That figure is measured rather than estimated. `node wasm/memory.mjs` reads it off the
allocator's own per-worm stride through `ptrV`, cross-checks it against the summed array
dimensions in `class Worm`, and fails if this paragraph stops agreeing with it. This
paragraph used to say a second worm cost almost nothing; it was out by a factor of a
hundred and stayed that way because nothing ever read it (#33).

It was 381,840 bytes until the 37 per-step scratch arrays were hoisted to module level.
Worms are stepped strictly sequentially and single-threaded, so one copy of the working
space is enough and 140,776 bytes an animal was buying nothing. Two arrays that look like
scratch are **not**: `contactX`/`contactY` are read by `sense()` before `contact()` rewrites
them, so they carry the previous step's wall forces and stay per-worm. See `wasm/memory.mjs`
and case 12 of `wasm/population.mjs`.

## Running measurements on it

The runtime is faster than the Python it was ported from, which is worth having for any
measurement whose cost is wall clock. **How much faster depends on how many you run at
once, and the headline number is the one that does not apply to a sweep.**

| | measured |
|---|---|
| one process, machine otherwise idle | **2.28x** real time |
| ten concurrent, on twelve cores | **~1.5x** real time |

The table under *What it costs* is the first row. A sweep is the second: ten workers do not
each get a core, and this machine stops scaling around eight concurrent trials. An hour of
animal costs about forty minutes under a full sweep, not the twenty-six the single-process
figure suggests. Worth stating plainly because the first version of this section quoted
2.3x for a ten-way sweep, which was measured on one idle process and was wrong by a factor
of about 1.5.

`wasm/egglaying.mjs` is the first user: egg-laying clustering is a claim about several
twenty-minute cycles, so a job is an hour long whichever implementation runs it.

The division of labour is the same one the model file rests on. **The runtime emits raw
observations and computes nothing**; every statistic comes from one implementation in
`tools/`. `wasm/trajectories.mjs` dumps curvature, centroid and gate for `tools/parity.py`;
`wasm/egglaying.mjs` dumps event times for `tools/egglaying.py clustering`. If each side
measured its own frequency or its own clustering, a disagreement would be ambiguous
between the model and the metric, and the metric is much the easier of the two to get
wrong.

**Where this is safe.** Long runs at the shipped parameters, where the question is what the
animal does and the answer is a statistic over many events.

**Where it is not, and this is the one to remember.** *Never split the arms of a comparison
across implementations.* Conformance is exact only with the noise off. With it on the two
agree to within what twenty animals a side can resolve -- gait to about 1%, net
displacement only to about 29% (see the parity table above). Running a control in Python
and a treatment here would fold that uncertainty straight into the effect being measured.
Both arms in one implementation, always.

**Parameter sweeps need a rebuild.** Every constant is compiled in: `model_gen.ts` has
`EGL_HSN_GAIN` as a literal, not a field. So an A/B on a parameter means exporting and
recompiling per arm -- about thirty seconds, which is nothing against a twenty-minute run,
but it is not wired up, and each arm needs its own matched `.wasm` and `.model` pair. A
mismatched pair does not degrade gracefully; it reads the wrong byte offsets. `tools/
compare.py` stays on the Python for now, which is the right default anyway: it is the
reference implementation, and an assay suite that ran entirely on the port would leave the
thing it is a port *of* untested.

## Serving it

```bash
docker build -t celegans-sim . && docker run --rm -p 8080:8080 celegans-sim
```

Static nginx, no application server. Two things in that image are worth knowing about.

**The build runs the conformance check**, so a container that would ship a diverged model
fails to build instead. That is not belt-and-braces: the `.wasm` has the `.model`'s byte
offsets compiled into it, so a mismatched pair does not degrade gracefully — it reads the
wrong offsets.

**The asset URLs carry a content hash.** They have to. The exported model is *not*
bit-reproducible across numpy builds, because `_resting_potentials` and `_balance` go
through LAPACK and the container's backend is not the host's. The exporter is perfectly
deterministic on one machine; across the two, **5 of the 97 arrays differ, worst relative
difference 1.2e-15** — two ULPs, in `k_vhalf`. Nothing numerically, but a different file at
the same URL is all a cache needs to serve a stale model against a fresh runtime, and the
`.wasm` has the `.model`'s byte offsets compiled in. `build.json` names the hashed assets
and is the one file that is never cached.

The guarantee this buys is the one that matters: the model and the reference it is checked
against are generated by the *same* interpreter in the *same* build, so conformance is
exact within a container even though the hash is not stable across them.

## Build

```bash
PYTHONPATH=. .venv/bin/python tools/export_model.py   # .model + model_gen.ts
cd wasm && npm install && npx asc assembly/index.ts --target release
PYTHONPATH=. .venv/bin/python tools/conform.py > web/conform.json
node wasm/conform.mjs                                 # must pass
```

Run all four lines, in that order, every time. `web/conform.json` is a generated
reference, not a fixture: it is a recording of what the Python did on the day it was
made. Skipping the third line while the Python has moved does not weaken the check, it
inverts it — the port is then measured against a model that no longer exists, and it
fails loudly with a disagreement in millivolts that looks exactly like a real porting
bug. It cost an hour once. The Dockerfile regenerates it unconditionally and deletes it
afterwards, which is why the container build cannot make this mistake.
