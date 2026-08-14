/* Tier two of the evolution project: heritable synaptic weights, and the development
 * that regrows a mutant's calibration from its own graph.
 *
 *     node --test wasm/weights.test.mjs
 *
 * TRACK B: nothing here is a claim about C. elegans. What IS being claimed, and therefore
 * tested, is a set of contracts about the machinery:
 *
 *   1. Development is the exporter's own construction, re-run. developWorm() on an
 *      UNMUTATED animal must reproduce the payload's V_th to LU rounding and leave the
 *      trajectory within conformance-scale noise of an untouched twin -- the pipeline is
 *      the same arithmetic worm/nervous.py and worm/muscle.py run at construction, so on
 *      the wild-type graph it must land where they landed. This is the test that makes
 *      the rest mean something: if development is wrong, every "mutant phenotype" after
 *      it is just miscalibration.
 *   2. The mechanism's refusals hold: a chemical synapse's two views scale in lockstep,
 *      a gap junction's two directions scale together, and a negative factor clamps to
 *      zero instead of flipping a sign.
 *   3. A real mutation is a real phenotype: it moves resting potentials, changes the
 *      trajectory, and the animal still passes the physics guard -- mutants are allowed
 *      to be bad at being a worm, not to stop doing physics.
 *   4. Inheritance is snapshot semantics, end to end: egg carries the weights it was laid
 *      with, hatches a developed animal with them, and neither later mutation of the
 *      parent nor the parent's death can reach back into the egg.
 *
 * Wild-type animals never pay: they alias one shared set of arrays and lay weightless
 * eggs. That contract is held by conform.mjs and the invariants pins, which run the same
 * binary this file runs.
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

const N_NEURONS = 302;
const FAM = { syn: 0, gap: 1, mus: 2 };

test('development on the wild-type graph reproduces the exporter', () => {
  const E = engine();
  const a = E.createWorm(7, 0.0, 0.0, 0.0);   // will be developed
  const b = E.createWorm(7, 0.0, 0.0, 0.0);   // untouched twin, same seed

  // Scale one synapse by exactly 1.0: gives the animal its own arrays (bit-identical
  // copies) without changing a single value, so develop runs the full pipeline on the
  // wild-type graph.
  E.scaleWeight(a, FAM.syn, 0, 1.0);
  assert.equal(E.hasOwnWeights(a), 1);
  assert.equal(E.hasOwnWeights(b), 0);

  const shift = E.developWorm(a);
  // The runtime LU against the exporter's LAPACK: measured 3.6e-14 mV before this was
  // built (docs/research-log, "The one thing the exporter rework needed to know").
  // 1e-12 is that with margin; anything past it means development is NOT the exporter's
  // construction re-run.
  assert.ok(shift < 1e-12, `wild-type development shifted V_th by ${shift} mV`);

  // And the difference must not amplify: 4000 steps, both animals, worst deviations at
  // conformance scale. The pre-build measurement was 5.3e-15 mm / 1.2e-12 mV at 4000
  // steps; 1e-9 mm / 1e-8 mV is that with the same four-orders margin conformance uses.
  E.stepAll(4000);
  const f64 = new Float64Array(E.memory.buffer);
  let worstV = 0, worstX = 0;
  const va = E.ptrV(a) >> 3, vb = E.ptrV(b) >> 3;
  for (let i = 0; i < N_NEURONS; i++) {
    worstV = Math.max(worstV, Math.abs(f64[va + i] - f64[vb + i]));
  }
  const xa = E.ptrNodesX(a) >> 3, xb = E.ptrNodesX(b) >> 3;
  // 49 nodes (N_LINKS = 48); see the out-of-bounds correction in metabolism.test.mjs.
  for (let i = 0; i <= 48; i++) {
    worstX = Math.max(worstX, Math.abs(f64[xa + i] - f64[xb + i]));
  }
  assert.ok(worstV < 1e-8, `developed twin diverged by ${worstV} mV`);
  assert.ok(worstX < 1e-9, `developed twin diverged by ${worstX} mm`);
});

test('the mechanism refuses what it says it refuses', () => {
  const E = engine();
  const w = E.createWorm(1, 0.0, 0.0, 0.0);

  // Chemical synapse: both views move together.
  const g0 = E.getWeight(w, FAM.syn, 5), ge0 = E.getWeight2(w, 5);
  E.scaleWeight(w, FAM.syn, 5, 2.0);
  assert.ok(Math.abs(E.getWeight(w, FAM.syn, 5) - 2 * g0) < 1e-15 * Math.abs(g0) + 1e-300);
  assert.ok(Math.abs(E.getWeight2(w, 5) - 2 * ge0) < 1e-15 * Math.abs(ge0) + 1e-300,
    'GE view did not move in lockstep with G');

  // Gap junction: one resistor, two directions, one scale.
  const k = 3, p = E.gapMirror(3);
  assert.ok(p >= 0 && p !== k, 'mirror should exist and differ (no self junctions)');
  assert.equal(E.gapMirror(p), k, 'mirroring is an involution');
  const gk = E.getWeight(w, FAM.gap, k), gp = E.getWeight(w, FAM.gap, p);
  assert.equal(gk, gp, 'the wild-type gap matrix should already be symmetric');
  E.scaleWeight(w, FAM.gap, k, 0.5);
  assert.equal(E.getWeight(w, FAM.gap, k), 0.5 * gk,
    'the scale must actually land (equal-stays-equal would pass a no-op)');
  assert.equal(E.getWeight(w, FAM.gap, k), E.getWeight(w, FAM.gap, p),
    'scaling one direction must scale the mirror');

  // Sign is topology: a negative factor clamps to zero, never crosses it.
  E.scaleWeight(w, FAM.mus, 2, -3.0);
  assert.equal(E.getWeight(w, FAM.mus, 2), 0.0, 'negative factor should clamp to deletion');

  // Counts are the payload's counts.
  assert.equal(E.weightCount(FAM.syn), 2279);
  assert.equal(E.weightCount(FAM.gap), 1104);
  assert.equal(E.weightCount(FAM.mus), 552);
});

test('a real mutation is a phenotype, not a crash', () => {
  const E = engine();
  const wt = E.createWorm(3, 0.0, 0.0, 0.0);
  const mut = E.createWorm(3, 0.0, 0.0, 0.0);

  // A deterministic scatter of substantial mutations across all three families.
  for (let i = 0; i < 60; i++) {
    const k = (i * 37) % E.weightCount(FAM.syn);
    E.scaleWeight(mut, FAM.syn, k, i % 2 ? 1.6 : 0.6);
  }
  for (let i = 0; i < 10; i++) E.scaleWeight(mut, FAM.gap, (i * 101) % 1104, 1.5);
  for (let i = 0; i < 10; i++) E.scaleWeight(mut, FAM.mus, (i * 53) % 552, 0.7);

  const shift = E.developWorm(mut);
  assert.ok(shift > 1e-3,
    `60 scaled synapses should move some resting potential visibly, got ${shift} mV`);

  E.stepAll(4000);
  assert.equal(E.checkInvariants(mut), 0, 'a mutant must still do physics');
  assert.equal(E.checkInvariants(wt), 0);

  const f64 = new Float64Array(E.memory.buffer);
  const vm = E.ptrV(mut) >> 3, vw = E.ptrV(wt) >> 3;
  let worst = 0;
  for (let i = 0; i < N_NEURONS; i++) {
    worst = Math.max(worst, Math.abs(f64[vm + i] - f64[vw + i]));
  }
  assert.ok(worst > 1e-3, `mutant should behave differently, worst diff ${worst} mV`);
});

test('inheritance is a snapshot: through the egg, past mutation, past death', () => {
  const E = engine();
  const parent = E.createWorm(11, 0.0, 0.0, 0.0);
  const probe = 42;
  const wtVal = E.getWeight(parent, FAM.syn, probe);
  E.scaleWeight(parent, FAM.syn, probe, 1.5);
  E.developWorm(parent);
  const parentVth5 = E.getVth(parent, 5);

  const egg = E.forceLay(parent);
  assert.ok(egg >= 0, 'the plate refused a forced egg');

  // Mutate the parent AFTER laying, then remove it: neither may reach the egg.
  E.scaleWeight(parent, FAM.syn, probe, 100.0);
  E.removeWorm(parent);

  const child = E.hatchEgg(egg, 99, 1.0);
  assert.ok(child >= 0);
  assert.equal(E.hasOwnWeights(child), 1, 'a mutant lineage must inherit its weights');
  const got = E.getWeight(child, FAM.syn, probe);
  assert.ok(Math.abs(got - 1.5 * wtVal) < 1e-12 * Math.abs(wtVal),
    `child carries ${got}, expected the snapshot ${1.5 * wtVal}`);
  // The child developed at hatch: same graph as the parent had at laying, same rest.
  assert.ok(Math.abs(E.getVth(child, 5) - parentVth5) < 1e-12,
    'hatchling should develop to the same rest its parent computed from the same graph');

  // And a wild-type egg stays free: no weights, no development, a clone.
  const wt = E.createWorm(12, 1.0, 1.0, 0.0);
  const egg2 = E.forceLay(wt);
  const child2 = E.hatchEgg(egg2, 100, 0.0);
  assert.equal(E.hasOwnWeights(child2), 0, 'wild-type eggs must not grow weight arrays');
});
