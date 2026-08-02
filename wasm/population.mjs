/* Invariants that only exist when more than one animal is on the plate.
 *
 * Everything in wasm/conform.mjs runs a *single* worm, because its job is to compare the
 * runtime against a Python `Simulation` and a Simulation is one animal. That is the right
 * scope for it and it leaves a hole: the multi-worm path is the only path a browser
 * visitor executes, and it is about to become the path a population evolves on, and until
 * now nothing anywhere in this repository ever had two worms alive at once.
 *
 * The hole was not merely untested, it was mis-advertised. conform.mjs claims its
 * `stepAll` case "covers the ordering -- one world advance per step, not one per animal
 * per step, which is the mistake the shape invites". With one animal it cannot: the
 * correct implementation, and the buggy one with `stepFields` moved inside the per-animal
 * loop, both come to exactly one worm step followed by exactly one field advance. The
 * check passed against the defect it was written to catch. That is this project's most
 * repeated bug -- a check that runs, passes, and covers less than its own comment claims --
 * and the fix is not a better comment, it is a second animal.
 *
 * These checks need no Python reference. They are properties the runtime owes on its own,
 * which makes them cheap enough to run on every push.
 *
 *     node wasm/population.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

for (const [file, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(file))) {
    console.error(`Missing ${file}; generate it with: ${how}`);
    process.exit(2);
  }
}

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);
const GRID = head.ints.world_grid;
const compiled = new WebAssembly.Module(wasmBuf);

/* A fresh runtime per scenario. Worlds and populations are module-level state in the
 * runtime, and a check that shares them with the previous check is measuring the previous
 * check. */
function engine() {
  const E = new WebAssembly.Instance(compiled, {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  E.setNoise(0);            // the runtime's RNG is not the numpy one; see conform.mjs
  return E;
}

// Views into linear memory must be re-taken after anything that may have grown it, and
// creating a worm allocates ~370 kB, so it routinely does.
const f64 = (E) => new Float64Array(E.memory.buffer);
const readArray = (E, ptr, n) => Array.from(f64(E).subarray(ptr >> 3, (ptr >> 3) + n));

const worst = (a, b) => {
  let d = 0;
  for (let i = 0; i < a.length; i++) d = Math.max(d, Math.abs(a[i] - b[i]));
  return d;
};

const results = [];
function report(name, ok, detail) {
  results.push(ok);
  console.log(`\n${name}`);
  if (detail) console.log(detail);
  console.log(ok ? '  PASS' : '  FAIL');
}

/* Well clear of one another: the body is 1 mm and `eat` withdraws from a 3x3 cell
 * neighbourhood, which at a 256-cell grid across a 90 mm plate is about 1 mm across. At
 * the model's ~0.3 mm/s these never come within an order of magnitude of interacting. */
const SPREAD = [
  [-16.0, 0.0, 0.0],
  [0.0, 0.0, 1.1],
  [16.0, 0.0, 2.2],
  [0.0, -16.0, 3.3],
  [0.0, 16.0, 4.4],
];
/* A lawn under every animal. The plate is the only thing worms share, so a check that
 * wants to know whether they interact has to put them somewhere they are all actually
 * withdrawing from it -- three animals starving on bare agar would agree with themselves
 * perfectly and prove nothing about the coupling. */
const plate = (E) => {
  for (const [x, y] of SPREAD) E.addFood(x, y, 4.0, 1.0, 1.0, 9.0);
  E.addRepellent(0.0, 8.0, 0.9, 5.0);
};
const STEPS = 900;                       // 0.45 s -- crosses ~22 field_dt ticks
// Feeding is slow to get going: the pump has to wind up from its off-food rate, and
// nothing is ingested at all for the first ~1.5 s. Measured on this model, 4 s is the
// point where every animal has taken a clearly non-zero amount off the plate.
const FEED_STEPS = 8000;                 // 4.0 s

/* ---------------------------------------------------------------------------------- 1 --
 * The plate ages once per step, however many animals are standing on it.
 *
 * This is the check conform.mjs could not make. The attractant field is diffused and
 * decayed by World.stepFields and is touched by nothing else -- animals withdraw from
 * `food`, which does not diffuse -- so after a fixed number of steps the grid is a pure
 * function of how many times stepFields has been called. If the world were advanced once
 * per animal per step, four animals would age the plate four times as fast and this
 * comparison would be nowhere near zero.
 */
function attractantAfter(nWorms) {
  const E = engine();
  plate(E);
  for (let i = 0; i < nWorms; i++) E.createWorm(1000 + i * 7717, ...SPREAD[i]);
  E.stepAll(STEPS);
  return readArray(E, E.ptrAttractant(), GRID * GRID);
}
{
  const one = attractantAfter(1);
  const four = attractantAfter(4);
  const d = worst(one, four);
  const spread = Math.max(...one) - Math.min(...one);
  report(
    `PLATE AGEING -- attractant grid after ${STEPS} steps, 1 animal against 4`,
    d === 0,
    `  worst cell disagreement       ${d.toExponential(3)}\n` +
    `  field is not trivially flat   range ${spread.toExponential(3)} over ${GRID * GRID} cells`,
  );
}

/* ---------------------------------------------------------------------------------- 2 --
 * Animals are independent except through the plate.
 *
 * Three worms far enough apart that no head ever enters another's eat-neighbourhood must
 * follow exactly the trajectory each follows alone. This is what makes a population a
 * population rather than a single coupled object, and it is the property a fitness
 * measure quietly assumes: if animals perturb one another through some path nobody
 * intended, `food_eaten` is scoring the neighbours as much as the animal.
 */
{
  const sample = (E, id) => ({
    nodes: readArray(E, E.ptrNodesX(id), 49),
    V: readArray(E, E.ptrV(id), 302),
    eaten: E.getEaten(id),
  });
  const start = [];
  const together = (() => {
    const E = engine();
    plate(E);
    const ids = SPREAD.slice(0, 3).map((p, i) => E.createWorm(1000 + i * 7717, ...p));
    for (const id of ids) start.push(readArray(E, E.ptrNodesX(id), 49));
    E.stepAll(FEED_STEPS);
    return ids.map((id) => sample(E, id));
  })();
  const alone = SPREAD.slice(0, 3).map((p, i) => {
    const E = engine();
    plate(E);
    const id = E.createWorm(1000 + i * 7717, ...p);
    E.stepAll(FEED_STEPS);
    return sample(E, id);
  });
  let d = 0;
  for (let i = 0; i < 3; i++) {
    d = Math.max(d, worst(together[i].nodes, alone[i].nodes));
    d = Math.max(d, worst(together[i].V, alone[i].V));
    d = Math.max(d, Math.abs(together[i].eaten - alone[i].eaten));
  }
  /* Guard against a vacuous pass. Two animals that never moved and never ate would agree
   * with each other to every decimal place and demonstrate nothing, which is the exact
   * shape of failure this file exists to stop repeating: the comparison has to be over
   * something that was actually happening. */
  const fed = together.every((w) => w.eaten > 0);
  const moved = together.every((w, i) => worst(w.nodes, start[i]) > 0.05);
  report(
    'INDEPENDENCE -- 3 animals stepped together against each stepped alone',
    d === 0 && fed && moved,
    `  worst disagreement            ${d.toExponential(3)}   (nodes, V, food eaten)\n` +
    `  every animal fed              ${fed}   [${together.map((w) => w.eaten.toFixed(5)).join(', ')}]\n` +
    `  every animal moved            ${moved}   (worst node travel > 0.05 mm)`,
  );
}

/* ---------------------------------------------------------------------------------- 3 --
 * A generation boundary: cull the unfit, breed replacements, and every handle still names
 * the animal it was given for.
 *
 * This is the operation the old handle-is-an-array-index representation could not express,
 * and it has to be tested as *cull and breed* rather than cull alone. Culling by itself is
 * not enough to catch slot-based resolution: swap-with-last moves an animal to a lower
 * slot while its id stays high, so a stale read past the end of the shortened array often
 * still lands on the right animal by accident. I watched exactly that happen -- an earlier
 * version of this check passed against slot resolution for that reason, which is the same
 * vacuous-pass this file was written to stop.
 *
 * Breeding is what reuses the slots, and it is also what a generational loop actually
 * does. Positions are compared before any stepping, so a correctly resolved handle agrees
 * exactly and a mis-resolved one is wrong by whole millimetres.
 */
{
  const survivors = [0, 2, 4];
  const BRED = [[-8.0, 8.0, 0.7], [8.0, -8.0, 1.9]];
  const turnover = (() => {
    const E = engine();
    plate(E);
    const ids = SPREAD.map((p, i) => E.createWorm(1000 + i * 7717, ...p));
    const goneA = E.removeWorm(ids[1]);
    const goneB = E.removeWorm(ids[3]);
    // Breed into the gap the cull left, which is what reuses the vacated slots.
    const bred = BRED.map((p, i) => E.createWorm(31337 + i, ...p));

    // Every live handle names the animal it was created for. No stepping yet, so this is
    // exact: a mis-resolved handle reports another animal's start position.
    const placed = [
      ...survivors.map((i) => [ids[i], SPREAD[i]]),
      ...bred.map((id, i) => [id, BRED[i]]),
    ];
    const misresolved = placed.filter(([id, p]) => E.getX(id) !== p[0] || E.getY(id) !== p[1]);

    const before = {
      goneA, goneB, count: E.wormCount(), misresolved: misresolved.length,
      staleRefused: E.hasWorm(ids[1]) === 0 && E.hasWorm(ids[3]) === 0,
      liveKept: survivors.every((i) => E.hasWorm(ids[i]) === 1),
      enumerated: Array.from({ length: E.wormCount() }, (_, k) => E.wormIdAt(k))
        .sort((a, b) => a - b),
      expected: [...survivors.map((i) => ids[i]), ...bred].sort((a, b) => a - b),
    };
    E.stepAll(STEPS);
    before.state = survivors.map((i) => ({
      nodes: readArray(E, E.ptrNodesX(ids[i]), 49),
      V: readArray(E, E.ptrV(ids[i]), 302),
    }));
    return before;
  })();

  /* The control: the same five animals, minus the two that were culled, plus the two that
   * were bred -- created directly, in that order, with nothing removed. A survivor that
   * lived through a generation boundary must be indistinguishable from one that never saw
   * one. */
  const control = (() => {
    const E = engine();
    plate(E);
    const ids = survivors.map((i) => E.createWorm(1000 + i * 7717, ...SPREAD[i]));
    BRED.forEach((p, i) => E.createWorm(31337 + i, ...p));
    E.stepAll(STEPS);
    return ids.map((id) => ({
      nodes: readArray(E, E.ptrNodesX(id), 49),
      V: readArray(E, E.ptrV(id), 302),
    }));
  })();

  let d = 0;
  for (let i = 0; i < survivors.length; i++) {
    d = Math.max(d, worst(turnover.state[i].nodes, control[i].nodes));
    d = Math.max(d, worst(turnover.state[i].V, control[i].V));
  }
  const idsOk = JSON.stringify(turnover.enumerated) === JSON.stringify(turnover.expected);
  const ok = d === 0 && turnover.goneA === 1 && turnover.goneB === 1 && turnover.count === 5
    && turnover.misresolved === 0 && turnover.staleRefused && turnover.liveKept && idsOk;
  report(
    'GENERATION TURNOVER -- 5 animals, cull 2, breed 2, against the same 5 built directly',
    ok,
    `  survivors match control       ${d.toExponential(3)}   (nodes, V)\n` +
    `  handles naming wrong animal   ${turnover.misresolved} of 5\n` +
    `  population after turnover     ${turnover.count}, survivors still resolve: ${turnover.liveKept}\n` +
    `  culled handles refused        ${turnover.staleRefused}\n` +
    `  enumeration matches           ${idsOk}  [${turnover.enumerated}]`,
  );
}

/* ---------------------------------------------------------------------------------- 4 --
 * The population is allowed to reach zero, and to come back.
 *
 * A generation boundary that clears and repopulates should not have to keep one arbitrary
 * survivor alive to satisfy the container -- which the old `popWorm` did, refusing to go
 * below one. Stepping an empty dish must also be a no-op rather than a trap, because the
 * loop that culls and the loop that breeds are not the same loop and the plate keeps
 * ageing in between.
 */
{
  let emptied = false, stepped = false, reborn = false, idsFresh = false;
  try {
    const E = engine();
    plate(E);
    const ids = SPREAD.slice(0, 3).map((p, i) => E.createWorm(1000 + i * 7717, ...p));
    for (const id of ids) E.removeWorm(id);
    emptied = E.wormCount() === 0;
    E.stepAll(50);
    stepped = true;
    const next = E.createWorm(4242, 0.0, 0.0, 0.0);
    E.stepAll(50);
    reborn = E.wormCount() === 1 && E.hasWorm(next) === 1;
    // Ids are never reused, so a handle from the previous generation cannot come back to
    // life as a different animal.
    idsFresh = !ids.includes(next) && E.hasWorm(ids[0]) === 0;
  } catch (err) {
    console.log(`  threw: ${err.message}`);
  }
  report(
    'EMPTY DISH -- cull the whole population, keep stepping, repopulate',
    emptied && stepped && reborn && idsFresh,
    `  population reached zero       ${emptied}\n` +
    `  stepping an empty dish        ${stepped ? 'no-op' : 'threw'}\n` +
    `  repopulated                   ${reborn}\n` +
    `  ids not reused                ${idsFresh}`,
  );
}

/* ---------------------------------------------------------------------------------- 5 --
 * The default genome is the model.
 *
 * Every gene is seeded from the scalar it was named after, so a population nobody has
 * mutated is bit-identical to the model before genes existed -- which is what lets
 * conform.mjs go on meaning something. Matched *by name* through the .model header rather
 * than by position, because the failure this guards against is the slot numbering drifting
 * between the exporter and the runtime, and a positional check would drift with it.
 */
{
  const E = engine();
  const id = E.createWorm(1, 0.0, 0.0, 0.0);
  const names = head.genes || [];
  const wrong = names
    .map((name, slot) => ({ name, slot, got: E.getGene(id, slot), want: head.scalars[name] }))
    .filter((g) => !Object.is(g.got, g.want));
  const counted = E.geneCount() === names.length;
  report(
    `DEFAULT GENOME -- ${names.length} genes seeded from the exported scalars`,
    names.length > 0 && counted && wrong.length === 0,
    `  genes declared                ${names.length}, runtime reports ${E.geneCount()}\n` +
    `  disagreeing with the model    ${wrong.length}` +
    (wrong.length
      ? `\n${wrong.map((g) => `    ${g.name} [${g.slot}]: ${g.got} != ${g.want}`).join('\n')}`
      : ''),
  );
}

/* ---------------------------------------------------------------------------------- 6 --
 * No gene is inert.
 *
 * The one check a genome most needs, and the one whose absence is hardest to notice. A
 * gene wired to nothing does not fail -- it makes its dimension of the search space flat,
 * the population drifts on it neutrally, and the run looks exactly like a run where that
 * trait was simply not under selection. This repo already has one parameter in that state:
 * `serotonin_mod1` is exported, documented, and recommended for a genome, and the runtime
 * ignores it entirely, because conformance passes when the shipped value is zero.
 *
 * So: perturb each gene on its own, and require the animal to end up somewhere else.
 *
 * Three of the fourteen need a context, and the reason is a documented property of the
 * model rather than a weakness of the check. The omega turn fires on a backward-to-forward
 * edge, and this animal reverses about 3.3 times a minute -- far too rarely for an assay
 * this short to catch one, and measured here it produced no reversal at all in ten
 * seconds. Those genes are therefore exercised against a baseline whose Schmitt trigger
 * oscillates. Both arms get the same context; only the gene under test differs.
 */
{
  const REVERSING = { sen_gate_bias: 0.20, sen_gate_hysteresis: 0.01 };
  const CONTEXT = {
    sen_gate_hysteresis: REVERSING,
    sen_omega_current: REVERSING,
    sen_omega_ventral_fraction: REVERSING,
  };
  const names = head.genes || [];
  const slotOf = Object.fromEntries(names.map((n, i) => [n, i]));
  const BLOCK = 2000, BLOCKS = 5;              // 5 s, poked once a second

  function run(context, mutate) {
    const E = engine();
    E.addFood(-16.0, 0.0, 4.0, 1.0, 1.0, 9.0);
    E.addRepellent(-13.0, 2.0, 0.9, 5.0);
    const id = E.createWorm(1000, -16.0, 0.0, 0.0);
    for (const [n, v] of Object.entries(context || {})) E.setGene(id, slotOf[n], v);
    if (mutate) mutate(E, id);
    // Poking drives the touch pathway, which nothing else on this plate would reach.
    for (let k = 0; k < BLOCKS; k++) { E.pokeWorm(id, 1, 1.0); E.stepAll(BLOCK); }
    return {
      nodes: readArray(E, E.ptrNodesX(id), 49),
      V: readArray(E, E.ptrV(id), 302),
      reversed: E.getGateForward(id),
    };
  }

  const controls = new Map();
  const controlFor = (ctx) => {
    const key = JSON.stringify(ctx || null);
    if (!controls.has(key)) controls.set(key, run(ctx, null));
    return controls.get(key);
  };

  const inert = [], moved = [];
  for (const name of names) {
    const ctx = CONTEXT[name];
    const base = controlFor(ctx);
    // x3 + 1 rather than x3, so a gene whose default is zero still moves.
    const m = run(ctx, (E, id) => E.setGene(id, slotOf[name], E.getGene(id, slotOf[name]) * 3 + 1));
    const d = Math.max(worst(m.nodes, base.nodes), worst(m.V, base.V));
    (d > 1e-9 ? moved : inert).push(`${name} (${d.toExponential(2)})`);
  }
  report(
    `NO GENE IS INERT -- each of ${names.length} perturbed alone, against its own control`,
    inert.length === 0 && names.length > 0,
    `  genes that changed the animal ${moved.length} of ${names.length}\n` +
    (inert.length ? `  INERT: ${inert.join(', ')}\n` : '') +
    `  ${moved.join('\n  ')}`,
  );
}

/* ---------------------------------------------------------------------------------- 7 --
 * A genome belongs to one animal.
 *
 * The whole point of per-worm genes, and the one way the change could be worse than
 * useless: if a gene leaked between animals, a population would still look like it was
 * evolving while actually sharing one genome, and every fitness comparison in it would be
 * meaningless. Mutate the middle animal of three and require the other two to be
 * bit-identical to a run where nobody was mutated.
 */
{
  const names = head.genes || [];
  const trio = (mutate) => {
    const E = engine();
    plate(E);
    const ids = SPREAD.slice(0, 3).map((p, i) => E.createWorm(1000 + i * 7717, ...p));
    if (mutate) mutate(E, ids[1]);
    E.stepAll(STEPS);
    return {
      ids,
      state: ids.map((id) => ({
        nodes: readArray(E, E.ptrNodesX(id), 49),
        V: readArray(E, E.ptrV(id), 302),
      })),
      genes: ids.map((id) => names.map((_, s) => E.getGene(id, s))),
    };
  };
  const plain = trio(null);
  // Mutate every gene at once on the middle animal -- the loudest version of the question.
  const one = trio((E, id) => names.forEach((_, s) => E.setGene(id, s, E.getGene(id, s) * 2 + 1)));

  let bystanders = 0;
  for (const i of [0, 2]) {
    bystanders = Math.max(bystanders, worst(one.state[i].nodes, plain.state[i].nodes));
    bystanders = Math.max(bystanders, worst(one.state[i].V, plain.state[i].V));
  }
  const target = Math.max(worst(one.state[1].nodes, plain.state[1].nodes),
                          worst(one.state[1].V, plain.state[1].V));
  // Their genomes must still read as the defaults, not as the mutant's.
  const genomesClean = [0, 2].every((i) => worst(one.genes[i], plain.genes[0]) === 0);
  report(
    `GENES ARE PRIVATE -- all ${names.length} mutated on the middle animal of three`,
    bystanders === 0 && genomesClean && target > 1e-9,
    `  the mutated animal moved      ${target.toExponential(3)}\n` +
    `  its neighbours moved          ${bystanders.toExponential(3)}   (must be exactly 0)\n` +
    `  neighbours' genomes intact    ${genomesClean}`,
  );
}

/* ---------------------------------------------------------------------------------- 8 --
 * Food is conserved across a population sharing one plate.
 *
 * The property a fitness measure needs and cannot check for itself: whatever the animals
 * are credited with having eaten must have come off the plate, and the plate must not lose
 * more than they got. With one animal this is nearly automatic; with several competing for
 * the same cells it is not, because `world.eat` serves them in turn out of a shrinking
 * neighbourhood and each has to be told what it actually received rather than what it
 * asked for.
 *
 * The animals are put deliberately on top of one another here -- the opposite of the
 * independence check -- on a lawn small enough that they run it down, so the competition
 * is real rather than nominal.
 */
{
  const N = 4;
  const E = engine();
  E.addFood(0.0, 0.0, 1.5, 1.0, 1.0, 4.0);       // a small lawn, four animals on it
  const foodTotal = () => {
    const f = f64(E).subarray(E.ptrFood() >> 3, (E.ptrFood() >> 3) + GRID * GRID);
    let s = 0;
    for (let i = 0; i < f.length; i++) s += f[i];
    return s;
  };
  const ids = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    ids.push(E.createWorm(2000 + i * 5171, Math.cos(a) * 0.4, Math.sin(a) * 0.4, a));
  }
  const before = foodTotal();
  E.stepAll(FEED_STEPS);
  const after = foodTotal();

  const removed = before - after;
  const eaten = ids.reduce((s, id) => s + E.getEaten(id), 0);
  const held = ids.reduce((s, id) => s + E.getIngested(id) + E.getLumen(id), 0);
  // Relative, because the grid sum is ~1e3 and cancellation in it dominates any honest
  // tolerance on the ~1e-2 that actually moved.
  const rel = (a, b) => Math.abs(a - b) / Math.max(Math.abs(b), 1e-12);
  const conserved = rel(eaten, removed) < 1e-9;
  const accounted = rel(held, eaten) < 1e-9;
  const competed = removed > 0 && ids.every(id => E.getEaten(id) > 0);
  report(
    `FOOD IS CONSERVED -- ${N} animals on one small lawn, ${(FEED_STEPS * 5e-4).toFixed(1)} s`,
    conserved && accounted && competed,
    `  plate lost                    ${removed.toExponential(6)}\n` +
    `  animals credited              ${eaten.toExponential(6)}   (relative gap ${rel(eaten, removed).toExponential(2)})\n` +
    `  intestine + lumen             ${held.toExponential(6)}   (relative gap ${rel(held, eaten).toExponential(2)})\n` +
    `  every animal actually fed     ${competed}   [${ids.map(id => E.getEaten(id).toFixed(6)).join(', ')}]`,
  );
}

/* ---------------------------------------------------------------------------------- 9 --
 * An egg is a heritable record, and it outlives its parent.
 *
 * This is what separates reproduction from decoration. An egg used to be two coordinates,
 * so a population could be *selected* -- something outside the dish reading fitness and
 * deciding who breeds -- but could not *inherit*, because nothing an animal produced
 * carried anything of the animal.
 *
 * The load-bearing assertion is the last one. An egg has to survive its parent being
 * culled, which is most of the point of laying it, so the genome is copied at laying
 * rather than referenced. A reference would work in every test that keeps the parent
 * alive and fail exactly when a generation turns over.
 */
{
  const names = head.genes || [];
  const E = engine();
  E.addFood(0.0, 0.0, 20.0, 1.0, 1.0, 30.0);      // a lawn worth laying on
  const parent = E.createWorm(7, 0.0, 0.0, 0.0);

  // A parent that is not wild type, so a hatchling carrying the defaults is a failure
  // rather than a coincidence.
  const want = names.map((_, s) => E.getGene(parent, s) * 2 + 0.5);
  want.forEach((v, s) => E.setGene(parent, s, v));

  let laid = false;
  for (let k = 0; k < 40 && !laid; k++) { E.stepAll(2000); laid = E.eggCount() > 0; }

  const eggT = laid ? E.eggTime(0) : NaN;
  const eggParent = laid ? E.eggParent(0) : -1;
  const carried = names.map((_, s) => E.eggGene(0, s));
  const ex = f64(E)[(E.ptrEggX() >> 3)], ey = f64(E)[(E.ptrEggY() >> 3)];
  const before = E.eggCount();

  // Kill the parent before hatching. Anything the egg cannot answer on its own now fails.
  E.removeWorm(parent);
  const chick = E.hatchEgg(0, 4242, 0.0);
  const got = chick >= 0 ? names.map((_, s) => E.getGene(chick, s)) : [];

  const inherited = chick >= 0 && worst(got, want) === 0;
  const recorded = laid && eggParent === parent && eggT > 0 && eggT < 40.0;
  const stored = laid && worst(carried, want) === 0;
  const placed = chick >= 0
    && Math.abs(E.getX(chick) - ex) < 1e-12 && Math.abs(E.getY(chick) - ey) < 1e-12;
  const consumed = E.eggCount() === before - 1;
  const nothingLost = E.eggsDropped() === 0;

  report(
    'EGGS ARE HERITABLE -- laid by a mutant, hatched after the parent was culled',
    laid && recorded && stored && inherited && placed && consumed && nothingLost,
    `  eggs laid                     ${before} (first at t=${eggT.toFixed(3)} s)\n` +
    `  egg records its parent        ${eggParent === parent}  (id ${eggParent})\n` +
    `  egg carries parent's genome   ${stored}   (worst gene gap ${worst(carried, want).toExponential(2)})\n` +
    `  hatchling inherits it         ${inherited}   -- with the parent already dead\n` +
    `  hatched where the egg lay     ${placed}\n` +
    `  egg consumed, none dropped    ${consumed} / ${nothingLost}`,
  );
}

/* --------------------------------------------------------------------------------- 10 --
 * Contested feeding does not depend on the order the animals are stepped in.
 *
 * This is the property a fitness measure needs and the one that is easiest to lose. Each
 * animal used to capture and debit inside its own step, so on a shared lawn worm 0 sampled
 * a full neighbourhood and worm 3 sampled what three others had been served from --
 * measured at 0.016039, 0.016034, 0.016030, 0.016024, monotonic in array order. Selecting
 * on `food_eaten` therefore partly selected for array position, and swap-with-last culling
 * makes position semi-heritable across generations.
 *
 * Checked by *reversing the creation order* rather than by leaning on the geometry being
 * symmetric. Four animals, same seeds and same places, created 0..3 and then 3..0; every
 * animal must eat exactly what it ate before. A symmetric-lawn check would pass on a
 * uniform field even with the bug, because every neighbourhood starts out identical --
 * this one cannot.
 */
{
  const N = 4;
  const spots = Array.from({ length: N }, (_, i) => {
    const a = (i / N) * Math.PI * 2;
    return [Math.cos(a) * 0.4, Math.sin(a) * 0.4, a];
  });
  const run = (order) => {
    const E = engine();
    E.addFood(0.0, 0.0, 1.5, 1.0, 1.0, 4.0);
    const ids = new Array(N);
    for (const i of order) ids[i] = E.createWorm(2000 + i * 5171, ...spots[i]);
    E.stepAll(FEED_STEPS);
    return ids.map((id) => E.getEaten(id));
  };
  const forward = run([0, 1, 2, 3]);
  const backward = run([3, 2, 1, 0]);
  const d = worst(forward, backward);
  const spread = Math.max(...forward) - Math.min(...forward);
  const fed = forward.every((v) => v > 0);
  report(
    `CONTESTED FEEDING IS ORDER-FREE -- ${N} animals on one lawn, created 0..3 then 3..0`,
    d === 0 && fed,
    `  worst per-animal difference   ${d.toExponential(3)}   (must be exactly 0)\n` +
    `  forward order                 ${forward.map((v) => v.toFixed(6)).join(', ')}\n` +
    `  reversed order                ${backward.map((v) => v.toFixed(6)).join(', ')}\n` +
    `  spread within one run         ${spread.toExponential(3)}   (rotational symmetry, up to the grid)\n` +
    `  every animal fed              ${fed}`,
  );
}

/* --------------------------------------------------------------------------------- 11 --
 * `createWorm`'s fourth argument points the animal backwards, and it is time that was
 * written down somewhere that fails.
 *
 * Node 0 is the mouth and sits at (x, y); `updateNodes` lays the rest of the body out
 * along `heading` behind it. So `heading` is the direction the body *trails* and the
 * animal travels at `heading + pi`. Python's `Body` does exactly the same thing, so this
 * is one convention consistently implemented and, until now, documented nowhere and
 * asserted nowhere.
 *
 * The cost of that was not hypothetical. Two callers translated "aim this animal at X"
 * into `heading = bearing of X` and aimed at the reflection of X: a foraging calibration
 * whose published conclusion had to be retracted, and the evolution assay's plate layout,
 * whose comment says it points animals *off* their lawn while the code drove every one of
 * them through the middle of it -- a factor of ten in the fitness being selected on.
 *
 * Bare agar, no food, no repellent, noise off: nothing here steers the animal, so the only
 * thing that can set the direction it leaves in is the layout. Cosine against the expected
 * heading rather than a bearing difference, because an undulating animal yaws about its
 * own track by a degree or two and a raw angle comparison would have to be loosened until
 * it stopped discriminating. The gap being caught is half a turn; 0.95 has enormous room.
 */
{
  const E = engine();                       // deliberately no plate(): nothing to steer by
  const SECONDS = 6.0;
  const ids = SPREAD.map(([x, y, h], i) => E.createWorm(1000 + i * 7717, x, y, h));
  const from = ids.map((id) => [E.getX(id), E.getY(id)]);
  E.stepAll(Math.round(SECONDS / head.scalars.dt));

  const rows = ids.map((id, i) => {
    const dx = E.getX(id) - from[i][0], dy = E.getY(id) - from[i][1];
    const dist = Math.hypot(dx, dy);
    const h = SPREAD[i][2];
    // Unit vector the animal should travel along if it faces `heading + pi`.
    const ex = Math.cos(h + Math.PI), ey = Math.sin(h + Math.PI);
    return { h, dist, cos: dist > 0 ? (dx * ex + dy * ey) / dist : 0.0 };
  });

  // A stationary animal has no bearing, so an implementation that simply stopped moving
  // would sail through a pure direction test. Require real displacement first.
  const moved = rows.every((r) => r.dist > 0.5);
  const aligned = rows.every((r) => r.cos > 0.95);

  report(
    'HEADING POINTS THE BODY, NOT THE FACE -- every animal travels at heading + pi',
    moved && aligned,
    rows.map((r, i) =>
      `  worm ${i}  heading ${r.h.toFixed(2)}  travelled ${r.dist.toFixed(2)} mm  ` +
      `cos to heading+pi ${r.cos.toFixed(4)}`).join('\n') +
    `\n  all moved > 0.5 mm in ${SECONDS} s   ${moved}\n` +
    `  all aligned within cos 0.95    ${aligned}`,
  );
}

/* --------------------------------------------------------------------------------- 12 --
 * Animals are independent through the *touch* pathway too, and that is a separate claim
 * from case 2.
 *
 * Case 2 already asserts that three animals stepped together follow the trajectories they
 * follow alone. It cannot see this one. Its animals sit within 16 mm of the centre of a
 * 45 mm dish, so `contact()` writes zeros for all of them on every step, and a defect that
 * leaked contact forces from one animal to another would leak zeros. Every other check in
 * this file has the same blind spot: nothing in this repository has ever run two animals
 * that were touching anything.
 *
 * That blind spot was load-bearing. #33 lists `contactX`/`contactY` among the per-step
 * scratch that can be hoisted to one shared module-level copy, and the shape supports it --
 * `contact()` writes them, `stepBody` reads them. But `sense()` reads them as well, and
 * `sense()` runs *before* `contact()` in `prepareStep`, so what the mechanosensory pathway
 * reads is the previous step's wall force. Share those arrays and animal k's nose feels
 * what animal k-1 is pressing against.
 *
 * They stayed per-worm, and this is the check that says so. It was watched failing with
 * them hoisted: worst disagreement 8.722e+1, while all eleven checks above stayed green and
 * `wasm/conform.mjs` passed outright, at its usual 5.0e-13 mm -- because conformance runs
 * one animal, and with one animal sharing an array with yourself is identity. Eleven checks
 * and a step-for-step comparison against the Python, and the only thing between that defect
 * and the browser was this case.
 *
 * Deliberately no lawn: the coupling under test is mechanical, and feeding is case 2's
 * subject. The animals are placed at different depths into the wall so their contact forces
 * genuinely differ -- three animals pressing identically would agree with each other
 * whether or not the arrays were shared, which is this file's recurring vacuous pass.
 */
{
  // Mouth on the wall at angle a, radius r; the body trails inward (heading = a + pi), so
  // the animal travels outward and keeps pressing. See case 11 for why heading reads
  // backwards.
  const WALL = [[0.35, 45.00], [2.20, 45.15], [4.10, 44.90]];
  const WALL_STEPS = 4000;                 // 2.0 s -- long enough for all three to be pressing
  const place = (E, i) => {
    const [a, r] = WALL[i];
    return E.createWorm(1000 + i * 7717, Math.cos(a) * r, Math.sin(a) * r, a + Math.PI);
  };
  const sample = (E, id) => ({
    nodes: readArray(E, E.ptrNodesX(id), 49),
    V: readArray(E, E.ptrV(id), 302),
    touch: E.getSensed(id, 4),             // the smoothed contact the touch neurons see
  });

  const together = (() => {
    const E = engine();
    const ids = WALL.map((_, i) => place(E, i));
    E.stepAll(WALL_STEPS);
    return ids.map((id) => sample(E, id));
  })();
  const alone = WALL.map((_, i) => {
    const E = engine();
    const id = place(E, i);
    E.stepAll(WALL_STEPS);
    return sample(E, id);
  });

  let d = 0;
  for (let i = 0; i < WALL.length; i++) {
    d = Math.max(d, worst(together[i].nodes, alone[i].nodes));
    d = Math.max(d, worst(together[i].V, alone[i].V));
    d = Math.max(d, Math.abs(together[i].touch - alone[i].touch));
  }
  const touches = together.map((w) => w.touch);
  // Two guards against a vacuous pass, and they are the whole point of the case. The first:
  // every animal has to be in contact at all, or this is case 2 with a smaller lawn. The
  // second: their contacts have to *differ*, or swapping one animal's forces for another's
  // would be a no-op.
  const feeling = touches.every((t) => t > 1e-3);
  const spread = Math.max(...touches) - Math.min(...touches);
  const distinct = spread / Math.max(...touches) > 0.1;
  report(
    `TOUCH IS PRIVATE -- ${WALL.length} animals pressing the dish wall, together against alone`,
    d === 0 && feeling && distinct,
    `  worst disagreement            ${d.toExponential(3)}   (nodes, V, touch readout)\n` +
    `  every animal in contact       ${feeling}   [${touches.map((t) => t.toFixed(6)).join(', ')}]\n` +
    `  contacts differ               ${distinct}   ` +
    `(spread ${(100 * spread / Math.max(...touches)).toFixed(0)}% of the largest, needs > 10%)`,
  );
}

const ok = results.every(Boolean);
console.log(ok ? '\nThe population behaves as a population.'
               : '\nThe population does NOT behave as a population.');
process.exit(ok ? 0 : 1);
