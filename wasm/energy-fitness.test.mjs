/* The regression property #37 asked for: a bigger pharynx must not buy fitness.
 *
 *     node --test wasm/energy-fitness.test.mjs
 *
 * #37 measured `food_eaten` multiplying by 9.3x when `volume_per_pump` was raised tenfold,
 * with the animal foraging fractionally *worse*, and asked for a check shaped like this:
 *
 *     "mutating `volume_per_pump` alone must not move fitness by more than it moves
 *      foraging behaviour. That is a property, not a number, and it would have caught
 *      this."
 *
 * WHY THIS TEST HAS TO PATCH A COMPILED CONSTANT.
 *
 * `volume_per_pump` is deliberately not a gene. `tools/export_model.py` says why, in the
 * comment above `GENES`: "It must not be a unit conversion sitting in front of the fitness
 * measure ... They are deliberately absent." So there is no `setGene` slot to turn, and
 * there is no payload field either -- the exporter writes it into the *header*, and the
 * runtime reads its own compiled copy from `wasm/assembly/model_gen.ts`. The property
 * therefore cannot be tested through the genome; it has to be tested against a runtime
 * whose constant is different.
 *
 * Rebuilding the runtime with a different constant would mean editing
 * `wasm/assembly/model_gen.ts` and `web/worm.wasm`, so instead this patches the `f64.const`
 * in an in-memory copy of the module bytes. `0.005` appears exactly once in the compiled
 * runtime, preceded by opcode 0x44, and `assertOneSite` fails loudly rather than guessing
 * if that ever stops being true. Patching the compiled constant stands in for editing
 * `worm/params.py` and re-exporting -- which is exactly why `fitness` is told the patched
 * value: a real re-export moves the header and the compiled constant together.
 *
 * WHAT IS ASSERTED, AND WHAT IS NOT.
 *
 * The literal reading of #37's sentence -- fitness moves no more, in relative terms, than
 * behaviour does -- is not achievable and this test does not pretend to check it. Measured
 * below: behaviour moves by 5e-5 while `energy` fitness moves by 9 to 46%. That residual is
 * not the unit conversion surviving. It is lumen saturation: a pump ten times larger leaves
 * the lumen ten times fuller at the next pump and captures a smaller fraction of what it
 * asks for. `the residual is lumen saturation, not the conversion` isolates that by scaling
 * `lumen_capacity` alongside, which restores specific intake to within 1% on every seed --
 * and that control is the closest thing to #37's literal property that this model admits.
 *
 * What is asserted is stronger than #37's inequality in the direction that matters and
 * weaker in the other: **the mutation must never buy fitness at all**. A direction that
 * loses fitness is not a direction a search follows, which is the failure #37 opened with
 * ("generation one of any search finds this, and after that the run is over").
 *
 * GUARDS AGAINST THIS PASSING FOR THE WRONG REASON. Every one of these has been watched to
 * fail, by mutating the thing it covers:
 *
 *   * `the exploit is real under food_eaten` -- if the byte patch silently did nothing,
 *     every other assertion here would pass on two identical runs. This one would not.
 *   * `the normalisation is what closes it` -- runs the same records through the same
 *     `fitness` with the *shipped* volume_per_pump, i.e. an energy budget over a raw
 *     intake total, and requires it to still show the exploit. Without this, a `fitness`
 *     that ignored its arguments would pass.
 *   * `neither half of the budget is trivial` -- a fitness of zero, an intake of zero, or a
 *     lambda of zero would make the ratio assertions meaningless or NaN.
 *   * `chunking the run does not change the trajectory` -- the drag proxy is built by
 *     stopping `stepAll` every 0.01 s to read the head position, which is only legitimate
 *     because `stepAll` carries no state between calls. That is an assumption about
 *     `wasm/assembly/index.ts`, so it is checked rather than believed.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { assay, engine, fitness, seedPlate, VOLUME_PER_PUMP } from './evolve.mjs';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const wasmBuf = fs.readFileSync(path.join(ROOT, 'web', 'worm.wasm'));
const modelBuf = fs.readFileSync(path.join(ROOT, 'web', 'worm.model'));
const headView = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const head = JSON.parse(new TextDecoder().decode(
  modelBuf.subarray(12, 12 + headView.getUint32(8, true))));
const DT = head.scalars.dt;

const SECONDS = Number(process.env.FITNESS_TEST_SECONDS || 10);
const STEPS = Math.round(SECONDS / DT);
const SEEDS = [5, 42];          // 5 is typical; 42 is the worst residual of six sampled
const LAMBDA = 0.1;             // evolve.mjs's default, pinned here so the numbers below hold
const FACTOR = 10;              // #37's mutation

/* Every `f64.const <value>` in the module, as byte offsets of the opcode. */
function constSites(buf, value) {
  const needle = Buffer.alloc(9);
  needle[0] = 0x44;                       // wasm f64.const
  needle.writeDoubleLE(value, 1);
  const out = [];
  for (let i = 0; i + 9 <= buf.length; i++) {
    if (buf.compare(needle, 0, 9, i, i + 9) === 0) out.push(i);
  }
  return out;
}

function assertOneSite(value, name) {
  const sites = constSites(wasmBuf, value);
  assert.equal(sites.length, 1,
    `expected exactly one f64.const ${value} in web/worm.wasm for ${name}, found `
    + `${sites.length} at ${JSON.stringify(sites)}. This test varies ${name} by patching `
    + `that constant, because it is not a gene and not in the payload -- see the header. `
    + `Zero sites means the constant changed or was folded away; more than one means the `
    + `patch could hit something else, and a test that patched the wrong constant would `
    + `pass by measuring nothing. Neither is safe to guess through.`);
  return sites[0];
}

const VPP_SITE = assertOneSite(head.scalars.ph_volume_per_pump, 'volume_per_pump');

/* `lumen_capacity` shares its value (0.05) with two other constants -- `MUS_C_NF` and
 * `PH_M4_TRANSPORT` -- so it cannot be picked by value alone. It is chosen as the site
 * nearest the `volume_per_pump` one, because the two sit in the same expression in
 * `Worm._fire`: `room` is computed from the lumen capacity on the line above the line that
 * multiplies by the pump volume. That is an inference about codegen, so nothing rests on
 * it being right: the only test that uses this site asserts an effect that *only*
 * `lumen_capacity` produces, and would fail rather than mislead on a wrong pick. */
function nearestSite(value, anchor) {
  const sites = constSites(wasmBuf, value);
  assert.ok(sites.length > 0, `no f64.const ${value} in web/worm.wasm`);
  return sites.reduce((a, b) => (Math.abs(b - anchor) < Math.abs(a - anchor) ? b : a));
}
const LUMEN_SITE = nearestSite(head.scalars.ph_lumen_capacity, VPP_SITE);

function patchedModule(edits) {
  const buf = Buffer.from(wasmBuf);
  for (const [site, value] of edits) buf.writeDoubleLE(value, site + 1);
  return new WebAssembly.Module(buf);
}

const MODULES = {
  wild: new WebAssembly.Module(wasmBuf),
  vpp: patchedModule([[VPP_SITE, head.scalars.ph_volume_per_pump * FACTOR]]),
  vppAndLumen: patchedModule([[VPP_SITE, head.scalars.ph_volume_per_pump * FACTOR],
                              [LUMEN_SITE, head.scalars.ph_lumen_capacity * FACTOR]]),
};

/* One animal, on evolve.mjs's own assay, under a given build of the runtime. Identical in
 * every respect except the compiled constant -- same drop point, same heading, same worm
 * seed, same noise -- so any difference in the record is the constant and nothing else. */
function record(module, seed) {
  const E = engine(module);
  E.setNoise(1);
  const ids = seedPlate(E, 1, seed);
  return assay(E, ids, STEPS)[0];
}

const cache = new Map();
function runs(which) {
  if (!cache.has(which)) cache.set(which, SEEDS.map((s) => record(MODULES[which], s)));
  return cache.get(which);
}

const score = (rec, vpp) =>
  fitness(rec, { mode: 'energy', volumePerPump: vpp, lambda: LAMBDA });
const VPP = head.scalars.ph_volume_per_pump;

// ------------------------------------------------------------------ the assumption used
test('chunking the run does not change the trajectory', () => {
  // The drag proxy stops `stepAll` every 0.01 s to read the head. That is only sound
  // because `stepAll(n)` is a bare loop over single steps with nothing carried between
  // calls. If that ever stops being true, every drag number in evolve.mjs silently becomes
  // a number from a different simulation than the intake it is subtracted from.
  // 4000 steps is 2 s, which is long enough to contain several pumps. 400 was the first
  // attempt and it eats nothing at all -- the equalities below all held on two runs that
  // had not yet done anything, which is precisely the shape of pass this file exists to
  // refuse. The "actually happened" assertions at the end caught it.
  const TOTAL = 4000, FIRST = 1373;
  const whole = engine();
  whole.setNoise(1);
  const a = seedPlate(whole, 1, SEEDS[0])[0];
  const dropX = whole.getX(a), dropY = whole.getY(a);
  whole.stepAll(TOTAL);

  const split = engine();
  split.setNoise(1);
  const b = seedPlate(split, 1, SEEDS[0])[0];
  split.stepAll(FIRST);
  split.stepAll(TOTAL - FIRST);

  assert.equal(whole.getX(a), split.getX(b), 'stepAll is not chunk-invariant in x');
  assert.equal(whole.getY(a), split.getY(b), 'stepAll is not chunk-invariant in y');
  assert.equal(whole.getEaten(a), split.getEaten(b),
    'stepAll is not chunk-invariant in food eaten');
  // ...and both runs actually did something, or the three equalities above compared the
  // state the animal was created in against itself and would hold for any implementation
  // of `stepAll`, including one that did nothing.
  // 0.01 mm, against a measured 0.0848 mm: two seconds is early in the run and the animal
  // is still building up its undulation, so the bar is "it is not standing exactly where
  // it was dropped" rather than "it has got anywhere".
  const went = Math.hypot(whole.getX(a) - dropX, whole.getY(a) - dropY);
  assert.ok(went > 0.01,
    `the animal moved ${went} mm in ${TOTAL} steps, so the position equalities above `
    + `compared the drop point to itself`);
  assert.ok(whole.getEaten(a) > 0,
    `nothing was eaten in ${TOTAL} steps, so the food equality above compared nothing`);
});

/* A stand-in for the runtime that replays a scripted head trajectory.
 *
 * `assay` reads the head through `getX`/`getY` and advances through `stepAll`, and nothing
 * else about the engine reaches the drag proxy, so a fake one pins the arithmetic exactly
 * -- against a trajectory whose integral can be worked out on paper -- without simulating
 * anything. `dt` and `sampleDt` are set to 1.0 so one `stepAll` is one sample of unit
 * duration and the sums below are readable.
 */
function scripted(points) {
  let k = 0;
  return {
    getX: () => points[k][0],
    getY: () => points[k][1],
    stepAll: (n) => { k += n; },
    // Every read `assay` makes has to be here, because a stand-in that is missing one does
    // not degrade -- it throws, and the failure names this file rather than the addition
    // that caused it. `getEggsHeld` arrived with the `eggs` measure (#98) and is the reason
    // this comment exists: nothing else pins the stand-in's surface to the real engine's.
    getEaten: () => 0, getIngested: () => 0, getEggsLaid: () => 0, getEggsHeld: () => 0,
  };
}
const dragOf = (points) =>
  assay(scripted(points), [0], points.length - 1,
        { dt: 1.0, sampleDt: 1.0, invariants: false })[0];

test('the drag proxy is quadratic in speed, not in distance', () => {
  /* The header claims this integral is `sum(v^2 dt)` and reasons from that: quadratic, so
   * dominated by the undulation rather than by net progress, so an animal thrashing in
   * place pays. Integrating |v| instead of v^2 would leave every other assertion in this
   * file passing -- checked, by making that exact edit -- while making all three of those
   * sentences false. So the exponent is pinned here.
   */
  const line = (v, n) => Array.from({ length: n + 1 }, (_, i) => [v * i, 0]);

  // Straight line, unit steps: n samples of speed v, each lasting 1.0.
  assert.equal(dragOf(line(1, 4)).drag, 4.0);
  assert.equal(dragOf(line(1, 4)).path, 4.0);
  assert.equal(dragOf(line(1, 4)).moved, 4.0);

  // Double the speed: four times the drag. Twice, and the integral is of |v|.
  assert.equal(dragOf(line(2, 4)).drag, 16.0);
  assert.equal(dragOf(line(3, 4)).drag, 36.0);

  // Thrash in place: the same speed and the same path, no net displacement, the same
  // drag. This is the property that makes the cost term mean "moving", not "getting
  // somewhere", and it is the reason a worm cannot dodge the cost by turning round.
  const zigzag = [[0, 0], [1, 0], [0, 0], [1, 0], [0, 0]];
  assert.equal(dragOf(zigzag).drag, 4.0);
  assert.equal(dragOf(zigzag).path, 4.0);
  assert.equal(dragOf(zigzag).moved, 0.0);

  // Standing still costs nothing, so the cost is of motion rather than of existing.
  assert.equal(dragOf([[0, 0], [0, 0], [0, 0]]).drag, 0.0);
});

// --------------------------------------------------------------------- the vacuity guard
test('the exploit is real under food_eaten', () => {
  // If the byte patch did nothing -- wrong offset, wrong endianness, a copy that was not
  // actually handed to the instance -- the two arms would be the same run and every
  // assertion below would pass on a comparison of a thing with itself. This is the check
  // that the mutation under test happened at all.
  const wild = runs('wild'), vpp = runs('vpp');
  for (let i = 0; i < SEEDS.length; i++) {
    const ratio = vpp[i].eaten / wild[i].eaten;
    assert.ok(ratio > 5.0,
      `seed ${SEEDS[i]}: volume_per_pump x${FACTOR} moved food_eaten by only x`
      + `${ratio.toFixed(3)} (${wild[i].eaten} -> ${vpp[i].eaten}). #37 measured 9.3x and `
      + `this reproduces 6.1x to 9.3x; anything near 1x means the runtime was not patched, `
      + `and then nothing else in this file is measuring what it says.`);
  }
});

test('the mutation does not change foraging behaviour', () => {
  // The other half of #37's observation, and what makes the fitness numbers damning: the
  // animal's trajectory is the same one. Without this, a fall in fitness could just mean
  // the mutant swam differently.
  const wild = runs('wild'), vpp = runs('vpp');
  for (let i = 0; i < SEEDS.length; i++) {
    for (const key of ['drag', 'moved', 'path']) {
      const ratio = vpp[i][key] / wild[i][key];
      assert.ok(Math.abs(ratio - 1) < 1e-3,
        `seed ${SEEDS[i]}: ${key} moved by x${ratio.toFixed(6)} under volume_per_pump `
        + `x${FACTOR}. Measured spread over six seeds is 5e-5; a change this large means `
        + `the pharynx is now feeding back into locomotion and the comparison is no longer `
        + `"same animal, different constant".`);
    }
  }
});

// ------------------------------------------------------------------------- the property
test('volume_per_pump x10 never buys energy fitness', () => {
  const wild = runs('wild'), vpp = runs('vpp');
  for (let i = 0; i < SEEDS.length; i++) {
    const before = score(wild[i], VPP);
    const after = score(vpp[i], VPP * FACTOR);
    // A ratio of two negative numbers is smaller than 1 for reasons that have nothing to
    // do with this property, so establish the sign before reading the ratio. Dropping the
    // normalisation makes both of these negative, and without this line the assertion
    // below would pass on exactly the bug it exists to catch.
    assert.ok(before > 0 && after > 0,
      `seed ${SEEDS[i]}: energy fitness went non-positive (${before.toFixed(5)} -> `
      + `${after.toFixed(5)}); the ratio below would not mean anything.`);
    const ratio = after / before;
    assert.ok(ratio <= 1.0,
      `seed ${SEEDS[i]}: volume_per_pump x${FACTOR} raised energy fitness by x`
      + `${ratio.toFixed(4)} (${before.toFixed(5)} -> ${after.toFixed(5)}). This is #37: a `
      + `bigger pharynx must not be worth anything, because nothing about the animal's `
      + `foraging changed. Measured over six seeds the ratio is 0.54 to 0.91.`);
    assert.ok(ratio >= 0.3,
      `seed ${SEEDS[i]}: energy fitness collapsed to x${ratio.toFixed(4)} under `
      + `volume_per_pump x${FACTOR}. A measure that merely destroys the signal is not a `
      + `fixed measure. The residual is lumen saturation and is bounded -- 0.54 was the `
      + `worst of six seeds -- so a value below 0.3 is a different problem, not this one.`);
  }
});

test('the normalisation is what closes it, not the subtraction', () => {
  // The same records, the same lambda, the same expression -- scored with the *shipped*
  // volume_per_pump against a runtime that has a tenfold one. That is "ingested minus a
  // locomotion cost" taken literally, without putting intake into pump-volumes first, and
  // it is what the obvious reading of #37 item 2 would have produced.
  //
  // It also pins that `fitness` uses the argument it is given. A `fitness` that ignored
  // `volumePerPump` would make the property test above trivially true and this one fail.
  const wild = runs('wild'), vpp = runs('vpp');
  for (let i = 0; i < SEEDS.length; i++) {
    const before = score(wild[i], VPP);
    const naive = score(vpp[i], VPP);
    const ratio = naive / before;
    assert.ok(ratio > 5.0,
      `seed ${SEEDS[i]}: subtracting a locomotion cost from a *raw* intake total moved `
      + `fitness by only x${ratio.toFixed(3)}. It is supposed to be as bad as food_eaten `
      + `or worse -- measured 7.1x to 13.0x against food_eaten's 6.1x to 9.3x, because `
      + `subtracting a constant from a multiplied quantity multiplies the difference by `
      + `more. If this no longer holds, then either fitness has stopped reading its `
      + `volumePerPump argument or the exploit is gone for some other reason, and the `
      + `property test above is no longer evidence of anything.`);
    assert.ok(ratio > vpp[i].eaten / wild[i].eaten,
      `seed ${SEEDS[i]}: the un-normalised budget (x${ratio.toFixed(3)}) should be a `
      + `*worse* exploit than raw food_eaten `
      + `(x${(vpp[i].eaten / wild[i].eaten).toFixed(3)}), not a better one.`);
  }
});

test('the residual is lumen saturation, not the conversion', () => {
  // Why the property above is stated as "never buys" rather than as #37's literal "moves
  // no more than behaviour does". Scaling lumen_capacity alongside volume_per_pump keeps
  // `room` -- the headroom factor in `Worm._fire` -- exactly where it was, and specific
  // intake then comes back flat. Nothing else in the pharynx would do that, which is also
  // what identifies LUMEN_SITE as the constant it is meant to be.
  const wild = runs('wild'), both = runs('vppAndLumen');
  for (let i = 0; i < SEEDS.length; i++) {
    const before = wild[i].ingested / VPP;
    const after = both[i].ingested / (VPP * FACTOR);
    const ratio = after / before;
    assert.ok(Math.abs(ratio - 1) < 0.01,
      `seed ${SEEDS[i]}: with volume_per_pump AND lumen_capacity scaled by ${FACTOR}, `
      + `specific intake moved by x${ratio.toFixed(4)} (${before.toFixed(5)} -> `
      + `${after.toFixed(5)} pump-volumes). It should be flat to under 1% -- measured `
      + `0.9944 to 0.9980 over six seeds -- because the pair scales the pharynx without `
      + `changing how full the lumen gets. If this drifts, either LUMEN_SITE is patching `
      + `the wrong constant or the residual in the property test is something other than `
      + `saturation and needs re-diagnosing.`);
  }
});

// --------------------------------------------------------- the budget is not degenerate
test('neither half of the budget is trivial', () => {
  // Every ratio above is a ratio of fitnesses. If intake were zero the ratios would be
  // NaN; if lambda or drag were zero the "energy" measure would just be a rescaled intake
  // total and the property test would be measuring the normalisation only. These pin that
  // both terms are present and neither dominates to the point of hiding the other.
  for (let i = 0; i < SEEDS.length; i++) {
    const rec = runs('wild')[i];
    const intake = rec.ingested / VPP;
    const cost = LAMBDA * rec.drag;
    assert.ok(intake > 1.0,
      `seed ${SEEDS[i]}: wild-type intake is ${intake.toFixed(5)} pump-volumes over `
      + `${SECONDS} s; measured 1.38 to 2.69. Near zero means the animal never found food `
      + `and every fitness ratio here is noise over noise.`);
    assert.ok(cost > 0.2,
      `seed ${SEEDS[i]}: the locomotion term is ${cost.toFixed(5)}; measured 0.26 to 0.37. `
      + `A cost near zero makes "energy" an intake total wearing a subtraction.`);
    assert.ok(cost / intake > 0.05,
      `seed ${SEEDS[i]}: locomotion is only ${(100 * cost / intake).toFixed(2)}% of intake; `
      + `measured 9.8% to 27%. Below a few percent the budget is not a budget.`);
    assert.ok(score(rec, VPP) > 0.5,
      `seed ${SEEDS[i]}: wild-type energy fitness is ${score(rec, VPP).toFixed(5)}. It has `
      + `to sit comfortably above zero, or selection is comparing sign flips -- which is `
      + `why EVO_LAMBDA defaults to 0.1 rather than to the break-even 0.33 to 0.44.`);
  }
});

test('the measure is the formula it claims to be', () => {
  /* Every assertion above is a ratio of two fitnesses, and ratios are blind to some very
   * large mistakes. Dropping the `- lambda * drag` term entirely leaves the property test,
   * the normalisation test and the behaviour test all passing: they compare intake against
   * intake. So the arithmetic is pinned directly, on synthetic records that need no
   * simulation.
   *
   * The two halves are checked separately because each has its own way of going missing:
   * the division silently reverts the measure to an intake total (#37), and the
   * subtraction silently turns the budget back into one. */
  const rec = { eaten: 3, ingested: 0.02, drag: 4.0 };
  assert.equal(fitness(rec, { mode: 'energy', volumePerPump: 0.005, lambda: 0.1 }),
    0.02 / 0.005 - 0.1 * 4.0);
  // The intake half responds to the normaliser...
  assert.equal(fitness(rec, { mode: 'energy', volumePerPump: 0.05, lambda: 0.1 }),
    0.02 / 0.05 - 0.1 * 4.0);
  // ...and the cost half responds to drag, downwards, by exactly lambda.
  const budget = { mode: 'energy', volumePerPump: 0.005, lambda: 0.1 };
  const a = fitness(rec, budget);
  const b = fitness({ ...rec, drag: 5.0 }, budget);
  assert.ok(Math.abs((a - b) - 0.1 * (5.0 - 4.0)) < 1e-12,
    `raising drag by 1.0 changed fitness by ${(a - b)}, not by lambda`);

  // And on a real record: moving has to cost something, or `energy` is `ingested` in
  // different units wearing a subtraction sign.
  const real = runs('wild')[0];
  assert.ok(score(real, VPP) < real.ingested / VPP - 0.2,
    `the locomotion term debited only ${(real.ingested / VPP - score(real, VPP)).toFixed(5)} `
    + `of a ${(real.ingested / VPP).toFixed(5)} intake`);

  // EVO_FITNESS is read from the environment, so a typo would otherwise select silently.
  assert.throws(() => fitness(rec, { mode: 'enrgy' }), /unknown EVO_FITNESS=enrgy/);
  assert.equal(fitness(rec, { mode: 'eaten' }), 3);
  assert.equal(VOLUME_PER_PUMP, VPP, 'evolve.mjs and this test disagree on volume_per_pump');
});
