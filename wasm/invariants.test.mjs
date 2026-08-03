/* The runtime's physics guard, and proof that it fires.
 *
 *     node --test wasm/invariants.test.mjs
 *
 * Python has two guards and the runtime had neither. `Params.validate` rejects a
 * nonphysical parameter set at construction, which is what closed #38; `check_invariants`
 * catches an animal that was legal on paper and stopped being physical while running.
 * Evolution runs on this runtime, so the second one has to exist here.
 *
 * The whole point of this file is the second test. A guard that has never been observed to
 * fire is not known to work -- it is assumed to work, and this repository has been bitten
 * three times by checks that were green because they compared nothing (#26). So the
 * divergent case is constructed rather than hoped for: a uniform 5.0 uN mm on every joint
 * folds the body past the link limit within about seven steps, which is reachable through
 * the runtime's own setMoment/stepBodyOnly API and needs no gene or payload surgery.
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

const inst = new WebAssembly.Instance(new WebAssembly.Module(wasmBuf), {
  env: { abort(msg, file, line, col) { throw new Error(`wasm abort at ${line}:${col}`); } },
});
const E = inst.exports;

const raw = E.alloc(payload.length + 8);
const ptr = (raw + 7) & ~7;
new Uint8Array(E.memory.buffer).set(payload, ptr);
E.setPayload(ptr);
E.initWorld();

const OK = E.INVARIANT_OK.valueOf();
const CURVATURE = E.INVARIANT_CURVATURE_OVER_LIMIT.valueOf();

test('a healthy animal passes', () => {
  const w = E.createWorm(0, 0.0, 0.0, 0.0);
  assert.equal(E.checkInvariants(w), OK, 'a fresh animal must be physical');
  E.setNoise(0);
  E.step(w, 4000);
  assert.equal(E.checkInvariants(w), OK, 'and must stay physical over two seconds of loop');
});

test('a body folded past the link limit is caught', () => {
  // 5.0 uN mm on every joint. The statics say this crosses the 150.8 /mm link limit at
  // about step 7; 200 steps is margin, not hope.
  const w = E.createWorm(0, 0.0, 0.0, 0.0);
  assert.equal(E.checkInvariants(w), OK, 'must start clean, or the test proves nothing');

  const joints = 47;
  for (let j = 0; j < joints; j++) E.setMoment(w, j, 5.0);
  E.stepBodyOnly(w, 0.0005, 200);

  const code = E.checkInvariants(w);
  assert.notEqual(code, OK, 'a body folded past the link limit must not pass');
  assert.equal(code, CURVATURE, `expected the curvature code, got ${code}`);
});

test('the guard reports the first failure rather than a boolean', () => {
  // Distinct codes are what let an evaluator say which invariant a lineage broke, instead
  // of recording that something, somewhere, went wrong.
  const codes = new Set([
    E.INVARIANT_OK.valueOf(),
    E.INVARIANT_ANGLES_NOT_FINITE.valueOf(),
    E.INVARIANT_POTENTIALS_NOT_FINITE.valueOf(),
    E.INVARIANT_CURVATURE_OVER_LIMIT.valueOf(),
    E.INVARIANT_NODES_NOT_FINITE.valueOf(),
    E.INVARIANT_LEFT_THE_DISH.valueOf(),
  ]);
  assert.equal(codes.size, 6, 'every invariant needs its own code');
});
