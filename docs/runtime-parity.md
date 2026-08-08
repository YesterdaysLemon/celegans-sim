# Runtime parity and model-path lifecycle

**Read this before changing any default in `worm/params.py`.**

Python is allowed to be a research superset. The browser runtime is the canonical shipped
animal. Those two sentences are compatible right up until a Python-only path becomes a
default, at which point the reference model and the animal a visitor sees are different
animals and nothing says so.

## Two questions, two axes — do not conflate them

This file answers two questions about every alternate model path, and they are independent:

| Axis | Question | Kind of fact |
|---|---|---|
| **Runtime support** | Does `wasm/assembly/index.ts` implement this? | Mechanical. Settled by reading the source. |
| **Scientific lifecycle** | What does this repository know about whether the path is any good? | Empirical. Settled by measurement, or not settled at all. |

They cross in all four combinations, and the combination that matters most is the one that
looks like a contradiction: **`omega_reflex_suppression` is fully implemented in the runtime
and scientifically refuted.** `params.py` records "it was tried, and it does nothing", every
confidence interval overlapping every other, and it is *kept* — implemented, exported,
running in the browser, permanently at 0.0 — because the refutation is the useful part.
"The runtime has it" says nothing about whether it works, and "it does not work" is not a
reason to remove it.

The machine-readable half of the first axis is `tools/export_model.py::RUNTIME_UNSUPPORTED`,
pinned by `tests/test_runtime_parity.py`. The second axis has no machine-readable form; it is
prose here and provenance in `worm/params.py`, which is where the measurements live.

---

## Axis 1 — how a parameter reaches the runtime

Three routes, and which one a parameter takes determines whether changing it is safe.

**Route 1 — construction-time, baked into the payload.** The parameter is consumed while
Python builds a `Simulation`, and only its *result* is exported. `v_th_from_rest` and
`normalise_nmj` are the clearest cases: one decides how `V_th` is solved, the other whether
the neuromuscular map is balanced, and the runtime receives the solved thresholds and the
balanced `G` without ever learning that a choice was made.

*Safe to change, as long as you re-export.* `tools/export_model.py` + `npx asc` regenerate
the pair, and the `dataset` job in `.github/workflows/python.yml` fails if the committed
artifacts no longer match. Forgetting to re-export is the failure mode, and conformance
catches it.

**Route 2 — exported as a scalar or a compile-time constant.** The parameter reaches the
runtime as a number, and `wasm/assembly/index.ts` implements *both* sides of whatever it
selects.

*Safe to change, with a re-export and a conformance run.*

**Route 3 — Python-only.** The parameter is not in the exporter's lists, is not in
`wasm/assembly/model_gen.ts`, and the code path it selects does not exist in
`wasm/assembly/index.ts` at all. Re-exporting does not help; there is nothing to export *to*.

*Changing one of these away from its shipped value silently forks the model.* Conformance
still passes, because `tools/conform.py` builds from `Params()` and would be comparing two
implementations of the new configuration only if the runtime had one.

---

## Axis 2 — lifecycle labels

Used below and in `tools/README.md`. Deliberately few, and `UNCERTAIN` is a real answer.

| Label | Means |
|---|---|
| `REFERENCE_SHIPPED` | In the canonical animal today. |
| `REFERENCE_CANDIDATE` | Measured, better than what ships on at least one axis, and genuinely open for adoption. |
| `HISTORICAL_SUPERSEDED` | An earlier configuration, measured against and beaten by what shipped. Kept because the comparison is the evidence for the current choice. |
| `HISTORICAL_NEGATIVE` | Tried and refuted. The refutation is the value. Each one names the form it should **not** be retried in. |
| `DIGITAL_LIFE_CANDIDATE` | Plausibly useful to Track B, whose fitness question is not the reference-gait question. |
| `UNCERTAIN` | The repository does not settle it. Not a guess dressed as a status. |

A path can carry two labels when the two tracks ask different questions of it. Force-velocity
does; see below.

---

## Route 3 — the Python-only paths

Three families. **All are off by default**, and that is what
`tests/test_runtime_parity.py` pins.

### `sensory.head_stages`, `sensory.head_stage_tau` — the head-reflex cascade
**Runtime: not implemented. Lifecycle: `REFERENCE_CANDIDATE`.**

Replaces the single first-order lag on the head stretch reflex with N stages in series, so
phase *adds* rather than averaging. At `head_stages = 4`, `head_stage_tau = 0.125`,
`head_delay = 0` it matches the shipped frequency and improves the travelling wave, net speed
and path straightness in every medium, retiring the largest fitted number in the model and
the 210,936-byte `headHist` ring with it.

**The argument it was built for was refuted.** `tools/head_medium.py` asked whether a
saturating cascade phase follows the mechanical load where a fixed delay cannot — the whole
reason to want it — and measured 1.27× shipped against 1.29× cascade. It does not fix gait
modulation. It survives as a *simplification*, which is a different and weaker claim than the
one it was built to support, and adopting it is still open.

Python: `worm/senses.py` — `_head_chain`, built in `Senses.__init__`, consumed in `sense()`.
Tools: `tools/head_cascade.py` (live), `tools/head_medium.py`, `tools/lag_span.py`.

> Why this does not show up in a naive "is it read in a step function" scan: both parameters
> are read in `Senses.__init__`, which looks like Route 1. They are Route 3 because what they
> build is a *step-time branch* (`if self._head_chain is None` in `sense()`), not a
> precomputed array the exporter could carry. Construction-time reads are only safe when the
> thing constructed is data.

### `muscle.fv_vmax` (+ `fv_curvature`, `fv_eccentric`, `fv_tau`) — force-velocity
**Runtime: not implemented. Lifecycle: `HISTORICAL_NEGATIVE` for the reference gait, and
`DIGITAL_LIFE_CANDIDATE`.**

Derates muscle force by shortening velocity — a Hill-type curve on `d(kappa)/dt`, low-passed
by `fv_tau`.

*Reference-gait verdict, measured:* `tools/force_velocity.py` was aimed at widening the
gait-modulation span and **narrowed it monotonically**, 1.27× → 1.17×. The tool's own header
predicted the mechanism: the derating acts on shortening rate, shortening rate is a property
of the gait rather than of the medium, this gait is similar at both ends, so it applies about
equally at both and cancels out of the ratio while adding lag. Not adopted, and it costs the
crawl where the model is calibrated.

**Do not retry as** a stronger derating — it is also unstable there.

*Track B:* the second label is not a consolation. It is more faithful muscle than none, and a
lineage that has to pay for shortening velocity is a different question from whether the
reference animal's span widens. Nothing in the repository has asked that question.

### `sensory.omega_wave_suppression` — standing the body wave down during a turn
**Runtime: not implemented. Lifecycle: `HISTORICAL_NEGATIVE`.**

Attenuates the head oscillator and the anterior proprioceptive propagators while an omega
turn is live, scaled by turn amplitude so it is exactly inert between turns.

*Measured and refuted* (`worm/params.py`, 2026-07-30; six paired animals per condition,
200 s each). It makes the turn **shallower, not deeper**: off food the median reorientation
fell 37.75 → 15.62 deg (paired difference −22.1, 95% CI −34.4 to −12.4); on food 42.63 →
29.05 deg (−13.6, CI −22.3 to −9.6). **The fraction over 120 deg fell to zero in both
conditions.** Net/path, heading drift and path speed did not move detectably. The conclusion
in `params.py` is that the travelling wave is *helping* carry the turn down the body rather
than consuming headroom the static bend could use — "so leave this off".

**Do not retry as** another target set or another gain. `params.py`'s turn analysis says so
directly: what the turn needs is more headroom in the motor units, or the static component
applied where it does not compete with the oscillation for the same dynamic range.

---

## Route 2 — the runtime implements both branches

Recorded because an earlier read of this repository reported these as Python-only. **They are
not.** The runtime is less frozen than it looks, and "the runtime cannot do X" is an expensive
thing to believe falsely.

| Parameter | Shipped | Runtime symbol | The alternate branch | Lifecycle of the alternate |
|---|---|---|---|---|
| `sensory.gate_latched` | `True` | `G.GATE_LATCHED` | the graded/sigmoid gate | **`HISTORICAL_SUPERSEDED`** — its "reversals" lasted 0.06 s, a fifteenth of a cycle: a difference dipping below threshold and bouncing back. Latching beat it on speed, net/path and travelling index at once. |
| `sensory.head_distributed` | `True` | `G.HEAD_DISTRIBUTED` | the lumped head reflex | **`HISTORICAL_SUPERSEDED`** — `tools/head_circuit.py`: travelling index +0.68 against +0.58, with less than half the invented delay (0.28 s against 0.60). |
| `sensory.head_delay` | `0.28 s` | `G.HEAD_DELAY_N` | `head_delay = 0` | **tied to the cascade `REFERENCE_CANDIDATE`** — zero delay is what the cascade is for. `params.py` calls the shipped 0.28 "a fit and not an explanation". |
| `sensory.omega_reflex_suppression` | `0.0` | `G.SEN_OMEGA_REFLEX_SUPPRESSION` | any value > 0 | **`HISTORICAL_NEGATIVE`** — "it was tried, and it does nothing"; every interval overlaps every other across 60–69 turns per condition. Nearly believed on four seeds until `tools/stats.py` turned it back into noise. Kept because the refutation is the useful part. |
| `body.substeps` | `1` | `body_substeps` | `substeps > 1` | **diagnostic control** — substepping sixteenfold reproduces `dt = 0.5 ms` exactly. That is what ruled the mechanics out and sent the search to the coupling. Kept *because* it is the control. |
| `neural.v_clamp` | `(-80, 45)` | `G.V_CLAMP_LO/HI` | n/a — a value, not a branch | — |

Every name in `tools/export_model.py`'s `NEURAL_SCALARS`, `MUSCLE_SCALARS`,
`SENSORY_SCALARS`, `MODULATOR_SCALARS`, `PHARYNX_SCALARS`, `EGGLAYING_SCALARS` and
`WORLD_SCALARS` is Route 2 as well. `_export_scalars` raises on a name that does not resolve,
so that list cannot silently lose an entry — which is how `sen_nose_touch_gain` was lost once,
and why it cannot be lost again.

## Route 1 — construction-time, baked

Not enumerated exhaustively; it is most of `Params`. The ones worth naming because they look
like switches and are not:

| Parameter | Shipped | Baked into | Lifecycle of the alternate |
|---|---|---|---|
| `neural.v_th_from_rest` | `True` | the exported `V_th` array | `UNCERTAIN` — the repository argues the solve removes 302 free parameters but records no measurement of the model with it off |
| `muscle.normalise_nmj` | `True` | the exported muscle `G` | **`REFERENCE_SHIPPED`, and load-bearing** — without it the heavier ventral innervation holds the worm in a permanent C |
| `neural.command_cross_inhibition` | `0.0` | the exported `G_syn`/`GE_syn` CSR | `HISTORICAL_NEGATIVE` — `tools/command_sweep.py`'s note records that cross-inhibition never moved the decision |
| `neural.glucl_pre`/`glucl_post`/`glucl_strength` | see `params.py` | the exported synapse matrices | `REFERENCE_SHIPPED` |
| `sensory.proprio_reach`, `head_reach`, `head_tau`, `head_field` | see `params.py` | `W_b`/`W_a`/`W_head` and the decay constants | `REFERENCE_SHIPPED`; `proprio_reach` is the target of the next open experiment in `NEXT.md` |

A change to any of these is a change to `web/worm.model`. Re-export and recompile as a pair;
never commit one without the other.

---

## The guard

`tools/export_model.py::RUNTIME_UNSUPPORTED` names each Route 3 parameter and the value the
runtime is equivalent to. `tests/test_runtime_parity.py` asserts that the shipped `Params()`
still sits on those values.

**It is an axis-1 guard only.** It knows nothing about whether a path is scientifically a good
idea, and it should not — a tripwire that also had opinions about biology would be wrong more
often and harder to argue with.

If it fails, the change is not wrong — it is *unfinished*, and the test message says what
finishing looks like:

1. implement the path in `wasm/assembly/index.ts`;
2. export whatever constant selects it from `tools/export_model.py`;
3. extend `tools/conform.py` and `wasm/conform.mjs` to cover both sides;
4. rebuild the `.model`/`.wasm` pair and run conformance;
5. remove the entry from `RUNTIME_UNSUPPORTED` in the same commit.

**Experimenting is untouched.** The guard pins the *default* in `Params()`, not what any tool,
test or sweep may construct. `tools/force_velocity.py` passes `fv_vmax=1000` today and will
keep passing it; nothing in the guard looks at a `replace()`d tree.

### What the guard does not cover

Stated so the coverage is not overestimated:

- It does not detect a *new* Python-only path. Someone adding a fourth one, leaving it off,
  and not registering it gets no warning. The registry is a decision written down, in the same
  shape as `OPTIONAL_SCALARS` and `NO_CI_NEEDED` elsewhere in this repository.
- It does not check that the runtime *still* implements a Route 2 branch. Deleting the lumped
  head path from `index.ts` while `head_distributed` stays `True` would pass this test and
  pass conformance. Conformance only exercises the shipped configuration.
- It says nothing about Route 1 staleness — that is the `dataset` job's business.
- It says nothing about axis 2 at all.
