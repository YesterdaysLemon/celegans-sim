/* The weight-drift instrument, pinned against the runtime it measures.
 *
 * The contract: driftOf sees exactly the loci scaleWeight touched, charges them to the
 * neurons the CSR tables say they connect, names them by those tables, and says null --
 * not zero -- for an animal that never mutated. Every assertion here is about the
 * instrument; the mutation mechanics themselves are pinned in weights.test.mjs.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { engine } from './evolve.mjs';
import { makeWiring, driftOf, neuronTopSynapses, driftLine } from '../web/weight-drift.js';

const modelBuf = fs.readFileSync(new URL('../web/worm.model', import.meta.url));
const headLen = modelBuf.readUInt32LE(8);
const HEAD = JSON.parse(modelBuf.subarray(12, 12 + headLen).toString());
const payloadAt = 12 + headLen;
const readArray = (name, Type) => {
  const a = HEAD.arrays[name];
  return new Type(modelBuf.buffer.slice(modelBuf.byteOffset + payloadAt + a.offset,
                                        modelBuf.byteOffset + payloadAt + a.offset + a.bytes));
};

const W = makeWiring(HEAD, readArray);

test('the wiring kit sees all 3,935 heritable loci', () => {
  const E = engine();
  const total = W.counts.reduce((a, b) => a + b, 0);
  assert.equal(W.counts[0], E.weightCount(0));
  assert.equal(W.counts[1], E.weightCount(1));
  assert.equal(W.counts[2], E.weightCount(2));
  assert.equal(total, 2279 + 1104 + 552);
});

test('wild-type baseline matches a fresh animal, and drift says null for it', () => {
  const E = engine();
  const id = E.createWorm(7, 0, 0, 0);
  for (const [fam, k] of [[0, 0], [0, 1000], [1, 50], [2, 300]]) {
    assert.equal(E.getWeight(id, fam, k), W.base[fam][k],
      `payload table and live weight disagree at fam ${fam} k ${k}`);
  }
  assert.equal(driftOf(E, id, W), null);
  assert.equal(driftLine(E, [id], W), 'wiring: wild-type everywhere');
});

test('driftOf sees exactly the touched loci, charged to the right neurons', () => {
  const E = engine();
  const id = E.createWorm(11, 0, 0, 0);
  // One chemical synapse doubled. Names and endpoints from the CSR tables.
  const k = 42;
  E.scaleWeight(id, 0, k, 2.0);
  E.developWorm(id);
  const d = driftOf(E, id, W);
  assert.ok(d, 'a mutated animal must report drift');
  assert.equal(d.moved, 1);
  assert.equal(d.top[0].fam, 0);
  assert.equal(d.top[0].k, k);
  assert.ok(Math.abs(d.top[0].log2 - 1) < 1e-12, 'doubling is one octave');
  assert.match(d.top[0].name, /^[A-Z][A-Z0-9]*→[A-Z][A-Z0-9]*$/);
  // Charged to both endpoints and nobody else.
  const [pre, post] = W.endpoints(0, k);
  for (let i = 0; i < W.nNeurons; i++) {
    if (i === pre || i === post) assert.ok(d.perNeuron[i] > 0.9, `endpoint ${i} uncharged`);
    else assert.equal(d.perNeuron[i], 0, `neuron ${i} charged for a synapse it lacks`);
  }
});

test('a gap junction drifts as one resistor: both mirrored entries move', () => {
  const E = engine();
  const id = E.createWorm(13, 0, 0, 0);
  const k = 10, mirror = E.gapMirror(k);
  E.scaleWeight(id, 1, k, 0.5);
  E.developWorm(id);
  const d = driftOf(E, id, W);
  const touched = new Set();
  // Rebuild the moved set from raw reads, then check drift agrees.
  for (let j = 0; j < W.counts[1]; j++) {
    if (Math.abs(Math.log2(E.getWeight(id, 1, j) / W.base[1][j])) > 0.01) touched.add(j);
  }
  assert.deepEqual([...touched].sort((a, b) => a - b), [k, mirror].sort((a, b) => a - b));
  assert.equal(d.moved, mirror === k ? 1 : 2);
  assert.match(W.nameOf(1, k), /⇄/);
});

test('a muscle-row weight charges only its presynaptic neuron', () => {
  const E = engine();
  const id = E.createWorm(17, 0, 0, 0);
  const k = 100;
  E.scaleWeight(id, 2, k, 1.7);
  E.developWorm(id);
  const d = driftOf(E, id, W);
  const [pre] = W.endpoints(2, k);
  assert.equal(d.moved, 1);
  assert.ok(d.perNeuron[pre] > 0);
  assert.equal(d.perNeuron.reduce((a, b) => a + (b > 0 ? 1 : 0), 0), 1);
  assert.match(W.nameOf(2, k), /→muscle row \d+$/);
});

test('neuronTopSynapses tells the hover story for exactly that neuron', () => {
  const E = engine();
  const id = E.createWorm(19, 0, 0, 0);
  const k = 42;
  E.scaleWeight(id, 0, k, 4.0);
  E.developWorm(id);
  const [pre, post] = W.endpoints(0, k);
  for (const n of [pre, post]) {
    const t = neuronTopSynapses(E, id, W, n);
    assert.equal(t.length, 1);
    assert.equal(t[0].k, k);
    assert.ok(Math.abs(t[0].log2 - 2) < 1e-12);
  }
  // A neuron the synapse does not touch hears nothing.
  const other = (post + 7) % W.nNeurons === pre ? (post + 8) % W.nNeurons : (post + 7) % W.nNeurons;
  assert.equal(neuronTopSynapses(E, id, W, other).length, 0);
});
