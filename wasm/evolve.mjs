/* Evolve the animal's behaviour, on the runtime, in the browser's own engine.
 *
 *     node wasm/evolve.mjs
 *     EVO_POP=16 EVO_GENERATIONS=10 EVO_SECONDS=40 node wasm/evolve.mjs
 *
 * NEXT.md argued that a population stopped being an architectural problem once the port
 * landed, and set out three tiers of heritability. This is tier one: the fifteen scalars
 * each `Worm` now carries, mutated and selected on an energy budget -- what the animal
 * takes in, less what it spends moving. It is deliberately the cheap version -- asexual
 * copy-with-mutation, selection from outside the dish -- because the point of building it
 * first was to find out whether the fitness measure is any good, and that question does
 * not need the honest version to answer. It was not: see "WHAT FITNESS IS" below.
 *
 * WHAT IS AND IS NOT SAFE TO EVOLVE, WHICH IS NOT AN ACCIDENT.
 *
 * NEXT.md's caution is that evolution finds bugs enthusiastically -- a way to gain food
 * without foraging, or a parameter that makes the integrator unstable in a profitable
 * direction. Both of those exist in this model *today*, and are measured:
 *
 *   * `volume_per_pump` x10 buys 9.3x the food on this assay at an unchanged trajectory.
 *     It is a unit conversion sitting in front of the fitness measure (#37). The gene list
 *     keeps a *gene* off it; the `energy` measure below keeps the *measure* off it, which
 *     is the half a gene list cannot do -- a re-export can still move a constant.
 *   * `body.EI` set negative gives an animal reporting 1.38e20 mm of displacement, finite,
 *     with no exception, warning or NaN (#38).
 *
 * Neither is reachable from here, and that is why the gene list was chosen the way it was:
 * every one of the fifteen is a sensory gain, a time constant or a decision threshold.
 * None of them is a conversion factor in front of intake, and none of them is a mechanical
 * property -- the bending modulus, the drag coefficients and the muscle balance are
 * anatomy, baked into the payload, and cannot be addressed by a gene at all. So a mutant
 * here can be *bad at being a worm* but it cannot stop being one.
 *
 * That is a property of the genome, not of this file, and it is worth restating whenever
 * the genome grows.
 *
 * WHAT FITNESS IS, AND WHY IT IS NOT `food_eaten`. (#37)
 *
 * `EVO_FITNESS=eaten` selects on intake, which is what NEXT.md proposed and what the
 * selection results quoted below were measured under. It is exploitable, and #37 measured
 * the exploit rather than arguing it. Re-measured here, on this file's own assay -- one
 * animal per plate, 15 s, three seeds -- with `volume_per_pump` raised tenfold in the
 * runtime's compiled constant and nothing else touched:
 *
 *     seed   food_eaten, wild   food_eaten, x10    ratio   drag ratio   net displ. ratio
 *       5        0.0095670          0.0890170      9.305     1.000028         0.999998
 *      11        0.0120774          0.1065927      8.826     1.000015         1.000010
 *      23        0.0107358          0.0994390      9.262     1.000033         1.000004
 *
 * Nine times the fitness, and the animal's trajectory is the same one to five figures.
 * #37's comment measured 9.3x for the same mutation; this reproduces it. Nothing about
 * foraging improved -- a conversion factor in front of the measure got bigger.
 *
 * `EVO_FITNESS=energy` -- the default -- is the energy budget #37 asked for:
 *
 *     fitness = ingested / volume_per_pump  -  EVO_LAMBDA * integral of v^2 dt
 *               \_______ intake ________/      \______ locomotion cost _______/
 *
 * Two decisions, and the first is the one that closes #37.
 *
 * INTAKE IS COUNTED IN PUMP-VOLUMES, NOT IN FOOD UNITS. Subtracting a cost does not, on
 * its own, fix anything. This is the trap worth recording, because it is the obvious
 * reading of "ingested minus a locomotion cost" and it makes the hole *wider*: the cost is
 * a constant with respect to the pharynx, and subtracting a constant from a multiplied
 * quantity multiplies the *difference* by more, not less. Measured, by running exactly
 * this expression with the un-normalised intake -- `ingested - lambda * drag`, everything
 * else identical:
 *
 *     seed   ratio under `eaten`   ratio under raw intake minus a cost
 *       5           9.305                        12.967
 *      11           8.826                        11.124
 *      23           9.262                        12.417
 *
 * The budget made it worse. A budget only helps once the two terms are in a currency the
 * anatomy cannot mint.
 *
 * So intake is divided by `ph_volume_per_pump`, read out of the model header -- the same
 * number the runtime compiles in. `volume_per_pump` is precisely the coefficient that
 * converts "one pump at unit density" into "an amount of food"; dividing it back out
 * leaves a dimensionless count of pump-volumes, which is a statement about *behaviour*
 * (how many pumps, at what density, with how much lumen headroom) rather than about how
 * generously the pharynx has been specified. #37's third item offers exactly this --
 * "freeze the pharyngeal and uterine conversion constants out of the genome, **or
 * normalise by them**"; the freeze is already done in `tools/export_model.py`'s `GENES`,
 * and this is the belt to that pair of braces. The freeze stops a *gene* reaching the
 * constant; the normalisation stops a *re-export* reaching it.
 *
 * What that buys, same runs:
 *
 *     seed   energy, wild   energy, vpp x10    ratio
 *       5        1.32784         1.19477       0.900
 *      11        1.86711         1.58349       0.848
 *      23        1.55383         1.39542       0.898
 *
 * 9.3x becomes 0.85-0.90x. The exploit is not merely smaller, it has changed sign: a
 * tenfold pharynx now *costs* fitness, and a direction that loses fitness is not a
 * direction a search follows. Over six seeds at 10 s the ratio runs 0.54 to 0.91 against
 * `food_eaten`'s 6.1 to 9.3; the worst case is a 46% penalty and there is no case that
 * pays.
 *
 * The residual is worth naming rather than rounding away, and the first guess about it was
 * wrong. It looks like patch depletion -- a mouth ten times the size strips its cells ten
 * times faster, and since #45 the plate debit conserves -- but it is not. Scaling
 * `lumen_capacity` by ten *alongside* `volume_per_pump` restores specific intake to
 * 0.9944 to 0.9980 of wild on every one of six seeds, i.e. flat to 0.6%, including the
 * seed where `volume_per_pump` alone costs 39%. Depletion would not care about the lumen
 * at all. So the residual is the `room` factor in `_fire`: a pump ten times bigger leaves
 * the lumen ten times fuller at the next pump, and captures less. That is real saturation
 * in the model, not the unit conversion coming back, and it is a diminishing return rather
 * than an increasing one.
 *
 * `lumen_capacity` on its own, #37's other scalar, barely registers on this runtime:
 * x10 moves `food_eaten` by 1.0071 / 1.0124 / 1.0077. #37's table had it worth a further
 * 1.66x on top of `volume_per_pump`; here it is worth 1.07x (9.305 -> 9.964 on seed 5).
 * That table was measured on the Python pharynx before #45 landed. The total is the same
 * order; the split between the two scalars is not, and it is reported here as it measures
 * *now* rather than as it was.
 *
 * THE LOCOMOTION COST IS A PROXY, AND SAYING SO IS PART OF THE MEASURE. At zero Reynolds
 * number -- `worm/body.py` puts a swimming C. elegans at Re around 1e-3, which is not
 * "small inertia" but "no inertia" -- there is no kinetic energy store, so the power the
 * body spends is the power it loses to drag, and resistive force theory makes that
 * quadratic in velocity: P = integral over the body of (c_T v_T^2 + c_N v_N^2) ds. The
 * runtime already assembles exactly that tensor in `dragMatrix`, but it does not export
 * the power, and exporting it means editing `wasm/assembly/index.ts` and rebuilding
 * `web/worm.wasm`, which is out of scope for this change. So the driver integrates
 * `sum(v^2 dt)` from the head position it *can* read, via `getX`/`getY`.
 *
 * What that is and is not:
 *
 *   * It is the right *shape*. Quadratic in speed, so it is dominated by the undulation
 *     rather than by net progress -- an animal thrashing in place pays, which is the whole
 *     point of costing locomotion at all -- and it is `energy` up to a single constant
 *     with units of (drag coefficient x length).
 *   * It is one point on a 49-node body, not the integral over all of it, so it weights
 *     the head's lateral sweep as if the whole animal moved that way. Head amplitude is
 *     the largest on the body, so this over-reads a real body integral rather than
 *     under-reading it.
 *   * It does not separate tangential from normal drag, so the c_N/c_T anisotropy that
 *     makes undulatory swimming work at all is absent. A body-integral version would.
 *
 * Replacing it with the real integral is a runtime export away, and the fitness expression
 * would not change -- only what feeds `drag`. That is the point of writing it this way.
 *
 * The proxy is sampled every `DRAG_SAMPLE_DT` seconds rather than every 0.5 ms step, and
 * 0.01 s was chosen by measuring the convergence rather than by taste. Seed 5, 15 s, this
 * assay:
 *
 *     sample interval   0.001    0.002    0.004    0.010    0.020    0.040    0.100
 *     integral v^2 dt   5.85781  5.85774  5.85747  5.85553  5.84864  5.82142  5.64799
 *
 * 0.01 s is 0.04% off the finest sampling and costs it a tenth of the readings; 0.1 s
 * loses 3.6% and is where the undulation starts to alias. `stepAll` carries no state
 * between calls -- it is a bare loop over single steps -- so chunking the run in order to
 * sample changes nothing about the trajectory. That is an assumption about a file this
 * change is not allowed to touch, so `energy-fitness.test.mjs` asserts it directly rather
 * than trusting this sentence.
 *
 * EVO_LAMBDA is the exchange rate between the two terms, and it is the one free constant
 * left. It is a property of the fitness function, not of the animal: no gene and no
 * re-export can move it, which is the whole reason the normalisation above had to happen
 * first. The default of 0.1 was calibrated so the wild type spends a visible but minority
 * share of its budget on moving. Measured over the same three seeds at 15 s: intake 1.913
 * / 2.415 / 2.147 pump-volumes against drag 5.856 / 5.484 / 5.933, so lambda 0.1 puts
 * locomotion at 31% / 23% / 28% of intake and leaves fitness at 1.328 / 1.867 / 1.554 --
 * positive with room to spare. Break-even is lambda 0.33 to 0.44 on these seeds; setting
 * it there would make wild-type fitness hover around zero and change sign on noise, which
 * is a worse measure rather than a stricter one.
 *
 * WHAT THIS DOES NOT CLOSE. `eggs_per_food` is the same shape of hole one layer along --
 * #37's opening paragraph says so -- and an egg-count fitness would inherit it whole. The
 * same normalisation applies (`egl_eggs_per_food` is exported in the header for it), but
 * nothing selects on eggs yet, so there is nothing here to normalise and a measure written
 * for a caller that does not exist is a measure nobody has tested.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

const POP = Number(process.env.EVO_POP || 8);
const GENERATIONS = Number(process.env.EVO_GENERATIONS || 5);
const SECONDS = Number(process.env.EVO_SECONDS || 25);
const SIGMA = Number(process.env.EVO_SIGMA || 0.12);   // mutation size, in units of a gene's own scale
const SEED = Number(process.env.EVO_SEED || 1);
const FITNESS = process.env.EVO_FITNESS || 'energy';
const LAMBDA = Number(process.env.EVO_LAMBDA ?? 0.1);

/* Run as a program, or imported as a library?
 *
 * `energy-fitness.test.mjs` imports `assay` and `fitness` and drives them against a
 * runtime it has patched, because patching the compiled constant is the only way to vary
 * `volume_per_pump` from outside the payload. That import must not start a forty-minute
 * evolution -- hence the guard around the driver at the bottom -- and a missing artefact
 * has to arrive as an exception the runner can attribute rather than as a `process.exit`
 * from inside somebody's import, which surfaces as "the test file produced no tests".
 */
const IS_MAIN = process.argv[1] !== undefined
             && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
function bail(msg) {
  if (!IS_MAIN) throw new Error(msg);
  console.error(msg);
  process.exit(2);
}

// Checked here rather than where it is first used, which is inside the scoring loop after
// a generation has already been simulated. A typo in an environment variable should cost a
// second, not forty minutes.
if (FITNESS !== 'energy' && FITNESS !== 'eaten') {
  bail(`EVO_FITNESS=${FITNESS} is not a measure this file implements; use 'energy' (the `
     + `energy budget, the default) or 'eaten' (raw intake, exploitable -- see #37)`);
}
if (!Number.isFinite(LAMBDA) || LAMBDA < 0) {
  bail(`EVO_LAMBDA=${process.env.EVO_LAMBDA} is not a non-negative number; it is the price `
     + `of moving, and a negative one would pay animals to thrash`);
}

for (const [file, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(file))) bail(`Missing ${file}; generate it with: ${how}`);
}

const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
const payload = modelBuf.subarray(12 + headLen);
const compiled = new WebAssembly.Module(wasmBuf);
const GENES = head.genes || [];
if (!GENES.length) {
  bail('this model declares no genes; export it from a tree that has them');
}
const DT = head.scalars.dt;
const STEPS = Math.round(SECONDS / DT);

/* The pharyngeal conversion constant, read from the model rather than assumed.
 *
 * This is the number `energy` fitness divides intake by, and it is the number #37 is
 * about, so it is read from the header the runtime was built alongside and checked. A
 * model that did not export it would silently make the normalisation a no-op -- fitness
 * would go back to being an intake total in disguise, with nothing anywhere saying so.
 */
export const VOLUME_PER_PUMP = head.scalars.ph_volume_per_pump;
if (!(VOLUME_PER_PUMP > 0)) {
  bail('this model exports no positive ph_volume_per_pump, so intake cannot be normalised '
     + 'into pump-volumes; re-export with tools/export_model.py');
}

/* How often the head position is read to build the drag proxy. See the header: 0.01 s is
 * 0.04% off sampling every 0.5 ms step, and 0.1 s loses 3.5% to aliasing the undulation. */
export const DRAG_SAMPLE_DT = 0.01;

/* Mutation size, per gene.
 *
 * A single multiplicative kick is the obvious choice and it is wrong here for two reasons.
 * The genes span 0.04 (`gate_bias`) to 4000 (`repellent_d_gain`), so one relative step
 * means wildly different things; and `mod_serotonin_mod1` ships at exactly 0.0, which a
 * multiplicative operator can never move off. So each gene carries a scale, and a mutation
 * is an additive draw of `SIGMA * scale`.
 *
 * The scale is the shipped value where that is meaningful. Where it is not -- a gene at
 * zero, or one that is a fraction rather than a magnitude -- it is stated, with the reason.
 */
const SCALE = {
  // Ships at zero. params.py documents 0.30 as the adopted setting and 0.60 as past the
  // corner, so a tenth of that range is a sensible step to explore it with.
  mod_serotonin_mod1: 0.10,
  // A fraction, not a magnitude: 1.0 is always-ventral, 0.5 is the shipped bias.
  sen_omega_ventral_fraction: 0.15,
  // A difference between two activations, and small: the hysteresis it lives inside is
  // 0.09, so scaling by the value itself would step far too coarsely.
  sen_gate_bias: 0.02,
  sen_gate_hysteresis: 0.02,
};
/* Bounds. Loose on purpose -- the interesting answers are the ones nobody predicted, and a
 * tight box just returns the box. These stop a gene going somewhere *meaningless* rather
 * than somewhere surprising: a negative conductance gain is not a worse worm, it is a
 * sign error, and a ventral fraction above 1 is not a stronger bias, it is the same as 1.
 */
const BOUNDS = {
  sen_omega_ventral_fraction: [0.0, 1.0],
  sen_gate_hysteresis: [0.005, 0.5],   // zero is a latch with no window at all
  mod_serotonin_mod1: [0.0, 2.0],
};
const scaleOf = (name) => SCALE[name] ?? (Math.abs(head.scalars[name]) || 1.0);
const clampGene = (name, v) => {
  const b = BOUNDS[name];
  if (b) return Math.min(b[1], Math.max(b[0], v));
  // Everything else is a gain or a drive. Negative would invert a pathway rather than
  // weaken it, which is a different animal rather than a worse one.
  return name === 'sen_gate_bias' ? v : Math.max(0.0, v);
};

/* A seeded PRNG, so a run is reproducible from EVO_SEED. Math.random would make every
 * result a story rather than a measurement. */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function normalFrom(rand) {                // Box-Muller
  return () => {
    const u = Math.max(rand(), 1e-12), v = rand();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
}

/* Instantiate the runtime and hand it the payload.
 *
 * `mod` is a parameter rather than the module-level `compiled` so that a caller can supply
 * a *different* build of the same payload. That is not decoration: `volume_per_pump` is
 * not a gene and is not in the payload either -- it is a compiled-in constant in
 * `wasm/assembly/model_gen.ts` -- so the only way to ask "what would this measure do if
 * the pharynx were ten times bigger" is to hand in a module whose constant has been
 * changed. `energy-fitness.test.mjs` does exactly that, and this signature is what lets it.
 */
export function engine(mod = compiled) {
  const E = new WebAssembly.Instance(mod, {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  return E;
}

/* Run a set of already-created animals for `steps`, sampling what fitness needs.
 *
 * The trajectory is untouched by this. `stepAll(n)` is a bare `for` loop over single
 * steps with no state carried between calls, so `stepAll(a); stepAll(b)` is the same
 * trajectory as `stepAll(a + b)` -- the whole reason the drag proxy can be built from
 * outside the runtime at all. That is an assumption about somebody else's file, so
 * `energy-fitness.test.mjs` asserts it rather than trusting this comment.
 *
 * `drag` is the proxy described in the header: `sum(v^2 dt)` over head samples, which is
 * the body's drag integral up to a coefficient. `net` is displacement from the drop point,
 * kept because an animal that never found its lawn should be visible as such rather than
 * only as a low score.
 */
export function assay(E, ids, steps, opts = {}) {
  const sampleDt = opts.sampleDt ?? DRAG_SAMPLE_DT;
  const dt = opts.dt ?? DT;
  const chunk = Math.max(1, Math.round(sampleDt / dt));
  const x0 = ids.map((id) => E.getX(id));
  const y0 = ids.map((id) => E.getY(id));
  const px = x0.slice(), py = y0.slice();
  const drag = ids.map(() => 0.0);
  const path = ids.map(() => 0.0);
  // First invariant an animal broke, 0 for those that never did. Sampled per chunk rather
  // than per step: the check is a few hundred operations against a chunk that is hundreds
  // of steps, and an animal that has stopped doing physics does not recover.
  //
  // A real engine that cannot check invariants is an error, not a reason to skip them
  // quietly -- a guard that disables itself when it goes missing is worse than no guard,
  // because the run still looks guarded. The scripted stand-in in energy-fitness.test.mjs
  // is the legitimate exception and passes `invariants: false` to say so.
  const guard = opts.invariants ?? true;
  if (guard && typeof E.checkInvariants !== 'function') {
    throw new Error('this engine cannot checkInvariants; rebuild the runtime, or pass ' +
                    'invariants: false if it is deliberately a stand-in');
  }
  const diverged = ids.map(() => 0);
  for (let done = 0; done < steps; done += chunk) {
    const n = Math.min(chunk, steps - done);
    E.stepAll(n);
    const h = n * dt;
    for (let i = 0; i < ids.length; i++) {
      const x = E.getX(ids[i]), y = E.getY(ids[i]);
      const d = Math.hypot(x - px[i], y - py[i]);
      // (d/h)^2 * h == d^2/h. Written the long way because the quantity being integrated
      // is a squared speed, and the reader should not have to reconstruct that.
      drag[i] += (d / h) ** 2 * h;
      path[i] += d;
      px[i] = x; py[i] = y;
      if (guard && diverged[i] === 0) diverged[i] = E.checkInvariants(ids[i]);
    }
  }
  return ids.map((id, i) => ({
    eaten: E.getEaten(id),
    ingested: E.getIngested(id),
    laid: E.getEggsLaid(id),
    drag: drag[i],
    path: path[i],
    moved: Math.hypot(E.getX(id) - x0[i], E.getY(id) - y0[i]),
    diverged: diverged[i],
  }));
}

/* The measure. One record in, one number out.
 *
 * `volumePerPump` and `lambda` are arguments with defaults rather than closed-over
 * constants, because a caller that has changed the runtime's pharynx has to be able to say
 * so. In the driver below they are the model's own value and EVO_LAMBDA. In the test they
 * are the *patched* value, which is the honest thing: patching the compiled constant is
 * standing in for editing `worm/params.py` and re-exporting, and a re-export moves the
 * header and the compiled constant together.
 *
 * Read the failure mode that matters: if this function ignored `volumePerPump`, or if the
 * caller passed the shipped 0.005 while running a x10 runtime, `energy` would inherit
 * `eaten`'s 9x exploit whole. The test asserts both directions -- right normaliser, flat;
 * wrong normaliser, 9x -- so "the division is load-bearing" is checked rather than claimed.
 */
export function fitness(rec, opts = {}) {
  // An animal that stopped doing physics scores nothing, whatever it accumulated on the
  // way out. This is checked before the mode, because it is not a statement about which
  // measure is in use -- a diverged animal's `ingested` and `drag` are both meaningless,
  // and #38's mutant reported 10^20 mm of displacement without raising anything at all.
  // `diverged` is absent on records built before this existed, which read as 0 and score
  // normally; that is deliberate, so an old record is not silently reclassified as lethal.
  if (rec.diverged) return 0;
  const mode = opts.mode ?? FITNESS;
  if (mode === 'eaten') return rec.eaten;
  if (mode !== 'energy') {
    throw new Error(`unknown EVO_FITNESS=${mode}; expected 'energy' or 'eaten'`);
  }
  const vpp = opts.volumePerPump ?? VOLUME_PER_PUMP;
  const lambda = opts.lambda ?? LAMBDA;
  return rec.ingested / vpp - lambda * rec.drag;
}

/* Every animal gets its own lawn, and starts on it, off-centre.
 *
 * Not a shared plate, deliberately. Feeding is order-dependent while several animals draw
 * on the same cells -- worm 0 samples a full neighbourhood and worm 3 samples what three
 * others have been served from, a systematic 0.09% per four seconds in array order (#32).
 * That is small against a real genetic difference and it is not small against nothing, and
 * a first run should not have to argue about which it is measuring.
 *
 * ON the lawn, and this is the part worth reading, because the reason is not the one an
 * earlier version of this comment gave. Dropping an animal *outside* its lawn would make
 * the score integrative in the way NEXT.md wants -- find the food, stay on it, pump. The
 * first calibration of that reported it scoring nothing at all, 0/3 animals arriving from
 * one millimetre outside the edge, and concluded the landscape was flat off the lawn.
 *
 * It is not. That calibration launched every animal *tangentially*, and this animal walks
 * in a nearly straight line, so it measured the drop angle rather than the animal.  Same
 * lawn, same three seeds, same 30 s, varying only the initial heading:
 *
 *     dropped at   pointed at the lawn      tangential        pointed away
 *         5 mm       3/3   0.18576        0/3   0.00000      0/3   0.00000
 *         8 mm       3/3   0.12276        0/3   0.00000      0/3   0.00000
 *
 * An animal dropped 8 mm out -- four millimetres clear of the edge -- and pointed at the
 * lawn eats more than one dropped dead centre and pointed sideways (0.09395). The
 * landscape off the lawn is not flat; it is dominated by one initial condition the genome
 * has no say in. With noise off the animal covers 3.24 mm in 10 s in a straight line, and
 * whether that line crosses a radius-4 disc is settled at t=0.
 *
 * That does *not* rescue foraging as an evolvable trait, and for the original reason:
 * README puts the chemotaxis index at +0.083 against an animal's +0.5 or better, so
 * arrival here is ballistics, not gradient climbing. A genome cannot be selected for
 * aiming, because it is not the genome that aims. But the honest statement is "arrival is
 * decided by the drop heading", not "every genome scores zero" -- the second is false and
 * was measured wrong.
 *
 * So the assay selects for what *does* vary once aiming is taken off the table: staying on
 * food and feeding well. Every animal gets the same heading relative to its own lawn, which
 * makes the drop angle a controlled constant rather than a lottery.
 *
 * WHAT IT SELECTED, AND THE REASON TO BELIEVE IT.
 *
 * Everything in this section was measured under `EVO_FITNESS=eaten`, in units of food
 * eaten, before the energy budget existed. It is left as measured rather than rescaled: a
 * number quoted in units the file no longer defaults to is recoverable, and a number
 * quietly re-expressed in units nobody re-ran it in is not. The gene movements are the
 * part worth carrying forward, and they are about the assay rather than the measure.
 *
 * 8 animals, 5 generations, 15 s, sigma 0.12, three seeds, against a selection-off control:
 *
 *     selection - control   0.01687 +- 0.00506 (s.e.)
 *
 * positive on every seed, on a first-generation median around 0.011 -- so selection
 * roughly triples median intake in five generations while the control arm goes nowhere
 * (+0.00214, -0.00128, +0.00085). That is the shape a control arm is supposed to have.
 *
 * The result worth trusting is not the effect size, though. It is which way two genes
 * moved:
 *
 *     gene                 wild    selected   control
 *     sen_tonic_forward    22.0       17.5      21.0
 *     sen_cord_drive        8.0        6.5       8.3
 *
 * Both down about 20%, both flat in the control. Less forward drive is exactly what "do
 * not walk off your lawn" asks for, and it is the adaptation this assay was built to
 * reward.
 *
 * Before the heading above was fixed, the same code aimed every animal *through* the
 * middle of its lawn, and the same two genes moved the *other way* -- tonic_forward 22 ->
 * 24.5, cord_drive 8 -> 10.1 -- because sprinting across a bullseye is what that assay
 * rewarded. The genes tracked the trait being selected, and reversed when the trait did.
 * A number that moves when the assay changes and in the direction the change implies is
 * worth more than a number that is merely large; the old run's effect was real too, and it
 * was an artefact.
 */
const RING = 26.0;         // mm between neighbouring lawns -- far past any interaction
const OFFSET = 3.0;        // mm off the lawn's centre; the lawn's radius is 4
function plate(E, n) {
  const spots = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const lx = Math.cos(a) * RING, ly = Math.sin(a) * RING;
    E.addFood(lx, ly, 4.0, 1.0, 1.0, 9.0);
    // Off-centre and pointing outwards, so an animal that simply swims straight ahead
    // leaves the lawn. Holding station is a behaviour, and this is what scores it.
    //
    // The `+ Math.PI` is not decoration. createWorm's fourth argument sets the direction
    // the *body trails*, not the direction the animal faces: node 0 is the mouth and sits
    // at (x, y), and updateNodes lays the rest of the body out along `heading` behind it,
    // so the animal travels at `heading + pi`. Measured, not inferred -- a worm created at
    // the origin with heading 0 and no noise is at (-3.23, +0.10) ten seconds later.
    // Without the half turn this line did the exact opposite of what it claims: it aimed
    // every animal straight through the middle of its own lawn.
    spots.push([lx + Math.cos(a) * OFFSET, ly + Math.sin(a) * OFFSET, a + Math.PI]);
  }
  return spots;
}

/* Put a population on plates and run it. `spots` is exported alongside the records because
 * a caller reproducing this assay for one animal needs the same drop point and heading. */
export function seedPlate(E, n, seed) {
  const spots = plate(E, n);
  return spots.map((s, i) => {
    const id = E.createWorm(1000 + i * 7717 + seed * 131, ...s);
    return id;
  });
}

function evaluate(genomes, seed) {
  const E = engine();
  E.setNoise(1);                       // real animals; the genome is what we are comparing
  const ids = seedPlate(E, genomes.length, seed);
  ids.forEach((id, i) => genomes[i].forEach((v, s) => E.setGene(id, s, v)));
  return assay(E, ids, STEPS);
}

const wild = GENES.map((n) => head.scalars[n]);
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const sd = (xs) => {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
};

/* One experiment: a population, N generations, selection either on or off.
 *
 * `select` is the only thing that differs between the two arms, and everything else is
 * held identical -- same environment seed, same worm seeds, same mutation stream from the
 * same PRNG seed, same starting population. That is common random numbers, and it is the
 * whole reason a difference between the arms means anything: animal-to-animal variance is
 * most of the variance here, and pairing cancels it. tools/compare.py does the same for the
 * behavioural assays, for the same reason.
 */
function runArm(seed, select, log) {
  const rand = rng(seed);
  const normal = normalFrom(rand);
  const mutate = (g) => g.map((v, s) => clampGene(GENES[s], v + normal() * SIGMA * scaleOf(GENES[s])));
  let population = Array.from({ length: POP }, (_, i) => (i === 0 ? wild.slice() : mutate(wild)));
  const history = [];
  for (let gen = 0; gen < GENERATIONS; gen++) {
    const scored = evaluate(population, seed)
      .map((r, i) => ({ ...r, genome: population[i], score: fitness(r) }));
    scored.sort((a, b) => b.score - a.score);
    const scores = scored.map((x) => x.score);
    history.push({ best: scores[0], median: median(scores), mean: mean(scores),
                   drag: mean(scored.map((x) => x.drag)),
                   // Intake in the same pump-volumes the budget is written in, so the two
                   // halves of the report are in the same units as each other.
                   intake: mean(scored.map((x) => x.ingested / VOLUME_PER_PUMP)),
                   means: GENES.map((_, s) => mean(scored.map((x) => x.genome[s]))) });
    if (log) {
      console.log(`  ${log} seed ${seed} gen ${gen}: best ${scores[0].toFixed(5)} `
                + `median ${median(scores).toFixed(5)}`);
    }
    /* Truncation selection, or the control.
     *
     * The control breeds from parents drawn uniformly at random -- the same number of
     * offspring, the same mutation operator, the same everything, chosen without reference
     * to fitness. A rising median in the selected arm means nothing until it beats this,
     * because a population whose worst members are replaced by *anything* drifts upward
     * when the measure is noisy and the survivors are resampled.
     */
    const pool = select
      ? scored.slice(0, Math.max(2, Math.floor(POP / 2)))
      : Array.from({ length: Math.max(2, Math.floor(POP / 2)) },
                   () => scored[Math.floor(rand() * scored.length)]);
    const next = [pool[0].genome.slice()];
    while (next.length < POP) next.push(mutate(pool[next.length % pool.length].genome));
    population = next;
  }
  return history;
}

function main() {
  const SEEDS = (process.env.EVO_SEEDS || String(SEED)).split(',').map(Number);
  const CONTROL = process.env.EVO_CONTROL !== '0';

  // Say which measure this run used, in the units it used. A log that reports a bare
  // number under two different fitness functions is a log that cannot be compared with
  // itself six months later; the quoted results in the header carry the same label.
  const describe = FITNESS === 'eaten'
    ? 'fitness = food eaten (#37: exploitable, kept for comparison)'
    : `fitness = ingested/${VOLUME_PER_PUMP} - ${LAMBDA} * integral v^2 dt (energy budget)`;
  console.log(`EVOLUTION -- ${POP} animals, ${GENERATIONS} generations, ${SECONDS} s each, `
            + `sigma ${SIGMA}`);
  console.log(`  ${GENES.length} genes, ${describe}, each animal on its own lawn`);
  console.log(`  seeds ${SEEDS.join(', ')}${CONTROL ? ', with a selection-off control arm' : ''}\n`);

  const t0 = Date.now();
  const runs = [];
  for (const seed of SEEDS) {
    const sel = runArm(seed, true, 'select ');
    const ctl = CONTROL ? runArm(seed, false, 'control') : null;
    runs.push({ seed, sel, ctl });
  }

  /* The paired comparison, which is the only part of this worth quoting.
   *
   * Per seed: how much the median moved from the first generation to the last, in the
   * selected arm and in the control. The difference of those two is the effect of
   * selection on that seed, with the environment held identical. Reported as a spread over
   * seeds rather than a single number, because one run is one sample -- this project
   * learned that on day eighteen, when a four-seed result that "reads as a clear win"
   * turned out to have every interval overlapping every other.
   */
  const gain = (h) => h[h.length - 1].median - h[0].median;
  console.log('\n  seed |  selected gain |  control gain |  difference');
  const diffs = [];
  for (const r of runs) {
    const g = gain(r.sel);
    if (r.ctl) {
      const c = gain(r.ctl);
      diffs.push(g - c);
      console.log(`  ${String(r.seed).padStart(4)} | ${g.toFixed(5).padStart(14)} `
                + `| ${c.toFixed(5).padStart(13)} | ${(g - c).toFixed(5).padStart(11)}`);
    } else {
      console.log(`  ${String(r.seed).padStart(4)} | ${g.toFixed(5).padStart(14)} |            -- |          --`);
    }
  }

  if (diffs.length) {
    const m = mean(diffs), s = sd(diffs);
    // A standard error, not a bootstrap: with a handful of seeds the point is the order of
    // magnitude of the spread against the effect, not a calibrated interval.
    const se = diffs.length > 1 ? s / Math.sqrt(diffs.length) : NaN;
    console.log(`\n  selection - control, over ${diffs.length} seed(s): `
              + `${m.toFixed(5)} +- ${Number.isNaN(se) ? '?' : se.toFixed(5)} (s.e.)`);
    const clears = diffs.length > 1 && Math.abs(m) > 2 * se;
    console.log(clears
      ? '  The difference clears twice its own standard error. That is worth following up.'
      : '  The difference does NOT clear twice its own standard error: this run shows no\n'
        + '  detectable effect of selection. More seeds, more generations, or a fitness\n'
        + '  measure with more dynamic range -- not a louder reading of this one.');
  }

  /* Under `energy`, the two halves of the budget are reported separately as well as
   * combined. A rising score with a falling drag term and a flat intake term is a
   * population that learned to stop moving, which is a legitimate answer to this assay and
   * a completely different finding from one that learned to feed better -- and the
   * combined number cannot tell them apart. */
  if (FITNESS === 'energy') {
    console.log('\n  seed | mean intake, first -> last gen | mean drag, first -> last gen');
    for (const r of runs) {
      const a = r.sel[0], b = r.sel[r.sel.length - 1];
      console.log(`  ${String(r.seed).padStart(4)} | `
                + `${a.intake.toFixed(3).padStart(13)} -> `
                + `${b.intake.toFixed(3).padStart(9)} | `
                + `${a.drag.toFixed(3).padStart(11)} -> ${b.drag.toFixed(3).padStart(9)}`);
    }
  }

  console.log(`\n  wall clock ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  console.log('\n  gene                            wild   selected mean   control mean');
  for (let s = 0; s < GENES.length; s++) {
    const selMean = mean(runs.map((r) => r.sel[r.sel.length - 1].means[s]));
    const ctlMean = runs[0].ctl ? mean(runs.map((r) => r.ctl[r.ctl.length - 1].means[s])) : NaN;
    console.log(`  ${GENES[s].padEnd(30)} ${wild[s].toFixed(4).padStart(9)}`
              + ` ${selMean.toFixed(4).padStart(14)} ${(Number.isNaN(ctlMean) ? '--' : ctlMean.toFixed(4)).padStart(14)}`);
  }
  console.log('\n  A gene is only interesting where the selected column differs from the control');
  console.log('  column by more than the columns differ from each other across seeds.');
}

if (IS_MAIN) main();
