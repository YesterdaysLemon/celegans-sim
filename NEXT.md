# NEXT

What to do next. Nothing else — no history, no status, no results already recorded elsewhere.
(Settled narratives move, verbatim, to [`docs/research-log/`](docs/research-log/) — most
recently `next-history-2026-08-05-through-2026-08-25.md`.)

New here? [`docs/project-architecture.md`](docs/project-architecture.md) says which of the two
tracks below you are in and what must not blur between them.

---

## Reference worm

**1. Adopt (or refuse) the amine load-sensing path.** Calibration is finished — the settled
locus reaches **+0.847 along the crawl→swim chord, buffer at 89% of the animal's swim
frequency, crawl untouched** — and the runtime port is discharged with per-path conformance
cases. One blocker remains: **the food/load confound on the dopamine scalar**
(`SensoryParams.load_gain` states it; on bare agar `load_gain=60` holds dopamine at ceiling,
the permanent-on-food state, and the behavioural gate measured exactly the reversal
suppression that predicts). Separate basal dopamine from the load response, or power the
amine-only chemotaxis arm to n=12 to confirm the attribution. Two protocol guards bind any
further measurement: the swim end is bistable — at muscle coefficients ≥ 0.7 badly, and at
the **shipped defaults** already measurably (2026-08-25: buffer seed 0 of {0,1,3,5,7} falls
into a 0.33 Hz near-standing mode by t ≈ 46 s while the rest hold 0.85 Hz — the scorecard
now prints per-seed frequencies for every medium so this cannot hide in a ±) — so re-run
the stability grid before moving a knob; and any assay of an enabled-amine configuration
needs a settle ≥ 3 dopamine taus or it measures the transient. Full dossier:
`tools/amine_gait.py` docstring, `docs/runtime-parity.md` (`REFERENCE_CANDIDATE`), and the
research log.

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

**1½. Decide proprio-as-conductance adoption.** The mechanism is built
(`SensoryParams.proprio_conductance`, default 0/off) and measured better than the current
on every gait guardrail (dv_corr −0.73 → −0.82, TWI +0.87 → +0.91, speed 0.304 → 0.361
mm/s at 5 nS; the sweep record is in `tools/clamp_occupancy.py`). What adoption wants:
reference evidence (whole-cell motor-neuron recordings under bend, if the literature has
them), the scorecard/ethogram baseline of item 2's protocol, and a runtime conductance
path ([`docs/runtime-parity.md`](docs/runtime-parity.md) — a Python-only default is not a
default).

**1¾. Finish the cord: adopt (or refuse) the AS-class field.** The mechanism is built and
its opening dossier is the best wave number on record (`SensoryParams.as_field_gain`,
tables at the parameter): +42% speed with the travelling index and dorsoventral antagonism
improving together, 16/16 seeds forward, better in all three media. The remaining gates,
in order: `tools/scorecard.py` + `tools/ethogram.py` against frozen main on identical
seeds; backward locomotion and omega depth re-checked; then the runtime port (Python-only
today, pinned in `RUNTIME_UNSUPPORTED`). Elsewhere on the sensory roster: **AWB stays
deaf on purpose** (measured, both signs hurt — `tools/awb_probe.py` has the reading and
the receptor-level follow-up hypothesis), ADF/ASI/ASG/ASJ wait on a `WorldParams` notion
of food quality, and PVD (harsh touch) is unrouted. The audit itself is
`tools/idle_neurons.py`; current reading 109/302 reachable.

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
- **Taxis magnitude.** Mechanisms point the right way with small outcomes (latest: the
  ASEL → AIB chloride moved both conditional pirouette rates correctly, ratio 0.52 → 0.87
  paired, outcome unmoved — provenance at `NeuralParams.glucl_pre`). Re-run these after a
  turn-depth mechanism clears its own paired gate; do not tune the assays around the
  current shallow turn.
- **Sleep's behavioural surface.** The circuit is in (worm/sleep.py) with its compressed
  clock; unmeasured beyond its own gates: bout statistics against You 2008's satiety
  quiescence, and whether arousal habituation should exist. Any long on-food assay now
  contains sleep unless it runs the sleepless control (`SleepParams.ris_drive = 0`).

---

## Digital Life Laboratory

Evolved animals are not *C. elegans*, and nothing here produces a claim about the animal —
[`docs/project-architecture.md`](docs/project-architecture.md) §1.

**1. Run the built tiers until they bite, then topology.** Heritable weights (tier two),
morphology (tier four's chain-shaped half), metabolism, rot, regrowth and development are
all landed and contracted (`wasm/*.test.mjs`); the first runs are in the research log and
`wasm/arena.mjs`. Open: a dish poor enough that the metabolic tax actually bites (smaller
lawns, shorter `ARENA_METAB_T`), a weight-drift readout in the arena reports (the
genes-only `proprio_gain` climb did not appear under weight mutation — drowned signal or
selection moved into the weights, and the readout distinguishes them), and then the
topology tier (entries added/removed, which changes the CSR pattern the weights ride on).
Branching bodies stay out of scope — engine rewrite, not a mutation.

**1c. The skater trap stays set.** The buffer-skater sighting stands as a sighting;
`wasm/skate.mjs` is the instrument and its first hunts were a NULL with three ecology
facts recorded in its header (founder starvation, the agar founder lottery, laying
stopping in buffer — which bounds any hunt at ~1,200 s unless the plate is topped up).
Re-arm when a richer-plate protocol exists.

**1d. Sex: decide whether the Fisher–Muller thread is worth a verdict.** The study ran
(2026-08-23, archived): a null on speed, two textures — across-seed canalisation under
sex (sd 1.4 vs 6.6 at the F-test's 5% edge) and the study's only stall-and-reversal being
asexual (hitchhiking a sexual dish can undo). The price of a verdict is more seeds and
longer dishes, not new machinery; re-run is one env-var away.

**2. (Superseded for the arena; open for the scalar measure.)** In-dish reproduction
dissolves the fitness degeneracy for Track B's main line. The physiology question stands
only if the scalar `EVO_FITNESS=eggs` measure is to be kept honest for short assays:
**make egg production depend on laying having made room for it** — `laid + held` is
conserved across a laying event, so the measure is intake in different units. It lands in
`worm/egglaying.py`, which is reference physiology that ships in the browser, so §1's
invariant applies: adopting the change needs reference evidence, not the fitness argument.

**3. Re-run the adversarial probe once the genome is bigger.** Priced at twelve seeds, about
five and a half hours. Not worth spending before (1): the current fifteen genes were chosen so
that none can reach a conversion factor, so a null result is the gene list working rather than
the model being clean.

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
