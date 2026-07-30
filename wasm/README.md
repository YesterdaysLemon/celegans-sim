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

| | |
|---|---|
| one worm | 0.87× real time (numpy manages 1.01×; its BLAS is very good at 302² matvecs) |
| two worms | 0.43× |
| over the wire | **~70 kB gzipped** — 51 kB model + 19 kB wasm |

The model file is 3.08 MB raw and gzips to 51 kB because the connectome is sparse. The
302×302 matrices are anatomy and shared between animals, so a second worm duplicates only
state — which is why two in one dish costs what it does and no more.

## Build

```bash
PYTHONPATH=. .venv/bin/python tools/export_model.py   # .model + model_gen.ts
cd wasm && npm install && npx asc assembly/index.ts --target release
PYTHONPATH=. .venv/bin/python tools/conform.py > web/conform.json
node wasm/conform.mjs                                 # must pass
```
