# NEXT

What to do next. Nothing else — no history, no status, no results already recorded elsewhere.

New here? [`docs/project-architecture.md`](docs/project-architecture.md) says which of the two
tracks below you are in and what must not blur between them.

---

## Reference worm

**1. Calibrate the amine load-sensing path toward the animal, then decide adoption.** The
mechanism search is over: the path is built (`worm/` — Python-only, every coefficient
defaulting to zero, provably inert when off) and measured (`tools/amine_gait.py`,
2026-08-13, 27/27 cells at the first probe calibration). The agar end holds the shipped
gait exactly with dopamine at its ceiling; the (f, λ) locus traverses **36% of the
animal's crawl→swim chord against the baseline's 11%**; the K ≈ 8 saturation is gone,
because the transduced drag force keeps discriminating after the bending dynamics go
blind. Full tables, blemishes included, in the tool's docstring; the lifecycle entry with
the whole measurement chain is in [`docs/runtime-parity.md`](docs/runtime-parity.md)
(`REFERENCE_CANDIDATE`).

The first two knobs are swept and folded in (buffer-end grid + full verification locus,
same day, tables in the tool): reach 0.48 paired with lag coefficient 1.30 takes the
locus to **+0.786 along the chord — 79% of the way to the animal's swim** — at TWI ≥
+0.72 everywhere and the crawl still untouched. Reach and lag must move *together*
(reach 0.48 at lag 1.0 breaks the wave outright); the effective lag now bottoms at the
0.4 floor in buffer. What remains:

The serotonin arm's function is measured and folded in (2026-08-14, the third
calibration): dopamine's withdrawal also speeds the muscle EC cascade
(`dopamine_muscle_rate`, with the note at the parameter on why it rides dopamine — the
serotonin *scalar* ships with a hot food effect that would fire backwards in liquid).
The settled locus is clean at all nine media: **+0.847 along the chord, buffer at 89% of
the animal's swim frequency**, crawl untouched with its best measured wave. Two guards
now bound further calibration:

- **The cliff.** Muscle coefficients ≥ 0.7 make the swim end genuinely bistable (a
  broken 0.17 Hz mode coexists with the fast gait; 1–2 of 3 seeds fall in, fully
  settled). 0.5 is 3/3 stable. Any knob change now needs the stability grid re-run
  first.
- **Slow-state protocols.** Measuring the amine path with a settle shorter than ~3
  dopamine taus measures its transient, not its attractor — the K = 3.54 lesson,
  recorded in the tool. Any future assay of an enabled-amine configuration inherits
  this.

What separates the path from the animal: the last 11% of swim frequency, a wavelength
ceiling near 1.40 L against 1.54, and mid-continuum trajectories that wander (net/path
0.29 at K = 5.3). The literal serotonin route (a second load-driven scalar with its own
effects) stays gated on separating the serotonin scalar's food roles — the same
confound-class precondition as adoption.

**Adoption is a separate decision from calibration, and the preconditions are down to
two.** Runtime parity is discharged (2026-08-14): the cascade and the whole amine path
are ported to `wasm/assembly/index.ts` behind per-worm setters with all-zero defaults,
each with its own conformance case agreeing to 5e-13 mm / 5e-11 mV and each measurably
doing something against its off control — see `docs/runtime-parity.md`. What remains:
the food/load confound on the dopamine scalar (`SensoryParams.load_gain` states it), and
the behavioural gate — **now fully run (2026-08-14, five assay families), and its one
finding is coherent: the configuration suppresses reversals globally.** Triage −1.5
[−2.8, −0.3] per 60 s; chemotaxis −2.8 [−5.5, −0.2] per animal; nociception −1.37
[−2.53, −0.21] reversals/min while clear (the tool scores that arm "better", but fewer
spontaneous reversals is the same suppression wearing a flattering assay). Everything
else: chemotaxis index/approach/weathervane no effect at n=12 (resolution 0.085);
thermotaxis no effect at n=3 (resolution 16 mm — uninformative, honestly); aerotaxis "O2
lowest reached" nominally worse at +1.47 [+0.06, +2.88] but n=2 and the CI grazes zero —
thin. **What adoption needs now is attribution:** the config bundles the cascade and the
amine arm, and a halved reversal rate must be assigned to one, the other, or their
interaction before any default moves. The paired attribution runs (cascade-only and
amine-only, triage + chemotaxis) were launched 2026-08-14; read those tables next.

*(The measurement chain that got here — locus, per-medium lock-in, the fv retirement, the
below-K≈8 constraint, the twice-validated open-loop screen — is recorded in the tool
docstrings, `worm/params.py::MediumParams`, and `docs/runtime-parity.md`.)*

> **Do not re-run these.** Four mechanisms have already been measured against the
> gait-modulation span and all four failed. Full tables in
> [`docs/research-log/`](docs/research-log/); this is the do-not-repeat list.
>
> **Absolute frequencies, not just spans** — an external reviewer given only the span column
> inferred a frequency floor at ~0.9 Hz and built a whole mechanism on it. The lag-cut row
> refutes that outright: buffer reaches **1.900 Hz**. A table of ratios discards exactly what
> is needed to reason about mechanism, so both are quoted here.
>
> | tried | agar Hz | buffer Hz | span | do not retry as |
> |---|---|---|---|---|
> | *(shipped, for reference)* | 0.656 | 0.833 | 1.27× | — |
> | the cascade's frequency-dependent phase | 0.644 | 0.833 | 1.29× | a stage count or a lag budget |
> | cutting the fixed head lag fourfold (0.500 → 0.125 s) | 1.356 | 1.900 | 1.40× | a smaller head reflex |
> | muscle force-velocity (`fv_vmax = 500`) | 0.600 | 0.700 | 1.17×, worse | a stronger derating; unstable there. And not at any dose as a modulation mechanism: its phase is load-scaled backwards and knee-bound (`tools/fv_phase.py`) |
> | body internal damping, down to zero | 0.667 | 0.867 | 1.30× | a mechanical-dissipation problem |
>
> Read the lag-cut row carefully before proposing anything: a fourfold cut roughly **doubles
> the frequency in both media at once**. Frequency is set by total loop lag and there is no
> floor — but the *span* barely moves, which is what an additive `τ_fixed + τ_body(K)` model
> cannot do. Fitting that model to those points puts the buffer-end body lag near 0.8 s,
> larger than the head reflex's entire budget, on a body with almost no drag on it. Both the
> additive frame and the floor frame are dead.

**2. Decide the head cascade, then port it.** Four stages of 0.125 s with `head_delay = 0`
match the shipped frequency, improve the wave in every medium, and retire the largest fitted
number in the model. **The argument it was built for was refuted** — it does not fix gait
modulation — so it is a simplification, not a mechanism, and that is the claim to weigh.

Blocking work, in order: `tools/scorecard.py` and `tools/ethogram.py` against the frozen
baseline on identical seeds; then the port, because `head_stages`/`head_stage_tau` are
Python-only and cannot become a default until the runtime has them
([`docs/runtime-parity.md`](docs/runtime-parity.md)).

**3. Second tier.** Subordinate to the above — changing the shared gait moves every
behavioural assay at once.

- **Gait-modulation magnitude.** Direction is right, size is not: 1.29× against the animal's
  5.9×.
- **Backward locomotion.** Reverses, but curvature and net speed stay poor after AVB removal.
  Not citable as a working phenotype.
- **Taxis magnitude.** Mechanisms point the right way with small outcomes. Re-run after a
  turn-depth mechanism clears its own paired gate; do not tune the assays around the current
  shallow turn.

---

## Digital Life Laboratory

Evolved animals are not *C. elegans*, and nothing here produces a claim about the animal —
[`docs/project-architecture.md`](docs/project-architecture.md) §1.

**1. Heritable weights are built (tier two); what remains is running them, then topology.**
Per-worm conductances landed 2026-08-14: every weight consumer in the runtime reads
through per-worm references (wild type aliases shared payload copies, bit-identical and
free), mutation is `scaleWeight` (chemical synapse's two views in lockstep, gap junction's
two directions together, no sign flips — sign is topology, tier three), and `developWorm()`
regrows the products from the animal's own graph: the ported LU resting solve, the
half-voltage offsets, the muscle rebalance, gap totals, born at rest. Eggs carry weight
snapshots; hatch develops. Contracts pinned in `wasm/weights.test.mjs`; the arena takes
`ARENA_WMUT`/`ARENA_WMUT_N`, default off. The first full run is on the record in
`wasm/arena.mjs`: the genes-only `proprio_gain` climb did not appear under weight
mutation — drowned signal or selection moved into the weights; a weight-drift readout
in the arena reports would distinguish them. Then the topology tier (entries
added/removed, which changes the CSR pattern the weights ride on). Tier four's
chain-shaped half landed 2026-08-14: heritable stiffness, width and muscle profiles
(`setMorphology`, twelve control points clamped [0.25, 4], eggs carry snapshots,
`ARENA_MMUT`; contracts in `wasm/morphology.test.mjs`). Branching bodies are explicitly
out of scope — that is an engine rewrite, not a mutation, and the mechanism says so.

**1b. The dish has a metabolism now — run it until it bites.** Death by physiology
landed 2026-08-14 (runtime: `setMetabolism`/`getEnergy`/`depositFood`, drag-power work
cost, muscle fade; contracts in `wasm/metabolism.test.mjs`; every constant invented, all
defaults off, off is bit-identical). Every death — starvation or cull — now feeds the
plate where the body stopped, a yield on the store included, so a culled well-fed animal
outfeeds a starved husk. The first shakedown selected *feeding harder* instead of dying
(record in `wasm/arena.mjs`): zero starvations at the default constants. Next: a dish
poor enough that the tax bites (smaller lawns, shorter `ARENA_METAB_T`), replication,
and the museum watch — scavenging lineages, corpse-camping, and whether laying-near-food
becomes a heritable strategy once eggs hatch onto their parent's grave.

**2. (Superseded for the arena; open for the scalar measure.)** In-dish reproduction
(`wasm/arena.mjs`, `web/arena.html`, 2026-08-14) dissolves the degeneracy for Track B's
main line: there is no fitness scalar to game — reproduction is eat → transport → uterus
→ HSN/VC laying → survive incubation, and a first arena run showed a founding dynasty
sweep to fixation in 150 dish-seconds followed by the plate economy shutting laying down.
The physiology question below stands only if the scalar `EVO_FITNESS=eggs` measure is to
be kept honest for short assays. **Make egg production depend on laying having made room
for it.** `EVO_FITNESS=eggs` is
measured to be intake in different units: `laid + held` is conserved across a laying event, so
egg production is blind to the egg-laying circuit by construction. A real uterus is not a
bucket that fills regardless. Small model change — but it lands in `worm/egglaying.py`, which
is reference-worm physiology that ships in the browser, so §1's invariant in
[`docs/project-architecture.md`](docs/project-architecture.md) applies: the fitness degeneracy
is a reason to *look*, and adopting a change needs reference evidence rather than the fitness
argument.

**3. Re-run the adversarial probe once the genome is bigger.** Priced at twelve seeds, about
five and a half hours. Not worth spending before (1): the current fifteen genes were chosen so
that none can reach a conversion factor, so a null result is the gene list working rather than
the model being clean.

---

## Blocked, or needs an owner decision


### Settled

- **`test_medium_changes_the_gait` asserts direction now.** The seed count it wanted was
  measured (16 seeds, the test's exact protocol): buffer faster at 16 of 16, ratios
  1.214–1.308, weakest directional margin three FFT bins. The bound is 1.15 directional —
  under the weakest measured seed with margin, and strictly stronger than the old
  direction-free 1.2, which accepted a backwards animal. Own commit, own seed count, own
  argument, per the rule this item set for itself.

- **Gait experiment order** — the (f, λ) locus test went first, and has now run
  (`tools/flambda_locus.py`, 2026-08-12). It subsumed the reach sweep's question — the reach
  sweep is retired with it — and the cascade work in (2) is unblocked.
- **The 25 uncertain tools stay where they are.** [`tools/README.md`](tools/README.md) solved
  the discoverability problem the move was for. Six could not have moved anyway: five are
  cited by path in `worm/params.py` as the provenance for shipped constants
  (`gate_calibrate.py`, `modulator_sweep.py`, `osc_control.py`, `reversal_test.py`,
  `tau_sweep.py`) and `twi_by_region.py` is cited from `tools/reflex_gain.py`.
- **`tools/optimise.py` stays live, and its search space is now pinned.** It covers four
  parameters `BOUNDS` deliberately excludes — `proprio_reach`, `peak_moment`, `head_tau`,
  `head_reach` — so it is not redundant with `wasm/evolve.mjs`. `tests/test_genome.py` pins
  that every `SPACE` name resolves, that the shared/search-only partition holds, and that the
  shared envelopes still overlap.

---

## Where everything else lives

This file is the frontier only. If what you want is not above, it is not next:

| Looking for | Go to |
|---|---|
| What was already tried, and what it measured | [`docs/research-log/`](docs/research-log/) |
| What the project is for, and the two-track boundary | [`docs/project-architecture.md`](docs/project-architecture.md) |
| Whether the runtime implements a path, and that path's lifecycle | [`docs/runtime-parity.md`](docs/runtime-parity.md) |
| How to run the gates, and why CI is paused | [`README.md`](README.md) → *Running the checks yourself* |
| Which tool measures what | [`tools/README.md`](tools/README.md) |
