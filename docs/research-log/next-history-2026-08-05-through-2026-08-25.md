# NEXT history: 2026-08-05 through 2026-08-25

The second pruning of NEXT.md, same contract as the first
(next-history-through-2026-08-04.md): NEXT.md is the frontier only, and settled
narratives move here VERBATIM once their items compact to actions. Nothing below
is deleted knowledge — it is knowledge relocated so an agent reading NEXT.md for
what to do next is not wading through what was already done. The full measurement
chains also live where they always did: the tool docstrings and worm/params.py
provenance blocks, which remain the primary record.

## Reference worm — item 1, the amine load-sensing path (through 2026-08-15)

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
thin. **Attribution ran (2026-08-15), and it points at the amine arm.** Amine-only reproduces
the full configuration's suppression almost exactly at the point estimate (triage −1.5
vs the config's −1.5; chemotaxis reversals −3.0 vs −2.8), while cascade-only comes in
weaker (−1.2 triage, −0.8 chemotaxis). Every attribution CI includes zero — the arms ran
at n=4–6 against the full run's n=12, so this is *suggestive attribution, not a
confirmed one* — but the mechanism reads clean: on bare agar `load_gain=60` holds
dopamine at ceiling, which is the permanent-on-food state, and an animal that believes
it is on food everywhere suppresses reversals the way fed animals do. **The food/load
confound is therefore not an accounting worry — it has a measured behavioural
signature**, and separating basal dopamine from the load response is now THE adoption
blocker, exactly where `SensoryParams.load_gain`'s docstring said to look. Powering the
amine-only chemotaxis arm to n=12 would confirm the attribution; resolving the confound
would moot it.

*(The measurement chain that got here — locus, per-medium lock-in, the fv retirement, the
below-K≈8 constraint, the twice-validated open-loop screen — is recorded in the tool
docstrings, `worm/params.py::MediumParams`, and `docs/runtime-parity.md`.)*

## Reference worm — item 1½, the clamp experiment (2026-08-16)

**1½. The clamp experiment ran, and split its hypothesis in half.** H2 (research log,
reflex-gain hypotheses) said proprioceptive input should be a conductance, not a current —
premised on motor neurons pinning the v_clamp rail under drive. Both halves now measured
(`SensoryParams.proprio_conductance`, default 0/off; instrument
`tools/clamp_occupancy.py`, 3 seeds × 30 s, both sweeps 2026-08-16). **The premise is
null**: at shipped defaults the A/B cord pools spend ~0% of sampled steps within 0.5 mV
of either rail — the v_clamp comment's rail touches are brief extremes, not occupancy.
**The prediction survives on its own merits**: translating the signed current as a *pair*
of half-wave-rectified saturating conductances (preferred bend → excitatory toward 0 mV,
anti-preferred → inhibitory toward E_inh — reciprocal inhibition through channels) matches
or beats the current on every gait guardrail: dv_corr −0.73 → −0.82, TWI +0.87 → +0.91,
speed 0.304 → 0.361 mm/s at 5 nS, frequency untouched, 3/3 seeds forward, plateau above
~10 nS. The first cut rectified away the inhibitory half and paid for it (dv_corr
collapsed to −0.06, a third of the speed gone) — the signed current's hyperpolarising
half was real push-pull, and the record keeps both sweeps. Self-limiting is proven at
absurdity (500 nS peaks the pool under 10 mV where 3000 pA pins +45 mV; pinned in
`tests/test_behaviour.py`). **Adoption is open and is not this item**: Track A discipline
wants reference evidence (whole-cell motor-neuron recordings under bend, if the
literature has them) plus the scorecard/ethogram baseline protocol item 2 already
demands, and the runtime has no conductance path yet
([`docs/runtime-parity.md`](docs/runtime-parity.md)) — a Python-only default is not a
default.


## Reference worm — item 1¾, the deaf cells (2026-08-24 – 2026-08-25)

**1¾. The deaf cells, measured.** `tools/idle_neurons.py` (2026-08-24) unions every
input route: 103 of 302 neurons were reachable by the world at the first reading; 48
sensory cells were DEAF — whatever they do in the animal, here transduction never
touched them. **The top two entries are paid off** (second reading: 109/302):
**PHA/PHB** now carry the repellent at the tail and **BAG** the oxygen downshift, both
runtimes, conformance-gated. The escape-direction claim came out the interesting way:
as reconstructed — every synapse excitatory — routing the tail *hurt* (paired escape
−1.37 mm head arm, −0.74 tail; a current step into the phasmids depolarised AVA
*more* than the same step into ASH, +0.714 mV against +0.566 — danger behind
out-commanding danger ahead). PHB → AVA joined the glutamate-chloride list on
Hilliard 2002's antagonism, and the same probes then read +0.572 into ASH against
+0.070 into the phasmids: the head-versus-tail asymmetry at the command level, pinned
by `test_a_repellent_at_the_tail_does_not_command_a_reversal`. BAG's lawn-border
behaviour is now measured (`tools/bag_border.py`, 2026-08-25, 8 seeds paired): the edge
response is real — border turning nearly doubles (2.8 → 5.1 heading flips within 1 mm
of the edge) and excursions end ~2 mm nearer the lawn — but the dwell gain (+0.062) is
carried by 2 of 8 seeds, because the turn the circuit asks for is shallower than the
animal's. That is the second-tier taxis-magnitude ceiling, not a BAG defect; re-run
after a turn-depth mechanism lands. **AWB is measured and deliberately NOT routed**
(`tools/awb_probe.py`, 2026-08-25): injected at either sign — relief-timed OFF or
presence-timed ON — it makes escape from a repellent drop measurably *worse* (paired
d_final −6.8 / −3.9 mm, clearance 25 → 37/45 s), because its principal targets (AIZ 13,
ADF 13 contacts) feed the reversal-adjacent path. Same wrong-way-wiring shape as
PHB → AVA and ASEL → AIB, but no prior measurement here names its receptor fix; the
recorded follow-up hypothesis is an OFF-response AWB with chloride on AIZ, which wants
its own paired run before any list is widened. ADF/ASI/ASG/ASJ (food-quality
chemosensation) stay deferred on a named precondition: the world has no notion of food
quality for them to transduce — that is a `WorldParams` feature first, a routing second.
**The AS class is built and measured, off by default, and it is the best wave number this
repository has produced** (`SensoryParams.as_field_gain`, 2026-08-25, tables at the
parameter): the anterior-field arm at ratio 1.0 improves *every* guardrail at once —
speed 0.281 → 0.399 mm/s (+42%), travelling index +0.886 → +0.936, dorsoventral
antagonism −0.758 → −0.843, frequency stable — 16/16 seeds keep the head-to-tail wave,
and the gain helps in all three media. Anatomy suggested the A-family side (Tolstenkov
2018's wiring bias); the wave chose B, and both arms are on the record. **Adoption is
the open item and it is close**: the scorecard/ethogram baseline against frozen main,
backward locomotion and omega depth re-checked, then the runtime port (Python-only
today, pinned in `RUNTIME_UNSUPPORTED`) — the head-cascade item's exact protocol, with
a far stronger opening dossier. PVD (harsh touch) is unrouted. NOT idle, for the record: HSN/VC (egg-laying
reads them as actuators), DD/VD (cross-inhibition IS the anatomy), and the pharyngeal
circuit (food reaches MC through NSM and the reconstructed wiring — worm/pharynx.py
documents the path).


## Digital Life Laboratory — the skater hunts (2026-08-15)

**1c. The buffer skater wants an instrument — and now has one.** The owner's dish,
switched to buffer, evolved coiled lineages that spin and skate in long arcs (>1500 µm/s
bursts; sighting recorded in `wasm/arena.mjs`). Not an exhibit until measured, and
`wasm/skate.mjs` is the instrument: the full living plate in buffer, logging per animal
per 30 s window the net midpoint displacement, the integrated drag dissipation (the
metabolism's own currency), their ratio (transport: mm bought per unit drag energy), the
signed and absolute curvature means, and net body-axis revolutions. A window is flagged
SKATER on coil + roll + displacement (|kbar| ≥ 3 /mm, |turns| ≥ 2, net ≥ 0.10 mm — the
cohorts sit far apart, so the thresholds are calibration, not biology), and a first flag
snapshots the animal's full heritable state for transplant-and-preserve. `SKATE_MEDIUM=agar`
is the control arm, so "skating is a buffer niche" is testable rather than assumed.
First hunts (2026-08-15, seeds 41/43/47): a NULL — one dish ran the sighting's full
protocol (10 evolved animals into buffer, 1,200 s of attrition) and every window read
as an honest undulator; no skater formed, so the sighting stands as a sighting and the
trap stays set. The hunts did measure three ecology facts, recorded in the tool's
header: buffer-from-birth starves founders before their first lawn, the showcase
scarcity is a founder lottery on agar (3 of 4 seeds extinct pre-hatch), and even an
evolved dish stops laying in buffer — which bounds any future hunt at ~1,200 s of
attrition unless the plate gets richer or a human tops up lawns, as the owner's
browser dish had.


## Digital Life Laboratory — the sex-vs-asex study (2026-08-23)

**The sex-vs-asex study ran** (2026-08-23: `ARENA_RECOMB` 0 vs 1 × seeds 1–3, 900 s ≈
9 generations, equal mutation supply — wmut 0.15/4, mmut 0.1; matings ≈ births in every
sexual dish, so crowding at cap 10 makes recombination effectively obligate). **On
speed, a null**: both arms climb the same genes about the same distance
(`proprio_gain` 30 → asex 34.5 / sex 33.3 at close; `food_gain` 11 → ~13.2 both; ~35
of 3,935 wiring loci moved in both; births 84 vs 88). Two textures worth keeping,
neither yet a claim. (1) The across-seed endpoint spread of `proprio_gain` is far
tighter under sex (sd 1.4 vs 6.6; variance ratio ~22, which at n = 3 sits at the 5%
edge of an F-test) — recombination as canalisation of the *outcome*, not acceleration.
(2) The one stall-and-reversal in the study is asexual (seed 3: 29.6 → 24.7 while F0
swept regardless): a lower-proprio lineage won its sweep on other merits and dragged
the gene backwards — hitchhiking that a sexual dish can undo by letting the good
allele escape its doomed background, and none of the three sexual dishes reversed.
That is the Fisher–Muller argument sticking its head up in one seed; if it is worth a
verdict, the price is more seeds and longer dishes, not new machinery. Logs in the
session record; re-run is one env-var away.


## Settled decisions (moved from NEXT.md's Blocked section)

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

