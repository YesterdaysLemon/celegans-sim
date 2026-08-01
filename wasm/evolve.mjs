/* Evolve the animal's behaviour, on the runtime, in the browser's own engine.
 *
 *     node wasm/evolve.mjs
 *     EVO_POP=16 EVO_GENERATIONS=10 EVO_SECONDS=40 node wasm/evolve.mjs
 *
 * NEXT.md argued that a population stopped being an architectural problem once the port
 * landed, and set out three tiers of heritability. This is tier one: the fifteen scalars
 * each `Worm` now carries, mutated and selected on how much the animal eats. It is
 * deliberately the cheap version -- asexual copy-with-mutation, selection from outside the
 * dish -- because the point of building it first was to find out whether the fitness
 * measure is any good, and that question does not need the honest version to answer.
 *
 * WHAT IS AND IS NOT SAFE TO EVOLVE, WHICH IS NOT AN ACCIDENT.
 *
 * NEXT.md's caution is that evolution finds bugs enthusiastically -- a way to gain food
 * without foraging, or a parameter that makes the integrator unstable in a profitable
 * direction. Both of those exist in this model *today*, and are measured:
 *
 *   * `volume_per_pump` x10 buys 5.6x the food at an identical pump count and unchanged
 *     speed; with `lumen_capacity` x10, 9.3x. It is a unit conversion sitting in front of
 *     the fitness measure (#37).
 *   * `body.EI` set negative gives an animal reporting 1.38e20 mm of displacement, finite,
 *     with no exception, warning or NaN (#38).
 *
 * Neither is reachable from here, and that is why the gene list was chosen the way it was:
 * every one of the fifteen is a sensory gain, a time constant or a decision threshold.
 * None of them is a conversion factor in front of intake, and none of them is a mechanical
 * property -- the bending modulus, the drag coefficients and the muscle balance are
 * anatomy, baked into the payload, and cannot be addressed by a gene at all. So a mutant
 * here can be *bad at being a worm* but it cannot stop being one.
 *
 * That is a property of the genome, not of this file, and it is worth restating whenever
 * the genome grows.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

const POP = Number(process.env.EVO_POP || 8);
const GENERATIONS = Number(process.env.EVO_GENERATIONS || 5);
const SECONDS = Number(process.env.EVO_SECONDS || 25);
const SIGMA = Number(process.env.EVO_SIGMA || 0.12);   // mutation size, in units of a gene's own scale
const SEED = Number(process.env.EVO_SEED || 1);

for (const [file, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(file))) {
    console.error(`Missing ${file}; generate it with: ${how}`);
    process.exit(2);
  }
}

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);
const compiled = new WebAssembly.Module(wasmBuf);
const GENES = head.genes || [];
if (!GENES.length) {
  console.error('this model declares no genes; export it from a tree that has them');
  process.exit(2);
}
const DT = head.scalars.dt;
const STEPS = Math.round(SECONDS / DT);

/* Mutation size, per gene.
 *
 * A single multiplicative kick is the obvious choice and it is wrong here for two reasons.
 * The genes span 0.04 (`gate_bias`) to 4000 (`repellent_d_gain`), so one relative step
 * means wildly different things; and `mod_serotonin_mod1` ships at exactly 0.0, which a
 * multiplicative operator can never move off. So each gene carries a scale, and a mutation
 * is an additive draw of `SIGMA * scale`.
 *
 * The scale is the shipped value where that is meaningful. Where it is not -- a gene at
 * zero, or one that is a fraction rather than a magnitude -- it is stated, with the reason.
 */
const SCALE = {
  // Ships at zero. params.py documents 0.30 as the adopted setting and 0.60 as past the
  // corner, so a tenth of that range is a sensible step to explore it with.
  mod_serotonin_mod1: 0.10,
  // A fraction, not a magnitude: 1.0 is always-ventral, 0.5 is the shipped bias.
  sen_omega_ventral_fraction: 0.15,
  // A difference between two activations, and small: the hysteresis it lives inside is
  // 0.09, so scaling by the value itself would step far too coarsely.
  sen_gate_bias: 0.02,
  sen_gate_hysteresis: 0.02,
};
/* Bounds. Loose on purpose -- the interesting answers are the ones nobody predicted, and a
 * tight box just returns the box. These stop a gene going somewhere *meaningless* rather
 * than somewhere surprising: a negative conductance gain is not a worse worm, it is a
 * sign error, and a ventral fraction above 1 is not a stronger bias, it is the same as 1.
 */
const BOUNDS = {
  sen_omega_ventral_fraction: [0.0, 1.0],
  sen_gate_hysteresis: [0.005, 0.5],   // zero is a latch with no window at all
  mod_serotonin_mod1: [0.0, 2.0],
};
const scaleOf = (name) => SCALE[name] ?? (Math.abs(head.scalars[name]) || 1.0);
const clampGene = (name, v) => {
  const b = BOUNDS[name];
  if (b) return Math.min(b[1], Math.max(b[0], v));
  // Everything else is a gain or a drive. Negative would invert a pathway rather than
  // weaken it, which is a different animal rather than a worse one.
  return name === 'sen_gate_bias' ? v : Math.max(0.0, v);
};

/* A seeded PRNG, so a run is reproducible from EVO_SEED. Math.random would make every
 * result a story rather than a measurement. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = rng(SEED);
const normal = () => {                     // Box-Muller
  const u = Math.max(rand(), 1e-12), v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};

function engine() {
  const E = new WebAssembly.Instance(compiled, {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  return E;
}

/* Every animal gets its own lawn, and starts on it, off-centre.
 *
 * Not a shared plate, deliberately. Feeding is order-dependent while several animals draw
 * on the same cells -- worm 0 samples a full neighbourhood and worm 3 samples what three
 * others have been served from, a systematic 0.09% per four seconds in array order (#32).
 * That is small against a real genetic difference and it is not small against nothing, and
 * a first run should not have to argue about which it is measuring.
 *
 * ON the lawn, and this is the part worth reading, because the obvious design does not
 * work. Dropping an animal *outside* its lawn would make the score integrative in the way
 * NEXT.md wants -- find the food, stay on it, pump -- and it produces no score at all.
 * Measured, one lawn of radius 4 mm, three seeds, 30 s:
 *
 *     dropped at   found food   mean eaten
 *         0 mm        3/3         0.09395
 *         3 mm        3/3         0.03762
 *         5 mm        0/3         0.00000      <- 1 mm outside the edge
 *         7 mm        0/3         0.00000
 *
 * The landscape is *flat* off the lawn: every genome scores exactly zero, so there is
 * nothing for selection to act on. That is not a defect in this file, it is the model's
 * own chemotaxis showing through -- README puts the index at +0.083 against an animal's
 * +0.5 or better, and an animal that cannot climb a gradient cannot be selected for
 * climbing one. Until that improves, foraging-from-scratch is not an evolvable trait here,
 * and pretending otherwise would produce a run full of zeros and a conclusion about
 * nothing.
 *
 * So the assay selects for what *does* vary: staying on food and feeding well. An animal
 * dropped 3 mm off centre eats less than half what one dropped at the centre does, so
 * there is a real gradient in how well an animal holds a lawn once it is on one.
 */
const RING = 26.0;         // mm between neighbouring lawns -- far past any interaction
const OFFSET = 3.0;        // mm off the lawn's centre; the lawn's radius is 4
function plate(E, n) {
  const spots = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const lx = Math.cos(a) * RING, ly = Math.sin(a) * RING;
    E.addFood(lx, ly, 4.0, 1.0, 1.0, 9.0);
    // Off-centre and pointing outwards, so an animal that simply swims straight ahead
    // leaves the lawn. Holding station is a behaviour, and this is what scores it.
    spots.push([lx + Math.cos(a) * OFFSET, ly + Math.sin(a) * OFFSET, a]);
  }
  return spots;
}

function evaluate(genomes) {
  const E = engine();
  E.setNoise(1);                       // real animals; the genome is what we are comparing
  const spots = plate(E, genomes.length);
  const ids = genomes.map((g, i) => {
    const id = E.createWorm(1000 + i * 7717 + SEED * 131, ...spots[i]);
    g.forEach((v, s) => E.setGene(id, s, v));
    return id;
  });
  E.stepAll(STEPS);
  return ids.map((id, i) => ({
    eaten: E.getEaten(id),
    laid: E.getEggsLaid(id),
    // Distance from where it was dropped: an animal that never found its lawn should be
    // visible as such rather than only as a low score.
    moved: Math.hypot(E.getX(id) - spots[i][0], E.getY(id) - spots[i][1]),
  }));
}

const wild = GENES.map((n) => head.scalars[n]);
const mutate = (g) => g.map((v, s) => clampGene(GENES[s], v + normal() * SIGMA * scaleOf(GENES[s])));

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

console.log(`EVOLUTION -- ${POP} animals, ${GENERATIONS} generations, ${SECONDS} s each, `
          + `sigma ${SIGMA}, seed ${SEED}`);
console.log(`  ${GENES.length} genes, fitness = food eaten, each animal on its own lawn\n`);
console.log('  gen |   best    median      mean | ate anything | wall');

// Generation zero is the wild type plus a first round of mutation, so there is variation
// to select on at all -- a population of clones has nothing for selection to act on and
// the first generation would be pure noise.
let population = Array.from({ length: POP }, (_, i) => (i === 0 ? wild.slice() : mutate(wild)));
const history = [];
const t0 = Date.now();

for (let gen = 0; gen < GENERATIONS; gen++) {
  const started = Date.now();
  const scored = evaluate(population).map((r, i) => ({ ...r, genome: population[i] }));
  scored.sort((a, b) => b.eaten - a.eaten);
  const eaten = scored.map((s) => s.eaten);
  const fed = scored.filter((s) => s.eaten > 0).length;
  history.push({ gen, best: eaten[0], median: median(eaten), mean: mean(eaten),
                 genome: scored[0].genome.slice(),
                 means: GENES.map((_, s) => mean(scored.map((x) => x.genome[s]))) });
  console.log(`  ${String(gen).padStart(3)} | ${eaten[0].toFixed(5)}  ${median(eaten).toFixed(5)}  `
            + `${mean(eaten).toFixed(5)} |    ${String(fed).padStart(2)} of ${POP}     `
            + `| ${((Date.now() - started) / 1000).toFixed(0)}s`);

  // Truncation selection: the better half breed, each producing two mutated offspring, and
  // the single best is carried over unchanged so a good genome cannot be lost to a bad
  // draw. Selection lives entirely out here -- the runtime provides mechanism, not policy.
  const parents = scored.slice(0, Math.max(2, Math.floor(POP / 2)));
  const next = [parents[0].genome.slice()];
  while (next.length < POP) next.push(mutate(parents[next.length % parents.length].genome));
  population = next;
}

const first = history[0], last = history[history.length - 1];
console.log(`\n  best fitness ${first.best.toFixed(5)} -> ${last.best.toFixed(5)}`
          + `   (x${(last.best / (first.best || 1e-9)).toFixed(2)})`);
console.log(`  median       ${first.median.toFixed(5)} -> ${last.median.toFixed(5)}`);
console.log(`  wall clock   ${((Date.now() - t0) / 1000).toFixed(0)} s\n`);

console.log('  gene                            wild      gen0 mean   final mean    moved');
for (let s = 0; s < GENES.length; s++) {
  const w = wild[s], a = first.means[s], b = last.means[s];
  const rel = Math.abs(w) > 1e-12 ? (b - w) / Math.abs(w) : b - a;
  const flag = Math.abs(rel) > 0.15 ? '  <--' : '';
  console.log(`  ${GENES[s].padEnd(30)} ${w.toFixed(4).padStart(9)} ${a.toFixed(4).padStart(11)}`
            + ` ${b.toFixed(4).padStart(12)} ${(rel * 100).toFixed(1).padStart(8)}%${flag}`);
}

/* A drift arrow is not evidence of selection.
 *
 * With a population this small, a gene under no selection at all still wanders -- the
 * survivors are a handful of animals and their genomes are correlated by descent. The
 * honest reading of the table above is that a marked gene is a *candidate*, to be confirmed
 * by re-running at another seed and seeing whether it moves the same way. Anything that
 * does not survive that is drift, and saying so here is cheaper than believing it later.
 */
console.log('\n  Arrows mark genes that moved more than 15%. With a population this small a');
console.log('  gene under no selection still drifts, so treat them as candidates and');
console.log('  re-run at another EVO_SEED before believing any of them.');
