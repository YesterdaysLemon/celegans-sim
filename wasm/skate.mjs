/* The skater trap: the instrument NEXT.md 1c asked for, pointed at the owner's sighting.
 *
 * THE SIGHTING (2026-08-15, the owner's browser dish, medium switched to buffer, ~140
 * births in): lineages that coil into tight spirals and SKATE -- rotating coiled bodies
 * translating in long arcs, header speed past 1500 um/s, kymograph showing deep
 * synchronised bend-blocks instead of a travelling wave. A wheel, not a swimmer.
 *
 * TRACK B, AND LOUDLY: nothing here is a claim about C. elegans. If skating is real and
 * cheap, that is a fact about THIS reconstruction -- 2D resistive-force theory with no
 * worm-worm collision and no cost for holding a deep bend -- and the museum's accession
 * rules (measured, pinned) are the bar this instrument exists to clear.
 *
 * WHAT IT MEASURES, per animal per reporting window:
 *
 *   net        straight-line displacement of the body midpoint over the window, mm.
 *   E_drag     integrated drag dissipation over the window (runtime dragPower * dt) --
 *              the same power the metabolism taxes, so "cheap" here is the dish's own
 *              currency, not an invented score.
 *   transport  net / E_drag: millimetres bought per unit of drag energy. The column the
 *              whole question lives in -- a skater that beats the undulators on it has
 *              found genuinely cheaper transport in this physics, not just faster.
 *   kbar       time-mean of the SIGNED per-joint curvature mean, /mm. An undulator's
 *              wave averages toward zero; a coiled skater holds a deep constant bend, so
 *              |kbar| is the shape signature.
 *   |k|bar     time-mean of the mean |curvature| -- effort of bending, either style.
 *   turns      net body-axis revolutions over the window (head-to-tail axis angle,
 *              unwrapped). Undulators wobble around zero; a skater ROLLS.
 *
 * THE FLAG. A window is called a SKATER when the shape says coil, the axis says roll,
 * and the animal is actually going somewhere:
 *
 *     |kbar| >= 3.0 /mm   AND   |turns| >= 2   AND   net >= 0.10 mm
 *
 * Thresholds are instrument calibration, not biology: an honest undulator in this model
 * runs |kbar| well under 1 /mm (the travelling wave cancels) and net axis rotation near
 * zero, so the gap between the cohorts is wide and the exact numbers are not load-
 * bearing. Every flagged window prints; the first flag per animal snapshots its full
 * heritable state to SKATE_OUT so a catch can be transplanted and preserved as a museum
 * specimen through the same pipeline as the communal jars.
 *
 * THE DISH: the full living plate in BUFFER -- metabolism, corpses, rot, regrowth, wind,
 * juveniles, gene + weight + morphology mutation. Buffer is the medium the sighting came
 * from and the one where drag anisotropy is weakest; agar available for the control arm
 * (SKATE_MEDIUM=agar) so "skaters are a buffer niche" is testable rather than assumed.
 *
 *     node wasm/skate.mjs
 *     SKATE_SECONDS=1500 SKATE_SEED=43 SKATE_MEDIUM=buffer node wasm/skate.mjs
 *
 * THE FIRST HUNTS (2026-08-15, seeds 41/43/47) -- A NULL, AND THREE ECOLOGY FINDINGS.
 * No skater formed. One dish ran the sighting's full protocol end to end: seed 41 held
 * a thriving agar population to the switch (10 animals, 49 births of accumulated
 * mutation) and survived 1,200 s of buffer, eroding 10 -> 1 with ZERO births after the
 * physics changed -- every window read as an honest undulator (|kbar| < 1 /mm, turns
 * near zero, buffer transport 25-60 mm/E against agar's 0.2-0.5). Seeds 43 and 47
 * collapsed on agar before their switches (1 animal each) and closed as dead dishes.
 * One full dish deciding nothing either way -- the owner's sighting stands as a
 * sighting, and the trap stays set.
 *
 * What the hunts DID establish, in three lessons the knobs above now embody:
 *   1. Buffer-from-birth is unsurvivable at this economy: founders cannot reach a lawn
 *      inside their metabolic window (both first dishes extinct, zero births). Hence
 *      SKATE_AGAR_UNTIL.
 *   2. The showcase scarcity is a founder lottery: at lawnScale 0.6/metabT 240, three
 *      of four tested seeds went extinct on AGAR before the first hatch. Hence the
 *      generous plate.
 *   3. Even an established, evolved dish stops LAYING in buffer -- seed 41's births
 *      froze at the switch and never resumed. The plate economy cannot sustain a
 *      buffer population, which bounds how long any hunt can watch selection operate
 *      there (~1,200 s of attrition). A future trap wanting generations IN buffer
 *      needs either a richer plate or laying that survives low drag; the owner's
 *      browser dish had a human topping up lawns, which may be the whole difference.
 */

import fs from 'fs';
import { engine, GENES, scaleOf, rng, normalFrom, DT } from './evolve.mjs';
import { makeArena } from '../web/arena-policy.js';

const env = (k, d) => (process.env[k] !== undefined ? Number(process.env[k]) : d);
const SECONDS = env('SKATE_SECONDS', 1800);
const SEED = env('SKATE_SEED', 41);
const MEDIUM = process.env.SKATE_MEDIUM || 'buffer';
const WINDOW = env('SKATE_WINDOW', 30);          // seconds per transport ledger window
/* THE PROTOCOL IS AGAR FIRST, AND THAT IS A MEASURED CORRECTION, not a convenience. The
 * first hunts ran buffer from birth and both dishes starved -- seed 43 extinct at 0
 * births/4 deaths, seed 41 down to one animal -- because buffer transport is too slow
 * for a founder to reach a 0.6-density lawn inside its metabolic window. The sighting
 * this instrument chases did not happen in a buffer-from-birth dish either: the owner
 * switched an ESTABLISHED, evolving agar population to buffer mid-run. So the trap does
 * what the sighting did -- agar until SKATE_AGAR_UNTIL while dynasties form, then the
 * physics changes under them and the ledger watches who reinvents locomotion. Set it to
 * 0 to reproduce the extinction result. */
const AGAR_UNTIL = env('SKATE_AGAR_UNTIL', 600);
const OUT = process.env.SKATE_OUT || `tmp_skate_seed${SEED}_${MEDIUM}.json`;
const CHUNK = 0.5;

// The model header carries the medium drag pairs; the runtime is switched the same way
// the viewer's Medium buttons switch it. Read directly -- evolve.mjs does not re-export
// the header, and six lines beat a new export nothing else wants.
const modelBuf = fs.readFileSync(new URL('../web/worm.model', import.meta.url));
const headLen = modelBuf.readUInt32LE(8);
const HEAD = JSON.parse(modelBuf.subarray(12, 12 + headLen).toString());
const CT = HEAD.scalars[`med_${MEDIUM}_ct`], CN = HEAD.scalars[`med_${MEDIUM}_cn`];
if (!(CT > 0)) throw new Error(`unknown medium ${MEDIUM}`);

/* A GENEROUS plate, and that is calibration, not science. At the showcase scarcity
 * (lawnScale 0.6, metabT 240, 4 founders) three of four tested seeds went extinct on
 * AGAR before the first hatch -- founder survival there is a lottery, and a trap whose
 * dish is usually dead measures nothing. The hunt needs a dish that reliably reaches an
 * evolving population before the physics switch; how harsh a plate can be before
 * ecology collapses is a different instrument's question. */
const OPT = {
  cap: 10, founders: 8, mut: 0.10, incubation: 45,
  wmut: 0.15, wmutN: 4, mmut: 0.08,
  metab: 0.1, metabT: 360, metabWorkP: 2.0,
  metabFloor: 0.25, metabKnee: 0.35, metabHatch: 0.6,
  corpse: 0.05, corpseYield: 0.8, seed: SEED,
  rotT: 45, regrow: 0.03, juvenile: 0.55, growT: 90,
  wind: 0.03, lawnScale: 0.9,
};

const rand = rng(SEED);
const normal = normalFrom(rand);
const E = engine();
E.setNoise(1);
// Agar for the establishment phase; the hunt medium takes over at AGAR_UNTIL.
if (AGAR_UNTIL <= 0) E.setMedium(CT, CN);

// Fresh views every read: any allocation can grow linear memory and detach old ones.
const f64 = () => new Float64Array(E.memory.buffer);
const nodeAt = (id, k) => {
  const m = f64();
  return [m[(E.ptrNodesX(id) >> 3) + k], m[(E.ptrNodesY(id) >> 3) + k]];
};
const N_JOINTS = HEAD.ints.n_joints;
const MID = HEAD.ints.n_nodes >> 1;

const arena = makeArena(E, { genes: GENES, scaleOf }, OPT, rand, normal,
                        (id) => nodeAt(id, MID));

/* Per-animal ledger for the current window. Keyed by worm id; ids are never reused, so
 * a dead animal's row just stops accumulating and is swept at the window boundary. */
const ledger = new Map();
function openRow(id) {
  const [x, y] = nodeAt(id, MID);
  const [hx, hy] = nodeAt(id, 0);
  const [tx, ty] = nodeAt(id, N_JOINTS);
  return { x0: x, y0: y, E: 0, kSum: 0, kAbsSum: 0, n: 0,
           axis: Math.atan2(ty - hy, tx - hx), turns: 0 };
}

function sample(id, row) {
  row.E += E.getDragPower(id) * CHUNK;
  const m = f64();
  const kp = E.ptrKappa(id) >> 3;
  let s = 0, a = 0;
  for (let j = 0; j < N_JOINTS; j++) { const k = m[kp + j]; s += k; a += Math.abs(k); }
  row.kSum += s / N_JOINTS;
  row.kAbsSum += a / N_JOINTS;
  row.n += 1;
  // Body-axis rotation, unwrapped one sample at a time: at 0.5 s a body cannot turn
  // half a revolution unnoticed at any speed this dish produces.
  const [hx, hy] = nodeAt(id, 0);
  const [tx, ty] = nodeAt(id, N_JOINTS);
  const axis = Math.atan2(ty - hy, tx - hx);
  let d = axis - row.axis;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  row.turns += d / (2 * Math.PI);
  row.axis = axis;
}

const catches = [];                    // first-flag snapshots, written to OUT
const flagged = new Set();             // ids already snapshotted

function snapshot(id, stats, t) {
  catches.push({
    caught: `t=${t}s ${MEDIUM} seed ${SEED}`,
    stats,
    dynasty: arena.founderOf.get(id) ?? -1,
    development: E.getDevelopment(id),
    morphology: Array.from({ length: 12 }, (_, j) => E.getMorph(id, j)),
    genes: GENES.map((g, s) => [g, E.getGene(id, s)]),
    // Weights only where the animal owns a mutated set -- fam x index x value triples
    // would be 3,935 rows; the ratio against a wild-type sibling reconstructs them, and
    // hasOwnWeights says whether there is anything to reconstruct.
    ownWeights: !!E.hasOwnWeights(id),
  });
  fs.writeFileSync(OUT, JSON.stringify({ seed: SEED, medium: MEDIUM, options: OPT,
                                         catches }, null, 1));
}

arena.seedPlate();
arena.spawnFounders();
for (const id of arena.ids()) ledger.set(id, openRow(id));

console.log(`SKATER TRAP -- agar until t=${AGAR_UNTIL}s, then ${MEDIUM} `
  + `(ct ${CT}, cn ${CN}); seed ${SEED}, ${SECONDS} s, window ${WINDOW} s, cap ${OPT.cap}`);
console.log('Track B: nothing below is a claim about C. elegans.');
console.log('flag: |kbar| >= 3.0 /mm AND |turns| >= 2 AND net >= 0.10 mm per window\n');

let simT = 0;
let nextWindow = WINDOW;
let switched = AGAR_UNTIL <= 0;
const t0 = Date.now();
while (simT < SECONDS) {
  E.stepAll(Math.round(CHUNK / DT));
  simT += CHUNK;
  arena.tick(simT);
  if (!switched && simT >= AGAR_UNTIL) {
    E.setMedium(CT, CN);
    switched = true;
    console.log(`  == t=${simT}s: the plate is now ${MEDIUM}. `
      + `${arena.ids().length} animals, ${arena.births} born so far -- new physics, `
      + 'same dynasties ==');
  }
  const pop = arena.ids();
  for (const id of pop) {
    let row = ledger.get(id);
    if (!row) ledger.set(id, row = openRow(id));   // hatched mid-window
    sample(id, row);
  }

  if (simT >= nextWindow) {
    const live = new Set(pop);
    const rows = [];
    for (const [id, r] of ledger) {
      if (!live.has(id) || r.n < 10) continue;     // died, or barely sampled
      const [x, y] = nodeAt(id, MID);
      const net = Math.hypot(x - r.x0, y - r.y0);
      const kbar = r.kSum / r.n, kabs = r.kAbsSum / r.n;
      rows.push({ id, net, E: r.E, transport: r.E > 1e-12 ? net / r.E : 0,
                  kbar, kabs, turns: r.turns,
                  skater: Math.abs(kbar) >= 3.0 && Math.abs(r.turns) >= 2 && net >= 0.10 });
    }
    const skaters = rows.filter((r) => r.skater);
    const undul = rows.filter((r) => Math.abs(r.kbar) < 1.0);
    const best = (xs) => xs.length ? xs.reduce((a, b) => (b.transport > a.transport ? b : a)) : null;
    const bu = best(undul), bs = best(skaters);
    console.log(`t=${String(simT).padStart(5)}s  pop ${rows.length}  `
      + `births ${arena.births}  deaths ${arena.deaths}  skaters ${skaters.length}`
      + (bu ? `  best-undulator ${bu.transport.toFixed(2)} mm/E` : '')
      + (bs ? `  BEST-SKATER ${bs.transport.toFixed(2)} mm/E` : '')
      + `  (${Math.round((Date.now() - t0) / 1000)}s wall)`);
    for (const r of skaters) {
      console.log(`    SKATER id ${r.id}: net ${r.net.toFixed(2)} mm, `
        + `transport ${r.transport.toFixed(2)} mm/E, kbar ${r.kbar.toFixed(2)}/mm, `
        + `|k| ${r.kabs.toFixed(2)}/mm, turns ${r.turns.toFixed(1)}`);
      if (!flagged.has(r.id)) {
        flagged.add(r.id);
        snapshot(r.id, { net: r.net, transport: r.transport, kbar: r.kbar,
                         kabs: r.kabs, turns: r.turns }, simT);
        console.log(`      -> snapshotted to ${OUT}`);
      }
    }
    // Fresh windows for the survivors; the dead leave the ledger with their ids.
    ledger.clear();
    for (const id of pop) ledger.set(id, openRow(id));
    nextWindow += WINDOW;
  }
}

const wall = (Date.now() - t0) / 1000;
console.log(`\ndish closed: ${SECONDS} s in ${wall.toFixed(0)} s wall, `
  + `${arena.births} born, ${arena.deaths} died, ${flagged.size} distinct animal(s) `
  + `flagged as skaters${flagged.size ? `; snapshots in ${OUT}` : ''}.`);
if (!flagged.size) {
  console.log('No skater this run. One seed decides nothing in either direction -- the '
    + 'sighting came from one dish in ~140 births, and this run is priced in the report '
    + 'lines above for when one does form.');
}
