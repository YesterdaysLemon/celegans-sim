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

## Status: complete and matching

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

The 302² matrices are anatomy and shared between animals, so a second worm duplicates only
state; that is why two in one dish costs what it does and no more.

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
