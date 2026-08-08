# NEXT

What to do next. Nothing else.

This file is deliberately short and is meant to stay that way. Measurements, discarded
hypotheses, retractions and the reasoning behind the items below live in
[`docs/research-log/`](docs/research-log/) — that record is complete and is not to be
edited. If you are new here, read [`docs/project-architecture.md`](docs/project-architecture.md)
first; it says which of the two tracks below you are working in and what must not blur
between them.

---

## Reference worm

**1. Sweep `proprio_reach` against wavelength, in every medium.** This is the sharpest
unexplained thing in the model and nothing has ever been aimed at it. The animal changes
wavelength by **2.37×** between crawling and swimming; this model changes it by 1.01–1.17×
under *every* configuration tried so far — three head-lag budgets, four force-velocity
strengths, two head-reflex architectures, four internal-damping values. Wavelength is set by
a fixed proprioceptive reach with nothing scaling it by load.

Cheap and well-posed before it is expensive: sweep the reach across both media and find out
whether wavelength can be moved at all, and whether moving it drags the frequency span with
it. If reach sets wavelength without touching the span, frequency and wavelength are
*separate* failures needing separate mechanisms — worth knowing before anyone builds either.

Frequency modulation has already cost four mechanisms. **Do not re-run these:**

| tried | result | do not re-run as |
|---|---|---|
| the head cascade's frequency-dependent phase | 1.27× vs 1.29× span | a stage count or a lag budget |
| cutting the fixed head lag fourfold | 1.29× → 1.40× | a smaller head reflex |
| muscle force-velocity (`fv_vmax`) | 1.27× → 1.17×, i.e. worse | a stronger derating; also unstable there |
| body internal damping, down to zero | 1.02× on agar, 1.04× in buffer | a mechanical-dissipation problem |

`tools/head_medium.py`, `tools/lag_span.py`, `tools/force_velocity.py`,
`tools/damping_sweep.py`. Full arguments and tables in the research log.

**2. Decide the head cascade on its own merits, then port it.** Four first-order stages of
0.125 s with `head_delay = 0` match the shipped frequency and beat it on everything else in
every medium (travelling index +0.880 vs +0.846 on agar, +0.761 vs +0.657 in buffer; net
speed 0.369 vs 0.295). It retires the model's largest fitted number and the 210,936-byte
`headHist` ring with it. **The argument it was built for failed** — it does not fix gait
modulation — so adopt it, if at all, as a simplification rather than as a mechanism.

Before adopting: `tools/scorecard.py` and `tools/ethogram.py` against the frozen baseline on
identical seeds, trajectory guards reported. **And it cannot become the default until it
exists in `wasm/assembly/index.ts`** — `head_stages`/`head_stage_tau` are Python-only today.
See [`docs/runtime-parity.md`](docs/runtime-parity.md).

**3. Second tier**, subordinate to the above because changing the shared gait moves every
behavioural assay at once:

- **Gait-modulation magnitude.** Direction is right (0.66 Hz agar → 0.85 Hz buffer); the
  animal goes 0.30 → 1.76 Hz. Size, not sign.
- **Backward locomotion.** The A-class wave reverses, but curvature and net speed stay poor
  after AVB is removed. Do not cite it as a working phenotype.
- **Taxis magnitude.** Chemotaxis, thermotaxis and aerotaxis point the right way with small
  outcomes. Re-run after a turn-depth mechanism clears its own paired gate; do not tune the
  assays around the current shallow turn.

---

## Digital Life Laboratory

Evolved animals are not *C. elegans*. Nothing below produces a claim about the animal — see
[`docs/project-architecture.md`](docs/project-architecture.md) §1.

**1. Export the raw muscle `G`, and finish the exporter rework.** This unblocks heritable
weights *and* topology together. The graph is already in the payload as CSR, so weights need
no format change, and `computeRestingPotentials` already solves for `V_th` on the runtime
and agrees with the exporter to 6.395e-14 mV. The one remaining blocker is narrow: the
exported muscle `G` is *post*-`_balance`, so the balance can be neither recomputed nor
checked from the payload. Export the raw one alongside it and port the bisection — 70
iterations over 95 cells, no linear algebra.

**2. Make egg production depend on laying having made room for it.** `EVO_FITNESS=eggs` is
measured to be intake in different units, because `laid + held` is conserved across a laying
event and egg production is therefore blind to the egg-laying circuit by construction. A
real uterus is not a bucket that fills regardless. Small model change; it is what makes the
feeding → transport → HSN/VC chain load-bearing at any assay length.
`wasm/eggs-fitness.test.mjs` keeps the current limitation attached to the measure.

**3. Re-run the adversarial probe once the genome is bigger.** Priced: twelve seeds, about
five and a half hours, to bring the standard error low enough for the effect size seen at
three seeds to clear it. Not worth spending before (1) — the current fifteen genes were
chosen so nothing in them can reach a conversion factor, so a null result there is the gene
list working rather than the model being clean.

---

## Infrastructure and validation

**1. CI is paused at the jobs, not at the triggers.** Every job is gated on the repository
variable `CI_ENABLED`; set it to `true` under Settings → Actions → Variables to re-enable.
Until then the gates run locally and there is one command:

```bash
npm run check                  # every gate CI would run, in the workflows' own order
npm run check -- --rebuild     # ...plus the ones that regenerate .model/.wasm/celegans.json
npm run check -- --python      # ...plus the ~37 minute pytest suite
```

A skip is never counted as a pass. `--strict` makes any skip a non-zero exit.

**2. Three Python-only step paths exist and are pinned.** `head_stages`/`head_stage_tau`,
`fv_vmax` and friends, and `omega_wave_suppression` are implemented in Python and not in the
runtime. All three are off by default and `tests/test_runtime_parity.py` fails if one is
switched on without the runtime work. This is a guardrail, not a bug list — Python is
allowed to be a research superset. See [`docs/runtime-parity.md`](docs/runtime-parity.md).

**3. Two standing habits, neither optional.** Run `npm run check` before pushing. And a
check is not real until you have watched it fail — `tools/audit.py --only <name>` takes
seconds.

---

## Blocked, or needs an owner decision

- **Which comes first, the reach sweep or the cascade port?** Both touch the shared gait, so
  they should not be in flight together. The reach sweep is cheaper and answers an open
  question; the cascade already measured better on every axis but needs a runtime port
  before it can be a default. No engineering argument settles the order.
- **What to do with the 25 uncertain tools.** Classified in [`tools/README.md`](tools/README.md),
  none moved. Whether the finished probes get archived under `tools/experiments/` is a taste
  call about how much of the record should stay executable.
- **Whether `tools/optimise.py` is still a live path** now that `wasm/evolve.mjs` exists.
  They search overlapping parameter sets and only one of the two lists is pinned by a test.

---

## Recently completed

A short rolling list, so this file stays honest about what moved. Detail in the research log.

- **The viewer scrubs.** `web/viewer/history.js` keeps a byte-budgeted ring of past frames
  and the transport bar walks it. This was *Third tier / nice to have* for most of the
  project's life.
- **The runtime solves for its own resting potentials**, and agrees with the exporter to
  6.395e-14 mV (`wasm/solve.test.mjs`). Half the exporter rework turned out to be done.
- **Force-velocity measured and not adopted** — more faithful muscle, and it costs the crawl
  where the model is calibrated. Kept, off by default, as a counterfactual.
- **Contested feeding settled onto the runtime's rule** rather than the linear program, and
  the multi-animal conformance case that found the disagreement now guards it.
- **The egg measure was characterised rather than shipped quietly**: it is intake in
  different units, and the test prints that verdict beside every number.

---

## Research history

Measurements, experiments, failed hypotheses, retractions and the full reasoning behind
everything above: [`docs/research-log/`](docs/research-log/).

Historical records are preserved exactly as written. A retraction stays a retraction.
