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
  // 49 nodes -- N_LINKS = 48. Reading past the end returns heap-neighbour bytes that
  // decode as plausible denormals; see the correction in metabolism.test.mjs.
  const nx = Array.from(f64.subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + 49));
  const ny = Array.from(f64.subarray(E.ptrNodesY(w) >> 3, (E.ptrNodesY(w) >> 3) + 49));
  return { nx, ny, disp: Math.hypot(nx[24], ny[24]), inv: E.checkInvariants(w) };
}
const maxNodeDiff = (a, b) => {
  let d = 0;
  for (let i = 0; i <= 48; i++) {
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

test('development scales the phenotype and NEVER the genome', () => {
  // The seed-41 lesson, pinned: growth once scaled the control points themselves, so
  // eggs inherited their parent's age and generations shrank 0.55x each. Genotype and
  // development are separate runtime state now, and this is the contract.
  const E = engine();
  const w = E.createWorm(11, 0, 0, 0);
  const genome = [1.6, 1.4, 1.2, 1.0, 0.9, 1.1, 1.3, 1.5, 1.2, 1.0, 0.8, 0.9];
  E.setMorphology(w, ...genome);
  E.setDevelopment(w, 0.5);
  assert.equal(E.getDevelopment(w), 0.5);
  for (let i = 0; i < 12; i++) {
    assert.equal(E.getMorph(w, i), genome[i],
      `development leaked into genome control ${i}`);
  }
  // A juvenile laid this egg; the child must inherit the GENOME, at adult development.
  const egg = E.forceLay(w);
  assert.ok(egg >= 0);
  const kid = E.hatchEgg(egg, 99, 0.0);
  assert.ok(kid >= 0);
  assert.equal(E.getDevelopment(kid), 1.0, 'age must not be heritable');
  for (let i = 0; i < 12; i++) {
    assert.equal(E.getMorph(kid, i), genome[i],
      `the egg carried a developmental state at control ${i}`);
  }
  // And development does real mechanical work: a half-scale animal moves differently.
  const run = (dev) => {
    const E2 = engine();
    const a = E2.createWorm(7, 0, 0, 0);
    E2.setMorphology(a, ...genome);
    E2.setDevelopment(a, dev);
    E2.stepAll(6 * STEPS_PER_S);
    const f64 = new Float64Array(E2.memory.buffer);
    return [f64[(E2.ptrNodesX(a) >> 3) + 24], f64[(E2.ptrNodesY(a) >> 3) + 24]];
  };
  const [ax, ay] = run(1.0), [bx, by] = run(0.5);
  assert.ok(Math.hypot(ax - bx, ay - by) > 0.05,
    'a juvenile should not move exactly like the adult of the same genome');
});

test('a juvenile is short, not merely narrow', () => {
  // Development scales bodyL, so a half-scale animal's node chain spans half the
  // reference contour. Measured as summed link lengths right after the set -- geometry,
  // not dynamics, so the tolerance is tight.
  const E = engine();
  const w = E.createWorm(3, 0, 0, 0);
  const contour = () => {
    const f64 = new Float64Array(E.memory.buffer);
    const nx = f64.subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + 49);
    const ny = f64.subarray(E.ptrNodesY(w) >> 3, (E.ptrNodesY(w) >> 3) + 49);
    let s = 0;
    for (let i = 1; i <= 48; i++) s += Math.hypot(nx[i] - nx[i - 1], ny[i] - ny[i - 1]);
    return s;
  };
  E.stepAll(200);                       // settle once so nodes are freshly placed
  const adult = contour();
  E.setMorphology(w, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);
  E.setDevelopment(w, 0.5);
  E.stepAll(200);
  const young = contour();
  assert.ok(Math.abs(young / adult - 0.5) < 0.02,
    `a dev-0.5 body should span half the contour: ${young} vs ${adult}`);
  E.setDevelopment(w, 1.0);
  E.stepAll(200);
  assert.ok(Math.abs(contour() / adult - 1.0) < 0.02, 'growing back restores the length');
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
