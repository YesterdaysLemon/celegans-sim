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
  // TWIN DISHES, not twin worms: two co-located animals in one dish share evolving
  // fields and drift apart at denormal scale whatever the setter does -- the first
  // draft of this test compared same-dish twins and failed on a 1e-306 tail
  // coordinate. Separate engines isolate exactly the thing under test.
  const run = (withSetter) => {
    const E = engine();
    const w = E.createWorm(5, 0.0, 0.0, 0.0);
    if (withSetter) E.setMetabolism(w, 0.0, 1e9, 1e9, 0.5, 0.5, 1.0);  // zero cap: inert
    E.stepAll(4 * STEPS_PER_S);
    const f64 = new Float64Array(E.memory.buffer);
    const nx = Array.from(f64.subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + 51));
    const v = Array.from(f64.subarray(E.ptrV(w) >> 3, (E.ptrV(w) >> 3) + 302));
    return { nx, v, fade: E.getMetabFade(w) };
  };
  const plain = run(false), setter = run(true);
  for (let i = 0; i <= 50; i++) {
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
    const nx = f64()[(E.ptrNodesX(w) >> 3) + 25], ny = f64()[(E.ptrNodesY(w) >> 3) + 25];
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
