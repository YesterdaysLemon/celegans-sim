# NEXT

What to do next. Nothing else — no history, no status, no results already recorded elsewhere.

New here? [`docs/project-architecture.md`](docs/project-architecture.md) says which of the two
tracks below you are in and what must not blur between them.

---

## Reference worm

**1. Localise the medium coupling: which stage of the loop actually changes between
K = 40 and K = 9, and why does it stop there?** The (f, λ) locus experiment ran 2026-08-12
— `tools/flambda_locus.py`, nine media K = 1.58–40, three seeds, full tables and the
considered reading in its docstring. Compressed:

- **The locus does not slide off the animal's crawl→swim line.** Perpendicular offset stays
  within −0.03 to −0.10 L, non-monotone, ending −0.05 L. Under the load axis — the axis the
  animal is measured on — f and λ move *together*, roughly along the chord. The
  two-independent-knobs suspicion is dead, and the parameter-space independence
  `tools/wave_speed.py` measured (reach moves λ, f flat to 1%) does not govern the load
  response; inferring one from the other was the error.
- **What dominates is bunching, not direction.** The model traverses **11%** of the animal's
  chord, and 89% of its frequency motion happens above K = 9. The saturation `MediumParams`
  documents in the frequency column holds for the locus as a whole, in both coordinates at
  once. Wave speed v = f·λ spans 1.37× measured across the full sweep, against the animal's
  13.9×.

So: one coupling between loop and load, moving f and λ together in roughly the animal's
proportion (log-log exponent ~0.22 against the chord's 0.49, coarse), a factor of ~10 too
small in reach, running out exactly where swimming begins. **Do not attack the flat
wavelength as its own problem** — under the load axis it rides the same saturating coupling
as the frequency.

The next probe: run the loop-phase decomposition per medium — `tools/loop_phase.py` opens
the head loop and measures each stage's gain and phase, and nobody has run it anywhere but
agar. Find which stage's numbers move between K = 40 and K = 9, and confirm they stop moving
below. That localises the coupling before any mechanism is proposed for it.

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
> | muscle force-velocity (`fv_vmax = 500`) | 0.600 | 0.700 | 1.17×, worse | a stronger derating; unstable there |
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

**1. Export the raw muscle `G`, and finish the exporter rework.** Unblocks heritable weights
*and* topology together. The graph is already in the payload as CSR and the runtime already
solves for `V_th`; the one remaining blocker is that the exported muscle `G` is
*post*-`_balance`, so the balance can be neither recomputed nor checked from the payload.
Export the raw one alongside it and port the bisection — 70 iterations over 95 cells, no
linear algebra.

**2. Make egg production depend on laying having made room for it.** `EVO_FITNESS=eggs` is
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

- **Should `test_medium_changes_the_gait` assert the *direction* of gait modulation?** It
  currently asserts `ratio > 1.2`, which is direction-free — and that is why the suite could
  not see a docstring claiming the model ran backwards. Direction is now right at every seed
  measured, but the margin is thin (seed 5 gives 1.214 against a 1.2 bound), so tightening it
  wants a larger seed count first. Changing it is a change to a scientific acceptance
  criterion and belongs in its own commit.

### Settled

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
