/* The arena: an in-dish evolutionary arms race, on the runtime, with no scorer outside
 * the glass.
 *
 *     node wasm/arena.mjs
 *     ARENA_SECONDS=1800 ARENA_CAP=10 ARENA_MUT=0.10 node wasm/arena.mjs
 *
 * TRACK B, AND LOUDLY: evolved animals are not C. elegans, and nothing this file produces
 * is a claim about the animal (docs/project-architecture.md section 1). This is the
 * departure track's next tier -- where evolve.mjs scores individuals from outside the
 * dish and copies winners by hand, the arena closes the loop the runtime always carried
 * the parts for: an animal eats from a finite plate, fills its uterus from what it
 * actually transported, lays through the HSN/VC circuit, and the egg -- which has carried
 * a copy of its parent's genome since the day eggs became records rather than dots --
 * incubates where it was laid and hatches into a new animal. Reproduction is the whole
 * chain or nothing. There is no fitness scalar anywhere in this file, and that is the
 * point: eggs-fitness.test.mjs proves the scalar egg measure is intake in different units
 * over any short assay, and the arena dissolves that degeneracy instead of patching it --
 * a lineage that games intake but never lays leaves nothing on the plate.
 *
 * WHAT IS POLICY HERE, STATED AS POLICY. The runtime provides mechanism (layEgg,
 * hatchEgg, removeWorm) and this file owns the three decisions a dish cannot make:
 *
 *   * INCUBATION -- eggs hatch ARENA_INCUBATION seconds after laying. Real eggs take
 *     nine-plus hours; the default 60 s is compressed so population dynamics are
 *     observable in a sitting, and the compression is a policy knob, not biology.
 *   * MUTATION -- applied at hatch, which for asexual copy-inheritance is the same event
 *     as at meiosis: gaussian per gene, sigma ARENA_MUT scaled per gene, through the
 *     same clampGene every other Track B driver uses (one home for the envelope policy).
 *   * DEATH -- the plate has a carrying capacity, ARENA_CAP. When a hatch would exceed
 *     it, the animal with the least intake over the trailing window dies first:
 *     starvation by proxy, chosen because intake is the one resource the arms race is
 *     about, and stated as policy because the reference animal has no death at all.
 *
 * Founders are wild-type clones; everything after them is descent with modification
 * under competition for a plate that is never restocked. What to watch for is exactly
 * what NEXT.md warns evolution finds: niches. A lineage that stops swimming to camp the
 * lawn, a gate bias that turns circling into lawn-holding -- every exploit that shows up
 * here is a measured defect or degeneracy of the reconstruction, found by creatures with
 * no incentive to be polite about it. Log them; they are the product. The log has a
 * building now: docs/niche-museum.md, whose accession rules (measured, pinned, Track B)
 * are the bar an observation must clear before it is called an exhibit.
 *
 * THE FIRST FULL RUN (2026-08-14, defaults, seed 1, 600 dish-seconds): first hatches at
 * t = 90 s; dynasty F0 swept to fixation by t = 150 s; 124 born, 118 died, no eggs
 * dropped. And one gene moved directionally and stayed moved: sen_proprio_gain climbed
 * from the wild-type 30.0 to a stable 39.8 +- 3.3 by t = 450 s while gate_bias and
 * food_gain barely drifted -- the dish, with no scorer, selected a stronger body reflex.
 * WHY is a hypothesis, not a result (stronger drive between depleting lawns is the
 * obvious story; a gain interaction nobody has looked for is the interesting one), and
 * per the header above it is a fact about this reconstruction's fitness landscape, never
 * about the animal. Laying also shut down in pulses as camped lawns ran dry -- the plate
 * economy is a real constraint, not scenery. One run, one seed: patterns, not findings.
 */

import {
  engine, GENES, clampGene, scaleOf, rng, normalFrom, DT,
} from './evolve.mjs';

const env = (k, d) => (process.env[k] !== undefined ? Number(process.env[k]) : d);
const SECONDS = env('ARENA_SECONDS', 900);
const CAP = env('ARENA_CAP', 10);
const FOUNDERS = env('ARENA_FOUNDERS', 4);
const MUT = env('ARENA_MUT', 0.10);
/* Tier-two mutation: ARENA_WMUT is the lognormal sigma applied to ARENA_WMUT_N heritable
 * weights per hatch, picked uniformly over all 3,935 entries (chemical synapses, gap
 * junctions, raw muscle rows) so every locus carries the same per-hatch rate. 0 -- the
 * default -- is genes-only, byte-identical to the arena before tier two existed. The
 * runtime refuses sign flips and asymmetric gap junctions on its own (wasm/weights.test.mjs);
 * what is policy here is only rate and size. developWorm() after mutation is NOT optional:
 * a mutated graph under inherited thresholds is bookkeeping error, not phenotype.
 * Shakedown (2026-08-14, seed 7, WMUT=0.15 N=4, 240 s): 37 births, the whole population
 * weighted by t=180 s, no drops, no physics failures -- and the scalar-gene spreads ran
 * visibly wider than any genes-only run (proprio_gain +-6.6 against the usual +-3.3),
 * which is what mutated wiring underneath the same genes should do. First full run
 * (2026-08-14, seed 21, 600 s): the genes-only proprio_gain climb DID NOT APPEAR --
 * final 31.8 +- 2.8 against 39.8 (seed 1) and 33.9 (seed 2) without weight mutation.
 * Either wiring variance drowns the gene-level signal or selection moved into the
 * weights where these reports cannot see it; distinguishing those needs a weight-drift
 * readout, and one seed decides nothing. Patterns, not findings. */
const WMUT = env('ARENA_WMUT', 0.0);
const WMUT_N = env('ARENA_WMUT_N', 3);
/* Tier-four-within-the-chain: ARENA_MMUT is the lognormal sigma applied at hatch to the
 * twelve morphology control points (stiffness, width and muscle profiles along the
 * body; runtime clamps to [0.25, 4]; contracts in wasm/morphology.test.mjs). getMorph
 * returns 1.0 for a reference-shaped animal, so the first mutated generation steps off
 * the reference smoothly. Default off. Branching bodies are NOT here and will not be --
 * that is an engine rewrite, recorded as out of scope at the mechanism.
 *
 * Shakedown (2026-08-14, seed 31, MMUT=0.10 with METAB=0.1, 240 s): 57 births, the
 * whole population shaped by t=180 s, no drops, no physics failures, and the width and
 * stiffness means idled near 1.0 -- no directional pull in four minutes, which is what
 * an honest null looks like. Also the record's FIRST starvation death: one animal ran
 * its store to zero and died where it stood, in a dish that also culled 50 -- physiology
 * is now a minority death mode waiting for a poorer plate. */
const MMUT = env('ARENA_MMUT', 0.0);
/* The metabolic budget (runtime mechanism: setMetabolism / getEnergy / depositFood;
 * contracts in wasm/metabolism.test.mjs). ARENA_METAB is the store capacity in food
 * units; 0 -- the default -- is the old dish exactly: no fading, no starvation, death
 * only by the cull. With it on, death becomes PHYSIOLOGY: the store drains at a basal
 * rate (a full store lasts ARENA_METAB_T seconds idle) plus the body's real drag
 * dissipation (scaled so that drag power ARENA_METAB_WORKP matches the basal rate),
 * the muscles fade below ARENA_METAB_KNEE of capacity toward the ARENA_METAB_FLOOR,
 * and an animal whose store hits zero dies where it stands. Every constant is invented
 * for dish timescales -- calibration in the commit: a feeding animal banks ~1e-2
 * units/s against a default burn of ~8e-4/s, so eating sustains easily and idleness
 * kills in ~ARENA_METAB_T seconds.
 *
 * AND THE PLATE GETS THE BODY BACK. Any death -- starvation or cull -- deposits food
 * where the animal stopped: ARENA_CORPSE units for the body itself plus
 * ARENA_CORPSE_YIELD of whatever store was left, so a culled well-fed animal is a
 * richer find than a starved husk, which is as it should be. Deposits conserve food
 * exactly (the runtime returns what the plate took). A corpse has no attractant plume
 * -- findable by the local food sense, not smellable across the dish; the runtime
 * states that first-cut honestly at depositFood.
 *
 * Shakedown (2026-08-14, seed 13, METAB=0.1, 240 s): ZERO starvation deaths -- and that
 * is the observation, not a disappointment. Mean store dipped to 0.64 by t=90 and then
 * the dish drove it back to the cap and held it there, while proprio_gain jumped to
 * 44.5 +- 7.6 and food_gain to 14.0 -- higher and faster than any run without the
 * budget. Under an energy tax the plate did not select animals that die less; it
 * selected animals that eat hard enough for death to never arrive. One run, one seed,
 * compressed incubation: a pattern. What would make it a finding is replication, and a
 * dish poor enough (smaller lawns, lower METAB_T) that the tax actually bites. */
const METAB = env('ARENA_METAB', 0.0);
const METAB_T = env('ARENA_METAB_T', 240);
const METAB_WORKP = env('ARENA_METAB_WORKP', 2.0);
const METAB_FLOOR = env('ARENA_METAB_FLOOR', 0.25);
const METAB_KNEE = env('ARENA_METAB_KNEE', 0.35);
const METAB_HATCH = env('ARENA_METAB_HATCH', 0.6);   // hatchling starting fill fraction
const CORPSE = env('ARENA_CORPSE', METAB * 0.5);
const CORPSE_YIELD = env('ARENA_CORPSE_YIELD', 0.8);
const CORPSE_R = 0.8;                                // mm; roughly a curled body
const BASAL = METAB > 0 ? METAB / METAB_T : 0;
const WORKC = METAB > 0 ? BASAL / METAB_WORKP : 0;
const INCUBATION = env('ARENA_INCUBATION', 60);
const REPORT = env('ARENA_REPORT', 60);
const SEED = env('ARENA_SEED', 1);
const CHUNK = 0.5;                       // seconds of simulation per policy pass

const rand = rng(SEED);
const normal = normalFrom(rand);

const E = engine();
E.setNoise(1);

/* Three lawns, never restocked. The plate is the whole economy. */
E.addFood(-8.0, 5.0, 4.0, 1.0, 1.0, 9.0);
E.addFood(7.0, -4.0, 4.0, 1.0, 1.0, 9.0);
E.addFood(0.0, 9.0, 3.0, 1.0, 0.8, 8.0);

const founderOf = new Map();             // worm id -> founder index, for dynasty stats
const born = new Map();                  // worm id -> sim time of hatch/creation
const eatenAt = new Map();               // worm id -> intake at the last policy pass
let simT = 0.0;
let births = 0, deaths = 0, seedIota = 1000;

const metabolise = (id, fill) => {
  if (METAB > 0) E.setMetabolism(id, METAB, BASAL, WORKC, METAB_FLOOR, METAB_KNEE, fill);
};

for (let i = 0; i < FOUNDERS; i++) {
  const a = (2 * Math.PI * i) / FOUNDERS;
  const id = E.createWorm(SEED + i, 6.0 * Math.cos(a), 6.0 * Math.sin(a), a + Math.PI / 2);
  metabolise(id, 1.0);                      // founders arrive fed
  founderOf.set(id, i);
  born.set(id, 0.0);
  eatenAt.set(id, 0.0);
}

const ids = () => Array.from({ length: E.wormCount() }, (_, k) => E.wormIdAt(k));

/* Every death routes through here, so every death feeds the plate. The mid-body node is
 * where the animal stopped; the deposit is the body plus a yield on whatever store was
 * left. With metabolism off the corpse is CORPSE alone (default 0), and the dish is the
 * one it always was. */
function die(id) {
  if (CORPSE > 0 || METAB > 0) {
    const f64 = new Float64Array(E.memory.buffer);
    const x = f64[(E.ptrNodesX(id) >> 3) + 25], y = f64[(E.ptrNodesY(id) >> 3) + 25];
    const worth = CORPSE + (METAB > 0 ? CORPSE_YIELD * E.getEnergy(id) : 0);
    if (worth > 0) E.depositFood(x, y, CORPSE_R, worth);
  }
  E.removeWorm(id);
  founderOf.delete(id); born.delete(id); eatenAt.delete(id);
  deaths++;
}

function cullTo(cap) {
  while (E.wormCount() > cap) {
    let worstId = -1, worstIntake = Infinity;
    for (const id of ids()) {
      const recent = E.getEaten(id) - (eatenAt.get(id) ?? 0);
      if (recent < worstIntake) { worstIntake = recent; worstId = id; }
    }
    die(worstId);
  }
}

/* Death by physiology: a store at zero is a body that stopped. Distinguished in the
 * ledger because the two death modes mean different things -- starvation is the plate
 * economy speaking, the cull is the policy backstop. */
let starved = 0;
function reap() {
  if (METAB <= 0) return;
  for (const id of ids()) {
    if (E.getEnergy(id) <= 0.0) { die(id); starved++; }
  }
}

function hatchDue() {
  // Walk backwards: hatchEgg swap-pops the egg array.
  for (let i = E.eggCount() - 1; i >= 0; i--) {
    if (simT - E.eggTime(i) < INCUBATION) continue;
    const parent = E.eggParent(i);
    const id = E.hatchEgg(i, SEED + seedIota++, rand() * 2 * Math.PI);
    if (id < 0) continue;
    for (let s = 0; s < GENES.length; s++) {
      const v = E.getGene(id, s) + normal() * MUT * scaleOf(GENES[s]);
      E.setGene(id, s, clampGene(GENES[s], v));
    }
    if (WMUT > 0) {
      const counts = [E.weightCount(0), E.weightCount(1), E.weightCount(2)];
      const total = counts[0] + counts[1] + counts[2];
      for (let j = 0; j < WMUT_N; j++) {
        let k = Math.floor(rand() * total);
        let fam = 0;
        while (k >= counts[fam]) { k -= counts[fam]; fam++; }
        E.scaleWeight(id, fam, k, Math.exp(normal() * WMUT));
      }
      E.developWorm(id);
    }
    if (MMUT > 0) {
      const ctl = Array.from({ length: 12 }, (_, j) =>
        E.getMorph(id, j) * Math.exp(normal() * MMUT));
      E.setMorphology(id, ...ctl);
    }
    metabolise(id, METAB_HATCH);            // hatchlings start part-stocked: policy
    founderOf.set(id, founderOf.get(parent) ?? -1);   // -1: parent already culled
    born.set(id, simT);
    eatenAt.set(id, 0.0);
    births++;
    cullTo(CAP);
  }
}

function report() {
  const pop = ids();
  const dyn = new Map();
  for (const id of pop) {
    const f = founderOf.get(id) ?? -1;
    dyn.set(f, (dyn.get(f) ?? 0) + 1);
  }
  const dynasties = Array.from(dyn.entries()).sort((a, b) => b[1] - a[1])
    .map(([f, n]) => `${f < 0 ? 'orphan' : 'F' + f}:${n}`).join(' ');
  const spread = (slot) => {
    const vs = pop.map((id) => E.getGene(id, slot));
    const m = vs.reduce((a, b) => a + b, 0) / vs.length;
    const sd = Math.sqrt(vs.reduce((a, b) => a + (b - m) * (b - m), 0) / vs.length);
    return `${m.toFixed(3)}±${sd.toFixed(3)}`;
  };
  const watch = ['sen_proprio_gain', 'sen_gate_bias', 'sen_food_gain']
    .map((g) => [g, GENES.indexOf(g)]).filter(([, s]) => s >= 0);
  const carriers = WMUT > 0
    ? `  weighted ${pop.filter((id) => E.hasOwnWeights(id)).length}/${pop.length}` : '';
  const shaped = MMUT > 0
    ? `  shaped ${pop.filter((id) => E.hasOwnMorphology(id)).length}/${pop.length}`
      + `  width ${(pop.reduce((a, id) => a + (E.getMorph(id, 4) + E.getMorph(id, 5)
          + E.getMorph(id, 6) + E.getMorph(id, 7)) / 4, 0) / (pop.length || 1)).toFixed(2)}`
      + `  stiff ${(pop.reduce((a, id) => a + (E.getMorph(id, 0) + E.getMorph(id, 1)
          + E.getMorph(id, 2) + E.getMorph(id, 3)) / 4, 0) / (pop.length || 1)).toFixed(2)}`
    : '';
  let metab = '';
  if (METAB > 0 && pop.length) {
    const es = pop.map((id) => E.getEnergy(id) / METAB);
    const mean = es.reduce((a, b) => a + b, 0) / es.length;
    metab = `  energy ${mean.toFixed(2)} [${Math.min(...es).toFixed(2)}`
      + `..${Math.max(...es).toFixed(2)}]  starved ${starved}`;
  }
  console.log(`t=${simT.toFixed(0).padStart(5)}s  pop ${pop.length}  eggs ${E.eggCount()}`
    + `  births ${births}  deaths ${deaths}  dropped ${E.eggsDropped()}`
    + `  | ${dynasties}`
    + watch.map(([g, s]) => `  ${g.replace('sen_', '')} ${spread(s)}`).join('')
    + carriers + shaped + metab);
}

console.log(`ARENA -- ${FOUNDERS} founders, cap ${CAP}, ${SECONDS} s of dish time,`
  + ` incubation ${INCUBATION} s, mutation sigma ${MUT}, seed ${SEED}`);
console.log('Track B: nothing below is a claim about C. elegans.\n');

const t0 = Date.now();
let nextReport = REPORT;
while (simT < SECONDS) {
  E.stepAll(Math.round(CHUNK / DT));
  simT += CHUNK;
  reap();
  hatchDue();
  if (simT >= nextReport) {
    for (const id of ids()) eatenAt.set(id, E.getEaten(id));
    report();
    nextReport += REPORT;
  }
}

const wall = (Date.now() - t0) / 1000;
console.log(`\ndish closed after ${SECONDS} s simulated in ${wall.toFixed(0)} s of wall`
  + ` clock: ${births} born, ${deaths} died, ${E.eggCount()} eggs still waiting,`
  + ` population ${E.wormCount()}.`);
if (births === 0) {
  console.log('No lineage reproduced. Either the dish was too short for the laying rate'
    + ' (11 eggs/hour/animal), the plate starved everyone first, or reproduction is'
    + ' broken -- distinguish before believing anything else this printed.');
}
