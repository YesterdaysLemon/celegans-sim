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

const ok = results.every(Boolean);
console.log(ok ? '\nThe population behaves as a population.'
               : '\nThe population does NOT behave as a population.');
process.exit(ok ? 0 : 1);
