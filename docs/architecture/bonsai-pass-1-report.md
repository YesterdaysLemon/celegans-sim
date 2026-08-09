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
~18 commits/day. Roughly 6.7k lines under `worm/`, 13.7k under `tools/` (`.py` + `.mjs`), 6.5k under `wasm/`,
4.6k under `tests/`, 3.5k under `web/` — and **282 kB of markdown**.

Three information bottlenecks, all measured rather than asserted:

| Bottleneck | Evidence |
|---|---|
| **`NEXT.md` had become the research log.** It answered "what should we do next" and "what did we already try" in one 181,216-byte, 2,934-line document, up 63% in its final seven days and never once shorter. It had grown its own *Start here* section because it could no longer be read front to back. | `git log` on `NEXT.md`, sizes per commit |
| **The two-track project identity existed nowhere in the tree.** The reconstruction and the digital-life laboratory share physics, world, organism representation, viewer and measurement tooling, and share nothing epistemically. Four mechanisms already defended the line; none of them said what the line *was*. | `grep` — no file described the second track |
| **Python-only model paths were undocumented and unguarded.** Nothing recorded which switches the runtime implements, and a fresh read of the repository got the answer wrong in both directions. | see §D |

Secondary: `tools/diagnose_loop.py` (42 importers) and `tools/assays.py` (32) described
themselves as printers; ~25 tools had no importer and no documentation (six turned out to be referenced; §F.9).

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

The compass is 19.3 kB. It states teleology and invariants and links out for everything
else, because a second 180 kB document would move the context problem rather than solve it.

---

## C. `NEXT.md` transformation

| | Before | After |
|---|---|---|
| Size | 181,216 B | **6,392 B** (−96.5%) |
| Lines | 2,934 | 114 |

**Archival destination:** `docs/research-log/next-history-through-2026-08-04.md`, named for
the last commit that modified it (`987129c`, 2026-08-04).

**Proof of preservation.** Moved with `git mv`, so the archive is a tracked rename — and the
strongest available form of the claim is not a content hash but the Git object identity:

```
git rev-parse 0f7c25b:NEXT.md                                   = 12da57c83f0b80a0b7907fd75536325ab044bea8
git rev-parse HEAD:docs/research-log/next-history-through-…md    = 12da57c83f0b80a0b7907fd75536325ab044bea8
sha256 of both                                                  = 78077ac3…845e
git log --follow                                                → 30 commits, the full history of NEXT.md
```

The same blob object, not merely equal bytes: Git stored no second copy, so there was no
re-encoding step in which anything could have changed. Not a heading, not a retraction, not a
stale line was edited in transit —
including two statements that are stale *now* (a *Third tier* still asking for a viewer
scrubber that exists, a *Second tier* its own later sections revise). Those stay because
they are the evidence for why an append-only roadmap stops being one, and
`docs/research-log/README.md` says so explicitly.

**How live tasks were selected.** From the archive's own *Start here* section, cross-checked
against the current repository, and kept only where the item is still open. Three
reference-worm items, three Digital Life items. The four already-eliminated gait-modulation
mechanisms are carried forward as a *do not re-run* table — that is history, but it is
history whose entire purpose is to prevent future work, which makes it a roadmap entry rather
than a narrative.

Nothing was invented. Items whose priority the repository cannot settle went to **Blocked, or
needs an owner decision** rather than being guessed at; see §C's owner-priority list.

**What was taken back out during review.** The first cut of this pass still had a roadmap
doing three jobs. Removed, each because it belongs somewhere that already holds it:

| Removed from `NEXT.md` | Because it lives in |
|---|---|
| *Recently completed* — five items | Every one was already recorded elsewhere; checked individually before removal (the scrubber in `README.md`, the rest in `wasm/README.md`, `worm/world.py` and the archive). A roadmap that lists finished work is a changelog. |
| CI status, `CI_ENABLED`, the `npm run check` commands | `README.md` §*Running the checks yourself* — verbatim, and it was already there when the duplicate was written |
| "a check is not real until you have watched it fail" | `docs/project-architecture.md` §7, invariant 9 |
| The runtime-parity guardrail as a standing item | `docs/runtime-parity.md`; the cascade item links to it at the point where it actually blocks work |
| Per-metric result narration (travelling indices, net speeds) | `docs/research-log/`. One decisive number per item is enough to decide with; the rest is evidence, not intent. |

A closing table now says where each of those went, so the roadmap answers "what next" and
routes everything else in one line rather than absorbing it.

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

## D. Runtime parity map, and model-path lifecycle

Recorded in `docs/runtime-parity.md`, which is built around **two independent axes** —
because the first cut of this pass ran them together and got answers that looked like status
and were really two different facts glued into one label:

| Axis | Question | Settled by |
|---|---|---|
| Runtime support | Does `wasm/assembly/index.ts` implement this? | reading the source |
| Scientific lifecycle | Is the path any good? | measurement, or nothing |

The case that proves they are independent is `omega_reflex_suppression`: **fully implemented
in the runtime and scientifically refuted.** `params.py` records "it was tried, and it does
nothing", every interval overlapping every other, and keeps it — implemented, exported,
running in the browser, permanently at 0.0 — because the refutation is the useful part.

**Correction to a previous reading of this repository.** An earlier fresh-agent audit
reported that `gate_latched`, `head_distributed`, `head_delay` and `omega_reflex_suppression`
were Python-only. **They are not.** All four are exported as compile-time constants and
`wasm/assembly/index.ts` implements *both* branches of each. The runtime is less frozen than
it looks, and "the runtime cannot do X" is an expensive thing to believe falsely.

Lifecycle labels: `REFERENCE_SHIPPED`, `REFERENCE_CANDIDATE`, `HISTORICAL_SUPERSEDED`,
`HISTORICAL_NEGATIVE`, `DIGITAL_LIFE_CANDIDATE`, `DIAGNOSTIC_CONTROL`, `UNCERTAIN`. A path may carry two when the
two tracks ask different questions of it, and `UNCERTAIN` is used where the repository does
not settle the matter. `neural.v_th_from_rest` was offered as the example and turned out to be
the wrong one — see §F.6; it is not uncertain, it is unread.

**Python-only, verified by AST sweep plus grep of the exporter and both runtime files:**

| Family | Parameters | Default | Status |
|---|---|---|---|
| Head-reflex cascade | `sensory.head_stages`, `sensory.head_stage_tau` | `1`, `0.0` (off) | `REFERENCE_CANDIDATE` — live, but as a *simplification*; the mechanism argument was refuted |
| Muscle force-velocity | `muscle.fv_vmax` (+ `fv_curvature`, `fv_eccentric`, `fv_tau`) | `0.0` (off) | `HISTORICAL_NEGATIVE` (reference gait — it *narrows* the span) **and** `DIGITAL_LIFE_CANDIDATE` |
| Omega wave suppression | `sensory.omega_wave_suppression` | `0.0` (off) | `HISTORICAL_NEGATIVE` — turn shallower, >120° fraction to zero; do not retry as another gain or target set |

The cascade pair is the subtle one: both are read in `Senses.__init__`, which looks like
construction-time, but what they build is a *step-time branch* (`_head_chain`) rather than an
array the payload could carry. Construction-time reads are only safe when the thing
constructed is data.

**Guardrail added.** `tools/export_model.py::RUNTIME_UNSUPPORTED` is the registry — data
only; nothing in the export reads it, because an exporter that refused to run would block the
experiments Python exists to host. `tests/test_runtime_parity.py` asserts the shipped
`Params()` still sits on those values, and includes a distinguishability self-test (§F.11)
so the registry cannot silently pin nothing.

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

`tools/README.md` classifies all 70-odd files by **measured** importer count and last-touched
date — never by filename. (A `ref` column existed until §F.9 removed it as unreproducible.) Each one-line purpose is its own docstring's first
line, not a guess.

| Class | n | Examples |
|---|---|---|
| `CORE_INFRASTRUCTURE` | 15 | `export_model.py`, `conform.py`, `build_dataset.py`, `audit.py`, `check_all.mjs`, `manifest.py` |
| `MEASUREMENT_LIBRARY` | 4 | `diagnose_loop.py` (42 importers), `assays.py` (32), `stats.py` (6), `coherence.py` (3) |
| `MAINTAINED_INSTRUMENT` | 24 | `kymo.py`, `scorecard.py`, `compare.py`, `ethogram.py`, … |
| `ACTIVE_EXPERIMENT` | **1** | `head_cascade.py` — the only one whose question is still open |
| `ANSWERED_PROBE` | 4 | `head_medium.py`, `lag_span.py`, `force_velocity.py`, `damping_sweep.py` — sacrifice branches, all four negative |
| `UNCERTAIN` | **25** | no importers, untouched since the first days — but six *are* referenced; see §F.9 |

The 25 are labelled uncertain rather than dead. No importers is evidence, not proof; several
are cited by name in the research log; a probe is cheap to keep and expensive to reconstruct.
**Nothing was moved or deleted.**

Four symbols are private by name and imported across modules anyway — `_dispatch`,
`_clean_plate` (`assays`), `_dominant` (`diagnose_loop`), `_output_position`
(`worm/senses.py`). The two `tools/` modules that own one — `assays.py` for `_dispatch` and
`_clean_plate`, `diagnose_loop.py` for `_dominant` — now say so; **`worm/senses.py`'s
does not, and cannot in this pass** — the change surface under `worm/` is deliberately zero,
so `_output_position` remains an unannotated cross-module import. Named here rather than
glossed. The three library docstrings
also state the blast radius: changing what a key of `analyse()` means, or how an assay is
scored, makes every number already in `docs/research-log/` incomparable with every future
one, silently, with nothing to fail.

---

## F. Scientific documentation corrections

Fourteen. Two in the pre-existing repository, and twelve in this pass's own drafts — recorded here
rather than quietly fixed, since a pass about not rewriting history should not begin by
rewriting its own. F.6 onwards came out of an independent adversarial audit commissioned
against the finished branch: F.6 onwards is nine entries, and all of F.10-F.14 were found by
auditors rather than by me.

### F.1 — a stale claim in a test docstring *(pre-existing)*

`tests/test_behaviour.py::test_medium_changes_the_gait`.

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

### F.2 — a check that could not run on Windows, reported green

`wasm/memory.mjs` reads `wasm/assembly/index.ts` and scans the `Worm` class body to derive
each per-animal array's size from the source rather than trusting a second copy of the
numbers. The scan is two `indexOf` calls: `'\nclass Worm {'` for the start, `'\n}\n'` for the
end.

Git for Windows checks out with `core.autocrlf=true` by default, so `index.ts` arrives CRLF.
`'\nclass Worm {'` still matches — it finds the `\n` of a `\r\n` — but `'\n}\n'` cannot match
`'\n}\r\n'`, so `classEnd` is `-1` and the tool exits 2 with **`cannot find class Worm in
wasm/assembly/index.ts`**. Reproduced on this PR's head, and the fix verified against a
genuinely CRLF-converted working tree rather than argued for.

Two things make it worth a numbered entry rather than a silent fix:

- **The diagnostic accused the wrong subject.** It named the runtime source as having lost a
  class it had not lost, in a file whose entire purpose is to notice when a documented claim
  goes stale. A parser that reports the wrong subject is worse than one that crashes.
- **The bug predates this pass, but this pass edits the file and reported it green.** The
  green was true on Linux and untrue on Windows, and nothing said so.

Fixed reader-side, in `wasm/memory.mjs` only: both `.ts` sources are read through one helper
that normalises `\r\n` to `\n`. Nothing downstream cares about `\r` — the constant regex uses
`\s*` and the document checks are substring and `\s`-based — and `wasm/assembly/*.ts` is not
touched. The repository stores LF; this makes the *reader* indifferent.

### F.3 — `omega_wave_suppression` was mislabelled by this pass

The first cut called it `REFERENCE_EXPERIMENTAL`, which reads as "untried, and available".
`worm/params.py` says otherwise, and had all along: tested at 1.0 on 2026-07-30, six paired
animals per condition, 200 s each. It makes the turn **shallower**, not deeper — median
reorientation 37.75 → 15.62 deg off food (paired difference −22.1, 95% CI −34.4 to −12.4) and
42.63 → 29.05 on food (−13.6, CI −22.3 to −9.6) — and **the fraction of turns over 120 deg
fell to zero in both conditions**. The recorded conclusion is "leave this off", and the
surrounding turn analysis names the form not to retry it in: *not* another target set and
*not* another gain, because what the turn lacks is dynamic range in the motor units.

Now `HISTORICAL_NEGATIVE`, with the do-not-retry form attached. No measurement changed; the
label was wrong, not the science.

### F.4 — four answered probes were called active experiments

`head_medium.py`, `lag_span.py`, `force_velocity.py` and `damping_sweep.py` were labelled
`ACTIVE_EXPERIMENT` on the strength of a recent commit date. Each had in fact *finished*: it
ran, answered its question in the negative, and closed it. They are the four rows of
`NEXT.md`'s do-not-re-run table — being the reason work is closed is the opposite of being
open work.

**Recency is evidence that a file mattered recently, not that its question is open.** They are
now `ANSWERED_PROBE` — sacrifice branches, kept executable because the answers are
load-bearing. `head_cascade.py` remains the sole `ACTIVE_EXPERIMENT`, and its own entry now
distinguishes the two claims about it: the mechanism argument it was built for was refuted by
`head_medium.py`, and it survives as a simplification, which is weaker and still open.

`force_velocity.py` carries the double label the two tracks earn it: `HISTORICAL_NEGATIVE`
for the reference-gait question it answered, `DIGITAL_LIFE_CANDIDATE` for the Track B question
nobody has asked.

### F.5 — biological provenance language *(pass's own wording)*

`docs/project-architecture.md` described Track A as having "real sensory modalities and
proprioceptive loops". That phrase blurs three epistemic classes at once. What is
reconstructed is **which cells carry which modality, and with what sign** — ASEL/ASER as an
ON/OFF pair, AWC as an OFF cell, AFD warm, URX/AQR/PQR for oxygen. The transduction that turns
a concentration into a current is *modelled*, and every gain in front of it is *tuned*.

Track A is now a per-component table with reconstructed / modelled / tuned as separate
columns, so no row can claim more than it has, plus one line stating that nothing in the
reference worm is evolved.

### F.6 — the registry's central justification was false for two of its three paths

This pass asserted, in four places, that conformance is blind to a flipped Python-only
default because "the runtime has no branch to disagree about". **That is wrong, and it was
measured wrong.** Flip the default, regenerate the reference with `tools/conform.py`, run
`node wasm/conform.mjs` against the committed `.wasm`:

| flipped | conformance |
|---|---|
| baseline | PASS, exit 0 |
| `sensory.head_stages = 4` | **FAIL**, exit 10 |
| `muscle.fv_vmax = 1.0` | **FAIL**, exit 10 |
| `sensory.omega_wave_suppression = 1.0` | **PASS**, exit 0 |

Conformance rebuilds the Python side from `Params()`, so the moment the new configuration
moves the Python trajectory the comparison diverges. The real gap is narrower and worse: a
path escapes conformance when it is **inert across every conformance case**.
`omega_wave_suppression` scales by `abs(omega)` and no conformance case fires an omega turn,
so the term is multiplied by zero however large the coefficient. `tools/conform.py` already
records the same shape of miss — it is how the serotonin-gated chloride path reached the
runtime unported.

The guard is therefore a *second, earlier, better-named* detector for two of the three paths,
and the **only** detector for the third. Corrected in `docs/runtime-parity.md`,
`tools/export_model.py`, `tests/test_runtime_parity.py` and `docs/project-architecture.md`;
the coverage section now also records that the registry pins a *value*, not the behaviour that
value stands for.

### F.7 — `neural.v_th_from_rest` was called `UNCERTAIN`; the flag is not read at all

`worm/nervous.py` calls `self.V_th = self._resting_potentials(s_half)` unconditionally. There
is no `if p.v_th_from_rest` anywhere in `worm/` — the only occurrences are the field itself, a
comment in `worm/modulators.py`, and an exclusion in `tests/test_genome.py`. Setting it
`False` produces a byte-identical model.

`UNCERTAIN` was the wrong label and the wrong kind of wrong: it says *nobody has measured
this*, which invites someone to go and measure a configuration that does not exist. The Route-1
table now records the flag as unread, and `normalise_nmj` — which is genuinely branched at
`worm/muscle.py` — replaces it as the Route-1 exemplar. **This also removes it from the
owner-decision list; the repository settles it.**

### F.8 — "every name in the scalar lists is Route 2" over-claimed by three

`MUS_REST_TENSION`, `WORLD_INGESTION_RATE` and `WORLD_RADIUS` are emitted into
`wasm/assembly/model_gen.ts` and never read by `index.ts`. `rest_tension` is Route 1 — it is
consumed inside `Muscles._balance` and reaches the animal baked into the exported `G`;
`ingestion_rate` is dead on both sides and `worm/genome.py` already says so; `world.radius`
reaches the runtime as `WORLD_EXTENT` instead. Harmless today, but the sentence was written to
close the question off, which is exactly what makes it worth correcting.

### F.9 — provenance and index corrections found by audit

Smaller, all evidence-backed, all now fixed:

- **Drag is not simply "measured".** `worm/params.py` attributes the buffer pair to Lighthill
  slender-body theory — computed, not measured. Only the agar tangential value is a direct
  force measurement.
- **"Evolution may touch some rate constants" was false.** Not one of the 15 `BOUNDS` keys has
  units of s or 1/s. In the permissive direction, which is the dangerous one.
- **`optimise.py::SPACE` is not `BOUNDS`.** Four of its seven members — `proprio_reach`,
  `peak_moment`, `head_tau`, `head_reach` — are tuned and deliberately *not* evolvable.
- **The genome's bounds do not travel.** `wasm/evolve.mjs` carries its own, looser clamps; the
  *allow-list* is what is enforced end to end, not the envelopes.
- **The damping row was in the wrong units.** In a column of gait-modulation spans it quoted
  `1.02–1.04×`, which is the per-medium frequency change. The span went 1.27× → 1.30× — it
  slightly *widened*. The conclusion survives; the number did not belong in that column.
- **"Nothing has ever been aimed at" the reach/wavelength question** was true only of the
  medium span; single-medium sweeps exist in `worm/params.py` and `tools/wave_speed.py`.
- **The `tools/README.md` UNCERTAIN criterion was false for six entries.** Five are cited by
  path in `worm/params.py` as the provenance for a shipped constant. That makes the archival
  question **not purely a taste call**, which `NEXT.md` now says.
- **The `ref` column was unreproducible** from its own stated definition — four readings gave
  four answers — so it is gone; `imp` remains, with the exact command that produces it.
- Plus: `export_model.py`'s importer count (this branch added the third), a dangling `§13`,
  and several self-measurements that went stale as the documents grew.

### F.10 — four defects this pass fixed silently in its own drafts

Recorded late, at an auditor's prompting, because the standard §F sets applies to the pass as
much as to the repository. Commit `26db467` corrected four of its own draft defects and put
the reasoning only in the commit message, never here:

- a Route-1 table whose column header promised "lifecycle of the alternate" while three of
  five rows described the shipped path instead;
- `DIAGNOSTIC_CONTROL` used as a label before it was one of the defined labels;
- a duplicated "built from the real animal downwards" across a paragraph break;
- a section introducing "four epistemic classes" above a table of five.

None changes a scientific claim. All four are the same shape as the errors §F does record,
and leaving them in a commit message while §F counted only the others was the inconsistency.

### F.11 — a self-test named for more than it measures

`test_the_guard_would_actually_fire` did not invoke the guard. An auditor neutered the real
assertion to `assert True`, moved a registered default, and the self-test still passed. It
checks the two vacuity traps *underneath* the guard — that every key resolves, and that
`shipped` is distinguishable from a moved value under numeric coercion — which is worth
having and is not what the name promised. Renamed to
`test_every_registered_value_is_distinguishable_from_a_moved_one`, with the limit stated in
its docstring. The guard has been watched to fail manually, and that transcript is above;
making that automatic is `tools/audit.py`'s job, not this file's.

### F.12 — "each owning module's docstring now says so" was false for one of four

§E claimed all four privately-named cross-module imports were annotated in their owning
module. `_output_position` lives in `worm/senses.py`, and this pass keeps the change surface
under `worm/` at zero — so it is not annotated and could not be. Three of four; now stated
that way in both §E and `tools/README.md`.

### F.13 — the 201-test run's exculpation used a wrong mechanism

It said "almost every test reads only the installed package". There is no installed package:
`worm` resolves into the working tree, and CI's `pip install -e` is an editable install of the
same tree, so all 201 import from the tree. The conclusion stands on a different footing — the
change surface in that window was markdown plus one additive comment — and §Validation now
says that instead. Six tests, not two, read tree *files* at runtime.

### F.14 — the fingerprint was over-sold as the binding evidence

With zero files changed under `worm/`, `data/` and `wasm/assembly/`, the trajectory
fingerprint can only differ if the harness is wrong. It is a consistency check on the change
surface, not an independent proof, and the change surface is the primary evidence. It is also
not third-party reproducible: the hash appears here but the serialisation is not committed as
a script.

**So do not take the fingerprint, or this report, as the evidence.** Check the change surface
yourself — it is one command, it needs no trust, and it is what the claim actually rests on:

```bash
git diff --name-only 0f7c25b..HEAD -- worm/ data/ wasm/assembly/ web/ docker/ .github/
#   (empty)
```

If that is empty, no committed line that the model reads has changed, and the fingerprint
could not have moved. During review an auditor did independently rebuild the claim from
scratch — their own base-vs-head fingerprint over a different seed set, duration, media and
state vector, identical in all five cases — but a report citing an auditor the next reader
cannot name is not evidence either. The command above is.

---

## G. Things deliberately left alone

Tempting refactors declined, with the reason:

| Declined | Why |
|---|---|
| Splitting `worm/senses.py` (the command layer out of sensory transduction) | Out of scope; it is a step function, so it costs a double implementation and a conformance run |
| Splitting `wasm/assembly/index.ts` (2,346 lines, 5.1× growth in 5 days) | Real risk of breaking a working artifact for readability |
| Consolidating the WASM bootstrap, which recurs in 9 `.mjs` files plus `web/local.js` | Genuine duplication, but a Pass 2 change with its own validation |
| `worm/params.py`'s structure and comment density (74% of its lines are comment-only) | The comments *are* the provenance. Splitting it is the most tempting and most harmful change available |
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
   `setPayload` sequence recurs in nine `.mjs` harnesses, with small local variations — how
   many are byte-identical depends entirely on where you cut the comparison window, so no
   such count is quoted here. Node-side only —
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
| **Reference-model change** | `README.md` 64 kB + `NEXT.md` 181 kB + `worm/params.py` 2,387 lines, with no way to know which was current | `docs/project-architecture.md` ~19 kB + `docs/runtime-parity.md` ~19 kB + the relevant `params.py` section. **~245 kB → ~38 kB** before touching source |
| **Runtime/WASM change** | `wasm/README.md` + grep `index.ts` to discover what exists | `docs/runtime-parity.md` answers "does the runtime implement this?" directly, with the porting procedure |
| **Digital Life change** | Nothing described the track at all; the boundary lived in the owner's head | `docs/project-architecture.md` §1 and §6 |
| **"What should I work on?"** | Read 181 kB and infer | `NEXT.md`, 6.4 kB, one sitting |

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
2,346 lines and 5.1× growth in five days, and ten copies of the WASM bootstrap. Both are
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

The executable edits are: `tools/export_model.py` (**purely additive** — a data-only constant
that no *export* path reads; `tests/test_runtime_parity.py` imports it); `wasm/memory.mjs`
(one path in `QUOTES`, plus the reader-side CRLF fix of §F.2); `tests/test_ci_policy.py`
(`NO_CI_NEEDED` data); and the new `tests/test_runtime_parity.py`. The three tool-library
edits are purely additive docstrings. **None of them is reachable from `worm/`** — which is
the actual load-bearing fact, and why the zero-file change surface under `worm/`, `data/` and
`wasm/assembly/` is the primary evidence here. The fingerprint below is a consistency check
on that, not an independent proof: with no file changed under `worm/`, it could only differ
if the harness were wrong.

**Checks run:**

| Check | Result |
|---|---|
| `node tools/check_web.mjs` | acyclic, all imports resolve |
| `node wasm/memory.mjs` | PASS — 239,360 B / 234 kB in 4 files, share 89% |
| `node wasm/population.mjs` | PASS |
| `node --test wasm/{invariants,solve,eggs-fitness,conform-inputs}.test.mjs` | 14 pass, 0 fail |
| `node --test wasm/{energy-fitness,medium}.test.mjs` — the two that also run without a rebuild | 14 pass, 0 fail |
| `node --test tools/sim_rate.test.mjs` | 4 pass, 0 fail |
| module parse sweep (`node --check`, all of `web/`, `tools/*.mjs`, `wasm/*.mjs`) | all parse |
| `pytest tests/test_ci_policy.py tests/test_local_checks.py` | 50 pass |
| `pytest tests/test_runtime_parity.py` | 6 pass, and watched to fail on a flipped default |
| `pytest tests/test_behaviour.py::test_medium_changes_the_gait` | pass |
| `pytest tests/` minus `test_behaviour`/`test_audit` | **201 passed, 0 failed** (47 min) |
| Link check across all 11 tracked markdown documents | 0 broken |
| Every symbol/path asserted in the new docs | all resolve |

**Re-validated after the review round** (the classification corrections in §F.3–F.5, which
touched five documents and one comment in `tools/export_model.py`):

| Check | Result |
|---|---|
| Trajectory fingerprint | `a9d09d63…d307f2` — **still identical** |
| `pytest test_runtime_parity + test_ci_policy + test_local_checks` | 56 pass |
| Guard watched to fail again, on `omega_wave_suppression = 1.0` | fires; `params.py` restored clean |
| `pytest test_export_model + test_genome + test_model_artifacts + test_export_precision + test_stats` | 42 pass |
| `node wasm/memory.mjs`, `node tools/check_web.mjs` | PASS, acyclic |
| Archive blob identity | unchanged, `12da57c8…` |
| Files changed under `worm/`, `data/`, `wasm/assembly/`, `web/`, `docker/`, `.github/` | **0** |

The 201-test result above was **not** re-run after the review round. It stands for everything
that cannot see the working tree, which is all of it except `test_ci_policy.py` and
`test_local_checks.py` — and those two were re-run against the final tree (in the 56 above).
`tools/export_model.py`'s only change is an additive comment, and nothing in `worm/` imports
it, which is why the fingerprint is the binding evidence rather than the test count.

**Re-validated again after the polish round**, from cleared bytecode caches and with
`PYTHONDONTWRITEBYTECODE=1`:

| Check | Result |
|---|---|
| `node wasm/memory.mjs` — **CRLF checkout** | **PASS**, exit 0 (was: `cannot find class Worm`, exit 2) |
| `node wasm/memory.mjs` — LF checkout | PASS, exit 0 |
| `node tools/check_web.mjs` | acyclic, every import resolves |
| `pytest test_runtime_parity + test_ci_policy + test_local_checks` | **56 passed** |
| `pytest test_export_model + test_genome + test_model_artifacts + test_export_precision + test_stats` | **42 passed** |
| Guard watched to fail | fires on `omega_wave_suppression = 1.0`; restore verified **by loaded value**, not only by `git diff` |
| Trajectory fingerprint | `a9d09d63…d307f2` — identical |
| Files changed under `worm/`, `data/`, `wasm/assembly/`, `web/`, `docker/`, `.github/` | **0** |

### A stale-bytecode incident, and what it changes about the claims above

The first attempt at the polish-round re-run reported `1 failed, 55 passed` — the parity guard
rejecting `omega_wave_suppression`. `worm/params.py` on disk was correct and `git`-clean; the
interpreter was loading `1.0` from `worm/__pycache__/params.cpython-311.pyc`.

The mechanism is worth recording because the restore *looked* verified. Demonstrating the
guard means writing a broken default, running pytest, and restoring. `0.0` → `1.0` preserves
the byte length, and the restore landed inside the same one-second mtime bucket the `.pyc`
had recorded — and (mtime, size) is exactly the pair CPython uses to decide a `.pyc` is
current. So the cache was considered valid and the broken compile survived a restore that
`git diff --quiet` correctly reported as clean.

`__pycache__` is gitignored, so **neither the repository nor this PR was ever affected**. What
was affected is the evidence: the review round's Python numbers were produced under that
cache. They have all been re-run above from cleared caches and are unchanged, which is the
expected outcome — the poisoned constant gates a branch (`wave_gain < 1.0`) that only runs
during an omega turn, and none of those tests takes one. Unchanged-on-re-run is the result,
not an argument for skipping the re-run.

The lasting fix is procedural and is now used above: verify a restore by the value the
interpreter actually loads, not only by `git diff`.

One caveat on that 201-test run, stated because a check whose conditions were not what they
look like is exactly what `tools/audit.py` exists to find: it was launched while this report
and the last two commits were still being written, so the working tree moved underneath it.
The reason first given for why that was tolerable was wrong, and is corrected here: it said
"almost every test reads only the installed package". There is no installed package — `worm`
resolves into the working tree, and CI's `pip install -e` is an editable install of the same
tree, so **every one of the 201 imports from the tree**. What actually bounds the exposure is
the change surface in that window: markdown, plus an additive comment in `tools/export_model.py`.
The tests that read tree *files* at runtime — `test_ci_policy.py`, `test_local_checks.py`,
and also `test_dataset_sources.py`, `test_export_precision.py`, `test_audit.py`,
`test_threads.py` — are the ones worth re-running, and the first two were: **50 passed**
against the final tree.

One environment caveat that applies to every Python number above: `pyproject.toml` pins
`pytest>=8.0,<9` and this environment runs **pytest 9.1.1**, so the local results were produced
outside the declared range. Moot while hosted CI is off — nothing else ran them — but it means
"the suite passes" is a claim about pytest 9, not about the pinned range.

Not run: the full `tests/test_behaviour.py` (~30 min of simulation) and `tools/audit.py`,
on the grounds that the trajectory fingerprint is a stronger and cheaper non-interference
proof than re-running scientific assays that no changed line can reach. Also not run:
`npm run check --rebuild`, which regenerates tracked artifacts — deliberately, since this
pass must not regenerate any.
