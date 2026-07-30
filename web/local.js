/* The local engine: the animal runs here, in your browser.
 *
 * There is no simulation server in this mode. The page loads a .wasm (the step functions)
 * and a .model (everything Python precomputed once -- the resting-potential solve, the
 * muscle balance, the receptive fields, the drag masks) and steps the worm itself. That
 * is why every visitor gets their own, and why a second one in the same dish is nearly
 * free: the 302x302 matrices are anatomy, identical for every animal, so only the state
 * duplicates.
 *
 * It presents the same shape the WebSocket feed did -- a `hello` describing the animal
 * and a stream of frames -- so the viewer does not have to care which it is talking to.
 */

const MODEL_URL = 'worm.model';
const WASM_URL = 'worm.wasm';

// Keep the wall clock and the simulated clock in step, but never try to catch up more
// than a moment's worth: a backgrounded tab returns with a huge elapsed time, and
// sprinting through thirty seconds of simulation to "catch up" just locks the page.
const MAX_CATCHUP = 0.25;   // s of simulated time per animation frame

export class LocalEngine {
  constructor() {
    this.ready = false;
    this.running = true;
    this.rate = 1.0;
    this.achieved = 0.0;
    this.worms = [];
    this.meta = null;
    this._acc = 0;
    this._last = 0;
    this._window = { steps: 0, t: 0 };
  }

  async init(nWorms = 2) {
    const [wasmBuf, modelBuf] = await Promise.all([
      fetch(WASM_URL).then((r) => r.arrayBuffer()),
      fetch(MODEL_URL).then((r) => r.arrayBuffer()),
    ]);

    // model file: 'WORM' + version, u32 header length, JSON header, raw payload
    const dv = new DataView(modelBuf);
    const headLen = dv.getUint32(8, true);
    const head = JSON.parse(new TextDecoder().decode(new Uint8Array(modelBuf, 12, headLen)));
    const payload = new Uint8Array(modelBuf, 12 + headLen);

    const { instance } = await WebAssembly.instantiate(wasmBuf, {
      env: {
        abort(_m, _f, line, col) { throw new Error(`wasm abort ${line}:${col}`); },
        seed: () => Date.now(),
      },
    });
    this.E = instance.exports;
    // Align the payload to 8 bytes. WebAssembly loads do not care, but the viewer takes
    // Float64Array views straight into linear memory and those must be aligned -- so the
    // arrays are padded on the Python side and the base is rounded up here.
    const raw = this.E.alloc(payload.length + 8);
    const ptr = (raw + 7) & ~7;
    new Uint8Array(this.E.memory.buffer).set(payload, ptr);
    this.E.setPayload(ptr);
    this.E.initWorld();
    this._base = ptr;

    this.head = head;
    this.dt = head.scalars.dt;
    this.n = head.ints.n_neurons;
    this.nMus = head.ints.n_muscles;
    this.nNodes = head.ints.n_nodes;
    this.nJoints = head.ints.n_joints;

    this._buildMeta(head);
    this._defaultPlate();

    for (let i = 0; i < nWorms; i++) {
      // Spread them out and point them different ways, so two worms do not start life as
      // one worm drawn twice.
      const ang = (i / nWorms) * Math.PI * 2;
      const r = i === 0 ? 0 : 3.5;
      this.worms.push(this.E.createWorm(1000 + i * 7717,
                                        Math.cos(ang) * r, Math.sin(ang) * r, ang + 0.6));
    }
    this.ready = true;
    this._last = performance.now();
    return this;
  }

  _buildMeta(head) {
    const split = (k) => (head.strings[k] || '').split('\n');
    const names = split('neuron_names');
    const cls = split('neuron_cls'), kind = split('neuron_kind');
    const gang = split('neuron_ganglion'), modality = split('neuron_modality');
    const tx = split('neuron_tx');
    const inhOff = head.arrays.neuron_inh.offset;
    const payloadBase = this._base;
    const inhArr = new Uint8Array(this.E.memory.buffer, payloadBase + inhOff, names.length);
    const somaOff = head.arrays.soma_pos.offset;
    const soma = new Float64Array(this.E.memory.buffer, payloadBase + somaOff, names.length);

    this.meta = {
      neurons: names.map((nm, i) => ({
        name: nm, cls: cls[i] || '', kind: kind[i] || '', ganglion: gang[i] || '',
        modality: modality[i] || '', tx: tx[i] || '', inh: !!inhArr[i],
        pos: soma[i],
      })),
      muscles: split('muscle_names').map((nm) => ({ name: nm })),
      n_nodes: this.nNodes,
      n_joints: this.nJoints,
      radius: null,
      world: { radius: head.scalars.world_extent, patches: [], obstacles: [] },
      counts: { chem: 2279, gap: 552, nmj: 0 },
      local: true,
    };
    // Body radius profile, for drawing.
    const rOff = head.arrays.body_radius.offset;
    const nSeg = head.arrays.body_radius.shape[0];
    this.meta.radius = Array.from(
      new Float64Array(this.E.memory.buffer, payloadBase + rOff, nSeg));
    this.meta.muscleIndex = {};
    this.meta.muscles.forEach((mu, i) => { this.meta.muscleIndex[mu.name] = i; });
  }

  _defaultPlate() {
    // The dish the server used to build: a couple of lawns and one noxious drop, so there
    // is something to find and something to avoid.
    this.E.addFood(-14.0, 8.0, 7.0, 1.0, 1.0, 9.0);
    this.E.addFood(16.0, -10.0, 5.0, 0.8, 0.8, 9.0);
    this.E.addRepellent(6.0, 14.0, 0.9, 5.0);
    this.meta.world.patches = [
      { x: -14.0, y: 8.0, r: 7.0, kind: 'food' },
      { x: 16.0, y: -10.0, r: 5.0, kind: 'food' },
      { x: 6.0, y: 14.0, r: 3.0, kind: 'repellent' },
    ];
  }

  dropFood(x, y, r = 2.5) {
    this.E.addFood(x, y, r, 1.0, 1.0, 6.0);
    this.meta.world.patches.push({ x, y, r, kind: 'food' });
  }
  poke(where, strength) {
    for (const w of this.worms) this.E.pokeWorm(w, where === 'anterior' ? 1 : 0, strength);
  }
  setMedium(ct, cn) { this.E.setMedium(ct, cn); }

  /* Advance by wall-clock time. Returns the number of simulated seconds actually run,
   * which is what the viewer reports as the achieved rate. */
  advance(nowMs) {
    if (!this.ready) return 0;
    const wall = Math.min((nowMs - this._last) / 1000, 0.5);
    this._last = nowMs;
    if (!this.running) { this.achieved = 0; return 0; }
    this._acc += wall * this.rate;
    if (this._acc > MAX_CATCHUP) this._acc = MAX_CATCHUP;
    const steps = Math.floor(this._acc / this.dt);
    if (steps <= 0) return 0;
    this._acc -= steps * this.dt;
    const t0 = performance.now();
    this.E.stepAll(steps);
    const spent = (performance.now() - t0) / 1000;
    this._window.steps += steps;
    this._window.t += Math.max(spent, 1e-6);
    if (this._window.t > 0.4) {
      this.achieved = this._window.steps * this.dt / this._window.t;
      this._window.steps = 0; this._window.t = 0;
    }
    return steps * this.dt;
  }

  /* One worm's state, as typed views straight into linear memory. No copying: these are
   * live windows, so they must be re-taken whenever the heap may have grown. */
  frame(i = 0) {
    const w = this.worms[i];
    const E = this.E, buf = E.memory.buffer;
    const nx = new Float64Array(buf, E.ptrNodesX(w), this.nNodes);
    const ny = new Float64Array(buf, E.ptrNodesY(w), this.nNodes);
    const nodes = new Float32Array(this.nNodes * 2);
    for (let k = 0; k < this.nNodes; k++) { nodes[k * 2] = nx[k]; nodes[k * 2 + 1] = ny[k]; }
    return {
      t: E.getTime(w),
      nodes,
      act: new Float64Array(buf, E.ptrAct(w), this.n),
      V: new Float64Array(buf, E.ptrV(w), this.n),
      tension: new Float64Array(buf, E.ptrTension(w), this.nMus),
      kappa: new Float64Array(buf, E.ptrKappa(w), this.nJoints),
      food: E.getEaten(w),
      dir: E.getGateForward(w) > 0.5 ? 1 : -1,
      pumpRate: E.getPumpRate(w),
      pumping: E.getPumping(w),
      lumen: E.getLumen(w),
      sensed: {
        attractant: E.getSensed(w, 0), temperature: E.getSensed(w, 1),
        oxygen: E.getSensed(w, 2), food: E.getSensed(w, 3),
        touch: E.getSensed(w, 4), repellent: E.getSensed(w, 5),
        habituation: E.getSensed(w, 6),
        gateF: E.getGateForward(w), gateB: 1 - E.getGateForward(w),
      },
      running: this.running ? 1 : 0,
      achieved: this.achieved,
    };
  }

  /* The chemical fields, downsampled to the same 128x128 RGB the server used to send, so
   * the viewer's field rendering works unchanged. */
  fieldImage(size = 128) {
    const E = this.E, buf = E.memory.buffer;
    const g = this.head.ints.world_grid;
    const step = Math.max(1, Math.ceil(g / size));
    const n = Math.ceil(g / step);
    const att = new Float64Array(buf, E.ptrAttractant(), g * g);
    const food = new Float64Array(buf, E.ptrFood(), g * g);
    const rep = new Float64Array(buf, E.ptrRepellent(), g * g);
    const out = new Uint8Array(n * n * 3);
    let k = 0;
    for (let i = 0; i < n; i++) {
      const row = Math.min(g - 1, i * step) * g;
      for (let j = 0; j < n; j++) {
        const c = row + Math.min(g - 1, j * step);
        out[k++] = Math.max(0, Math.min(255, (att[c] / 1.2) * 255));
        out[k++] = Math.max(0, Math.min(255, food[c] * 255));
        out[k++] = Math.max(0, Math.min(255, rep[c] * 255));
      }
    }
    return { n, data: out };
  }
}
