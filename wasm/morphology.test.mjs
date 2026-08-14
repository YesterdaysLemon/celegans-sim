/* Heritable chain morphology: the shape of the worm, within the shape of the solver.
 *
 *     node --test wasm/morphology.test.mjs
 *
 * TRACK B. The body stays one unbranched chain -- branching is a different physics
 * engine and is deliberately out of scope (see the field block in assembly/index.ts).
 * What these tests pin:
 *
 *   1. Off is bit-identical, all-ones is bit-identical, and set-then-clear restores the
 *      reference exactly. All-ones to the BIT is a strong claim about the rebuild: the
 *      per-joint stencil accumulation reproduces the payload's BLAS-built dense
 *      matrices exactly at scale one (measured before it was asserted).
 *   2. Each profile does mechanical work: stiffness moves the gait, width's drag slows
 *      the body, a weak muscle profile moves it less -- and every variant stays
 *      physical (checkInvariants), because the clamp floor exists so a mutant cannot
 *      stop being a worm.
 *   3. The clamp actually clamps: wild control points come back in [0.25, 4].
 *   4. Eggs inherit a SNAPSHOT: the hatchling develops the parent's shape at laying,
 *      and a parent mutated after laying cannot reach back into its egg.
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
const STEPS_PER_S = 2000;

/* One worm, one dish, one configuration; returns final nodes and displacement. */
function run(seconds, configure) {
  const E = engine();
  const w = E.createWorm(5, 0.0, 0.0, 0.0);
  if (configure) configure(E, w);
  E.stepAll(Math.round(seconds * STEPS_PER_S));
  const f64 = new Float64Array(E.memory.buffer);
  const nx = Array.from(f64.subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + 51));
  const ny = Array.from(f64.subarray(E.ptrNodesY(w) >> 3, (E.ptrNodesY(w) >> 3) + 51));
  return { nx, ny, disp: Math.hypot(nx[25], ny[25]), inv: E.checkInvariants(w) };
}
const maxNodeDiff = (a, b) => {
  let d = 0;
  for (let i = 0; i <= 50; i++) {
    d = Math.max(d, Math.abs(a.nx[i] - b.nx[i]), Math.abs(a.ny[i] - b.ny[i]));
  }
  return d;
};

test('off, all-ones, and set-then-clear are all bit-identical to the reference', () => {
  const ref = run(4);
  const ones = run(4, (E, w) => E.setMorphology(w, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1));
  const cleared = run(4, (E, w) => {
    E.setMorphology(w, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2);
    E.clearMorphology(w);
  });
  assert.equal(maxNodeDiff(ones, ref), 0,
    'all-ones morphology must rebuild the reference mechanics to the bit');
  assert.equal(maxNodeDiff(cleared, ref), 0,
    'clearMorphology must restore the payload path exactly');
});

test('each profile does mechanical work, and every variant stays physical', () => {
  const ref = run(8);
  const floppy = run(8, (E, w) => E.setMorphology(w, 0.4, 0.4, 0.4, 0.4, 1, 1, 1, 1, 1, 1, 1, 1));
  const stiff = run(8, (E, w) => E.setMorphology(w, 2.5, 2.5, 2.5, 2.5, 1, 1, 1, 1, 1, 1, 1, 1));
  const wide = run(8, (E, w) => E.setMorphology(w, 1, 1, 1, 1, 2.5, 2.5, 2.5, 2.5, 1, 1, 1, 1));
  const weak = run(8, (E, w) => E.setMorphology(w, 1, 1, 1, 1, 1, 1, 1, 1, 0.3, 0.3, 0.3, 0.3));
  for (const [name, r] of [['reference', ref], ['floppy', floppy], ['stiff', stiff],
                           ['wide', wide], ['weak', weak]]) {
    assert.equal(r.inv, 0, `${name} body must stay physical`);
  }
  assert.ok(maxNodeDiff(floppy, ref) > 0.1, 'a floppy spine must change the gait');
  assert.ok(maxNodeDiff(stiff, ref) > 0.1, 'a stiff spine must change the gait');
  // More cuticle means more drag everywhere; the same moments move it less.
  assert.ok(wide.disp < ref.disp,
    `a wide body should be slower: ref ${ref.disp}, wide ${wide.disp}`);
  assert.ok(weak.disp < 0.8 * ref.disp,
    `a weak musculature should clearly undertravel: ref ${ref.disp}, weak ${weak.disp}`);
});

test('the clamp holds against wild control points', () => {
  const E = engine();
  const w = E.createWorm(3, 0, 0, 0);
  E.setMorphology(w, 10, -3, 0, 1e9, 0.01, 4.2, 1, 1, -1, 100, 0.25, 4);
  assert.equal(E.hasOwnMorphology(w), 1);
  for (let i = 0; i < 12; i++) {
    const v = E.getMorph(w, i);
    assert.ok(v >= 0.25 && v <= 4.0, `control ${i} escaped the clamp: ${v}`);
  }
  // And a worm with no morphology reads as reference-shaped for uniform drivers.
  const plain = E.createWorm(4, 1, 1, 0);
  assert.equal(E.hasOwnMorphology(plain), 0);
  assert.equal(E.getMorph(plain, 0), 1.0);
});

test('eggs carry a snapshot: hatchlings develop it, later parent mutation cannot reach it', () => {
  const E = engine();
  const w = E.createWorm(9, 0, 0, 0);
  E.setMorphology(w, 1.5, 1.4, 1.3, 1.2, 0.8, 0.9, 1.1, 1.2, 1.3, 1.2, 1.1, 0.9);
  const egg = E.forceLay(w);
  assert.ok(egg >= 0, 'the plate must take the egg');
  // Mutate the parent AFTER laying; the egg's snapshot must not move.
  E.setMorphology(w, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4);
  const kid = E.hatchEgg(egg, 77, 0.0);
  assert.ok(kid >= 0, 'the egg must hatch');
  assert.equal(E.hasOwnMorphology(kid), 1, 'the hatchling must develop its inheritance');
  const want = [1.5, 1.4, 1.3, 1.2, 0.8, 0.9, 1.1, 1.2, 1.3, 1.2, 1.1, 0.9];
  for (let i = 0; i < 12; i++) {
    assert.equal(E.getMorph(kid, i), want[i],
      `control ${i}: the egg carried ${E.getMorph(kid, i)}, the parent laid ${want[i]}`);
  }
});
