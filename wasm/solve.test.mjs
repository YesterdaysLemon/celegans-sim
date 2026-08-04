/* The runtime's resting-potential solve, against the exporter's.
 *
 *     node --test wasm/solve.test.mjs
 *
 * `V_th` is not anatomy. It is a *product* of the anatomy -- the fixed point
 * `NervousSystem._resting_potentials` solves for, with every release curve half-activated
 * so the network sits on the steep part of its transfer function (Kunert et al. 2014). The
 * payload carries the answer, which is exactly right for one fixed animal and exactly wrong
 * the moment a lineage mutates a synaptic weight or adds a connection: the exported array
 * then describes a network that no longer exists. That is #96.
 *
 * The graph was already exported. G_syn, GE_syn and G_gap go out as CSR, so making weights
 * heritable needs no payload format change at all -- only the runtime has to gain the solve.
 * `computeRestingPotentials` is that solve, and this file is the reason it can be trusted.
 *
 * WHAT THIS IS ACTUALLY GUARDING, because "it agrees" is the weakest possible reading.
 *
 * Nothing calls the solve yet: the step still reads the exported `V_th`, so the runtime now
 * has two sources of truth for the same 302 numbers. That is the shape of defect this
 * repository keeps finding -- two copies of a quantity with nothing comparing them, one of
 * which goes stale for a reason nobody was tracking. The comparison here is what makes the
 * pair safe to hold, and it is what has to keep passing when the step is eventually flipped
 * over to the computed value.
 *
 * The tolerance is not arbitrary. NEXT.md measured the port before it was written: cond(A)
 * = 94, a plain LU with partial pivoting matching LAPACK to 3.6e-14 mV and 5.7e-16
 * relative, and the difference failing to amplify -- 5.3e-15 mm of node movement after 4000
 * steps against a conformance tolerance of 1e-9. So 1e-11 mV here is loose against the
 * measurement and tight against anything that would matter downstream. A regression that
 * merely doubled the error would still pass; one that changed the arithmetic would not.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

for (const [f, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(f))) throw new Error(`missing ${f}; build it with: ${how}`);
}

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);

function engine() {
  const E = new WebAssembly.Instance(new WebAssembly.Module(wasmBuf), {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  // Align to 8: the payload is read as f64 through `load<f64>`, and an unaligned base makes
  // every offset in model_gen.ts point a few bytes into the wrong number.
  const raw = E.alloc(payload.length + 8);
  const ptr = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, ptr);
  E.setPayload(ptr);
  E.initWorld();
  return E;
}

const N = head.scalars.n_neurons ?? 302;

test('the runtime solves for the same resting potentials the exporter did', () => {
  const E = engine();
  const solved = E.computeRestingPotentials();
  // Read after the call: any allocation inside it can grow linear memory, which detaches
  // every view taken before. This is the same trap viewer/history.js is built around.
  const got = new Float64Array(E.memory.buffer, solved, N);
  const want = new Float64Array(E.memory.buffer, E.ptrExportedVth(), N);

  assert.equal(got.length, N);
  assert.ok([...got].every(Number.isFinite), 'the solve produced a non-finite potential');

  let worst = 0, worstAt = -1, worstRel = 0;
  for (let i = 0; i < N; i++) {
    const d = Math.abs(got[i] - want[i]);
    if (d > worst) { worst = d; worstAt = i; }
    const rel = d / Math.max(1e-12, Math.abs(want[i]));
    if (rel > worstRel) worstRel = rel;
  }
  console.log(`    max |computed - exported| = ${worst.toExponential(3)} mV `
            + `at neuron ${worstAt}, ${worstRel.toExponential(3)} relative`);

  assert.ok(worst < 1e-11,
    `the runtime's resting-potential solve disagrees with the exporter's by ${worst} mV `
    + `at neuron ${worstAt}. The measurement this port was sized against put a plain LU `
    + `within 3.6e-14 mV of LAPACK, so a difference this large is a defect in the solve, `
    + `not float noise.`);
});

test('it is solving, not reading the answer back', () => {
  /* The failure this exists for is the one that would look like success.
   *
   * A solve that quietly returned the exported array -- through a copied pointer, a
   * mistaken offset, or a future refactor that "optimises" the call away -- would pass the
   * test above perfectly, at exactly 0.0. The repository has shipped that bug: an
   * egg-laying conformance comparison printed a perfect 0.000e+0 from comparing zero
   * fields, and it was reported as bit-identical agreement.
   *
   * So: the two arrays must not be the same memory, and the agreement must be *approximate*
   * rather than exact. A genuine independent LU on this matrix cannot reproduce LAPACK bit
   * for bit -- the measurement says 3.6e-14, not 0 -- so an exactly-zero difference across
   * all 302 cells is evidence of aliasing rather than of a very good solve.
   */
  const E = engine();
  const solved = E.computeRestingPotentials();
  const exported = E.ptrExportedVth();
  assert.notEqual(solved, exported,
    'computeRestingPotentials returned the exported array itself, so the test above is '
    + 'comparing a buffer with itself');

  const got = new Float64Array(E.memory.buffer, solved, N);
  const want = new Float64Array(E.memory.buffer, exported, N);
  const identical = [...got].every((v, i) => v === want[i]);
  assert.ok(!identical,
    'every one of the 302 potentials matches the exported value bit for bit. An '
    + 'independent LU cannot reproduce a LAPACK solve exactly, so this is the solve '
    + 'reading its answer rather than computing it.');
});

test('the two constants the payload gained for this are present and sane', () => {
  // s_half was always derivable from a_rise and a_decay; ca_offset was the one genuine gap,
  // and m0 -- the calcium gate's opening at rest -- cannot be formed without it.
  const s = head.scalars;
  for (const k of ['neural_a_rise', 'neural_a_decay', 'neural_ca_slope', 'neural_ca_offset']) {
    assert.ok(k in s, `${k} is missing from the model header; the solve cannot form its constants`);
    assert.ok(Number.isFinite(s[k]), `${k} is not finite`);
  }
  const sHalf = 0.5 * s.neural_a_rise / (0.5 * s.neural_a_rise + s.neural_a_decay);
  assert.ok(sHalf > 0 && sHalf < 1, `s_half came out at ${sHalf}, which is not a release fraction`);
  assert.ok(s.neural_ca_slope !== 0, 'ca_slope is zero, so m0 would divide by it');
});
