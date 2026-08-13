# NEXT

What to do next. Nothing else — no history, no status, no results already recorded elsewhere.

New here? [`docs/project-architecture.md`](docs/project-architecture.md) says which of the two
tracks below you are in and what must not blur between them.

---

## Reference worm

**1. Find what keeps a load-scaled time in the loop below K = 9 — and screen candidates
open-loop, which is now cheap.** Two measurements (2026-08-12/13) turned gait modulation
from a mystery into a mechanism search with tight constraints:

- `tools/flambda_locus.py` (nine media, K = 1.58–40): the model's (f, λ) locus does **not**
  slide off the animal's crawl→swim line — it is *bunched* on it. 11% of the chord
  traversed, 89% of the frequency motion above K = 9, v = f·λ spanning 1.37× against the
  animal's 13.9×. One coupling moves f and λ together; the two-independent-knobs suspicion
  is dead; **do not attack the flat wavelength as its own problem**.
- `tools/loop_medium.py` (per-medium lock-in, five media, both body-reflex arms): that
  coupling is **the passive body's bending relaxation and nothing else**. From K = 40 → 7.9
  the tension→curvature stage moves +40°; every other stage ≤0.2°; below K = 7.9 nothing
  moves at all, both arms identical. The analytic form τ = c_n/(EI·k⁴), committed before the
  run, placed the knee correctly and the magnitudes within 2×. And the open-loop account
  closes quantitatively: plant phase + analytic receptor phase predicts the measured
  closed-loop frequency at **every** medium to ≤1.5% (0.662 vs 0.656 at K = 40, 0.800 vs
  0.800 at 17.8, 0.836 vs 0.833 at 1.58).

So the constraint on any gait-modulation mechanism, stated so it can kill proposals early:
the loop's only load-dependent time falls like c_n and is finished by K ≈ 8, five orders of
magnitude too fast in buffer. The mechanism must keep a *time* in the loop scaled to the
load all the way down the continuum. Load-independent elements — gains, fixed lags, cascade
shapes, internal damping (load-independent by form, and `tools/damping_sweep.py` measured
it) — cannot do it by construction, which is why the do-not-repeat table below reads the
way it does.

**The screening is now cheap.** A candidate no longer needs closed-loop gait sweeps:
measure its phase contribution open-loop at the operating band (`tools/loop_medium.py`
machinery), add the receptor arctans, read the predicted frequency per medium. A mechanism
that cannot move the predicted crossover between K = 9 and K = 1.58 is dead before any
behavioural assay runs.

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
