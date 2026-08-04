/* Is `EVO_FITNESS=eggs` measuring reproduction, or measuring intake in different units?
 *
 *     node --test wasm/eggs-fitness.test.mjs
 *
 * #98 asked for reproduction to be scored on egg output, because egg output requires
 * eating, pharyngeal transport and the HSN/VC circuit all working as one chain, which makes
 * it a genuinely integrative measure. That argument is sound and this file is about the
 * conditions under which it is actually true of *this* implementation.
 *
 * Two facts decide it, and both are in the runtime rather than in an opinion.
 *
 *   * The uterus fills as `eglEggs += EGGS_PER_FOOD * ingestedDelta`, capped at
 *     UTERUS_CAPACITY. Below the cap, that is a linear function of intake and nothing else.
 *   * Laying removes one egg at a time behind a threshold and a refractory, at a measured
 *     11.0 eggs/hour -- which is 0.061 eggs in a 20 s assay.
 *
 * So over a short assay, with the cap far away and no laying, eggs produced is *exactly*
 * EGGS_PER_FOOD times ingested. Selecting on it would be selecting on intake with the units
 * changed: every exploit intake has, it has, and the egg-laying circuit contributes nothing
 * because nothing it does is reachable.
 *
 * That is not an argument against the measure. It is a statement about assay length, and it
 * is the sort of thing that is cheap to check and expensive to discover after a week of
 * selection runs. So this file does not assert that the measure is good; it measures which
 * regime the assay is in and asserts that the code is honest about it:
 *
 *   1. the normalisation actually divides -- a model without `egl_eggs_per_food` must fail
 *      loudly rather than silently scoring in egg units;
 *   2. the unearned starting fill is removed, so an animal that eats nothing scores zero
 *      rather than scoring EGGS_INITIAL;
 *   3. and the correlation against intake is reported, with the verdict stated, so nobody
 *      reads a number out of this measure without knowing whether it is a new measurement
 *      or a rescaled old one.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { assay, fitness, engine, seedPlate, DT, EGGS_PER_FOOD, EGGS_INITIAL,
         UTERUS_CAPACITY, VOLUME_PER_PUMP } from './evolve.mjs';

const SECONDS = 20;
const SEEDS = [5, 11, 23];

test('the unearned starting fill does not count as reproduction', () => {
  // An animal that has done nothing holds EGGS_INITIAL eggs, because the model starts it
  // stocked. Scoring that would give every individual the same free constant, and -- worse
  // -- would make a lineage that eats nothing look like a lineage that reproduced three
  // times.
  const idle = { laid: 0, held: EGGS_INITIAL, diverged: 0 };
  assert.equal(fitness(idle, { mode: 'eggs' }), 0,
    'an animal that has produced nothing scores something');

  const one = { laid: 0, held: EGGS_INITIAL + EGGS_PER_FOOD, diverged: 0 };
  assert.ok(Math.abs(fitness(one, { mode: 'eggs' }) - 1) < 1e-12,
    'one food unit turned into eggs should normalise back to one food unit');
});

test('a diverged animal scores nothing under the egg measure too', () => {
  const rec = { laid: 40, held: UTERUS_CAPACITY, diverged: 3 };
  assert.equal(fitness(rec, { mode: 'eggs' }), 0,
    'an animal that stopped doing physics scored for what it accumulated on the way out');
});

test('the normalisation is a division, not decoration', () => {
  const rec = { laid: 0, held: EGGS_INITIAL + 7, diverged: 0 };
  const plain = fitness(rec, { mode: 'eggs' });
  const doubled = fitness(rec, { mode: 'eggs', eggsPerFood: EGGS_PER_FOOD * 2 });
  assert.ok(Math.abs(doubled - plain / 2) < 1e-12,
    'doubling eggs_per_food did not halve the score, so the constant is not being divided '
    + 'out and a re-export could multiply this measure without the animal changing');
});

test('eggs produced against intake, across seeds', () => {
  const rows = [];
  const steps = Math.round(SECONDS / DT);
  for (const seed of SEEDS) {
    const E = engine();
    E.setNoise(1);
    const ids = seedPlate(E, 1, seed);
    const recs = assay(E, ids, steps);
    for (const r of recs) {
      rows.push({
        seed,
        laid: r.laid,
        held: r.held,
        produced: r.laid + r.held - EGGS_INITIAL,
        intake: r.ingested / VOLUME_PER_PUMP,
        eggsScore: fitness(r, { mode: 'eggs' }),
        eatenScore: fitness(r, { mode: 'eaten' }),
      });
    }
  }

  console.log('\n    seed |  laid |   held  | produced | intake (pump-vol) | eggs score');
  for (const r of rows) {
    console.log(`    ${String(r.seed).padStart(4)} | ${String(r.laid).padStart(5)} | `
      + `${r.held.toFixed(4).padStart(7)} | ${r.produced.toFixed(5).padStart(8)} | `
      + `${r.intake.toFixed(5).padStart(17)} | ${r.eggsScore.toFixed(5)}`);
  }

  const anyLaid = rows.some((r) => r.laid > 0);
  const capped = rows.some((r) => r.held >= UTERUS_CAPACITY - 1e-9);
  console.log(`\n    any animal laid an egg: ${anyLaid}`);
  console.log(`    any uterus reached capacity (${UTERUS_CAPACITY}): ${capped}`);

  /* The verdict, and getting it right took being wrong first.
   *
   * The obvious test is "did an animal lay?", on the reasoning that a measure of
   * reproduction must at least require reproduction to happen. Every animal here lays
   * exactly one egg in 20 s -- not the 0.061 the measured 11 eggs/hour implies, because the
   * uterus starts stocked at EGGS_INITIAL and the first lay does not wait to be earned.
   *
   * And it does not matter in the slightest, which is the finding. `laid + held` is
   * **conserved** across a laying event: laying decrements `eglEggs` and increments
   * `eglLaid` by the same one egg. So eggs *produced* is blind to laying by construction,
   * and the HSN/VC circuit -- the entire reason #98 wanted this measure -- cannot move it.
   * What moves it is `eglEggs += EGGS_PER_FOOD * ingestedDelta`, and nothing else.
   *
   * So the question is not whether an egg was laid, it is whether the score is anything
   * other than intake. Below the cap it is exactly EGGS_PER_FOOD * ingested, so the ratio
   * of score to intake is the same constant for every animal, and that is what to check.
   */
  const ratios = rows.map((r) => r.eggsScore / r.intake);
  const spread = (Math.max(...ratios) - Math.min(...ratios)) / Math.max(...ratios);
  console.log(`\n    score / intake per seed: ${ratios.map((x) => x.toExponential(6)).join(', ')}`);
  console.log(`    relative spread: ${spread.toExponential(3)}`);

  if (spread < 1e-6) {
    console.log(`\n    VERDICT: at ${SECONDS} s this measure is intake in different units.`);
    console.log('    Animals laid, and it changed nothing: laid + held is conserved across a');
    console.log('    laying event, so eggs produced is blind to the egg-laying circuit by');
    console.log('    construction and tracks feeding alone. Selecting on it is selecting on');
    console.log('    intake, and it inherits every exploit intake has (#37).');
    console.log('    It becomes a measure of reproduction only once the uterus caps, which');
    console.log(`    needs ${(UTERUS_CAPACITY - EGGS_INITIAL).toFixed(0)} eggs of headroom to fill -- a far longer assay -- or once`);
    console.log('    production is made to depend on laying having made room for it.');
  } else {
    console.log('\n    VERDICT: the score is not a fixed multiple of intake, so something');
    console.log('    other than feeding is moving it at this assay length. Worth reading.');
  }

  // Whichever regime, the identity the measure is built on has to hold, or the normalisation
  // is not doing what its comment says.
  for (const r of rows) {
    const foodUnits = r.produced / EGGS_PER_FOOD;
    const rel = Math.abs(foodUnits - r.eggsScore) / Math.max(1e-12, Math.abs(r.eggsScore));
    assert.ok(rel < 1e-9,
      `seed ${r.seed}: the normalised egg score and eggs-produced-per-food disagree`);
  }

  // Whatever the regime, the score has to be finite and non-negative or the selection loop
  // is sorting on nonsense.
  for (const r of rows) {
    assert.ok(Number.isFinite(r.eggsScore) && r.eggsScore >= 0,
      `seed ${r.seed} produced a score of ${r.eggsScore}`);
  }
});
