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
    /* SEX. With recomb > 0, a hatchling crosses over with the nearest living animal
     * within recombR mm: each gene, each of the 3,935 weights and each morphology
     * control takes either lineage's value on a fair coin, BEFORE mutation. Stated as
     * the policy it is: fertilisation here happens at HATCH with whoever is nearby --
     * the egg's snapshot is one parent, the neighbour is the other -- because the
     * runtime's eggs carry one genome and this file owns what a dish cannot decide.
     * No mate in radius means selfing: the asexual path, untouched. Default OFF, and
     * off consumes no rng -- every recorded run keeps replaying; ON forks the mutation
     * stream by design and says so in the knob. Dynasty follows the LAYING parent
     * (the census is a patriline; a fair-coin genome does not need a fair-coin flag). */
    recomb: o.recomb ?? 0.0,
    recombR: o.recombR ?? 9,
    metab,
    metabT: o.metabT ?? 240,
    metabWorkP: o.metabWorkP ?? 2.0,
    metabFloor: o.metabFloor ?? 0.25,
    metabKnee: o.metabKnee ?? 0.35,
    metabHatch: o.metabHatch ?? 0.6,
    corpse: o.corpse ?? (metab > 0 ? metab * 0.5 : 0.0),
    corpseYield: o.corpseYield ?? 0.8,
    corpseR: o.corpseR ?? 0.8,
    /* Rot: a corpse this many seconds old turns -- its marker sours and a repellent
     * miasma is deposited where it lay, sized by what the body was worth. The
     * repellent field diffuses and decays on its own, so the plate forgets. 0 = off. */
    rotT: o.rotT ?? 0,
    rotStench: o.rotStench ?? 2.0,        // repellent units per unit of corpse worth
    /* Regrowth: bacteria grow back. Each lawn site receives regrow food-units/s,
     * deposited into the food field on the policy cadence -- so the plate's carrying
     * capacity becomes a THROUGHPUT, not a stock, and "too much food on average" is a
     * knob instead of a fate. 0 = the never-restocked plate. */
    regrow: o.regrow ?? 0,
    /* Wind: the plate's food and repellent drift at this many mm/s in a direction that
     * meanders deterministically with dish time (no rng -- weather must not fork a
     * seeded run's mutation stream). Regrowth keeps feeding the lawn SITES while the
     * wind smears what is already down, so a windy plate develops plumes and drifts
     * instead of tidy discs. The attractant stays pinned to its colonies -- the
     * mechanism says why. 0 = a still day. */
    wind: o.wind ?? 0,
    /* Lawn scale multiplies the founding lawns' densities: below 1 the plate starts
     * poorer without moving the sites. And `lawns` replaces the layout wholesale --
     * a caller randomising starting conditions passes its own. */
    lawnScale: o.lawnScale ?? 1.0,
    lawns: o.lawns ?? null,
    /* Development: hatchlings start at juvenile scale and grow toward their inherited
     * adult morphology while their store is above the fade knee -- growth is fed-time,
     * so a hatchling that cannot win food stays small. 0 = hatch at full size. */
    juvenile: o.juvenile ?? 0,            // starting scale, e.g. 0.55; 0 disables
    growT: o.growT ?? 90,                 // seconds of fed time from juvenile to adult
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
    matings: 0,               // hatches that actually crossed over (a mate was in radius)
    /* Every animal that ever lived, kept after death because descent IS the record:
     * id -> { parent (-1 for founders), born, died (null while alive), dyn }. Bounded
     * -- the oldest finished twigs are forgotten past ~600 so a long dish cannot grow
     * an unbounded family bible. Consumes no rng; feeds the lineage panel. */
    pedigree: new Map(),
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

  /* Three lawns: the plate is the whole economy. With regrow at 0 they are never
   * restocked, exactly the original dish; with it on, each site receives its share of
   * regrow food-units/s and the economy becomes throughput-limited -- the stock can
   * start smaller because the tap stays open. The attractant plume and the oxygen
   * depression stay at the founding lawn's shape either way (patch shapes are cached at
   * creation; a regrown lawn smells like its founder) -- a stated first cut. Returns
   * the patch list so a viewer can hand it to its minimap. */
  const LAWNS = opt.lawns || [
    { x: -8.0, y: 5.0, r: 4.0, d: 1.0 },
    { x: 7.0, y: -4.0, r: 4.0, d: 1.0 },
    { x: 0.0, y: 9.0, r: 3.0, d: 0.8 },
  ];
  arena.seedPlate = () => {
    for (const l of LAWNS) {
      E.addFood(l.x, l.y, l.r, l.d * opt.lawnScale, l.d, 9.0);
    }
    return LAWNS.map((l) => ({ x: l.x, y: l.y, r: l.r, kind: 'food' }));
  };
  let regrowT = 0;
  function regrowPass() {
    if (opt.regrow <= 0) return;
    const dt = arena.simT - regrowT;
    if (dt < 2.0) return;                 // a trickle, not a drip-per-tick
    regrowT = arena.simT;
    const per = (opt.regrow * dt) / LAWNS.length;
    for (const l of LAWNS) E.depositFood(l.x, l.y, l.r * 0.8, per);
  }
  /* The weather. Direction meanders on two incommensurate slow clocks, magnitude
   * breathes on a third -- deterministic in dish time, so identical seeds get
   * identical weather and the mutation stream is untouched. */
  let windT = 0;
  function windPass() {
    if (opt.wind <= 0) return;
    const dt = arena.simT - windT;
    if (dt < 1.0) return;
    windT = arena.simT;
    const t = arena.simT;
    const dir = 2 * Math.PI * (t / 173.0) + 0.8 * Math.sin(t / 41.0);
    const mag = opt.wind * (0.55 + 0.45 * Math.sin(t / 67.0));
    E.driftFields(Math.cos(dir) * mag * dt, Math.sin(dir) * mag * dt);
  }

  /* Wild-type clones on a ring, fed. Everything after them is descent with
   * modification. */
  arena.spawnFounders = () => {
    for (let i = 0; i < opt.founders; i++) {
      const a = (2 * Math.PI * i) / opt.founders;
      const id = E.createWorm(opt.seed + i,
                              6.0 * Math.cos(a), 6.0 * Math.sin(a), a + Math.PI / 2);
      metabolise(id, 1.0);
      arena.founderOf.set(id, i);
      arena.pedigree.set(id, { parent: -1, born: 0, died: null, dyn: i });
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
    const twig = arena.pedigree.get(id);
    if (twig) twig.died = arena.simT;
    if (arena.pedigree.size > 600) {
      for (const [k, v] of arena.pedigree) {
        if (arena.pedigree.size <= 400) break;
        if (v.died !== null) arena.pedigree.delete(k);
      }
    }
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
  /* One recombination: child (carrying the egg's parental snapshot) against the
   * nearest living animal. Genes and morphology cross by value; weights cross by
   * RATIO (scaleWeight is multiplicative and refuses sign flips, so a mate's value is
   * reached by scaling child/mate -- skipped for loci where either side is zero, which
   * multiplication cannot cross). The whole weight pass short-circuits when both
   * lineages are wild-type there: 3,935 coins for two identical decks buys nothing.
   * developWorm() after any weight change is NOT optional -- inherited thresholds over
   * a recombined graph is bookkeeping error, not phenotype (same contract as wmut). */
  function crossover(id) {
    const [cx, cy] = midOf(id);
    let mate = -1, best = opt.recombR * opt.recombR;
    for (const other of ids()) {
      if (other === id) continue;
      const [ox, oy] = midOf(other);
      const d = (ox - cx) * (ox - cx) + (oy - cy) * (oy - cy);
      if (d < best) { best = d; mate = other; }
    }
    if (mate < 0) return;                      // nobody near: selfing, the asexual path
    for (let s = 0; s < genes.length; s++) {
      if (rand() < 0.5) E.setGene(id, s, E.getGene(mate, s));
    }
    let rewired = false;
    if (E.hasOwnWeights(id) || E.hasOwnWeights(mate)) {
      for (let fam = 0; fam < 3; fam++) {
        const n = E.weightCount(fam);
        for (let k = 0; k < n; k++) {
          if (rand() >= 0.5) continue;
          const mine = E.getWeight(id, fam, k), theirs = E.getWeight(mate, fam, k);
          if (mine === theirs || !(mine > 0) || !(theirs > 0)) continue;
          E.scaleWeight(id, fam, k, theirs / mine);
          rewired = true;
        }
      }
      if (rewired) E.developWorm(id);
    }
    if (E.hasOwnMorphology(id) || E.hasOwnMorphology(mate)) {
      const ctl = Array.from({ length: 12 }, (_, j) =>
        rand() < 0.5 ? E.getMorph(mate, j) : E.getMorph(id, j));
      E.setMorphology(id, ...ctl);
    }
    arena.matings++;
  }

  arena.hatchDue = () => {
    for (let i = E.eggCount() - 1; i >= 0; i--) {
      if (arena.simT - E.eggTime(i) < opt.incubation) continue;
      const parent = E.eggParent(i);
      const id = E.hatchEgg(i, opt.seed + arena.iota++, rand() * 2 * Math.PI);
      if (id < 0) continue;
      if (opt.recomb > 0 && rand() < opt.recomb) crossover(id);
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
      arena.beginGrowth(id);
      arena.founderOf.set(id, arena.founderOf.get(parent) ?? -1);
      arena.pedigree.set(id, { parent, born: arena.simT, died: null,
                               dyn: arena.founderOf.get(id) ?? -1 });
      arena.eatenAt.set(id, 0.0);
      arena.births++;
      if (arena.onBirth) arena.onBirth(id, parent);
      arena.cullTo(opt.cap);
    }
  };

  /* One policy pass at simulated time `t`: the reaper first (a starved body should not
   * be counted against the cap a hatchling needs), then the hatchery, then the plate's
   * own life -- regrowth, rot, growth. */
  arena.tick = (t) => {
    arena.simT = t;
    arena.reap();
    arena.hatchDue();
    regrowPass();
    windPass();
    arena.fadeCorpses();
    arena.growthPass();
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

  /* Corpse aging. A corpse older than rotT TURNS: its marker sours (c.rotted, for a
   * renderer to recolour) and a one-time repellent miasma proportional to its worth is
   * deposited where it lay -- the runtime's repellent field then diffuses and decays it
   * away on its own. Markers older than `age` are forgotten either way; the food a body
   * left is real and stays until eaten. */
  arena.fadeCorpses = (age = 90) => {
    const c = arena.corpses;
    for (let i = c.length - 1; i >= 0; i--) {
      const k = c[i];
      const elapsed = arena.simT - k.t;
      if (opt.rotT > 0 && !k.rotted && elapsed > opt.rotT) {
        k.rotted = true;
        E.depositRepellent(k.x, k.y, opt.corpseR * 1.5, opt.rotStench * k.worth);
      }
      if (elapsed > age) c.splice(i, 1);
    }
  };

  /* Development: every animal below adult scale grows while fed, through the runtime's
   * setDevelopment -- PHENOTYPE, never the genome. The first draft scaled the genome's
   * control points directly, and eggs then inherited their parent's developmental
   * state: a juvenile's child hatched pre-shrunk and shrank again, 0.55 a generation
   * (seed 41, width mean 0.35 by t=90 against a juvenile floor of 0.55). The runtime
   * now keeps genotype and age apart, so this pass cannot contaminate inheritance
   * however it is driven. A juvenile is thinner (less drag) and weaker (the muscle
   * profile scales), which makes being small a real disadvantage in the cull's intake
   * contest. Growth is gated on the store sitting above the fade knee -- fed time, so a
   * hatchling that cannot win food stays small -- and consumes NO randomness, so seeded
   * replays are untouched by turning it on or off. */
  const grownOf = new Map();               // id -> { scale, lastT }
  arena.beginGrowth = (id) => {
    if (opt.juvenile <= 0) return;
    grownOf.set(id, { scale: opt.juvenile, lastT: arena.simT });
    E.setDevelopment(id, opt.juvenile);
  };
  arena.growthPass = () => {
    if (opt.juvenile <= 0) return;
    for (const [id, g] of grownOf) {
      if (!arena.founderOf.has(id)) { grownOf.delete(id); continue; }   // buried
      if (g.scale >= 1.0) { grownOf.delete(id); continue; }             // grown up
      const dt = arena.simT - g.lastT;
      g.lastT = arena.simT;
      if (dt <= 0) continue;
      // Fed time only: below the knee the store is buying survival, not growth.
      if (opt.metab > 0 && E.getEnergy(id) < opt.metabKnee * opt.metab) continue;
      g.scale = Math.min(1.0, g.scale + ((1.0 - opt.juvenile) / opt.growT) * dt);
      E.setDevelopment(id, g.scale);
      if (arena.onGrowth) arena.onGrowth(id, g.scale);
    }
  };
  arena.scaleOfWorm = (id) => {
    const g = grownOf.get(id);
    return g ? g.scale : 1.0;
  };

  return arena;
}
