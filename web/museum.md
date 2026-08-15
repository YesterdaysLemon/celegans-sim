# The niche museum

A catalogue of the measured ways this reconstruction falls short of the animal, and the
niches those shortfalls open for anything evolving inside it. The charter is the owner's,
nearly verbatim: the second dish exists to show *the delightful ways the simulation falls
short and the fun niches which can be exploited for reproduction* — and a museum is the
right building for that, because these are not embarrassments to fix quietly. They are the
product. Every lineage that camps a defect has run an audit no test author thought to
write.

Three rules of accession, and they are the whole editorial policy:

1. **An exhibit must be measured.** A suspected hole is a to-do, not an exhibit. Numbers,
   seeds, and the instrument that produced them, or it does not go on the floor.
2. **An exhibit must be pinned.** Somewhere in the tree — a test, a tool's docstring, an
   issue — the measurement must be reproducible. The museum holds the guided tour, not the
   evidence.
3. **An exhibit is a statement about the reconstruction, never about the animal.** This
   whole building stands on Track B ground (`docs/project-architecture.md` §1). A worm
   that exploits `volume_per_pump` has discovered a fact about our arithmetic. *C. elegans*
   remains uninformed and unimplicated.

---

## Wing I — conversion factors: fitness the anatomy can mint

The oldest wing, and the reason the museum exists. A fitness measure with a unit
conversion in front of it can be farmed by moving the conversion, and nothing about
behaviour needs to change.

**I.1 — `volume_per_pump` ×10 buys 9.3× the food.** The founding exhibit (#37). Raise the
pharynx's volume-per-pump tenfold in the compiled constant, change nothing else, and
`food_eaten` multiplies by 9.3 while the trajectory stays identical to five significant
figures — drag ratio 1.000028, displacement ratio 0.999998. Nothing foraged better; a
coefficient got bigger. Pinned: `wasm/energy-fitness.test.mjs` ("the exploit is real under
`food_eaten`"), re-measured in `wasm/evolve.mjs`'s header on seeds 5/11/23.

**I.2 — subtracting a cost makes it *worse*.** The obvious fix — intake minus a locomotion
cost — widens the hole to 11–13× on the same three seeds, because the cost is constant
with respect to the pharynx and subtracting a constant from a multiplied quantity
multiplies the *difference*. The trap is instructive enough that `evolve.mjs` keeps the
measurement in its header. The working fix divides intake by `volume_per_pump` first
(`EVO_FITNESS=energy`): the exploit ratio then reads 0.85–0.90 — the sign flips, a mutant
pharynx becomes a *cost*. A budget only helps once both terms are in a currency the
anatomy cannot mint.

**I.3 — eggs are intake in different units, over any short assay.** `laid + held` is
conserved across a laying event, the uterus fills as a linear function of intake below
capacity, and the laying rate is 11.0 eggs/hour — 0.061 eggs in a 20 s assay. So the
scalar egg score is `EGGS_PER_FOOD × ingested` with the units changed, and every exploit
in this wing transfers to it whole. Pinned: `wasm/eggs-fitness.test.mjs`, which measures
the regime rather than asserting the measure is good. The arena (`wasm/arena.mjs`)
dissolves the degeneracy instead of patching it: no scalar anywhere, reproduction is the
whole eat → transport → lay → hatch chain or nothing, and a lineage that games intake but
never lays leaves nothing on the plate.

## Wing II — physics that fails politely

Failures that raise no exception, print no NaN, and return a finite number. The worst kind
of wrong answer: one shaped exactly like a right answer.

**II.1 — a negative bending modulus reports 1.38×10²⁰ mm of displacement.** Set `body.EI`
negative and the integrator does not blow up — it *diverges quietly*, and the animal
reports a finite, orderable displacement fourteen orders of magnitude past the dish (#38).
A fitness measure that reads displacement would select for it enthusiastically. Fences:
the gene list keeps mechanical properties unaddressable ("a mutant can be *bad at being a
worm* but it cannot stop being one" — `wasm/evolve.mjs`), and `checkInvariants` on the
runtime scores an animal that stops doing physics as zero rather than as well-travelled.

**II.2 — the bistability cliff at the muscle rate floor.** With the amine path's muscle
rate coefficient at 0.7 or above, the swim configuration has a *coexisting* broken mode:
a 0.17 Hz limit cycle sharing parameter space with the healthy gait, reached from some
initial conditions and not others — 2 of 3 seeds, fully settled, at the (1.30, 0.9)
configuration. Nothing errors; the animal just swims at a tenth speed forever. The shipped
coefficient of 0.5 is the measured 3/3-stable frontier, not a taste choice. Pinned:
`tools/amine_gait.py` (stability grid in the docstring).

**II.3 — the transient that impersonates a broken worm.** Not a model defect — a
*protocol* defect, exhibited because it cost this project a wrong conclusion for an
afternoon. With a 6 s dopamine integrator, a 6 s settle measures the transient: the K=3.54
locus row read 0.956±0.534 Hz — "broken, sometimes" — until the settle was extended past
three amine time-constants and the row collapsed to a healthy ±0.016. The rule earned
here: **any measurement downstream of a slow state settles ≥3τ or it is measuring the
transient.** Pinned: `tools/flambda_locus.py` and `tools/amine_gait.py` (both carry the
24 s settle with the disclosure comment).

**II.4 — the read past the end that impersonated physics, twice.** The body has 49 nodes
(48 links). Four files written in one sitting read 51, and the two out-of-bounds f64s
were heap-neighbour bytes decoding as ~10⁻³⁰⁶ — which is (0, 0) in world coordinates, so
every animal in the browser arena was drawn towing a line to the dish centre. The exhibit
is what happened *before* the screenshot caught it: a twin-worm test failed on the
garbage index, and the author wrote down a plausible mechanism ("co-located animals share
evolving fields and drift at denormal scale") that a later measurement refuted outright —
in-bounds, same-dish twins are bit-identical. The twin-engine "fix" worked *because
identical engines allocate identically and therefore contain identical garbage*, which is
the most polite failure in this wing: not only did the wrong read return a plausible
number, the wrong explanation survived its own regression test. Two morals, both cheap:
a coordinate at 10⁻³⁰⁶ is a read error, not a small number; and a causal story written
into a comment is a claim, which means it is measurable, which means measure it. Pinned:
the correction block in `wasm/metabolism.test.mjs`, and the 49s now carry comments at
every read site.

## Wing III — where the reconstruction falls short of the animal

The honest-gap wing: places where Track A knows it is not the animal, measured precisely
enough to say *how* it is not.

**III.1 — below K≈8, the body's dynamics cannot feel the medium.** The bending relaxation
time τ = c_n/(EI·k⁴) is the sensorimotor loop's only load-dependent time, and it
saturates: below drag ratio K≈8 (buffer is K=1.58) it carries no medium information at
all. The animal spans 0.30 Hz/0.65 L on agar to 1.76 Hz/1.54 L in buffer — a 13.9× span
in v = fλ; the passive loop alone cannot produce the low-K half of that chord, which is
why the amine load-sensing path exists (drag force `c×v` — slip — is the signal that
survives saturation). Pinned: `tools/loop_medium.py`, `worm/params.py` (`MediumParams`
docstring).

**III.2 — serotonin turning would fire backwards in liquid.** `serotonin_turning=0.6`
ships hot, tuned on agar, where suppressing turns on food is right. In buffer the same
term would *promote* dwell-shaped output in a medium where the animal thrashes — the sign
of the behaviour is medium-dependent and the coefficient is not. The serotonin arm of the
gait project is parked on exactly this. Pinned: `worm/params.py` (`ModulatorParams`
rationale).

**III.3 — the food/load confound: bare agar saturates dopamine.** The dopaminergic
neurons (CEP/ADE/PDE) transduce mechanical load through a saturating `F/(F+load_half)`,
and on bare agar at the working `load_gain` the transduction is already near ceiling — so
the *food* signal those same neurons carry in the real animal has nowhere to add. The
reconstruction currently cannot have basal slowing and load sensing be independently
honest at this operating point. Named as an adoption precondition in `NEXT.md`. Pinned:
`worm/params.py` (`SensoryParams` docstring).

## Wing IV — live specimens: what the dish has actually found

Exhibits from the arena, where the finders have no incentive to be polite. Everything here
carries the arena's own caveat — small population (cap 10), compressed incubation, and
until replication lands, *patterns, not findings*.

**IV.1 — the dish selects a stronger body reflex. A finding, five seeds deep.**
`sen_proprio_gain` ended above the wild-type 30.0 in every one of five independent
600-second dishes — 39.8, 33.9, 37.7, 33.6, 38.6 — no reversals, while `gate_bias` and
`food_gain` barely drifted. Five same-signed seeds is a one-sided sign test at
p = 1/32 = 0.031. No scorer anywhere in the loop: the plate economy did the selecting.
WHY remains open (stronger drive between depleting lawns is the boring story; a gain
interaction with the intake contest is the fun one) — the finding is *that* it selects,
about this reconstruction's fitness landscape and nothing else. Pinned:
`wasm/arena.mjs` header, per-seed tables in the run logs.

**IV.2 — laying shuts down in pulses as camped lawns run dry.** The plate is never
restocked, so a lineage that camps a lawn eats its own reproductive substrate: laying
halts, the lawn recovers nothing, and only the eggs already incubating carry the line
through. The plate economy is a real constraint, not scenery — and "camp harder" is a
niche with a built-in cliff. Same pin.

**IV.3 — fixation in 150 dish-seconds is drift moving fast, not selection moving fast.**
Dynasty F0 swept a 4-founder, cap-10 dish inside 150 s. At this population size, drift
fixes *something* quickly regardless of merit; which founder wins is nearly noise even
when which *allele* wins is not. Any cross-seed claim must be about gene values (IV.1's
shape), never about dynasty labels. Same pin — recorded so nobody reads dynasty sweeps as
fitness.

---

## Accession desk

To add an exhibit: measure it (seeds and instrument), pin it (test, tool docstring, or
issue), then file it here in the wing it belongs to, with the pin named. If it is a
fitness hole, say what currency the anatomy minted; if it is polite physics, say what
finite number it returns instead of failing; if it is a Track A gap, say what the animal
does that the reconstruction cannot. And if the arena found it first, credit the lineage
— they work cheap, and they never file the report themselves.
