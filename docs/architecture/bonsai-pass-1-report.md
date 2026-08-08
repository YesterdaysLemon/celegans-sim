# Bonsai Pass 1 — report

*Expose the intended silhouette, separate attention from memory, make the repository legible
to future humans and agents.*

**Date:** 2026-08-08 · **Branch:** `claude/repo-architecture-investigation-w43stj` ·
**Base:** `0f7c25b` (identical to `main` at the time of the pass)

This pass changed **no model behaviour**. Its output is documentation, one guardrail test,
and one narrow prose correction backed by remeasurement.

---

## A. Baseline

The repository at `0f7c25b`: 141 commits over eight days (2026-07-29 → 2026-08-05),
~18 commits/day. Roughly 6.7k lines under `worm/`, 12.7k under `tools/`, 6.5k under `wasm/`,
4.6k under `tests/`, 3.5k under `web/` — and **282 kB of markdown**.

Three information bottlenecks, all measured rather than asserted:

| Bottleneck | Evidence |
|---|---|
| **`NEXT.md` had become the research log.** It answered "what should we do next" and "what did we already try" in one 181,216-byte, 2,934-line document, up 63% in its final seven days and never once shorter. It had grown its own *Start here* section because it could no longer be read front to back. | `git log` on `NEXT.md`, sizes per commit |
| **The two-track project identity existed nowhere in the tree.** The reconstruction and the digital-life laboratory share physics, world, organism representation, viewer and measurement tooling, and share nothing epistemically. Four mechanisms already defended the line; none of them said what the line *was*. | `grep` — no file described the second track |
| **Python-only model paths were undocumented and unguarded.** Nothing recorded which switches the runtime implements, and a fresh read of the repository got the answer wrong in both directions. | see §D |

Secondary: `tools/diagnose_loop.py` (42 importers) and `tools/assays.py` (32) described
themselves as printers; ~25 tools had no importer, no reference and no documentation.

---

## B. Owner-intent encoding

| Intent | Now recorded in |
|---|---|
| **Track A — Reference *C. elegans*** | `docs/project-architecture.md` §1, §2, §5 |
| **Track B — Digital Life Laboratory** | `docs/project-architecture.md` §1, §6 |
| **The two must not blur** | `docs/project-architecture.md` §1 "The line between them" — a table of the four mechanisms that already hold it (`worm/genome.py::BOUNDS`, the `energy` fitness measure, `wasm/eggs-fitness.test.mjs`, and conformance guarding only the unevolved baseline), plus the invariant stated so it can be cited in review |
| **Static-first deployment** | `docs/project-architecture.md` §6, including two explicit non-claims: servers are not forbidden, and `worm/server.py` remains supported |
| **Python as research superset** | `docs/project-architecture.md` §4, `docs/runtime-parity.md` |
| **WASM as canonical shipped configuration** | same, plus the four-step porting procedure that must precede a default change |
| **Shared substrate** | `docs/project-architecture.md` §3 — described as it exists today, with an explicit instruction not to generalise it before a second consumer disagrees |
| **Reading order for a fresh maintainer** | `README.md` (a six-line pointer, near the top) and `docs/project-architecture.md` §8 |

The compass is 15.6 kB. It states teleology and invariants and links out for everything
else, because a second 180 kB document would move the context problem rather than solve it.

---

## C. `NEXT.md` transformation

| | Before | After |
|---|---|---|
| Size | 181,216 B | **8,607 B** (−95.3%) |
| Lines | 2,934 | 156 |

**Archival destination:** `docs/research-log/next-history-through-2026-08-04.md`, named for
the last commit that modified it (`987129c`, 2026-08-04).

**Proof of preservation.** Moved with `git mv`, so the archive is a tracked rename:

```
sha256(NEXT.md @ 0f7c25b)  = 78077ac31a7160b68cc103da0bd9f5c56b90aad9701b8e2c1713ac5bb8aa845e
sha256(archive @ HEAD)     = 78077ac31a7160b68cc103da0bd9f5c56b90aad9701b8e2c1713ac5bb8aa845e
git log --follow           → 30 commits, the full history of NEXT.md
```

Byte-for-byte. Not a heading, not a retraction, not a stale line was edited in transit —
including two statements that are stale *now* (a *Third tier* still asking for a viewer
scrubber that exists, a *Second tier* its own later sections revise). Those stay because
they are the evidence for why an append-only roadmap stops being one, and
`docs/research-log/README.md` says so explicitly.

**How live tasks were selected.** From the archive's own *Start here* section, cross-checked
against the current repository, and kept only where the item is still open. Three
reference-worm items, three Digital Life items, three infrastructure items. The four
already-eliminated gait-modulation mechanisms are carried forward as a *do not re-run* table
— that is history, but it is history whose entire purpose is to prevent future work, which
makes it a roadmap entry rather than a narrative.

Nothing was invented. Items whose priority the repository cannot settle went to **Blocked, or
needs an owner decision** rather than being guessed at (§13).

**Unresolved owner-priority questions**, now visible in `NEXT.md`:

1. Reach sweep first, or the cascade port? Both touch the shared gait; no engineering
   argument settles the order.
2. Do the 25 uncertain tools get archived under `tools/experiments/`?
3. Is `tools/optimise.py` still a live path now that `wasm/evolve.mjs` exists?

**Two machine references followed the text.** `wasm/memory.mjs` asserted the per-worm memory
figure against `NEXT.md`; that claim moved with the document, so `QUOTES` now names the
archive. The live roadmap makes no memory claim and should not be made to carry one.
`tests/test_ci_policy.py::NO_CI_NEEDED` was updated for the same reason, and its caveat about
the unguarded-prose hole moved to the entry it now applies to. Both checks pass.

---

## D. Runtime parity map

Recorded in `docs/runtime-parity.md`, with three routes a parameter can take to the runtime.

**Correction to a previous reading of this repository.** An earlier fresh-agent audit
reported that `gate_latched`, `head_distributed`, `head_delay` and `omega_reflex_suppression`
were Python-only. **They are not.** All four are exported as compile-time constants and
`wasm/assembly/index.ts` implements *both* branches of each. The runtime is less frozen than
it looks, and "the runtime cannot do X" is an expensive thing to believe falsely.

**Python-only, verified by AST sweep plus grep of the exporter and both runtime files:**

| Family | Parameters | Default | Status |
|---|---|---|---|
| Head-reflex cascade | `sensory.head_stages`, `sensory.head_stage_tau` | `1`, `0.0` (off) | `REFERENCE_EXPERIMENTAL` — live adoption candidate |
| Muscle force-velocity | `muscle.fv_vmax` (+ `fv_curvature`, `fv_eccentric`, `fv_tau`) | `0.0` (off) | `HISTORICAL_EXPERIMENT` / `DIGITAL_LIFE_CANDIDATE` — measured, not adopted |
| Omega wave suppression | `sensory.omega_wave_suppression` | `0.0` (off) | `REFERENCE_EXPERIMENTAL` |

The cascade pair is the subtle one: both are read in `Senses.__init__`, which looks like
construction-time, but what they build is a *step-time branch* (`_head_chain`) rather than an
array the payload could carry. Construction-time reads are only safe when the thing
constructed is data.

**Guardrail added.** `tools/export_model.py::RUNTIME_UNSUPPORTED` is the registry — data
only; nothing in the export reads it, because an exporter that refused to run would block the
experiments Python exists to host. `tests/test_runtime_parity.py` asserts the shipped
`Params()` still sits on those values, and includes a `test_the_guard_would_actually_fire`
case so the check is not trusted unwatched.

It has been watched to fail. Setting `head_stages = 4`:

```
AssertionError: sensory.head_stages defaults to 4, but the WebAssembly runtime
implements only 1.
  1. implement it in wasm/assembly/index.ts
  2. export the constant that selects it from tools/export_model.py
  3. extend tools/conform.py and wasm/conform.mjs to cover both sides
  4. rebuild web/worm.model and web/worm.wasm as a pair, and run conformance
  5. drop 'sensory.head_stages' from RUNTIME_UNSUPPORTED, in this commit
```

`worm/params.py` was restored byte-identical afterwards.

**What the guard does not cover**, stated in the document so coverage is not overestimated: a
*new* Python-only path added and left off is not detected; deleting a Route-2 branch from the
runtime is not detected; Route-1 staleness is the `dataset` job's business.

**Future guardrail recommended, not built:** a check that the runtime still implements both
branches of every Route-2 switch. Conformance only exercises the shipped configuration, so
the unused branch is currently unguarded.

---

## E. Tooling silhouette

`tools/README.md` classifies all 70-odd files by **measured** importer count, reference count
and last-touched date — never by filename. Each one-line purpose is its own docstring's first
line, not a guess.

| Class | n | Examples |
|---|---|---|
| `CORE_INFRASTRUCTURE` | 15 | `export_model.py`, `conform.py`, `build_dataset.py`, `audit.py`, `check_all.mjs`, `manifest.py` |
| `MEASUREMENT_LIBRARY` | 4 | `diagnose_loop.py` (42 importers), `assays.py` (32), `stats.py` (6), `coherence.py` (3) |
| `MAINTAINED_INSTRUMENT` | 24 | `kymo.py`, `scorecard.py`, `compare.py`, `ethogram.py`, … |
| `ACTIVE_EXPERIMENT` | 5 | `head_cascade.py`, `head_medium.py`, `lag_span.py`, `force_velocity.py`, `damping_sweep.py` |
| `UNCERTAIN` | **25** | no importers, no references, untouched since the first days |

The 25 are labelled uncertain rather than dead. No importers is evidence, not proof; several
are cited by name in the research log; a probe is cheap to keep and expensive to reconstruct.
**Nothing was moved or deleted.**

Four symbols are private by name and imported across modules anyway — `_dispatch`,
`_clean_plate` (`assays`), `_dominant` (`diagnose_loop`), `_output_position`
(`worm/senses.py`). Each owning module's docstring now says so. The three library docstrings
also state the blast radius: changing what a key of `analyse()` means, or how an assay is
scored, makes every number already in `docs/research-log/` incomparable with every future
one, silently, with nothing to fail.

---

## F. Scientific documentation corrections

**One.** `tests/test_behaviour.py::test_medium_changes_the_gait`.

Its docstring said the model *"gets it backwards: ~1.25 Hz on agar and ~0.55 Hz in buffer"*.
`README.md`'s limitations section says the opposite — *"gait modulation points the right way
now"*, 0.66 Hz agar against 0.85 Hz buffer — and so does the three-medium sweep in the
research log. The assertion (`ratio > 1.2`) is direction-free, which is why the suite could
not see the contradiction.

**This was not adjudicated between two prose sources.** It was remeasured, through the test's
own configuration (`analyse`, 20 s, bare world, `sim.body.medium` swapped in place):

| seed | agar Hz | buffer Hz | ratio |
|---|---|---|---|
| 3 | 0.6500 | 0.8500 | 1.308 |
| 5 | 0.7000 | 0.8500 | 1.214 |
| 11 | 0.6500 | 0.8500 | 1.308 |

Buffer faster at every seed. The docstring was stale; the README was current. Only prose
changed.

**The assertion was deliberately left alone**, per the pass's own scope: tightening it or
making it directional is a change to a scientific acceptance criterion and wants its own
commit, its own seed count and its own argument. The docstring now records that, and the
observation that the margin above 1.2 is thin at some seeds.

A targeted search found no other instance of the same claim outside the archive.

---

## G. Things deliberately left alone

Tempting refactors declined, with the reason:

| Declined | Why |
|---|---|
| Splitting `worm/senses.py` (the command layer out of sensory transduction) | Out of scope; it is a step function, so it costs a double implementation and a conformance run |
| Splitting `wasm/assembly/index.ts` (2,346 lines, 5.1× growth in 5 days) | Real risk of breaking a working artifact for readability |
| Consolidating the WASM bootstrap duplicated across 8 files | Genuine duplication, but a Pass 2 change with its own validation |
| `worm/params.py`'s structure and 58% comment density | The comments *are* the provenance. Splitting it is the most tempting and most harmful change available |
| `worm/body.py` drag assembly, `worm/nervous.py` gap iteration, `worm/world.py::_settle_by_claim` | Load-bearing and verified; `_settle_by_claim` is a floating-point transcription whose iteration order matters |
| Removing `Simulation.snapshot()` (zero callers) and an unused `import time` | Trivially safe, but out of scope for a pass whose value is *not changing code* |
| Deleting or moving any of the 25 uncertain tools | Owner decision; classification first |
| `web/worm.js` / `web/worm.d.ts` (generated bindings nothing loads) | Same — needs an owner call on the `asconfig` binding mode |
| Unifying the three medium-setting routes | Verified equivalent today (nothing but `Body.__init__` reads `p.medium`); documented as a future candidate rather than redesigned |
| Strengthening `test_medium_changes_the_gait`'s assertion | §F |

---

## H. Future bonsai candidates (max five, ranked)

1. **Command-layer extraction from `worm/senses.py`** — `WIRE`. `sense()` is 262 lines
   spanning seven scientific subsystems *plus* the forward/backward gate, the omega turn, the
   descending drive and the head oscillator. `SensoryParams` is 919 lines. Largest single
   context load in the model. Needs a conformance run and a port; not a documentation change.
2. **Runtime "both branches still exist" guard** — `DOCUMENT` → then `WIRE`. Closes the gap
   §D names: conformance exercises only the shipped configuration, so deleting an unused
   Route-2 branch is invisible.
3. **Node-side WASM loader consolidation** — `CONSOLIDATE`. The
   `readFileSync` → instantiate → `alloc(payload.length + 8)` → `(raw + 7) & ~7` →
   `setPayload` sequence is byte-identical across seven `.mjs` harnesses. Node-side only —
   do **not** force `web/local.js` into it; the browser fetches rather than reads.
4. **Archive the finished one-shot tools** — `NEEDS HUMAN TASTE`. 25 candidates classified;
   how much of the record should stay executable is not an engineering question.
5. **`wasm/assembly/index.ts` decomposition along Python subsystem boundaries** —
   `NEEDS HUMAN TASTE`. Would make the two implementations file-for-file comparable and cut
   the largest context cost on the runtime side. Also the change most likely to break a
   working artifact for readability alone.

Not executed. That is the point of Pass 1.

---

## I. Fresh-agent context impact

Estimated *first read before a safe change*, before and after:

| Task | Before | After |
|---|---|---|
| **Viewer change** | `web/README.md` (6.5 kB) — already excellent | `web/README.md`. Unchanged; it was already the best compressor in the repo |
| **Reference-model change** | `README.md` 64 kB + `NEXT.md` 181 kB + `worm/params.py` 2,387 lines, with no way to know which was current | `docs/project-architecture.md` 15.6 kB + `docs/runtime-parity.md` 9.5 kB + the relevant `params.py` section. **~245 kB → ~25 kB** before touching source |
| **Runtime/WASM change** | `wasm/README.md` + grep `index.ts` to discover what exists | `docs/runtime-parity.md` answers "does the runtime implement this?" directly, with the porting procedure |
| **Digital Life change** | Nothing described the track at all; the boundary lived in the owner's head | `docs/project-architecture.md` §1 and §5 |
| **"What should I work on?"** | Read 181 kB and infer | `NEXT.md`, 8.6 kB, one sitting |

The archive is *larger* to read than the old `NEXT.md` was — but it is now reached
deliberately, when the question is "has this been tried?", instead of being the only door
into the roadmap.

---

## J. Hidden-context delta

Questions the previous fresh-agent audit could not answer from the repository, and their
status now:

| Question | Now |
|---|---|
| Is `NEXT.md` a lab notebook or a handover document? | **Answered** — a roadmap; the notebook is `docs/research-log/`, with handling rules |
| Is the WASM port meant to converge on Python, or stay a snapshot? | **Answered** — `docs/project-architecture.md` §4: Python is a superset by design; the runtime carries the canonical configuration |
| Are the retired model switches kept for re-measurement, or finished? | **Answered per switch** — `docs/runtime-parity.md`, with a status for each |
| Which tooling is infrastructure? | **Answered** — `tools/README.md`, from measured importer counts |
| Is `tools/optimise.py` still live? | **Still owner-only** — surfaced in `NEXT.md` Blocked |
| Are `tools/`'s one-shots finished? | **Partially** — 25 named as uncertain; disposition is owner-only |
| Does the project want a Digital Life track at all, and where does it end? | **Answered for existence and boundary**; scope beyond that is owner-only |

Five of seven moved from hidden to documented. The two that did not are genuine taste calls
and are now *visible* as such rather than absent.

---

## K. Bonsai verdict

```
coherent small system → GROWING BUT LEGIBLE → architecture under strain → context-dependent → sprawl
                              ▲ was here                ▲ and drifting this way
                              ▲ still here, no longer drifting
```

**The repository was and remains "growing but legible."** The pass did not move it leftward
on structure — no structure changed — but it removed the two vectors that were pushing it
right:

- the append-only roadmap now has a lifecycle and a home for history, so the document that
  must stay short can stay short;
- the Python/WASM divergence that no check could see now has a registry, a test, and a
  written procedure.

What is left pushing right is real and unaddressed by design: `wasm/assembly/index.ts` at
2,346 lines and 5.1× growth in five days, and eight copies of the WASM bootstrap. Both are
Pass 2 candidates.

The honest summary from the pre-pass audit stands, with one clause resolved: *this
repository's documentation is a genuine competitive advantage and was also its largest
unmanaged asset.* It is now managed — attention and memory are different files with
different rules.

---

## Validation

No simulation behaviour changed, and that is asserted rather than assumed.

**Behavioural fingerprint**, captured before the pass and re-run after: `Params()`, seed 7,
3.0 s closed loop, SHA-256 over node positions, membrane potentials, muscle tension and body
angles:

```
before  a9d09d6312bcf621fe288ff7402d1dc9b35ed928e306ded5f30c514bc1d307f2
after   a9d09d6312bcf621fe288ff7402d1dc9b35ed928e306ded5f30c514bc1d307f2   IDENTICAL
```

**Change surface** — `git diff --name-only 0f7c25b..HEAD`, checked against the sensitive set:

| Area | Files changed |
|---|---|
| `worm/` | **0** |
| `data/` | **0** |
| `wasm/assembly/` | **0** |
| `web/worm.model`, `web/worm.wasm`, `web/build.json` | **0** |
| `docker/`, `.github/workflows/` | **0** |

No connectome change, no model default change, no physical equation change, no WASM
step-function change, no regenerated artifact, no measured constant changed.

The only executable edits are `tools/export_model.py` (**purely additive** — a data-only
constant no code path reads) and `wasm/memory.mjs` (one path in `QUOTES`, following the
document the claim lives in). The three tool-library edits are purely additive docstrings.

**Checks run:**

| Check | Result |
|---|---|
| `node tools/check_web.mjs` | acyclic, all imports resolve |
| `node wasm/memory.mjs` | PASS — 239,360 B / 234 kB in 4 files, share 89% |
| `node wasm/population.mjs` | PASS |
| `node --test wasm/{invariants,solve,eggs-fitness,conform-inputs}.test.mjs` | 14 pass, 0 fail |
| `node --test tools/sim_rate.test.mjs` | 4 pass, 0 fail |
| module parse sweep (`node --check`, all of `web/`, `tools/*.mjs`, `wasm/*.mjs`) | all parse |
| `pytest tests/test_ci_policy.py tests/test_local_checks.py` | 50 pass |
| `pytest tests/test_runtime_parity.py` | 6 pass, and watched to fail on a flipped default |
| `pytest tests/test_behaviour.py::test_medium_changes_the_gait` | pass |
| `pytest tests/` minus `test_behaviour`/`test_audit` | *(running at the time this line was written; result appended below)* |
| Link check across all 9 markdown documents | 0 broken |
| Every symbol/path asserted in the new docs | all resolve |

Not run: the full `tests/test_behaviour.py` (~30 min of simulation) and `tools/audit.py`,
on the grounds that the trajectory fingerprint is a stronger and cheaper non-interference
proof than re-running scientific assays that no changed line can reach. Also not run:
`npm run check --rebuild`, which regenerates tracked artifacts — deliberately, since this
pass must not regenerate any.
