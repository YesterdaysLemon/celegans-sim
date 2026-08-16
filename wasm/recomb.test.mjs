/* Sex as policy, descent as record: the recombination and pedigree contracts.
 *
 *     node --test wasm/recomb.test.mjs
 *
 * TRACK B, emphatically: C. elegans has males and hermaphrodites, sperm storage and a
 * five-day life; this dish has "the nearest animal within nine millimetres shares a
 * fair coin per locus". These are contracts about the machinery in web/arena-policy.js:
 *
 *   1. OFF IS OFF. recomb defaults to 0, an explicit 0 is the same bytes, and the off
 *      path consumes NO rng -- every recorded run keeps replaying. The fork, when the
 *      knob is on, is exactly one draw (the coin) on the selfing path.
 *   2. Selfing is the asexual path: no mate in radius means the hatchling keeps its
 *      egg's snapshot untouched, and matings does not count it.
 *   3. A mating mixes: each gene from either lineage on a fair coin, BEFORE mutation;
 *      weights cross by ratio at loci where the lineages differ and nowhere else;
 *      two wild-type-wired parents leave the child wild-type-wired (the short-circuit
 *      spends no coins on identical decks).
 *   4. The pedigree is the record: founders are their own roots, a child hangs off the
 *      LAYING parent with its dynasty, death stamps the twig, and a long dish's family
 *      bible stays bounded without ever forgetting the living.
 *
 * No physics: forceLay + hatchDue drive the whole policy, so the suite runs in
 * milliseconds and every rng draw is accounted for.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { engine, GENES, scaleOf, rng, normalFrom } from './evolve.mjs';
import { makeArena, resolveOptions } from '../web/arena-policy.js';

/* A dish with a counting rng: every draw -- the policy's own and normalFrom's -- goes
 * through `rand.n`, which is what makes "consumes no rng" an assertion instead of a
 * reading of the source. */
function dish(opts, seed = 1) {
  const E = engine();
  const base = rng(seed);
  const rand = () => { rand.n++; return base(); };
  rand.n = 0;
  const normal = normalFrom(rand);
  const midOf = (id) => {
    const f64 = new Float64Array(E.memory.buffer);
    return [f64[(E.ptrNodesX(id) >> 3) + 24], f64[(E.ptrNodesY(id) >> 3) + 24]];
  };
  const arena = makeArena(E, { genes: GENES, scaleOf }, { seed, ...opts },
                          rand, normal, midOf);
  arena.spawnFounders();
  return { E, arena, rand, midOf };
}
const wormIds = (E) => Array.from({ length: E.wormCount() }, (_, k) => E.wormIdAt(k));

test('recomb defaults off, and off consumes no rng', () => {
  assert.equal(resolveOptions({}).recomb, 0);
  assert.equal(resolveOptions({}).recombR, 9);

  // Twin dishes, same seed, same ops: the default knob and an explicit 0 must draw the
  // same stream and hatch the same animal -- byte-identical genes, zero matings.
  const run = (opts) => {
    const { E, arena, rand } = dish(opts, 7);
    const parent = wormIds(E)[0];
    E.forceLay(parent);
    arena.simT = 100;
    arena.hatchDue();
    const kid = wormIds(E).find((id) => arena.pedigree.get(id).parent >= 0);
    return { draws: rand.n, matings: arena.matings,
             genes: GENES.map((_, s) => E.getGene(kid, s)) };
  };
  const dflt = run({});
  const zero = run({ recomb: 0 });
  assert.equal(dflt.matings, 0);
  assert.equal(zero.matings, 0);
  assert.equal(dflt.draws, zero.draws, 'an explicit 0 must not move the stream');
  assert.deepEqual(dflt.genes, zero.genes, 'the hatchling must be the same animal');
});

test('selfing: no mate in radius, no mating, and the fork is exactly the coin', () => {
  // One founder lays and is buried before the hatch: the child is alone on the plate.
  const run = (recomb) => {
    const { E, arena, rand } = dish({ founders: 1, recomb }, 7);
    const parent = wormIds(E)[0];
    E.forceLay(parent);
    arena.die(parent, 'culled');
    arena.simT = 100;
    arena.hatchDue();
    const child = wormIds(E)[0];
    return { draws: rand.n, matings: arena.matings, child,
             genes: GENES.map((_, s) => E.getGene(child, s)) };
  };
  const asex = run(0);
  const self = run(1);
  assert.equal(self.matings, 0, 'selfing must not count as a mating');
  assert.equal(self.draws, asex.draws + 1,
    'recomb on, nobody near: the stream forks by the one coin and nothing else');
});

test('a mating mixes genes from both lineages, fair coin, before mutation', () => {
  // Two founders made distinguishable: B's every gene shifted by a known delta. A lays;
  // A is moved out of radius and B moved next to the egg, so the nearest mate is the
  // OTHER lineage. Mutation off, so the child's genome is pure crossover.
  const { E, arena } = dish({ founders: 2, recomb: 1, recombR: 8, mut: 0 }, 11);
  const [A, B] = wormIds(E);
  const aGene = GENES.map((_, s) => E.getGene(A, s));
  const delta = 0.037;
  GENES.forEach((_, s) => E.setGene(B, s, aGene[s] + delta));
  E.forceLay(A);
  E.translateWorm(A, 20, 0);          // out of the 8 mm radius
  // Park B near the egg site: A stood at ring angle 0 -> (6, 0); B at (-6, 0), 12 mm out.
  E.translateWorm(B, 10, 0);          // B now ~2 mm from the egg
  arena.simT = 100;
  arena.hatchDue();
  assert.equal(arena.matings, 1, 'the child had a mate in radius');
  const child = wormIds(E).find((id) => arena.pedigree.get(id).parent >= 0);
  const from = GENES.map((_, s) => {
    const v = E.getGene(child, s);
    if (Math.abs(v - aGene[s]) < 1e-12) return 'A';
    if (Math.abs(v - (aGene[s] + delta)) < 1e-12) return 'B';
    return '?';
  });
  assert.ok(!from.includes('?'), `every gene must come from one lineage: ${from}`);
  assert.ok(from.includes('A') && from.includes('B'),
    `a fair coin over ${GENES.length} genes shows both parents (seed-pinned): ${from}`);
  // Two wild-type-wired parents leave a wild-type-wired child: the weight pass
  // short-circuited, no clone was made for nothing.
  assert.equal(E.hasOwnWeights(child), 0, 'identical decks must not buy a copy');

  // The pedigree half of the same event: the child hangs off the LAYING parent.
  const twig = arena.pedigree.get(child);
  assert.equal(twig.parent, A, 'descent follows the laying parent, not the mate');
  assert.equal(twig.born, 100);
  assert.equal(twig.died, null);
  assert.equal(twig.dyn, arena.founderOf.get(A) ?? -1, 'dynasty is the patriline');
});

test('weights cross by ratio where the lineages differ, and nowhere else', () => {
  const { E, arena } = dish({ founders: 2, recomb: 1, recombR: 8, mut: 0 }, 13);
  const [A, B] = wormIds(E);
  const k = 42, wild = E.getWeight(A, 0, k);
  E.scaleWeight(B, 0, k, 4.0);        // B's lineage carries one quadrupled synapse
  E.developWorm(B);
  E.forceLay(A);                      // the egg is A's snapshot: wild-type wiring
  E.translateWorm(A, 20, 0);
  E.translateWorm(B, 10, 0);
  arena.simT = 100;
  arena.hatchDue();
  assert.equal(arena.matings, 1);
  const child = wormIds(E).find((id) => arena.pedigree.get(id).parent >= 0);
  const got = E.getWeight(child, 0, k);
  assert.ok(Math.abs(got - wild) < 1e-12 || Math.abs(got - 4 * wild) < 1e-12,
    `locus ${k} must hold one lineage's value, got ${got} against wild ${wild}`);
  // Everywhere the lineages agree, the child agrees too: the ratio pass skips
  // identical loci, so no other synapse moved.
  for (const probe of [0, 7, 41, 43, 100, 1000, 2278]) {
    if (probe === k) continue;
    assert.equal(E.getWeight(child, 0, probe), E.getWeight(A, 0, probe),
      `locus ${probe} moved though both lineages agreed there`);
  }
});

test('the pedigree stays bounded without forgetting the living', () => {
  const { E, arena } = dish({ founders: 4 }, 3);
  // A long dish's worth of finished twigs, planted directly: the bound is policy
  // bookkeeping, not simulation, and 650 simulated lifetimes buys no extra truth.
  for (let i = 0; i < 650; i++) {
    arena.pedigree.set(100000 + i, { parent: -1, born: i, died: i + 1, dyn: 0 });
  }
  const living = wormIds(E);
  arena.die(living[0], 'culled');     // any death runs the prune pass
  assert.ok(arena.pedigree.size <= 401,
    `the family bible must stay bounded, holds ${arena.pedigree.size}`);
  for (const id of wormIds(E)) {
    assert.ok(arena.pedigree.get(id), `living animal ${id} pruned from the record`);
    assert.equal(arena.pedigree.get(id).died, null);
  }
});
