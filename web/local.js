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

/* The .wasm has the .model's byte offsets compiled into it, so they are a matched pair:
 * a new .wasm against a cached .model would not degrade gracefully, it would read the
 * wrong offsets. Both are cached hard, so both carry a content hash -- and the manifest
 * naming them is the one file that must not be cached. */
async function assetUrls() {
  try {
    const b = await fetch('build.json', { cache: 'no-cache' }).then((r) => r.json());
    return [`worm.model?v=${b['worm.model']}`, `worm.wasm?v=${b['worm.wasm']}`];
  } catch (e) {
    return ['worm.model', 'worm.wasm'];      // dev, served straight off disk
  }
}

/* How long stepping may take per animation frame, in milliseconds of *wall* time.
 *
 * This must be a wall-clock budget and not a cap on simulated time, and the difference is
 * not subtle. The first version capped the backlog at 0.25 s of simulation. On a machine
 * that runs two worms at 0.43x real time, 0.25 s of simulation costs 0.58 s to compute --
 * so every frame spent 580 ms stepping before drawing anything, which made the next
 * frame's elapsed time larger still. It settled at two frames a second and stayed there.
 *
 * With a wall budget the renderer always gets its turn: the animal runs at whatever
 * fraction of real time the machine can manage, the viewer says so honestly in SIM RATE,
 * and the page stays at 60 fps regardless. */
const BUDGET_MS = 7;
const CHUNK = 20;           // steps between clock checks; checking every step is not free

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
    const [modelUrl, wasmUrl] = await assetUrls();
    const [wasmBuf, modelBuf] = await Promise.all([
      fetch(wasmUrl).then((r) => r.arrayBuffer()),
      fetch(modelUrl).then((r) => r.arrayBuffer()),
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

  /* Worms come and go at runtime. They share the plate and the anatomy, so adding one
   * costs a few kB of state and nothing else -- the 302x302 matrices are read-only and
   * common to every animal. */
  addWorm() {
    const a = Math.random() * Math.PI * 2;
    const r = 2 + Math.random() * 9;
    const seed = (Math.random() * 0x7fffffff) | 0;
    this.worms.push(this.E.createWorm(seed, Math.cos(a) * r, Math.sin(a) * r,
                                      Math.random() * Math.PI * 2));
    return this.worms.length - 1;
  }
  removeWorm() {
    if (this.worms.length <= 1) return false;
    this.E.popWorm();
    this.worms.pop();
    return true;
  }
  reset(nWorms) {
    const n = nWorms || this.worms.length;
    this.E.clearWorms();
    this.E.resetWorld();
    this.worms = [];
    this.meta.world.patches = [];
    this._defaultPlate();
    for (let i = 0; i < n; i++) {
      const ang = (i / n) * Math.PI * 2;
      const r = i === 0 ? 0 : 3.5;
      this.worms.push(this.E.createWorm(1000 + i * 7717,
                                        Math.cos(ang) * r, Math.sin(ang) * r, ang + 0.6));
    }
    this._acc = 0;
  }

  /* Ablation applies to one animal, which is the interesting way round: kill AVB in one
   * worm and watch it next to an intact one in the same dish. */
  setAblated(wormIndex, indices) {
    const n = indices.length;
    if (!this._ablPtr || this._ablCap < n) {
      this._ablPtr = this.E.alloc(Math.max(16, n) * 4);
      this._ablCap = Math.max(16, n);
    }
    const view = new Int32Array(this.E.memory.buffer, this._ablPtr, Math.max(1, n));
    for (let i = 0; i < n; i++) view[i] = indices[i];
    this.E.setAblated(this.worms[wormIndex], this._ablPtr, n);
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
    const chunkT = this.dt * CHUNK;
    const t0 = performance.now();
    let steps = 0;
    while (this._acc >= chunkT) {
      this.E.stepAll(CHUNK);
      this._acc -= chunkT;
      steps += CHUNK;
      if (performance.now() - t0 >= BUDGET_MS) break;
    }
    if (steps === 0) return 0;
    // Whatever could not be afforded is *dropped*, not owed. Carrying the debt forward is
    // what turned a slow machine into a slideshow.
    if (this._acc > chunkT) this._acc = 0;
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
