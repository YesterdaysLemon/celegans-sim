/* The arena's policy, in one place, for every driver.
 *
 * The runtime provides mechanism (layEgg, hatchEgg, removeWorm, setMetabolism,
 * setMorphology, depositFood); this module owns the decisions a dish cannot make --
 * incubation, mutation at hatch, death by starvation with the cap as backstop, corpses
 * becoming food where they fell -- exactly as argued in wasm/arena.mjs's header, which
 * remains the essay of record. It exists because the policy used to live twice, once in
 * the node driver and once inlined in the browser page, and the two had to be edited in
 * lockstep by hand. Three drivers now import it: wasm/arena.mjs (node), the in-viewer
 * ArenaEngine (web/arena-engine.js), and anything a test wants to build.
 *
 * TRACK B, as ever: nothing this module produces is a claim about C. elegans.
 *
 * The module is deliberately dependency-free and environment-free -- no process.env, no
 * DOM, no fetch -- so node and the browser import the same bytes. Randomness comes in
 * from the caller, because the node driver's seeded rng must keep replaying its recorded
 * runs bit for bit.
 */

/* Every knob, with the same defaults the node driver documents. `metabCorpse` defaults
 * to half the store capacity -- a body is worth about half a full stomach -- and 0 when
 * metabolism is off, which keeps the plain dish exactly the old plain dish. */
export function resolveOptions(o = {}) {
  const metab = o.metab ?? 0.0;
  return {
    cap: o.cap ?? 10,
    founders: o.founders ?? 4,
    mut: o.mut ?? 0.10,
    incubation: o.incubation ?? 60,
    wmut: o.wmut ?? 0.0,
    wmutN: o.wmutN ?? 3,
    mmut: o.mmut ?? 0.0,
    metab,
    metabT: o.metabT ?? 240,
    metabWorkP: o.metabWorkP ?? 2.0,
    metabFloor: o.metabFloor ?? 0.25,
    metabKnee: o.metabKnee ?? 0.35,
    metabHatch: o.metabHatch ?? 0.6,
    corpse: o.corpse ?? (metab > 0 ? metab * 0.5 : 0.0),
    corpseYield: o.corpseYield ?? 0.8,
    corpseR: o.corpseR ?? 0.8,
    seed: o.seed ?? 1,
    basal: metab > 0 ? metab / (o.metabT ?? 240) : 0,
    workC: metab > 0 ? (metab / (o.metabT ?? 240)) / (o.metabWorkP ?? 2.0) : 0,
  };
}

/* The gene clamp, shared verbatim with wasm/evolve.mjs: gate bias is the one gene with
 * a meaningful sign, everything else is a gain or a time and stays non-negative. */
export const clampGene = (name, v) => (name === 'sen_gate_bias' ? v : Math.max(0, v));

/* One dish's policy state and passes. `E` is the runtime's exports; `meta` must carry
 * `genes` (the heritable-scalar names) and `scalars` (for per-gene mutation scale);
 * `rand`/`normal` are the caller's seeded generators -- consumed in a fixed order
 * (hatch heading, then genes, then weights, then morphology) so a seeded run replays.
 *
 * The caller owns worm bookkeeping outside the dish (a viewer's handle list, a driver's
 * ledger), so births and deaths surface through the `onBirth`/`onDeath` callbacks; the
 * policy never reaches into anyone else's arrays. */
export function makeArena(E, meta, options, rand, normal, midOf) {
  const opt = resolveOptions(options);
  // Per-gene mutation scale. A caller with its own table (the node driver reuses
  // evolve.mjs's) passes it as meta.scaleOf; otherwise the model header's scalars serve,
  // which is the same arithmetic against the same numbers.
  const scaleOf = meta.scaleOf || ((name) => Math.abs(meta.scalars[name]) || 1.0);
  const genes = meta.genes || [];

  const arena = {
    opt,
    founderOf: new Map(),      // worm id -> founder index (-1: parent culled first)
    eatenAt: new Map(),        // worm id -> intake at the last accounting pass
    corpses: [],               // { x, y, worth, t } -- the ledger of deaths, for drawing
    simT: 0.0,
    births: 0,
    deaths: 0,
    starved: 0,
    iota: 1000,                // hatchling seed offset, monotonic
    onBirth: null,             // (id, parentId) => void
    onDeath: null,             // (id, cause: 'starved' | 'culled') => void
  };

  const metabolise = (id, fill) => {
    if (opt.metab > 0) {
      E.setMetabolism(id, opt.metab, opt.basal, opt.workC,
                      opt.metabFloor, opt.metabKnee, fill);
    }
  };

  /* Three lawns, never restocked: the plate is the whole economy. Returns the patch
   * list so a viewer can hand it to its minimap. */
  arena.seedPlate = () => {
    E.addFood(-8.0, 5.0, 4.0, 1.0, 1.0, 9.0);
    E.addFood(7.0, -4.0, 4.0, 1.0, 1.0, 9.0);
    E.addFood(0.0, 9.0, 3.0, 1.0, 0.8, 8.0);
    return [
      { x: -8.0, y: 5.0, r: 4.0, kind: 'food' },
      { x: 7.0, y: -4.0, r: 4.0, kind: 'food' },
      { x: 0.0, y: 9.0, r: 3.0, kind: 'food' },
    ];
  };

  /* Wild-type clones on a ring, fed. Everything after them is descent with
   * modification. */
  arena.spawnFounders = () => {
    for (let i = 0; i < opt.founders; i++) {
      const a = (2 * Math.PI * i) / opt.founders;
      const id = E.createWorm(opt.seed + i,
                              6.0 * Math.cos(a), 6.0 * Math.sin(a), a + Math.PI / 2);
      metabolise(id, 1.0);
      arena.founderOf.set(id, i);
      arena.eatenAt.set(id, 0.0);
      if (arena.onBirth) arena.onBirth(id, -1);
    }
  };

  /* Every death routes through here, so every death feeds the plate: the body plus a
   * yield on whatever store was left -- a culled well-fed animal outfeeds a starved
   * husk. `midOf(id)` is the caller's midpoint reader (node 24, G.N_LINKS >> 1). */
  function die(id, cause) {
    const worth = opt.corpse + (opt.metab > 0 ? opt.corpseYield * E.getEnergy(id) : 0);
    if (worth > 0) {
      const [x, y] = midOf(id);
      E.depositFood(x, y, opt.corpseR, worth);
      arena.corpses.push({ x, y, worth, t: arena.simT });
    }
    E.removeWorm(id);
    arena.founderOf.delete(id);
    arena.eatenAt.delete(id);
    arena.deaths++;
    if (cause === 'starved') arena.starved++;
    if (arena.onDeath) arena.onDeath(id, cause);
  }
  arena.die = die;

  const ids = () => Array.from({ length: E.wormCount() }, (_, k) => E.wormIdAt(k));
  arena.ids = ids;

  arena.cullTo = (cap) => {
    while (E.wormCount() > cap) {
      let worstId = -1, worstIntake = Infinity;
      for (const id of ids()) {
        const recent = E.getEaten(id) - (arena.eatenAt.get(id) ?? 0);
        if (recent < worstIntake) { worstIntake = recent; worstId = id; }
      }
      die(worstId, 'culled');
    }
  };

  /* Death by physiology: a store at zero is a body that stopped. Only meaningful with
   * the budget on; without it the cull is the only death, as it always was. */
  arena.reap = () => {
    if (opt.metab <= 0) return;
    for (const id of ids()) {
      if (E.getEnergy(id) <= 0.0) die(id, 'starved');
    }
  };

  /* Hatch everything due, walking backwards because hatchEgg swap-pops the egg array.
   * Mutation order is FIXED -- genes, then weights, then morphology -- because the
   * drivers share one seeded stream and reordering it silently forks every recorded
   * run. */
  arena.hatchDue = () => {
    for (let i = E.eggCount() - 1; i >= 0; i--) {
      if (arena.simT - E.eggTime(i) < opt.incubation) continue;
      const parent = E.eggParent(i);
      const id = E.hatchEgg(i, opt.seed + arena.iota++, rand() * 2 * Math.PI);
      if (id < 0) continue;
      for (let s = 0; s < genes.length; s++) {
        const v = E.getGene(id, s) + normal() * opt.mut * scaleOf(genes[s]);
        E.setGene(id, s, clampGene(genes[s], v));
      }
      if (opt.wmut > 0) {
        const counts = [E.weightCount(0), E.weightCount(1), E.weightCount(2)];
        const total = counts[0] + counts[1] + counts[2];
        for (let j = 0; j < opt.wmutN; j++) {
          let k = Math.floor(rand() * total);
          let fam = 0;
          while (k >= counts[fam]) { k -= counts[fam]; fam++; }
          E.scaleWeight(id, fam, k, Math.exp(normal() * opt.wmut));
        }
        E.developWorm(id);
      }
      if (opt.mmut > 0) {
        const ctl = Array.from({ length: 12 }, (_, j) =>
          E.getMorph(id, j) * Math.exp(normal() * opt.mmut));
        E.setMorphology(id, ...ctl);
      }
      metabolise(id, opt.metabHatch);
      arena.founderOf.set(id, arena.founderOf.get(parent) ?? -1);
      arena.eatenAt.set(id, 0.0);
      arena.births++;
      if (arena.onBirth) arena.onBirth(id, parent);
      arena.cullTo(opt.cap);
    }
  };

  /* One policy pass at simulated time `t`: the reaper first (a starved body should not
   * be counted against the cap a hatchling needs), then the hatchery. */
  arena.tick = (t) => {
    arena.simT = t;
    arena.reap();
    arena.hatchDue();
  };

  /* Refresh the trailing-intake window the cull judges by. The node driver does this on
   * its report cadence; a viewer does it on its own clock. */
  arena.markIntake = () => {
    for (const id of ids()) arena.eatenAt.set(id, E.getEaten(id));
  };

  /* The dynasty census, sorted largest first -- the one line every driver prints. */
  arena.dynasties = () => {
    const dyn = new Map();
    for (const id of ids()) {
      const f = arena.founderOf.get(id) ?? -1;
      dyn.set(f, (dyn.get(f) ?? 0) + 1);
    }
    return Array.from(dyn.entries()).sort((a, b) => b[1] - a[1]);
  };

  /* Forget corpse markers older than `age` simulated seconds -- the food they left is
   * real and stays on the plate; only the marker fades. */
  arena.fadeCorpses = (age = 90) => {
    const c = arena.corpses;
    for (let i = c.length - 1; i >= 0; i--) {
      if (arena.simT - c[i].t > age) c.splice(i, 1);
    }
  };

  return arena;
}
