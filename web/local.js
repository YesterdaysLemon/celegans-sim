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

import { makeWiring } from './weight-drift.js';
import { mulberry, loadSeed, DISH_STREAM } from './deal.js';

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

/* How much *wall* time each rate estimate is averaged over.
 *
 * Long enough that the chunk quantisation washes out -- one chunk is 10 ms of animal, so a
 * 60 Hz frame at 1x steps one chunk or two and a shorter window would read as a flutter
 * between 0.6x and 1.2x. Short enough that a stalled second shows up as a stalled second.
 *
 * Even the window used to be measured against the stepping clock: 0.4 s of *stepping* is
 * about 0.95 s of wall clock at a full 7 ms budget and 60 Hz, so the readout also updated
 * at less than half the rate this constant reads as. */
const RATE_WINDOW_S = 0.4;

export class LocalEngine {
  /* `clock` is the monotonic millisecond source used for the stepping budget and for the
   * compute half of the rate accounting. It defaults to performance.now(), which is what
   * the viewer wants and what the animation-frame timestamps handed to advance() share an
   * origin with; nothing in web/ passes anything else. It is a parameter at all so the
   * rate accounting can be driven by a scripted clock in tools/sim_rate.test.mjs -- the
   * numbers below are ratios of two times, and a test that measured them against the real
   * clock would be asserting how fast the machine running CI happens to be that day. */
  constructor(clock, opts) {
    this.ready = false;
    /* The deal stream: every random choice about the WORLD -- lawns, drops, spawn
     * seeds, headings -- draws from this seeded generator, so ?dish=N replays the
     * exact plate (web/deal.js). Reset re-deals from the same seed on purpose: reset
     * means "this dish again", the contract the arena always had. Sim noise is the
     * runtime's own and is untouched. */
    this.dealSeed = (opts && opts.dealSeed !== undefined ? opts.dealSeed : loadSeed()) >>> 0;
    this._deal = mulberry((this.dealSeed ^ DISH_STREAM.animal) >>> 0);
    this.running = true;
    this.rate = 1.0;
    /* Two rates, because there are two questions and this file used to answer the second
     * one under the first one's name (#56):
     *
     *   achieved     simulated seconds per *wall* second, end to end. This is the header's
     *                Sim rate, and it is the one that says whether the animal is keeping up
     *                with real time. The denominator is the whole frame -- stepping,
     *                rendering, compositing, idle, scheduling -- and backlog the budget
     *                threw away stays in it, because the wall clock does not care that we
     *                gave up on it.
     *   computeRate  simulated seconds per second spent *inside* the stepping loop.
     *                Headroom, not progress. 2.5x here beside 1.2x above means the machine
     *                could run this animal twice as fast again and is being held by the
     *                7 ms budget rather than by the model.
     *
     * They are not close. Dividing by stepping time alone reported a run that was plainly
     * advancing at 0.600x as 1.43x, and -- worse -- reported a 1000 ms frame that stepped
     * 140 ms of animal as 20x, because the stalled second never entered the denominator. */
    this.achieved = 0.0;
    this.computeRate = 0.0;
    this.worms = [];
    this.meta = null;
    this._acc = 0;
    this._last = 0;
    this._window = { steps: 0, wall: 0, cpu: 0 };
    this._now = clock || (() => performance.now());
    /* The reference dish's weather: a gentle baseline drift on the food and repellent
     * fields, same deterministic meander the arena's policy uses, so the plate reads
     * as a live place rather than a still life. The arena zeroes this -- its policy
     * owns its own wind -- and the header's Weather slider multiplies it live via
     * setWeather(). Dish physics, not animal model: the reference worm is untouched. */
    this.wind = 0.05;
    this._weatherT = 0;
    this._windMark = 0;
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
    /* The wiring kit for the drift view (#B): wild-type tables and CSR endpoint maps,
     * COPIED out of the payload -- views into wasm memory detach when the heap grows,
     * and these are constants. ~35 kB once per engine. */
    const pb = this._base;
    this.meta.wiring = makeWiring(head, (name, Type) => {
      const a = head.arrays[name];
      return new Type(this.E.memory.buffer.slice(pb + a.offset, pb + a.offset + a.bytes));
    });
    this._defaultPlate();

    for (let i = 0; i < nWorms; i++) {
      // Spread them out, point them different ways, and seed them fresh each load --
      // the fixed seeds meant every visitor's animal lived the same first minute.
      const ang = (i / nWorms) * Math.PI * 2;
      const r = i === 0 ? 0 : 3.5;
      this.worms.push(this.E.createWorm((this._deal() * 0x7fffffff) | 0,
                                        Math.cos(ang) * r, Math.sin(ang) * r,
                                        this._deal() * Math.PI * 2));
    }
    this.ready = true;
    this._last = this._now();
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
    /* A different plate every load. The fixed two-lawn layout meant every visitor saw
     * the same dish forever -- and saw it EMPTY, because both lawns sat outside the
     * 6.5 mm opening view and the first minute of a first visit was a worm in a void.
     * So: one lawn is always dealt close enough that its plume reaches the spawn (the
     * opening frame has something happening in it), the rest of the plate is dealt
     * fresh -- lawn count, positions, sizes, densities, and where the noxious drops
     * land. Attractant is dealt at 1.4-2.0, roughly twice the old 0.8-1.0: the plume
     * is the food field made visible, and it was too faint to read as weather began
     * moving it. Repellent keeps its distance from the spawn; being born in pain is
     * not a first impression. */
    const R = Math.min(20, (this.meta.world.radius || 25) - 5);
    const patches = [];
    const deal = (rMin, rMax) => {
      const a = this._deal() * Math.PI * 2;
      const d = rMin + this._deal() * (rMax - rMin);
      return [Math.cos(a) * d, Math.sin(a) * d];
    };
    // The near lawn: its plume's SHOULDER reaches the spawn, not its core. Getting a
    // field to read on screen took three tries, all on the record: attractant above
    // the image clamp (local.js fieldImage caps at 1.2) is a flat blue wall; a hotter
    // gamma washes the frame instead; and at the old 9 mm length scale nothing helps,
    // because the plume barely decays across a 6.5 mm view -- there is no gradient IN
    // FRAME to show. A ~5 mm scale decays visibly within the opening view, so the
    // plume reads as "coming from over there", which is what a plume is.
    {
      const r = 3.5 + this._deal() * 2.0;
      const [x, y] = deal(r + 3.5, r + 6.0);
      this.E.addFood(x, y, r, 0.9 + this._deal() * 0.2,
                     0.9 + this._deal() * 0.2, 5.0);
      patches.push({ x, y, r, kind: 'food' });
    }
    // The far field: one to three more lawns, spread over the plate.
    const extra = 1 + (this._deal() * 3 | 0);
    for (let i = 0; i < extra; i++) {
      const r = 3.0 + this._deal() * 4.0;
      const [x, y] = deal(9, R);
      this.E.addFood(x, y, r, 0.7 + this._deal() * 0.4,
                     0.8 + this._deal() * 0.3, 6.0);
      patches.push({ x, y, r, kind: 'food' });
    }
    // Something to avoid: one or two noxious drops, never near the spawn.
    const drops = 1 + (this._deal() < 0.4 ? 1 : 0);
    for (let i = 0; i < drops; i++) {
      const [x, y] = deal(8, R);
      this.E.addRepellent(x, y, 0.8 + this._deal() * 0.4, 5.0);
      patches.push({ x, y, r: 3.0, kind: 'repellent' });
    }
    this.meta.world.patches = patches;
  }

  /* Worms come and go at runtime. They share the plate, the anatomy and the runtime's
   * per-step scratch, so adding one costs state and nothing else -- but state is 240,304
   * bytes, 235 kB, of which 210,936 is the head-reflex delay line. Measured off the
   * allocator's per-worm stride by `node wasm/memory.mjs`; this comment claimed a few
   * kilobytes until #33 went and checked, and it was out by a factor of a hundred.
   *
   * A hundred animals is 22.8 MB and this button will not stop you, which is the right
   * policy for a viewer. Worth knowing that WebAssembly's memory.grow is one-way: a tab
   * that has once held a large population holds that much until it is closed. */
  addWorm() {
    const a = Math.random() * Math.PI * 2;
    const r = 2 + Math.random() * 9;
    const seed = (Math.random() * 0x7fffffff) | 0;
    this.worms.push(this.E.createWorm(seed, Math.cos(a) * r, Math.sin(a) * r,
                                      Math.random() * Math.PI * 2));
    return this.worms.length - 1;
  }
  /* Remove one animal -- by default the last, which is what the viewer's button wants,
   * but any of them. `this.worms` holds runtime handles rather than positions, so the
   * splice below re-indexes the viewer's own list without disturbing anyone's identity in
   * the runtime; a handle stays valid for the life of the animal it was issued for.
   *
   * The viewer keeps at least one animal on the plate because an empty dish is a blank
   * screen. That is a viewer policy, not a runtime one: the runtime will now go to zero,
   * because a generational loop has to be able to clear a population outright. */
  removeWorm(i) {
    if (this.worms.length <= 1) return false;
    const at = i === undefined ? this.worms.length - 1 : i;
    if (!Number.isInteger(at) || at < 0 || at >= this.worms.length) return false;
    this.E.removeWorm(this.worms[at]);
    this.worms.splice(at, 1);
    return true;
  }
  reset(nWorms) {
    const n = nWorms || this.worms.length;
    this.E.clearWorms();
    this.E.resetWorld();
    this.worms = [];
    this.meta.world.patches = [];
    this._deal = mulberry((this.dealSeed ^ DISH_STREAM.animal) >>> 0);
    this._defaultPlate();
    for (let i = 0; i < n; i++) {
      const ang = (i / n) * Math.PI * 2;
      const r = i === 0 ? 0 : 3.5;
      this.worms.push(this.E.createWorm((this._deal() * 0x7fffffff) | 0,
                                        Math.cos(ang) * r, Math.sin(ang) * r,
                                        this._deal() * Math.PI * 2));
    }
    this._acc = 0;
    this._weatherT = 0;
    this._windMark = 0;
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

  /* Drop a lawn, and say whether the plate took it.
   *
   * A lawn is not free any more. Since #48 a patch caches the two field shapes it sources
   * -- 1,048,576 bytes of them, four animals' worth -- so that eating it can dim the
   * attractant and the oxygen depression without recomputing 65,536 exponentials fifty
   * times a second. The runtime therefore caps the plate at 16 lawns and refuses past
   * that, and a viewer that pushed a marker regardless would be painting food that is not
   * on the plate. So the marker follows the runtime's own count, not the request. */
  dropFood(x, y, r = 2.5) {
    const before = this.E.foodPatchCount();
    this.E.addFood(x, y, r, 1.0, 1.0, 6.0);
    if (this.E.foodPatchCount() === before) return false;
    this.meta.world.patches.push({ x, y, r, kind: 'food' });
    return true;
  }
  /* The deposit mechanism spreads its amount as a TOTAL over the disc's grid cells --
   * ~128 of them at r 2.5 -- and the first shipping doses (0.5, 0.6 total) landed
   * 0.004 per cell against fields whose real features sit near 1.0. Invisible on the
   * layer, imperceptible to the animal: two bottles that measurably did nothing (the
   * owner squeezed them and asked). Doses are PER-CELL targets now, converted through
   * the grid geometry the model header declares, so a squeeze deposits what it looks
   * like it deposits whatever the grid resolution is. */
  _cellsIn(r) {
    const g = this.head.ints.world_grid;
    const h = (2 * this.head.scalars.world_extent) / g;
    return Math.max(1, Math.PI * r * r / (h * h));
  }
  /* The repellent bottle: straight into the live field -- no patch object, no cached
   * shapes, no 16-lawn cap -- because since the fields went dynamic the field IS the
   * state: it diffuses, decays and blows downwind, and the animals smell it through
   * the same sensedRep path as the seeded noxious drop. Dosed per-cell at ~0.7,
   * commensurate with the seeded drop's ~1.0 peak: strong enough to read and to
   * repel, small enough to fade instead of walling off the dish. */
  dropRepellent(x, y, r = 2.5) {
    this.E.depositRepellent(x, y, r, 0.7 * this._cellsIn(r));
    return true;
  }
  /* The rack's other two bottles, each a field source the plate already understands.
   * Crumbs are food with no colony behind them: straight into the live food field
   * (depositFood -- the corpse path), no patch, no plume, no slot against the 16-lawn
   * cap; the animal finds them by touch, which is its own small experiment. Dosed
   * per-cell at ~0.6 against a lawn's ~1.0, so the pile is visible and worth eating
   * (the eating rate is proportional to local density -- a thin smear feeds 250x
   * slower than it looks like it should). Scent is the mirror: a patch whose colony
   * is nearly foodless, so it smells like dinner and mostly is not -- it takes a
   * patch slot, because the plume machinery is the patch, and it refuses at the cap
   * the same way a lawn does. */
  dropCrumbs(x, y, r = 2.0) {
    this.E.depositFood(x, y, r, 0.6 * this._cellsIn(r));
    return true;
  }
  dropScent(x, y, r = 2.5) {
    const before = this.E.foodPatchCount();
    this.E.addFood(x, y, r, 0.05, 1.0, 6.0);
    if (this.E.foodPatchCount() === before) return false;
    this.meta.world.patches.push({ x, y, r, kind: 'scent' });
    return true;
  }
  poke(where, strength) {
    for (const w of this.worms) this.E.pokeWorm(w, where === 'anterior' ? 1 : 0, strength);
  }
  setMedium(ct, cn) { this.E.setMedium(ct, cn); }

  /* Advance by wall-clock time. Returns the number of simulated seconds actually run.
   *
   * `nowMs` is the animation frame's timestamp. Both rate readouts are accumulated here --
   * see the constructor for what each of them means and why they differ. */
  advance(nowMs) {
    if (!this.ready) return 0;
    // Floored at zero: a caller handing back a timestamp older than the last one would
    // otherwise credit negative wall time and inflate the rate.
    const elapsed = Math.max(0, (nowMs - this._last) / 1000);
    this._last = nowMs;
    const w = this._window;
    if (!this.running) {
      /* Paused time is not slow time, so it is charged to neither side of the ratio: 0x
       * while paused, and the window starts over on resume rather than carrying up to
       * RATE_WINDOW_S of pre-pause frames into the first estimate after it. Without the
       * reset, pausing during a 1.0x stretch and resuming with the slider at 0.2x reports
       * 0.90x for the first window on the far side -- almost entirely made of frames from
       * before the pause. */
      this.achieved = 0;
      this.computeRate = 0;
      w.steps = 0; w.wall = 0; w.cpu = 0;
      return 0;
    }
    // The *accumulator* is capped at half a second: a frame longer than that is asking for
    // more animal than any budget will step, and owing it forward is what turned a slow
    // machine into a slideshow. The rate window below is deliberately not capped the same
    // way -- see there.
    this._acc += Math.min(elapsed, 0.5) * this.rate;
    const chunkT = this.dt * CHUNK;
    const t0 = this._now();
    let steps = 0;
    while (this._acc >= chunkT) {
      this.E.stepAll(CHUNK);
      this._acc -= chunkT;
      steps += CHUNK;
      if (this._now() - t0 >= BUDGET_MS) break;
    }
    // Whatever could not be afforded is *dropped*, not owed. Carrying the debt forward is
    // what turned a slow machine into a slideshow. (Not reachable with steps === 0: the
    // loop only exits early once it has run at least one chunk, so `_acc < chunkT` here.)
    if (this._acc > chunkT) this._acc = 0;
    /* Every frame's wall time goes into the denominator, stepped or not, and uncapped.
     *
     * Stepped or not: at 0.2x a 60 Hz frame asks for 3.3 ms of animal against a 10 ms
     * chunk, so two frames in three step nothing at all. Returning early on those -- which
     * this used to do -- leaves only the frames that did work in the denominator and
     * reports 0.6x for a run that is advancing at 0.2x by anyone's clock.
     *
     * Uncapped: a 1000 ms frame really is a second during which the animal advanced 140 ms,
     * and saying so is the entire job of this number. It is the accumulator that must not
     * chase that second, not the measurement of it. One outlier frame flushes the window
     * immediately (it is longer than the window), so the readout recovers on the next one
     * rather than smearing the stall over the following second. */
    w.wall += elapsed;
    w.steps += steps;
    // Floored, because a clock with millisecond resolution can time a 20-step chunk as
    // zero and the compute rate is not infinite, it is unmeasured.
    if (steps) w.cpu += Math.max((this._now() - t0) / 1000, 1e-6);
    if (w.wall > RATE_WINDOW_S) {
      this.achieved = w.steps * this.dt / w.wall;
      this.computeRate = w.cpu > 0 ? w.steps * this.dt / w.cpu : 0;
      w.steps = 0; w.wall = 0; w.cpu = 0;
    }
    this._windPass(steps * this.dt);
    return steps * this.dt;
  }

  /* The weather pass: direction meanders on two incommensurate slow clocks, magnitude
   * breathes on a third -- the arena policy's exact formula, driven here by accumulated
   * simulated time. Deterministic in dish time and touching no rng; at most one field
   * advection a simulated second, which is what the fields can absorb for free. */
  _windPass(ran) {
    // The scripted-clock rate test drives this engine with a stub runtime that has no
    // fields; an engine with nothing to drift has no weather rather than an error.
    if (ran <= 0 || this.wind <= 0 || !this.ready || !this.E.driftFields) return;
    this._weatherT += ran;
    const dt = this._weatherT - this._windMark;
    if (dt < 1.0) return;
    this._windMark = this._weatherT;
    const t = this._weatherT;
    const dir = 2 * Math.PI * (t / 173.0) + 0.8 * Math.sin(t / 41.0);
    const mag = this.wind * (0.55 + 0.45 * Math.sin(t / 67.0));
    this.E.driftFields(Math.cos(dir) * mag * dt, Math.sin(dir) * mag * dt);
  }

  /* The header's Weather slider: a live multiplier on the dish's baseline wind. */
  setWeather(x) {
    if (this._wind0 === undefined) this._wind0 = this.wind;
    this.wind = this._wind0 * Math.max(0, x);
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
      eggsHeld: E.getEggsHeld(w),
      eggsLaid: E.getEggsLaid(w),
      vulva: E.getVulvalMuscle(w),
      eglActive: E.getEglActive(w),
      asleep: E.wormAsleep(w),
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

  /* Every egg on the plate, as a flat x,y list. Read straight out of linear memory: the
   * runtime keeps them in a dense bounded array, slots 0..eggCount, so this is a view
   * rather than a copy until the caller wants one. Shared by all the animals, because the
   * dish is.
   *
   * Each egg also carries its parent, its lay time and a copy of that parent's genome --
   * see eggParent/eggTime/eggGene/hatchEgg on the runtime. None of that is needed to draw
   * a dot, which is why it is not read here. */
  eggs() {
    const E = this.E, n = E.eggCount();
    if (!n) return null;
    return {
      n,
      x: new Float64Array(E.memory.buffer, E.ptrEggX(), n),
      y: new Float64Array(E.memory.buffer, E.ptrEggY(), n),
    };
  }

  /* The chemical fields as one RGB image, at the world grid's own resolution.
   *
   * This used to downsample to the 128x128 the server historically sent, by taking
   * every second cell -- skip-sampling, not averaging. Nobody noticed for as long as
   * the reference dish was the only dish: its lawns are 5-7 mm across and mostly
   * looked at from inside at 6.5 mm span, where a halved field grid still blurs into
   * gradient under the canvas's bilinear scaling. The arena broke the disguise -- small
   * 3-4 mm lawns, the whole plate in frame -- and its lawn edges came out staircased,
   * because the ~1 mm smoothstep skirt of a lawn is barely one cell wide at 128. Same
   * inherited code path in both dishes; a resolution choice that was only ever tested
   * against one of them. Native resolution doubles the cells across that skirt and the
   * bilinear upscale has enough to work with; the rebuild is cached behind
   * S.field.stamp at about once a second, so the cost of the larger image is nothing
   * per frame. `size` remains for callers that genuinely want the old thumbnail. */
  fieldImage(size) {
    const E = this.E, buf = E.memory.buffer;
    const g = this.head.ints.world_grid;
    const step = Math.max(1, Math.ceil(g / (size || g)));
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
