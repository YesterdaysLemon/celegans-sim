# NEXT

What to do next. Nothing else — no history, no status, no results already recorded elsewhere.

New here? [`docs/project-architecture.md`](docs/project-architecture.md) says which of the two
tracks below you are in and what must not blur between them.

---

## Reference worm

**1. Sweep `proprio_reach` against wavelength, in both media.** The sharpest unexplained
thing in the model, and nothing has ever been aimed at it. The animal changes wavelength by
**2.37×** between crawling and swimming; this model changes it by 1.01–1.17× under every
configuration tried so far. Wavelength is set by a fixed proprioceptive reach with nothing
scaling it by load.

Find out whether wavelength can be moved at all, and whether moving it drags the frequency
span with it. If reach sets wavelength without touching the span, frequency and wavelength are
*separate* failures needing separate mechanisms — worth knowing before anyone builds either.

> **Do not re-run these.** Four mechanisms have already been measured against the
> gait-modulation span and all four failed. The tables are in
> [`docs/research-log/`](docs/research-log/); this is the do-not-repeat list.
>
> | tried | result | do not retry as |
> |---|---|---|
> | the cascade's frequency-dependent phase | 1.27× → 1.29× | a stage count or a lag budget |
> | cutting the fixed head lag fourfold | 1.29× → 1.40× | a smaller head reflex |
> | muscle force-velocity | 1.27× → 1.17×, worse | a stronger derating; unstable there |
> | body internal damping, down to zero | 1.02–1.04× | a mechanical-dissipation problem |

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
bucket that fills regardless. Small model change, and it is what makes the feeding →
transport → HSN/VC chain load-bearing at any assay length.

**3. Re-run the adversarial probe once the genome is bigger.** Priced at twelve seeds, about
five and a half hours. Not worth spending before (1): the current fifteen genes were chosen so
that none can reach a conversion factor, so a null result is the gene list working rather than
the model being clean.

---

## Blocked, or needs an owner decision

- **Reach sweep or cascade port first?** Both touch the shared gait, so they should not be in
  flight together. The reach sweep answers an open question; the cascade already measured
  better but needs a runtime port before it can be a default. No engineering argument settles
  the order.
- **The 25 uncertain tools.** Classified in [`tools/README.md`](tools/README.md), none moved.
  Whether finished probes get archived under `tools/experiments/` is a taste call about how
  much of the record should stay executable.
- **Is `tools/optimise.py` still live** now that `wasm/evolve.mjs` exists? They search
  overlapping parameter sets and only one of the two lists is pinned by a test.

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
