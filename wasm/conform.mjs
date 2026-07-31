/* Check the WebAssembly runtime against the Python, step for step.
 *
 * Both sides read their setup out of web/worm.model, so a disagreement here is in the
 * stepping and nowhere else. The mechanics are checked first because they are the piece
 * most likely to be got wrong -- a 50x50 drag metric assembled from masked matrix
 * products, then solved -- and the piece where being wrong is least obvious downstream,
 * since slightly wrong drag still produces a worm-shaped thing that wriggles.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// fileURLToPath, not .pathname. A file URL's pathname on Windows is "/C:/src/wasm/", and
// joining that onto anything gives "C:\C:\src\...", which is not a path anywhere.
const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

const inputs = [
  {
    path: at('web', 'worm.wasm'),
    display: 'web/worm.wasm',
    command: 'cd wasm && npx asc assembly/index.ts --target release',
  },
  {
    path: at('web', 'worm.model'),
    display: 'web/worm.model',
    command: 'PYTHONPATH=. python tools/export_model.py',
  },
  {
    path: at('web', 'conform.json'),
    display: 'web/conform.json',
    command: 'PYTHONPATH=. python tools/conform.py > web/conform.json',
  },
];
const missing = inputs.filter(input => !fs.existsSync(input.path));
if (missing.length) {
  for (const input of missing) {
    console.error(`Missing ${input.display}; generate it with: ${input.command}`);
  }
  process.exit(2);
}

const modelMtime = fs.statSync(at('web', 'worm.model')).mtimeMs;
const referenceMtime = fs.statSync(at('web', 'conform.json')).mtimeMs;
if (referenceMtime < modelMtime) {
  console.warn(
    'Warning: web/conform.json is older than web/worm.model; regenerate it with: ' +
    'PYTHONPATH=. python tools/conform.py > web/conform.json',
  );
}

const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const ref = JSON.parse(fs.readFileSync(at('web', 'conform.json'), 'utf8'));

// --- model file: 'WORM' + version, u32 header length, JSON header, payload ------------
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const meta = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);

const mod = new WebAssembly.Module(wasmBuf);
const inst = new WebAssembly.Instance(mod, {
  env: { abort(msg, file, line, col) { throw new Error(`wasm abort at ${line}:${col}`); } },
});
const E = inst.exports;

// The payload holds f64 arrays, so it has to start on an 8-byte boundary or the views
// the runtime builds over it are misaligned.
const raw = E.alloc(payload.length + 8);
const ptr = (raw + 7) & ~7;
new Uint8Array(E.memory.buffer).set(payload, ptr);
E.setPayload(ptr);
E.initWorld();

const F64 = () => new Float64Array(E.memory.buffer);

// --- the mechanics ---------------------------------------------------------------------
const c = ref.body;
const w = E.createWorm(0, 0.0, 0.0, 0.0);
c.moment.forEach((v, j) => E.setMoment(w, j, v));

let worstXY = 0, worstK = 0, prev = 0;
for (const f of c.frames) {
  E.stepBodyOnly(w, c.dt, f.step - prev);
  prev = f.step;
  const nx = F64().subarray(E.ptrNodesX(w) >> 3, (E.ptrNodesX(w) >> 3) + f.x.length);
  const ny = F64().subarray(E.ptrNodesY(w) >> 3, (E.ptrNodesY(w) >> 3) + f.y.length);
  const kk = F64().subarray(E.ptrKappa(w) >> 3, (E.ptrKappa(w) >> 3) + f.kappa.length);
  for (let i = 0; i < f.x.length; i++) {
    worstXY = Math.max(worstXY, Math.abs(nx[i] - f.x[i]), Math.abs(ny[i] - f.y[i]));
  }
  for (let i = 0; i < f.kappa.length; i++) {
    worstK = Math.max(worstK, Math.abs(kk[i] - f.kappa[i]));
  }
}

const last = c.frames[c.frames.length - 1];
const span = Math.hypot(last.x[0] - last.x[last.x.length - 1],
                        last.y[0] - last.y[last.y.length - 1]);
console.log(`MECHANICS -- prescribed moment, ${c.steps} steps, no biology, no noise`);
console.log(`  worst node disagreement       ${worstXY.toExponential(3)} mm` +
            `   (body spans ${span.toFixed(3)} mm)`);
console.log(`  worst curvature disagreement  ${worstK.toExponential(3)} /mm`);
const mechOk = worstXY < 1e-9 && worstK < 1e-7;
console.log(mechOk ? '  PASS' : '  FAIL');

// --- the whole loop --------------------------------------------------------------------
// The same plate the Python built. This has to be kept in step with conform.py by hand,
// and it is worth the nuisance: the first version of this test ran both sides on an empty
// dish, where every sensory field reads zero -- so it passed while the WASM's food field
// had an exponential skirt the Python's does not, and an animal seven millimetres outside
// a five millimetre lawn thought it was standing on one.
const fc = ref.full;
E.setNoise(0);
E.addFood(-6.0, 4.0, 5.0, 1.0, 1.0, 9.0);
E.addRepellent(7.0, -3.0, 0.9, 5.0);
const w2 = E.createWorm(0, 0.0, 0.0, 0.0);
let wXY = 0, wV = 0, wT = 0, gateBad = 0;
prev = 0;
for (const f of fc.frames) {
  E.step(w2, f.step - prev);
  prev = f.step;
  const nx = F64().subarray(E.ptrNodesX(w2) >> 3, (E.ptrNodesX(w2) >> 3) + f.x.length);
  const ny = F64().subarray(E.ptrNodesY(w2) >> 3, (E.ptrNodesY(w2) >> 3) + f.y.length);
  const vv = F64().subarray(E.ptrV(w2) >> 3, (E.ptrV(w2) >> 3) + f.V.length);
  const tt = F64().subarray(E.ptrTension(w2) >> 3, (E.ptrTension(w2) >> 3) + f.tension.length);
  for (let i = 0; i < f.x.length; i++)
    wXY = Math.max(wXY, Math.abs(nx[i] - f.x[i]), Math.abs(ny[i] - f.y[i]));
  for (let i = 0; i < f.V.length; i++) wV = Math.max(wV, Math.abs(vv[i] - f.V[i]));
  for (let i = 0; i < f.tension.length; i++) wT = Math.max(wT, Math.abs(tt[i] - f.tension[i]));
  if (E.getGateForward(w2) !== f.gate) gateBad++;
}
console.log(`\nWHOLE LOOP -- neurons, muscle, senses, body; ${fc.steps} steps, noise off`);
console.log(`  worst node disagreement       ${wXY.toExponential(3)} mm`);
console.log(`  worst membrane potential      ${wV.toExponential(3)} mV`);
console.log(`  worst muscle tension          ${wT.toExponential(3)}`);
console.log(`  direction gate disagreed on   ${gateBad} of ${fc.frames.length} samples`);
const fullOk = wXY < 1e-6 && wV < 1e-6 && wT < 1e-8 && gateBad === 0;
console.log(fullOk ? '  PASS' : '  FAIL');

const ok = mechOk && fullOk;
console.log(ok ? '\nThe port reproduces the Python model.'
               : '\nThe port does NOT reproduce the Python model.');
process.exit(ok ? 0 : 1);
