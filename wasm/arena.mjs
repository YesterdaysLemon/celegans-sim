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
 * no incentive to be polite about it. Log them; they are the product.
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

for (let i = 0; i < FOUNDERS; i++) {
  const a = (2 * Math.PI * i) / FOUNDERS;
  const id = E.createWorm(SEED + i, 6.0 * Math.cos(a), 6.0 * Math.sin(a), a + Math.PI / 2);
  founderOf.set(id, i);
  born.set(id, 0.0);
  eatenAt.set(id, 0.0);
}

const ids = () => Array.from({ length: E.wormCount() }, (_, k) => E.wormIdAt(k));

function cullTo(cap) {
  while (E.wormCount() > cap) {
    let worstId = -1, worstIntake = Infinity;
    for (const id of ids()) {
      const recent = E.getEaten(id) - (eatenAt.get(id) ?? 0);
      if (recent < worstIntake) { worstIntake = recent; worstId = id; }
    }
    E.removeWorm(worstId);
    founderOf.delete(worstId); born.delete(worstId); eatenAt.delete(worstId);
    deaths++;
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
  console.log(`t=${simT.toFixed(0).padStart(5)}s  pop ${pop.length}  eggs ${E.eggCount()}`
    + `  births ${births}  deaths ${deaths}  dropped ${E.eggsDropped()}`
    + `  | ${dynasties}`
    + watch.map(([g, s]) => `  ${g.replace('sen_', '')} ${spread(s)}`).join(''));
}

console.log(`ARENA -- ${FOUNDERS} founders, cap ${CAP}, ${SECONDS} s of dish time,`
  + ` incubation ${INCUBATION} s, mutation sigma ${MUT}, seed ${SEED}`);
console.log('Track B: nothing below is a claim about C. elegans.\n');

const t0 = Date.now();
let nextReport = REPORT;
while (simT < SECONDS) {
  E.stepAll(Math.round(CHUNK / DT));
  simT += CHUNK;
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
