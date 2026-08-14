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
Python builds a `Simulation`, and only its *result* is exported. `normalise_nmj` is the
clearest case: it decides whether the neuromuscular map is balanced, and the runtime
receives the balanced `G` without ever learning that a choice was made.

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

*Changing one of these away from its shipped value forks the model.* Whether anything
notices depends on a second property, and an earlier draft of this file got that wrong.

**Measured, against the committed `web/worm.wasm`** — flip the default, regenerate the
reference with `tools/conform.py`, run `node wasm/conform.mjs`:

| flipped | conformance |
|---|---|
| baseline | PASS, exit 0 |
| `sensory.head_stages = 4` | **FAIL**, exit 10 |
| `muscle.fv_vmax = 1.0` | **FAIL**, exit 10 |
| `sensory.omega_wave_suppression = 1.0` | **PASS**, exit 0 |

So conformance is *not* blind to a Python-only default in general. It reproduces the Python
side from `Params()`, so the moment the new configuration changes the Python trajectory the
comparison against the unchanged runtime diverges and the run fails.

**The real gap is narrower and worse.** A path escapes conformance when it is *inert across
every conformance case* — when the term it controls is multiplied by something that is zero
throughout the reference trajectories. `omega_wave_suppression` scales by `abs(self.omega)`
(`worm/senses.py`: `wave_gain = max(0.0, 1.0 - p.omega_wave_suppression * abs(self.omega))`),
and no conformance case ever fires an omega turn, so the whole term is
multiplied by zero however large the coefficient is.

This repository has been bitten by exactly that before, and says so at `tools/conform.py`:
"a term multiplied by zero is not being checked — which is exactly how the whole
serotonin-gated chloride path reached the runtime unported and stayed that way, passing
every conformance run because absent and zero agree to every decimal place."

For `head_stages` and `fv_vmax` the guard is therefore a *second* detector that fires earlier
and names the cause. For `omega_wave_suppression` it is the **only** detector.

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
| `DIAGNOSTIC_CONTROL` | Not a candidate mechanism at all. It exists so that a null result can be produced on demand — the switch is kept *because* turning it on changes nothing, and that is what rules a suspect out. Distinct from `HISTORICAL_NEGATIVE`, where something was proposed and failed; here nothing was ever proposed. |
| `UNCERTAIN` | The repository does not settle it. Not a guess dressed as a status. **No model path currently carries it** — `v_th_from_rest` did until it turned out to be unread, not uncertain. The label stays defined because the next genuinely-undetermined path needs somewhere to go that is not a guess. (`tools/README.md` has an identically-named *tool* class; different definition, different subject.) |

A path can carry two labels when the two tracks ask different questions of it. Force-velocity
does; see below.

---

## Route 3 — the Python-only paths

Four families, two of which crossed into the runtime on 2026-08-14 (the cascade and the
amine path — see their entries). **All are off by default**, and the two still
Python-only are what `tests/test_runtime_parity.py` pins.

### `sensory.load_gain` (+ `load_half`, `proprio_reach_swim`, `modulator.dopamine_head_lag`, `modulator.dopamine_reach_swim`, `modulator.dopamine_muscle_rate`) — the amine load-sensing path
**Runtime: implemented (2026-08-14 port), off by default. Lifecycle: `REFERENCE_CANDIDATE`.**

*The port:* `Worm.dragLoad` mirrors `Body.drag_load` from the saved qdot; the transduction
current, dopamine's three effect scales and the swim-field blend run per worm behind
`setAminePath`, whose all-zero default is the canonical animal; the swim receptive fields
ride in the payload as `wbs`/`was` at the third-calibration reach, built by the same
`_receptive_fields` the Python constructs with. The `amine` conformance case runs the
whole configuration for 4000 steps and agrees to 5.0e-13 mm / 5.0e-11 mV, with 68 mV of
measured effect against cascade-only — the same absent-and-zero-agree argument every
enabled case exists for. Adoption (flipping defaults) remains gated on the behavioural
scorecard and the food/load confound in NEXT.md; the runtime-parity precondition is
discharged.

CEP/ADE/PDE transduce the drag force the cuticle bears (`Body.drag_load`, the mean |c·v|
per unit length — the one gait signal measured to survive below the K ≈ 8 knee where the
bending dynamics go medium-blind); dopamine integrates it through the existing wireless
layer; and two effects engage as it falls: the head reflex's lag budget shrinks (a
load-scaled *time*) and the proprioceptive reach lengthens toward a third precomputed
field pair. Biology: Vidal-Gadea et al. 2011 (dopamine holds the crawl), Korta et al.
2007 (load modulates the swim); both cited with what could be verified at
`SensoryParams.load_gain`.

*Measured* (`tools/amine_gait.py`, 2026-08-13/14, three calibrations, each a full
nine-media locus): the agar end holds the shipped gait at every calibration (dopamine at
ceiling; the third's crawl carries the best agar wave measured, TWI +0.889), and the
(f, λ) locus reaches **+0.847 along the animal's crawl→swim chord against the baseline's
+0.347 endpoint** — 85% of the way to the swim, buffer at 89% of the animal's swim
frequency, wave-speed span 3.72× against the baseline's 1.39× (animal: 13.9×), the K ≈ 8
saturation gone, TWI ≥ +0.73 at every medium. The calibration sequence (+0.595 → +0.786
→ +0.847) and its two guards — the bistability cliff above muscle coefficient ~0.5, and
the three-tau settle a slow modulator demands of any protocol measuring it — are in the
tool's docstring. The candidate label is earned, not
aspirational — but adoption has named preconditions: the food/load confound on the
dopamine scalar (stated at `load_gain`), a full behavioural scorecard (dopamine now moves
during ordinary locomotion), runtime parity for five constants plus the cascade this path
runs on, and the calibration knobs in `NEXT.md`.

Python: `worm/body.py::drag_load`, `worm/senses.py` (transduction, swim fields, cascade
rescale), `worm/modulators.py::head_lag_scale/swim_reach_blend`, `worm/engine.py` (the
load pass-through). Tools: `tools/amine_gait.py`.

### `sensory.head_stages`, `sensory.head_stage_tau` — the head-reflex cascade
**Runtime: implemented (2026-08-14 port) — Route 2 now, kept here for its history. Lifecycle: `REFERENCE_CANDIDATE`.**

*The port:* `HEAD_STAGES`/`HEAD_STAGE_DECAY`/`HEAD_STAGE_TAU` are exported scalars, the
stage chain runs in both reflex forms, and `setHeadCascade` configures it per worm so the
`cascade` conformance case exercises stages = 4 against the canonical payload: 4.98e-13 mm
/ 5.0e-11 mV over 4000 steps, 31 mV of effect against the single-lag reflex. At the
shipped stages = 1 the single-lag path is untouched byte for byte. Adoption is still its
own decision; what this port removes is only the parity blocker.

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
| `body.substeps` | `1` | `G.BODY_SUBSTEPS` | `substeps > 1` | **`DIAGNOSTIC_CONTROL`** — substepping sixteenfold reproduces `dt = 0.5 ms` exactly. Nobody ever proposed substepping as an improvement; it exists so that "the mechanics are under-integrated" can be ruled out on demand, which is what sent the search to the coupling instead. Kept *because* it changes nothing. |
| `neural.v_clamp` | `(-80, 45)` | `G.V_CLAMP_LO/HI` | n/a — a value, not a branch | — |

Almost every name in `tools/export_model.py`'s `NEURAL_SCALARS`, `MUSCLE_SCALARS`,
`SENSORY_SCALARS`, `MODULATOR_SCALARS`, `PHARYNX_SCALARS`, `EGGLAYING_SCALARS` and
`WORLD_SCALARS` is Route 2 as well. `_export_scalars` raises on a name that does not resolve,
so that list cannot silently lose an entry — which is how `sen_nose_touch_gain` was lost once,
and why it cannot be lost again.

**Three of those names are exported and then not read by the runtime**, so "it is in the
scalar list" is not by itself evidence that the runtime honours it:

| exported constant | what it actually is |
|---|---|
| `MUS_REST_TENSION` | Route **1**. `rest_tension` is consumed inside `Muscles._balance` and reaches the animal baked into the exported muscle `G`; `index.ts` never reads the scalar. |
| `WORLD_INGESTION_RATE` | dead on both sides. `worm/genome.py` already names `world.ingestion_rate` among "known dead parameters". |
| `WORLD_RADIUS` | redundant. The runtime uses `WORLD_EXTENT`, exported separately from the same `p.radius`. |

Verified by checking each `export const` in `model_gen.ts` for a `G.<name>` reference in
`index.ts`, **restricted to the seven scalar-group names above** — that restriction matters:
run unrestricted, the same method also returns `BODY_LENGTH`, `BODY_RADIUS_MAX`, the four
`MED_*` medium constants, `ODOUR_DECAY`, `TOUCH_DECAY` and `N_NODES`, none of which
`index.ts` reads either. So the honest count of exported-but-unread constants is around
twelve; three is the number *within the seven scalar lists this paragraph is about*. Run
without that restriction over **all** 371 `export const`s the count is 101, because the
layout constants (`LEN_*`, `OFF_*`, `ROWS_*`, `COLS_*`) are addressed through generated
accessors rather than by name. Harmless today
— `rest_tension` still reaches the animal, the rest are inert on both sides — but an audit run
from this document alone would otherwise conclude the runtime honours constants it ignores.

## Route 1 — construction-time, baked

Not enumerated exhaustively; it is most of `Params`. The ones worth naming because they look
like switches and are not:

Two columns, because a single "lifecycle" column cannot answer honestly for both binary
switches and continuous constants: the shipped value always has a status, and only some of
these have an alternate to classify at all. Where there is no discrete alternate, the cell
says so rather than restating the shipped status under a heading that promises otherwise.

| Parameter | Shipped | Baked into | Shipped value | The alternate, if there is one |
|---|---|---|---|---|
| `neural.v_th_from_rest` | `True` | the exported `V_th` array | `REFERENCE_SHIPPED` | **none — the flag is not read.** `worm/nervous.py` calls `self.V_th = self._resting_potentials(s_half)` unconditionally; there is no `if p.v_th_from_rest` anywhere in `worm/`. Setting it `False` produces a byte-identical model, so there is no alternate to classify. An earlier draft of this table called it `UNCERTAIN` — "argued for, never measured with it off" — which reads as *nobody has run it* rather than *it cannot be run*, and would send someone off to measure a configuration that does not exist. |
| `muscle.normalise_nmj` | `True` | the exported muscle `G` | `REFERENCE_SHIPPED`, **load-bearing** | `False` → `HISTORICAL_SUPERSEDED`. The uncorrected map is what the reconstruction gives you, and `params.py` records the outcome: the heavier ventral innervation holds the worm in a permanent C. |
| `neural.command_cross_inhibition` | `0.0` | the exported `G_syn`/`GE_syn` CSR | `REFERENCE_SHIPPED` (0.0 = as reconstructed) | `> 0` → `HISTORICAL_NEGATIVE`. `tools/command_sweep.py` records that cross-inhibition never moved the correlation it was proposed to fix. |
| `neural.glucl_pre`/`glucl_post`/`glucl_strength` | see `params.py` | the exported synapse matrices | `REFERENCE_SHIPPED` | none — a cell list and a strength, not a switch. |
| `sensory.proprio_reach`, `head_reach`, `head_tau`, `head_field` | see `params.py` | `W_b`/`W_a`/`W_head` and the decay constants | `REFERENCE_SHIPPED` | none — continuous constants with no discrete alternative. `proprio_reach` is the target of the next open experiment in `NEXT.md`, which will produce a value rather than a branch. |

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
- **It pins a value, not the behaviour that value stands for.** The registry records that
  `omega_wave_suppression = 0.0` is runtime-equivalent; that equivalence is a property of one
  line of `worm/senses.py` (`wave_gain = max(0.0, 1.0 - p.omega_wave_suppression * abs(omega))`)
  and of the target set built beside it. Re-parameterise that line — an offset, a different
  baseline, a change to `_omega_wave_body` — and the shipped Python animal moves while the
  registered value is still `0.0`. The guard stays green because it only compares the value,
  and, uniquely for this path, no conformance case exercises it either. For `head_stages` and
  `fv_vmax` conformance is a second detector; here there is none.
- It says nothing about axis 2 at all.
