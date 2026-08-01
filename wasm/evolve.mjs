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
function normalFrom(rand) {                // Box-Muller
  return () => {
    const u = Math.max(rand(), 1e-12), v = rand();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
}

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

function evaluate(genomes, seed) {
  const E = engine();
  E.setNoise(1);                       // real animals; the genome is what we are comparing
  const spots = plate(E, genomes.length);
  const ids = genomes.map((g, i) => {
    const id = E.createWorm(1000 + i * 7717 + seed * 131, ...spots[i]);
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
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const sd = (xs) => {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
};

/* One experiment: a population, N generations, selection either on or off.
 *
 * `select` is the only thing that differs between the two arms, and everything else is
 * held identical -- same environment seed, same worm seeds, same mutation stream from the
 * same PRNG seed, same starting population. That is common random numbers, and it is the
 * whole reason a difference between the arms means anything: animal-to-animal variance is
 * most of the variance here, and pairing cancels it. tools/compare.py does the same for the
 * behavioural assays, for the same reason.
 */
function runArm(seed, select, log) {
  const rand = rng(seed);
  const normal = normalFrom(rand);
  const mutate = (g) => g.map((v, s) => clampGene(GENES[s], v + normal() * SIGMA * scaleOf(GENES[s])));
  let population = Array.from({ length: POP }, (_, i) => (i === 0 ? wild.slice() : mutate(wild)));
  const history = [];
  for (let gen = 0; gen < GENERATIONS; gen++) {
    const scored = evaluate(population, seed).map((r, i) => ({ ...r, genome: population[i] }));
    scored.sort((a, b) => b.eaten - a.eaten);
    const eaten = scored.map((x) => x.eaten);
    history.push({ best: eaten[0], median: median(eaten), mean: mean(eaten),
                   means: GENES.map((_, s) => mean(scored.map((x) => x.genome[s]))) });
    if (log) {
      console.log(`  ${log} seed ${seed} gen ${gen}: best ${eaten[0].toFixed(5)} `
                + `median ${median(eaten).toFixed(5)}`);
    }
    /* Truncation selection, or the control.
     *
     * The control breeds from parents drawn uniformly at random -- the same number of
     * offspring, the same mutation operator, the same everything, chosen without reference
     * to fitness. A rising median in the selected arm means nothing until it beats this,
     * because a population whose worst members are replaced by *anything* drifts upward
     * when the measure is noisy and the survivors are resampled.
     */
    const pool = select
      ? scored.slice(0, Math.max(2, Math.floor(POP / 2)))
      : Array.from({ length: Math.max(2, Math.floor(POP / 2)) },
                   () => scored[Math.floor(rand() * scored.length)]);
    const next = [pool[0].genome.slice()];
    while (next.length < POP) next.push(mutate(pool[next.length % pool.length].genome));
    population = next;
  }
  return history;
}

const SEEDS = (process.env.EVO_SEEDS || String(SEED)).split(',').map(Number);
const CONTROL = process.env.EVO_CONTROL !== '0';

console.log(`EVOLUTION -- ${POP} animals, ${GENERATIONS} generations, ${SECONDS} s each, `
          + `sigma ${SIGMA}`);
console.log(`  ${GENES.length} genes, fitness = food eaten, each animal on its own lawn`);
console.log(`  seeds ${SEEDS.join(', ')}${CONTROL ? ', with a selection-off control arm' : ''}\n`);

const t0 = Date.now();
const runs = [];
for (const seed of SEEDS) {
  const sel = runArm(seed, true, 'select ');
  const ctl = CONTROL ? runArm(seed, false, 'control') : null;
  runs.push({ seed, sel, ctl });
}

/* The paired comparison, which is the only part of this worth quoting.
 *
 * Per seed: how much the median moved from the first generation to the last, in the
 * selected arm and in the control. The difference of those two is the effect of selection
 * on that seed, with the environment held identical. Reported as a spread over seeds
 * rather than a single number, because one run is one sample -- this project learned that
 * on day eighteen, when a four-seed result that "reads as a clear win" turned out to have
 * every interval overlapping every other.
 */
const gain = (h) => h[h.length - 1].median - h[0].median;
console.log('\n  seed |  selected gain |  control gain |  difference');
const diffs = [];
for (const r of runs) {
  const g = gain(r.sel);
  if (r.ctl) {
    const c = gain(r.ctl);
    diffs.push(g - c);
    console.log(`  ${String(r.seed).padStart(4)} | ${g.toFixed(5).padStart(14)} `
              + `| ${c.toFixed(5).padStart(13)} | ${(g - c).toFixed(5).padStart(11)}`);
  } else {
    console.log(`  ${String(r.seed).padStart(4)} | ${g.toFixed(5).padStart(14)} |            -- |          --`);
  }
}

if (diffs.length) {
  const m = mean(diffs), s = sd(diffs);
  // A standard error, not a bootstrap: with a handful of seeds the point is the order of
  // magnitude of the spread against the effect, not a calibrated interval.
  const se = diffs.length > 1 ? s / Math.sqrt(diffs.length) : NaN;
  console.log(`\n  selection - control, over ${diffs.length} seed(s): `
            + `${m.toFixed(5)} +- ${Number.isNaN(se) ? '?' : se.toFixed(5)} (s.e.)`);
  const clears = diffs.length > 1 && Math.abs(m) > 2 * se;
  console.log(clears
    ? '  The difference clears twice its own standard error. That is worth following up.'
    : '  The difference does NOT clear twice its own standard error: this run shows no\n'
      + '  detectable effect of selection. More seeds, more generations, or a fitness\n'
      + '  measure with more dynamic range -- not a louder reading of this one.');
}

console.log(`\n  wall clock ${((Date.now() - t0) / 1000).toFixed(0)} s`);
console.log('\n  gene                            wild   selected mean   control mean');
for (let s = 0; s < GENES.length; s++) {
  const selMean = mean(runs.map((r) => r.sel[r.sel.length - 1].means[s]));
  const ctlMean = runs[0].ctl ? mean(runs.map((r) => r.ctl[r.ctl.length - 1].means[s])) : NaN;
  console.log(`  ${GENES[s].padEnd(30)} ${wild[s].toFixed(4).padStart(9)}`
            + ` ${selMean.toFixed(4).padStart(14)} ${(Number.isNaN(ctlMean) ? '--' : ctlMean.toFixed(4)).padStart(14)}`);
}
console.log('\n  A gene is only interesting where the selected column differs from the control');
console.log('  column by more than the columns differ from each other across seeds.');
