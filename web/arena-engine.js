/* The arena as an engine the viewer can plug in.
 *
 * This is the whole point of the source seam: LocalEngine already presents everything
 * loop.js consumes -- advance(), frame(i), eggs(), fieldImage(), meta -- so the arena is
 * that surface plus policy, by inheritance. The panels, the kymograph, the traces, the
 * ablation tools and the scrubber all work on an evolved animal because they only ever
 * wanted numbers, and an evolved animal has all the same numbers. Nobody had ever seen
 * inside a mutant before this class existed; now clicking one lights up its 302 neurons.
 *
 * TRACK B: this dish is the departure track. Nothing in it is a claim about C. elegans,
 * and the header chrome says so whenever this engine is the one on stage.
 *
 * What differs from the reference dish, and only this:
 *   * the plate is the arena's three-lawn economy, never restocked;
 *   * founders are wild-type clones; every hatchling mutates (genes + morphology);
 *   * death exists -- starvation with the cap as backstop -- and feeds the plate;
 *   * frames carry per-worm style (dynasty hue, energy dim, width profile) the dish
 *     renders, and dishStats() feeds the arena's own header tiles.
 */

import { LocalEngine } from './local.js';
import { makeArena } from './arena-policy.js';

/* The browser dish's defaults: metabolism, morphology mutation, corpse rot, lawn
 * regrowth, juvenile development and WEATHER all on, because this dish is the showcase
 * -- the plate economy and the drifting bodies are what it is FOR. The tax is set to
 * BITE (metabT 150, lawns at 60% density against a slow regrowth tap; the owner
 * watched a dish idle at energy 0.99 with zero starvations and called it correctly:
 * too much food on average). Starting conditions are RANDOMISED per load -- a fresh
 * seed, lawns jittered around the reference layout -- so no two browser dishes tell
 * the same story; the node driver keeps fixed defaults for controlled, replayable
 * runs, and both read the same makeArena. */
function browserOpts() {
  const jit = (v, r) => v + (Math.random() * 2 - 1) * r;
  return {
    metab: 0.1, metabT: 150, mmut: 0.08,
    /* Heritable wiring, on for the showcase since the drift view exists to watch it:
     * every hatchling takes lognormal nudges on 4 of its 3,935 synapses. */
    wmut: 0.12, wmutN: 4,
    /* Sex, on for the showcase: hatchlings recombine with the nearest neighbour, so
     * the dynasties a visitor watches are mixing lineages, not just mutating clones. */
    recomb: 1.0, recombR: 9,
    rotT: 45, regrow: 0.02, juvenile: 0.55, growT: 90,
    wind: 0.03, lawnScale: 0.6,
    seed: (Math.random() * 0x7fffffff) | 0,
    lawns: [
      { x: jit(-8, 3), y: jit(5, 3), r: jit(4, 0.8), d: 1.0 },
      { x: jit(7, 3), y: jit(-4, 3), r: jit(4, 0.8), d: 1.0 },
      { x: jit(0, 3), y: jit(9, 3), r: jit(3, 0.6), d: 0.8 },
    ],
  };
}

const HUE = (f) => (f < 0 ? 0 : 40 + f * 77) % 360;
export const dynastyHue = HUE;   // the lineage panel colours branches the way the dish does

export class ArenaEngine extends LocalEngine {
  constructor(clock, options) {
    super(clock);
    this.dynastyHue = HUE;
    this.options = Object.assign(browserOpts(), options || {});
    this.simT = 0;
    this._policyT = 0;
    this._widthCache = new Map();      // worm id -> per-node width factors, built at birth
    this.arena = null;
  }

  /* A separate WebAssembly instance from the reference dish's, on purpose: two plates,
   * two worlds. super.init(0) does the whole load-and-wire dance and creates nobody;
   * the arena then seeds its own plate and founders through policy. */
  async init() {
    await super.init(0);
    this.E.setNoise(1);
    this._wirePolicy();
    this.meta.arena = true;            // the one flag chrome may key Track B labels on
    return this;
  }

  /* Build the policy with a fresh seeded stream and wire its callbacks into this
   * engine's bookkeeping. One home, used by init and reset, because a replayable dish
   * is one where those two paths cannot drift. meta.genes rides the model header, which
   * LocalEngine._buildMeta does not copy, so the header itself is handed over. */
  _wirePolicy() {
    let rs = (this.options.seed ?? 1) >>> 0;
    const rand = () => {
      rs = (rs + 0x6D2B79F5) >>> 0;
      let t = Math.imul(rs ^ (rs >>> 15), 1 | rs);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const normal = () => {
      const u = Math.max(rand(), 1e-12), v = rand();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    };
    const midOf = (id) => {
      const f = new Float64Array(this.E.memory.buffer);
      return [f[(this.E.ptrNodesX(id) >> 3) + 24], f[(this.E.ptrNodesY(id) >> 3) + 24]];
    };
    this.arena = makeArena(this.E, { genes: this.head.genes || [],
                                     scalars: this.head.scalars },
                           this.options, rand, normal, midOf);
    this.arena.onBirth = (id) => {
      this.worms.push(id);
      this._buildWidth(id);
    };
    this.arena.onDeath = (id) => {
      const at = this.worms.indexOf(id);
      if (at >= 0) this.worms.splice(at, 1);
      this._widthCache.delete(id);
    };
    // A growth step rescales the animal's whole morphology, so its cached width profile
    // is stale the moment it fires.
    this.arena.onGrowth = (id) => this._buildWidth(id);
    this.meta.world.patches = this.arena.seedPlate();
    this.arena.spawnFounders();
  }

  /* The reference plate's lawns and drop do not belong here; the policy seeds its own.
   * Overridden to nothing rather than skipped, so super.init stays one code path. */
  _defaultPlate() { this.meta.world.patches = []; }

  /* Per-node width factors from the four width control points, built once per animal --
   * morphology is set at hatch and never after, so this cannot go stale. Node k's
   * position along the body is k / (nNodes - 1). Reference-shaped animals get no entry
   * and draw at the anatomy's own radius. */
  _buildWidth(id) {
    if (!this.E.hasOwnMorphology(id)) return;
    // Drawn width is the EFFECTIVE width: genome times developmental scale, matching
    // what the mechanics were built from -- a juvenile looks as small as it is.
    const dev = this.E.getDevelopment(id);
    const cp = [this.E.getMorph(id, 4) * dev, this.E.getMorph(id, 5) * dev,
                this.E.getMorph(id, 6) * dev, this.E.getMorph(id, 7) * dev];
    const n = this.nNodes;
    const w = new Float32Array(n);
    for (let k = 0; k < n; k++) {
      const t = Math.min(2.999, (k / (n - 1)) * 3);
      const seg = Math.floor(t), f = t - seg;
      w[k] = cp[seg] + f * (cp[seg + 1] - cp[seg]);
    }
    this._widthCache.set(id, w);
  }

  /* Step physics on the wall-clock budget the parent owns, then run policy on the
   * simulated time that actually elapsed -- four passes a simulated second, matching the
   * node driver's cadence closely enough that neither starves eggs nor spams the
   * reaper. */
  advance(nowMs) {
    const ran = super.advance(nowMs);
    if (ran > 0 && this.arena) {
      this.simT += ran;
      if (this.simT - this._policyT >= 0.25) {
        this._policyT = this.simT;
        this.arena.tick(this.simT);   // reap, hatch, regrow, rot, grow
      }
      if (!this._intakeT || this.simT - this._intakeT > 8) {
        this._intakeT = this.simT;
        this.arena.markIntake();
      }
    }
    return ran;
  }

  /* The parent's frame, plus what the arena knows about this animal: identity for the
   * trails-by-id bookkeeping, and style for the dish -- dynasty hue, energy dim, the
   * inherited width profile. */
  frame(i = 0) {
    const f = super.frame(i);
    const id = this.worms[i];
    f.id = id;
    const founder = this.arena ? (this.arena.founderOf.get(id) ?? -1) : -1;
    const e = this.options.metab > 0
      ? Math.max(0, Math.min(1, this.E.getEnergy(id) / this.options.metab)) : 1;
    f.style = { hue: HUE(founder), dim: e };
    const w = this._widthCache.get(id);
    if (w) f.widthScale = w;
    return f;
  }

  /* The arena's own header tiles. The per-animal tiles (speed, pumping, eaten) stay
   * live for the focused animal through the ordinary path. */
  dishStats() {
    const a = this.arena;
    const pop = this.E.wormCount();
    let meanE = 0;
    if (this.options.metab > 0 && pop > 0) {
      for (const id of this.worms) meanE += this.E.getEnergy(id);
      meanE /= pop * this.options.metab;
    }
    return {
      population: pop,
      cap: a.opt.cap,
      eggs: this.E.eggCount(),
      births: a.births,
      deaths: a.deaths,
      starved: a.starved,
      meanE,
      dynasties: a.dynasties()
        .map(([f, n]) => `${f < 0 ? 'or' : 'F' + f}:${n}`).join(' '),
    };
  }

  corpses() { return this.arena ? this.arena.corpses : null; }

  /* The weather knob: a live multiplier on the dish's baseline wind. The wind pass
   * reads opt.wind every tick and the drift clocks are deterministic functions of dish
   * time, so this neither forks the seeded mutation stream nor desynchronises a replay
   * beyond the wind itself -- turning the knob is weather, not a new dish. */
  setWeather(x) {
    if (!this.arena) return;
    if (this._wind0 === undefined) this._wind0 = this.arena.opt.wind;
    this.arena.opt.wind = this._wind0 * Math.max(0, x);
  }

  /* The viewer's +/- buttons, rerouted through the dish's own rules: a new animal is a
   * fresh wild-type founder (fed, so the reaper does not eat the button press), and a
   * removal is a death like any other -- it feeds the plate. */
  addWorm() {
    const a = Math.random() * Math.PI * 2;
    const r = 2 + Math.random() * 7;
    const id = this.E.createWorm((Math.random() * 0x7fffffff) | 0,
                                 Math.cos(a) * r, Math.sin(a) * r,
                                 Math.random() * Math.PI * 2);
    if (this.options.metab > 0) {
      this.E.setMetabolism(id, this.options.metab, this.arena.opt.basal,
                           this.arena.opt.workC, this.arena.opt.metabFloor,
                           this.arena.opt.metabKnee, 1.0);
    }
    this.arena.founderOf.set(id, -1);
    this.arena.eatenAt.set(id, 0.0);
    this.worms.push(id);
    return this.worms.length - 1;
  }

  removeWorm(i) {
    if (this.worms.length <= 1) return false;
    const at = i === undefined ? this.worms.length - 1 : i;
    if (!Number.isInteger(at) || at < 0 || at >= this.worms.length) return false;
    this.arena.die(this.worms[at], 'culled');   // onDeath splices this.worms
    return true;
  }

  /* Reset: a fresh dish, same seed, same story -- the arena's replay property is the
   * seeded rng, so a reset rebuilds the policy from scratch rather than patching
   * state. */
  reset() {
    this.E.clearWorms();
    this.E.resetWorld();
    this.worms = [];
    this._widthCache.clear();
    this.simT = 0;
    this._policyT = 0;
    this._intakeT = 0;
    this._acc = 0;
    this._wirePolicy();
  }
}
