/* Dump raw trajectories from the WebAssembly runtime, with the noise ON.
 *
 * `wasm/conform.mjs` proves the two implementations agree to floating point with the noise
 * *off*. That is the right check for the arithmetic, and it is the wrong check for the
 * question anyone actually cares about, because nothing runs with the noise off. The
 * browser runs noisy and the assays run noisy; the mode conformance covers is a mode
 * neither deployment uses.
 *
 * With noise on the two cannot agree sample for sample -- one draws from numpy's PCG64
 * through a ziggurat, the other from xoshiro256++ through Box-Muller -- so the only
 * available claim is statistical: the same animal, not the same trajectory.
 *
 * This program takes no position on what the statistics are. It writes out the raw
 * quantities and lets `tools/parity.py` compute every metric for *both* sides with one
 * implementation. That is deliberate, and it is the same reason the model file exists: if
 * each side computed its own frequency, a disagreement would be ambiguous between the
 * model and the metric, and the metric is the easier of the two to get wrong.
 *
 *   node wasm/trajectories.mjs [seeds] [seconds]  >  web/traj-wasm.bin
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

const SEEDS = Number(process.argv[2] || 8);
const SECONDS = Number(process.argv[3] || 60);
const WARMUP = 4.0;
// 4 dt is what tools/diagnose_loop.py samples at, and it is far more than the metrics
// need -- 500 Hz for a signal under 1 Hz. 40 dt is 50 Hz, still seventy times Nyquist,
// and it makes the dump a tenth of the size. Both sides use this same number.
const STRIDE = 40;

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);

const DT = head.scalars.dt;
const N_JOINTS = head.ints.n_joints;
const N_NODES = head.ints.n_nodes;

const inst = new WebAssembly.Instance(new WebAssembly.Module(wasmBuf), {
  env: { abort(_m, _f, line, col) { throw new Error(`wasm abort ${line}:${col}`); } },
});
const E = inst.exports;
const raw = E.alloc(payload.length + 8);
const base = (raw + 7) & ~7;
new Uint8Array(E.memory.buffer).set(payload, base);
E.setPayload(base);

const warmSteps = Math.round(WARMUP / DT);
const nSamples = Math.floor(SECONDS / DT / STRIDE);

// Layout, little-endian float32 throughout, so numpy can read it with one fromfile:
//   header: seeds, samples, joints, dt*stride           (4 x f32 is lossy for dt, so f64)
// Simpler and less error-prone: a JSON sidecar for the shape, a flat binary for the data.
const kappa = new Float32Array(SEEDS * nSamples * N_JOINTS);
const cx = new Float32Array(SEEDS * nSamples);
const cy = new Float32Array(SEEDS * nSamples);
const fwd = new Uint8Array(SEEDS * nSamples);

for (let s = 0; s < SEEDS; s++) {
  // A fresh dish per animal. An empty one: no food, no gradients, nothing to react to but
  // the body itself, which is what tools/diagnose_loop.py's bare_world builds.
  E.resetWorld();
  E.clearWorms();
  E.setNoise(1);
  const w = E.createWorm(s, 0.0, 0.0, 0.0);
  // createWorm returns a stable handle, not a position: ids are never reused, so the one
  // returned here names this animal for as long as it exists whatever else joins the dish.
  E.step(w, warmSteps);

  for (let i = 0; i < nSamples; i++) {
    E.step(w, STRIDE);
    const k = new Float64Array(E.memory.buffer, E.ptrKappa(w), N_JOINTS);
    kappa.set(k, (s * nSamples + i) * N_JOINTS);
    const nx = new Float64Array(E.memory.buffer, E.ptrNodesX(w), N_NODES);
    const ny = new Float64Array(E.memory.buffer, E.ptrNodesY(w), N_NODES);
    let ax = 0, ay = 0;
    for (let j = 0; j < N_NODES; j++) { ax += nx[j]; ay += ny[j]; }
    cx[s * nSamples + i] = ax / N_NODES;
    cy[s * nSamples + i] = ay / N_NODES;
    fwd[s * nSamples + i] = E.getGateForward(w) > 0.5 ? 1 : 0;
  }
  process.stderr.write(`  seed ${s + 1}/${SEEDS}\r`);
}
process.stderr.write('\n');

const out = at('web', 'traj-wasm.bin');
const meta = {
  arm: 'wasm', seeds: SEEDS, samples: nSamples, joints: N_JOINTS,
  dt: DT * STRIDE, seconds: SECONDS, warmup: WARMUP, stride: STRIDE,
};
fs.writeFileSync(at('web', 'traj-wasm.json'), JSON.stringify(meta));
fs.writeFileSync(out, Buffer.concat([
  Buffer.from(kappa.buffer), Buffer.from(cx.buffer),
  Buffer.from(cy.buffer), Buffer.from(fwd.buffer),
]));
console.error(`wrote ${out}  (${SEEDS} seeds x ${nSamples} samples x ${N_JOINTS} joints, `
            + `${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`);
