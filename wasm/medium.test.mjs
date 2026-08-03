/* The medium belongs to the dish, not to whichever animals happened to exist when it was
 * chosen.
 *
 * `setMedium` used to walk the existing population and nothing else, and every `Worm` was
 * born with `G.MED_AGAR_CT/CN` written into it. So selecting buffer and then pressing Add
 * Worm produced a dish running two different drag physics at once, with the control still
 * reading "buffer" -- and Reset returned the whole population to agar while the control
 * still read "buffer". #47 measured the divergence at about 0.01043 mm of x after 400
 * steps between two animals that should have been identical.
 *
 * That is a bad shape of bug for this project specifically: nothing errors, nothing looks
 * wrong, and the dish quietly stops being a controlled comparison. An animal added to
 * watch beside another is exactly the case where the two must be in the same fluid.
 *
 *     node --test wasm/medium.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

for (const [file, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(file))) throw new Error(`Missing ${file}; generate it with: ${how}`);
}

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);
const compiled = new WebAssembly.Module(wasmBuf);

const AGAR = [head.scalars.med_agar_ct, head.scalars.med_agar_cn];
const BUFFER = [head.scalars.med_buffer_ct, head.scalars.med_buffer_cn];

function engine() {
  const E = new WebAssembly.Instance(compiled, {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  E.setNoise(0);
  return E;
}

const STEPS = 800;                       // 0.4 s -- #47 saw its divergence by 400
const trace = (E, id) => [E.getX(id), E.getY(id)];
const gap = (a, b) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]));

test('the two media are actually different, or nothing below discriminates', () => {
  assert.ok(AGAR[0] !== undefined && BUFFER[0] !== undefined,
    'the model does not export both media; this test cannot mean anything');
  assert.notDeepEqual(AGAR, BUFFER, 'agar and buffer have identical drag coefficients');

  // ...and different enough to move an animal measurably, which is the property every
  // assertion below leans on. A pair of media that produced the same trajectory would
  // make every "same medium" check pass for free.
  const a = engine(); a.setMedium(...AGAR);
  const ida = a.createWorm(4242, 0, 0, 0); a.stepAll(STEPS);
  const b = engine(); b.setMedium(...BUFFER);
  const idb = b.createWorm(4242, 0, 0, 0); b.stepAll(STEPS);
  const d = gap(trace(a, ida), trace(b, idb));
  assert.ok(d > 1e-4, `agar and buffer put the same animal within ${d.toExponential(3)} mm`
    + ' of itself, so a medium mix-up would be invisible here');
});

test('a worm added after setMedium is in the same fluid as the one already there', () => {
  const E = engine();
  const first = E.createWorm(4242, 0, 0, 0);
  E.setMedium(...BUFFER);
  const second = E.createWorm(4242, 0, 0, 0);   // same seed, same place, same heading
  E.stepAll(STEPS);
  assert.equal(gap(trace(E, first), trace(E, second)), 0,
    'the animal added after the medium was selected followed a different trajectory'
    + ' from the identical animal already in the dish');
});

test('the dish remembers its medium across a reset', () => {
  const E = engine();
  E.setMedium(...BUFFER);
  E.clearWorms();
  E.resetWorld();
  const after = E.createWorm(4242, 0, 0, 0);

  const ref = engine();
  ref.setMedium(...BUFFER);
  const refId = ref.createWorm(4242, 0, 0, 0);

  E.stepAll(STEPS); ref.stepAll(STEPS);
  assert.equal(gap(trace(E, after), trace(ref, refId)), 0,
    'the animal created after a reset was not in the medium the dish was set to');
  assert.deepEqual([E.getMediumCT(), E.getMediumCN()], BUFFER,
    'the dish reports a different medium from the one it was set to');
});

test('setMedium moves the animals already in the dish, not only future ones', () => {
  const E = engine();
  const id = E.createWorm(4242, 0, 0, 0);
  E.setMedium(...BUFFER);
  E.stepAll(STEPS);

  const ref = engine();
  ref.setMedium(...BUFFER);
  const refId = ref.createWorm(4242, 0, 0, 0);
  ref.stepAll(STEPS);

  assert.equal(gap(trace(E, id), trace(ref, refId)), 0,
    'an animal that existed before the medium was chosen kept the old drag');
});

test('the default dish is agar, and readback agrees with it', () => {
  const E = engine();
  assert.deepEqual([E.getMediumCT(), E.getMediumCN()], AGAR,
    'a fresh dish does not report agar');

  const id = E.createWorm(4242, 0, 0, 0);
  E.stepAll(STEPS);
  const ref = engine();
  ref.setMedium(...AGAR);
  const refId = ref.createWorm(4242, 0, 0, 0);
  ref.stepAll(STEPS);
  assert.equal(gap(trace(E, id), trace(ref, refId)), 0,
    'the implicit default and an explicit setMedium(agar) disagree');
});
