# Where this is, and what to do next

## Start here

Ordered, with the reason each one is where it is. Everything below this section is the
record that justifies the order; this is the part to read if you are picking the project up.

**1. Adopt the head cascade -- but not for the reason it was built.** Four first-order stages
of 0.125 s in series, with `head_delay = 0`, match the shipped frequency and beat it on
everything else in every medium: travelling index +0.880 against +0.846 on agar and +0.761
against +0.657 in buffer, net speed 0.369 against 0.295, net-to-path 0.94 against 0.80. It
retires the largest fitted number in the model and takes `headHist` with it -- 210,936 B,
**89% of an animal**. That is a good change on its own merits.

> **The medium sweep ran and the argument for it did not survive.** The cascade was supposed
> to fix gait modulation, because a saturating `arctan` phase should follow the mechanical
> load where a pure delay's exactly-linear phase cannot. Measured, both arms paired across
> three media and three seeds: span 1.27x shipped against **1.29x** cascade, where the animal
> is 5.87x. A difference of 0.02x is nothing. **Do not re-run this as a stage count or a lag
> budget** -- the two arms are the same shape of animal in every medium, and the difference
> between a saturating phase and a linear one does not reach the gait. See
> `SensoryParams.head_stage_tau` and `tools/head_medium.py`.

  What remains before adoption is only the standing requirement for any change to the shared
  gait: `tools/scorecard.py` and `tools/ethogram.py` against the frozen baseline on identical
  seeds with the trajectory guards reported, then the port to `wasm/assembly/index.ts`.

**1b. And the gait-modulation search has a new and much sharper target.** Measuring all three
media rather than the two ends moved the diagnosis:

> **If you are picking this up and want the destination rather than the route, skip to
> "`proprio_reach` swept against the medium" at the end of this item.** Four mechanisms were
> tested and four failed; the fifth and sixth things tried were not mechanisms but
> measurements, and between them they turn the search into a build:
>
> 1. **Both of the animal's wavelengths are essentially already reachable by this model** —
>    0.60 L on agar at reach 0.10 and 1.30 L in buffer at reach 0.24, against the animal's
>    0.65 and 1.54. What is missing is not range. It is the *selection*.
> 2. **And there is a signal to select on.** The moment-to-curvature lag runs 47.9 → 2.9 →
>    1.1 ms across K = 40 → 9 → 1.58, and it is **the first quantity measured in this project
>    that does not saturate by K = 9** — 26% of its movement is below that point, where
>    everything else manages 6–7%. A neuron can read it as a quadrature phase detector, and
>    this model already holds both of its inputs in the same cell.
>
> Everything between here and there is why those are the surprising answers.

```
  arm      agar K=40   viscous K=9   buffer K=1.58
  shipped   0.656 Hz     0.844 Hz      0.833 Hz
  cascade   0.644 Hz     0.833 Hz      0.833 Hz
```

**The model's modulation appears to saturate by K = 9.** All of it happens between K = 40 and
K = 9 — 1.29x — and from K = 9 to K = 1.58 the table shows 0.99x and 1.00x.

> **Qualified after the fact, and the qualification matters.** That last step is *one FFT
> bin*. `tools/diagnose_loop.py` took the dominant frequency as a bare `argmax` with no
> interpolation until this was found, so every frequency published here is a multiple of
> 1/30 Hz or a three-seed mean of them — and the `sd = 0.000` columns are the quantiser, not
> reproducibility. The estimator interpolates now and resolves a known tone to better than
> 0.5 mHz. What survives regardless is the size of the gap, 1.29x against 5.87x; whether the
> last leg is flat or weakly alive matters much less than that.

The animal does not saturate, which is how it reaches 1.76 Hz. So this is not a uniformly
weak response wanting a bigger gain; it is a response that has largely **stopped by the time
swimming begins**.

> **Amended at the end of this item, and this is the amendment that matters most.** What
> saturates by K = 9 is everything the *nervous system is currently reading* — frequency,
> wavelength, bend amplitude, bend per unit commanded moment, all putting 6–7% of their
> movement below that point. It is not a property of the animal's mechanics. The
> moment-to-curvature lag falls 47.9 → 2.9 → 1.1 ms and puts **26%** of its movement in that
> same leg. The model's *body* tracks the whole drag continuum. Its *circuit* has simply never
> been given the one quantity that does.

And frequency was never the only half. **Wavelength is flat and nobody was watching it**: the
animal goes 0.65 L to 1.54 L, a factor of 2.37, while this model goes 0.83 to 0.91 -- 1.10x,
and the cascade 1.06x. At low K an undulating body converts almost nothing to forward
progress, so waveform is what is left to change, and this animal does not change it. Net speed
in buffer is 0.038 mm/s against a real swim of roughly 0.4: it undulates at a plausible
frequency and goes nowhere.

**And that question now has an answer, so this is no longer a search.** The first suspect was
the body's own internal damping: `internal_damping` is a constant while external drag falls
four and a half orders of magnitude, and its docstring's "negligible against the external
medium" is a claim made on agar. `tools/damping_sweep.py` tested it, four values down to
**zero**, both media, three seeds — and it moves buffer by 1.04x and agar by 1.02x. Switching
off mechanical dissipation in the body entirely buys 0.03 Hz. The documented claim survives in
the regime it was never tested in, and the cheap suspect is eliminated.

What that leaves is structural, and it means **no amount of tuning fixes this**:

> The frequency is set by where the loop's total lag reaches half a period, and that total is
> a sum of fixed constants plus **exactly one** term that depends on the medium — the body's
> drag response. `head_tau` 0.22 s, `head_delay` 0.28 s, `tau_calcium` 0.060 s, `tau_tension`
> 0.035 s, the synapses: all constants. The muscle is `calcium -> tension` through two
> first-order lags with **no dependence on shortening velocity at all**.
>
> Measured on agar, frequency goes as roughly 1/lag — 0.22 s gives 1.300 Hz, 0.50 s gives
> 0.65 — and **two structurally different implementations of the same 0.50 s land within
> 0.012 Hz of each other.** The ceiling is set by the lag's magnitude, not its shape, which is
> the cascade's failure reported from the other direction.
>
> So by K = 9 the body's contribution is already small against the fixed remainder, and below
> that the frequency is pinned by constants the medium cannot reach. The wavelength, set by a
> fixed proprioceptive reach, has nothing to scale it either. **The animal saturates because
> the model gave it exactly one way to feel the medium, and it runs out.**

> **Retracted the same day it was written, by `tools/lag_span.py`.** The diagnosis above
> predicts that shrinking the fixed lag exposes the body's load-dependent contribution and
> widens the span. Cutting the head budget fourfold, 0.500 s to 0.125 s:
>
> ```
>   head lag   agar Hz   buffer Hz   span
>   0.500       0.644      0.833     1.29x
>   0.250       0.967      1.300     1.34x
>   0.125       1.356      1.900     1.40x
> ```
>
> Frequency really is set by total lag — a fourfold cut roughly doubles it in both media, so
> that half stands. But the span barely moves, and it could not behave that way if the media
> differed by an additive lag. Fitting the additive model to those points puts the buffer-end
> body lag near 0.8 s, larger than the head reflex's whole budget, which a body with almost no
> drag on it cannot be doing. **"The body's drag response is the one load-dependent term" was
> the wrong reading of the saturation**, and what produces even the 1.3x that exists is not
> identified. Two hypotheses eliminated, none confirmed.

**What survives the retraction, and is worth more than it was:**

- **Wavelength never modulates at all** — span 1.06x, 1.01x, 1.03x at the three lag budgets,
  against the animal's **2.37x**. It is flat at every lag, in every medium, under every
  configuration tried so far. The frequency story has moved twice; this one has not moved at
  all, and nothing has yet been aimed at it. Wavelength is set by a fixed proprioceptive reach
  with nothing scaling it, and that is now the cleanest unexplained thing in the model.
  *Half-superseded at the end of this item, and the correction is the flat kind rather than
  the interesting kind: the wavelength was flat in every configuration above because every one
  of them held the reach fixed. Aimed at directly, it moves 1.7× in both media. "Wavelength
  never modulates" was a statement about what had been varied, not about the model.*
- **The shipped lag budget is near-optimal for the wave.** Cutting it degrades everything
  else — travelling index 0.880 → 0.753 on agar and 0.761 → 0.434 in buffer, buffer net speed
  0.039 → 0.016 mm/s, wavelength collapsing 0.86 → 0.48 L. A shorter loop is a faster, worse
  animal. The cascade should keep its 0.50 s.

**Force-velocity was measured too, and it is not the mechanism either.**
`MuscleParams.fv_vmax` exists, off by default; `tools/force_velocity.py`, both media, three
seeds, no failures:

```
  vmax   agar Hz   buffer Hz   span    wavelength span
  off     0.656      0.833     1.27x       1.10x
  1000    0.622      0.767     1.23x       1.10x
  700     0.600      0.733     1.22x       1.16x
  500     0.600      0.700     1.17x       1.17x
```

The span does not widen; it **narrows**, monotonically. That is the failure the sweep's own
header predicted before the run: the derating acts on shortening rate, shortening rate is a
property of the gait rather than of the medium, this gait is similar at both ends, so it
applies about equally at both and cancels out of the ratio — while adding lag, which narrows
it. Not adopted: it is more faithful muscle than none and it costs the crawl, which is where
the model is calibrated.

> **"Monotonically" is over-read, and the sweep at the end of this item is what shows it.**
> Every span in this table — and in the cascade, damping and lag tables above — is a ratio of
> two *pooled* means with **no error bar on it at all**. `tools/reach_span.py` was the first
> to compute spans per seed and average those, and the typical seed sd it found is **±0.44**.
> Against that, 1.27 → 1.23 → 1.22 → 1.17 is one plausible draw out of many; the ordering is
> not evidence. What survives is the size, not the shape: none of these arms comes within a
> factor of four of the animal's 5.87×, and a 0.44 error bar cannot rescue that. **Every
> "mechanism failed" conclusion above is safe. Every claim about the direction or the
> ordering of the small differences between them is not**, and the four tools that produced
> them should be moved onto per-seed pairing before any of those numbers is quoted again.

**Four mechanisms tested, four failures**, and it is worth having them in one place so
nobody re-runs them:

| tried | result | do not re-run as |
|---|---|---|
| cascade's frequency-dependent phase | 1.27x vs 1.29x | a stage count or a lag budget |
| body internal damping, down to zero | 1.02x agar, 1.04x buffer | a smaller `internal_damping` |
| cutting the fixed lag 4x | 1.29x → 1.40x | a smaller head reflex |
| muscle force-velocity | 1.27x → 1.17x | a stronger derating; it is also unstable there |

All four are frequency mechanisms, and that is the pattern rather than a coincidence: the
frequency is what every one of them was aimed at, because the frequency is what had been
moving. The thing that finally gave was the column nobody had touched.

**So proprioception is next, and the wavelength column is why.** Across every configuration
above — three lag budgets, four force-velocity strengths, two head-reflex architectures, four
internal-damping values — the wavelength span has been 1.01x to 1.17x against the animal's
**2.37x**. Frequency has moved for all sorts of reasons today. Wavelength has essentially
never moved, and **nothing has ever been aimed at it**. It is set by `proprio_reach`, a fixed
fraction of the body, with nothing scaling it by load; the one arm that nudged it at all was
force-velocity, which touches the muscle rather than the reach.

That experiment has now run, and it is the first thing in this search to come back with
somewhere to go.

### `proprio_reach` swept against the medium: the range is already there, the selection is not

`tools/reach_span.py`, four reaches × two media × three seeds, 24 trials, no failures, on the
instrumentation after both measurement defects were fixed. Full table in
`SensoryParams.proprio_reach`; the two rows that matter:

```
  reach  medium | freq Hz         wavelen   TWI    k_rms  net mm/s  n/p
   0.10  agar   |  0.662 +-0.003    0.60   +0.756   3.82   0.2281   0.91
   0.24  buffer |  0.856 +-0.001    1.30   +0.808   4.54   0.0545   0.64
```

**Both of the animal's wavelengths are essentially already reachable.** It crawls at 0.65 L
and swims at 1.54 L; this model gives 0.60 L on agar at reach 0.10 — on the nose — and 1.30 L
in buffer at reach 0.24, which is 16% short. (Reach 0.32 in buffer gives 1.55 L, but see
below: that one is bought by wrecking the gait, so 1.30 is what is reachable and creditable at
the same time.) Nothing is saturated. Nothing is missing from the mechanism. **What is missing
is the selection** — anything at all that tells the reach which medium the animal is in.

Three things make those two cells worth building on rather than a lucky pick out of the noise:

- they are the two **tightest** cells in the whole table, frequency sd 0.003 and 0.001 Hz
  against 0.229, 0.261 and 0.295 elsewhere;
- buffer at 0.24 is a **better animal** than the shipped 0.16 in buffer on the columns that
  matter here — TWI +0.808 against +0.657, net speed 0.0545 against 0.0380 mm/s, wavelength
  1.30 against 0.91 — so the wavelength is not being bought by wrecking the gait. It is not
  better on *every* column: net-to-path goes 0.70 → 0.64. It covers 43% more ground per second
  along a slightly less direct path, which is a trade and not a free win, and the direction of
  that trade should be checked against the ethogram before adoption. (Reach 0.32 in buffer
  hits 1.55 L, almost exactly the animal's 1.54, and *is* bought by wrecking the gait: TWI
  +0.479, n/p 0.37, net speed below the shipped value. 0.24 is the honest target, not 0.32.)
- reach moves the wavelength ~1.7× in **both** media — 0.60 → 1.05 L on agar, 0.90 → 1.52 L in
  buffer — so the mechanism is not saturated at the swimming end. **The wavelength is FIXED,
  not STUCK**: it has a working range and no input from the medium. That is a wire that was
  never run, which is the cheapest of the four outcomes this sweep was written to distinguish.

The implied span, reach 0.10 on agar to 0.24 in buffer, is about **2.2× against the animal's
2.37×**. That is a prediction and not a result — the cells above are per-cell means off an
unpaired grid — and it has to be measured per-seed-paired before it is claimed.

> **And the sweep's own verdict overstated how it got there, which is worth more than the
> verdict.** It printed "the span does not respond to the medium". It is not entitled to
> that. The flatness test is `trend ≤ max(0.20, 2·sd)`, and it fired on **trend 0.58 against
> a threshold of 0.88** — flat because the error bars are huge, not because the trend is
> small. The per-reach spans are 2.05 ±1.21, 1.09 ±0.06, 1.15 ±0.35, 1.47 ±0.15: 59%
> relative spread at the low end. Whether the span responds to reach is **unresolved at three
> seeds**. What survives is the within-medium half, which divides no noisy numbers. The
> threshold was right and has not been retuned; the tool now prints `trend` against
> `threshold` and says outright when the scatter rather than the floor set it, because a
> verdict that cannot be checked from its own output is how the last one got believed.

**The build is small, and the seam exists.** `Senses.step` already blends two banks of
receptive fields through `Modulators.wavelength_shortening` — dead code today, because
`ModulatorParams.dopamine_wavelength` is 0.0. It only shortens, towards `proprio_reach_food`,
so lengthening in buffer needs a third bank and a signed blend. `_receptive_fields` normalises
every row to unit sum, so a bank at any reach carries the same total weight and `g_scale_prop`
needs no recalibration.

**What it must not be is a medium sensor.** The animal has no such thing, and neither should
this. The load signal has to be something the nervous system could actually have — which is
the standing problem, because **there is no force, velocity, tension or effort afferent
anywhere in this model.** The nervous system only ever senses geometry. That is the same
finding from the other side: the medium reaches the circuit only through realised body shape.

### And there is a signal. It is the first thing here that does not saturate by K = 9

`tools/load_signal.py` asked whether *anything* in this animal's own geometry knows which
medium it is in, because the answer might have been no — and if no geometric quantity
separates the media, a load-dependent reach is not badly built, it is **unbuildable**, and the
model needs an afferent it does not have. Three media × three seeds, seven candidates:

```
  signal                          agar    viscous   buffer   buffer/agar  leg2  vs gait
  bending amplitude               4.588    3.791    3.739       0.816      7%    0.8x
  bend per unit commanded moment 14.445   12.388   12.273       0.850      6%    0.7x
  moment -> curvature lag, ms      47.9      2.9      1.1       0.022     26%   15.3x
  travelling index                0.849    0.724    0.657       0.774
```

**The moment-to-curvature lag is the signal.** And the column to read is `leg2` — the share of
a quantity's movement happening *below* K = 9 — not the ratio. Every other quantity in this
model puts 6–7% of its movement there. That is the shape of every frequency table above and
the entire reason this search exists. The lag puts **26%** there: a further 2.6× drop across
the leg where amplitude manages 1.4% and frequency 1.6%.

So the standing diagnosis needs amending. It has never been that *nothing* in this animal
tracks the drag continuum below K = 9 — **something does, and it has never been wired to
anything.**

**Two candidates separated the two ends and were thrown out, which is the other half.**
Amplitude and compliance both saturate by K = 9, and both move by about what the travelling
index moves — TWI −22%, amplitude −18%, compliance −15%. Same size, same shape. A signal that
moves no more than the gait's own deterioration is at least as likely to be reading *this
animal is swimming badly* as *this animal is in water*, and a reach driven from it would be
positive feedback on gait failure. Separating agar from buffer is the easy half and it is not
the half that matters.

> **And the mechanism the sweep was built around is refuted by the sweep.** Its header argued
> compliance would be *low* on agar — "a body pushing against a stiff medium bends less for
> the same muscular effort". It is **higher** on agar, 14.445 against 12.273: the sign is
> backwards. What compliance tracks is the bend amplitude falling, which is the gait confound.
> The lag survives on the time-domain argument alone; the amplitude-domain argument that
> motivated the compliance column was wrong, and the column earned its place by failing.
>
> The verdict also had to be tightened after the fact. It first passed all three of amplitude,
> compliance and lag, because it tested only separation and monotonicity — neither of which
> notices a signal that saturates where it matters or one that merely tracks the gait. Both
> are columns now, with thresholds fixed in the constants. Replaying the measured numbers
> through them cuts three usable signals to one.

**Can a neuron compute a lag? Yes, and this model is unusually well placed for it.** A cell
cannot cross-correlate, but it can multiply its own output by its own sensory input and
low-pass the product — a phase detector — and **both signals are already in the same cell**:
B-type motor neurons *are* the stretch receptors (Wen et al. 2012), so the cell commanding the
bend is the cell reading it. No new pathway is needed.

The form matters, though, and the obvious one fails. At these frequencies 47.9 ms is only
**11.9°** of phase, and `cos` is flat near zero:

```
  in-phase   output x proprio        buffer/agar 1.02   -- useless
  quadrature output x d(proprio)/dt  buffer/agar 0.028  -- 36x, second leg still 0.37
```

So the buildable form is the **quadrature** product. It keeps 36× of the 45×, and keeps the
property that actually matters — the viscous-to-buffer leg still falls 2.7×, where an in-phase
detector reads 1.0001 and is blind over exactly the half of the continuum that needs it. That
is arithmetic off the measured lag rather than a measurement, and it is written down here
before being built.

**So the next build is well posed**: a quadrature phase detector on each B-type cell's own
output against its own proprioceptive input, low-passed, driving a signed blend between
receptive-field banks at reach 0.10 and 0.24. Then `tools/scorecard.py` and `tools/ethogram.py`
against the frozen baseline before anything is adopted.

**And a warning that came out of this sweep unasked for.** The shipped 0.16 is the
reproducible one: frequency sd 0.012 and 0.023 Hz there against 0.229, 0.261 and 0.295 at
reaches away from it. The gait is fragile off the value it was fitted at — this file's
standing bistability warning, now visible in a sweep that was not looking for it. Anything
that moves the reach at runtime has to carry that, and the 0.10/0.24 pair being the two tight
cells is what makes it survivable.

Before adopting anything that touches the shared gait, freeze the baseline with
`tools/scorecard.py` and `tools/ethogram.py` on identical seeds — it can move every
behavioural assay at once.

**1c. The five sweep tools are on per-seed pairing now — so re-run them before quoting any
span above.** The code is done; the numbers in this file are not. Every span printed above was
a ratio of two *pooled* means, and a ratio of two means has **no error bar at all**.

`tools.assays.paired` computes the statistic within each seed and averages those, which is
what the tools now call. Three defects it cures, and the third is the one that bites:

- **no spread.** A bare ratio invites belief in its last digit. Per-seed values give a sd for
  free, which is what makes a `2·sd` threshold meaningful rather than decorative.
- **animal-to-animal variance stays in.** The seeds are the same in both arms by construction —
  `tools/compare.py`'s common-random-numbers argument, applied to sweeps — so pairing cancels
  most of the variance instead of adding the two arms'.
- **survivorship bias.** Pooling lets the two ends come from different seed subsets. When a
  buffer trial diverges and its agar partner does not, the numerator loses a seed the
  denominator keeps and the ratio silently compares different animals. Not hypothetical:
  `force_velocity.py` records buffer diverging at every value it first tried.

Each tool's verdict now names the case where the scatter, not the effect, decided the call.
`tests/test_stats.py` pins the helper — including a case where a pooled ratio is wrecked by one
missing seed and the paired one is not, watched failing first.

Two smaller defects of the same family are fixed too, both watched failing first:
`force_velocity.py` took `spans[0]` as the force-velocity-off baseline, which is the off arm
only while the off arm completes — a diverged one silently promoted `vmax = 1000` to the label
"(off)". It now looks the baseline up by value and refuses to print a verdict without it.
`damping_sweep.py` had one verdict branch covering two opposite outcomes, so "damping moves
the crawl and not the swim" — the one arrangement that would make removing it *narrow* the
span — printed the text written for "damping moves both".

Until the re-runs happen, the honest form of every span in this file is **"about 1.3, and this
project cannot yet say to what precision"**. The conclusions built on them survive that, because
they rest on the gap to 5.87× rather than on differences of 0.02; the trend *shapes* do not.

**2. Export the raw muscle `G`, and finish the exporter rework.** The graph is already in the
payload as CSR, so weights need no format change; `computeRestingPotentials` already solves
for `V_th` on the runtime and agrees with the exporter to 6.395e-14 mV. The remaining blocker
is narrow: the exported muscle `G` is *post*-`_balance`, so the balance can be neither
recomputed nor checked from the payload. Export the raw one alongside it, port the bisection
-- 70 iterations over 95 cells, no linear algebra -- and tiers two and three of the evolution
project are unblocked together.

**3. Make egg production depend on laying having made room for it.** `EVO_FITNESS=eggs`
exists and is measured to be intake in different units, because `laid + held` is conserved
across a laying event and eggs produced is therefore blind to the egg-laying circuit. A real
uterus is not a bucket that fills regardless. This is a model change rather than a fitness
change, it is small, and it is what would make the feeding -> transport -> HSN/VC chain
load-bearing at any assay length.

**4. Re-run the adversarial probe once the genome is bigger.** Priced: twelve seeds, about
five and a half hours, to bring the standard error down far enough for the effect size seen
at three seeds to clear it. Not worth spending before step 2, because the current fifteen
genes were deliberately chosen so that nothing in them can reach a conversion factor -- a
null result there is the gene list working, not the model being clean.

**Two standing habits, neither optional.** Run `npm run check` before pushing; it runs every
gate CI would and reports what it skipped rather than counting a skip as a pass. And a check
is not real until you have watched it fail -- `tools/audit.py --only <name>` takes seconds,
and on the day this section was written seven checks were wrong before they were right, six
of them written by the person who then had to find out.

## Decided: the shape of the evolution project

Settled 2026-08-03, and written here because until now it lived only in a conversation.
The section below it predates all of this and is stale in one important way: it describes
evolution as not started, when tier one has been running in `wasm/evolve.mjs` for some time.
Read this first and that as history.

**Fitness is `energy`, and `eaten` is an adversarial probe rather than a default.** #37
measured `food_eaten` as exploitable — `volume_per_pump` ×10 buys 9.3× the score at a
trajectory unchanged to five figures — and `evolve.mjs` already implements the replacement.
`EVO_FITNESS=eaten` is kept, and running it deliberately to see what the model will let a
population get away with is a *use*, not a fallback: it is `tools/audit.py`'s move, aimed at
the model instead of at the checks. Results from it are defect reports.

**All four tiers are wanted heritable: parameters, synaptic weights, topology, morphology.**
Tier one (the 15 bounded scalars in `worm/genome.py`) exists. The rest do not.

**Weights and topology land together.** Topology forces the exporter to carry the graph
rather than its precomputed products — `_balance` and `_resting_potentials` both depend on
it — and once that rework is done, weights ride along for free. Doing weights first would
mean doing the same rework twice.

> **Half of that turned out to be already done, and the paragraph above overstates the
> work.** The graph *is* carried: `tools/export_model.py` writes `G_syn`, `GE_syn` and
> `G_gap` through `Blob.csr`, so topology and per-synapse weight are both in the payload
> already and **making weights heritable needs no payload format change at all.** What is
> baked is the graph's *products*. `_resting_potentials` is now ported and agrees with the
> exporter to 6.395e-14 mV; `_balance` is the remainder, and it needs the raw muscle `G`
> exported alongside the balanced one, because what goes out today is post-balance and so
> the balance can be neither recomputed nor checked from the payload.

**Reproduction goes generational first, then continuous.** Fitness reads egg output, which
requires eating, pharyngeal transport and the HSN/VC circuit all working, inside the
existing generational loop and its harness. The standing in-dish population, where animals
lay eggs that hatch into animals and selection becomes implicit, comes after that behaves.

> **But not eggs *laid*, and that is settled by arithmetic rather than by preference.** The
> rate is 11.0 eggs/hour, so a 20 s assay produces 0.061 eggs and `evolve.mjs`'s 25 s
> default produces 0.076. `eglLaid` is an integer count, so every animal in the population
> lays zero, every individual scores identically, and truncation selection has nothing to
> act on — the selected arm would match the selection-off control by construction and the
> run would read as a null result rather than as a measure with no range. A countable number
> needs about an hour per animal, which at ~1.5 animal-seconds per wall-second is 8 animals
> × 8 generations ≈ **43 hours per seed per arm**. Two orders of magnitude, not a tuning
> problem.
>
> Select on **eggs produced** instead: `eggsLaid * uterus_capacity + eggsHeld`. `getEggsHeld`
> is already exported, the uterus fills from what the pharynx transported, and it moves on
> the feeding timescale rather than the laying one — so it keeps the whole chain load-bearing
> while having range at 20 s. It still needs normalising by `egl_eggs_per_food`, which is in
> the header for exactly that and is `volume_per_pump`'s hole one layer along (#37). Sizing
> measured under #98; the branch is deliberately not written until it has been run, because
> a measure nobody has tested is what that file's own header warns against.

**Evolution runs on the runtime, not in Python**, and evolved animals are fenced off from
every claim about the animal — see "Evolved animals are not C. elegans" in the README.

Two prerequisites are already done. `Body.self_contact_force` and its runtime twin close
#86, so a lineage cannot evolve a body that folds through itself and be scored for it; and
`checkInvariants` now exists on the runtime, where evolution actually runs, so an animal
that stops doing physics scores zero instead of scoring well.

### The one thing the exporter rework needed to know, measured

`_resting_potentials` solves a 302×302 dense system, and the runtime would have to redo it
whenever weights or topology mutate. Porting a dense solve and still conforming to 1e-13 is
the kind of thing that eats a fortnight and then does not work, so it was measured before it
was built:

* the matrix is well conditioned, **cond(A) = 94** — consistent with the docstring's claim
  that it is a strictly diagonally dominant M-matrix;
* a plain LU with partial pivoting, written the way an AssemblyScript port would be, matches
  numpy's LAPACK solve to **3.6e-14 mV, 5.7e-16 relative**;
* and that difference **does not amplify**. Applied to every threshold and run 4000 steps it
  moves nodes by 5.3e-15 mm and potentials by 1.2e-12 mV, against conformance tolerances of
  1e-9 and ~5e-11. Four orders of margin.

So the port is viable and the rework can proceed. `_balance` is the easy half: a 70-iteration
bisection over 95 cells, no linear algebra at all.

## A direction worth thinking about: reproduction and evolution

Not started, and deliberately not started yet — but the WebAssembly port changed what is
cheap, and it is worth writing down what it made possible while that is fresh.

**Animals are cheap, and they are not free.** The 302×302 matrices are *anatomy*:
read-only, identical for every worm, shared. A second animal duplicates only state -- but
that state is **239,360 bytes, 234 kB**, measured off the allocator's own per-worm stride
by `node wasm/memory.mjs`. This paragraph claimed a few kilobytes for a long time, and so
did two other places; nobody had measured it, and it was out by a factor of a hundred
(#33).

That is a budget rather than a freebie, and `wasm/evolve.mjs` is already spending it: at
its default of 8 animals that is 1.8 MB, and it takes `EVO_POP` from the environment with
no ceiling. The real table:

| population | memory |
|---|---|
| 10 | 2.3 MB |
| 100 | 22.8 MB |
| 256 | 58.4 MB |

on top of a ~2.6 MB shared `World` (5 × 256² f64 grids) and whatever the canvas holds. Two
things follow. **`memory.grow` is one-way**, so a run that peaks at 500 animals keeps that
high-water mark for the life of the tab -- size the population for the peak, not the mean.
And **89% of an animal is `headHist`** -- 210,936 B, the 560-sample delay line for
`head_delay = 0.28 s`,
which `README.md` names as one of the two fitted parameters it is least happy about
("nothing that slow exists in a real stretch receptor"). The single largest cost of running
a population is the model's least-defended constant; if that number ever comes down, the
budget improves dramatically.

It was 372 kB an animal until the per-step scratch was hoisted to module level -- 37% of a
worm was working space that `stepAll`, being strictly sequential and single-threaded, only
ever needs one copy of. A population is still not an architectural problem, it is a
throughput one, and throughput is 2.36× real time per animal.

**And the animal is already a file.** `tools/export_model.py` freezes the whole animal into
one block of arrays. That file *is* a genome in every sense that matters here: change a
number in it and you have a different worm, with no code touched.

That framing makes the real question sharp, and it is not a coding question.

**What is heritable?** Three answers, in increasing order of interest and difficulty.

1. **Parameters** — the ~99 scalars: gains, time constants, thresholds. Trivial to mutate
   and immediately meaningful, since `omega_current`, `gate_bias`, `chemo_gain` and
   `serotonin_mod1` all visibly change behaviour. Build this one first, because it can run
   in an afternoon and it will tell us whether the fitness measure is any good.
2. **Synaptic weights** — mutate `G_syn` while keeping the connectome's *topology* fixed.
   Biologically odd (real variation is mostly not per-synapse weight jitter) but it is the
   version that would actually explore the space this model lives in.
3. **Topology** — adding and removing connections. Closest to real evolution, and the one
   that breaks the current framing: the exported model would have to carry the graph rather
   than its precomputed products, because `_balance` and `_resting_potentials` depend on it.

**What is fitness?** Easier than it looks. The animal already eats, and `food_eaten`
depends on the whole chain working — find the lawn, stay on it, pump. It is a genuinely
integrative measure and it already exists.

**What is reproduction?** The honest version needs the egg-laying circuit: HSN and VC, and
another dozen neurons currently doing nothing. That is a satisfying amount of biology to
add, and it connects to the pharynx work — an animal that has eaten enough lays. The cheap
version is asexual copy-with-mutation on a food threshold, which needs no new neurons and
would work today.

**One caution, recorded now rather than after.** Evolution finds bugs, enthusiastically.
Anywhere the model is exploitable — a way to gain food without foraging, a parameter that
makes the integrator unstable in a profitable direction — is where a population will end
up. That is not a reason to avoid it; it is a reason to keep `tools/conform.py` and the
assay suite pointed at whatever comes out. "It evolved a high fitness" and "it evolved a
worm" are different claims, and only one of them is interesting.

> ## Day twenty-two. The checks get somewhere to run, and two of them turn out never to have run at all.
>
> Nothing in the model moved today. Everything below is about whether the things that
> watch it are real, which is the question this project keeps answering badly.
>
> **The gates got one command.** CI is paused at the jobs, so the gates live in two
> workflow files and a README section, in an order that matters —
> `every module parses` before the browser check, so a syntax error arrives as a syntax
> error rather than as a blank rectangle. `tools/check_all.mjs` runs them in that order,
> probes for Docker, Chrome and a Python with numpy, and **skips what it cannot honestly
> do, loudly**. Skips are counted apart from passes and reprinted with the reason and the
> fix; `--strict` makes any skip a non-zero exit. That is the whole design. A local runner
> is what you consult to decide you are finished, so one that folded an unrunnable gate
> into a green summary would be this project's most repeated bug installed in the worst
> possible place. `tests/test_local_checks.py` pins the gate list against both workflows
> in both directions, and its own parser initially matched only `- name:` and so silently
> missed python.yml's discovery step — the file's subject matter caught in the file itself.
>
> **The `?server` viewer had not drawn an animal for some time.** `dish.js` paints bodies
> out of `S.worms` and out of nothing else. `S.worms` arrived with the multi-animal port;
> the socket path predates it, carries one worm, and was never moved onto it. Measured
> before the fix: connected, 98 nodes, t advancing, `S.trail` 40 points long, and
> `S.worms.length` **0**. The page drew a plate, three chemical fields, and a track
> crawling around the dish with nothing at the end of it.
>
> `tools/smoke_server.mjs` is called *"the Python WebSocket reaches the viewer"* and it
> passed the whole time, because the frames genuinely do reach it — node counts, neuron and
> muscle counts, finiteness, the egg fields, no unparsed bytes at the tail, all true.
> Whether the viewer then *drew* them was the one question it never asked, and its name
> reads as though it had.
>
> **A scrubber, and what it cost to size it.** `viewer/history.js` is a ring of past frames
> bounded in *bytes* rather than in frames, because a frame costs 3,376 B per animal —
> measured — so a fixed frame count would quietly mean a 27 MB ring on a populated plate.
> It copies on the way in: `LocalEngine.frame(i)` returns `act`, `V`, `tension` and `kappa`
> as views into WASM linear memory, and `memory.grow` detaches them.
>
> The assertion written to catch exactly that was itself wrong first time. It compared node
> coordinates — but `frame(i)` already allocates a fresh array for the centreline, so nodes
> are copies whether or not the ring copies anything. Replacing the copy step with the
> identity function left every assertion passing. It asserts on `V` now. **A check is not
> real until you have watched it fail, including a check you wrote ten minutes ago for
> precisely this failure mode.**
>
> ### The audit's second round, and the battery that could not ask the question
>
> `tools/audit.py` ran graph, viewer, conform and pytest. CI also runs
> `invariants.test.mjs`, `population.mjs` and `memory.mjs`. `checkInvariants` is owned by
> `invariants.test.mjs` — the file whose own header says a guard never observed to fire is
> not known to work — so **there was no battery a mutation to that guard could be measured
> against.** The audit would have reported "nothing caught it" and been describing itself.
>
> With a `runtime` entry added, two mutations, both imitating *a guard that is present,
> runs, and can never fire*:
>
> | mutation | graph | viewer | runtime | conform |
> |---|---|---|---|---|
> | `wasm/self-contact-inert` | missed | missed | missed | **CAUGHT** (126 s) |
> | `wasm/invariant-curvature-inert` | missed | missed | **CAUGHT** | — |
>
> So #86's self-avoidance is real rather than assumed. It was installed while inert on the
> live animal precisely so it could be shown to change nothing at the one moment that was
> possible, and that argument only held if something would notice it being switched off.
> Something does.
>
> And the curvature guard is caught only by the entry that did not exist this morning.
>
> **`wasm/invariants.test.mjs` appears in no workflow and no README.** The physics guard
> was ported to the runtime because evolution runs there; its test was written, works, and
> has never run anywhere. Now wired into the conformance job and into `check_all.mjs`.
>
> ### And a number that was measured once and then quietly became wrong
>
> `headHist` is **89%** of an animal, 210,936 B. This file and `wasm/assembly/index.ts`
> both carried a much smaller figure, and it was not invented — it was true back when a
> worm cost 372 kB, before the per-step scratch was hoisted to module level. Hoisting
> shrank the animal by a third, which *raised* every remaining array's share, and the two
> sentences quoting that share were not among the things updated.
>
> It survived because `memory.mjs` checked that four documents quote the **total** and
> nothing checked that they quote the **share**. It does now, watched to fail against the
> stale figure. This is #33 in miniature: a measured number, a reason to go stale that
> nobody was tracking, and a check next to it looking at a different number.
>
> It also makes `head_delay`'s case sharper than the roadmap put it. Nine tenths of a worm
> is the delay line for the model's least-defended constant; every other per-worm array put
> together is about 27 kB.
>
> ### And the adversarial probe ran, and priced itself out
>
> `EVO_FITNESS=eaten` was run deliberately, as the top of this file says it should be —
> aimed at the model rather than at the checks. Eight animals, eight generations, 20 s,
> three seeds, with the selection-off control arm. 4,997 s of wall clock.
>
> ```
>   seed |  selected gain |  control gain |  difference
>      5 |        0.01938 |       0.00027 |     0.01911
>     11 |        0.02120 |       0.01925 |     0.00195
>     23 |        0.07338 |      -0.00193 |     0.07531
>
>   selection - control, over 3 seeds: 0.03212 +- 0.02215 (s.e.)
> ```
>
> **No detectable effect of selection**, and the per-seed column is the finding. Seeds 5 and
> 23 read as clear wins — the selected arm gaining 70× and 38× what its control did — and
> seed 11's control gained almost as much as its selected arm. Day eighteen arriving again,
> on a run built specifically to be able to see it. Seed 5 alone would have been written up
> as selection working.
>
> **No exploit was found, and this run is not entitled to say more than that.** It could not
> detect selection at all, so it had no sensitivity with which to detect an exploit either;
> a probe that cannot see the thing it is a control for is not evidence of absence. What it
> bought is a price: about four times the seeds to bring that ±0.022 down far enough for a
> 0.032 difference to clear it — twelve seeds, five and a half hours — and more generations
> would probably do more than more seeds, with eight being few for 15 genes.
>
> Against the pessimism: a null result under `eaten` is what this gene list was *designed*
> to produce. Every one of the fifteen is a sensory gain, a time constant or a decision
> threshold, and none is a conversion factor in front of intake. The version of this probe
> worth real compute is the one after the genome grows to weights and topology, where the
> space is large enough to hold surprises and the argument for why it cannot reach a
> conversion factor has to be made again from scratch.
>
> ### The exporter rework is smaller than this file said, and half of it is done
>
> **The graph was already in the payload.** `tools/export_model.py` writes G_syn, GE_syn and
> G_gap through `Blob.csr`, so *making weights heritable needs no payload format change at
> all*. What is baked is not the graph but its **products** — `V_th`, `V_init`, and the
> muscle balance. The job restates as "give the runtime the two solves", which is a much
> better-bounded thing than "carry the graph rather than its precomputed products".
>
> `computeRestingPotentials` does the hard half. It assembles A and b from the CSR and runs
> a plain LU with partial pivoting, and it lands where the measurement above predicted:
> **6.395e-14 mV, 1.734e-15 relative** against the exporter's LAPACK solve, four orders
> inside the conformance tolerance. Only two constants were missing and only one genuinely —
> `s_half` was always derivable from `a_rise` and `a_decay`; `ca_offset` is now exported.
>
> Nothing calls it. The step still reads the exported `V_th`, so no trajectory moves. What
> the runtime now has is *two sources of truth for the same 302 numbers*, which is this
> project's favourite defect, so `wasm/solve.test.mjs` compares them — and asserts the
> agreement is **approximate**, because an independent LU cannot reproduce LAPACK bit for
> bit and an exact match across all 302 cells would be aliasing rather than a good solve.
>
> Writing that test is what caught the bug. **`g_leak` and `E_leak` are network-wide scalars,
> shape [1]**, not per-neuron arrays. Indexing an 8-byte array by neuron runs off the end
> into whichever array the exporter laid down next, and it is silent: every cell got a
> plausible finite number, and the first sign of trouble was a zero pivot 300 columns later.
>
> `_balance` is the remaining half, and it needs one thing this did not: the exported muscle
> G is *post*-balance, so the balance cannot be recomputed or checked from the payload as it
> stands. The raw G has to go out alongside it — a payload addition, not a format change.
>
> ### And egg fitness turns out to be intake wearing a hat
>
> `EVO_FITNESS=eggs` exists now, and it does not measure what #98 wanted, for a structural
> reason. **`laid + held` is conserved across a laying event** — laying decrements `eglEggs`
> and increments `eglLaid` by the same egg — so eggs *produced* is blind to laying by
> construction. The HSN/VC circuit, the whole reason the measure was wanted, cannot move it.
>
> Measured, three seeds at 20 s: score divided by intake is **5.000000e-3 in every case,
> relative spread 4.195e-11**. It is `ingested`, exactly, in different units.
>
> The prediction that got there was wrong, and worth recording as such. This file argued the
> problem was assay length — 0.061 eggs in 20 s, so everyone scores zero. In fact every
> animal lays exactly one egg, because the uterus starts stocked at `eggs_initial` and the
> first lay is not earned. It simply does not matter.
>
> The fix worth having is a model change rather than a fitness change: **make production
> depend on laying having made room for it.** A real uterus is not a bucket that fills
> regardless, and that single change would make the chain load-bearing at any assay length.
>
> ### And the head cascade works, which retires the largest fitted number in the model
>
> `head_delay` has been the largest fitted number here for a long time, openly recorded as
> unearned — "the size of what the model is missing, stated plainly". Its own note named the
> replacement: a distributed multi-stage circuit accumulates phase a single first-order lag
> cannot. That is now built, measured, and it works.
>
> The first attempt failed for a reason worth keeping. A cascade of N stages of
> `head_tau / N` lowers the frequency — 1.300 Hz at one stage to 1.033 at four, the first
> thing in this project to move it *without* the delay, and it improved the wave doing so —
> but it plateaus far above the shipped 0.656 Hz. The ceiling is arithmetic: that
> construction converges on a pure delay of `head_tau`, worth **51.96°** at 0.656 Hz against
> the 42.20° of the single lag it replaces. Under ten degrees, at any stage count, while
> `head_delay` supplies another 66.12°. It was subdividing the wrong budget.
>
> Given its own budget — `head_stage_tau`, four stages of 0.125 s, totalling the 0.50 s the
> shipped loop actually carries — **with no transport delay at all**:
>
> ```
>   stages delay stage_tau | freq Hz        wavelen   TWI    k_rms  net mm/s  n/p
>     1     0.28    --     | 0.656 +-0.031    0.83   +0.846   4.45   0.2949   0.80  <- shipped
>     4     0.00   0.1250  | 0.644 +-0.016    0.86   +0.880   4.58   0.3688   0.94
>     6     0.00   0.0833  | 0.611 +-0.016    0.84   +0.799   4.52   0.2718   0.75
> ```
>
> Same frequency to well inside the seed scatter, and better on everything else measured:
> travelling index +0.880 against +0.846, net speed 0.369 against 0.295, net-to-path 0.94
> against 0.80. **The delay bought its frequency by giving away the wave. This does not.**
>
> Six stages is *worse*, and that is the more interesting row. More stages is nearer a pure
> delay, and nearer a pure delay is nearer what the model already had. The cascade wins at
> four because it approximates a delay **badly**, in the particular way that makes the loop's
> phase depend on frequency — which is exactly the property `head_delay`'s note says gait
> modulation needs and a fixed delay cannot offer. Argued for a long time; measured now.
>
> **Not adopted, and the gap is coverage rather than doubt.** One assay, bare world, 30 s,
> three seeds. Before it replaces anything it needs `tools/scorecard.py` and
> `tools/ethogram.py` against the frozen baseline on identical seeds with the trajectory
> guards reported, and it needs the medium sweep — gait modulation is the entire reason to
> want this and nothing here has measured it. It is also not ported to the runtime.
>
> If it survives those, `headHist` goes: 210,936 B, **89% of an animal**, a 560-sample ring
> per joint held only to look up one sample 0.28 s old. A cascade is four scalars per joint.
> The population budget in this file — 22.8 MB for 100 animals — improves by close to an
> order of magnitude, and `memory.grow` being one-way stops being the constraint it is.
>
> ## Day twenty-one. Eight more neurons get a job, and the checks get audited.
>
> **Egg-laying.** HSN and the VCs had the pharynx's problem with the opposite cause. The
> pharynx was anatomically isolated and needed a reason to exist; these eight are wired
> deep into the somatic network -- 86 chemical contacts out, 27 in, 4 gap junctions, and
> HSN has been in `serotonin_sources` since the modulator layer was built -- and needed
> somewhere to *send* their output. Vulval muscle is not among the 95 body-wall cells,
> exactly as pharyngeal muscle was not.
>
> The uterus fills from what the pharynx transported, so feeding is load-bearing for this
> rather than adjacent. Measured over five animals for an hour each: **11.0 eggs/hour, CV
> 1.79**, 60% of intervals under a minute and 20% over two. Both tails populated is the one
> shape a timer cannot make, and nothing schedules a phase -- the gaps are a depleting
> resource behind a Schmitt trigger.
>
> Two things it does not do, both written next to the parameters. The median interval is
> 6.0 s, which is exactly `refractory`, so the *fast* half of that bimodality is a number I
> chose; only the slow half emerges. And HSN-ablated animals lay **nothing**, where the real
> phenotype is defective-but-not-incapable. Measuring the drive showed why: with HSN gone
> the vulval muscle spans four hundredths above its median and never comes within 0.05 of
> threshold, so there is no fluctuation for a threshold to catch and any constant flips the
> animal from never to often. That needs stochastic vulval-muscle calcium, which the model
> does not have -- a mechanism, not a better number.
>
> **A modulator bug it exposed.** Ablating a modulator source could *raise* that modulator.
> The level was a mean over the *surviving* sources, so removing a cell whose activation sat
> below its siblings' pushed the mean up: killing HSN took serotonin 0.120 -> **0.219**. The
> sign of every modulator-source ablation depended on where that cell happened to sit
> relative to its siblings. Dead sources now stay in the denominator at resting release;
> with nothing ablated it is arithmetically identical, so no existing result moved. The
> pharynx's five phenotypes still point the right way, and NSM now gets there by the correct
> route.
>
> ### And then the checks were audited, which was worse
>
> `tools/audit.py` applies a deliberate defect, runs the battery, and records who caught it.
> Every mutation imitates a bug this repository has actually shipped. **Four holes on the
> first run**, and the first one is the one to remember:
>
> The egg-laying conformance comparison **had never compared anything**. The runtime side
> read `f.egl`; the Python side never emitted it, because the edit meant to add it anchored
> on text that existed only on another branch and silently matched nothing. A guard then
> turned missing data into a pass, so it printed a perfect `0.000e+0` from comparing zero
> fields -- and that was reported, in the pull request that added it, as bit-identical
> agreement.
>
> Also: three of the four egg variables were constant anyway, because the conformance animal
> starts off the lawn and never eats. `stepAll` -- the only path a browser visitor runs --
> had never been executed by any check. Ablation only ever happened at t=0, so every line
> that clears *live* state was a no-op, while the viewer's Ablate button kills cells
> mid-swim.
>
> Three of those four are the same failure: **a check that runs, passes, and covers less
> than its own comment claims.** That is now this project's most repeated bug, ahead of
> anything in the model. The empty conformance dish that hid the missing field diffusion,
> the lawn-less plate that hid the food skirt, and these are all one mistake.
>
> Three of the ten mutations also came back as false alarms -- the mutation was wrong, not
> the coverage -- and establishing that cost the same work as finding the real holes. A tool
> that cannot tell *"you missed this"* from *"you asked the wrong question"* gets ignored
> within a month.
>
> **The rule that falls out, and it is cheap now:** a check is not real until you have
> watched it fail. `tools/audit.py --only <name>` takes seconds.
>
> ## Day twenty. The repellent stops trapping, and the browser's plate starts ageing.
>
> Two things, one of which was only found because of the other.
>
> **ASH now senses the derivative.** The repellent was the last purely tonic chemical sense
> in the model, and a tonic sense cannot tell approaching from leaving. Same shape as the
> oxygen path — an adapting baseline at `repellent_tau_adapt = 2 s`, a tonic term plus
> `repellent_d_gain = 4000` on the deviation. Against the paired plain-agar control the
> drop now puts the animal **+14.67 mm [+8.04, +21.06]** further out instead of 9.5 mm
> closer, and 12/12 clear it instead of 7/12.
>
> The interesting part is *how* it works, because it is not how the assay was written to
> look. Time-to-clear is unchanged — the animal does not escape faster. It escapes
> **further**, because heading out of the drop makes `drep` negative, which suppresses ASH,
> which suppresses the reversal that would have taken it back in. The old mechanism panel
> now reads 0.22 reversals/min while exposed against 0.58 while clear — the number the
> original assay celebrated went *down* while the behaviour became correct. Outcomes
> against a control, not mechanisms.
>
> **The browser's dish was chemically frozen.** `World.step` diffuses and decays the
> attractant and repellent every 20 ms and was never ported. It survived the conformance
> test for a year of days because the conformance plate was an empty dish, and a field of
> zeros diffuses to zeros. Putting a lawn and a drop on that plate — done for the sensory
> paths, not for this — turned it into a run that agreed to 1e-15 through step 40 and then
> stepped off a cliff at step 41. 41 steps is 0.0205 s. `field_dt` is 0.02.
>
> A second, self-inflicted lesson from the same afternoon: `web/conform.json` was a
> *tracked* file. It is a recording of what the Python did on the day it was made, so a
> stale one does not weaken the check, it inverts it — the port gets measured against a
> model that no longer exists and fails with a 17 mV disagreement that looks exactly like a
> porting bug. It is now untracked and must be regenerated every time, which is what the
> Dockerfile already did.
>
> ## Day nineteen. The pharynx eats.
>
> Twenty neurons were simulated in full and drove nothing. Measured in this reconstruction
> the pharyngeal nervous system makes 203 chemical contacts and 86 gap junctions *within
> itself*, **zero** chemical contacts to or from the somatic nervous system, and four gap
> junctions across — the I1–RIP coupling, the single anatomical bridge, which is why
> Albertson & Thomson called it autonomous. It also makes zero neuromuscular contacts here,
> because pharyngeal muscle is not among the 95 body-wall cells. So it could have been
> deleted without changing a number, while feeding was a flat rate applied whenever the
> head happened to be over food.
>
> Now it pumps, and the pump is what feeds the animal.
>
> **The pump is myogenic and the neurons modulate it** — Avery & Horvitz killed every
> pharyngeal neuron and the pharynx still pumped, slowly, while the animal starved. So the
> oscillator is a relaxation cycle with its own base rate that MC speeds up, M3 shortens,
> I2 slows and M4 gates.
>
> The food signal already travelled that way through the reconstructed wiring, before
> anything was fitted. Dropped on a lawn: NSM 0.390 → 0.969, and from there I2 +0.216,
> M3 +0.080, MC +0.042, M4 +0.045. What was missing was not a signal. It was an effector.
>
> ```
> condition    | off food /min | on food /min | pump ms | ingested /s
> intact       |      33       |     249      |   150   |  0.0143
> MC (eat-2)   |      32       |      22      |   144   |  0.0015
> M3           |       0       |     239      |   180   |  0.0148
> M4           |      16       |     252      |   151   |  0.0022
> I2           |      33       |     258      |   151   |  0.0148
> NSM          |      60       |      40      |   173   |  0.0028
> ```
>
> The rate is fitted — three coefficients put it in the animal's 200–300/min. **The
> ablations are not fitted to anything**, and all five go the right way:
>
> - **MC** — 11× slower and starving. The eat-2 phenotype.
> - **M4** — pumps at a *normal rate* and starves anyway, with food backing up in the lumen
>   to 0.044 against a 0.05 capacity. This is the phenotype that forced capture and
>   transport to be separate steps; a model where ingestion is a property of the pump
>   cannot express it at all.
> - **M3** — pumps lengthen 150 → 180 ms.
> - **NSM** — the on-food rate collapses to the off-food one.
> - **I2** — faster, by disinhibition.
>
> ### Two things the pharynx forced, both bugs elsewhere
>
> **Serotonin had to act *through* MC, not beside it.** Modelled as a parallel term,
> ablating MC cost 5% of the rate — the serotonergic drive simply carried on with no
> pacemaker to act on. Routing it through MC is also the better biology: SER-7 is expressed
> in MC and that is where serotonin's stimulation of pumping acts (Song & Avery 2012),
> which makes the pacemaker epistatic to the food signal.
>
> **An ablated cell was signalling in reverse.** Modulator levels and pharyngeal drives are
> deviations from a resting activation of 0.5, and an ablated neuron reads 0.0 — so killing
> NSM drove serotonin to **−0.133** where it should have gone to zero, and flipped the
> serotonergic turn bias from +0.090 to −0.080. Every ablation experiment that touched a
> modulator source has been reading a sign error. The pharynx only made it visible because
> it turned the pacemaker off outright.

> ## Day eighteen. Error bars, and the first thing they killed.
>
> The assays got confidence intervals and a paired A/B harness, and then the harness
> immediately refuted the hypothesis it was built to test. Both halves are worth reading.
>
> ### The measurement problem
>
> Chemotaxis is sixteen animals scattering by ±12 mm about a mean of −10. A chemotaxis
> index quoted as "+0.070" from that carries an uncertainty near ±0.09 — not
> distinguishable from zero, and certainly not from "+0.014". Days of this project compared
> two such numbers and believed the difference.
>
> Two fixes, one of them free:
>
> - **Bootstrapped intervals** on every headline number, seeded so they are reproducible.
>   Bootstrap rather than normal theory because the samples are small and several
>   statistics are ratios — the pirouette ratio has a denominator that can be zero.
> - **Common random numbers.** `tools/compare.py` runs two configurations in one queue on
>   *identical seeds*, so the animal-to-animal variance — most of the variance — cancels in
>   the difference. Both arms differ by a per-trial parameter override rather than an edit
>   to `worm/`, which also retires the workflow this project has a standing rule against.
>
> ```bash
> PYTHONPATH=. .venv/bin/python tools/compare.py all sensory.omega_current=450
> ```
>
> Every verdict is "no effect detected" unless the interval clears zero, and nulls are
> reported next to the smallest effect the sample could have resolved.
>
> ### And the first thing it killed
>
> The plan was that the omega turn saturates because it is *fighting the head reflex* —
> `head_proprio_gain` is 150 and that reflex regulates exactly the quantity the turn is
> displacing. Standing it down during the transient should buy depth without costing the
> travelling index.
>
> A first look at four seeds showed the median turn going 59° → 89° at half suppression.
> That reads as a clear win. With six seeds and intervals, over 60–69 turns per condition:
>
> | suppression | median turn | >120% | TWI |
> |---|---|---|---|
> | 0.00 | 67.2 [48.5, 89.8] | 13% [6, 22] | +0.88 |
> | 0.40 | 54.9 [39.3, 93.0] | 12% [4, 19] | +0.78 |
> | 0.70 | 65.3 [48.2, 93.2] | 13% [5, 23] | +0.86 |
> | 1.00 | 42.5 [28.0, 72.1] | 3% [0, 8] | +0.82 |
>
> Every interval overlaps every other. **The harness caught a false positive on its first
> real use**, which is the whole argument for building it.
>
> ### What the refutation points at
>
> Turn rate is path speed × path curvature, and path speed is pinned near 0.35 mm/s. A 180°
> turn in the two seconds a real omega takes needs a radius of **0.22 mm** — a 1 mm animal
> curled into a circle a fifth of its length. That is a whole-body coil, and the transient
> only drives head and neck (s = 0.08–0.35). So: drive the body's B-class too.
>
> That fails as well, and the two failures together are the actual finding:
>
> | pool | pA | turn deg/s | path mm/s | TWI |
> |---|---|---|---|---|
> | head + neck | 60 | 19.7 | 0.346 | +0.91 |
> | head + neck | 120 | 1.8 | 0.060 | +0.58 |
> | + body B-class | 60 | 20.6 | 0.100 | +0.52 |
> | + body B-class | 120 | 9.4 | 0.014 | +0.43 |
>
> **Turn depth is limited by dynamic range, not by drive and not by opposition.** A
> sustained bend has to be carried by the same motor neurons already spending their range
> on the travelling wave. A DC offset through them collapses the wave, and without the wave
> there is no forward motion — and turn rate is speed times curvature. Head-only saturates
> near 20 deg/s; whole-body trades away the propulsion and buys nothing.
>
> So the next attempt is not another target set or another gain. The bend has to cost the
> wave less: more headroom in the motor units, or the static component applied where it does
> not compete with the oscillation for the same range. Everything downstream waits on it —
> the ventral bias can come back, and `serotonin_mod1` can be switched on, only once a turn
> is worth what it costs in reversals.

> ## Day seventeen. The worm was flying in circles, and I put it there.
>
> Going after the sensory route for suppressing reversals on food found something else
> first: **the omega turn shipped on day fifteen bends the animal the same way every
> time.** Every turn was ventral by construction, so the heading changes accumulated
> instead of cancelling. On a lawn, where reversals are most frequent, the animal rotated
> at **+17.4 deg/s — a full circle every twenty seconds** — with net-to-path 0.18.
>
> It hid off food, where reversals are half as frequent and the drift reads as noise. And
> it had been misdiagnosed as a reversal-rate problem: the giveaway was that killing
> reversals outright did *not* restore net-to-path, which is what pointed at the turns.
>
> | ventral fraction | off-food rotation | on-food rotation | on-food net/path |
> |---|---|---|---|
> | 1.00 (as shipped) | 5.8 deg/s | 17.0 deg/s | 0.084 |
> | 0.80 | 4.6 | 13.5 | 0.142 |
> | 0.50 | 1.8 | 5.8 | 0.277 |
>
> The bias is not what is wrong — **the turns are too shallow for it**. A real omega turn
> is 160–170°, and at that depth it hardly matters which way the animal bends: it ends up
> reversed either way. Ours are 50–100°, where ventral and dorsal differ by a hundred
> degrees, so a bias the animal carries harmlessly becomes a spiral here.
>
> ### A correction to day fifteen
>
> The reorientation figures reported then — 55.5° median, 24% above 120° — **were inflated
> by this circling**. The measure compares mean heading two seconds before a reversal to
> two seconds after, and at 17 deg/s the spiral lands inside that window. With the drift
> removed the honest figure is 37.7° off food, against a pre-omega baseline of 21.1°. The
> omega turn still nearly doubles reorientation; it does not reach 120° nearly as often as
> claimed.
>
> ### What that bought
>
> Fixing the sign is a clean win with no cost anywhere:
>
> | | before | after |
> |---|---|---|
> | on-food net/path | 0.149 | **0.332** |
> | chemotaxis index | +0.070 | **+0.083** |
> | aerotaxis, lowest reached | 9.8% | 9.9% |
> | nociception, exposed/clear | 5.15 / 0.34 | **7.25 / 0.46** |
>
> ### And the sensory route itself
>
> It was built, and it works, and it is switched off.
>
> The requirement was a signal that exists only on food. Serotonin already is one — +0.013
> off food against +0.160 on it, because NSM is driven by bacteria sampled at the nose and
> not by the diffusible attractant. What was missing was any route to the command layer,
> and there is no synaptic one: **CEP, ADE, PDE and NSM make zero contacts onto AIY, AIB or
> AVA** in this reconstruction, which is why raising `food_gain` elevenfold moves the
> command difference by a tenth of its own standard deviation and then stops.
>
> So it goes through the wireless layer, as a **MOD-1-style serotonin-gated chloride
> conductance** — a conductance, not a current, so it shunts and saturates like the channel
> it represents. AIB is where MOD-1 actually is, and AIB does not work: the channel silences
> it perfectly (activation 0.65 → 0.08, −20 → −45 mV) and the signal reaches RIM (0.573 →
> 0.455), but AVA moves 0.584 → 0.572 and the command difference not at all. Three chemical
> contacts and six gap junctions cannot move a pool that heavily coupled.
>
> On the command pool itself it works, and the food selectivity survives: +0.155 on food
> against +0.014 off it. On-food reversals 6.45 → 2.85 a minute, net-to-path *higher* on
> food than off it for the first time, and a **pirouette ratio of 1.58** — the best this
> model has produced, against every other configuration sitting within noise of 1.
>
> But the chemotaxis index falls +0.083 → +0.014 and aerotaxis weakens. A better mechanism
> and a worse outcome: the model is steering correctly and not far enough, so the reversals
> being suppressed are the same ones carrying the taxis. **Until the omega turn reorients as
> deeply as the animal's, spending reversals costs more than biasing them gains.** That is
> the dependency, and it says plainly what to do next: deepen the turn, then switch this on.

> ## Day sixteen. The on-food latch, and one number serving two masters.
>
> On a lawn the animal spent **57% of its time reversing** at 10 commanded reversals a
> minute against the animal's 0.7–1.25, with net-to-path 0.05. It thrashed in place. No
> gait metric showed it — the travelling-wave index was healthy throughout — because the
> animal was reversing every couple of seconds and retracing its own track.
>
> ### The bug is a bound that was never there
>
> The direction gate is a Schmitt trigger: it flips forward-to-backward below
> `gate_bias − gate_hysteresis` and back above `gate_bias + gate_hysteresis`. A modulator
> adds to `gate_bias`, and nothing limited how much. On a dense lawn the serotonergic turn
> bias reached **+0.103 against a hysteresis of 0.09**, which lifted *both* thresholds
> above the resting command difference. The trigger became a one-way latch — the animal
> fell into reversal and could not climb back out.
>
> Keeping the shift strictly inside the hysteresis is exactly the condition for the window
> to keep straddling the operating point. That is a structural invariant rather than a
> tuned number, and it is now asserted in a test, on the lawn that used to break it.
>
> ### One number serving two masters
>
> How tight to make the bound is not free, and the sweep showed something the model had not
> revealed before:
>
> | limit | chemo CI | aerotaxis end | noci /min | on-food rev/min | on-food net/path |
> |---|---|---|---|---|---|
> | 0.05 | −0.021 | 20.6% wrong | 1.32 | 2.22 | 0.268 |
> | **0.30** | **+0.070** | **14.5% right** | **5.15** | 7.79 | 0.149 |
> | unbounded | +0.070 | 14.2% right | 5.46 | 10.21 | 0.052 |
>
> **The reversals the taxis assays run on are the same reversals that make the on-food
> ethogram look wrong.** Tighten the bound and the animal stops thrashing on a lawn, but
> chemotaxis inverts, aerotaxis climbs the gradient again and nociception nearly stops —
> a biased random walk with no reversals has nothing to bias. Deleting the turning term
> outright is worse still: chemotaxis +0.070 → −0.015, pirouette ratio 0.38, nociception
> 5.46 → 0.14 reversals a minute while exposed.
>
> 0.3 is the corner: every taxis number identical to the unbounded model, and the latch
> gone — 57% of time reversing down to 17%, net/path 0.052 → 0.149.
>
> ### The basal slowing response was never real
>
> `serotonin_turning` was adopted to reproduce it, and the parameter block already admitted
> the route was wrong. It is worse than that: the "slowing" *was* the thrashing, measured
> as lost net displacement.
>
> Looking for an honest lever found none. Descending cord drive, proprioceptive gain, head
> reflex gain, the motor neurons' adaptation time constant and both Morris-Lecar ratios —
> **the undulation frequency sits at 0.650 Hz in every one of them** and path speed varies
> by at most 13%. That matches `tools/thrust.py` finding the animal already at 100% of its
> mechanical ceiling: speed here is set by the body and the medium.
>
> Since speed is f × λ × (U/V) and f is pinned, the only route left is a shorter wave, and
> that does work — `dopamine_wavelength` at 2.3 slows the animal to 79% of its off-food
> path speed, the only genuine slowing this model has produced. But it costs the chemotaxis
> index half (+0.070 → +0.034), because a slower animal covers less ground in a 200 s
> assay. It is implemented, measured, and **left at zero**.
>
> ### What is still open
>
> On food the animal reverses 7.8 times a minute against 0.7–1.25. Fixing it needs food to
> suppress reversals **by a route that does not also suppress them off food** — a sensory
> pathway, not a global shift of the decision boundary that every behaviour shares. That is
> the next thing, and it is now well posed.
>
> (Food depletion works, incidentally, and was checked while looking: the worm ingests
> 0.02/s, and over 200 s on a 22 mm lawn eats 4.0 units, taking the centre from 1.000 to
> 0.957 with a visible dent under the head that partly refills by diffusion.)

> ## Day fifteen. The animal turns, and every assay woke up.
>
> The omega turn works. It is an **edge, not a level**: on the backward-to-forward
> transition a transient is injected into the head motor pool and decays over 1.5 s, and
> the undulation carries the resulting bias down the body as a turn. Amplitude is set by
> the reversal's own duration, so the *distribution* of turn angles falls out rather than
> being fitted.
>
> ```
>   pA  tau | reorientation deg (median / >120%) |  net   path    TWI   k_rms
>    0   1.5 |      25.3  /   0%                 | 0.273  0.373  +0.88   4.55
>  200   2.0 |      93.3  /  21%                 | 0.135  0.351  +0.88   4.50
>  300   1.5 |     106.1  /  32%   <- shipped    | 0.102  0.351  +0.86   4.60
>  450   2.0 |     101.3  /  33%                 | 0.168  0.299  +0.74   4.98
> ```
>
> Read the two speed columns together: **path** speed barely moves while **net** speed
> halves. That is not the animal slowing, it is its track becoming tortuous, which is what
> turning means. The travelling index and curvature are untouched at 300 pA; by 450 the
> wave starts to suffer and that is the ceiling.
>
> ### Two things had to be right, and both are lessons this file already contains
>
> **A differential, not a push.** Ventral drive alone saturates the cells without bending
> the animal — 400 pA pins RIV and SMDV at activation 0.9999 and reaches −0.56 /mm against
> an undulation of 4.5. Ventral drive *plus dorsal release* reaches −6.4, an order of
> magnitude more. The head is antagonistic pairs that read a difference, exactly as the ASE
> pair did and as the command pools do. That is now three times.
>
> **A transient, not a level.** Held on continuously, 150 pA and above freezes the animal
> bent: travelling index +0.19, path speed 0.03 mm/s, because saturating one side of the
> head pool stops it oscillating. A decaying transient passes back through that region
> rather than sitting in it — which is why 300 pA is usable here and would not be as a
> sustained drive.
>
> ### What it unlocked
>
> | assay | before | after |
> |---|---|---|
> | chemotaxis index | +0.002 | **+0.070** |
> | thermotaxis, warm group | did not turn round | **−2.96 mm towards cooler** |
> | aerotaxis | ascended the gradient | **descends**, 16.5% → 14.2%, reaching 9.8% |
> | ethogram off food | 21.1°, 0% >120° | **55.5°, 24% >120°** |
>
> All four point the right way for the first time. **None is at the animal's magnitude** —
> the chemotaxis index is seven times short of +0.5 — so this opens the problem rather than
> closing it. The next question is what limits the magnitude now that the mechanism exists.
>
> ### Two things found on the way, both still open
>
> **On food, the animal over-reverses badly** — 15.7 commanded reversals a minute against
> the animal's 0.7–1.25, with net/path 0.22. This predates the omega work (the turn
> actually reduced it to 10.2) and is a defect in the food/serotonin path, not the turn.
> It is probably now the single worst number in the model.
>
> **300 pA is the largest injected current here**, an order of magnitude above `cord_drive`.
> It is openly fitted. What is *not* fitted is the mechanism, which is the whole reason it
> is worth more than the RIV gain it replaced.

> ## Day fourteen. RIV is not the omega turn, and the measurement says why.
>
> Day thirteen ended by naming the omega turn as the missing half of the steering and RIV
> as the obvious way in. The anatomy was encouraging — RIV innervates ventral body muscle
> and nothing else, 9 contacts ventral and 0 dorsal, which is exactly the anatomy of a cell
> whose job is to bend the animal one way; it is reached through RIA and SMDV rather than
> from the command pool; and it is already 25% more active during reversals. So it was
> given authority, in all three places a gain can go.
>
> **All three fail, and the third one is the informative one.**
>
> | where the gain acts | what happens |
> |---|---|
> | on the conductance, after the muscle balance | gain 5: reorientation 18 → 72°, 11% above 120° — but net speed 0.301 → 0.027 mm/s. The balance cancels resting tone, so scaling after it amplifies RIV's *tonic* release and bends the animal permanently. |
> | on the conductance, before the balance | gain 8: reorientation 18.1 → 14.6°. Nearly a no-op — the balance equalises each muscle cell's total drive and divides the change straight back out. |
> | on RIV's deviation from its resting release | reorientation climbs 18 → 55° and **never once exceeds 120°**, while net speed falls 81% and the travelling index +0.84 → +0.74. |
>
> The third is the principled one. The balance cancels tone on the assumption that every
> neuron sits at `s_eq`, so amplifying deviations *from* `s_eq` leaves the balanced resting
> state untouched by construction and acts only on the phasic part. It is now a tested
> property (`test_omega_gain_amplifies_only_the_phasic_part`), and it still fails — which
> is what makes this a result about RIV rather than about where a constant was multiplied.
>
> **Why.** Decompose RIV's release variance over 180 s into the part explained by the
> direction state and the part within each state:
>
> ```
> reversal-locked variance    0.5% of total
> undulatory variance        99.5%
> ```
>
> RIV oscillates with the gait, and that oscillation is two hundred times larger than the
> reversal-linked shift a turn would have to be made of. Any gain on RIV therefore
> amplifies the wave two hundred times harder than the signal — which is precisely the
> observed exchange rate. The 25% elevation during reversals is real and is simply not
> where RIV's output lives.
>
> **What this rules in.** The driver has to be something whose variance *is* reversal-locked
> — the command state itself, or a cell reading it — and in the animal the omega turn fires
> at the *reversal-to-forward transition*, not during the reversal. That is a different
> object from a gain on a tonically oscillating motor neuron: a transient locked to an
> edge. It is testable the same way, and it makes two predictions the animal also makes —
> the turn should *follow* the reversal rather than accompany it, and longer reversals
> should end in deeper turns.
>
> `omega_gain` stays at 1.0, exactly the unmodified model. The deviation-gain machinery is
> kept because it is the right way to amplify any phasic drive without disturbing the
> resting balance, and whatever drives the turn will want it. `tools/omega.py` has the
> table and the reasoning.

> ## Day thirteen. One thing is missing, and it explains every remaining sensory failure.
>
> **The animal reverses and does not reorient. Median heading change across a reversal is
> 23 degrees; not one of 53 exceeded 120. A real animal ends about 35% of its reversals in
> an omega turn of 160-170 degrees.**
>
> A biased random walk steers by choosing *when* to change direction. If changing direction
> does not change the direction, there is nothing to bias. The animal reverses along the
> axis it came in on and retraces its own path, so a correctly-signed turning bias moves it
> nowhere -- which is exactly what every taxis assay reports:
>
> * **chemotaxis** -- pirouette ratio 1.24, correctly above 1, index +0.002;
> * **aerotaxis** -- the circuit biases turning correctly, 3.67 reversals a minute at
>   ambient against 2.67 in a lawn, and the animal still ascends the gradient;
> * **thermotaxis** -- the cold group moves +28 mm towards warmer, correctly, and the warm
>   group does not turn round.
>
> Three assays, three correct mechanisms, three null outcomes. **Nociception is the one that
> works, and it is the one that does not need reorientation** -- "get away from here" is
> achievable by reversing alone.
>
> So omega turns are not a refinement to add later. They are the missing half of the
> steering, and until they exist no amount of sensory gain or receptor bookkeeping will
> produce a taxis. That is the next thing, and it is well specified: 35% of reversals should
> terminate in a turn of 160-170 degrees, which needs deep ventral bending -- in the animal
> that is RIV and SMD driving a coil the body cannot make in two dimensions with the current
> muscle model. Whether it can be done at all in 2D is the first question.
>
> ### Two world bugs found on the way there
>
> **Oxygen had no gradient.** It was derived pointwise from the food field, so outside a
> lawn edge it was exactly ambient everywhere -- a cliff, not a slope, with nothing for an
> animal to follow. The attractant has had a 9 mm exponential skirt all along; oxygen now
> has a 5 mm one, shorter because oxygen is also resupplied from the air above the agar
> rather than only laterally. Out from a lawn centre it now reads 6.0, 6.2, 10.9, 14.3,
> 18.0, 20.9% where it used to read 6.0, 20.7, 21.0, 21.0, 21.0, 21.0.
>
> **Oxygen was the only purely tonic sense, and that made its taxis point backwards.** A
> run-and-tumble walker with a position-dependent turning rate settles at a density
> proportional to that rate: it lingers where it turns often. So an animal that turns more
> at high oxygen accumulates at high oxygen. Every other channel here already reports a
> deviation from its own adapting baseline; oxygen now does too, and both terms are kept
> because both are real -- URX is genuinely tonic, and the tonic part sets how much the
> animal turns while the differential part decides where it ends up. Occupied oxygen went
> 19.9% to 18.8%, which is the right direction and not nearly enough on its own, for the
> reason above.


> ## Day twelve. The best the gait has ever been, and gait modulation finally points the right way.
>
> **State: 38 tests pass. Travelling index +0.85, net-to-path 0.75, curvature 4.51 against
> a measured 4.3, and for the first time in this project's history the animal speeds up in
> water instead of slowing down.**
>
> ```
>   quantity                  before      after      animal
>   Travelling-wave index      +0.61      +0.85      +1 pure travelling
>   Net displacement / path     0.53       0.75      well above 0.5
>   Crawling speed            0.105      0.275      0.219 +- 0.029 mm/s
>   Curvature r.m.s.           4.35       4.51      4.3 +- 0.3
>   Dorsoventral antagonism    -0.54      -0.73      strongly negative
>   Undulation frequency       0.45       0.67      see below on 0.30
>   head_delay (fitted)         0.60       0.28      nothing justifies either
> ```
>
> ### Two changes, and the second was not the one expected to matter
>
> **The head reflex is distributed over its own neurons.** It used to hand all twelve head
> motor neurons the same number -- the mean curvature of the front 17% of the body -- so
> cells acting on different pieces of body all saw the same thing. Weighted by their own
> neuromuscular maps they act between s = 0.135 and 0.229, and letting each read the
> curvature around the piece it moves halves the invented delay, 0.60 s to 0.28.
>
> It did **not** do what it was built to do. Distributing alone leaves the frequency at
> 1.28 Hz against the lumped reflex's 1.18: a spread of delays low-passes the loop rather
> than adding phase, and this crossover is phase-limited. The delay is smaller but it is
> still there and still unearned.
>
> **The command layer was recalibrated, and that is where everything came from.** The new
> head circuit more than doubled the spread of the command difference, 0.04 to 0.0885, so
> the gate threshold fitted to the old gait sat 0.29 sigma from the mean instead of 1.33
> and the animal flickered at **40 reversals a minute**. Nothing about the command layer
> was wrong; it was calibrated against a gait that no longer existed. Re-fitting it to
> bias 0.04 / hysteresis 0.09 gives 3.33 reversals a minute against the animal's 3.2-3.5,
> and the travelling index, the net-to-path ratio and the speed all came with it -- because
> an animal that is not constantly changing its mind travels, and thrust is the travelling
> index.
>
> **Gait modulation is the right way round.** 0.67 Hz on agar to 0.85 in buffer, where the
> animal goes 0.30 to 1.76. The magnitude is far short but the *sign* has been wrong since
> day two. What fixed it was removing the flicker, not any change to the mechanics.
>
> ### The senses, re-run
>
> * **Nociception works.** 3.81 reversals a minute while exposed to the repellent against
>   1.72 while clear, and the animal leaves: concentration at the end 0.027 against 0.264
>   at the start. That is avoidance, and it is the first sensory behaviour here that works
>   without qualification.
> * **Chemotaxis is biased the right way** and stays there -- pirouette ratio 1.24, above
>   the 1 that separates chemotaxis from its absence. The index is +0.002 because the
>   animal now covers a lot of ground (24 mm in 200 s) without a net bias towards anything.
> * **Thermotaxis is half right**: animals started cold move +28 mm towards warmer, which
>   is correct; animals started warm move +9 mm, which is not.
> * **Aerotaxis still does not work**: 20.9% oxygen occupied against an ambient 21%.
>
> ### And the ON/OFF pair was cancelling itself
>
> `Senses` gives ASEL +dC/dt and ASER -dC/dt, a genuine opponent pair. But both project
> onto AIY with the same sign -- 19 contacts against 16 -- so AIY receives (+dC/dt) +
> (-dC/dt) and the opponency dies at the first synapse. Measured as the shift in the
> command difference under a held gradient:
>
> ```
>   chloride on        improving   worsening   opponency
>   neither             +0.15409    +0.15435    -0.00026
>   both                +0.15412    +0.15412    -0.00000    exactly nothing
>   ASEL only (ON)      +0.15457    +0.15379    +0.00078    correct sign
>   ASER only (OFF)     +0.15376    +0.15465    -0.00089    inverted
> ```
>
> Giving both cells the same receptor cancels it to five decimal places. Giving the ON cell
> a chloride channel and the OFF cell not makes them push AIY the same way and the sign
> comes right. **Adopted, and still about a hundredfold too small** -- 0.009 sigma where
> biasing the walk wants of order 0.1 -- which is not attenuation along the way, since the
> chain is strong at every stage (ASE->AIY is 206% of AIY's own conductance, AIY->AIZ 91%,
> AIZ->AVE 25%). Where the signal goes instead is the open question.
>
> ### Also
>
> The dish is a 9 cm plate now rather than 5 cm, because at 0.275 mm/s a 200 s assay covers
> 55 mm and every trial was ending up against the wall. It surfaced as a habituation test
> failing -- sustained wall contact re-depletes the mechanoreceptor, which is correct
> behaviour and a confound there -- and would have quietly corrupted every taxis assay.
>
> A bug of mine, worth the warning: `head_delay` was applied only on the lumped branch of
> the reflex, so it was a silent no-op in distributed mode and a whole sweep was noise. It
> now buffers the curvature itself, ahead of any spatial pooling, which is where a
> transduction delay physically belongs and works for both forms.


> ## Day eleven. The speed target contradicts the frequency target, and thrust is the travelling index.
>
> Two results from `tools/thrust.py`, which drives the body with a clean prescribed wave
> and no biology at all, so whatever it says is what the mechanics can do if something
> drives them properly.
>
> ### The targets do not admit a solution
>
> A travelling wave of frequency f and wavelength L runs along the body at V = f*L, and an
> inextensible body in a viscous medium cannot advance faster than its own wave: U/V < 1
> strictly, approaching 1 only as the drag anisotropy goes to infinity. The table this
> project scores itself against quotes 0.219 mm/s from Ramot et al. beside 0.30 Hz and
> 0.65 L from Fang-Yen et al., and
>
>     U/V  =  0.219 / (0.30 * 0.65)  =  1.12
>
> which is above the bound. Different experiments, different conditions, and no animal
> satisfies all three at once.
>
> Measured, at the agar anisotropy of 40 that Berri et al. report and at the animal's own
> curvature of 4.3, the mechanics cap U/V at about **0.51**. So:
>
> * 0.30 Hz with a 0.65 L wavelength implies **at most 0.099 mm/s**;
> * 0.219 mm/s implies **0.66 Hz**;
> * the model, at 0.45 Hz and 0.105 mm/s, is doing U/V = 0.32 -- comfortably inside the
>   bound, and much closer to a self-consistent animal than the table suggests.
>
> Eight days of gait work have been scored against a target set that contradicts itself,
> which is worth knowing before any more of it happens. It also explains some of the
> razor's-edge behaviour: configurations were being pushed towards a corner that does not
> exist.
>
> ### Thrust is the travelling index, quantitatively
>
> At the model's own kinematics -- 0.45 Hz, 0.73 L -- a clean prescribed wave reproducing
> the animal's curvature reaches **0.169 mm/s**. The model reaches 0.105, which is 62%.
> Its travelling index is +0.61. And
>
>     0.169  x  0.61  =  0.103        against a measured 0.105
>
> to 2%. A standing wave produces exactly zero net thrust however large its amplitude, so
> the fraction of the oscillation that travels is the fraction of the ceiling collected:
>
>     net speed  ~  (mechanical ceiling at these kinematics)  x  (travelling index)
>
> **So thrust and the travelling index are one problem.** There is no separate thrust
> deficit to find, and the way to more speed is a wave that travels better rather than a
> body that pushes harder. The index has been this project's central diagnostic since day
> two and it is now also its speed equation.
>
> **[Withdrawn on day twelve.** That was a coincidence at one operating point. Re-measured
> at 0.67 Hz, 0.83 L and curvature 4.51, the ceiling is 0.274 mm/s and the model reaches
> 0.275 -- 100% of it -- at a travelling index of 0.85, not 85%. The *bound* on U/V stands
> and so does the target inconsistency; the proportionality does not. What replaces it:
> the model now extracts essentially all the thrust a sinusoidal wave of its own kinematics
> allows, so speed is a kinematics question rather than a waveform one.**]
>
> ### What that makes the next move
>
> Raise the travelling index from +0.61. It was +0.75 before `head_delay` went in, so the
> delay bought the frequency partly by degrading the wave -- which is a third count against
> it, after being unearned and being the wrong kind of object for gait modulation. The
> head-circuit work that replaces it should be scored on the index, not only on the
> frequency.


> ## Day ten. The convergence failure was a coupling bug. Three days of conclusions withdrawn.
>
> **`BodyParams.dt` was documented as "shared with the neural step" and was shared with
> nothing.** `Body` kept its own timestep, `Simulation` used `NeuralParams.dt`, and nothing
> synchronised them -- so changing the neural step left the body advancing 0.5 ms per call
> while the rest of the animal believed it had advanced by the neural step. At dt = 0.125 ms
> the body ran **four times fast relative to its own nervous system**.
>
> Every timestep-convergence measurement in this project was measuring that. The day-eight
> conclusion -- that the coherent gait exists at dt = 0.5 ms and nowhere else, and that
> integrated accurately this reflex chain does not produce C. elegans locomotion -- **is
> withdrawn**. So are the twenty-five "drift" numbers and everything inferred from them.
>
> With the body synchronised:
>
> ```
>    dt ms |  freq Hz (sd)   wavelen L    TWI     k_rms   before the fix
>    0.125 |  0.250 (0.141)     1.00    +0.566    4.78    0.13-0.20 Hz, 2-6 L
>    0.250 |  0.444 (0.008)     0.73    +0.679    4.27
>    0.500 |  0.344 (0.138)     2.05    +0.640    4.48
>    1.000 |  0.444 (0.008)     0.71    +0.635    4.35
>    2.000 |  0.450 (0.000)     0.74    +0.585    4.50
> ```
>
> Frequency 0.44-0.45 Hz across a sixteen-fold range, curvature 4.3-4.8, travelling index
> 0.59-0.68. Two rows carry a seed spread of 0.14 Hz where the others carry 0.008; that is
> the gait bistability documented since day two, it is a property of the model rather than
> of the integrator, and three seeds is not enough to characterise it.
>
> ### Everything re-measured afterwards, and it is a mixed picture
>
> `tools/scorecard.py` is new and exists because this project's headline table had drifted
> into quoting a crawling speed from day two beside a frequency from day nine -- numbers
> never true of the same animal. It measures every row at once, over five seeds:
>
> ```
>   quantity                     model (mean +- sd)     animal
>   Undulation frequency, agar    0.45 +- 0.01 Hz       0.30 +- 0.02
>   Wavelength, agar              0.73 +- 0.01 L        0.65 +- 0.03
>   Curvature, r.m.s.             4.35 +- 0.10 /mm      4.3 +- 0.3
>   Curvature, peak               14.4 +- 1.5 /mm       9.8 +- 1.1
>   Crawling speed (net)          0.105 +- 0.025 mm/s   0.219 +- 0.029
>   Net displacement / path       0.53 +- 0.13          well above 0.5
>   Travelling-wave index         +0.61 +- 0.04         +1 pure travelling
> ```
>
> The seed spread is tight -- frequency 0.43 to 0.45 across five seeds -- so the gait
> bistability worried about above was itself an artefact of the desynchronised runs.
>
> **Frequency, wavelength and curvature rms have landed. Speed has halved.** 0.105 against
> the animal's 0.219, with net-to-path at 0.53, barely over the bar. Slowing the undulation
> to the animal's band bought the kinematics and cost the transport, and a real worm does
> not have to make that trade -- it does 0.30 Hz *and* 0.219 mm/s. **How much thrust the
> model gets per undulation is now the sharpest open question in the locomotion.**
>
> It shows up everywhere above the gait, because every taxis assay needs the animal to
> cover ground:
>
> * **Chemotaxis is biased the right way for the first time.** The pirouette ratio crossed
>   1, at 1.22 against a real animal's ~2, so the animal now suppresses turning while
>   conditions improve. The index is still -0.016, because it ends 1.7 mm from where it
>   started.
> * **Thermotaxis regressed from working to not.** It moved both groups towards the
>   cultivation isotherm on day seven; it now moves neither, -1.4 and -0.6 mm.
> * **Aerotaxis never reaches the lawn**: 21.0% oxygen occupied, which is ambient.
> * Chemosensory drive fell 0.58 -> 0.35 pA, because a slower animal crosses a gradient
>   more slowly.
>
> None of that is a sensory failure. It is the speed, and it is one problem.
>
> **And gait modulation is dead, which indicts head_delay directly.** Across three media:
> 0.45 Hz on agar, 0.18 in viscous, 0.19 in buffer, against an animal that goes 0.30 Hz
> crawling to 1.76 swimming. In buffer it does not undulate coherently at all -- a 2 L
> wavelength is less than half a wave on the body -- and it travels 6 um/s.
>
> A fixed transport delay contributes fixed phase at every frequency, so it pins the loop's
> crossover regardless of what the medium does to the mechanical load. The animal *cannot*
> speed up in water while that delay dominates. So the 0.60 s is not merely unearned, it is
> the wrong kind of object: whatever replaces it must have a frequency that follows the
> load, and a delay never will. That is a sharp constraint on the head-circuit work in
> task 9, and it is worth more than the frequency the delay bought.
>
> ### How it was found, because the method is the transferable part
>
> Not by sweeping. Eight days of parameter sweeps -- reach, head_tau, head gain, body gain,
> ca_ratio, head_delay, gap_iters, twenty-five configurations -- produced eliminations and
> never the cause, because every one of them inferred the loop's behaviour from the gait.
>
> `tools/loop_phase.py` opens the head loop, injects a sinusoid in place of the reflex, and
> reads the gain and phase of each stage with a lock-in. One pass localised it: neurons
> agree to 0.3 degrees between step sizes, synapses to 0.1, muscle transfer to 1 -- and
> tension-to-curvature differs by 10 to 31, with the plant gain differing by up to 86%.
>
> Then four eliminations, each killing the obvious reading of that:
>
> * substepping the mechanics 16x at dt = 0.5 reproduced dt = 0.5 exactly rather than
>   dt = 0.125, so the body's own integration was already converged;
> * `ca_ratio` 0, removing the Hopf bifurcation, left the gap unchanged;
> * `proprio_gain` 0, opening every feedback path, left it unchanged -- so it was
>   feedforward;
> * with the noise off, the joint-moment profile along the *whole* body was identical to
>   0.1%, mean and oscillating alike, while head curvature differed by 18% in amplitude and
>   24 degrees in phase.
>
> Same moment field, same body, different answer. And driving `Body` alone with an analytic
> moment showed it converged to 0.05% in amplitude and 0.01 degrees in phase over a 32-fold
> range of dt. Those two cannot both be true of a correctly coupled model, and that is what
> pointed at the coupling rather than at either end of it.
>
> ### What this does and does not change
>
> **Does not change the shipped model.** The fix is a no-op at dt = 0.5 ms, where the body's
> own dt already was 0.5. 38 tests pass, unchanged.
>
> **Does change what head_delay means.** 0.60 s was adopted on the argument that the loop
> needs phase the modelled components do not supply -- which stands, since it was fitted at
> the step where the coupling was correct. But the *surrounding* argument, that the coarse
> step was supplying free damping and the delay was replacing it, was based on the broken
> measurements and should be re-derived. The number is still fitted and still the largest in
> the model; it is now worth asking again what it is standing in for, with a convergence
> study that means something.
>
> **Next, in order.** Re-run the gait numbers across seeds now that a step size can be
> trusted -- the two high-variance rows above are the interesting ones. Then re-examine
> head_delay against a working convergence study. Then the assays, which have not run since
> the command layer changed.
>
> ### Do not repeat this
>
> A parameter whose comment claims it is shared with something else, and is not. The
> comment is what stopped anyone checking: it read as documentation of an invariant when it
> was a description of an intention. Eight days of sweeps went past it.


> ## Day nine. The frequency lands, and it costs one honest parameter.
>
> **Superseded in part by day ten: every step-size result below was measured while the body ran at its own timestep, and the convergence conclusions are withdrawn. The parameter results stand.**
>
> **State: 38 tests pass. 0.44 Hz against the animal's 0.30-0.50, curvature rms 4.48
> against 4.3, net speed 0.171 mm/s against 0.15-0.22, wave head to tail. Three of the
> four gait targets met, the first time any configuration in this project has managed
> more than one.**
>
> ### What did it
>
> An explicit transport delay in the head reflex, `SensoryParams.head_delay`, at 0.60 s.
> Measured at reach 0.16, three seeds:
>
> ```
>   delay s |  freq Hz   wavelength L    TWI    k_rms   net mm/s
>     0.00  |   1.178       0.64       +0.746   2.40     0.218
>     0.15  |   0.811       0.73       +0.707   3.29     0.180
>     0.40  |   0.544       0.68       +0.700   4.12     0.166
>     0.60  |   0.433       0.75       +0.655   4.44     0.186   <- adopted
>     0.80  |   0.367       0.76       +0.653   4.63     0.149
> ```
>
> The frequency was the largest single error in this project -- 1.18 Hz against a crawling
> gait of 0.30-0.50, nearly four times too fast -- and the curvature was 43% low. Both are
> now within a few percent, and nothing else tried in eight days moved either without
> destroying the wave: head_tau, head gain, body gain, reach, the segmental oscillators,
> and head_tau paired with a compensating gain all failed, and are recorded as failing.
>
> `proprio_reach` was re-fitted to 0.16 alongside it, because the delay raises the
> wavelength and reach is what trades against it. The trade is clean -- 0.13 lands the
> wavelength exactly and gives up 40% of the speed, 0.22 lands the speed and misses the
> wavelength by a quarter -- and 0.16 is the setting that puts all four gait numbers inside
> 15% of the animal at once.
>
> ### Why the number is not honest yet, and what would make it so
>
> **0.60 s is not a measured delay.** Mechanotransduction takes milliseconds. No element of
> the real head circuit is this slow, and the parameter is now the largest fitted quantity
> in the model.
>
> What it actually states is arithmetic about the loop. An oscillation at 0.43 Hz needs
> about 1.15 s of lag to reach its half period; the modelled components -- head_tau, the
> synapses, the muscle cascade, the body -- supply about 0.42 s; the remaining 0.7 s has to
> exist somewhere, or the animal would undulate at 1.18 Hz, which it does not. So the
> parameter is the size of what the model is missing, named rather than hidden.
>
> The obvious candidate for what it stands in for is the head circuit itself. RMD, SMD and
> SMB are lumped here into one reflex with one gain and one filter; the real thing is
> several classes with their own dynamics, and RMD is frankly bistable (Mellem et al.
> 2008). A distributed multi-stage circuit accumulates phase that a single first-order lag
> cannot. **Replacing this number with that circuit is how to earn it back, and it is the
> next thing worth doing.**
>
> ### And a suspect ruled out: the gap-junction solve
>
> The step solves the gap coupling by fixed-point iteration, and the contraction factor per
> pass is `(1 - decay) * ||G_gap / g_tot||` with `decay = exp(-g_tot dt / C)`. That factor
> *grows with dt*, so a coarser step converges the iteration more slowly and ends up with a
> different effective gap conductance -- which, since AVB's gap junctions set the
> bifurcation point of the whole motor cord, looked like an excellent candidate for the
> step dependence.
>
> The residual is exactly as predicted. Largest voltage error against the fully converged
> fixed point of the same step, mid-gait:
>
> ```
>   passes |  dt = 0.5 ms   dt = 0.125 ms
>      3   |   1.37e-01       6.79e-03
>      6   |   8.32e-03       3.46e-05
>     10   |   2.37e-04       4.15e-08
> ```
>
> Twenty times less converged at the shipped step. And it makes **no difference at all**:
> raising the count from 3 to 24 leaves the frequency identical to three decimals at both
> step sizes and the drift at exactly 54%.
>
> So the residual is real, measurable, twenty times worse where it matters, and
> behaviourally irrelevant -- 0.137 mV in the worst neuron does not move a gait. `gap_iters`
> is now a parameter, still 3, and that is a measured choice rather than an assumed one.
>
> The step dependence has one fewer suspect and no new hypothesis. What is left, and
> untested: the synaptic drive is held constant across each step and every synapse carries
> an explicit one-step delay, which is the last first-order term in the neural integration.
> Worth measuring the loop's phase directly at both step sizes rather than guessing again.
>
> ### It did not fix convergence, which was the other half of the hope
>
> The delay is the one lag in the loop whose size cannot be a numerical artefact, so it was
> the best candidate for making the crossover step-independent. It moved the drift from 44%
> to 54% -- that is, not at all, and slightly the wrong way. Across twenty-five
> configurations now swept, nothing gets the drift below 38%, and at dt = 0.125 ms every
> one of them collapses to 0.13-0.20 Hz with a 2-6 L wavelength.
>
> **So every gait number in this file should be read as "at dt = 0.5 ms".** That caveat is
> now in the README's limitations section rather than buried here.
>
> ### One thing got worse, and it is worth having measured
>
> Ablating AVB and PVC used to end forward locomotion; it now halves it, 0.114 to 0.060
> mm/s. The head reflex propels the animal on its own and is untouched by the ablation, and
> the delay made that share larger. The test threshold moved from 0.25 to 0.65 of intact
> and says so in its own comment. It is a fair measure of how much of the gait the command
> layer actually commands, and it should get stricter as that improves rather than looser.


> ## Day eight. The wavelength is right. (The step-size claim here was a bug.)
>
> **Superseded in part by day ten: every step-size result below was measured while the body ran at its own timestep, and the convergence conclusions are withdrawn. The parameter results stand.**
>
> **State: 38 tests pass. Wavelength 0.64 L against the animal's 0.65, net speed 0.218
> against 0.219. And a structural result that matters more than either.**
>
> ### The wavelength, which turned out to be one knob
>
> Sweeping `proprio_reach` over a 3.75-fold range moves the wavelength from 0.49 to 0.64 L
> and leaves the frequency flat at 1.167-1.178 Hz:
>
> ```
>   reach |  freq Hz   wavelength L   TWI     k_rms   net mm/s
>    0.08 |   1.167       0.49      +0.489    2.27     0.108
>    0.20 |   1.178       0.55      +0.796    2.45     0.210   <- was shipped
>    0.30 |   1.178       0.64      +0.746    2.40     0.218   <- adopted
> ```
>
> So wavelength and frequency are **not** two views of one phase velocity here. Reach sets
> the wavelength and does nothing at all to the frequency, which belongs entirely to the
> head loop. Every note in this file that treats them as a single problem -- and there are
> several, going back to day two -- is wrong on this evidence.
>
> 0.30 costs nothing: net speed goes 0.210 to 0.218 against a measured 0.219, and the
> travelling index slips from +0.80 to +0.75. `test_wavelength_on_agar` now asserts
> 0.55-0.80 instead of the old 0.45-1.8 shrug.
>
> ### The frequency has no working setting, and day two's last thread is closed
>
> Four sweeps, all at reach 0.30, all failures, and one of them has been open since day two:
>
> * **`head_tau` 0.22 -> 2.00** halves the frequency to 0.544 Hz and takes curvature from
>   2.40 to 1.12 and speed from 0.218 to 0.038 with it. The filter buys phase by throwing
>   away gain.
> * **Filter plus compensating gain**, which nobody had tried because every earlier sweep
>   moved one at a time, does recover the amplitude -- head_tau 1.0 with gain 400 gives
>   0.656 Hz, curvature 3.11, speed 0.228 -- and blows the wavelength out to 3.09 L, a
>   third of a wave on the whole body.
> * **Doubling the body reflex gain** is day two's queued and never-run experiment
>   ("backing the head off is the untested half"). It is now run and it fails: the wave is
>   destroyed at every head gain, TWI at or below zero, curvature 6.4-8.1 against a
>   measured 4.3, and a reported 0.100 Hz which is the bottom FFT bin and means no coherent
>   oscillation. A stronger body reflex does not carry the wave; it makes a large
>   incoherent bend.
> * **Backing the head off alone** reaches 0.544 Hz at a net speed of 0.006 mm/s.
>
> ### The result that matters
>
> **The coherent 1.2 Hz gait exists at dt = 0.5 ms and nowhere else in the parameter space
> swept.** Frequency drift between dt = 0.5 and 0.125 ms is 44% at the shipped setting and
> 67-86% everywhere else, across nineteen configurations spanning reach, head_tau, head
> gain, body gain and ca_ratio. At the fine step *every* one of them falls to 0.13-0.20 Hz
> with a wavelength of 2 to 6 L and a travelling index of 0.17 to 0.41.
>
> Integrated accurately, this head-driven reflex chain does not produce C. elegans
> locomotion. That is a larger statement than "the frequency is wrong" and it should be
> read as the main finding of the day.
>
> The mechanism is visible in the head pool's own numbers. RMD, SMD and SMB have membrane
> time constants of 0.93 to 2.34 ms, so the shipped step is 0.21 to 0.54 of a time constant
> and the loop's fast dynamics are only marginally resolved. At 0.125 ms they resolve, the
> fast mode stops being damped for free, and what takes over is not a gait.
>
> ### So what would actually work
>
> Not another parameter; nineteen configurations is enough to stop. Two candidates, and
> both are design changes:
>
> 1. **Put an explicit delay in the loop** to replace the numerical one it has been leaning
>    on. The head reflex currently reads curvature and acts on it within a step; a real
>    stretch receptor has transduction and transmission delays of tens of milliseconds. A
>    physical delay sets the crossover frequency honestly, is dt-independent by
>    construction, and is the smallest change that could make the frequency a property of
>    the animal rather than of the integrator.
> 2. **Generate the rhythm somewhere that is not a phase crossover.** The head loop
>    oscillates because a negative feedback loop with enough lag must; its frequency is
>    therefore whatever the loop's phase happens to cross 180 degrees at, which is not a
>    quantity anyone measured in a worm. A dedicated oscillator with its own time constant
>    -- the RMD bistability Mellem et al. describe is the obvious candidate -- would have a
>    frequency that means something.
>
> Do (1) first. It is cheap, it is testable against the existing convergence tool, and if
> it works it fixes the frequency and the convergence together.


> ## Day seven. The command layer moves, the animal reverses, and it remembers.
>
> **State: 37 tests pass. Spontaneous reversals at 4.67/min in episodes of 0.69 s, where
> there were none. Locomotion better than before: 0.208 mm/s, net/path 0.813, TWI +0.769.
> The model has a memory for the first time.**
>
> ### Read this first: the command layer moves now
>
> The day-six diagnosis was that every sensory behaviour failed at one junction -- the
> direction gate, sitting 3.81 standard deviations from its own boundary with nothing able
> to reach it. That junction is now fixed, and the fix was structural rather than a gain.
>
> **The gate did two jobs with one number.** `fwd_frac` chose the direction *and* scaled
> the descending drive, so at 0.5 both cords were driven at half strength and fought over
> the same muscles. The decision could not move without moving the gait, which is why every
> attempt to give the command layer dynamic range cost locomotion. Latching it -- a Schmitt
> trigger that picks a cord and commits, giving the selected cord the whole drive and
> letting the other go passive -- separates them.
>
> With that done, the command adaptation that was worthless on day six works, because its
> dynamics no longer come out of the gait:
>
> ```
>                          rev/min   episode s   %rev |  speed   net/path    TWI
>   graded gate (day six)     1.67      0.06      0.2 |  0.1853   0.783    +0.767
>   latched                   2.67      0.44      1.8 |  0.2079   0.823    +0.781
>   latched + adaptation      4.67      0.69      5.3 |  0.2077   0.813    +0.769
>   real animal, off food   3.2-3.5    1 to 4          |  0.219      --        --
> ```
>
> Reversals went from **0.06 s to 0.69 s** -- eleven times longer, and the thing that was
> catastrophically wrong, since a body cannot reverse in one fifteenth of an undulation
> cycle. The rate is 4.67 per minute against 3.2-3.5. And locomotion came out *better* than
> the graded model it replaces on every measure, because the cords stopped sharing drive.
>
> ### The assays, rerun on an animal that can reverse
>
> First full run since day four, and the first ever on an animal with a working reversal.
>
> **Thermotaxis works.** This is the first sensory behaviour in the project to do so.
> Animals started at 18.1 C moved +12.6 mm towards warmer; animals started at 21.9 C moved
> -16.1 mm towards cooler. Both groups converge on the 20 C cultivation isotherm at
> x = -6.2 mm, which is what the assay asks for.
>
> **Chemotaxis is positive for the first time, and still bad**: CI +0.053 against -0.014 on
> day four, with 4 of 16 animals approaching. Reversals are real now -- 29 +- 27 per animal
> over 200 s, 8.3% of the time spent reversing, against 1 per six animal-minutes before.
>
> And the mechanism measurement says exactly what is wrong, which is worth more than the
> index:
>
> ```
>   reversals/min while improving (dC/dt > 0):  13.36
>   reversals/min while worsening (dC/dt < 0):   9.03
>   ratio 0.68        real animal ~2; anything above 1 is chemotaxis
> ```
>
> **The biased random walk is now running, and it is biased the wrong way.** The animal
> turns *more* when things are getting better. Pierce-Shimomura's mechanism is present and
> inverted, which is a sign error somewhere between ASE and the command pools rather than a
> missing behaviour -- and it is a far more tractable problem than the one this replaces.
> ASEL depolarises when the attractant rises and should be suppressing reversals; either
> its route to AVA has the wrong net sign, or the ASE -> AIY/AIB stage does.
>
> That is the single next thing to chase, and `tools/assays.py chemotaxis` scores it
> directly.
>
> **Aerotaxis still does not work**: 20.4% oxygen occupied against an ambient 21% and a
> preference of 5-12%. **Nociception did not run** -- see the timeout note below.
>
> ### The chemotaxis sign: half fixed, and the other half named
>
> The bias pointed the wrong way -- the animal turned *more* when conditions improved,
> ratio 0.68 where the animal is about 2. The route is short enough to trace: ASEL and
> ASER both project onto AIY (19 and 16 contacts), AIY projects onto AIZ (21), and AIZ
> makes 10 contacts onto the backward command pool. AIY reaches the command layer only
> through AIZ. Measured directly, 3 pA into AIY takes the reversal rate from 4.7 to 6.0 per
> minute and the same current into AIZ does the same -- so exciting AIY makes the animal
> turn, and a rising attractant excites AIY.
>
> In the animal AIY does the opposite, and the reason this model has it backwards is the
> same simplification that made the command pools mutually excitatory: glutamate collapsed
> to one excitatory reversal. Chalasani et al. (2007) showed the same glutamate release
> inhibits AIY through the chloride channel GLC-3 while exciting AIB through GLR-1 -- one
> transmitter, two receptors, opposite signs, and none of it survives deciding a synapse's
> sign from the transmitter alone. `glucl_strength` applies that correction through the
> per-synapse reversal matrix, and AIB is deliberately left excitatory.
>
> **The sign flips.** A steady 3 pA into ASEL takes the reversal rate from +0.33 to -0.33
> against baseline: from promoting reversals while things improve to suppressing them.
> Locomotion is untouched, and there is a test.
>
> **The bias does not yet win.** The pirouette ratio goes 0.68 -> 0.88, the right direction
> and still the wrong side of 1, and the chemotaxis index stays near zero. Raising
> `chemo_gain` six-fold makes it *worse*, back to 0.66, which says a second route from ASE
> to the backward pool outruns the AIY arm when both are driven hard -- most likely ASE ->
> AIB -> RIM, which reaches the backward pool through 16 gap junctions and is not
> correctable the same way, because AIB holds GLR-1 and is supposed to be excited.
>
> **What is actually missing is the opponency.** ASEL should mean "better" and ASER "worse",
> and in this reconstruction they are wired almost identically -- ASEL 19 contacts onto AIY
> and 9 onto AIB, ASER 16 and 12. Their separation in the animal is functional rather than
> anatomical, so contact counts cannot produce it and no gain on a symmetric pair will
> either. That is the next thing, and it is a modelling decision rather than a bug: either
> give ASEL and ASER different downstream receptors the way the AIY correction does, or
> accept that salt chemotaxis needs more than the wiring diagram carries.
>
> ### What still does not work, and it is now a narrower thing
>
> **A tap still does not reverse the animal.** Forward progress over three seconds is
> +0.739 mm after a tap against +0.786 with none, and the animal spends 0.05 s in the
> backward state. The margin is now 1.33 sigma and a tap moves the command difference by
> about 0.53 sigma -- so it gets 40% of the way, against 0.6% before. Closer, and still
> short.
>
> The remaining gap is the touch pathway itself rather than the gate. Anterior touch makes
> 12 chemical contacts and 2 gap contacts onto the whole backward pool, against 27 chemical
> contacts onto the *forward* one, so ALM and AVM in this reconstruction drive AVB harder
> than they drive AVA. That is a wiring fact, and the two honest things to do with it are
> to check it against a newer reconstruction, and to ask whether the tap-withdrawal circuit
> needs AVD treated as its own stage rather than lumped into the backward pool.
>
> So habituation, which is implemented and works at the receptor, still has no
> tap-withdrawal response to decrement. That is now one specific pathway rather than the
> whole animal.
>
> ### Four bugs, in the order they were found
>
> **1. The gait is not converged at the timestep it ships at**, and two headline numbers
> change meaning. Halving the step from 0.25 to 0.125 ms still moves the frequency by 15%
> and net speed by 17%, against a seed spread of 0.03 Hz, monotonically across a sixteen-
> fold range. The frequency discrepancy is therefore *worse* than reported -- refine and it
> runs away from the animal, reaching 1.62 Hz at 0.125 ms -- and the crawling speed
> agreeing with the measured 0.219 mm/s is partly an artefact of this step size, since at
> 0.125 ms it does 0.3245. `tools/timestep_convergence.py`, four minutes.
>
> **2. Mechanosensation scaled with the timestep.** `touch_state` accumulated one whole
> force per step and leaked with `touch_tau`, so its steady state was proportional to
> 1/dt -- touch was four times more sensitive at 0.125 ms than at 0.5 ms. Now an
> exponential moving average, with the factor that used to hide in the integrator written
> into `touch_gain`.
>
> **3. The volatile odour pathway was deaf, and had been all along.** Its adaptation used
> `(1 - chem_decay * 0.5)` as a per-step rate, and `chem_decay` is very nearly 1, so the
> effective time constant was about 2 dt -- one millisecond, not the seven seconds
> intended. AWA and AWC adapted out any odour within two timesteps. AWC is the OFF cell
> that fires when an attractant is removed, one of the better characterised reversal
> triggers in this animal.
>
> **4. `touch_gain` was two hundred times too large.** A standard tap implied an **8745 mV**
> depolarisation of ALM, clamped by `v_clamp` to +45. The mechanosensory channel was not a
> sensor but a binary switch, and nothing graded downstream of it could show -- which is
> why the first attempt at habituation depleted the receptor to 52% and changed the
> response by 2%. Recalibrated to 75 pA/uN: the receptor stays off the clamp, and the
> current lands in the tens of pA that O'Hagan, Chalfie & Goodman (2005) measured.
>
> **And ablation was backwards.** Zeroing a cell's conductances leaves it still receiving
> whatever current the sensory layer injects, with only its leak to shunt it -- so ablating
> AVB, which carries a 22 pA tonic drive, took it to +34.8 mV and its activation from 0.84
> to **0.9994**. Silencing the forward command made it maximally active. `NervousSystem`
> now carries an explicit alive mask; it reads 0.0000, and restoring gives 0.833 back.
>
> ### Three refutations
>
> **`head_tau` does not suppress the fast mode. The coarse timestep was doing it.** At
> dt = 0.5 ms the power above 1.5 Hz is 1-2% at *every* `head_tau` from 0.22 to 1.20. At
> 0.125 ms with the shipped 0.22 it is **53%**. Refining further finds no `head_tau` at
> which the answer stops depending on the step: the frequency clusters near 0.15, 0.70 and
> 1.0-1.4 Hz and flips between clusters on changes too small to move any physical quantity.
> The head loop has several coexisting limit cycles and the integrator is selecting among
> them, so "the undulation frequency" is not currently a well-defined property of this
> model. That is a stronger statement than the frequency being wrong.
>
> **The body cannot be made the oscillator by turning the segmental gain up.** Raising
> `ca_ratio` does raise curvature -- 2.7 to about 6.3, against a measured 4.3, having been
> too low -- and destroys the wave doing it: TWI falls from +0.71 to zero and net speed to
> 0.02 mm/s. The units free-run and lock to each other instead of organising into a
> travelling wave, and weakening the head does not rescue it (the `ca_ratio` 0.40 rows are
> equally dead at head gains of 150, 60, 25 and 0), which was the obvious objection to the
> earlier version of this result. Proprioceptive coupling as built can carry phase to
> segments that have no rhythm of their own; it cannot impose a phase gradient on segments
> that do. Making it impose a phase *lag* -- an explicit propagation delay, or asymmetric
> coupling -- is a design change and is the next thing to try.
>
> **Presynaptic depression cannot habituate this connectome's tap response**, because the
> response is not chemical. Cutting ALM and AVM's entire chemical output leaves the AVA
> response unchanged at +0.18; cutting their gap junctions halves it. The machinery is
> kept, at zero, because it is the standard model and the refutation is specific to this
> pathway rather than to the idea.
>
> ### What was added
>
> * **Habituation** (`SensoryParams.touch_habituation_use`). A depleting resource on the
>   mechanoreceptor: taps consume it, rest refills it, and a shorter interval habituates
>   deeper. Three properties from one equation. The interval dependence is the one that
>   could have failed and it holds -- 0.25 resource at a 10 s interval against 0.45 at
>   30 s, same rate, same number of taps -- which is what separates habituation from
>   fatigue. Integrated exactly, so how much the animal learns does not depend on how
>   finely it is stepped, and there is a test for that.
> * **Reversible ablation**, on `Simulation`, with the alive mask above, plus a viewer UI:
>   an Ablate mode, a Restore button, and dead cells drawn hollow and crossed.
> * `tools/timestep_convergence.py`, `tools/head_mode.py`, `tools/body_oscillator.py`,
>   `tools/habituation.py`.
> * A **HiDPI fix in the viewer**: neuron hover and click have never worked on a Retina
>   display. The layout is built in backing-store pixels and the hit test compared them
>   against CSS pixels, so at devicePixelRatio 2 it was out by a factor of two and no cell
>   could be selected at all.
> * The assay runner uses one flat job queue instead of one `pooled()` call per assay, and
>   eight workers rather than ten. Both measured; see `tools/assays.py`. Flattening also
>   put every job under a single timeout where each assay used to have its own, and the
>   first full run afterwards died with eight trials unfinished and nociception missing
>   entirely; the budget now scales with the queue.
>
> ### Do not repeat these
>
> * **Do not edit anything under `worm/` while a sweep is in flight.** `pooled()` launches
>   a fresh process per trial that imports the package from disk, so an edit part-way
>   through silently mixes two code versions in one result table.
> * **Do not score a response with a peak over a window.** A peak is a biased estimator of
>   a fluctuating signal -- it is positive with no stimulus at all -- and here that bias is
>   +0.070 against a real tap response of +0.020. The first habituation assay was measuring
>   almost entirely noise and reported the memory as absent when it was merely swamped. Use
>   a difference of means over matched windows.
> * **Do not measure locomotion with unsigned speed.** The first ablation test passed the
>   AVB-ablated animal at 0.24 mm/s, *faster* than intact, because it had handed over to
>   the backward generator and was crawling away tail-first. The sign is the phenotype.
> * **Do not trust a gait number without knowing the step size it was measured at**, until
>   item 1 above is resolved.

> ## Day six. The decision has no input, and that is now a number.
>
> **State: locomotion untouched, 33 tests pass. Everything below is diagnosis and four
> refuted fixes. Nothing shipped is changed -- every parameter added today is zero.**
>
> ### The finding
>
> The forward/backward decision sits **3.81 standard deviations** from its own boundary,
> and a physiological chemosensory signal moves it **0.008 of one standard deviation**.
>
> `tools/command_probe.py` drives named neurons with known currents and reports what the
> command difference does. Bare plate, three seeds:
>
> ```
>   probe          fwd act   bwd act   difference (sd)    gate    shift    crossings
>   baseline       0.792     0.582     +0.2100 (0.0315)   0.952   +0.0000   1
>   ASEL +1pA      0.793     0.583     +0.2097 (0.0315)   0.951   -0.0003   1
>   ASEL +10pA     0.794     0.585     +0.2087 (0.0314)   0.946   -0.0013   3
>   AVA +5pA       0.797     0.592     +0.2048 (0.0313)   0.944   -0.0051   3
>   AVA +20pA      0.809     0.619     +0.1903 (0.0314)   0.917   -0.0196  13
>   AVB -20pA      0.729     0.586     +0.1427 (0.0646)   0.744   -0.0672  153
> ```
>
> ASE at 10 pA is **seventeen times** what the pathway actually delivers -- the triage
> measures 0.58 pA rms on a real lawn gradient -- and it closes 1% of the distance to the
> boundary. At the physiological 1 pA it closes nothing measurable. Even 20 pA injected
> straight into the backward command pool gets 16% of the way.
>
> This is the day-four table's single cause, stated as a quantity. It is not a gain
> problem: no gain multiplies 0.008 into 3.81.
>
> ### Why: the two pools are a mutual amplifier
>
> They **correlate at +0.76**. Read the AVA +20 pA row again -- driving the backward pool
> raises it by 0.037 and drags the forward pool up by 0.017 at the same time. Nearly half
> the injected current crosses over, because every command interneuron here is cholinergic
> or glutamatergic and the model collapses both to a 0 mV reversal: the pools are wired to
> each other *excitatorily*, 70 reconstructed contacts one way, 33 the other, 10 gap
> junctions. The decision reads their difference, which is the one component that common
> drive cannot move.
>
> ### Four fixes tried. All four refuted, and the last two are the interesting ones.
>
> **1. Reciprocal inhibition between the pools does nothing.** `command_cross_inhibition`
> retargets the cross-pool synapses onto an inhibitory receptor -- licensed by the same
> argument this model already uses for AVL and DVB, whose GABA lands on the cation channel
> EXP-1, run in reverse: C. elegans glutamate opens the glutamate-gated chloride channels
> AVR-14, AVR-15 and GLC-1/2/3 as well as the AMPA-type GLR-1, so reversal potential is a
> property of the synapse rather than of the presynaptic cell.
>
> ```
>   cross  adapt |  corr   difference   margin   rev/min |  speed   net/path    TWI
>    0.00   0.00 | +0.744   +0.2128      3.83     1.67   |  0.1853   0.783    +0.767
>    0.25   0.00 | +0.748   +0.2174      3.99     1.67   |  0.1935   0.812    +0.767
>    0.50   0.00 | +0.746   +0.2221      4.10     1.00   |  0.1988   0.827    +0.770
>    1.00   0.00 | +0.737   +0.2316      4.30     1.00   |  0.2077   0.853    +0.774
> ```
>
> The correlation will not move and the margin gets *worse*. Both for the same reason: the
> forward pool makes 70 contacts onto the backward one against 33 coming back, so making
> the pair mutually inhibitory only lets the stronger side win harder -- and the pools were
> never correlated *by* those synapses in the first place. They are correlated by shared
> input, and retargeting a few percent of each pool's conductance cannot touch that.
>
> **2. Slow adaptation moves the margin and buys no behaviour.** `command_adapt_ratio`,
> 15 s time constant, so the winning side tires:
>
> ```
>   adapt |  corr   difference   margin   rev/min   dur s |  speed   net/path
>    0.00 | +0.744   +0.2128      3.83     1.67     0.06  |  0.1853   0.783
>    0.02 | +0.728   +0.2057      3.47     3.67     0.07  |  0.1855   0.790
>    0.05 | +0.694   +0.1957      2.95    12.00     0.06  |  0.1839   0.798
>    0.10 | +0.611   +0.1808      2.18    30.00     0.07  |  0.1752   0.783
>    0.30 | +0.473   +0.1220      0.42    82.33     0.22  |  0.0974   0.518
> ```
>
> The margin comes down monotonically at almost no cost to locomotion, and the reversals
> are not reversals. **Every episode lasts 0.06 to 0.08 s** -- one fifteenth of an
> undulation cycle -- at every setting, including the one producing thirty a minute. A body
> cannot reverse in 0.07 s. What is counted is the difference dipping below a threshold it
> still sits above and bouncing straight back. Turned up until the *rate* looks biological,
> the margin collapses into the noise and net speed halves.
>
> So fatigue is not the missing property. **Persistence is**: a reversal is a state the
> animal stays in for seconds. Adaptation lowers the mean of a noisy signal towards a
> threshold; it does nothing to make the far side of that threshold somewhere the animal
> can remain.
>
> **3. Bistability supplies both missing properties, and halves locomotion.**
> `command_ca_ratio` adds the regenerative limb -- the same Morris-Lecar construction the
> B-class motor neurons already carry, and where the recordings put it: AVA holds
> depolarised plateaus lasting seconds.
>
> ```
>    ca    adapt |  corr   difference   margin   rev/min   dur s |  speed  net/path   TWI
>    0.00   0.05 | +0.694   +0.1957      2.95    12.00    0.06  |  0.1839   0.798   +0.757
>    0.20   0.05 | +0.487   +0.2074      1.38    66.00    0.07  |  0.1111   0.537   +0.725
>    0.35   0.05 | -0.042   +0.2274      1.15   104.00    0.13  |  0.0853   0.427   +0.719
>    0.50   0.05 | -0.015   +0.3143      1.62    28.00    0.25  |  0.0851   0.385   +0.753
>    0.50   0.15 | +0.714   +0.2160      0.44    10.33    3.19  |  0.0404   0.233   -0.096
> ```
>
> **The correlation finally breaks** -- +0.69 to -0.04, the first thing all day to move it
> -- and episodes leave the flicker floor, reaching 3.19 s. Those are precisely the two
> properties that were missing. And every calcium row costs about half the locomotion.
>
> **4. Two explanations for that cost, both refuted.** This is where it stopped, and the
> refutations are worth having because both were plausible enough to act on.
>
> *It is not the reversals.* Holding `gate_bias` at 0.00 so that the animal reversed **not
> once** in the whole run still gave speed 0.091 and net/path 0.400, against 0.185 and
> 0.783 shipped. The cost is there with the behaviour switched off.
>
> *It is not the resting depolarisation.* At `ca_offset` 0 the calcium gate is half open at
> rest, a standing depolarising load on cells whose potential matters. Closing it at rest
> (`command_ca_offset` 8 and 16 mV) made locomotion slightly **worse**, 0.091 -> 0.063 ->
> 0.061.
>
> *And it is not AVB's gap junctions to the B cord*, which was the best structural guess:
> AVB and PVC gap-junction onto the B class with 58 contacts and AVB's resting potential is
> the bifurcation parameter that poises those units, whereas AVA/AVD/AVE put 102 contacts
> onto the A class, which carries no regenerative conductance at all (`a_class_scale` is
> 0) and is therefore poising nothing. Putting the calcium on AVA alone should then have
> been free. It was not -- if anything it was slightly worse than doing both pools:
>
> ```
>   where         ca   adapt  bias |  corr   difference  margin  rev/min  dur s | speed  net/path
>   AVA only     0.35   0.05   0.09 | +0.046   +0.1551     0.46    95.00   0.23 | 0.0749   0.388
>   AVA only     0.50   0.05   0.09 | +0.025   +0.2343     0.99    47.67   0.24 | 0.0678   0.313
>   both pools   0.35   0.05   0.09 | -0.042   +0.2274     1.15   104.00   0.13 | 0.0853   0.427
>   shipped      0.00   0.00   0.09 | +0.744   +0.2128     3.83     1.67   0.06 | 0.1853   0.783
> ```
>
> ### What this says the next move is
>
> The mechanism is right and the *place* is wrong. Something about carrying dynamics on the
> command interneurons costs the gait, and it is none of the three obvious routes. The
> leading remaining candidate, and the first thing to measure, is that depolarising AVA
> wakes the backward cord: `a_class_scale` is 0 precisely because "held at equal strength
> both cords amplify at once and fight over the same muscles", and a bistable AVA drives
> the A class through 102 gap contacts and its chemical synapses whether or not the
> direction gate ever flips. That is testable directly -- measure A-class calcium gate and
> muscle drive with and without the calcium, which needs no new parameter.
>
> There is also a structural reading worth taking seriously, because it is the same
> conflation day five only half removed. `tonic_forward` was split into a decision bias and
> a cord drive, but the *gate* still does both jobs: one scalar picks the direction **and**
> apportions how much drive each cord receives. Giving the decision dynamic range therefore
> necessarily modulates the gait. Separating "which cord" (a latched, hysteretic choice)
> from "how much" (a constant) is the change that would let the decision move freely, and
> it is a small change to `Senses.sense`.
>
> ### The gait is not converged at the timestep it ships at
>
> This started as a performance question -- everything costs 2000 steps per simulated
> second, so raising `dt` is the obvious lever -- and turned into something worth more than
> the speed. `tools/timestep_convergence.py`, five step sizes, three seeds, 60 s each,
> net displacement over the whole window rather than a trailing average:
>
> ```
>    dt ms   steps/s |   freq Hz (sd)    wavelen L      TWI     k_rms   speed mm/s
>    0.125     8000  |  1.622 (0.021)      0.61      +0.729     2.68    0.3245
>    0.250     4000  |  1.411 (0.034)      0.58      +0.771     2.64    0.2770
>    0.500     2000  |  1.233 (0.036)      0.54      +0.764     2.30    0.1918   <- shipped
>    1.000     1000  |  1.028 (0.042)      0.50      +0.708     1.80    0.0899
>    2.000      500  |  0.717 (0.083)      0.49      +0.524     1.42    0.0203
> ```
>
> Halving the step from 0.25 to 0.125 ms still moves the frequency by **15%** and the net
> speed by **17%**, against a seed spread of 0.03 Hz. The trend is monotonic across a
> sixteen-fold range and nowhere near flat at the finest step tried. Curvature amplitude is
> close to converged (2.64 -> 2.68, +1.5%); frequency, wavelength and speed are not.
>
> Two headline numbers in this project change meaning as a result.
>
> **The frequency discrepancy is worse than reported, not better.** The model is recorded as
> undulating at 1.2 Hz against the animal's 0.30-0.50 Hz. Refine the integrator and it goes
> *up*: 1.62 Hz at 0.125 ms and still climbing. Whatever the converged value is, it is
> further from the animal than the number we have been quoting, so every "the frequency is
> too high" note in this file understates the problem.
>
> **The speed agreement is partly an artefact of this timestep.** At 0.5 ms the animal
> crawls at roughly the measured 0.219 mm/s, which has been read as the model getting
> something right. At 0.125 ms it does 0.3245 mm/s, half again too fast. The model is not
> matching the animal's speed; it is matching it at one step size, on the way past.
>
> Those two are the same fact seen twice -- an undulation that is too fast drives a body
> that travels too fast -- and it makes the frequency the single problem to solve rather
> than one of several.
>
> **The likely cause is the body, not the neurons.** Integration is exponential Euler on the
> membrane equations, which is exact for their linear part. `Body.step` puts backward Euler
> on the constant elastic and damping matrices but evaluates the configuration-dependent
> drag metric explicitly and then takes `pos + qdot*dt`, so the mechanics are first-order.
> The gait is a limit cycle closed through that integrator, and a limit cycle's period is
> exactly what first-order phase error moves.
>
> So `dt` should come **down**, or the body should go to second order, and neither is a
> performance decision. Do not raise it: that would make an unresolved number cheaper to
> compute without making it truer. `tools/timestep_convergence.py` is the tool that settles
> it, and it takes four minutes.
>
> ### On the assay runner
>
> One flat job queue instead of one `pooled()` call per assay, and eight workers instead of
> ten. The old arrangement ran each assay to completion before starting the next, so a
> 12-job assay finished with a wave of two trials holding the machine for as long as a full
> wave -- about 30% of the wall clock across the suite. Workers past the eighth land on
> this machine's efficiency cores and, because a wave ends when its slowest trial does,
> drag the whole wave with them: going 8 -> 12 buys 10% aggregate throughput while making
> each individual trial 37% slower. Both measurements are recorded in `tools/assays.py`.
>
> Not done, and deliberately: **decimating the world field sampling.** It is 14.6% of every
> step and it is safe -- 99% of the power in what ASE actually reads sits below 1.23 Hz and
> 99.9% below 4.2 Hz, so a zero-order hold at 100 Hz costs 0.24% rms error in that signal.
> But it buys 14% in exchange for putting a second clock into a model that currently has
> exactly one, and it is worth much more after the timestep question is settled than
> before: at `dt` = 0.125 ms the same 100 Hz hold saves four times as much.
>
> ### Added
>
> * `tools/command_probe.py` -- what each input is worth, in units of the decision's own
>   fluctuation. This is the tool that turned "chemotaxis does not work" into a number.
> * `tools/command_sweep.py` -- scores the behavioural and locomotor halves side by side,
>   because either alone is easy to fake. The **duration** column is the one that matters;
>   it is what separates a reversal from a threshold flicker, and without it configurations
>   2 and 3 above both look like successes.
> * `tools/ethogram.py` -- reversal rate, run durations and reorientation off food and on,
>   against Zhao et al. Only smoke-tested so far, one animal for 20 s per condition, and
>   even that turned up something: **the food dependence runs backwards.** Off food the gate
>   never crosses at all; on a lawn it crosses 99 times a minute. The animal's ordering is
>   3.2-3.5 per minute off food and 0.7-1.25 on it, so the model is inverted as well as
>   mistimed. This is the serotonergic turning arm from day five doing exactly what it was
>   calibrated to do -- `serotonin_turning` shifts the gate towards reversal on food, and it
>   is the only reason the basal slowing response reproduces at all -- meeting a threshold
>   that cannot tell dwelling from a flicker. Worth a proper run before anything is
>   concluded from it, but it points at the same place everything else today does.
> * `NervousSystem.E_syn`, a per-synapse reversal potential (post, pre) instead of a
>   per-neuron one. Receptor identity belongs to the postsynaptic cell. Costs no arithmetic
>   -- `G_syn @ (s * E_pre)` becomes `(G_syn * E) @ s` with the product taken once at
>   construction -- and reproduces the previous model to 2e-15 relative, membrane potentials
>   and synaptic activations exactly.
> * Five zero-valued parameters in `NeuralParams`: `command_cross_inhibition`,
>   `command_adapt_ratio`, `command_adapt_tau`, `command_ca_ratio`, `command_ca_offset`,
>   `command_ca_classes`. All zero-safe, all with their measurements recorded next to them.
>
> ### Still outstanding from day five
>
> **The assay rerun did not complete.** Only `triage` finished before it had to be
> abandoned (see the hazard below), and its result is the one that mattered: **zero
> reversals across six animals in sixty seconds each**, gate pinned at 0.95 forward in every
> one. Chemotaxis, aerotaxis, thermotaxis and nociception are still un-rerun since the food
> fix. Aerotaxis remains the best bet.
>
> ### Do not repeat these
>
> * **Do not edit anything under `worm/` while a sweep is in flight.** `pooled()` launches
>   a fresh OS process per trial that imports the package from disk, so an edit part-way
>   through a run silently mixes two code versions in one result table. This cost a
>   45-minute assay run today. Finish the code, then start the sweep.
> * **Do not score a reversal by counting threshold crossings.** Every configuration in
>   section 2 above looks like progress on rate alone and is worthless on duration. Any
>   claim about reversals needs the episode length next to it.
> * **Do not read a sweep whose threshold was calibrated for a different operating point.**
>   `gate_bias` was placed against a difference of mean 0.21 and sd 0.032; calcium
>   quadruples that sd, so the same number means something else. Re-place it per
>   configuration or the rows are not comparable.

> ## Day five. Modulators, and two real bugs in the world.
>
> **State: locomotion 0.246 mm/s (animal 0.219), TWI +0.778, net/path 0.905, 33 tests pass.**
>
> ### What landed
>
> **The command decision is decoupled from the gait drive.** `tonic_forward` was doing two
> incompatible jobs -- choosing direction, and (since the Morris-Lecar work) deciding
> whether the animal could walk at all. Now `tonic_forward` (22 pA) only biases the
> decision, `cord_drive` (8 pA) feeds the gait to whichever cord the gate selects, and the
> gate reads the *difference* between command pools instead of cubing absolute activities.
> Worth +23% speed on its own, and the gate finally has dynamic range (sd 0.000 -> 0.038).
>
> **`worm/modulators.py`: the wireless connectome.** Four slow scalars -- dopamine,
> serotonin, octopamine, PDF -- produced by their real source neurons, decaying on their own
> time constants, acting by scaling gains rather than injecting current. Every coefficient
> is zero-safe; zero reproduces the previous model exactly. Basal slowing response
> calibrated to **0.50** against the animal's ~0.5.
>
> ### Two bugs that invalidated earlier results
>
> **Every bacterial lawn was inside-out.** Transposed `_smoothstep` arguments meant food was
> 0 at a patch's centre and 1 everywhere *outside* it, out to the dish wall -- a 9 mm lawn
> sampled 0.002 at its own centre while the dish held 26,000 units. Oxygen derives from that
> field, so **the aerotaxis null in the day-four notes is withdrawn**; it was scored against
> a backwards gradient. Now 6% on a lawn against 21% at the edge.
>
> **The animal ate a hole under itself in ~2 s.** `World.eat` subtracted the full requested
> amount from each of nine cells, removing 9x what was asked, and `ingestion_rate` was 45x
> too fast besides. "On food" was therefore a condition that decayed away during any
> measurement. Fixed to a proportional total withdrawal at 0.02 units/s, which matches
> `world.py`'s own stated intent of depletion mattering "over tens of minutes".
>
> ### The honest caveat on the slowing response
>
> We reproduce the behaviour by the wrong route. Dopamine scaling the cord drive turns out
> to be a *weak* lever -- pinned at its 0.25 floor the animal still only slows 23%, because
> speed here is set by the proprioceptive loop and the motor neurons' own dynamics, not by
> how hard the cord is driven. All of our slowing comes from the serotonergic turning arm.
> In the animal, cat-2 mutants that cannot make dopamine *fail to slow*, so dopamine is
> necessary. Ours does not need it. Worth fixing, and worth not forgetting.
>
> ### Next, in order
>
> 1. **Rerun every assay.** All of them predate the food fix; aerotaxis is known-invalid and
>    the rest are suspect. `PYTHONPATH=. .venv/bin/python tools/assays.py all`, ~45 min.
>    Oxygen is the best bet: URX/AQR/PQR make 44 direct contacts onto the backward command
>    pool, more than any other sensory pathway, and the gradient is now real.
> 2. **Does the modulator layer unblock chemotaxis?** The dwelling result is a small
>    existence proof -- food changed the gate's behaviour, which nothing sensory had managed
>    before. Modulators act slowly and scale gains, so the 70x ASE->AVA attenuation that
>    blocks the fast route may not apply to them.
> 3. **Habituation.** Cheap, and Rankin's decrement and spontaneous-recovery curves are
>    quantitative targets. First thing on the list that is memory rather than modulation.
> 4. Fix the dopamine route above.
>
> ### Do not repeat these
>
> * **Do not use a process pool for sweeps.** `multiprocessing.Pool` and
>   `ProcessPoolExecutor` both deadlocked -- four runs lost, every worker at 0% CPU, parent
>   blocked on a lock, on an idle machine with 70% memory free. `pooled()` now launches one
>   independent OS process per trial with results as JSON on stdout. It cannot deadlock and
>   it reports per-job failures. Do not "optimise" it back into a pool.
> * **Anything using `pooled()` must live in a real file.** Spawn cannot re-import
>   `__main__` from a heredoc. This trap was documented, then walked into anyway.
> * **Do not run sweeps and pytest together.** Not a correctness issue but the suite goes
>   from ~5 min to 23 min.
> * The reversal detector (centroid velocity vs body axis) is only meaningful when net/path
>   is above ~0.3. Below that it reports slosh as turns.
> * Timing: one trial of D simulated seconds costs ~1.7xD wall-seconds on one core (0.58x
>   real time, flat regardless of BLAS threads). `estimate()` prints the prediction.

> ## Day four. The senses are measured, and they do not work. One cause.
>
> `tools/assays.py` reproduces standard plate experiments and scores them the way the
> original papers do. Locomotion is untouched (33 tests pass, 0.19 mm/s, TWI +0.75).
>
> | assay | result | real animal |
> |---|---|---|
> | chemotaxis index | **−0.014**, 7/16 animals approached | +0.5 or better |
> | approach over 200 s | **−0.86 ± 5.35 mm** | — |
> | aerotaxis, O2 occupied | **20.2%** (start 20.2, ambient 21) | 5–12% |
> | reversals | **1 per 6 animal-minutes** | 1–2 per minute |
>
> **The cause is a single structural conflation, and it explains every row.**
> `tonic_forward` injects 90 pA into AVB, which does two incompatible jobs at once:
>
> 1. it sets *which direction the animal goes*, via the cubed winner-take-all in
>    `Senses.sense` (gate reads 0.91/0.25 → 98% forward, in every animal, all run); and
> 2. since day three it also sets *whether the animal can walk at all*, because AVB's
>    membrane potential is what holds the B-class motor neurons at their Hopf bifurcation.
>
> Lower it and the gait dies before the decision changes: at tonic 22 the gate has only
> moved from 98% to 90% forward, but net/path has collapsed from 0.76 to 0.05. We
> re-entered day two's failure through a different door.
>
> **What is NOT wrong, so nobody re-checks it:**
> - *The wiring.* ASE reaches AVA and AVB in two hops via AIY/AIB, which is the real circuit.
> - *The sensors.* Raising `chemo_gain` 46× does propagate: ASE moves 24.8 mV, AIY 5.1,
>   AIB 1.05, AVA 0.35, DB/VB 2.72. It is real, and it deflects the path by 0.157 mm out of
>   9.4 mm travelled — 1.7%. Gain alone cannot rescue this; sweeping it to 1200 pA/unit
>   (drive 60 pA, well past the 10–250 pA anyone has injected experimentally) changes the
>   chemotaxis outcome by less than the seed-to-seed spread.
> - *Signal-to-noise alone.* The drive is 0.48 pA against a 2.2 pA noise floor, which is
>   real but is not the binding constraint — see above.
>
> **The A-class mirror, tested and left off.** AVA makes 102 gap contacts onto 20 of 21
> A-class units (AVB: 55 onto 18), so the backward cord has the same architecture and
> should get the same regenerative treatment. It is implemented (`oscillator_classes` now
> includes DA/VA, gated by `a_class_scale`) and switched off at 0.0, because the command
> circuit does not separate the cords: during forward locomotion the B class sits at
> calcium gate 0.780 and the A class at 0.670, **both above the 0.5 bifurcation**, 2.2 mV
> apart. Both cords amplify at once and fight over the same muscles. Full sweep in
> `NeuralParams.a_class_scale`. This unblocks the moment (1) is fixed.
>
> **So the next job is to decouple those two roles**, and the pieces are already in place:
> the locomotor drive should come from the AVB→B gap junctions (real, in the connectome,
> and since day three genuinely doing that job), leaving the forward/backward decision as a
> separate contest between AVA and AVB that does not drag the gait's operating point with
> it. In the animal the A and B classes are antagonistic at the motor level, not gated by
> one scalar. Expect chemotaxis, aerotaxis, nociceptive escape and the A-class fix all to
> move together, because they are all downstream of the same missing dynamic range.
>
> Thermotaxis and nociception assays are written but not yet run.
>
> **Tooling notes for whoever picks this up.** One trial of D simulated seconds costs
> ~1.7 × D wall-seconds on one core (0.58× real time, flat regardless of BLAS threads --
> the body's matrices are 49×49). `estimate()` prints the prediction; `pooled()` streams
> per-trial progress, because a `pool.map` deadlocked silently at 0% CPU for thirteen
> minutes and looked exactly like a slow run. Anything using the pool must live in a real
> file: spawn cannot re-import `__main__` from a heredoc. And the reversal detector
> (centroid velocity vs body axis) is only meaningful when net/path is above ~0.3 — below
> that it reports slosh as turns, which is why an early sweep appeared to show 25 reversals
> in a worm that was going nowhere.

> ## Day three. The travelling wave is fixed. Read this part first.
>
> Two changes landed, and the control sweep separating them is `tools/osc_control.py`.
>
> **1. Sensory input is now scaled by each target's resting conductance.** A fixed current
> produces a voltage inversely proportional to the cell's input conductance, and across the
> B class that conductance spans 0.63 to 3.20 nS — so a uniform proprioceptive current was
> hitting the small posterior units five times harder than the large anterior ones. Worth
> +14% on its own.
>
> **2. The B-type motor neurons became Morris-Lecar regenerative units** (`ca_ratio`,
> `adapt_ratio` in `NeuralParams`), poised at a Hopf bifurcation by the descending AVB gap
> junctions that were already in the connectome. Worth a further +31%.
>
> | | TWI | net mm/s | net/path | amplitude head/mid/tail | tail coherence |
> |---|---|---|---|---|---|
> | day two | +0.60 | 0.105 | 0.70 | 2.5 / 1.3 / 1.0 | 0.03–0.05 |
> | conductance scaling only | +0.64 | 0.120 | 0.71 | 2.5 / 1.3 / 1.0 | 0.08 |
> | **today** | **+0.75** | **0.172** | **0.86** | **2.6 / 1.9 / 1.9** | **0.35** |
> | this body, prescribed wave | +0.996 | 0.174 | — | — | — |
> | real animal | — | 0.219 | — | roughly flat | — |
>
> Net speed is now at the prescribed-wave ceiling for this body, and 78% of the animal's.
> The exponential amplitude decay down the body — the thing the whole day-two analysis was
> about — is gone: 2.5/1.3/1.0 became 2.6/1.9/1.9. Coherence rose in *every* region
> (head 0.4→0.90, mid 0.4→0.84, tail 0.03→0.35).
>
> **The result that surprised me, and the reason to keep the tooling.** Net speed peaks at
> `ca_ratio` 0.20, where the Hopf margin is 0.94 — the units sit *at* the bifurcation, not
> past it. Pushed past (0.26, 0.32, 0.55) each segment free-runs, locks to itself, the tail
> reaches 4x the head's amplitude and **the wave runs backwards**. Xu et al.'s mechanism is
> right; "just past the bifurcation" is doing a lot of work in that sentence, and the
> useful regime is critically poised amplifier, not autonomous oscillator.
>
> **Still wrong, in priority order:**
> 1. **Frequency: 1.17–1.24 Hz against 0.4–0.5 Hz for a real animal.** Sweeping `adapt_tau`
>    over an eighteen-fold range moves it under 5%, so it is set by the body and the reflex
>    loop, not the neurons. Go after drag, `internal_damping`, and muscle activation
>    kinetics. This is now the biggest single discrepancy.
> 2. **Wavelength 0.52 L against 0.65 L.** Probably the same cause as (1).
> 3. **Curvature rms 2.3 against 4.3.** The worm undulates too shallowly.
> 4. **Backward locomotion is known-poor.** Clamping AVB off correctly hands over to the
>    A-class generator and the wave does reverse, but curvature rms goes to 7.5 and net
>    speed to 0.018 mm/s. The gate offsets are placed relative to a resting potential solved
>    with AVB intact and do not follow it down. Untested before today; do not cite it as
>    working.
> 5. Tail coherence is 0.35 — much better than 0.03, still the worst region.
>
> Everything below this line is from day two. The sections on *why* the wave decayed remain
> the correct analysis; the "what to try" lists are superseded by the above.

> **Day two. The big one is fixed, and here is the state.**
>
> Proprioception was the one sensory channel still responding to absolute value rather than
> to change. Making the stretch receptor adapt took net speed from 0.005 to **0.10 mm/s**
> and the net-to-path ratio from 0.07 to **0.66-0.72** — inside the real animal's range.
> The worm crawls. Details in the README; the rest of this file is what is still wrong.
>
> **Everything below now hangs off one number,** the travelling-wave index. A standing wave
> makes no net thrust at all, so this is the quantity that decides the speed:
>
> | | TWI | net mm/s |
> |---|---|---|
> | this body, prescribed travelling wave | **+0.996** | **0.174** |
> | the model today | +0.48 to +0.57 | 0.10 |
> | the model yesterday | +0.33 | 0.005 |
> | real animal | — | 0.219 |
>
> The relationship is close to linear, so closing the remaining gap gets to the animal's
> speed and takes the wavelength and frequency errors with it — they are the same standing
> wave seen from other angles.
>
> **Where the wave actually fails, measured by region** (`tools/twi_by_region.py`):
>
> ```
> head and neck   0.00-0.30    TWI -0.10    45-55% of all curvature power
> body behind it  0.30-1.00    TWI +0.24 to +0.50
> posterior half  0.45-1.00    TWI -0.02 to +0.18
> ```
>
> So the head is a strong standing oscillator carrying about half the total power, the
> mid-body travels weakly, and **the posterior half barely travels at all**. The wave is
> generated at the front and dies before it gets down the body. That is the single
> remaining problem, and it is the same one the per-segment reflex gain measures.
>
> **Four hypotheses tested and refuted today.** Do not redo these:
> 1. *Back off the head reflex.* Tested from 150 down to 0: TWI goes **negative** (the wave
>    reverses) and speed collapses. The head reflex is what makes the wave go head-to-tail.
> 2. *Push the head reflex harder.* Tested 150 up to 900: TWI saturates flat at +0.58.
>    Worth perhaps 15% more speed at a gain of 400, and nothing beyond that. The ceiling is
>    not set by head gain in either direction.
> 3. *Bending stiffness.* Swept over a 1600-fold range with muscle moment scaled to hold
>    curvature fixed. A shallow 25% effect peaking 4-8x **above** the measured value, and
>    the literature's low value (Sznitman) is much worse. Not the lever.
> 4. *AVB broadcasting a common rhythm through its gap junctions.* It swings 4 mV, and
>    clamping it to a constant potential changes nothing.
>
> **Fifth hypothesis, also refuted, and it discredits a tool.** The reflex-gain sweep was
> rerun with the adapting receptor and said `peak_moment = 3.2` beat the current 2.6 in all
> twelve pairings, with tail gains up to 19. In the closed loop it is clearly worse:
>
> ```
> moment   TWI     TWI posterior   amp tail   net mm/s   net/path
> 2.6     +0.48..+0.57   -0.02..+0.28    2.4-3.3     0.095-0.106   0.66-0.72   <- current
> 3.2     +0.33..+0.42   -0.08..-0.01    8.3-8.6     0.068-0.071   0.46-0.50
> 4.0     +0.14..+0.40   -0.14..+0.05   12.0-12.9    0.041-0.079   0.26-0.29
> ```
>
> Absolute tail amplitude more than triples while the posterior travelling index stays at
> zero. It is making a **bigger standing wave**, not a travelling one, and going slower for
> it. `reflex_gain.py`'s headline number is a ratio whose denominator dies towards the tail,
> so it cannot distinguish those two outcomes; the caveat is now written into the tool.
> **Decide with `tools/twi_by_region.py` and absolute amplitudes instead.**
>
> **Sixth hypothesis refuted, and it corrects the fifth.** After the adaptation fix the
> phase profile reads completely differently: the phase gradient along the cord is now
> **-379 degrees**, against the -300 a 0.65 L wavelength needs. It is clean, monotonic, and
> more than sufficient. The circuit generates a properly travelling pattern; earlier
> conclusions drawn from the pre-adaptation profile (-159 deg) are void.
>
> What decays sevenfold head to tail is the *coherent* component -- the amplitude at the
> wave frequency. Total curvature variance is roughly equal head and tail. So the posterior
> moves plenty; it just does not move in time with the wave. That is a different fault from
> "the wave is attenuated", and it took a second measurement to tell them apart.
>
> The muscle efficacy taper looked like the obvious cause, since this model copies Boyle's
> 1.0-to-0.41 head-to-tail ramp. Flattening it does raise posterior amplitude, dramatically
> -- the head/tail ratio goes from about 1.0 to 0.17, so the tail ends up six times the head
> -- and everything gets worse:
>
> ```
> eff_tail   TWI            TWI post        head/tail   net mm/s      k_max
> 0.41    +0.48..+0.57   -0.02..+0.28      1.0-1.4    0.095-0.106   12-14   <- current
> 0.70    +0.18..+0.28   -0.06..+0.00      0.27-0.29  0.032-0.039   29-30
> 1.00    -0.57..-0.21   -0.38..-0.26      0.20-0.21  0.009-0.017   38-40
> 1.40    -0.01..+0.12   -0.05..+0.08      0.16-0.17  0.012-0.028   54
> ```
>
> The taper is load-bearing: it is what stops the posterior thrashing incoherently. Boyle
> was right and 0.41 is the best of the range.
>
> **Six parameter directions have now been tested and every one confirms the current
> defaults sit at a local optimum**: head reflex weaker, head reflex stronger, bending
> stiffness, AVB gap-junction broadcast, muscle moment, muscle taper. The travelling index
> will not go above about +0.57 for any of them, and the failure mode is always the same --
> the posterior moves, but incoherently.
>
> **So the next thing to do** is not another parameter sweep. Five have now failed, and the
> pattern across all of them is that the posterior travelling index will not move off zero
> no matter what the parameters do. That points at structure rather than tuning -- most
> likely hypotheses H1 (the graded synapse cannot more than double its conductance, which
> caps how much a motor neuron can modulate its muscle) and H2 (proprioceptive input should
> be a conductance, not a current) in the list below. Those are the two that change the
> model rather than its numbers, and they are what is left.

## The one problem worth solving first

**Make an omega turn change the animal's direction.** The command circuit now reverses at
the right off-food rate, but a reversal changes heading by only a few tens of degrees. A
biased random walk cannot steer strongly if its reorientation event mostly retraces the
same path.

This is the current evidence, measured rather than inherited from an older note:

| Measurement | Current model | What it decides |
|---|---:|---|
| Off-food median reorientation | 37.75 deg | The turn is still shallow |
| Off-food fraction above 120 deg | 2.38% | Deep turns are rare, not merely hidden by the median |
| On-food median reorientation | 42.63 deg | Food does not repair turn depth |
| On-food fraction above 120 deg | 8.33% | Still far below the animal's roughly 35% deep-turn fraction |

Those values are the baseline arm of six paired animals per condition, 200 s each, from
`tools/compare.py ethogram`. The trajectory guards were net/path 0.406 off food and 0.332
on food; absolute heading drift was 2.25 and 4.05 deg/s. Reporting those guards is
load-bearing because the older ventral-only turn inflated reorientation by making the
animal circle.

### The wave-suppression route is decided, and it failed

The next hypothesis after the dynamic-range diagnosis was to quiet anterior undulation
while the omega transient was live. It was tested at the predeclared full-suppression
value on the same seeds. It made the turn **shallower**:

| Condition | Median, baseline -> suppressed | Paired difference (95% CI) |
|---|---:|---:|
| Off food | 37.75 -> 15.62 deg | -22.1 [-34.4, -12.4] deg |
| On food | 42.63 -> 29.05 deg | -13.6 [-22.3, -9.6] deg |

The fraction above 120 deg fell to zero in both conditions. Net/path, absolute heading
drift, and path speed did not move detectably. The travelling wave is helping carry the
turn down the body rather than consuming range a static bend could reclaim. Do not repeat
this as another suppression gain or target-set sweep; the negative result is recorded
beside `sensory.omega_wave_suppression`, which remains zero.

**Start with the dimensional ceiling.** The mechanical body is two-dimensional even
though a real deep omega brings the head alongside the tail out of plane. The next honest
implementation project is an explicitly scoped three-dimensional body representation
with a reorientation assay that still reports the spiral guards above. Do not hide that
project inside another current increase: `omega_current` is already in its saturation
regime, RIV gain failed, reflex suppression failed, and wave suppression now failed in the
opposite direction.

### Self-contact is not the constraint, and the steric half of the argument does not hold

The body has no self-avoidance — `World.contact_force` handles the dish wall and obstacles
and nothing compares the body against itself — so before starting a three-dimensional
project on the grounds that a deep omega leaves the plane, it is worth knowing whether the
plane was ever the obstacle. `tools/self_contact.py` measures it. It is not.

Bending the body's own radius profile into a uniform arc, self-contact first occurs at a
turn radius of **0.158 mm**, which is nothing more than the body closed into a circle
(L/2π = 0.159). The omega wants 0.22 mm and clears that by 1.4×, with 0.132 mm of daylight.
A two-dimensional worm can make the turn this roadmap asks for without touching itself, and
this one could pass through itself even if it could not.

Measured on the animal rather than on paper — five seeds, 60 s, both food conditions,
sampled every 50 ms — there is **no overlap at any scale, 0.00%**. The tightest approach
anywhere is 0.0254 mm, about 0.4 body diameters, between midbody and tail tip. One caveat
is worth carrying: on food the margin is thinner and much more seed-dependent than off
food, 0.1605 ± 0.1006 mm at the half-body cut against 0.2311 ± 0.0155 off it. A standard
deviation two thirds of the mean says at least one seed came considerably closer, in the
condition with more turning.

So **self-avoidance is latent, not live**, and closing it will not deepen a single turn.
What it will do is keep the turn project honest: a reorientation earned by folding the head
through the body would read as a clean turn in `tools/compare.py ethogram`, and no assay
here could say otherwise. It is inert *now*, which is the only moment it can be installed
and shown to change nothing — added afterwards, a regression could never be separated into
"the turn was passing through the body" and "the contact model is too stiff." Tracked in
issue #86.

None of this retires the dimensional ceiling; it retires one of its two arguments. The
steric case — that a deep omega must leave the plane because the animal cannot pass through
itself — is measurably not this model's problem. The case that survives is the one
`params.py` already makes under *what actually limits the turn*: a sustained bend and a
travelling wave are competing for the dynamic range of the same motor neurons, and a second
bending axis would give them somewhere to go. That is a better reason to build it, and a
different one, and it predicts something the steric argument does not — that the turn
should deepen when the two stop sharing a channel, whether or not anything leaves the plane.

### And then the surviving argument failed too: the ceiling is mechanical

**Retracting the paragraph above.** It was written before anyone asked the prior question,
and the prior question settles it the other way. Every experiment on this turn — the current
sweep, RIV gain, reflex suppression, wave suppression, and the dynamic-range reading that
survived them — drove the body *through the nervous system*. None asked whether the body can
make the turn at all.

`tools/moment_ceiling.py` bypasses the nervous system and drives the joints directly.
`Body.step` takes the bending moment as an array and `Simulation` reads it from one call to
`Muscles.joint_moment`, so an extra moment can be added there without touching any model
code. Curvature turns out not to be the scarce thing at all — the statics agree with the
elastica they are meant to be, and holding the 4.5 /mm an omega needs costs 0.43 µN·mm
against a `peak_moment` of 2.6, about six times over.

But with the gait running and a moment added on top, over five seeds:

| moment µN·mm | turn deg/s | path mm/s | TWI | κ max |
|---:|---:|---:|---:|---:|
| 0.00 | 4.8 ± 3.8 | 0.367 | +0.87 | 12.5 |
| 0.10 | 38.3 ± 6.7 | 0.331 | +0.89 | 13.2 |
| **0.15** | **47.5 ± 5.7** | 0.281 | +0.88 | 14.8 |
| 0.20 | 42.2 ± 10.2 | 0.215 | +0.86 | 19.2 |
| 0.43 | 18.7 ± 1.3 | 0.050 | +0.63 | 30.1 |
| 2.60 | 1.6 ± 1.1 | 0.006 | 0.00 | 119.4 |

**It peaks at 47.5 deg/s and comes back down.** A real omega needs about 90. Five profiles
were tried, and where the moment goes matters more than how much of it there is:

| profile | peak deg/s | at µN·mm | best row set aside, and why |
|---|---:|---:|---|
| whole body | **47.5 ± 5.7** | 0.15 | — |
| phase-locked | 22.8 ± 6.5 | 0.43 | **48.6 ± 3.0** at 0.80, path 0.148 under half free-running |
| travelling pulse | 25.5 ± 5.1 | 0.30 | 49.5 ± 32.0 at 2.60, spread 65% of mean |
| anterior third | 21.8 ± 4.5 | 0.15 | — |
| posterior third | 7.7 ± 0.7 | 0.43 | — |

**The two numbers that matter are 47.5 and 48.6, and they come from opposite strategies.**
The whole-body profile is the crudest thing available — a constant moment on every joint,
blind to what the body is doing. The phase-locked one is the opposite: it reads the animal's
own curvature every step and adds moment only where the body is already bending dorsally,
saturating at the gait's own amplitude, so it deepens one side of the wave and never fights
the other. They agree to within their error bars, and the phase-locked figure has the
tightest spread in the whole sweep at ±3.0, six percent of its mean.

Two unrelated routes arriving at the same wall is much better evidence than one route hitting
it. That is the result: **about 48 deg/s, a little over half what the animal does, and it does
not care how the moment is delivered.**

The 48.6 is reported as set aside rather than as the headline because path speed had fallen
to 40% of free-running, under the 50% floor. That floor is a judgement and a reader may
reasonably disagree with it — the gait was still alive there, TWI +0.83, and the animal was
still moving. The tool prints the row and the reason precisely so the judgement is arguable
instead of invisible; a cap that hides its best excluded cell reads as *nothing better was
found*, which is a different claim from *something better was found and rejected for this
reason*.

The posterior third is the control and behaves like one: a moment back there does almost
nothing, so this is not a measurement that would report a turn from any push at all. The
anterior third — which is where the omega drive *actually* lands, on RIV, SMD and RMD —
manages less than half the whole-body figure, which is its own small finding about where the
circuit is pushing.

The travelling pulse is the one that mattered, because it was the recorded caveat: a real
omega is not a constant bend held everywhere at once but a deep bend that starts at the head
and runs down the body, and a ceiling measured only on static profiles would not have tested
it. It was tested. **It does worse, not better** — 25.5 against 47.5. The kinematically
realistic profile buys about half of what the crude one does, so the ceiling is not an
artifact of holding the moment still.

Worth recording how close that came to reading the other way. Before the estimator was fixed,
turn rate was the difference of the heading trace's two endpoints, which is fine for a steady
turn and badly wrong for an oscillating one — and a travelling moment swings the heading back
and forth about its trend. It reported the travelling profile at 49.5 deg/s at full moment,
beating every static profile and overturning the whole result. The spread was ±32.0 across
five seeds, on a residual wobble of 79 degrees about its own trend. Two guards now stand
between that cell and the headline: a row must still be moving at half the free-running path
speed, and its across-seed spread must be under 40% of its mean. Both are in the tool.

The mechanism is in the definition. Turn rate is path speed times path curvature, and every
increment of curvature costs speed: by 2.6 µN·mm the animal is bent to κ = 120 and travelling
0.006 mm/s. The product therefore has a maximum, and that maximum — not any neural quantity —
is the ceiling. The rows past the peak are excluded from the headline by the tool itself,
because a turn rate read off a stationary animal is ill-conditioned and its error bars say so.

So the dynamic-range diagnosis is wrong, or at least it is not what binds. **No
redistribution of drive across motor neurons can buy a turn the body cannot make, and a
second bending axis is somewhere to put drive that was never the scarce resource.** That is
now four closed routes plus two closed arguments, and the honest position is that the
three-dimensional body project has lost both of its stated justifications and should not be
started on either of them.

What is left to explain is why v·κ peaks where it does. That is a statement about drag
anisotropy — `K = C_N/C_T` is 40 on agar — and about what a travelling wave does to a body
that is already bent. The next measurement is the peak's dependence on `K` and on `EI`,
because if the ceiling moves with the medium then it is hydrodynamic and the model's agar is
what is capping the turn; if it does not, it is the body's own elasticity. Neither answer is
a bending axis.

Both recorded caveats are now closed. The travelling profile tested whether the ceiling was
an artifact of holding the moment still: it is not. The phase-locked profile tested whether
it was an artifact of driving open-loop, a moment arriving at segments already bending the
wrong way and fighting them: it is not that either, and closing the loop bought about a
degree per second over the crudest possible alternative.

### And the ceiling is not a wall, it is a trade

`tools/turn_scaling.py` asked what sets the ~48 deg/s — the medium or the body — by sweeping
drag anisotropy across the three media and `EI` across a factor of eight. The answer is
neither, and the reason is more useful than either would have been.

A real omega is 90 deg/s at a 0.22 mm radius, which is the animal travelling **0.35 mm/s
while turning that tightly**. Both at once is the target. Splitting the measurement into
those two components:

| arm | radius mm | path mm/s | deg/s |
|---|---:|---:|---:|
| agar (K=40) | 0.363 — too wide | 0.278 — **ok** | 43.9 |
| viscous (K=9) | 0.366 — too wide | 0.204 — slow | 31.9 |
| buffer (K=1.6) | **0.069 — ok** | 0.027 — slow | 22.1 |
| EI 0.19 | 0.768 — too wide | 0.128 — slow | 9.6 |
| EI 0.38 | 1.613 — too wide | 0.049 — slow | 1.7 |

In buffer the animal drives a 0.069 mm arc, *three times tighter* than an omega needs — at
0.027 mm/s. On agar it has the speed and cannot make the radius.

**Do not over-read the buffer number.** Radius is v/ω, so an animal that barely translates
has a small radius almost by construction, and this one covers 0.27 mm in ten seconds while
turning 221°. That is consistent with a genuine 0.069 mm arc rather than an artifact — the
arithmetic closes — but it is much nearer pivoting on the spot than to what an omega does,
which is carrying the body through the turn. The honest statement is that tight *curvature of
the path* is available and tight curvature *at speed* is not; it is not established that the
first would survive being asked to do the second.

So the medium and the stiffness do not move radius and speed independently; they slide the
animal along a frontier. Nothing tested has both ends of it at once, and **that trade is the
ceiling** — not any single parameter, which is why four sweeps through the nervous system and
two through the mechanics all landed in the same place.

Two cautions attached to it. The buffer end is confounded by a defect this project already
knows about: gait modulation is far too weak, 0.66 → 0.85 Hz where the animal goes 0.30 →
1.76, so a buffer animal here is not swimming the way a real one does and its path speed is
as much symptom as measurement. And `EI` is measured rather than fitted — Fang-Yen et al. put
it at 9.5e-2 µN·mm² — so that arm was never a knob to turn, only a check that the measured
value is not accidentally the problem. It is not.

**Which makes gait modulation the next thing, not a bending axis.** It was already on this
roadmap as a second-tier quantitative gap. It is now on the critical path: the frontier says
turn depth needs speed *and* tightness together, and the reason the tight end is slow is the
same too-weak medium response that makes this animal fail to swim.

And that work already has a diagnosis waiting for it, written down under
`SensoryParams.head_delay`. The 0.28 s delay is the largest fitted number in the model and
is openly recorded as unearned — mechanotransduction takes milliseconds, and what the number
really states is the size of the phase the model is missing. The candidate for what it stands
in for is named there too: RMD, SMD and SMB are lumped into one reflex with one gain and one
filter, where the real thing is several cell classes with their own dynamics and an RMD that
is frankly bistable (Mellem et al. 2008). A distributed multi-stage circuit accumulates phase
a single first-order lag cannot — and, unlike a fitted constant, its phase can follow the
mechanical load, which is exactly what gait modulation is.

That note also records, correctly, that the *old* argument for why a fixed delay must kill
modulation was withdrawn once the reflex was distributed and the direction came out right.
None of what is above reinstates it. The claim here is only that the magnitude is still four
times short, and that the frontier now makes that shortfall load-bearing for the turn rather
than a separate quantitative gap to get to later.

> **That circuit now exists, the first half of the prediction held, and the second half
> failed.** Four first-order stages in series carrying 0.50 s between them reach the shipped
> frequency with `head_delay = 0` and improve the wave rather than trading it away — see
> `SensoryParams.head_stages` for the tables. But the claim this paragraph actually makes,
> that such a circuit's phase "can follow the mechanical load", **was tested and is false in
> this model**: `tools/head_medium.py` puts the cascade's frequency span at 1.29x against the
> shipped 1.27x, where the animal is 5.87x. The sentence above is left standing because it is
> the argument that motivated the work and it deserves to be visible next to its refutation,
> not because it survived. The live diagnosis is now under **Start here, 1b** — the
> modulation saturates by K = 9 and the wavelength never moves at all.

### Current gait baseline, so the turn project does not reopen a solved diagnosis

`tools/scorecard.py` on 2026-07-30 measured five seeds from the same configuration:

| Quantity | Current model |
|---|---:|
| Frequency on agar | 0.66 +/- 0.01 Hz |
| Wavelength on agar | 0.86 +/- 0.02 L |
| Net speed on agar | 0.309 +/- 0.051 mm/s |
| Travelling-wave index | +0.87 +/- 0.04 |
| Wave direction | 5/5 head -> tail |

`tools/diagnose_loop.py` independently found 0.680 Hz, 0.87 L and TWI +0.827 in its
single-seed diagnostic. The gait is too fast and too long, and its medium modulation is
far too small (0.66 -> 0.85 Hz where the animal goes 0.30 -> 1.76), but the wave is no
longer mostly passive or backwards. Those are quantitative gaps, not the old structural
failure.

`tools/reflex_gain.py --quick` reported gains 0.92, 1.73, 2.31, 1.81 and 2.86 from head
to tail at the current parameters. That non-monotone ratio is not a verdict on wave
quality: the tool now warns that its passive denominator becomes tiny posteriorly, which
can make a standing oscillation look like large regeneration. The closed-loop TWI and
absolute amplitudes decide; do not restore this ratio as the roadmap's primary evidence.

---

## Retired priority: the body wave is mostly passive

> **Historical, superseded 2026-07-30. Do not start here.** This section is preserved as
> the record of the earlier diagnosis and the experiments it motivated. Its 1.2 Hz,
> 1.4 L, 0.03-0.11 mm/s and backwards-modulation baseline predates the converged current
> model. Proprioceptive reach now changes wavelength, the wave travels head to tail in
> every scorecard seed, and the current numbers are in the section above.

**The body wave is mostly passive.** The head oscillates, the body follows because it is
mechanically attached, and the proprioceptive reflex adds only a modest amount on top.
Everything else that is wrong follows from this:

| Symptom | Model | Real |
|---|---|---|
| Undulation frequency, agar | 1.2 Hz | 0.30 Hz |
| Wavelength | 1.4 L | 0.65 L |
| Crawling speed | 0.03–0.11 mm/s | 0.219 mm/s |
| Gait modulation direction | backwards | agar slow, water fast |

Three independent measurements say the same thing:

1. Wavelength is **insensitive to proprioceptive reach** — 1.11 → 1.20 L as the reach goes
   from 0.10 to 0.20 body lengths. If the reflex set the wavelength, this would be the
   single most sensitive knob in the model. It is nearly flat.
2. Driving the head externally and toggling the body reflex changes mid-body amplitude
   from 0.17 to 0.25 — a per-segment gain near **1.4**, where regenerating a wave needs
   something closer to a sustained 1.0 *per segment* over many segments.
3. If the wave were regenerated along the body, the medium would act on every segment and
   gait modulation would work. It acts mostly on the head, and gait modulation is inverted.

`tools/reflex_gain.py` measures (2) directly and sweeps it over gain, reach and muscle
strength. **Start there.**

### A first sweep already ran, and it changes the plan

Partial results (each row is the gain at five positions from head to tail; a row that
*rises* left to right is a reflex regenerating the wave rather than merely passing it on):

```
gain   reach  moment   s=0.25  s=0.40  s=0.55  s=0.70  s=0.85
45     0.10   1.6        1.11    1.50    0.84    0.19    0.34
45     0.10   3.2        1.25    1.28    1.42    2.33    2.58
45     0.20   1.6        1.11    1.23    2.79    1.31    2.93
45     0.20   3.2        1.30    2.03    2.99    2.00    3.58
45     0.30   1.6        0.99    1.04    3.14    1.69    3.55
45     0.30   3.2        1.43    2.04    4.45    3.76    5.92   <-- strongly regenerating
90     0.10   1.6        1.21    1.27    1.47    1.55    1.51
90     0.10   3.2        1.26    1.28    1.96    1.81    0.90
90     0.20   1.6        1.24    1.96    2.00    1.08    1.69
```

Three things fall out of this, and the first two were not what I expected:

1. **`proprio_gain` is not the main lever.** Going from 45 to 90 pA does not reliably help
   and sometimes hurts. I had been treating it as the knob; it is not. Every hour spent
   sweeping it was largely wasted, which is worth knowing before repeating it.
2. **`proprio_reach` and `peak_moment` are the levers**, and they compound. The best row so
   far is the *lowest* proprioceptive gain with the longest reach and the strongest muscle:
   gain rising monotonically to 5.9 by the tail. That is the signature the model needs.
3. The current defaults (gain 90, reach 0.20, moment 1.6) sit in the weak-reflex corner of
   this table. That is precisely why the wave is passive.

**So the concrete first experiment tomorrow is:** set `peak_moment ≈ 3.2` and
`proprio_reach ≈ 0.30`, *drop* `proprio_gain` to ~45, and then **reduce
`head_proprio_gain`** so the head stops dominating — the body should now be able to carry
the wave itself. Then check with `tools/diagnose_loop.py` across at least three seeds
whether the 0.31 Hz / 0.70 L attractor has become the robust one.

Note that `peak_moment = 3.0` was rejected earlier in the build for producing twice the
real curvature, but that was measured with the *old, unfiltered* head reflex at full gain.
With the head backed off, the balance is different and it deserves re-testing rather than
being ruled out. Watch `kappa_max` — it must stay near 10 /mm.

The sweep was still running when this was written; re-run
`PYTHONPATH=. python tools/reflex_gain.py --out scratch/reflex_gain.json` for the full
24-row table (about 50 minutes; the `gain=180` and `gain=360` rows are the missing ones,
and on this evidence they are the least interesting).

### I then tried that configuration in the closed loop. It is the right direction.

`peak_moment=3.2, proprio_reach=0.30, proprio_gain=45`, head reflex left at its current
150, three seeds:

```
seed   freq   wavelen  direction    k_rms  k_max   speed   dv_corr
0     1.111    1.00   head->tail     5.15  22.42   0.118    -0.80
3     1.222    0.62   head->tail     8.32  23.88   0.118    -0.76
7     0.111    1.09   tail->head     8.34  23.28   0.099    -0.80
```

Compare against the shipped defaults (1.2 Hz, 1.4 L, k_max ~10, speed 0.03–0.11,
dv_corr −0.31). What improved, and it is not subtle:

- **Dorsoventral antagonism goes from −0.31 to −0.80.** The two muscle sheets are now
  genuinely alternating instead of half-heartedly. This is the single biggest jump I saw
  from any parameter change in the whole build.
- **Wavelength drops** from 1.4 L towards the measured 0.65 L (seed 3 hits 0.62 exactly).
- **Speed rises** and becomes consistent across seeds at ~0.10–0.12 mm/s.

What broke, and both look tractable:

- **Peak curvature is 22–24 /mm against a measured 9.8.** The body is being over-bent by
  roughly 2.3×. The obvious response is to back `peak_moment` down from 3.2 towards
  ~2.0–2.4 and see how much of the dv_corr and wavelength gain survives. There may be a
  sweet spot; there may not, and if not, that itself is informative about whether moment
  and reflex gain are separable.
- **Seed 7 runs backwards and very slow.** Reproducibility regressed, which is expected —
  the head reflex is still at 150 and is now fighting a much stronger body reflex for
  control of the wave. **Backing the head off is the untested half of this experiment**
  and is the first thing to run. I had `head_proprio_gain` at 60 and 25 queued and did not
  get to them.

So the ordered plan is: (a) re-run this with `head_proprio_gain` at 60 and 25 across the
same three seeds; (b) scale `peak_moment` down until `k_max` lands near 10; (c) confirm
with `test_gait_is_reproducible_across_seeds`; (d) if frequency is still high, *then* look
at H1 and H2 below. Do not touch H1/H2 before (a)–(c) — they are much more invasive and
this cheaper change may make them unnecessary.

### Hypotheses for why the reflex gain is low, roughly in order of my confidence

- **H1 — the synaptic dynamic range is the ceiling.** With each neuron's release threshold
  placed at its own resting potential, `phi = 0.5` at rest, so `s_rest` is always ≥ 50% of
  `s_max` and **no graded synapse can more than double its conductance**. That is a
  structural consequence of the Kunert threshold trick, not a parameter. It caps how much
  a motor neuron can swing its muscle, which caps the moment, which caps the regenerated
  bend. Worth testing by biasing the thresholds a few mV *above* rest so the resting
  release is lower and the upward range larger — at the cost of the network being less
  responsive to hyperpolarisation. This is the deepest of the hypotheses and the one I
  would try first.
- **H2 — proprioceptive input should be a conductance, not a current.** Real stretch
  receptors are ion channels; opening one moves the cell towards a reversal potential and
  never past it. Injecting current instead is why motor neurons hit the voltage rail under
  strong drive, and why the drive has to be tuned so carefully to avoid a static bend.
  Switching to a rectified excitatory conductance (`g ∝ relu(stretch)`, reversal 0 mV) is
  more faithful, self-limiting, removes the clamp entirely, and makes the dorsal/ventral
  pair genuinely alternate rather than push-pull through one shared signed current.
  Moderate work: `Senses.sense` returns a conductance vector, `NervousSystem.step` accepts
  it. Sketch already in `worm/senses.py`'s structure.
- **H3 — the muscle is still leak-dominated.** After the per-cell balance, NMJ conductance
  is 1.45 nS against a 2.2 nS leak. Lowering muscle `g_leak` (keeping `tau_m` sensible by
  also lowering `C_m`) would give the motor neurons more authority per unit release. Cheap
  to test: it is two numbers in `MuscleParams`.
- **H4 — 48 segments coupled through a dense drag metric is too stiff.** The mechanical
  coupling between neighbouring segments may be washing out the local reflex. Test by
  running at `n_links = 96` and seeing whether the reflex gain per unit *length* holds up.
- **H5 — the B-type receptive fields are too wide.** A reach of 0.20 L is 10 joints; each
  neuron averages over a fifth of the body, which low-passes the very spatial structure it
  is meant to propagate. Wen et al.'s 200 µm is a *dendrite length*, not necessarily a
  flat averaging window. Try a weighted kernel peaked at the near end.

### The prize

The slow attractor is still in there. Before the head stretch receptor was given its own
kinetics, the head loop had two limit cycles and the slow one sat at **0.31 Hz with a
0.70 L wavelength** — almost exactly the real crawling gait. It was only reachable from
about a third of random seeds, which is why the filter is there. If the body reflex gets
strong enough to dominate, that attractor should become the robust one and four of the
table's five rows fix themselves at once.

---

## Second tier

- **Gait modulation magnitude.** Its direction is fixed: the current scorecard goes
  0.66 Hz on agar to 0.85 Hz in buffer. The animal goes 0.30 to 1.76 Hz, so the remaining
  problem is the size of the response, not its sign. Keep it subordinate to turn depth;
  changing the shared gait can move every behavioural assay at once.
- **Backward locomotion.** The A-class wave reverses direction, but curvature and net speed
  remain poor after AVB is removed. This should not be cited as a working phenotype.
- **Taxis magnitude.** Chemotaxis, thermotaxis and aerotaxis have mechanisms pointing the
  right way but small outcomes. Re-run them after a turn-depth mechanism clears its own
  paired gate; do not tune the assays around the current shallow turn.

## Third tier / nice to have

- A recorded-playback mode in the viewer — the transport bar has no scrubber because there
  is no history buffer. A ring buffer of a few thousand frames would let the media-player
  metaphor actually be one.

### Done, and left here so the list stays honest about what moved

- ~~Pharyngeal pumping. The 20 pharyngeal neurons are simulated and drive nothing.~~
  **Done, day nineteen.** They drive a myogenic pump, the pump is what feeds the animal,
  and five ablation phenotypes come out of it. See `worm/pharynx.py`.
- ~~Multi-worm. The engine is one `Simulation` object; nothing prevents several.~~
  **Done with the WebAssembly port.** The connectome is read-only and shared, so a second
  animal duplicates only state -- 239,360 bytes of it, 234 kB, measured; the viewer runs n
  of them and focuses one. This is what makes the population direction at the top of this
  file thinkable, at the budget set out there.

---

## Things that will bite whoever picks this up

- **Know the resolution of the number you are comparing.** `tools/diagnose_loop.py` took the
  dominant frequency as a bare FFT `argmax`, so its resolution was `1/MEASURE` — 0.0333 Hz at
  a 30 s window — and **every frequency this project published before 2026-08-05 is an integer
  multiple of 1/30 Hz, or a three-seed mean of them.** Two ways that misleads. Seeds landing
  in one bin print `sd = 0.000`, which reads as perfect agreement and is the quantiser
  refusing to resolve them. And a conclusion can rest on a single bin without looking like it:
  "modulation saturates from K = 9 to K = 1.58" was 0.8444 → 0.8333, one bin in one seed. The
  peak is interpolated now, but the habit is the lesson — before comparing two measurements,
  ask what the smallest difference the instrument can express is.
- **`bare_world` was not gradient-free, and its docstring said it was.** `World.temperature`
  is an unconditional 17→25 °C ramp across the plate that no world construction disabled;
  `Senses` samples it at the nose every step and drives AFD from it. The tracking error is
  `tau * v * grad`, so it **scales with the animal's own speed** — 0.37 pA in buffer against
  2.10 pA on agar, next to 2.2 pA of noise. That is a confound pointed directly at every
  medium comparison in `tools/`, and it sat behind a docstring asserting the opposite. Fixed
  by flattening the ramp to `cultivation_temp`. The general form: a helper that promises a
  controlled condition is worth checking against the code that implements the condition.
- **A payload array may not be the shape you assume, and reading past it is silent.**
  `g_leak` and `E_leak` are network-wide scalars of shape `[1]`, not per-neuron arrays.
  Indexing an eight-byte array by neuron walks straight into whichever array the exporter
  laid down next and produces a plausible finite number for every cell. The first symptom
  was a zero pivot three hundred columns into an LU. Check `head['arrays'][name]['shape']`
  before writing `m(OFF_x, i)`, and note that the step functions already read both of these
  at index 0 — the existing code was right and the new code was not.
- **Choose the assertion that can detect the bug, not the one that is easy to write.** The
  scrubber's ring had to copy, because the engine hands out views into WASM memory. The
  first test compared node coordinates — but `frame(i)` already allocates a fresh centreline
  array, so nodes are copies whether or not the ring copies anything. Deleting the copy step
  entirely left every assertion passing. It asserts on `V` now. *Which* field a check reads
  is usually the whole check.
- **Order a sweep so that being cut short still answers something.** The first cascade sweep
  ordered its jobs stage-major, timed out with three quarters unrun, and had measured
  exactly one stage count — the single arrangement that answers nothing — under a table that
  looked populated. Seed-major means a truncated run holds every configuration at fewer
  seeds instead. And report `n` per row: a divergence left one row averaged over a single
  surviving seed, printed `+-0.000`, reading as the most precise row rather than the least
  supported.
- **A conserved quantity cannot measure the thing it is conserved under.** `laid + held`
  does not change when an egg is laid, so egg *production* is blind to the egg-laying
  circuit however long the assay runs. The measure looked integrative and was intake in
  different units. Before building a fitness function, ask what it is invariant to.
- **Do not edit the working tree while `tools/audit.py` is running.** It fingerprints the
  caller's checkout and exits 2 if it moves. That is the tool working; it still costs you
  the run.
- **Do not trust a single seed.** The gait was bistable across seeds until very late, and
  two thirds of seeds went the wrong way. `test_gait_is_reproducible_across_seeds` guards
  it now. Any change to the head loop should be checked against at least three seeds.
- **Do not add intrinsic oscillators to the motor neurons.** It was tried. Dorsal and
  ventral members have identical dynamics and are gap-coupled, so they phase-lock to each
  other, and the animal contracts both sides at once with a measured input correlation of
  0.97. The rhythm has to come from something dorsoventrally antisymmetric. See the long
  comment in `NeuralParams`.
- **Reference receptive fields to the muscles a neuron drives, not to its soma.** DB and VB
  somas are interleaved along the cord in a way that does not line up dorsoventrally.
  `_output_position` in `worm/senses.py` handles this; do not "simplify" it back.
- **The muscle balance step is load-bearing.** Without it the heavier ventral innervation
  in the connectome holds the worm in a permanent C. Without the *per-cell* version, head
  muscles rest on the flat end of their tension curve and go deaf.
- **Watch the summary statistics.** A lot of time went into inferring behaviour from
  frequency/wavelength numbers that were hiding a statically bent worm. `tools/kymo.py`
  prints an ASCII kymograph in a few seconds and would have caught it immediately. Look at
  the picture first.
- **The server's simulation thread must yield.** It holds the GIL through a batch of steps;
  without the small unconditional sleep, new WebSocket connections time out during the
  opening handshake. Already fixed, but it is the kind of thing that gets "optimised" back.

---

## Ready-to-run baseline before changing the turn

The former "first command" swept head proprioceptive gain inside the now-retired passive
wave plan. Do not use it as the next experiment. Before a three-dimensional turn branch
changes the model, freeze the current gait and reorientation baselines with:

```bash
PYTHONPATH=. .venv/bin/python tools/scorecard.py
PYTHONPATH=. .venv/bin/python tools/ethogram.py
```

After the change, use `tools/compare.py ethogram key=value` on identical seeds and require
both median reorientation and the fraction above 120 degrees to improve with cluster-level
paired intervals. Report net/path and absolute heading drift beside them. A result that
only improves the median, or makes the animal circle, is not a deeper turn.

## Useful commands

```bash
PYTHONPATH=. .venv/bin/python tools/kymo.py                 # look at the body, first
PYTHONPATH=. .venv/bin/python tools/diagnose_loop.py        # gait metrics
PYTHONPATH=. .venv/bin/python tools/command_probe.py        # can anything reach the decision?
PYTHONPATH=. .venv/bin/python tools/command_sweep.py        # ...and does the gait survive it
PYTHONPATH=. .venv/bin/python tools/ethogram.py             # reversal statistics, on food and off
PYTHONPATH=. .venv/bin/python tools/assays.py triage        # two minutes; run before the full assay
PYTHONPATH=. .venv/bin/python tools/reflex_gain.py --quick  # historical wave diagnostic; ratio needs care
PYTHONPATH=. .venv/bin/python tools/calibrate_body.py       # mechanics only, no biology
PYTHONPATH=. .venv/bin/python tools/head_mode.py            # which limit cycle, and why
PYTHONPATH=. .venv/bin/python tools/habituation.py          # the only memory in the model
PYTHONPATH=. .venv/bin/python tools/timestep_convergence.py # is the gait converged? (~4 min)
PYTHONPATH=. .venv/bin/python tools/head_circuit.py         # lumped vs spatially distributed
PYTHONPATH=. .venv/bin/python tools/head_cascade.py         # can stages in series pay for head_delay?
PYTHONPATH=. .venv/bin/python tools/audit.py --only <name>  # watch a check fail, in seconds
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q           # full regression suite
.venv/bin/python run.py --headless 60
npm run check                                               # every gate CI would run, locally
npm run check -- --rebuild                                  # ...including the artifact rebuilds
```

`npm run check` is the one to reach for before pushing while CI is paused. It runs the gates
in the workflows' own order and **reports what it skipped rather than counting a skip as a
pass**; `--strict` turns any skip into a non-zero exit.

Every tool takes `key=value` overrides for the parameters it cares about, e.g.
`tools/kymo.py pg=180 moment=3.0 medium=buffer`.

Closed-loop probes are CPU-heavy. Run sweeps in batches, do not overlap them with the test
suite, and report completed jobs rather than estimating success from a partial run.
