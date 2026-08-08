# Project architecture and intent

**Read this first.** It is the compass, not the map. It says what the project is *for*, what
must never be conflated, and which invariants a change is allowed to move. It deliberately
contains almost no implementation detail — that lives in `README.md`, `wasm/README.md`,
`web/README.md` and in the source, all of which are linked from here.

If you are an agent or a new maintainer, the intended reading order is:

1. this file — what kind of project this is (~10 minutes);
2. [`NEXT.md`](../NEXT.md) — what we are doing right now;
3. [`docs/runtime-parity.md`](runtime-parity.md) — what the browser runtime does and does not implement;
4. the subsystem document for whatever you are touching;
5. [`docs/research-log/`](research-log/) — only when you need to know what was already tried.

---

## 1. There are two tracks, and they must not blur

This repository serves two long-term purposes. They share code. They do not share
epistemic status.

### Track A — Reference *C. elegans*

A reconstruction. The goal is a convincing simulated roundworm, viewable in a browser,
built from the real animal downwards. Every line below mixes things of different epistemic
status, and the mixture is the point of the project — so each says which:

| Component | Reconstructed / identified | Modelled | Tuned |
|---|---|---|---|
| **Nervous system** `worm/nervous.py` | the 302 cells and their names; gap and chemical contact counts, from electron micrographs | graded non-spiking dynamics (Wicks/Kunert form); the self-consistent `V_th` solve | `g_gap`, `g_syn` per contact; synaptic timescale |
| **Neuromuscular map** `worm/muscle.py` | which neurons contact which of the 95 muscle cells | the three-stage excitation–contraction cascade | `peak_moment`; the per-cell balance that corrects for sectioning completeness and 2-D quadrant merging |
| **Sensory pathways** `worm/senses.py` | **cell identity and polarity only** — ASEL/ASER as an ON/OFF pair, AWC as an OFF cell, AFD warm, URX/AQR/PQR for oxygen, ALM/AVM and PLM for touch | adapting differential transduction; the proprioceptive receptive-field construction | every gain and adaptation time constant |
| **Proprioceptive loops** `worm/senses.py` | that B-type cells read curvature anterior to the muscles they drive (Wen et al.); that head motor neurons are themselves proprioceptive (Yeon et al.) | reach, sign and filter as implemented here | `proprio_gain`, `proprio_reach`, `head_proprio_gain`, `head_tau`, `head_delay` |
| **Command layer** `worm/senses.py` | AVB/PVC and AVA/AVD/AVE class membership | the Schmitt-trigger direction gate; the omega-turn transient | gate bias, hysteresis, cord drive, omega current |
| **Mechanics** `worm/body.py` | — | inextensible active elastica; resistive force theory at zero Reynolds | — (bending modulus and drag are **measured**) |
| **Environment** `worm/world.py` | — | steady-state diffusion fields, `D∇²c = λc` | lawn geometry, gradient scales |
| **The loop** `worm/engine.py` | — | **behaviour emerges from the sensorimotor loop; nothing in the middle is scripted** | — |

So "the model has real sensory modalities" is a claim that would blur three of those columns
at once, and it is not one this document makes. What is real is **which cells carry which
modality and with what sign**. The transduction that turns a concentration into a current,
and every gain in front of it, is modelled and tuned — and `worm/params.py` says which is
which, constant by constant. Where a phrase like "real X" appears in older prose, read it as
"routed to the cells that actually carry X".

The founding constraint, stated at the top of `tools/optimise.py` and in the README's
*Evolved animals are not C. elegans*: **the connectome is anatomy, not parameters.**
Reconstructed contact counts *are* the synaptic weights. Fitting them would throw away the
reason the model is built on a connectome at all. Measured constants — capacitance,
reversal potentials, bending modulus, drag — are treated as facts.

**Nothing in the reference worm is evolved.** That is the whole of the boundary in one line,
and §5 is the full table of the five epistemic classes.

Biological claims belong to this track and to nothing else.

### Track B — Digital Life Laboratory

An intentional departure. The eventual goal is populations of digital organisms that
compete, reproduce, mutate, diversify, and evolve — neural organisation first, potentially
morphology later. The reference worm may be the ancestor and may share the physical
substrate, but the lineage is free to leave the animal behind.

Today this track exists as: `wasm/evolve.mjs` (selection on the runtime),
`worm/genome.py` (the bounded, allow-listed genome), `wasm/population.mjs` (the invariants
that only exist when several animals share a plate), and the `Population` class in
`worm/engine.py`.

**Results from Track B are not evidence about *C. elegans*.** Not in `README.md`, not in
`NEXT.md`, not in an issue, not in a commit message.

### The line between them

The distinction has to be hard to cross by accident, because crossing it is cheap and
silently destroys the value of Track A. Four mechanisms currently hold it:

| Mechanism | Where | What it stops |
|---|---|---|
| Genome allow-list — 15 bounded scalars, no measured constant among them | `worm/genome.py::BOUNDS`, pinned to `tools/export_model.py::GENES` by `tests/test_genome.py` | A lineage mutating anatomy or a measured constant |
| Fitness that refuses unit-conversion exploits | `wasm/evolve.mjs` (`EVO_FITNESS=energy` default) | Selection paying for `volume_per_pump`-style defects (#37) |
| A measure that prints its own limitation | `wasm/eggs-fitness.test.mjs` | `EVO_FITNESS=eggs` being quoted as if it measured the egg-laying circuit |
| Conformance and the assay suite guard the *unevolved baseline only* | `tools/conform.py` + `wasm/conform.mjs`; `tests/` | An evolved genome inheriting the baseline's credibility |

**The invariant, stated so it can be cited:**

> A parameter, genome, or configuration that improves evolved fitness must never migrate
> into the reference worm's defaults on the strength of that fitness. A change to the
> reference model needs reference evidence: a measurement against a live animal, or a
> mechanical argument from anatomy or physics.

If you find yourself about to move a number from an evolution run into `worm/params.py`,
that is the moment this document exists for. Stop and get owner review.

---

## 2. The trunk

The shape both tracks are built on. This is the part where a change is a change of project,
not a change of code.

```
       anatomical / source data          data/raw_sources.json  (hash-pinned)
                  |                      tools/fetch_raw.py, tools/build_dataset.py
                  v
    immutable connectome representation  data/celegans.json -> worm/dataset.py
                  |
                  v
            neural dynamics              worm/nervous.py
                  |
                  v
           muscle activation             worm/muscle.py
                  |
                  v
            body mechanics               worm/body.py
                  |
                  v
              environment                worm/world.py
                  |
                  +------> sensory / proprioceptive feedback -----+
                                         worm/senses.py           |
                  ^--------------------------------------------- +
```

closed once per tick by `worm/engine.py::Simulation.prepare_step` / `finish_step`.

Supporting roots, each of which is load-bearing and none of which is decorative:

- **Units.** One convention, stated once, at the top of `worm/params.py`:
  mm · s · mV · pA · pF · nS · µN. Electrical rates are per-millisecond and are converted
  exactly once, inside `NervousSystem`.
- **Provenance.** Every constant in `worm/params.py` carries its source, and where the
  model departs from a published value it says which value and why.
- **Reproducibility.** Seeded RNG; frozen parameter dataclasses; a committed dataset that
  records the SHA-256 of every input it was built from.
- **Measured vs modelled vs tuned**, kept distinguishable — see §5.
- **Scientific verification.** `tests/`, `tools/assays.py`, `tools/scorecard.py`,
  `tools/audit.py`.

Two crowns grow out of that trunk: Track A above it (biological fidelity, scientific
measurement, the canonical browser animal) and Track B beside it (controlled departure,
evolvable genomes, populations, eventually morphology).

---

## 3. Shared substrate

These concepts are used by both tracks *as they exist today*. Listing them is not a design
proposal — nothing here should be redesigned to "serve both tracks" until a second consumer
actually exists and disagrees.

| Concept | Today | Shared because |
|---|---|---|
| Physics / mechanics | `worm/body.py`, `MediumParams` | Zero-Reynolds drag is not biology-specific |
| World / environment | `worm/world.py`, `wasm` `World` | A plate is a plate |
| Organism representation | `Simulation` / `Worm` | An evolved animal is still an animal |
| Population & shared world | `worm/engine.py::Population`, `stepAll` | Ecology needs it; conformance uses it |
| Neural primitives | `worm/nervous.py` | Evolvable topology will reuse the integrator |
| Muscle / body primitives | `worm/muscle.py` | Morphology evolution will reuse the moment map |
| Visualization | `web/` | One viewer, two kinds of animal |
| Measurement tooling | `tools/diagnose_loop.py`, `tools/assays.py`, `tools/stats.py` | Both tracks need honest statistics |
| Export / runtime infrastructure | `tools/export_model.py`, `wasm/assembly/` | Evolution runs on the runtime |

**Do not prematurely generalise this substrate.** The current absence of a plugin layer, a
strategy interface, or an "organism" abstract base class is intentional negative space.

---

## 4. Python and WebAssembly

### The relationship

```
Python  worm/*.py
        reference implementation
        + research experiments
        + counterfactual model paths          <-- allowed to be a SUPERSET
              |
              |  tools/export_model.py, on the CANONICAL configuration only
              v
        web/worm.model  +  wasm/assembly/model_gen.ts
              |
              v
WASM    wasm/assembly/index.ts
        the browser/runtime implementation
        the canonical shipped animal
```

**Python is the compiler; WebAssembly is the runtime.** Everything expensive that happens
once at construction — the resting-potential solve, the per-cell muscle balance, the
proprioceptive receptive fields, the drag masks — stays in Python and is exported as a block
of plain arrays. The runtime implements only the per-step arithmetic. This is why a
disagreement between the two can never be about the setup: both read the same file.

`wasm/assembly/index.ts` is **hand-written**, not transpiled. Every change to a step
function has to be made twice. `wasm/README.md` states the trade and the alternatives that
were rejected; do not relitigate it without reading that first.

### The contract

1. **Python may be a research superset.** A model path that exists only in Python is not a
   bug. Counterfactuals, retired mechanisms and half-tested ideas are allowed to live there.
2. **The runtime implements the canonical configuration.** What ships in the browser is the
   default `Params()` tree, exported and compiled.
3. **Experimental divergence is fine. Canonical divergence is dangerous.** The failure mode
   is: a Python-only path exists → someone flips its default because it measures better →
   the Python animal changes → the runtime still implements the old path → the browser and
   the reference are different animals, and nothing says so.
4. **So: turning a Python-only path into a default requires runtime parity first.** Port it
   to `wasm/assembly/index.ts`, export whatever constant selects it, extend
   `tools/conform.py` / `wasm/conform.mjs` to cover it, and only then move the default.

The current classification of every switch is in
[`docs/runtime-parity.md`](runtime-parity.md), and the machine-readable version is
`tools/export_model.py::RUNTIME_UNSUPPORTED`, pinned by `tests/test_runtime_parity.py`.

### What the runtime is checked against

- `tools/conform.py` + `wasm/conform.mjs` — step-for-step, noise off, six cases, to
  5e-13 mm on node positions and 5e-11 mV on membrane potentials.
- `tools/parity.py` — the noisy paths, compared statistically, because the two draw from
  different generators and always will.

Neither has any purchase on a path the runtime does not implement. That is the whole reason
`runtime-parity.md` exists.

---

## 5. Measured, reconstructed, modelled, tuned, evolved

Five epistemic classes. Keeping them separable is a Track A requirement and a Track B
safety property.

| Class | Example | Where it is recorded | May evolution touch it? |
|---|---|---|---|
| **Measured** | `C_m = 1.5 pF`, `EI = 9.5e-14 N·m²`, drag coefficients, reversal potentials | `worm/params.py`, with citation | **No** — absent from `BOUNDS` by design |
| **Reconstructed** | gap/chemical contact counts, soma positions, muscle roster | `data/celegans.json`, with input hashes | **No** — anatomy, baked into the payload |
| **Modelled** | the graded-neuron equations, resistive force theory, the three-stage EC cascade | `worm/params.py` docstrings, `README.md` | Structure no; some rate constants yes |
| **Calibrated / tuned** | `proprio_gain`, `head_proprio_gain`, `cord_drive`, gate thresholds | `worm/params.py`, `tools/optimise.py::SPACE` | **Yes** — this is what `BOUNDS` is |
| **Evolved** | anything out of `wasm/evolve.mjs` | never in `worm/params.py` | n/a — it is the output |

A correction to a *measured* value needs a citation. A change to a *tuned* value needs a
paired comparison on identical seeds (`tools/compare.py`). An *evolved* value needs owner
review before it is even discussed as a model change.

---

## 6. Deployment philosophy: static-first

The canonical viewer requires **no backend**. `web/` is native ES modules with no build
step and no dependencies; the animal is compiled to WebAssembly and runs in the visitor's
tab. The production image is `nginx:alpine` with a directory of static files
(`Dockerfile`, `docker/nginx.conf`).

The intent, stated as a requirement:

> No always-on simulation server should be necessary merely to view or use the canonical
> worm. Client-side computation is the default, and a static file host is a complete
> deployment.

Two things this does **not** say:

- It does not say servers are forbidden. `worm/server.py` exists and is supported: `?server`
  is how the *Python* model is driven, and it is the only way to watch the reference
  implementation rather than the port. It is a development and research affordance.
- It does not rule out optional services forever. It says an always-on backend is not
  currently part of the canonical requirement, and a change that makes one *necessary* is a
  change of deployment philosophy that needs owner review.

The no-build-step constraint on `web/` follows from the same requirement: a toolchain in
front of the viewer would take back the property the WASM port exists to provide.
`tools/check_web.mjs` and `tools/check_cache_headers.mjs` enforce it.

### Where Track B fits without breaking this

A plausible direction, recorded so it is not reinvented, and **not** a commitment:

- **Small / local evolution** — browser → WASM → Web Workers → local populations. Static
  hosting is preserved; the visitor's machine pays.
- **Large / offline evolution** — workstation or compute cluster → lineage and genome
  artifacts → published as static files → the browser *replays and visualises* them rather
  than computing them.

Both keep "no required always-on backend" true. Neither is built. See `NEXT.md` for what is
actually next.

---

## 7. Invariants a change should not break silently

A short checklist. If your change touches one of these, say so explicitly in the commit.

1. Reconstructed contact counts are not fitted, tuned, or evolved.
2. Measured constants change only with a citation.
3. Behaviour emerges from the loop; nothing in the middle is scripted.
4. One unit convention, converted at exactly one place per quantity.
5. Evolved results never become biological claims.
6. A Python-only model path does not become a default without runtime parity.
7. The canonical viewer needs no backend.
8. Negative results, failed experiments and retractions are preserved, not tidied away.
9. A check is worth what it covers — see `tools/audit.py`; a green suite is not evidence
   until you have watched the check fail.
10. `NEXT.md` stays short. History goes to `docs/research-log/`.

---

## 8. Map of the documents

| Document | Answers |
|---|---|
| `docs/project-architecture.md` (this) | What kind of project is this? What must not blur? |
| [`NEXT.md`](../NEXT.md) | What should we do next? |
| [`docs/runtime-parity.md`](runtime-parity.md) | Does the browser runtime implement this path? |
| [`README.md`](../README.md) | What does the model do, and how well? How do I run it? |
| [`wasm/README.md`](../wasm/README.md) | How is the port split, and what is it checked against? |
| [`web/README.md`](../web/README.md) | Which viewer module owns this pixel/event/number? |
| [`tools/README.md`](../tools/README.md) | Which tool measures this, and is it infrastructure or a one-shot? |
| [`data/README.md`](../data/README.md) | How is the anatomy sourced and rebuilt? |
| [`docs/research-log/`](research-log/) | What was already tried, and what did it fail at? |
| [`docs/architecture/`](architecture/) | Why is the repository shaped the way it is? Records of maintainability passes. |
