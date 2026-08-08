# tools/ — the instrument shelf

Seventy-odd files live here and they are not the same kind of thing. Some are load-bearing
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
| **MAINTAINED_INSTRUMENT** | A measurement you are meant to reach for. Documented in `README.md`, and expected to still work. |
| **ACTIVE_EXPERIMENT** | Tied to a currently-open question in `NEXT.md`; touched in the last few days of active work. |
| **UNCERTAIN** | No importers, no references, untouched since the first days. *Probably* a finished one-shot — but "probably" is the honest word, and none of them has been confirmed dead. |

The evidence columns are `imp` (modules importing it), `ref` (files mentioning its path) and
`last` (last commit touching it). They were measured, not guessed. A tool cited only in
`docs/research-log/` is marked `log` — that means it has historical standing, not that it is
current.

---

## CORE_INFRASTRUCTURE

Touch these and something else stops building.

| tool | imp | ref | does |
|---|---|---|---|
| `export_model.py` | 2 | 18 | Freezes the model into `web/worm.model` + `wasm/assembly/model_gen.ts`. Also owns `GENES` and `RUNTIME_UNSUPPORTED`. |
| `conform.py` | 0 | 8 | Reference trajectories the WebAssembly port is checked against. Paired with `wasm/conform.mjs`. |
| `build_dataset.py` | 0 | 5 | Raw anatomy → validated `data/celegans.json`. Assertion-heavy on purpose. |
| `fetch_raw.py`, `fetch_raw.sh` | 0 | 3 | Download the exact bytes approved in `data/raw_sources.json`, fail-closed on hash. |
| `raw_sources.py` | 1 | 0 | The pinned source manifest and its verification helpers. |
| `check_model_artifacts.py` | 1 | 2 | Fails when committed browser artifacts are stale against a fresh export. |
| `manifest.py` | 0 | 0 | Content-hashes the runtime assets so `immutable` caching is safe. Run by the Docker build. |
| `audit.py` | 0 | 3 | Breaks things on purpose and reports which check notices. The meta-check. |
| `parity.py` | 0 | 2 | Python vs WASM, noise **on**, compared statistically. |
| `check_all.mjs` | 0 | 3 | Runs every gate CI would, in the workflows' order. A skip is never a pass. |
| `check_web.mjs` | 0 | 6 | Viewer module graph: cycles, unresolved imports, leftovers. |
| `check_cache_headers.mjs` | 0 | 3 | Every served asset has a deliberate cache policy. |
| `smoke_web.mjs` | 0 | 5 | The viewer in a real browser, desktop and mobile. |
| `smoke_server.mjs` | 0 | 4 | The `?server` transport against a live Python model. |
| `sim_rate.test.mjs` | 0 | 4 | The rate readouts measure what their labels claim. |

## MEASUREMENT_LIBRARY

**These look like scripts and are not.** They have command-line front ends, which is how they
came to be misread as one-offs, but their importers outnumber every other file here.

| tool | imp | the imported surface |
|---|---|---|
| `diagnose_loop.py` | **42** | `analyse`, `bare_world`, `travelling_index`, `_dominant`. `analyse`'s return dict is this project's operational definition of "what the gait is doing". |
| `assays.py` | **32** | `pooled`, `estimate`, `run_trial`, `reversals`, `SAMPLE_DT`, `ASSAYS`, `DURATIONS`, `ORDER`, `THROUGHPUT`, `WORKERS`, `_dispatch`, `_clean_plate`. |
| `stats.py` | 6 | `bootstrap_ci`, `paired_ci`, `ratio_ci`, `mde`, `verdict`, `fmt`, `BOOTSTRAP`. Reached transitively by everything through `assays`. |
| `coherence.py` | 3 | `profile` — per-position wave coherence. A small library rather than a hub, but it has importers and no documentation elsewhere. |

Four of those symbols are private by name and imported across modules anyway: `_dispatch`,
`_clean_plate`, `_dominant`, and (from `worm/senses.py`) `_output_position`. Renaming one is
a cross-module change. Each module's own docstring now says so.

Changing what a key of `analyse` *means*, or how an assay is *scored*, silently makes every
number already recorded in `docs/research-log/` incomparable with every future one, with
nothing to fail. Add keys and assays; do not repurpose them.

## MAINTAINED_INSTRUMENT

Documented in `README.md`'s layout table and expected to still work. Reach for these by name.

| tool | does |
|---|---|
| `kymo.py` | ASCII kymograph. **Look at the picture first** — a lot of time has gone into inferring behaviour from summary statistics that were hiding a statically bent worm. |
| `scorecard.py` | Every headline number at once, across seeds, in three media. The README's table comes from here. |
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
| `optimise.py` | Fits the handful of unmeasured parameters against behavioural targets. **See the open question in `NEXT.md`** — its `SPACE` overlaps `worm/genome.py::BOUNDS` and only one of the two lists is pinned by a test. |

## ACTIVE_EXPERIMENT

Tied to open questions. All last touched in the final days of active work.

| tool | last | question |
|---|---|---|
| `head_cascade.py` | 2026-08-04 | Can a cascade of head-cell lags buy what the invented delay was buying? |
| `head_medium.py` | 2026-08-04 | Does the cascade's phase follow the mechanical load? *(Answered: no.)* |
| `lag_span.py` | 2026-08-04 | Does cutting the fixed lag widen the modulation span? *(Answered: barely.)* |
| `force_velocity.py` | 2026-08-04 | Does a force-velocity curve widen it? *(Answered: it narrows it.)* |
| `damping_sweep.py` | 2026-08-04 | Is the buffer-end frequency set by internal damping? *(Answered: no.)* |

Four of the five are negative results, and that is the point of listing them: the answers are
in `NEXT.md`'s do-not-re-run table, and the reasoning is in `docs/research-log/`.

## UNCERTAIN — probably finished one-shots, not confirmed

No importers, no references outside their own file, and untouched since the earliest days of
the project. Each answered a specific question during a specific investigation; several are
cited by name in the research log, which is why none has been moved.

**Do not delete these on the strength of this table.** "No importers" is evidence, not proof,
and a probe is cheap to keep and expensive to reconstruct. Whether they eventually move to
`tools/experiments/` is an owner decision recorded in `NEXT.md`.

| tool | asked | cited in log |
|---|---|---|
| `adapt_moment.py` | Recover curvature amplitude via muscle strength, with the receptor adapting | |
| `adaptation.py` | Does adapting the stretch receptor let the wave travel? | |
| `chemo_gain_sweep.py` | Can chemosensory gain alone produce chemotaxis? | |
| `common_drive.py` | Is a shared oscillating drive forcing the motor neurons into lockstep? | |
| `coupling_strength.py` | How much muscle-muscle coupling keeps the tail coherent? | |
| `efficacy.py` | Is the efficacy gradient attenuating the wave before the tail? | |
| `gate_calibrate.py` | Place the direction gate and size the cord drive | |
| `gate_sweep.py` | Why the animal never reverses, and what letting him costs | |
| `head_balance.py` | Retest the head reflex now the body reflex works | |
| `ml_scan.py` | Search Morris-Lecar space for a usable conditional oscillator | |
| `modulator_sweep.py` | Calibrate the modulator layer against basal slowing | |
| `moment_candidate.py` | Test the `peak_moment` candidate, and the ratio caveat | |
| `muscle_leak.py` | Is the coupling weak, or is the muscle leak too high? | |
| `noise_test.py` | Is the tail's incoherence just amplified background noise? | |
| `osc_control.py` | Separate the two changes | log |
| `osc_entrain.py` | Oscillator strength against proprioceptive coupling | |
| `osc_sweep.py` | Conditional-oscillator parameters in the full closed loop | |
| `phase_profile.py` | Where along the chain does the phase gradient get lost? | |
| `pool_probe.py` | Does `pooled()` lose jobs when there are more than workers? | |
| `reflex_gain.py` | Per-segment gain of the proprioceptive reflex | log |
| `reversal_test.py` | Does the animal reverse now both cords are regenerative? | |
| `stiffness.py` | Does bending stiffness decide travelling vs standing? | |
| `tau_sweep.py` | `adapt_tau` at the critically-poised operating point | |
| `twi_by_region.py` | Is the travelling-wave ceiling the head dragging the average down? | log |
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
- Population and sweep drivers should call `worm.threads.pin_blas_threads(1)` **before**
  importing numpy.
