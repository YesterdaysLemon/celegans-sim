# tools/ — the instrument shelf

Ninety-odd files live here and they are not the same kind of thing. Some are load-bearing
infrastructure that half the repository imports; some are maintained instruments you should
reach for by name; most of the rest are one-shot probes that answered a question once and
have not been touched since.

This index exists so that question is answerable without grepping the tree. **Nothing has
been moved or deleted** — a probe that answered a question is part of the scientific record,
and several of the ones below are cited by name in `docs/research-log/`.

## How to read the classification

| Label | Means |
|---|---|
| **CORE_INFRASTRUCTURE** | Part of the build, export, data or check pipeline. Breaking it breaks CI or the artifacts. |
| **MEASUREMENT_LIBRARY** | Imported by many other tools. The blast radius of an edit is the whole tooling layer. |
| **MAINTAINED_INSTRUMENT** | A measurement you are meant to reach for. Listed with a line each in `docs/deploy.md`, and expected to still work. |
| **ACTIVE_EXPERIMENT** | Its question is **still open** in `NEXT.md`. |
| **ANSWERED_PROBE** | Asked a sharp question, got an answer, and the answer is load-bearing. A sacrifice branch: it did its job. Kept executable because the result is a do-not-repeat. |
| **UNCERTAIN** | No importers, and untouched since the first days. *Probably* a finished one-shot — but "probably" is the honest word, none has been confirmed dead, and six of them **are** referenced — see the section's own note. |

**Recency is not activity, and this index used to make that mistake.** Four probes were
labelled `ACTIVE_EXPERIMENT` because they had been touched in the project's last days of
work. They had been touched because they were *finishing* — each one ran, answered its
question in the negative, and closed it. Being edited recently is evidence that a file
mattered recently; whether its question is still open is a separate fact, and only `NEXT.md`
and `worm/params.py` settle it.

`imp` is the number of modules importing it, and it is the column that carries the decision
weight. It is reproducible by exactly one command, stated here so a future reader can check it
rather than trust it:

```bash
grep -rlE "from tools\.<name> import|import tools\.<name>\b|from tools import ([A-Za-z_]+, )*<name>\b|from \.<name> import" \
  --include="*.py" tools tests | grep -v "tools/<name>.py" | wc -l
```

(Re-measured 2026-09-24. The earlier form of this command matched only the first two import
styles, so `from tools import audit` and `from .raw_sources import ...` counted as nothing --
`audit.py` read 0 importers with a test importing it. A 0 here is safe to act on only if
the command that produced it could have seen the import.)

An earlier version of this index also carried a `ref` column defined as "files mentioning its
path". That definition did not reproduce its own numbers — four plausible readings of it gave
four different answers — so it has been removed rather than left as an unverifiable figure in
a table whose header claims everything in it was measured. Where a reference matters it is now
named in prose instead.

`last` is the last commit touching the file.

For the *model paths* these tools test, the lifecycle labels are in
[`docs/runtime-parity.md`](../docs/runtime-parity.md), which also explains why "the runtime
implements it" and "it works" are independent facts.

---

## CORE_INFRASTRUCTURE

Touch these and something else stops building.

| tool | imp | does |
|---|---|---|
| `export_model.py` | 3 | Freezes the model into `web/worm.model` + `wasm/assembly/model_gen.ts`. Also owns `GENES` and `RUNTIME_UNSUPPORTED`. |
| `conform.py` | 0 | Reference trajectories the WebAssembly port is checked against. Paired with `wasm/conform.mjs`. |
| `build_dataset.py` | 0 | Raw anatomy → validated `data/celegans.json`. Assertion-heavy on purpose. |
| `fetch_raw.py`, `fetch_raw.sh` | 0 | Download the exact bytes approved in `data/raw_sources.json`, fail-closed on hash. |
| `raw_sources.py` | 3 | The pinned source manifest and its verification helpers. |
| `check_model_artifacts.py` | 1 | Fails when committed browser artifacts are stale against a fresh export. |
| `manifest.py` | 0 | Content-hashes the runtime assets so `immutable` caching is safe. Run by the Docker build. |
| `audit.py` | 1 | Breaks things on purpose and reports which check notices. The meta-check. Every mutation's pattern is pinned by `tests/test_audit.py`, because one stale pattern stops the whole audit. |
| `parity.py` | 0 | Python vs WASM, noise **on**, compared statistically. |
| `ci_test_targets.py` | 1 | The Python suite's CI matrix: which files run together, and the dense ones sharded by test id. `--json` lists the targets, `--run T` runs one. |
| `check_all.mjs` | 0 | Runs every gate CI would, in the workflows' order. A skip is never a pass. |
| `check_web.mjs` | 0 | Viewer module graph: cycles, unresolved imports, leftovers. |
| `check_cache_headers.mjs` | 0 | Every served asset has a deliberate cache policy. |
| `smoke_web.mjs` | 0 | The viewer in a real browser, desktop and mobile. |
| `smoke_server.mjs` | 0 | The `?server` transport against a live Python model. |
| `sim_rate.test.mjs` | 0 | The rate readouts measure what their labels claim. |

## MEASUREMENT_LIBRARY

**These look like scripts and are not.** They have command-line front ends, which is how they
came to be misread as one-offs, but their importers outnumber every other file here.

| tool | imp | the imported surface |
|---|---|---|
| `diagnose_loop.py` | **49** | `analyse`, `bare_world`, `travelling_index`, `_dominant`. `analyse`'s return dict is this project's operational definition of "what the gait is doing". |
| `assays.py` | **40** | `pooled`, `estimate`, `run_trial`, `reversals`, `SAMPLE_DT`, `ASSAYS`, `DURATIONS`, `ORDER`, `THROUGHPUT`, `WORKERS`, `_dispatch`, `_clean_plate`, `_chemo_placement`, `_chemo_score`, `apply_overrides`, `current_params`. |
| `stats.py` | 7 | `bootstrap_ci`, `paired_ci`, `ratio_ci`, `mde`, `verdict`, `fmt`, `BOOTSTRAP`, `clears_zero`, `two_sample_ci`. Reached transitively by everything through `assays`. |
| `coherence.py` | 3 | `profile` — per-position wave coherence. A small library rather than a hub, but it has importers and no documentation elsewhere. |

Six of those symbols are private by name and imported across modules anyway: `_dispatch`,
`_clean_plate`, `_chemo_placement`, `_chemo_score`, `_dominant`, and (from `worm/senses.py`)
`_output_position`. Renaming one is
a cross-module change. The two `tools/` modules that own one now say so — `assays.py` for
`_dispatch`, `_clean_plate` and the two `_chemo_` helpers, `diagnose_loop.py` for `_dominant`. `worm/senses.py`'s does
not, because this pass keeps the change surface under `worm/` at zero.

Changing what a key of `analyse` *means*, or how an assay is *scored*, silently makes every
number already recorded in `docs/research-log/` incomparable with every future one, with
nothing to fail. Add keys and assays; do not repurpose them.

## MAINTAINED_INSTRUMENT

Listed in `docs/deploy.md` with a line each, and expected to still work. Reach for these by name.

| tool | does |
|---|---|
| `kymo.py` | ASCII kymograph. **Look at the picture first** — a lot of time has gone into inferring behaviour from summary statistics that were hiding a statically bent worm. |
| `scorecard.py` | Every headline number at once, across seeds, in three media. With `--emit` it writes the README table block and `docs/scorecard.md` from the same run — `tests/test_scorecard_doc.py` pins the two copies identical, and the dispatch-only `scorecard` workflow refreshes them on demand. |
| `idle_neurons.py` | Which neurons the world cannot reach: unions every input route and lists the deaf sensory cells, the field-blind motor classes, and the wiring-only interneurons. The routing roadmap's evidence. |
| `bag_border.py` | Does BAG hold the animal where the food is? Paired lawn-dwell assay for the oxygen-downshift route; its docstring carries the first reading and the taxis-ceiling caveat. |
| `awb_probe.py` | Would routing AWB help the escape? Three-arm injected probe (OFF, ON, neither); the docstring carries the negative reading — both signs hurt through the wiring as reconstructed — and the receptor-level follow-up hypothesis. The reason AWB stays deaf on purpose. |
| `ethogram.py` | Reversal rate, run lengths, reorientation, on food and off. |
| `compare.py` | A/B two configurations on identical seeds with paired intervals. The tool for "does this change help?". |
| `assays.py` | Chemotaxis, aerotaxis, thermotaxis, nociception, pirouettes, weathervaning. |
| `calibrate_body.py` | Mechanics checks, independent of the biology. |
| `timestep_convergence.py` | Is the gait converged at the step size it runs at? |
| `thrust.py` | What speed the mechanics allow, and what the circuit collects. |
| `head_mode.py` | Which of the head loop's limit cycles the animal lands in, and why. |
| `head_circuit.py` | Lumped vs distributed head reflex, scored on the wave. |
| `loop_phase.py` | Opens the head loop and measures each stage's gain and phase. |
| `wave_speed.py` | What sets the wavelength and the frequency. |
| `body_oscillator.py` | Can the body carry the rhythm instead of the head? |
| `command_probe.py` | What each input is worth to the forward/backward decision. |
| `command_sweep.py` | …and does locomotion survive changing it. |
| `habituation.py` | Tap habituation — decrement, interval dependence, recovery. |
| `pharynx.py` | Pump rate on and off food, and five ablation phenotypes. |
| `egglaying.py` | Rate, retention, the HSN and serotonin phenotypes. |
| `omega.py` | The omega turn: what did not work, what did, and what it bought. |
| `ase_opponency.py` | Which way round the ON and OFF chemosensors should push. |
| `self_contact.py` | Does the body pass through itself, and when would it start. |
| `moment_ceiling.py` | Can the mechanics make the turn the circuit cannot? |
| `turn_scaling.py` | What sets that ceiling: the medium, or the body? |
| `optimise.py` | Fits the handful of unmeasured parameters against behavioural targets. Its `SPACE` overlaps `worm/genome.py::BOUNDS`, and both lists are pinned (`tests/test_genome.py`). |

## ACTIVE_EXPERIMENT

Two. Their questions are open in `NEXT.md`.

| tool | last | open question |
|---|---|---|
| `head_cascade.py` | 2026-08-04 | Should the cascade be adopted? It matches the shipped frequency with `head_delay = 0` and improves the wave, so it is live **as a simplification** — the mechanism argument it was built for was refuted by `head_medium.py` below. The runtime port is done (2026-08-14; its constructor allocation corrected 2026-09-24), so adoption waits only on a scorecard/ethogram baseline. Now also load-bearing for the amine path, which runs on it. |
| `amine_gait.py` | 2026-08-13 | How far toward the animal can the amine load-sensing path be calibrated, and should it be adopted? Measured three times: the third calibration reaches 85% of the way along the animal's chord (baseline endpoint 35%), buffer at 89% of the swim frequency, agar untouched every time, K ≈ 8 saturation gone; the cliff and the settle guard are in the tool. Calibration knobs and adoption preconditions in `NEXT.md`; lifecycle in `docs/runtime-parity.md`. |

## ANSWERED_PROBE — sacrifice branches

Each of these asked one sharp question, ran, and answered it. They are not active work and
their questions are not open; they are kept executable because the answers are load-bearing
do-not-repeats, and because a probe is cheap to keep and expensive to reconstruct.

| tool | last | question, and the answer |
|---|---|---|
| `head_medium.py` | 2026-08-04 | Does the cascade's saturating phase follow the mechanical load where a fixed delay cannot? **No** — 1.27× shipped against 1.29× cascade. This is the measurement that retired the cascade's *reason*, leaving only its merits. |
| `lag_span.py` | 2026-08-04 | If the fixed lag pins the swimming end, does cutting it widen the span? **Barely** — 1.29× → 1.40× for a fourfold cut, which retracted the diagnosis the same day it was written. The tool fixed its own success criteria before the run; that is why the retraction was clean. |
| `force_velocity.py` | 2026-08-04 | Does a Hill-type force-velocity curve widen the span? **It narrows it**, monotonically, 1.27× → 1.17×. Its own header predicted this failure mode before the run. |
| `damping_sweep.py` | 2026-08-04 | Is the buffer-end frequency set by the body's internal damping rather than the medium? **No** — zero internal damping buys 0.03 Hz. An existing assumption checked outside the regime it was made in. |
| `flambda_locus.py` | 2026-08-12 | Does the model's (f, λ) locus lie on the animal's crawl→swim line, or slide off it as the medium sweeps? **On it, but bunched** — perpendicular drift never exceeds 0.10 L while the model traverses 11% of the chord, 89% of its frequency motion above K = 9. One saturating coupling moves f and λ together; the two-independent-knobs suspicion is dead, and the flat wavelength is not its own problem. **Also a library**: `amine_gait.py` (active), `loop_medium.py` and `fv_phase.py` import its sweep, chord geometry and plotting. |
| `loop_medium.py` | 2026-08-13 | Which stage of the loop feels the medium, and why does it stop by K = 9? **The passive body, alone** — tension→curvature moves +40° from K = 40 → 7.9 while every other stage moves ≤0.2°, both body-reflex arms identical, knee where τ = c_n/(EI·k⁴) put it in a prediction committed mid-run. Open-loop phase + analytic receptor predicts the closed-loop frequency at every medium to ≤1.5%, so gait-modulation candidates can now be screened without closed-loop sweeps. **Also a library**: `fv_phase.py` imports its job, lock-in and receptor phase. |
| `fv_phase.py` | 2026-08-13 | Is muscle force-velocity a load-scaled time, or a brake that cancels out of the span? **A load-scaled time, backwards and knee-bound** — it brakes hardest in thin fluid (−16.8° of plant phase on agar, −34.9° in buffer) and its load-dependence saturates at the same K ≈ 8, because it reads the body's motion. Retired for modulation with its mechanism named; the screen reproduced the closed-loop fv = 500 record (span 1.170 predicted vs 1.167 measured), its second validation. |
| `clamp_occupancy.py` | 2026-08-26 | Should proprioception act as a conductance rather than a current? **No** (#194) — better on every forward-gait guardrail, and it abolishes spontaneous reversals (2.03/min → 0 in clean space): a conductance shunts as well as drives, so the backward command pushes on a leakier membrane. Its docstring holds THE BATTERY, the behavioural tables that refused it. |
| `buffer_basin.py` | 2026-08-26 | Does the swimming animal have a second, coiled attractor? **No** (#195) — at the shipped defaults the coil-up is a recurrent, self-ending ~15 s episode no seed stays in; a real bistability appears only at muscle coefficients ≥ 0.7. Now a protocol guard: any buffer measurement must not let an episode hide in its window. |
| `turn_depth.py` | 2026-08-27 | What held the omega turn shallow? **The bias lifetime, not its amplitude** (#196) — at `omega_tau = 1.5` the bias decayed inside one undulation; 2.5 restores the animal's ~35% deep turns, adopted on fit-maintenance grounds. (That it was not the taxis bottleneck is `chemo_power.py`'s answer.) |
| `sleep_surface.py` | 2026-08-26 | What does sleep look like from outside? **Duration is the circuit's, timing the ecology's** (#197) — bouts last ≈ tau_sleep·ln(0.69/0.25) ≈ 46 s nearly deterministically, while intervals run 114 ± 114 s on the animal's own foraging. The run also caught the dish rim dropping a roamer (#211). |
| `thermo_memory.py` | 2026-08-27 | Can the learned thermotaxis setpoint steer through a tonic input to AFD? **No** (#198) — the memory learns where the animal was fed and ships live, but every tonic routing was refused: AFD steers through its transient, not its level. The recorded follow-up is a setpoint-conditional differential. |
| `chemo_power.py` | 2026-08-28 | Did clearing the turn-depth ceiling (#215) re-open chemotaxis? **No** — 16/16 paired seeds, every metric no-effect (CI −0.045 [−0.154, +0.034]). Its pirouette rows were then audited by the next entry and belong to the detector. |
| `pirouette_audit.py` | 2026-09-24 | Was the deep-turn animal's pirouette flip (1.41 → 0.79) the detector or the circuit? **The detector** — the circuit's up-gradient command rate held (3.65 → 3.51/min) while the longer omega made more of the ~0.35 s commands visible to `assays.reversals` (35% → 59%); neither circuit conditions detectably on command onsets (0.98, 1.15). Its `omega` counterfactual found the turn backing the body up (+0.88 s uncommanded tail-first per command), which is open in `NEXT.md`. |

The four 2026-08-04 probes are negative results and all four are in `NEXT.md`'s
do-not-re-run table. The reasoning is in [`docs/research-log/`](../docs/research-log/); the
model-path lifecycle labels are in [`docs/runtime-parity.md`](../docs/runtime-parity.md).

`force_velocity.py` is the one with a second life: its verdict is negative **for the
reference-gait question only**. Whether a lineage that must pay for shortening velocity
evolves differently is a Track B question nobody has asked, which is why the parity document
labels the path `HISTORICAL_NEGATIVE` *and* `DIGITAL_LIFE_CANDIDATE`.

## UNCERTAIN — probably finished one-shots, not confirmed

No importers, and untouched since the earliest days of the project.

**They are not all unreferenced, and an earlier version of this section said they were.**
Five are cited by path in `worm/params.py` as the provenance for a shipped constant — that
is, the model's own parameter file points at them to say *how this number was calibrated* —
and a sixth is cited from another tool. The "cited in" column below names them. This matters
beyond bookkeeping: `docs/project-architecture.md` makes "every constant carries its source"
a load-bearing root, so archiving one of those five would break a provenance reference in
`params.py`. The disposition was settled (b1227cc, 2026-08-25): they stay. Each answered a specific question during a specific investigation; several are
cited by name in the research log, which is why none has been moved.

**Do not delete these on the strength of this table.** "No importers" is evidence, not proof,
and a probe is cheap to keep and expensive to reconstruct. Whether they eventually move to
`tools/experiments/` is an owner decision recorded in `NEXT.md`.

| tool | asked | cited in |
|---|---|---|
| `adapt_moment.py` | Recover curvature amplitude via muscle strength, with the receptor adapting | |
| `adaptation.py` | Does adapting the stretch receptor let the wave travel? | |
| `chemo_gain_sweep.py` | Can chemosensory gain alone produce chemotaxis? | |
| `common_drive.py` | Is a shared oscillating drive forcing the motor neurons into lockstep? | |
| `coupling_strength.py` | How much muscle-muscle coupling keeps the tail coherent? | |
| `efficacy.py` | Is the efficacy gradient attenuating the wave before the tail? | |
| `gate_calibrate.py` | Place the direction gate and size the cord drive | `params.py` |
| `gate_sweep.py` | Why the animal never reverses, and what letting him costs | |
| `head_balance.py` | Retest the head reflex now the body reflex works | |
| `ml_scan.py` | Search Morris-Lecar space for a usable conditional oscillator | |
| `modulator_sweep.py` | Calibrate the modulator layer against basal slowing | `params.py` |
| `moment_candidate.py` | Test the `peak_moment` candidate, and the ratio caveat | |
| `muscle_leak.py` | Is the coupling weak, or is the muscle leak too high? | |
| `noise_test.py` | Is the tail's incoherence just amplified background noise? | |
| `osc_control.py` | Separate the two changes | `params.py`, log |
| `osc_entrain.py` | Oscillator strength against proprioceptive coupling | |
| `osc_sweep.py` | Conditional-oscillator parameters in the full closed loop | |
| `phase_profile.py` | Where along the chain does the phase gradient get lost? | |
| `pool_probe.py` | Does `pooled()` lose jobs when there are more than workers? | |
| `reflex_gain.py` | Per-segment gain of the proprioceptive reflex | log |
| `reversal_test.py` | Does the animal reverse now both cords are regenerative? | `params.py` |
| `stiffness.py` | Does bending stiffness decide travelling vs standing? | |
| `tau_sweep.py` | `adapt_tau` at the critically-poised operating point | `params.py` |
| `twi_by_region.py` | Is the travelling-wave ceiling the head dragging the average down? | `tools/reflex_gain.py`, log |
| `where_it_stands.py` | Localise the standing wave: muscle drive, or body? | |

That is **25 tools**, about a third of this directory, whose status cannot be determined from
the repository alone.

---

## Conventions

- Run from the repository root with `PYTHONPATH=.`.
- Every Python tool takes `key=value` overrides for the parameters it cares about, e.g.
  `tools/kymo.py pg=180 moment=3.0 medium=buffer`.
- Closed-loop probes are CPU-heavy. Run sweeps in batches, do not overlap them with the test
  suite, and report completed jobs rather than estimating from a partial run.
- Order a sweep seed-major, not stage-major, so a run cut short still answers something —
  and report `n` per row.
- Sweep drivers get one BLAS thread per worker for free: `tools/assays.py` sets the BLAS
  thread variables before numpy loads, and `pooled()`'s workers inherit them. A driver that
  does not import `assays` first can call `worm.threads.pin_blas_threads(1)` before numpy
  itself; none currently needs to.
