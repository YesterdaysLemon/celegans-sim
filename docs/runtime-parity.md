# Runtime parity: what the browser implements, and what only Python does

**Read this before changing any default in `worm/params.py`.**

Python is allowed to be a research superset. The browser runtime is the canonical shipped
animal. Those two sentences are compatible right up until a Python-only path becomes a
default, at which point the reference model and the animal a visitor sees are different
animals and nothing says so.

This file is the map of which is which. The machine-readable half is
`tools/export_model.py::RUNTIME_UNSUPPORTED`, pinned by `tests/test_runtime_parity.py`.

---

## How a parameter reaches the runtime

There are exactly three routes, and which one a parameter takes determines whether changing
it is safe.

**Route 1 — construction-time, baked into the payload.** The parameter is consumed while
Python builds a `Simulation`, and only its *result* is exported. `v_th_from_rest` and
`normalise_nmj` are the clearest cases: one decides how `V_th` is solved, the other whether
the neuromuscular map is balanced, and the runtime receives the solved thresholds and the
balanced `G` without ever learning that a choice was made.

*Changing one of these is safe as long as you re-export.* `tools/export_model.py` +
`npx asc` regenerate the pair, and the `dataset` job in `.github/workflows/python.yml`
fails if the committed artifacts no longer match. Forgetting to re-export is the failure
mode, and conformance catches it.

**Route 2 — exported as a scalar or a compile-time constant.** The parameter reaches the
runtime as a number, and `wasm/assembly/index.ts` implements *both* sides of whatever it
selects. `GATE_LATCHED`, `HEAD_DISTRIBUTED`, `HEAD_DELAY_N` and
`SEN_OMEGA_REFLEX_SUPPRESSION` are all of this kind: flip the Python default, re-export,
recompile, and the runtime follows.

*Changing one of these is safe with a re-export and a conformance run.*

**Route 3 — Python-only.** The parameter is not in the exporter's lists, is not in
`wasm/assembly/model_gen.ts`, and the code path it selects does not exist in
`wasm/assembly/index.ts` at all. Re-exporting does not help; there is nothing to export
*to*.

*Changing one of these away from its shipped value silently forks the model.* Conformance
still passes, because `tools/conform.py` builds from `Params()` and would be comparing two
implementations of the new configuration only if the runtime had one.

---

## Route 3, in full: the Python-only paths

Three families, five parameters plus one pair. **All of them are off by default**, and that
is the property `tests/test_runtime_parity.py` pins.

### 1. The head-reflex cascade — `REFERENCE_EXPERIMENTAL`

| | |
|---|---|
| Parameters | `SensoryParams.head_stages` (default `1`), `SensoryParams.head_stage_tau` (default `0.0`) |
| What it changes | Replaces the single first-order lag on the head stretch reflex with N stages in series, so the phase *adds* rather than averaging. At `head_stages = 4`, `head_stage_tau = 0.125`, `head_delay = 0` it matches the shipped frequency and retires both the largest fitted number in the model and the 210,936-byte `headHist` ring. |
| Python | `worm/senses.py` — `_head_chain` is built in `Senses.__init__` and consumed in `sense()` |
| Runtime | **Absent.** No `headChain`, no `HEAD_STAGES`, no `head_stage_tau` anywhere in `wasm/assembly/`. |
| Exporter | **Absent.** |
| Coverage | `tools/head_cascade.py`, `tools/head_medium.py`, `tools/lag_span.py`. No conformance case; there is nothing to conform against. |
| Status | Live candidate for adoption — see `NEXT.md`. **Porting it to the runtime is part of adopting it, not a follow-up.** |

> Note on why this one does not show up in a naive "is it read in a step function" scan:
> both parameters are read in `Senses.__init__`, which looks like Route 1. They are Route 3
> because what they build is a *step-time branch* (`if self._head_chain is None` in
> `sense()`), not a precomputed array the exporter could carry. Construction-time reads are
> only safe when the thing constructed is data.

### 2. Muscle force-velocity — `HISTORICAL_EXPERIMENT` / `DIGITAL_LIFE_CANDIDATE`

| | |
|---|---|
| Parameters | `MuscleParams.fv_vmax` (default `0.0` = off), `fv_curvature`, `fv_eccentric`, `fv_tau` |
| What it changes | Derates muscle force by shortening velocity — a Hill-type curve on `d(kappa)/dt`, low-passed by `fv_tau` before the factor is applied. |
| Python | `worm/muscle.py::_force_velocity` and `joint_moment`; the rate is finite-differenced in `worm/engine.py::prepare_step` |
| Runtime | **Absent.** |
| Exporter | **Absent.** |
| Coverage | `tools/force_velocity.py` |
| Status | Measured and **not adopted**: it narrows the gait-modulation span rather than widening it (1.27× → 1.17×), and it costs the crawl, which is where the model is calibrated. Kept because it is more faithful muscle than none, and because a lineage that has to pay for shortening velocity is a plausible Track B experiment. |

### 3. Omega wave suppression — `REFERENCE_EXPERIMENTAL`

| | |
|---|---|
| Parameter | `SensoryParams.omega_wave_suppression` (default `0.0` = off) |
| What it changes | Scales down the body proprioceptive drive and the head reflex gain in proportion to the omega turn's depth, so the travelling wave stands down while the turn runs. |
| Python | `worm/senses.py::sense` — `wave_gain` |
| Runtime | **Absent.** (`omega_reflex_suppression`, which is a *different* parameter acting only on the head gain, **is** implemented.) |
| Exporter | **Absent.** |
| Coverage | `tests/test_behaviour.py::test_omega_wave_suppression_is_inert_between_turns_and_anterior_during_one` |
| Status | Part of the turn-depth investigation. Reference-experimental. |

---

## Route 2: switches the runtime does implement

Recorded because the previous fresh-agent read of this repository got these wrong in the
pessimistic direction, and "the runtime cannot do X" is an expensive thing to believe
falsely.

| Parameter | Default | Runtime symbol | Both branches implemented? |
|---|---|---|---|
| `sensory.gate_latched` | `True` | `G.GATE_LATCHED` | Yes — Schmitt trigger and sigmoid, `index.ts` `sense()` |
| `sensory.head_distributed` | `True` | `G.HEAD_DISTRIBUTED` | Yes — sparse `W_head` product and the lumped `head_window` |
| `sensory.head_delay` | `0.28 s` | `G.HEAD_DELAY_N` | Yes — ring buffer and the zero-delay path |
| `sensory.omega_reflex_suppression` | `0.0` | `G.SEN_OMEGA_REFLEX_SUPPRESSION` | Yes |
| `neural.v_clamp` | `(-80, 45)` | `G.V_CLAMP_LO/HI` | n/a — a value, not a branch |
| `body.substeps` | `1` | `body_substeps` | Yes |

Every name in `tools/export_model.py`'s `NEURAL_SCALARS`, `MUSCLE_SCALARS`,
`SENSORY_SCALARS`, `MODULATOR_SCALARS`, `PHARYNX_SCALARS`, `EGGLAYING_SCALARS` and
`WORLD_SCALARS` is Route 2 as well. `_export_scalars` raises on a name that does not
resolve, so that list cannot silently lose an entry — which is how `sen_nose_touch_gain`
was lost once, and why it cannot be lost again.

## Route 1: construction-time, baked

Not enumerated exhaustively — it is most of `Params`. The ones worth naming because they
look like switches and are not:

| Parameter | Default | Baked into |
|---|---|---|
| `neural.v_th_from_rest` | `True` | the exported `V_th` array |
| `muscle.normalise_nmj` | `True` | the exported muscle `G` |
| `neural.command_cross_inhibition` | `0.0` | the exported `G_syn` / `GE_syn` CSR |
| `neural.glucl_pre` / `glucl_post` / `glucl_strength` | see `params.py` | the exported synapse matrices |
| `sensory.proprio_reach`, `head_reach`, `head_tau`, `head_field` | see `params.py` | `W_b`/`W_a`/`W_head` and the decay constants |

A change to any of these is a change to `web/worm.model`. Re-export and recompile as a pair;
never commit one without the other.

---

## The guard

`tools/export_model.py::RUNTIME_UNSUPPORTED` names each Route 3 parameter and the value the
runtime is equivalent to. `tests/test_runtime_parity.py` asserts that the shipped `Params()`
still sits on those values.

It is a tripwire, not a prohibition. If it fails, the change is not wrong — it is
*unfinished*, and the test message says what finishing looks like:

1. implement the path in `wasm/assembly/index.ts`;
2. export whatever constant selects it from `tools/export_model.py`;
3. extend `tools/conform.py` and `wasm/conform.mjs` to cover both sides;
4. rebuild the `.model`/`.wasm` pair and run conformance;
5. remove the entry from `RUNTIME_UNSUPPORTED` in the same commit.

**Experimenting is untouched.** The guard pins the *default* in `Params()`, not what any
tool, test or sweep may construct. `tools/force_velocity.py` passes `fv_vmax=1000` today and
will keep passing it; nothing in the guard looks at a `replace()`d tree.

### What the guard does not cover

Stated so the coverage is not overestimated:

- It does not detect a *new* Python-only path. Someone adding a fourth one, leaving it off,
  and not registering it gets no warning. The registry is a decision written down, in the
  same shape as `OPTIONAL_SCALARS` and `NO_CI_NEEDED` elsewhere in this repository.
- It does not check that the runtime *still* implements a Route 2 branch. Deleting the
  lumped head path from `index.ts` while `head_distributed` stays `True` would pass this
  test and pass conformance. Conformance only exercises the shipped configuration.
- It says nothing about Route 1 staleness — that is the `dataset` job's business.
