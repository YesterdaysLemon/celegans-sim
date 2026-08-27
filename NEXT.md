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
further measurement: the swim end wobbles — at muscle coefficients ≥ 0.7 badly (a real
bistability), and at the **shipped defaults** as a recurrent, self-ending ~15 s coil-up
episode (mapped 2026-08-27, `tools/buffer_basin.py` #195: no seed ever stays in; the
2026-08-25 "0.33 Hz by t ≈ 46 s" reading was one episode straddled by the scorecard's own
window; the scorecard prints per-seed frequencies so an episode cannot hide in a ±) — so
re-run the stability grid before moving a knob; and any assay of an enabled-amine configuration
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

**1½. Proprio-as-conductance: measured, REFUSED (#194).** Better than the current on
every forward-gait guardrail (dv_corr −0.73 → −0.82, speed 0.304 → 0.361 mm/s at 5 nS) —
and the behavioural battery showed why that table was incomplete: the conductance
abolishes spontaneous reversals (2.03/min → exactly 0 in clean space; 1 reversal event
against the baseline's 9 off food; reorientation 53° → 13°; chemotaxis approach 15 mm
worse; pirouette conditioning inverted). A conductance shunts as well as drives: both
halves raise the cord's total membrane conductance, so the backward command pushes on a
leakier membrane and loses its lever — the wave keeps its shape and loses its ability to
change direction. Current mode stays the animal; the refusal tables live in
`tools/clamp_occupancy.py` (THE BATTERY), and the default is now pinned in the runtime
registry like every other Python-only path.

**1¾. The AS-class field: measured, REFUSED (#193).** The opening dossier was the best
wave number on record; the behavioural battery said no, twice (2026-08-26, full tables at
`SensoryParams.as_field_gain`). At gain 1.0 turns deepen beautifully (fraction over 120°
+23 points) but the animal veers — heading drift 2.9 → 8.2 °/s, spontaneous reversals in
clean space double, pirouette food-conditioning collapses. At 0.5 the nociception and
chemotaxis guards recover but the navigation gains vanish with them, and the drift stays
detectable (+2.85 °/s). The depth-with-drift coupling is inherent — a standing field rides
the direction gate all the time, not just in turns — so the field ships at 0.0, and the
follow-up hypothesis belongs to the turn-depth thread (#196): a turn-phase-gated field
that exists only while an omega is being commanded. Elsewhere on the sensory roster: **AWB stays
deaf on purpose** (measured three times now — plain OFF, plain ON, and the
OFF+chloride-on-AIZ second chance all lose to deaf; `tools/awb_probe.py` has all three
readings), ADF/ASI/ASG/ASJ wait on a `WorldParams` notion
of food quality (#199), and PVD carries harsh touch — the whole-body contact total
high-passed at `pvd_threshold`, so escape survives ablating the gentle-touch sextet
(Way & Chalfie 1989). The audit itself is `tools/idle_neurons.py`; current reading
112/302 reachable.

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
- **Taxis magnitude — the turn-depth ceiling is CLEARED (#196).** The shared ceiling was
  the omega bias LIFETIME: at `omega_tau = 1.5` s the bias decayed inside one undulation
  period, amplitude never mattered (corr 0.04), and the shipped animal had slid to 13.6%
  of reversals over 120° against its own fitted 32%. `omega_tau = 2.5` restores the
  animal's ~35% with every guard clean (`tools/turn_depth.py` has the sweep;
  `SensoryParams.omega_current` the refit dossier). NOW re-run the taxis magnitudes at
  power: chemotaxis at tau 2.5 already trends better (CI +0.049, approach +5.6 mm) but
  n = 4 resolves nothing under 0.111 — the ASEL → AIB ratio, BAG dwell, and nociception
  d_gain question all deserve their paired re-runs against the deeper turn.
- **Sleep's behavioural surface: measured (#197, `tools/sleep_surface.py`).** Bout
  duration belongs to the circuit (46 s ≈ tau_sleep·ln(0.69/0.25), near-deterministic);
  bout timing belongs to the ecology — intervals run metronomic to 114 ± 114 s depending
  on the animal's own foraging, and on the default plate sleep is a rare late event
  (~7–8 min to onset). The variance the model still lacks against You 2008 is in bout
  *durations*; if that ever matters it should come from satiety reaching tau_sleep, not a
  noise dial. Arousal habituation remains unmeasured. Any long on-food assay contains
  sleep unless it runs the sleepless control (`SleepParams.ris_drive = 0`). The surface
  run also caught the dish rim dropping a roamer (#211).

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
