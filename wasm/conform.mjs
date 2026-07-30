/* Check the WebAssembly runtime against the Python, step for step.
 *
 * Both sides read their setup out of web/worm.model, so a disagreement here is in the
 * stepping and nowhere else. The mechanics are checked first because they are the piece
 * most likely to be got wrong -- a 50x50 drag metric assembled from masked matrix
 * products, then solved -- and the piece where being wrong is least obvious downstream,
 * since slightly wrong drag still produces a worm-shaped thing that wriggles.
 */
import fs from 'fs';

const ROOT = new URL('..', import.meta.url).pathname;
const wasmBuf = fs.readFileSync(ROOT + 'web/worm.wasm');
const modelBuf = fs.readFileSync(ROOT + 'web/worm.model');
const ref = JSON.parse(fs.readFileSync(ROOT + 'web/conform.json', 'utf8'));

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

const ptr = E.alloc(payload.length);
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
const ok = worstXY < 1e-9 && worstK < 1e-7;
console.log(ok ? '\n  PASS -- the two implementations agree to floating point'
               : '\n  FAIL -- the port does not reproduce the Python mechanics');
process.exit(ok ? 0 : 1);
