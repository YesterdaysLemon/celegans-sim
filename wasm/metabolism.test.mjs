/* The metabolic budget: dish physiology that makes starvation a mechanism.
 *
 *     node --test wasm/metabolism.test.mjs
 *
 * TRACK B, and doubly so: the reference animal has no death and no energy budget -- a
 * worm that never eats swims at full strength forever (docs/niche-museum.md holds the
 * immortality exhibit). These are contracts about the *machinery*:
 *
 *   1. Off is bit-identical. metabFade multiplies every muscle moment, so the off state
 *      has to be exactly 1.0, not nearly.
 *   2. An unfed animal runs down: the store reaches zero, the fade reaches its floor
 *      exactly, and the body measurably weakens -- while still passing the physics guard.
 *      Starvation is allowed to be fatal, not to be a NaN.
 *   3. Eating actually refills the store: the intake term is the pharynx's real
 *      transport, not a proxy.
 *   4. A corpse deposit conserves food: the plate gains exactly what was deposited, and
 *      a deposit entirely off the dish is refused rather than vanished.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const payload = modelBuf.subarray(12 + headLen);

function engine() {
  const inst = new WebAssembly.Instance(new WebAssembly.Module(wasmBuf), {
    env: { abort(msg, file, line, col) { throw new Error(`wasm abort at ${line}:${col}`); } },
  });
  const E = inst.exports;
  const raw = E.alloc(payload.length + 8);
  const ptr = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, ptr);
  E.setPayload(ptr);
  E.initWorld();
  E.setNoise(0);
  return E;
}
const STEPS_PER_S = 2000;   // DT = 0.0005

test('metabolism off is bit-identical, and a zero-cap setter is off', () => {
  // A correction, on the record because the first two stories were both wrong. The
  // first draft compared same-dish twins and failed on a ~1e-306 "node 50"; this
  // comment then blamed co-located animals drifting through shared fields. Both
  // fictions: the body has 49 nodes (N_LINKS = 48), and the read was 51 -- indices 49
  // and 50 were out-of-bounds heap-neighbour bytes decoding as denormals, different
  // per worm within one dish, identical across twin engines (same allocation order,
  // same garbage), which is why the "fix" appeared to work. Measured after the fix:
  // same-dish twins are bit-identical over all 49 real nodes. The twin-dish shape is
  // kept anyway -- it isolates the setter from everything else -- but the read is 49,
  // and the moral is the museum's: garbage that decodes as a plausible float is the
  // politest failure there is.
  const run = (withSetter) => {
    const E = engine();
    const w = E.createWorm(5, 0.0, 0.0, 0.0);
    if (withSetter) E.setMetabolism(w, 0.0, 1e9, 1e9, 0.5, 0.5, 1.0);  // zero cap: inert
    E.stepAll(4 * STEPS_PER_S);
    const f64 = new Float64Array(E.memory.buffer);
    const nx = Array.from(f64.subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + 49));
    const v = Array.from(f64.subarray(E.ptrV(w) >> 3, (E.ptrV(w) >> 3) + 302));
    return { nx, v, fade: E.getMetabFade(w) };
  };
  const plain = run(false), setter = run(true);
  for (let i = 0; i <= 48; i++) {
    assert.equal(setter.nx[i], plain.nx[i], `node ${i} differs with metabolism zero-capped`);
  }
  for (let i = 0; i < 302; i++) {
    assert.equal(setter.v[i], plain.v[i], `V[${i}] differs with metabolism zero-capped`);
  }
  assert.equal(setter.fade, 1.0, 'fade must be exactly 1.0 when off');
});

test('an unfed animal runs down to the floor, weakened but physical', () => {
  const E = engine();                       // no food anywhere on this plate
  const w = E.createWorm(3, 0.0, 0.0, 0.0);
  // 0.02 units at 2e-3/s basal: empty in at most 10 s, well inside the assay.
  E.setMetabolism(w, 0.02, 2e-3, 1e-4, 0.2, 0.5, 1.0);

  const f64 = () => new Float64Array(E.memory.buffer);
  const mid = () => {
    const nx = f64()[(E.ptrNodesX(w) >> 3) + 24], ny = f64()[(E.ptrNodesY(w) >> 3) + 24];
    return [nx, ny];
  };
  E.stepAll(4 * STEPS_PER_S);
  const e4 = E.getEnergy(w);
  const [x0, y0] = mid();
  E.stepAll(4 * STEPS_PER_S);
  const [x1, y1] = mid();
  const strideEarly = Math.hypot(x1 - x0, y1 - y0);
  assert.ok(e4 < 0.02 && e4 > 0.0, `store should be draining at 4 s, is ${e4}`);

  E.stepAll(12 * STEPS_PER_S);              // 20 s total: long past empty
  assert.equal(E.getEnergy(w), 0.0, 'the store must bottom at exactly zero');
  assert.equal(E.getMetabFade(w), 0.2, 'at an empty store the fade IS the floor');
  assert.equal(E.checkInvariants(w), 0, 'a starved animal is weak, not unphysical');

  const [x2, y2] = mid();
  E.stepAll(4 * STEPS_PER_S);
  const [x3, y3] = mid();
  const strideLate = Math.hypot(x3 - x2, y3 - y2);
  assert.ok(strideLate < 0.6 * strideEarly,
    `a floored animal should visibly slow: early ${strideEarly}, late ${strideLate}`);
});

test('eating refills the store through the real pharynx', () => {
  const E = engine();
  E.addFood(0, 0, 4.0, 1.0, 1.0, 9.0);
  const w = E.createWorm(1, 0.5, 0.5, 0.0);
  // Start at half: on a lawn, intake (~1e-2/s measured) dwarfs these costs, so the
  // store should climb toward the cap rather than drain.
  E.setMetabolism(w, 0.05, 1e-4, 1e-5, 0.2, 0.5, 0.5);
  const e0 = E.getEnergy(w);
  E.stepAll(20 * STEPS_PER_S);
  const e1 = E.getEnergy(w);
  assert.ok(e1 > e0 + 5e-3,
    `a feeding animal should bank energy: started ${e0}, has ${e1}`);
  assert.ok(e1 <= 0.05 + 1e-15, 'and the cap must hold');
});

test('a rot miasma deposits into the repellent field, and the plate forgets it', () => {
  const E = engine();
  const f64 = () => new Float64Array(E.memory.buffer);
  const G2 = 256 * 256;
  const total = () => {
    const rep = f64().subarray(E.ptrRepellent() >> 3, (E.ptrRepellent() >> 3) + G2);
    let s = 0; for (let i = 0; i < G2; i++) s += rep[i];
    return s;
  };
  const before = total();
  const taken = E.depositRepellent(-2.0, 3.0, 1.2, 0.4);
  assert.equal(taken, 0.4, 'an in-dish miasma is taken whole');
  const justAfter = total();
  assert.ok(Math.abs(justAfter - before - 0.4) < 1e-9,
    `the field must gain exactly the deposit: gained ${justAfter - before}`);
  // The repellent field diffuses and decays in stepFields; a fouled patch must fade
  // rather than accumulate forever. Two simulated seconds is plenty to see the decay
  // moving; full disappearance takes longer and is the field dynamics' own business.
  const w = E.createWorm(1, 20.0, 20.0, 0.0);   // far corner; fields step with the dish
  E.stepAll(2 * STEPS_PER_S);
  assert.ok(total() < justAfter,
    `the miasma should be decaying: ${justAfter} -> ${total()}`);
});

test('a corpse deposit conserves food exactly, and off-dish is refused', () => {
  const E = engine();
  const f64 = () => new Float64Array(E.memory.buffer);
  const G2 = 256 * 256;
  const plateTotal = () => {
    const food = f64().subarray(E.ptrFood() >> 3, (E.ptrFood() >> 3) + G2);
    let s = 0; for (let i = 0; i < G2; i++) s += food[i];
    return s;
  };
  const before = plateTotal();
  const taken = E.depositFood(3.0, -2.0, 1.5, 0.125);
  assert.equal(taken, 0.125, 'an in-dish deposit is taken whole');
  const after = plateTotal();
  assert.ok(Math.abs(after - before - 0.125) < 1e-9,
    `the plate must gain exactly the deposit: gained ${after - before}`);
  const refused = E.depositFood(100.0, 100.0, 1.0, 0.5);
  assert.equal(refused, 0.0, 'a deposit entirely off the dish reports zero taken');
  assert.ok(Math.abs(plateTotal() - after) < 1e-12, 'and adds nothing');
});
