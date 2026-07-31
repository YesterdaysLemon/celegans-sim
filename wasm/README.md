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
where the two must agree to floating point, and the noisy case is checked on gait
*statistics* instead. Anything else would be measuring the random number generator.

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
```

Those figures are the rounding granularity of the reference file, so the two agree to at
least the precision the reference stores. Everything is ported: nervous system, muscle,
body, senses, modulators, pharynx, world.

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

## Build

```bash
PYTHONPATH=. .venv/bin/python tools/export_model.py   # .model + model_gen.ts
cd wasm && npm install && npx asc assembly/index.ts --target release
PYTHONPATH=. .venv/bin/python tools/conform.py > web/conform.json
node wasm/conform.mjs                                 # must pass
```
