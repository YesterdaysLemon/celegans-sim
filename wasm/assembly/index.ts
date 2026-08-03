/* celegans-sim, WebAssembly runtime.
 *
 * This is the *stepping* half of the model. Everything expensive and fiddly that happens
 * once at construction -- the resting-potential solve, the per-cell muscle balance, the
 * proprioceptive receptive fields, the drag masks -- stays in Python and arrives here as
 * a block of precomputed arrays (see tools/export_model.py). The code below is only the
 * per-step arithmetic, and it reads the same numbers the Python does.
 *
 * That split is the reason this port can be trusted rather than merely believed: any
 * disagreement between the two implementations cannot be in the setup, because both read
 * it out of the same file. Whatever differs is in the stepping, which is where a
 * conformance test can actually localise it.
 *
 * ONE THING CANNOT MATCH, BY CONSTRUCTION. The background noise is an Ornstein-Uhlenbeck
 * current driven by numpy's PCG64 and its ziggurat normal sampler. Reproducing that bit
 * for bit would mean porting both, and would buy nothing -- the noise is meant to be
 * noise. So conformance runs with noise disabled, where the two must agree to
 * floating-point tolerance; the noisy case is checked on gait *statistics* instead.
 * Anything else would be measuring the random number generator.
 *
 * Layout: one shared Model (read-only, the payload), one shared World (the fields the
 * animals eat from), one block of shared per-step scratch, and N independent Worms. The
 * 302x302 matrices are anatomy, identical for every animal, so only state is duplicated --
 * but state is not nothing. A second animal costs a measured 239,360 bytes, 234 kB, of
 * which 210,936 is the head-delay line alone. See the scratch block below and #33; the
 * figure is asserted by wasm/memory.mjs, which also checks that every document quoting it
 * quotes this number, because the previous one was out by a factor of a hundred and stayed
 * that way because nothing read it.
 */

import * as G from "./model_gen";

// ---------------------------------------------------------------------------- payload --

let B: usize = 0;

export function alloc(nbytes: i32): usize { return heap.alloc(<usize>nbytes); }
export function setPayload(ptr: usize): void { B = ptr; }

@inline function m(off: usize, i: i32): f64 { return load<f64>(B + off + (<usize>i << 3)); }
@inline function mi(off: usize, i: i32): i32 { return load<i32>(B + off + (<usize>i << 2)); }

/* Sparse matrix-vector product, compressed sparse row.
 *
 * Every connectome matrix here is between 0.3% and 2.5% non-zero, so the dense version
 * spent 556,000 mul-adds a step accumulating about 4,500 that were not zero. */
@inline function spmv(pOff: usize, iOff: usize, vOff: usize, rows: i32,
                      x: StaticArray<f64>, out: StaticArray<f64>): void {
  for (let r = 0; r < rows; r++) {
    let acc: f64 = 0.0;
    const e = mi(pOff, r + 1);
    for (let k = mi(pOff, r); k < e; k++) acc += m(vOff, k) * unchecked(x[mi(iOff, k)]);
    unchecked(out[r] = acc);
  }
}

@inline function sigmoid(x: f64): f64 {
  if (x >= 0) return 1.0 / (1.0 + Math.exp(-x));
  const e = Math.exp(x);
  return e / (1.0 + e);
}
@inline function clamp(v: f64, lo: f64, hi: f64): f64 {
  return v < lo ? lo : (v > hi ? hi : v);
}

// 1 inside edge0, falling smoothly to 0 by edge1. The lawn's edge.
@inline function smoothstep(e0: f64, e1: f64, x: f64): f64 {
  const t = clamp((x - e0) / (e1 - e0 + 1e-12), 0.0, 1.0);
  return 1.0 - t * t * (3.0 - 2.0 * t);
}

/* ------------------------------------------------------------------------- linear algebra
 * The body is the expensive part of a step: assembling a (n+2)^2 drag metric out of
 * several n x n products and then solving it. Everything here is dense and small
 * (n = 48), so straightforward loops beat anything cleverer.
 */

// Dense LU with partial pivoting, solving A x = b in place. A is (n x n) row-major.
// Returns false if the matrix is singular, which for this drag metric would mean the
// medium has no viscosity -- worth reporting rather than silently producing NaNs.
function solveInPlace(A: StaticArray<f64>, b: StaticArray<f64>, n: i32): bool {
  for (let k = 0; k < n; k++) {
    let piv = k;
    let best = Math.abs(unchecked(A[k * n + k]));
    for (let r = k + 1; r < n; r++) {
      const v = Math.abs(unchecked(A[r * n + k]));
      if (v > best) { best = v; piv = r; }
    }
    if (best < 1e-300) return false;
    if (piv != k) {
      for (let c = k; c < n; c++) {
        const t = unchecked(A[k * n + c]);
        unchecked(A[k * n + c] = unchecked(A[piv * n + c]));
        unchecked(A[piv * n + c] = t);
      }
      const t = unchecked(b[k]); unchecked(b[k] = unchecked(b[piv])); unchecked(b[piv] = t);
    }
    const d = unchecked(A[k * n + k]);
    for (let r = k + 1; r < n; r++) {
      const f = unchecked(A[r * n + k]) / d;
      if (f == 0.0) continue;
      unchecked(A[r * n + k] = 0.0);
      for (let c = k + 1; c < n; c++) {
        unchecked(A[r * n + c] -= f * unchecked(A[k * n + c]));
      }
      unchecked(b[r] -= f * unchecked(b[k]));
    }
  }
  for (let r = n - 1; r >= 0; r--) {
    let acc = unchecked(b[r]);
    for (let c = r + 1; c < n; c++) acc -= unchecked(A[r * n + c]) * unchecked(b[c]);
    unchecked(b[r] = acc / unchecked(A[r * n + r]));
  }
  return true;
}

// -------------------------------------------------------------------------------- rng --
// xoshiro256++ with a Box-Muller normal. Deliberately not numpy's: see the header.
class Rng {
  s0: u64 = 0; s1: u64 = 0; s2: u64 = 0; s3: u64 = 0;
  spare: f64 = 0.0; hasSpare: bool = false;
  constructor(seed: u64) {
    let z: u64 = seed;
    for (let i = 0; i < 4; i++) {
      z += 0x9E3779B97F4A7C15;
      let x = z;
      x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9;
      x = (x ^ (x >> 27)) * 0x94D049BB133111EB;
      x = x ^ (x >> 31);
      if (i == 0) this.s0 = x; else if (i == 1) this.s1 = x;
      else if (i == 2) this.s2 = x; else this.s3 = x;
    }
  }
  @inline next(): u64 {
    const r = rotl(this.s0 + this.s3, 23) + this.s0;
    const t = this.s1 << 17;
    this.s2 ^= this.s0; this.s3 ^= this.s1; this.s1 ^= this.s2; this.s0 ^= this.s3;
    this.s2 ^= t; this.s3 = rotl(this.s3, 45);
    return r;
  }
  @inline uniform(): f64 { return <f64>(this.next() >> 11) * (1.0 / 9007199254740992.0); }
  normal(): f64 {
    if (this.hasSpare) { this.hasSpare = false; return this.spare; }
    let u = this.uniform(); if (u < 1e-300) u = 1e-300;
    const v = this.uniform();
    const r = Math.sqrt(-2.0 * Math.log(u));
    this.spare = r * Math.sin(2.0 * Math.PI * v);
    this.hasSpare = true;
    return r * Math.cos(2.0 * Math.PI * v);
  }
}
@inline function rotl(x: u64, k: i32): u64 { return (x << k) | (x >> (64 - k)); }

// ------------------------------------------------------------------------------ world --
// Shared by every animal in the dish: they eat the same lawn and feel the same walls.

/* How many bacterial lawns one plate may hold.
 *
 * A cap exists because a lawn is no longer free: since depleting one has to dim the fields
 * it sources, each patch caches its two field shapes and costs 1,048,576 bytes, plus up to
 * 524,288 more for the lawn density over its own bounding box. See the note above
 * `patchAtt`. The viewer's drop-food button is the one caller that can be pressed
 * arbitrarily often, and 16 lawns is 16 MB -- about the same as 70 animals -- which is a
 * ceiling a tab can survive rather than a leak.
 *
 * 16 and not 8: wasm/population.mjs authors five, and a cap that a check in this repository
 * already sits three under is a cap that will be hit by accident. Nothing here allocates
 * for patches that do not exist, so the only cost of the headroom is the ceiling itself. */
const MAX_FOOD_PATCHES: i32 = 16;

class World {
  g: i32 = G.WORLD_GRID;
  extent: f64 = G.WORLD_EXTENT;
  h: f64 = 2.0 * G.WORLD_EXTENT / <f64>G.WORLD_GRID;
  // Allocated before anything reads `this`: AssemblyScript will not let a constructor
  // touch the instance until every field is initialised.
  food: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);
  attractant: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);
  repellent: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);
  o2: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);
  // Eggs, as flat x,y pairs. The first thing on this plate that persists: fields decay
  // and the worm forgets, but an egg stays where it was put. Capped so a long-running tab
  // cannot grow without bound -- the oldest go, which is the right end to lose.
  eggX: StaticArray<f64> = new StaticArray<f64>(G.MAX_EGGS);
  eggY: StaticArray<f64> = new StaticArray<f64>(G.MAX_EGGS);
  // Who laid it, when, and what it carries. See layEgg.
  eggParent: StaticArray<i32> = new StaticArray<i32>(G.MAX_EGGS);
  eggT: StaticArray<f64> = new StaticArray<f64>(G.MAX_EGGS);
  eggGene: StaticArray<f64> = new StaticArray<f64>(G.MAX_EGGS * G.N_GENES);
  nEggs: i32 = 0;
  eggsDropped: i32 = 0;
  scratch: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);
  facc: f64 = 0.0;

  /* What the standing bacteria emit, and the per-patch caches that produce it.
   *
   * The model is worm/world.py's, stated once there: the attractant and the oxygen
   * depression are both the steady state of `D grad^2 c = lambda c` away from a finite
   * source, that equation is linear in the source strength, so a lawn with fraction f of
   * its bacteria left sources f times the field with an unchanged spatial shape. Oxygen is
   * rebuilt outright; the attractant is relaxed towards `attSource` by `relax` below.
   *
   * WHY THE SHAPES ARE CACHED. The shape is fixed for the life of a patch and only its
   * scalar amplitude moves. Recomputing it would be 65,536 `Math.exp` calls per patch per
   * field step, 50 field steps a second, forever -- which is not a cost this runtime can
   * pay at 2 kHz inside a browser tab. Cached, a field step costs two multiply-accumulates
   * a cell a patch, and even those are skipped on the steps where nothing was eaten.
   *
   * WHAT IT COSTS. Two f64 grids a patch, 2 * 65,536 * 8 = 1,048,576 bytes, plus the
   * patch's own lawn density over its bounding box -- 6,496 bytes for the 5 mm lawn in the
   * conformance plate, at most 524,288 for one that covers the dish. So 1.0 MB a patch in
   * the ordinary case and 1.5 MB in the worst, against 239,360 bytes for a whole animal:
   * a lawn is four worms. MAX_FOOD_PATCHES is what stops the viewer's drop-food button
   * from turning that into an unbounded leak; past it, `addPatch` refuses and counts the
   * refusal, the same way a full plate refuses an egg. */
  patchAtt: Array<StaticArray<f64>> = [];
  patchO2: Array<StaticArray<f64>> = [];
  patchW: Array<StaticArray<f64>> = [];     // this patch's own lawn density over its box
  patchI0: Array<i32> = []; patchI1: Array<i32> = [];
  patchJ0: Array<i32> = []; patchJ1: Array<i32> = [];
  patchFood0: Array<f64> = [];              // weighted food in the box when it was built
  patchFrac: Array<f64> = [];               // f_p as of the last source rebuild
  patchesRefused: i32 = 0;
  attSource: StaticArray<f64> = new StaticArray<f64>(G.WORLD_GRID * G.WORLD_GRID);

  /* The chemical fields diffuse and decay. This was missing entirely -- the browser's
   * plate was frozen -- and it is the kind of omission a conformance test on an empty
   * dish cannot see, because a field of zeros diffuses to zeros. It showed up as an
   * exact-agreement run that diverged on step 41 and nowhere else: 41 steps is 0.0205 s,
   * and field_dt is 0.02. */
  /* An egg is a record, not a dot.
   *
   * It used to be two coordinates, which is all a picture needs and not enough for
   * anything downstream of it: no parent, no time, and above all no genome, so the one
   * thing on this plate that outlives the animal that made it carried nothing heritable.
   * That is the difference between reproduction and decoration, and between evolution and
   * selection imposed from outside.
   *
   * The genome is **copied**, not referenced. An egg has to outlive its parent -- that is
   * most of the point of laying it -- so a dead or recycled parent must not be able to
   * change or invalidate what its eggs carry. At 15 genes and 4096 eggs that is 480 kB,
   * which is affordable; a much larger genome would want a shared table and an index. */
  layEgg(x: f64, y: f64, parent: i32, t: f64, genes: StaticArray<f64>): void {
    /* Eggs used to live in a ring that silently dropped the oldest when it filled. That is
     * right for a picture and wrong for a record, and it does not survive eggs being
     * hatchable either: removing one from the middle of a ring leaves the write head
     * pointing at a live egg. So they are a plain bounded array now -- slots 0..nEggs,
     * which is what the viewer already read -- and a full plate refuses to take another
     * rather than quietly forgetting one it already has.
     *
     * The bound is not close: at the measured 11 eggs/hour/animal, four animals need
     * about 39 hours of wall clock to reach 4096. Refusals are counted anyway, because
     * the number that matters is whether any were lost, not how likely it was. */
    if (this.nEggs >= G.MAX_EGGS) { this.eggsDropped++; return; }
    const at = this.nEggs++;
    unchecked(this.eggX[at] = x);
    unchecked(this.eggY[at] = y);
    unchecked(this.eggParent[at] = parent);
    unchecked(this.eggT[at] = t);
    const base = at * G.N_GENES;
    for (let g = 0; g < G.N_GENES; g++) {
      unchecked(this.eggGene[base + g] = unchecked(genes[g]));
    }
  }

  /* Take an egg off the plate, leaving the array dense. Swap-with-last, the same shape as
   * removeWorm, so an index is only valid until the next removal -- read what you need
   * from an egg before taking it. */
  takeEgg(i: i32): bool {
    if (i < 0 || i >= this.nEggs) return false;
    const last = --this.nEggs;
    if (i != last) {
      unchecked(this.eggX[i] = unchecked(this.eggX[last]));
      unchecked(this.eggY[i] = unchecked(this.eggY[last]));
      unchecked(this.eggParent[i] = unchecked(this.eggParent[last]));
      unchecked(this.eggT[i] = unchecked(this.eggT[last]));
      const a = i * G.N_GENES, b = last * G.N_GENES;
      for (let g = 0; g < G.N_GENES; g++) {
        unchecked(this.eggGene[a + g] = unchecked(this.eggGene[b + g]));
      }
    }
    return true;
  }

  stepFields(dt: f64): void {
    this.facc += dt;
    while (this.facc >= G.WORLD_FIELD_DT) {
      this.facc -= G.WORLD_FIELD_DT;
      // What the standing bacteria emit *this* step, before anything reads it. Matches
      // World.step's ordering; rebuilding afterwards would leave the attractant one field
      // step behind the oxygen for no defensible reason.
      this.refreshSources();
      this.relax(this.attractant, G.WORLD_DIFFUSION_ATTRACTANT,
                 G.WORLD_DECAY_ATTRACTANT, G.WORLD_FIELD_DT, this.attSource);
      this.diffuse(this.repellent, G.WORLD_DIFFUSION_REPELLENT,
                   G.WORLD_DECAY_ATTRACTANT, G.WORLD_FIELD_DT);
    }
  }

  /* Food left in patch k's footprint, weighted by the density patch k put in each cell.
   *
   * Weighted rather than a hard `d < radius` disc, and that is not a stylistic choice.
   * Python computes the distance with `np.hypot` and this file with
   * `Math.sqrt(dx*dx+dy*dy)`; those can differ in the last bit, and a boolean footprint
   * straddling the lawn edge would then put a whole cell in one side's denominator and not
   * the other's -- a 1e-3 divergence grown out of a 1e-16 difference. Weighting by the lawn
   * profile makes the same last-bit disagreement worth about 1e-32, because the profile is
   * already ~0 at the rim it would disagree about. */
  patchFood(k: i32): f64 {
    const g = this.g;
    const i0 = this.patchI0[k], i1 = this.patchI1[k];
    const j0 = this.patchJ0[k], j1 = this.patchJ1[k];
    const w = this.patchW[k];
    let total = 0.0;
    let at = 0;
    for (let i = i0; i < i1; i++) {
      const row = i * g;
      for (let j = j0; j < j1; j++) {
        total += unchecked(this.food[row + j]) * unchecked(w[at]);
        at++;
      }
    }
    return total;
  }

  /* f_p: how much of patch k's own bacteria is left, clamped to [0, 1].
   *
   * Neither bound is reachable through `addPatch` and `eat` alone -- authoring a lawn grows
   * numerator and denominator by the same amount, and eating only ever lowers the
   * numerator. They are here for a caller that writes to `food` directly, which every assay
   * in tools/ is entitled to do: a lawn must not source twice what it was authored with
   * because somebody doubled the food field, and a negative source would pump the
   * attractant down through zero rather than fail. tests/test_world_depletion.py drives the
   * upper bound deliberately, because a clamp only tested where it cannot bite is not
   * tested at all. */
  patchFraction(k: i32): f64 {
    const denominator = this.patchFood0[k];
    if (denominator <= 0.0) return 0.0;      // authored outside the dish, or at zero density
    const fraction = this.patchFood(k) / denominator;
    return fraction < 0.0 ? 0.0 : (fraction > 1.0 ? 1.0 : fraction);
  }

  /* Rebuild sum_p f_p * shape_p for the attractant source and the oxygen deficit.
   * Accumulated in patch order, cell by cell, because World._rebuild_sources accumulates
   * the same two sums patch by patch in the same order and the two have to agree bit for
   * bit. */
  rebuildSources(): void {
    const n = this.patchAtt.length;
    const cells = this.g * this.g;
    for (let c = 0; c < cells; c++) {
      unchecked(this.attSource[c] = 0.0);
      unchecked(this.o2[c] = 0.0);
    }
    for (let k = 0; k < n; k++) {
      const f = this.patchFrac[k];
      const att = this.patchAtt[k], o2s = this.patchO2[k];
      for (let c = 0; c < cells; c++) {
        unchecked(this.attSource[c] += f * unchecked(att[c]));
        unchecked(this.o2[c] += f * unchecked(o2s[c]));
      }
    }
  }

  /* Recompute every f_p and rebuild the sourced fields only if one moved.
   *
   * f_p is a pure function of the food field, recomputed every field step over the patch's
   * bounding box -- 812 cells for the conformance plate's 5 mm lawn, against the grid's
   * 65,536. Deliberately not a dirty flag set by the feeding code: a flag is a second piece
   * of state the two implementations have to agree about, and a runtime that missed a
   * withdrawal the reference caught would diverge silently. Reading the field cannot.
   *
   * The `changed` guard is what makes this affordable, and the numbers are measured, on
   * 5,000 field steps of an empty plate (`stepAll` with no worms, so nothing but this code
   * runs):
   *
   *   16 lawns, guard in   8.24 s      16 lawns, rebuilding every step   27.62 s
   *    2 lawns, guard in   8.33 s       2 lawns, rebuilding every step   11.26 s
   *    0 lawns             8.23 s      -- the two 256^2 diffusion sweeps alone
   *
   * So a rebuild is 0.24 ms a lawn and the guard removes it from the ~96% of field steps on
   * which nothing was eaten; with it, sixteen lawns cost what none do. Recomputing the
   * shapes with `Math.exp` instead of caching them is 5.43 ms a lawn -- 23x the scaled
   * rebuild, and 271 ms per simulated second for a single lawn, which is where the caching
   * argument above stops being an opinion. End to end, one animal on the conformance plate
   * runs at 2739-2957 steps/s against 2703-2991 before this change: inside the noise. */
  refreshSources(): void {
    const n = this.patchAtt.length;
    if (n == 0) return;
    let changed = false;
    for (let k = 0; k < n; k++) {
      const fraction = this.patchFraction(k);
      if (fraction != this.patchFrac[k]) { this.patchFrac[k] = fraction; changed = true; }
    }
    if (changed) this.rebuildSources();
  }

  /* `diffuse` with a standing source: relax c towards `src` as well as spreading it.
   *
   * Deliberately without `diffuse`'s D <= 0 shortcut, which skips the clip and the dish
   * mask as well as the Laplacian -- defensible for a field with no source, not for one
   * being driven towards a masked profile. World._relax carries the same note.
   *
   * `decay * (src - c)` and not `- decay*c + decay*src`: with an intact lawn src IS c, so
   * the term is a bitwise zero and the step reduces to exactly the diffusion that was here
   * before any of this existed. The left-to-right form subtracts a quantity comparable to
   * `D*lap` and adds it straight back; on the conformance plate it happens to agree to 0.0
   * as well, but by luck of the operand magnitudes rather than by construction. The full
   * argument is in worm/world.py's module docstring. */
  relax(c: StaticArray<f64>, D: f64, decay: f64, dt: f64, src: StaticArray<f64>): void {
    const g = this.g;
    const inv = 1.0 / (this.h * this.h);
    for (let i = 0; i < g; i++) {
      const up = ((i - 1 + g) % g) * g, dn = ((i + 1) % g) * g, row = i * g;
      for (let j = 0; j < g; j++) {
        const lf = (j - 1 + g) % g, rt = (j + 1) % g;
        const v = unchecked(c[row + j]);
        const lap = (unchecked(c[up + j]) + unchecked(c[dn + j])
                   + unchecked(c[row + lf]) + unchecked(c[row + rt]) - 4.0 * v) * inv;
        let out = v + dt * (D * lap + decay * (unchecked(src[row + j]) - v));
        if (out < 0.0) out = 0.0;
        unchecked(this.scratch[row + j] = out);
      }
    }
    for (let i = 0; i < g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const k = i * g + j;
        unchecked(c[k] = Math.sqrt(x * x + y * y) <= this.extent ? unchecked(this.scratch[k]) : 0.0);
      }
    }
  }

  diffuse(c: StaticArray<f64>, D: f64, decay: f64, dt: f64): void {
    const g = this.g;
    if (D <= 0.0) {
      const k = 1.0 - decay * dt;
      for (let i = 0; i < g * g; i++) unchecked(c[i] *= k);
      return;
    }
    // Five-point Laplacian with wrap-around, matching numpy's np.roll exactly -- the
    // dish mask below is what keeps the wrap from meaning anything physical.
    const inv = 1.0 / (this.h * this.h);
    for (let i = 0; i < g; i++) {
      const up = ((i - 1 + g) % g) * g, dn = ((i + 1) % g) * g, row = i * g;
      for (let j = 0; j < g; j++) {
        const lf = (j - 1 + g) % g, rt = (j + 1) % g;
        const v = unchecked(c[row + j]);
        const lap = (unchecked(c[up + j]) + unchecked(c[dn + j])
                   + unchecked(c[row + lf]) + unchecked(c[row + rt]) - 4.0 * v) * inv;
        let out = v + dt * (D * lap - decay * v);
        if (out < 0.0) out = 0.0;
        unchecked(this.scratch[row + j] = out);
      }
    }
    for (let i = 0; i < g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const k = i * g + j;
        unchecked(c[k] = Math.sqrt(x * x + y * y) <= this.extent ? unchecked(this.scratch[k]) : 0.0);
      }
    }
  }
  sample(f: StaticArray<f64>, x: f64, y: f64): f64 {
    const fx = (x + this.extent) / this.h - 0.5;
    const fy = (y + this.extent) / this.h - 0.5;
    let x0 = <i32>Math.floor(fx); let y0 = <i32>Math.floor(fy);
    x0 = x0 < 0 ? 0 : (x0 > this.g - 2 ? this.g - 2 : x0);
    y0 = y0 < 0 ? 0 : (y0 > this.g - 2 ? this.g - 2 : y0);
    const tx = clamp(fx - <f64>x0, 0.0, 1.0);
    const ty = clamp(fy - <f64>y0, 0.0, 1.0);
    const i00 = y0 * this.g + x0;
    const f00 = unchecked(f[i00]), f10 = unchecked(f[i00 + 1]);
    const f01 = unchecked(f[i00 + this.g]), f11 = unchecked(f[i00 + this.g + 1]);
    return (f00 * (1.0 - tx) + f10 * tx) * (1.0 - ty)
         + (f01 * (1.0 - tx) + f11 * tx) * ty;
  }
  temperature(x: f64): f64 {
    const f = clamp((x + this.extent) / (2.0 * this.extent), 0.0, 1.0);
    return G.WORLD_TEMP_COLD + (G.WORLD_TEMP_WARM - G.WORLD_TEMP_COLD) * f;
  }
  oxygen(x: f64, y: f64): f64 {
    const d = clamp(this.sample(this.o2, x, y), 0.0, G.WORLD_O2_AMBIENT - 0.01);
    return G.WORLD_O2_AMBIENT - d;
  }
  eat(x: f64, y: f64, amount: f64): f64 {
    // Proportional withdrawal from the 3x3 neighbourhood, matching World.eat: taking the
    // full amount from every cell would remove up to nine times what was asked for.
    let j = <i32>Math.floor((x + this.extent) / this.h);
    let i = <i32>Math.floor((y + this.extent) / this.h);
    i = i < 0 ? 0 : (i > this.g - 1 ? this.g - 1 : i);
    j = j < 0 ? 0 : (j > this.g - 1 ? this.g - 1 : j);
    const lo_i = i > 0 ? i - 1 : 0, hi_i = i < this.g - 1 ? i + 1 : this.g - 1;
    const lo_j = j > 0 ? j - 1 : 0, hi_j = j < this.g - 1 ? j + 1 : this.g - 1;
    let avail: f64 = 0.0;
    for (let a = lo_i; a <= hi_i; a++)
      for (let b2 = lo_j; b2 <= hi_j; b2++) avail += unchecked(this.food[a * this.g + b2]);
    if (avail <= 0.0) return 0.0;
    const take = amount < avail ? amount : avail;
    const k = 1.0 - take / avail;
    for (let a = lo_i; a <= hi_i; a++)
      for (let b2 = lo_j; b2 <= hi_j; b2++) unchecked(this.food[a * this.g + b2] *= k);
    return take;
  }
  /* A bacterial lawn, matching World.add_food_patch exactly.
   *
   * The three fields have *different* shapes, and getting that wrong is not cosmetic.
   * Bacteria stop at the lawn edge -- a smoothstep from three quarters of the radius to
   * the radius, and zero beyond. Only the diffusible attractant gets an exponential
   * skirt, because that is the steady state of a chemical leaking out of a finite source.
   * Giving food the skirt too, which this did, meant an animal seven millimetres outside
   * a five millimetre lawn read food 0.78 where the Python read 0.0: it thought it was on
   * a lawn almost everywhere in the dish, ate, pumped, and stayed. The conformance test
   * could not see it, because it ran on an empty plate where every field is zero. */
  addPatch(cx: f64, cy: f64, r: f64, density: f64, att: f64, ls: f64): void {
    // A refusal, not a silent forget: see MAX_FOOD_PATCHES and `foodPatchesRefused`.
    if (this.patchAtt.length >= MAX_FOOD_PATCHES) { this.patchesRefused++; return; }
    const g = this.g;
    const existing = this.patchAtt.length;
    // What every existing patch's weighted footprint holds *before* this lawn lands. Their
    // denominators grow by exactly what it adds, so that on a plate where nothing has been
    // eaten yet numerator and denominator stay bit-identical and f_p is exactly 1.0 -- and
    // so that dropping a lawn from the viewer cannot re-bless a half-eaten plate as full.
    const before = new StaticArray<f64>(existing > 0 ? existing : 1);
    for (let k = 0; k < existing; k++) unchecked(before[k] = this.patchFood(k));

    const attShape = new StaticArray<f64>(g * g);
    const o2Shape = new StaticArray<f64>(g * g);
    let i0 = g, i1 = 0, j0 = g, j1 = 0;
    for (let i = 0; i < g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const dx = x - cx, dy = y - cy;
        const d = Math.sqrt(dx * dx + dy * dy);
        const k = i * g + j;
        const skirt = Math.exp(-(d > r ? d - r : 0.0) / ls);
        const lawn = density * smoothstep(r * 0.75, r, d);
        // Masked here rather than by maskDish, because these are cached and maskDish only
        // ever sees the live fields. Python masks each shape the same way and for the same
        // reason; masking a sum and summing masked terms agree exactly, since the mask is
        // only ever an exact 1 or an exact 0.
        const keep = Math.sqrt(x * x + y * y) <= this.extent;
        unchecked(this.food[k] += lawn);
        unchecked(attShape[k] = keep ? att * skirt : 0.0);
        unchecked(o2Shape[k] = keep ? G.WORLD_O2_DEPTH * density
                  * Math.exp(-(d > r ? d - r : 0.0) / G.WORLD_O2_LENGTH_SCALE) : 0.0);
        unchecked(this.attractant[k] += unchecked(attShape[k]));
        // The bounding box of this patch's own lawn, taken from the UNMASKED profile so it
        // matches Python's `lawn > 0.0`. Cells outside the dish carry zero food and so
        // contribute nothing to the weighted sum anyway.
        if (lawn > 0.0) {
          if (i < i0) i0 = i;
          if (i + 1 > i1) i1 = i + 1;
          if (j < j0) j0 = j;
          if (j + 1 > j1) j1 = j + 1;
        }
      }
    }
    if (i1 <= i0 || j1 <= j0) { i0 = 0; i1 = 0; j0 = 0; j1 = 0; }
    this.maskDish();

    const weights = new StaticArray<f64>((i1 - i0) * (j1 - j0));
    let at = 0;
    for (let i = i0; i < i1; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = j0; j < j1; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const dx = x - cx, dy = y - cy;
        unchecked(weights[at] = density * smoothstep(r * 0.75, r, Math.sqrt(dx * dx + dy * dy)));
        at++;
      }
    }

    this.patchAtt.push(attShape);
    this.patchO2.push(o2Shape);
    this.patchW.push(weights);
    this.patchI0.push(i0); this.patchI1.push(i1);
    this.patchJ0.push(j0); this.patchJ1.push(j1);
    this.patchFood0.push(0.0);
    this.patchFrac.push(1.0);

    for (let k = 0; k < existing; k++) {
      this.patchFood0[k] += this.patchFood(k) - unchecked(before[k]);
    }
    this.patchFood0[existing] = this.patchFood(existing);
    for (let k = 0; k <= existing; k++) this.patchFrac[k] = this.patchFraction(k);
    this.rebuildSources();
  }

  /* Nothing exists outside the plate. Python applies this after every source. */
  maskDish(): void {
    for (let i = 0; i < this.g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < this.g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        if (Math.sqrt(x * x + y * y) <= this.extent) continue;
        const k = i * this.g + j;
        unchecked(this.food[k] = 0.0);
        unchecked(this.attractant[k] = 0.0);
        unchecked(this.repellent[k] = 0.0);
        unchecked(this.o2[k] = 0.0);
      }
    }
  }
  addRepellent(cx: f64, cy: f64, strength: f64, ls: f64): void {
    for (let i = 0; i < this.g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < this.g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const dx = x - cx, dy = y - cy;
        const k = i * this.g + j;
        unchecked(this.repellent[k] += strength * Math.exp(-Math.sqrt(dx * dx + dy * dy) / ls));
      }
    }
    this.maskDish();
  }
}

let world: World = new World();

/* ------------------------------------------------------------------------ scratch ------
 * Working space for one animal's step, shared by all of them.
 *
 * These 37 arrays used to be fields of `class Worm`, which made a worm cost 379,262 bytes
 * of declared arrays -- 381,840 measured, allocator overhead included -- of which 140,776
 * was per-step scratch: written from index 0 to the end and read back inside the same
 * call, holding nothing between steps. Duplicating it per animal bought nothing, and it
 * was 37% of the population budget. See #33.
 *
 * WHAT MAKES THIS SAFE. Worms are stepped strictly sequentially and single-threaded --
 * `stepAll` runs `prepareStep` to completion for animal k before touching animal k+1, and
 * there is no threading anywhere in this runtime. So one copy is enough, and the change is
 * bit-identical: the same arithmetic reads the same values out of a different address.
 *
 * WHAT WOULD MAKE IT UNSAFE, and what to check before adding an array here. Every array
 * below is *fully written before it is read within a single call*. An array that is read
 * before it is written in a step is not scratch however much it looks like it: it is
 * carrying state from the previous step, and sharing it would silently hand animal k the
 * value animal k-1 left behind. Two of the arrays #33 lists as scratch are exactly that
 * and have been kept per-worm -- see `contactX`/`contactY` in `class Worm`.
 *
 * The grouping below records, per group, *why* each is safe, because "it is scratch" is
 * the claim that has to be re-checked whenever the order of a step changes. If Web Workers
 * ever arrive (each worker owning a sub-population, as #33 suggests), each worker instance
 * gets its own module state and this stays correct; interleaving two worms *within* one
 * instance would not, and would break loudly rather than subtly only for the arrays that
 * are read early -- which is why the read-before-write ones are not here.
 *
 * Not hoisted, and why: `act` (read by the viewer via `ptrAct`, and read again in
 * `finishStep` after every animal's `prepareStep` has run), `nodesX`/`nodesY` (read via
 * `ptrNodesX`/`ptrNodesY`, and by `settleFeeding` between the two halves of a batch step),
 * and `moment` (an *input* on the `setMoment`/`stepBodyOnly` path). Every other array
 * reachable through an exported pointer -- `V`, `mTen`, `kappa`, `theta` -- is state, not
 * scratch, and was never a candidate.
 */

// -- mechanics. `dragMatrix` fills sUx..sNyv over all N_LINKS, then sPm/sQm/sAs/sBs over
//    the whole n x n grid, and zeroes sDm before assembling into it; `stepBody` zeroes sQv
//    before accumulating into it and hands sDm/sQv straight to the solver. Nothing here
//    survives the call that wrote it.
let sUx: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
let sUy: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
let sNxv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
let sNyv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
let sDm: StaticArray<f64> = new StaticArray<f64>((G.N_LINKS + 2) * (G.N_LINKS + 2));
let sQv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 2);
let sPm: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
let sQm: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
let sAs: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
let sBs: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);

// -- nervous system. `sense` zeroes sIext at its first line and every other array here is
//    written across all N_NEURONS by a loop or an spmv earlier in `stepNervous` than any
//    read of it. sVold is the previous *voltage*, but it is copied out of `V` -- which is
//    per-worm state -- at the top of the same call that reads it, so the buffer itself
//    holds nothing between steps.
let sIext: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sGs: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sEs: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sGtot: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sFx: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sDec: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sVn: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sVold: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sGapv: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sGapAcc: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sRel: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sWbv: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sWav: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sWbf: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sWaf: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
let sWhv: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);

// -- muscle. `stepMuscle` writes sMg/sMe over every row, then sMgt/sMfx/sMdec/sMVn over
//    every cell, before the gap iteration reads any of them; `jointMoment` fills sRowD and
//    sRowV over all MUS_N_ROWS before interpolating from them.
let sMVn: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMg: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMe: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMgt: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMfx: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMdec: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sMgap: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
let sRowD: StaticArray<f64> = new StaticArray<f64>(G.MUS_N_ROWS);
let sRowV: StaticArray<f64> = new StaticArray<f64>(G.MUS_N_ROWS);

// -- proprioception. sKn is the normalised curvature, recomputed from the per-worm `kappa`
//    every call; sKh is read out of the per-worm `headHist` ring immediately after. The
//    delay line is the state and stays per-worm -- it is also 55% of what a worm costs.
let sKn: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);
let sKh: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);

// ------------------------------------------------------------------------------- worm --

class Worm {
  // Stable identity, assigned by createWorm and never reused. Not the array slot: see
  // the note above `worms` at the bottom of this file.
  id: i32 = -1;
  rng: Rng = new Rng(0);
  bx: f64 = 0.0; by: f64 = 0.0;
  theta: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  // Read after the step through ptrNodesX/ptrNodesY, and read by settleFeeding between the
  // two halves of a batch step. Not scratch.
  nodesX: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  nodesY: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  /* NOT SCRATCH, despite looking exactly like it, and despite #33 listing it as scratch.
   *
   * `contact()` writes these and `stepBody` reads them, which is the write-then-read shape
   * everything in the scratch block above has. But `sense()` reads them too -- the
   * mechanosensory sum at the top of the touch pathway -- and `sense()` runs *before*
   * `contact()` in `prepareStep`. So what mechanosensation reads is the wall force computed
   * at the end of the animal's *previous* step. These arrays carry state across steps.
   *
   * That one-step delay is the model, not an accident of this port: worm/engine.py:149
   * passes `self._contact` to `senses.sense` and only recomputes it at :155, and
   * `self._contact` is a per-Simulation attribute. Hoisting them would hand animal k the
   * wall forces animal k-1 felt this step, and animal 0 those of the last animal in the
   * previous step -- a cross-animal coupling through the touch pathway, in a runtime whose
   * whole claim is that animals interact only through the plate.
   *
   * It would also have passed every check in this repository as of writing. conform.mjs
   * runs one animal, where sharing is identity. population.mjs runs its animals within
   * 16 mm of the centre of a 45 mm dish, so `contact` is identically zero in every one of
   * its cases and the leak has nothing to leak. Case 12 was added with this change to give
   * the decision something that fails; it was watched failing with these hoisted.
   *
   * 784 bytes per animal, which is what a correct 37% is worth against a broken 38%. */
  contactX: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  contactY: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  kappa: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);
  // An *input* on the conformance path: setMoment writes it, stepBodyOnly reads it, and
  // nothing in between recomputes it. Per-worm even though jointMoment fills it whole.
  moment: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);
  // nervous
  V: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  sv: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  av: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  Dv: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  Inoise: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  /* Read after the step through ptrAct, which is reason enough. It is also read in
   * `finishStep` -- by `stepEggLaying`, for the HSN and VC pools -- and in a batch step
   * every animal's `prepareStep` has run by then, so a shared buffer would hand every
   * animal the last one's activations at the moment eggs are decided. Two independent
   * reasons; the second is the one that would have bitten. */
  act: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  /* Ablation. Zeroing a cell's conductances is not enough on its own: a cell whose
   * synaptic and gap conductances are gone still receives whatever the sensory layer
   * injects, with only its leak to shunt it -- which is how ablating AVB once drove it
   * from -11.6 mV to +34.8 mV and made the forward command *maximally* active. A dead
   * cell is cut off from external input, pinned at its leak potential, and releases
   * nothing. */
  alive: StaticArray<u8> = new StaticArray<u8>(G.N_NEURONS);
  gapTot: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  anyDead: bool = false;
  // muscle
  mV: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
  mCa: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
  mTen: StaticArray<f64> = new StaticArray<f64>(G.N_MUSCLES);
  // senses
  headSignal: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  propAdapt: StaticArray<f64> = new StaticArray<f64>(G.N_NEURONS);
  headHist: StaticArray<f64> = new StaticArray<f64>((G.HEAD_DELAY_N + 1) * G.N_JOINTS);
  headHistI: i32 = 0;
  cAdapt: f64 = 0.0; odourAdapt: f64 = 0.0; tAdapt: f64 = 0.0; o2Adapt: f64 = 0.0;
  repAdapt: f64 = 0.0;
  adaptReady: bool = false;
  touchA: f64 = 0.0; touchP: f64 = 0.0;
  availA: f64 = 1.0; availP: f64 = 1.0;
  pokeA: f64 = 0.0; pokeP: f64 = 0.0;
  goingForward: bool = true;
  omega: f64 = 0.0; omegaSign: f64 = 1.0; revSteps: i32 = 0;
  // modulators, in the order used by model_gen: dopamine, serotonin, octopamine, pdf
  modDA: f64 = 0.0; modSER: f64 = 0.0; modOA: f64 = 0.0; modPDF: f64 = 0.0;
  // pharynx
  phPhase: f64 = 0.0; phOpen: f64 = 0.0; phPumping: bool = false;
  phRate: f64 = 0.0; phDur: f64 = 0.0; phPumps: i32 = 0;
  lumen: f64 = 0.0; ingested: f64 = 0.0; eaten: f64 = 0.0;
  // What the last pump actually got off the plate, which is what the world lost.
  phCaptured: f64 = 0.0;
  phWant: f64 = 0.0;      // this step's capture demand, before the plate has answered
  phFood: f64 = 0.0;      // food density at the mouth when the demand was formed
  // Egg-laying. See worm/egglaying.py for the circuit; the shapes here follow it exactly.
  eglVm: f64 = 0.0;
  eglEggs: f64 = G.EGL_EGGS_INITIAL;
  eglResource: f64 = 1.0;
  eglInPhase: bool = true;
  eglRefractory: f64 = 0.0;
  eglLaid: i32 = 0;
  eglVcRest: f64 = 0.0;
  eglRestN: i32 = 0;
  sensedFood: f64 = 0.0; sensedAtt: f64 = 0.0; sensedRep: f64 = 0.0;
  sensedO2: f64 = 0.0; sensedT: f64 = 0.0;

  cT: f64 = G.MED_AGAR_CT; cN: f64 = G.MED_AGAR_CN;
  t: f64 = 0.0;

  /* The genome: the handful of scalars this animal may differ from its parents in.
   *
   * Everything else the runtime reads is shared -- the connectome matrices are anatomy,
   * identical for every worm, which is what makes a second animal cheap. These fourteen
   * are per-animal, so a dish can hold genuinely different worms rather than N clones.
   *
   * Seeded from the exported defaults, so a population nobody has mutated is bit-identical
   * to the model before this existed. That is deliberate: it is what lets the conformance
   * check go on meaning something while a genome is added underneath it.
   *
   * The slot numbering is generated by tools/export_model.py, which is also where the list
   * of genes and the reasoning about what may be on it live. */
  genes: StaticArray<f64> = new StaticArray<f64>(G.N_GENES);

  @inline gene(slot: i32): f64 { return unchecked(this.genes[slot]); }

  resetGenes(): void {
    unchecked(this.genes[G.GENE_SEN_PROPRIO_GAIN] = G.SEN_PROPRIO_GAIN);
    unchecked(this.genes[G.GENE_SEN_HEAD_PROPRIO_GAIN] = G.SEN_HEAD_PROPRIO_GAIN);
    unchecked(this.genes[G.GENE_SEN_CORD_DRIVE] = G.SEN_CORD_DRIVE);
    unchecked(this.genes[G.GENE_SEN_GATE_BIAS] = G.SEN_GATE_BIAS);
    unchecked(this.genes[G.GENE_SEN_GATE_HYSTERESIS] = G.SEN_GATE_HYSTERESIS);
    unchecked(this.genes[G.GENE_SEN_TONIC_FORWARD] = G.SEN_TONIC_FORWARD);
    unchecked(this.genes[G.GENE_SEN_OMEGA_CURRENT] = G.SEN_OMEGA_CURRENT);
    unchecked(this.genes[G.GENE_SEN_OMEGA_VENTRAL_FRACTION] = G.SEN_OMEGA_VENTRAL_FRACTION);
    unchecked(this.genes[G.GENE_MOD_SEROTONIN_MOD1] = G.MOD_SEROTONIN_MOD1);
    unchecked(this.genes[G.GENE_SEN_CHEMO_GAIN] = G.SEN_CHEMO_GAIN);
    unchecked(this.genes[G.GENE_SEN_THERMO_GAIN] = G.SEN_THERMO_GAIN);
    unchecked(this.genes[G.GENE_SEN_OXYGEN_GAIN] = G.SEN_OXYGEN_GAIN);
    unchecked(this.genes[G.GENE_SEN_REPELLENT_D_GAIN] = G.SEN_REPELLENT_D_GAIN);
    unchecked(this.genes[G.GENE_SEN_FOOD_GAIN] = G.SEN_FOOD_GAIN);
    unchecked(this.genes[G.GENE_SEN_TOUCH_GAIN] = G.SEN_TOUCH_GAIN);
  }

  constructor(seed: u64, x: f64, y: f64, heading: f64) {
    this.resetGenes();
    this.rng = new Rng(seed);
    this.bx = x; this.by = y;
    for (let i = 0; i < G.N_LINKS; i++) unchecked(this.theta[i] = heading);
    for (let i = 0; i < G.N_NEURONS; i++) {
      unchecked(this.V[i] = m(G.OFF_V_init, i));
      unchecked(this.sv[i] = m(G.OFF_s_init, i));
      unchecked(this.av[i] = m(G.OFF_a_init, i));
      unchecked(this.Dv[i] = m(G.OFF_d_rest, i));
    }
    for (let i = 0; i < G.N_MUSCLES; i++) unchecked(this.mV[i] = G.MUS_E_LEAK);
    for (let i = 0; i < G.N_NEURONS; i++) unchecked(this.alive[i] = 1);
    this.rebuildGap();
    this.updateNodes();
  }

  /* ------------------------------------------------------------------ nervous system --
   * Exponential Euler on the diagonal, with the gap-junction coupling refined by a few
   * fixed-point passes -- which converge because the conductance matrix is diagonally
   * dominant. That buys implicit-solver accuracy for two extra matrix-vector products
   * instead of an N^3 solve per step. */
  stepNervous(): void {
    const n = G.N_NEURONS, dt = G.DT;
    const gLeak = m(G.OFF_g_leak, 0), eLeak = m(G.OFF_E_leak, 0);

    const nd = Math.exp(-dt / G.NEURAL_NOISE_TAU);
    const kick = G.NEURAL_NOISE_SIGMA * Math.sqrt(1.0 - nd * nd);
    for (let i = 0; i < n; i++) {
      // Not gated by `alive`, where the Python multiplies the whole input current by it.
      // Checked, and the difference is inert: a dead cell's voltage is overwritten with
      // its leak potential after the solve, it is skipped in the gap accumulation, its
      // gapTot is zero and its activation is forced to zero -- so the noise written here
      // for an absent cell has no way out. It is also drawn either way, on both sides, so
      // the two generators stay in step with each other's consumption.
      //
      // Worth stating because conformance cannot see it: with the noise off this line is
      // identical whatever `alive` says, so a real ordering difference here would pass
      // every check in the repository. It was looked for deliberately.
      let noise = unchecked(this.Inoise[i]) * nd;
      if (noiseOn) noise += kick * this.rng.normal();
      unchecked(this.Inoise[i] = noise);
      unchecked(sVold[i] = unchecked(this.V[i]));
    }

    // G_syn and GE_syn are the same matrix scaled per element, so one pass over the
    // shared pattern produces both.
    for (let c = 0; c < n; c++) {
      let rel = unchecked(this.sv[c]);
      if (G.ANY_DEPRESS) rel *= unchecked(this.Dv[c]);
      if (this.anyDead && !unchecked(this.alive[c])) rel = 0.0;   // releases nothing
      unchecked(sRel[c] = rel);
    }
    for (let r = 0; r < n; r++) {
      let a1: f64 = 0.0, a2: f64 = 0.0;
      const e = mi(G.OFF_syn_ptr, r + 1);
      for (let k = mi(G.OFF_syn_ptr, r); k < e; k++) {
        const rv = unchecked(sRel[mi(G.OFF_syn_idx, k)]);
        a1 += m(G.OFF_syn_val, k) * rv;
        a2 += m(G.OFF_syn_val2, k) * rv;
      }
      unchecked(sGs[r] = a1); unchecked(sEs[r] = a2);
    }

    /* MOD-1: the serotonin-gated chloride channel, as a conductance rather than a current
     * so it shunts and saturates like the real channel instead of driving the cell without
     * limit. Peak is a fraction of each target's own resting conductance, which is what
     * `mod1_unit` carries; the fraction itself is this animal's own gene.
     *
     * Only the depolarising half of the serotonin level opens it -- less food than
     * baseline should not prise a channel open backwards.
     *
     * This existed in Python from the day the modulator layer was built and was never
     * ported. It survived every conformance run because the shipped coefficient is zero,
     * and zero is indistinguishable from absent. */
    const mod1 = this.gene(G.GENE_MOD_SEROTONIN_MOD1)
                 * (this.modSER > 0.0 ? this.modSER : 0.0);
    for (let i = 0; i < n; i++) {
      const V = unchecked(sVold[i]);
      const gAd = m(G.OFF_g_adapt, i) * unchecked(this.av[i]);
      const gC = m(G.OFF_g_ca, i) * 0.5 *
                 (1.0 + Math.tanh((V - m(G.OFF_ca_vhalf, i)) / G.NEURAL_CA_SLOPE));
      let gt = gLeak + unchecked(this.gapTot[i]) + unchecked(sGs[i]) + gAd + gC;
      let fx = gLeak * eLeak + unchecked(sEs[i])
               + gAd * G.NEURAL_E_K + gC * G.NEURAL_E_CA
               + unchecked(this.Inoise[i])
               + (this.anyDead && !unchecked(this.alive[i]) ? 0.0 : unchecked(sIext[i]));
      if (mod1 != 0.0) {
        const gm = m(G.OFF_mod1_unit, i) * mod1;
        gt += gm;
        fx += gm * G.NEURAL_E_INH;
      }
      unchecked(sGtot[i] = gt);
      unchecked(sFx[i] = fx);
      unchecked(sDec[i] = Math.exp(-gt * dt / (G.NEURAL_C_M * 1e-3)));
      unchecked(sVn[i] = V);
    }
    for (let it = 0; it < G.GAP_ITERS; it++) {
      if (this.anyDead) {
        for (let r = 0; r < n; r++) {
          let acc: f64 = 0.0;
          const e = mi(G.OFF_gap_ptr, r + 1);
          for (let k = mi(G.OFF_gap_ptr, r); k < e; k++) {
            const c = mi(G.OFF_gap_idx, k);
            if (unchecked(this.alive[c])) acc += m(G.OFF_gap_val, k) * unchecked(sVn[c]);
          }
          unchecked(sGapAcc[r] = acc);
        }
      } else {
        spmv(G.OFF_gap_ptr, G.OFF_gap_idx, G.OFF_gap_val, n, sVn, sGapAcc);
      }
      for (let r = 0; r < n; r++) {
        const vInf = (unchecked(sFx[r]) + unchecked(sGapAcc[r])) / unchecked(sGtot[r]);
        unchecked(sGapv[r] = vInf + (unchecked(sVold[r]) - vInf) * unchecked(sDec[r]));
      }
      for (let r = 0; r < n; r++) unchecked(sVn[r] = unchecked(sGapv[r]));
    }

    for (let i = 0; i < n; i++) {
      if (this.anyDead && !unchecked(this.alive[i])) {
        unchecked(this.V[i] = m(G.OFF_E_leak, 0));
        unchecked(this.sv[i] = 0.0);
        continue;
      }
      unchecked(this.V[i] = clamp(unchecked(sVn[i]), G.V_CLAMP_LO, G.V_CLAMP_HI));
      // Release is driven by the *pre-update* voltage, so the network has one consistent
      // step of delay everywhere rather than an index-order dependence.
      const V = unchecked(sVold[i]);
      const phi = sigmoid(G.NEURAL_BETA * (V - m(G.OFF_V_th, i)));
      const nInf = 0.5 * (1.0 + Math.tanh((V - m(G.OFF_k_vhalf, i)) / G.NEURAL_K_SLOPE));
      unchecked(this.av[i] = nInf + (unchecked(this.av[i]) - nInf) * m(G.OFF_adapt_decay, i));
      const rise = G.NEURAL_A_RISE * phi;
      const rate = rise + G.NEURAL_A_DECAY;
      const sInf = rise / rate;
      unchecked(this.sv[i] = sInf + (unchecked(this.sv[i]) - sInf) * Math.exp(-rate * dt));
      if (G.ANY_DEPRESS) {
        const rec = 1.0 / G.NEURAL_DEPRESSION_TAU;
        const dr = rec + m(G.OFF_depress_use, i) * phi;
        const dInf = rec / dr;
        unchecked(this.Dv[i] = dInf + (unchecked(this.Dv[i]) - dInf) * Math.exp(-dr * dt));
      }
    }
  }

  activation(): void {
    for (let i = 0; i < G.N_NEURONS; i++) {
      // Zero for an ablated cell. This matters beyond tidiness: the direction gate reads
      // the mean activation of the command pools, so a dead neuron reporting anything but
      // zero votes in a decision it is not present for.
      unchecked(this.act[i] = (this.anyDead && !unchecked(this.alive[i])) ? 0.0
        : sigmoid(G.NEURAL_BETA * (unchecked(this.V[i]) - m(G.OFF_V_th, i))));
    }
  }

  /* ---------------------------------------------------------------------- muscle ----- */
  stepMuscle(): void {
    const mm = G.N_MUSCLES, n = G.N_NEURONS, dt = G.DT;
    for (let c = 0; c < n; c++) {
      let sp = unchecked(this.sv[c]);
      if (G.ANY_PHASIC) {
        sp = clamp(G.MUS_S_EQ + m(G.OFF_mus_phasic_gain, c) * (sp - G.MUS_S_EQ), 0.0, 1.0);
      }
      unchecked(sRel[c] = sp);
    }
    for (let r = 0; r < mm; r++) {
      let a1: f64 = 0.0, a2: f64 = 0.0;
      const e = mi(G.OFF_mus_ptr, r + 1);
      for (let k = mi(G.OFF_mus_ptr, r); k < e; k++) {
        const c = mi(G.OFF_mus_idx, k);
        const gv = m(G.OFF_mus_val, k) * unchecked(sRel[c]);
        a1 += gv;
        a2 += gv * m(G.OFF_mus_E_pre, c);
      }
      unchecked(sMg[r] = a1); unchecked(sMe[r] = a2);
    }
    for (let i = 0; i < mm; i++) {
      const gt = G.MUS_G_LEAK + unchecked(sMg[i]) + m(G.OFF_mus_gap_total, i);
      unchecked(sMgt[i] = gt);
      unchecked(sMfx[i] = G.MUS_G_LEAK * G.MUS_E_LEAK + unchecked(sMe[i]));
      unchecked(sMdec[i] = Math.exp(-gt * dt / G.MUS_C_NF));
      unchecked(sMVn[i] = unchecked(this.mV[i]));
    }
    for (let it = 0; it < 2; it++) {
      for (let r = 0; r < mm; r++) {
        let acc: f64 = 0.0;
        const row = B + G.OFF_mus_G_gap + (<usize>(r * mm) << 3);
        for (let c = 0; c < mm; c++) acc += load<f64>(row + (<usize>c << 3)) * unchecked(sMVn[c]);
        const vInf = (unchecked(sMfx[r]) + acc) / unchecked(sMgt[r]);
        unchecked(sMgap[r] = vInf + (unchecked(this.mV[r]) - vInf) * unchecked(sMdec[r]));
      }
      for (let r = 0; r < mm; r++) unchecked(sMVn[r] = unchecked(sMgap[r]));
    }
    for (let i = 0; i < mm; i++) {
      unchecked(this.mV[i] = unchecked(sMVn[i]));
      const target = sigmoid(G.MUS_BETA * (unchecked(this.mV[i]) - G.MUS_V_HALF));
      unchecked(this.mCa[i] = target + (unchecked(this.mCa[i]) - target) * G.MUS_DECAY_CA);
      unchecked(this.mTen[i] = unchecked(this.mCa[i])
                + (unchecked(this.mTen[i]) - unchecked(this.mCa[i])) * G.MUS_DECAY_TE);
    }
  }

  /* Active bending moment per joint. Muscle can only pull, so the moment is the
   * *difference* of two one-sided tensions -- both sides fully contracted is rigid and
   * straight, not bent. */
  jointMoment(): void {
    const rows = G.MUS_N_ROWS, mm = G.N_MUSCLES;
    for (let r = 0; r < rows; r++) {
      let sd: f64 = 0.0, sv: f64 = 0.0;
      const rd = B + G.OFF_mus_row_mask_d + <usize>(r * mm);
      const rv = B + G.OFF_mus_row_mask_v + <usize>(r * mm);
      for (let c = 0; c < mm; c++) {
        if (load<u8>(rd + <usize>c)) sd += unchecked(this.mTen[c]);
        if (load<u8>(rv + <usize>c)) sv += unchecked(this.mTen[c]);
      }
      unchecked(sRowD[r] = sd / m(G.OFF_mus_row_n_d, r));
      unchecked(sRowV[r] = sv / m(G.OFF_mus_row_n_v, r));
    }
    // Linear interpolation of the row tensions onto the mechanical joints, matching
    // np.interp: clamped at both ends, rows are sorted by body position.
    for (let j = 0; j < G.N_JOINTS; j++) {
      const s = m(G.OFF_mus_joint_s, j);
      let k = 0;
      while (k < rows - 2 && m(G.OFF_mus_row_pos, k + 1) < s) k++;
      const p0 = m(G.OFF_mus_row_pos, k), p1 = m(G.OFF_mus_row_pos, k + 1);
      let f = p1 > p0 ? (s - p0) / (p1 - p0) : 0.0;
      f = clamp(f, 0.0, 1.0);
      if (s <= m(G.OFF_mus_row_pos, 0)) f = 0.0;
      if (s >= m(G.OFF_mus_row_pos, rows - 1)) { k = rows - 2; f = 1.0; }
      const dj = unchecked(sRowD[k]) + f * (unchecked(sRowD[k + 1]) - unchecked(sRowD[k]));
      const vj = unchecked(sRowV[k]) + f * (unchecked(sRowV[k + 1]) - unchecked(sRowV[k]));
      unchecked(this.moment[j] = m(G.OFF_mus_joint_gain, j) * (dj - vj));
    }
  }

  /* Total gap conductance per cell, over living neighbours only. A dead cell neither
   * drives nor is driven, so it has to leave the conductance sum as well as the matrix. */
  rebuildGap(): void {
    this.anyDead = false;
    for (let i = 0; i < G.N_NEURONS; i++) if (!unchecked(this.alive[i])) { this.anyDead = true; break; }
    for (let r = 0; r < G.N_NEURONS; r++) {
      if (!unchecked(this.alive[r])) { unchecked(this.gapTot[r] = 0.0); continue; }
      let acc: f64 = 0.0;
      const e = mi(G.OFF_gap_ptr, r + 1);
      for (let k = mi(G.OFF_gap_ptr, r); k < e; k++) {
        if (unchecked(this.alive[mi(G.OFF_gap_idx, k)])) acc += m(G.OFF_gap_val, k);
      }
      unchecked(this.gapTot[r] = acc);
    }
  }

  updateNodes(): void {
    const L = G.N_LINKS, l = G.BODY_L;
    let cx = this.bx, cy = this.by;
    unchecked(this.nodesX[0] = cx); unchecked(this.nodesY[0] = cy);
    for (let i = 0; i < L; i++) {
      cx += l * Math.cos(unchecked(this.theta[i]));
      cy += l * Math.sin(unchecked(this.theta[i]));
      unchecked(this.nodesX[i + 1] = cx); unchecked(this.nodesY[i + 1] = cy);
    }
    for (let i = 0; i < G.N_JOINTS; i++) {
      unchecked(this.kappa[i] =
        (unchecked(this.theta[i + 1]) - unchecked(this.theta[i])) / l);
    }
  }

  /* The (n+2)x(n+2) viscous drag metric, assembled exactly as Body._drag_matrix does.
   * The triple sum over segments collapses into three n x n products once P and Q are
   * masked by "strictly behind", which is what makes this affordable at 2 kHz. */
  dragMatrix(): void {
    const n = G.N_LINKS, l = G.BODY_L, N = n + 2;
    const cT = this.cT, cN = this.cN;
    const D = sDm;
    for (let i = 0; i < N * N; i++) unchecked(D[i] = 0.0);

    for (let i = 0; i < n; i++) {
      const th = unchecked(this.theta[i]);
      const c = Math.cos(th), s = Math.sin(th);
      unchecked(sUx[i] = c); unchecked(sUy[i] = s);
      unchecked(sNxv[i] = -s); unchecked(sNyv[i] = c);
    }
    // P[m,k] = n_m . u_k,  Q[m,k] = n_m . n_k, and the two masked copies.
    for (let mm = 0; mm < n; mm++) {
      const nx = unchecked(sNxv[mm]), ny = unchecked(sNyv[mm]);
      for (let k = 0; k < n; k++) {
        const p = nx * unchecked(sUx[k]) + ny * unchecked(sUy[k]);
        const q = nx * unchecked(sNxv[k]) + ny * unchecked(sNyv[k]);
        const idx = mm * n + k;
        unchecked(sPm[idx] = p); unchecked(sQm[idx] = q);
        // The rotational block multiplies two lever arms that must *share* one factor of
        // rho_k between them, so it uses the square-root mask -- (A A^T)[m,p] then sums
        // rho_k rather than rho_k^2.
        unchecked(sAs[idx] = p * m(G.OFF_body_mask_sqrt, idx));
        unchecked(sBs[idx] = q * m(G.OFF_body_mask_sqrt, idx));
      }
    }

    // translation / translation
    let txx: f64 = 0.0, txy: f64 = 0.0, tyy: f64 = 0.0;
    for (let k = 0; k < n; k++) {
      const rho = m(G.OFF_body_rho, k);
      const ux = unchecked(sUx[k]), uy = unchecked(sUy[k]);
      const nx = unchecked(sNxv[k]), ny = unchecked(sNyv[k]);
      txx += cT * rho * ux * ux + cN * rho * nx * nx;
      txy += cT * rho * ux * uy + cN * rho * nx * ny;
      tyy += cT * rho * uy * uy + cN * rho * ny * ny;
    }
    unchecked(D[0] = l * txx); unchecked(D[1] = l * txy);
    unchecked(D[N] = l * txy); unchecked(D[N + 1] = l * tyy);

    // translation / rotation
    const l2 = l * l;
    for (let mm = 0; mm < n; mm++) {
      let cx: f64 = 0.0, cy: f64 = 0.0;
      for (let k = 0; k < n; k++) {
        const idx = mm * n + k;
        const mr = m(G.OFF_body_mask_rho, idx);
        const a = unchecked(sPm[idx]) * mr;
        const b2 = unchecked(sQm[idx]) * mr;
        cx += cT * a * unchecked(sUx[k]) + cN * b2 * unchecked(sNxv[k]);
        cy += cT * a * unchecked(sUy[k]) + cN * b2 * unchecked(sNyv[k]);
      }
      const rho = m(G.OFF_body_rho, mm);
      cx = l2 * (cx + 0.5 * cN * rho * unchecked(sNxv[mm]));
      cy = l2 * (cy + 0.5 * cN * rho * unchecked(sNyv[mm]));
      unchecked(D[(2 + mm) * N + 0] = cx);
      unchecked(D[(2 + mm) * N + 1] = cy);
      unchecked(D[0 * N + (2 + mm)] = cx);
      unchecked(D[1 * N + (2 + mm)] = cy);
    }

    // rotation / rotation
    const l3 = l * l * l;
    for (let a = 0; a < n; a++) {
      for (let b2 = a; b2 < n; b2++) {
        let acc: f64 = 0.0;
        for (let k = 0; k < n; k++) {
          acc += cT * unchecked(sAs[a * n + k]) * unchecked(sAs[b2 * n + k])
               + cN * unchecked(sBs[a * n + k]) * unchecked(sBs[b2 * n + k]);
        }
        acc += cN * 0.5 * unchecked(sQm[a * n + b2]) * m(G.OFF_body_rho_max_off, a * n + b2);
        if (a == b2) acc += cN * m(G.OFF_body_rho, a) / 3.0;
        const v = l3 * acc;
        unchecked(D[(2 + a) * N + (2 + b2)] = v);
        unchecked(D[(2 + b2) * N + (2 + a)] = v);
      }
    }
  }

  /* One mechanical step. `moment` is the active bending moment per joint; contact forces
   * are whatever the wall and obstacles are pushing with. Backward Euler on the elastic
   * and internal-damping terms, which are constant matrices and so cost nothing here but
   * remove the stiffest timescale from the stability condition entirely. */
  stepBody(dt: f64): void {
    const n = G.N_LINKS, N = n + 2, l = G.BODY_L, J = G.N_JOINTS;
    this.dragMatrix();
    const Q = sQv;
    for (let i = 0; i < N; i++) unchecked(Q[i] = 0.0);

    // Elastic restoring torque plus the active moment, mapped through Dif^T.
    for (let j = 0; j < J; j++) {
      const joint = unchecked(this.theta[j + 1]) - unchecked(this.theta[j]);
      const tq = -m(G.OFF_body_K, j) * joint + unchecked(this.moment[j]);
      unchecked(Q[2 + j] -= tq);
      unchecked(Q[2 + j + 1] += tq);
    }
    // A force at node j moves the head coordinate and rotates every joint anterior to it.
    let sx: f64 = 0.0, sy: f64 = 0.0;
    for (let i = 0; i <= n; i++) {
      unchecked(Q[0] += unchecked(this.contactX[i]));
      unchecked(Q[1] += unchecked(this.contactY[i]));
    }
    for (let mm = n - 1; mm >= 0; mm--) {
      sx += unchecked(this.contactX[mm + 1]);
      sy += unchecked(this.contactY[mm + 1]);
      unchecked(Q[2 + mm] += l * (unchecked(sNxv[mm]) * sx + unchecked(sNyv[mm]) * sy));
    }

    for (let a = 0; a < n; a++) {
      for (let b2 = 0; b2 < n; b2++) {
        const idx = a * n + b2;
        unchecked(sDm[(2 + a) * N + (2 + b2)] +=
          m(G.OFF_body_B_mat, idx) + dt * m(G.OFF_body_K_mat, idx));
      }
    }
    if (!solveInPlace(sDm, Q, N)) return;
    this.bx += unchecked(Q[0]) * dt;
    this.by += unchecked(Q[1]) * dt;
    for (let i = 0; i < n; i++) unchecked(this.theta[i] += unchecked(Q[2 + i]) * dt);
    this.updateNodes();
  }

  /* --------------------------------------------------------------------- modulators --
   * One slow scalar each, produced by named source neurons in proportion to their
   * activity. An ablated source is masked out elsewhere; here every cell is alive. */
  stepModulators(): void {
    this.modDA  = this.modLevel(this.modDA,  G.OFF_idx_mod_dopamine,  G.LEN_idx_mod_dopamine,  G.MOD_RATE_DOPAMINE);
    this.modSER = this.modLevel(this.modSER, G.OFF_idx_mod_serotonin, G.LEN_idx_mod_serotonin, G.MOD_RATE_SEROTONIN);
    this.modOA  = this.modLevel(this.modOA,  G.OFF_idx_mod_octopamine,G.LEN_idx_mod_octopamine,G.MOD_RATE_OCTOPAMINE);
    this.modPDF = this.modLevel(this.modPDF, G.OFF_idx_mod_pdf,       G.LEN_idx_mod_pdf,       G.MOD_RATE_PDF);
  }
  modLevel(level: f64, off: usize, len: i32, rate: f64): f64 {
    if (len == 0) return level;
    // Levels are deviations from a resting release of 0.5, and a dead cell's activation
    // reads 0.0, so an unmasked ablated source does not fall silent -- it signals the
    // *opposite*. A dead source therefore contributes a deviation of zero.
    //
    // It stays in the denominator while doing so. Dropping it instead makes the level a
    // mean over the survivors, which is not a quantity a neuron can affect by dying:
    // removing a source whose activation sits below its siblings' *raises* the mean.
    // Killing HSN, at 0.521 against a serotonin source mean of 0.62, drove serotonin from
    // 0.120 to 0.219 -- up, on removing one of the cells that makes it. With nothing
    // ablated this is arithmetically identical to dropping them, so no unablated result
    // moves.
    let acc: f64 = 0.0;
    for (let i = 0; i < len; i++) {
      const c = mi(off, i);
      if (this.anyDead && !unchecked(this.alive[c])) continue;   // deviation of zero
      acc += unchecked(this.act[c]) - 0.5;
    }
    const target = acc / <f64>len;
    return level + (target - level) * rate;
  }
  turnBias(): f64 { return G.MOD_SEROTONIN_TURNING * this.modSER - G.MOD_PDF_ROAMING * this.modPDF; }
  locomotorScale(): f64 {
    return clamp(1.0 - G.MOD_DOPAMINE_SLOWING * this.modDA
                     - G.MOD_SEROTONIN_SLOWING * this.modSER
                     + G.MOD_OCTOPAMINE_SPEEDING * this.modOA, 0.25, 1.6);
  }
  wavelengthShortening(): f64 { return clamp(G.MOD_DOPAMINE_WAVELENGTH * this.modDA, 0.0, 1.0); }

  /* ------------------------------------------------------------------------ senses --- */
  @inline addTo(off: usize, len: i32, v: f64): void {
    for (let i = 0; i < len; i++) unchecked(sIext[mi(off, i)] += v);
  }
  sense(): void {
    const n = G.N_NEURONS, dt = G.DT;
    for (let i = 0; i < n; i++) unchecked(sIext[i] = 0.0);
    const nx = unchecked(this.nodesX[0]), ny = unchecked(this.nodesY[0]);

    // -- chemosensation. Sensation is differential: each channel keeps an adapting
    //    baseline and reports the deviation, so a worm in a uniform concentration --
    //    however high -- stops responding to it within seconds.
    const c = world.sample(world.attractant, nx, ny);
    const rep = world.sample(world.repellent, nx, ny);
    const T = world.temperature(nx);
    const o2 = world.oxygen(nx, ny);
    const food = world.sample(world.food, nx, ny);
    if (!this.adaptReady) {
      this.cAdapt = c; this.odourAdapt = c; this.tAdapt = G.SEN_CULTIVATION_TEMP;
      this.o2Adapt = o2; this.repAdapt = rep; this.adaptReady = true;
    }
    this.sensedAtt = c; this.sensedRep = rep; this.sensedT = T;
    this.sensedO2 = o2; this.sensedFood = food;

    const dc = c - this.cAdapt;
    this.cAdapt += (c - this.cAdapt) * (1.0 - G.CHEM_DECAY);
    this.addTo(G.OFF_idx_ase_on, G.LEN_idx_ase_on, this.gene(G.GENE_SEN_CHEMO_GAIN) * dc);
    this.addTo(G.OFF_idx_ase_off, G.LEN_idx_ase_off, -this.gene(G.GENE_SEN_CHEMO_GAIN) * dc);

    const dodour = c - this.odourAdapt;
    this.odourAdapt += (c - this.odourAdapt) * G.ODOUR_RATE;
    this.addTo(G.OFF_idx_awa, G.LEN_idx_awa, this.gene(G.GENE_SEN_CHEMO_GAIN) * 0.6 * dodour);
    this.addTo(G.OFF_idx_awc, G.LEN_idx_awc, -this.gene(G.GENE_SEN_CHEMO_GAIN) * 0.6 * dodour);

    // Tonic and differential, as for oxygen. The tonic part sets how much the animal
    // reverses near a drop at all; the differential part is what makes those reversals
    // happen while it is heading *into* the drop rather than out of it. Without it the
    // drop does not repel the animal, it traps it.
    const drep = rep - this.repAdapt;
    this.repAdapt += (rep - this.repAdapt) * G.REP_RATE;
    this.addTo(G.OFF_idx_ash, G.LEN_idx_ash,
               this.gene(G.GENE_SEN_CHEMO_GAIN) * 1.6 * rep + this.gene(G.GENE_SEN_REPELLENT_D_GAIN) * drep);
    this.addTo(G.OFF_idx_adl, G.LEN_idx_adl, this.gene(G.GENE_SEN_CHEMO_GAIN) * 0.8 * rep);
    this.addTo(G.OFF_idx_ask, G.LEN_idx_ask, -this.gene(G.GENE_SEN_CHEMO_GAIN) * 0.3 * rep);

    // -- thermosensation. AFD is a warm receptor above the cultivation temperature and
    //    silent below it.
    const dT = T - this.tAdapt;
    this.tAdapt += (T - this.tAdapt) * (1.0 - G.THERM_DECAY);
    this.addTo(G.OFF_idx_afd, G.LEN_idx_afd, this.gene(G.GENE_SEN_THERMO_GAIN) * (dT < -0.5 ? -0.5 : dT));

    // -- oxygen. Tonic and differential, and the differential is what makes the taxis
    //    point the right way.
    const do2 = o2 - this.o2Adapt;
    this.o2Adapt += (o2 - this.o2Adapt) * G.O2_RATE;
    this.addTo(G.OFF_idx_urx, G.LEN_idx_urx,
               this.gene(G.GENE_SEN_OXYGEN_GAIN) * (o2 - G.SEN_OXYGEN_PREFERRED) + G.SEN_OXYGEN_D_GAIN * do2);

    // -- mechanosensation. Smoothed contact, not accumulated: as an exponential moving
    //    average the steady state is the force itself, and does not scale with 1/dt.
    const half = (G.N_LINKS + 1) / 2;
    let ant: f64 = this.pokeA, post: f64 = this.pokeP;
    let mag0: f64 = 0.0, mag1: f64 = 0.0;
    for (let i = 0; i <= G.N_LINKS; i++) {
      const fxv = unchecked(this.contactX[i]), fyv = unchecked(this.contactY[i]);
      const mg = Math.sqrt(fxv * fxv + fyv * fyv);
      if (i == 0) mag0 = mg; else if (i == 1) mag1 = mg;
      if (i < half) ant += mg; else post += mg;
    }
    this.touchA += (ant - this.touchA) * G.TOUCH_RATE;
    this.touchP += (post - this.touchP) * G.TOUCH_RATE;
    this.pokeA = 0.0; this.pokeP = 0.0;
    if (G.HABITUATES) {
      const rA = G.HAB_RECOVER + G.HAB_USE * this.touchA;
      const rP = G.HAB_RECOVER + G.HAB_USE * this.touchP;
      const iA = G.HAB_RECOVER / rA, iP = G.HAB_RECOVER / rP;
      this.availA = iA + (this.availA - iA) * Math.exp(-rA * dt);
      this.availP = iP + (this.availP - iP) * Math.exp(-rP * dt);
    }
    this.addTo(G.OFF_idx_touch_ant, G.LEN_idx_touch_ant, this.gene(G.GENE_SEN_TOUCH_GAIN) * this.touchA * this.availA);
    this.addTo(G.OFF_idx_touch_post, G.LEN_idx_touch_post, this.gene(G.GENE_SEN_TOUCH_GAIN) * this.touchP * this.availP);
    this.addTo(G.OFF_idx_nose_touch, G.LEN_idx_nose_touch, this.gene(G.GENE_SEN_TOUCH_GAIN) * 0.5 * (mag0 + mag1));

    // -- food, sensed by the dopaminergic mechanoreceptors and tasted by NSM
    this.addTo(G.OFF_idx_dopaminergic, G.LEN_idx_dopaminergic, this.gene(G.GENE_SEN_FOOD_GAIN) * food);
    this.addTo(G.OFF_idx_nsm, G.LEN_idx_nsm, this.gene(G.GENE_SEN_FOOD_GAIN) * food);

    // -- locomotory command bias: a bias, not a clamp
    this.addTo(G.OFF_idx_avb, G.LEN_idx_avb, this.gene(G.GENE_SEN_TONIC_FORWARD));
    this.addTo(G.OFF_idx_ava, G.LEN_idx_ava, G.SEN_TONIC_BACKWARD);

    // -- the direction decision. Read the *difference* between the pools: absolute
    //    activity has no dynamic range (AVB saturates and stays saturated), but the
    //    difference moves whenever either pool is driven.
    let fa: f64 = 0.0, ba: f64 = 0.0;
    for (let i = 0; i < G.LEN_idx_avb; i++) fa += unchecked(this.act[mi(G.OFF_idx_avb, i)]);
    for (let i = 0; i < G.LEN_idx_ava; i++) ba += unchecked(this.act[mi(G.OFF_idx_ava, i)]);
    fa /= <f64>G.LEN_idx_avb; ba /= <f64>G.LEN_idx_ava;
    // Bounded, so no modulator can shift the latch window clear of the operating point
    // and turn the Schmitt trigger into a one-way latch.
    const lim = G.SEN_TURN_BIAS_LIMIT * this.gene(G.GENE_SEN_GATE_HYSTERESIS);
    const bias = this.gene(G.GENE_SEN_GATE_BIAS) + clamp(this.turnBias(), -lim, lim);
    const diff = fa - ba;
    let fwd: f64;
    if (G.GATE_LATCHED) {
      if (this.goingForward) {
        if (diff < bias - this.gene(G.GENE_SEN_GATE_HYSTERESIS)) this.goingForward = false;
      } else if (diff > bias + this.gene(G.GENE_SEN_GATE_HYSTERESIS)) this.goingForward = true;
      fwd = this.goingForward ? 1.0 : 0.0;
    } else {
      fwd = 1.0 / (1.0 + Math.exp(-G.SEN_GATE_SLOPE * (diff - bias)));
    }
    const bwd = 1.0 - fwd;

    // -- the omega turn: a transient locked to the reversal-to-forward *edge*
    const forwardNow = fwd >= 0.5;
    if (forwardNow) {
      if (this.revSteps > 0) {
        this.omega = Math.min(1.0, <f64>this.revSteps / G.OMEGA_REF_N);
        this.omegaSign = this.rng.uniform() < this.gene(G.GENE_SEN_OMEGA_VENTRAL_FRACTION) ? 1.0 : -1.0;
        this.revSteps = 0;
      }
    } else {
      this.revSteps++;
      this.omega = 0.0;
    }
    this.omega *= G.OMEGA_DECAY;
    if (this.gene(G.GENE_SEN_OMEGA_CURRENT) > 0.0 && this.omega > 1e-4) {
      // A differential, not a push: releasing the dorsal antagonist is worth an order of
      // magnitude more than driving the ventral side harder, which saturates.
      const dOm = this.gene(G.GENE_SEN_OMEGA_CURRENT) * this.omega * this.omegaSign;
      this.addTo(G.OFF_idx_omega_v, G.LEN_idx_omega_v, dOm);
      this.addTo(G.OFF_idx_omega_d, G.LEN_idx_omega_d, -dOm);
    }

    // -- descending drive to the selected cord. The B and A motor neurons only oscillate
    //    when their command interneuron is engaged, so the drive follows the gate.
    const drive = this.gene(G.GENE_SEN_CORD_DRIVE) * this.locomotorScale();
    this.addTo(G.OFF_idx_db, G.LEN_idx_db, drive * fwd);
    this.addTo(G.OFF_idx_vb, G.LEN_idx_vb, drive * fwd);
    this.addTo(G.OFF_idx_da, G.LEN_idx_da, drive * bwd);
    this.addTo(G.OFF_idx_va, G.LEN_idx_va, drive * bwd);

    // -- proprioception. Normalised curvature; 5 /mm is roughly the peak a crawling worm
    //    reaches. Adapt out the static component before the receptor saturates on it.
    const J = G.N_JOINTS;
    for (let j = 0; j < J; j++) unchecked(sKn[j] = clamp(unchecked(this.kappa[j]) / 5.0, -2.0, 2.0));
    const short = this.wavelengthShortening();
    spmv(G.OFF_wb_ptr, G.OFF_wb_idx, G.OFF_wb_val, n, sKn, sWbv);
    spmv(G.OFF_wa_ptr, G.OFF_wa_idx, G.OFF_wa_val, n, sKn, sWav);
    if (short > 1e-6) {
      // Basal slowing: shorten the wave rather than weaken the drive, because the
      // frequency is mechanics-set and will not move.
      spmv(G.OFF_wbf_ptr, G.OFF_wbf_idx, G.OFF_wbf_val, n, sKn, sWbf);
      spmv(G.OFF_waf_ptr, G.OFF_waf_idx, G.OFF_waf_val, n, sKn, sWaf);
      for (let r = 0; r < n; r++) {
        unchecked(sWbv[r] = (1.0 - short) * unchecked(sWbv[r]) + short * unchecked(sWbf[r]));
        unchecked(sWav[r] = (1.0 - short) * unchecked(sWav[r]) + short * unchecked(sWaf[r]));
      }
    }
    for (let r = 0; r < n; r++) {
      const wb = unchecked(sWbv[r]), wa = unchecked(sWav[r]);
      const raw = wb * fwd + wa * bwd;
      unchecked(this.propAdapt[r] += (raw - unchecked(this.propAdapt[r])) * G.PROP_ADAPT_RATE);
      unchecked(sIext[r] += Math.tanh(raw - unchecked(this.propAdapt[r]))
                * this.gene(G.GENE_SEN_PROPRIO_GAIN) * m(G.OFF_g_scale_prop, r));
    }

    // -- the head reflex. It runs whichever way the animal is going: it is what keeps the
    //    nose sweeping, and the sweep is what steering acts on.
    let headOff: i32 = 0;
    if (G.HEAD_DELAY_N > 0) {
      // Buffer the curvature, not the reduced signal, so the delay sits where a
      // transduction delay physically would -- between strain and receptor.
      const wslot = this.headHistI * J;
      for (let j = 0; j < J; j++) unchecked(this.headHist[wslot + j] = unchecked(sKn[j]));
      this.headHistI = (this.headHistI + 1) % (G.HEAD_DELAY_N + 1);
      headOff = this.headHistI * J;
    }
    let headGain = this.gene(G.GENE_SEN_HEAD_PROPRIO_GAIN);
    if (G.SEN_OMEGA_REFLEX_SUPPRESSION > 0.0 && Math.abs(this.omega) > 1e-4) {
      const f = 1.0 - G.SEN_OMEGA_REFLEX_SUPPRESSION * Math.abs(this.omega);
      headGain *= f > 0.0 ? f : 0.0;
    }
    for (let j = 0; j < J; j++) {
      unchecked(sKh[j] = G.HEAD_DELAY_N > 0 ? unchecked(this.headHist[headOff + j])
                                            : unchecked(sKn[j]));
    }
    if (G.HEAD_DISTRIBUTED) {
      spmv(G.OFF_whead_ptr, G.OFF_whead_idx, G.OFF_whead_val, n, sKh, sWhv);
      for (let r = 0; r < n; r++) {
        const raw = unchecked(sWhv[r]);
        unchecked(this.headSignal[r] += (raw - unchecked(this.headSignal[r])) * (1.0 - G.HEAD_DECAY));
        unchecked(sIext[r] += Math.tanh(unchecked(this.headSignal[r])) * headGain
                  * m(G.OFF_g_scale_head, r));
      }
    } else {
      let raw: f64 = 0.0;
      for (let j = 0; j < J; j++) raw += m(G.OFF_head_window, j) * unchecked(sKh[j]);
      unchecked(this.headSignal[0] += (raw - unchecked(this.headSignal[0])) * (1.0 - G.HEAD_DECAY));
      const v = Math.tanh(unchecked(this.headSignal[0])) * headGain;
      for (let r = 0; r < n; r++) {
        unchecked(sIext[r] += m(G.OFF_W_head_sign, r) * m(G.OFF_g_scale_head, r) * v);
      }
    }
  }

  /* ----------------------------------------------------------------------- pharynx --- */
  @inline meanDev(off: usize, len: i32): f64 {
    let acc: f64 = 0.0; let live = 0;
    for (let i = 0; i < len; i++) {
      const c = mi(off, i);
      if (this.anyDead && !unchecked(this.alive[c])) continue;
      acc += unchecked(this.act[c]); live++;
    }
    return live > 0 ? acc / <f64>live - 0.5 : 0.0;
  }
  stepPharynx(foodAtMouth: f64): f64 {
    const dt = G.DT;
    // Serotonin acts *through* the pacemaker rather than beside it: SER-7 sits in MC, so
    // an animal without MC does not pump fast however much serotonin it has.
    let mc = this.meanDev(G.OFF_idx_mc, G.LEN_idx_mc);
    // Serotonin acts through the pacemaker, so with MC gone it has nothing to act on.
    let mcLive = false;
    for (let i = 0; i < G.LEN_idx_mc; i++) {
      if (!this.anyDead || unchecked(this.alive[mi(G.OFF_idx_mc, i)])) { mcLive = true; break; }
    }
    if (mcLive) mc += G.PH_SEROTONIN_TO_MC * this.modSER - G.PH_OCTOPAMINE_TO_MC * this.modOA;
    const i2 = this.meanDev(G.OFF_idx_i2, G.LEN_idx_i2);
    this.phRate = clamp(G.PH_MYOGENIC_RATE + G.PH_MC_RATE_GAIN * mc - G.PH_I2_RATE_GAIN * i2,
                        0.0, G.PH_MAX_RATE);

    // The cycle runs during the pump as well as between pumps, so the rate is the one the
    // animal achieves; what remains is a refractory period, capping it at 1/duration.
    this.phCaptured = 0.0;
    this.phWant = 0.0;          // a step with no pump asks for nothing
    this.phPhase += this.phRate * dt;
    if (this.phPumping) {
      this.phOpen -= dt;
      if (this.phOpen <= 0.0) this.phPumping = false;
    }
    if (!this.phPumping && this.phPhase >= 1.0) {
      this.phPhase = 0.0;
      const m3 = this.meanDev(G.OFF_idx_m3, G.LEN_idx_m3);
      this.phDur = G.PH_PUMP_DURATION / (1.0 + G.PH_M3_DURATION_GAIN * (m3 > 0.0 ? m3 : 0.0));
      this.phOpen = this.phDur;
      this.phPumping = true;
      this.phPumps++;
      const room = 1.0 - this.lumen / G.PH_LUMEN_CAPACITY;
      const want = G.PH_VOLUME_PER_PUMP * (foodAtMouth > 0.0 ? foodAtMouth : 0.0)
                   * (this.phDur / G.PH_PUMP_DURATION) * (room > 0.0 ? room : 0.0);
      /* What the pump asks for. The plate is debited by the caller, not here, because
       * with several animals on one lawn the order they are served in must not matter --
       * see settleFeeding. `step` settles immediately for one animal; `stepAll` collects
       * every demand first and settles them together. */
      this.phWant = want;
    }
    return this.phWant;
  }

  /* The second half: take what the plate actually gave, then move it on.
   *
   * Split from the demand phase so a population can be settled simultaneously. Transport
   * lives here rather than with the demand because M4 empties a lumen that this step may
   * just have filled, and doing it before the allocation is known would move food the
   * animal had not been given yet. */
  settlePharynx(got: f64): f64 {
    const dt = G.DT;
    this.phCaptured = got;
    this.lumen += got;
    // Isthmus peristalsis. M4 is what moves the lumen's contents on; without it the
    // animal pumps normally and starves, so transport is its own step.
    const m4 = this.meanDev(G.OFF_idx_m4, G.LEN_idx_m4);
    const drv = G.PH_M4_TRANSPORT + G.PH_M4_GAIN * (m4 > 0.0 ? m4 : 0.0);
    let moved = this.lumen * (drv > 0.0 ? drv : 0.0) * dt;
    if (moved > this.lumen) moved = this.lumen;
    this.lumen -= moved;
    this.ingested += moved;
    return moved;
  }

  /* ------------------------------------------------------------------- a whole step -- */
  prepareStep(): f64 {
    this.activation();
    // The modulators read the same activation the senses do and are updated first, so the
    // wireless layer is one step behind the wired one -- the same consistent unit delay
    // used everywhere else in this model.
    this.stepModulators();
    this.sense();
    this.stepNervous();
    this.stepMuscle();
    this.contact();
    this.jointMoment();
    const sub = G.BODY_SUBSTEPS;
    if (sub > 1) {
      const d = G.DT / <f64>sub;
      for (let i = 0; i < sub; i++) this.stepBody(d);
    } else {
      this.stepBody(G.DT);
    }
    this.phFood = world.sample(world.food, unchecked(this.nodesX[0]), unchecked(this.nodesY[0]));
    return this.stepPharynx(this.phFood);
  }

  /* Everything downstream of knowing what the plate gave.
   *
   * `eaten` is what the world lost; `ingested` is what reached the intestine; they differ
   * by whatever is in the lumen. The uterus fills from what the pharynx actually
   * transported, so an animal that does not eat does not make eggs, and the vulva is
   * halfway down the body. */
  finishStep(got: f64): void {
    const moved = this.settlePharynx(got);
    this.eaten += got;
    if (this.stepEggLaying(moved, this.phFood) > 0.0) {
      const mid = G.N_LINKS >> 1;
      world.layEgg(unchecked(this.nodesX[mid]), unchecked(this.nodesY[mid]),
                   this.id, this.t, this.genes);
    }
    this.t += G.DT;
  }

  /* One animal, settled against the plate on its own. Identical to the batch path when
   * there is only one demand, which is what keeps the conformance case exact. */
  step(): void {
    const want = this.prepareStep();
    const got = want > 0.0
      ? world.eat(unchecked(this.nodesX[0]), unchecked(this.nodesY[0]), want) : 0.0;
    this.finishStep(got);
  }

  /* Vulval muscle, the uterus that feeds it, and the resource that clusters it.
   * Mirrors worm/egglaying.py line for line; the reasoning is all in that file. */
  stepEggLaying(ingestedDelta: f64, onFood: f64): f64 {
    const dt = G.DT;

    if (this.eglRestN < G.EGL_REST_SAMPLES) {
      this.eglRestN++;
      const k = 1.0 / <f64>this.eglRestN;
      let acc: f64 = 0.0;
      for (let i = 0; i < G.LEN_idx_egl_vc; i++) acc += unchecked(this.act[mi(G.OFF_idx_egl_vc, i)]);
      const mean = G.LEN_idx_egl_vc > 0 ? acc / <f64>G.LEN_idx_egl_vc : 0.0;
      this.eglVcRest += (mean - this.eglVcRest) * k;
    }

    // HSN as ABSOLUTE activation -- it is the driver, and a deviation term contributes no
    // mean drive, so ablating it would change nothing. The VCs as a deviation, because
    // they modulate. See EggLayingParams for what that distinction cost to find.
    let hAcc: f64 = 0.0; let hLive = 0;
    for (let i = 0; i < G.LEN_idx_egl_hsn; i++) {
      const c = mi(G.OFF_idx_egl_hsn, i);
      if (this.anyDead && !unchecked(this.alive[c])) continue;
      hAcc += unchecked(this.act[c]); hLive++;
    }
    const aHsn = hLive > 0 ? hAcc / <f64>hLive : 0.0;

    let vAcc: f64 = 0.0; let vLive = 0;
    for (let i = 0; i < G.LEN_idx_egl_vc; i++) {
      const c = mi(G.OFF_idx_egl_vc, i);
      if (this.anyDead && !unchecked(this.alive[c])) continue;
      vAcc += unchecked(this.act[c]); vLive++;
    }
    const dVc = vLive > 0 ? vAcc / <f64>vLive - this.eglVcRest : 0.0;

    let eggs = this.eglEggs + G.EGL_EGGS_PER_FOOD * ingestedDelta;
    this.eglEggs = eggs > G.EGL_UTERUS_CAPACITY ? G.EGL_UTERUS_CAPACITY : eggs;

    const drive = G.EGL_MYOGENIC + G.EGL_HSN_GAIN * aHsn
                + G.EGL_SEROTONIN_GAIN * this.modSER - G.EGL_VC_GAIN * dVc;
    const gate = G.EGL_OFF_FOOD_FLOOR + (1.0 - G.EGL_OFF_FOOD_FLOOR) * clamp(onFood, 0.0, 1.0);
    const target = clamp(drive, 0.0, 1.0) * gate;
    /* Exponential Euler, matching worm/egglaying.py. This was
     * `this.eglVm += (target - this.eglVm) * (dt / G.EGL_VM_TAU)` -- forward Euler, the
     * only such integrator in the model, amplifying by |1 - dt/vm_tau| and diverging for
     * vm_tau < dt/2. It does not raise or produce a NaN when it does; it lays eggs,
     * because vm is reset to 0 on every lay and the instability self-limits by firing the
     * trigger every refractory period. Profitable and invisible, on any fitness that
     * counts eggs. See #42. */
    this.eglVm = target + (this.eglVm - target) * G.EGL_VM_DECAY;

    /* The exported rate, not a locally derived one. This used to be
     * `1.0 - Math.exp(-dt / G.EGL_RESOURCE_TAU)` -- an exp evaluated two thousand times a
     * second to recompute a constant, and computed by the one arrangement of the
     * arithmetic that loses six significant digits to cancellation. Python now uses
     * -expm1 and exports the result, so both implementations read one number instead of
     * each deriving its own and disagreeing at 6.5e-12. */
    this.eglResource += (1.0 - this.eglResource) * G.EGL_RESOURCE_RECOVER;
    if (this.eglRefractory > 0.0) {
      this.eglRefractory -= dt;
      if (this.eglRefractory < 0.0) this.eglRefractory = 0.0;
    }

    // Two thresholds, not one. A single one leaves the resource sitting *at* the bar when
    // a phase ends, so it climbs back over within a step or two and there is no quiet
    // period. See EggLayingParams.
    if (this.eglInPhase) {
      if (this.eglResource < G.EGL_RESOURCE_OFF) this.eglInPhase = false;
    } else if (this.eglResource >= G.EGL_RESOURCE_ON) {
      this.eglInPhase = true;
    }

    if (this.eglRefractory <= 0.0 && this.eglEggs >= 1.0
        && this.eglVm >= G.EGL_VM_THRESHOLD && this.eglInPhase) {
      this.eglEggs -= 1.0;
      this.eglLaid++;
      this.eglRefractory = G.EGL_REFRACTORY;
      this.eglResource -= G.EGL_RESOURCE_COST;
      if (this.eglResource < 0.0) this.eglResource = 0.0;
      this.eglVm = 0.0;
      return 1.0;
    }
    return 0.0;
  }

  contact(): void {
    const n = G.N_LINKS;
    const stiff: f64 = 40.0, R = world.extent - 0.05;
    for (let i = 0; i <= n; i++) {
      const x = unchecked(this.nodesX[i]), y = unchecked(this.nodesY[i]);
      const r = Math.sqrt(x * x + y * y);
      const over = r - R;
      if (over > 0.0) {
        const inv = 1.0 / (r > 1e-9 ? r : 1e-9);
        unchecked(this.contactX[i] = -stiff * over * x * inv);
        unchecked(this.contactY[i] = -stiff * over * y * inv);
      } else {
        unchecked(this.contactX[i] = 0.0);
        unchecked(this.contactY[i] = 0.0);
      }
    }
  }
}

// Noise can be switched off, which is what makes the two implementations comparable at
// all: see the note at the top of this file.
let noiseOn: bool = true;

/* The population, and why a handle is not an array index.
 *
 * `worms` is kept dense so `stepAll` can walk it without a gap test, but an animal's
 * identity is its `id` and not its position. Those were the same thing until now --
 * `createWorm` returned `worms.length - 1` -- and that is exactly the representation a
 * generational loop cannot use. Selection culls the *unfit*, not the most recently
 * created, and removing anyone but the tail renumbers every animal after them while
 * every accessor here takes a handle. The viewer would go on reading what it thought was
 * worm 3 and get whichever animal had been shuffled into slot 3.
 *
 * So ids are handed out monotonically and never reused. A stale handle then names an
 * animal that is gone rather than aliasing a live one, which is the difference between a
 * loud failure and a silently wrong experiment.
 */
let worms: Worm[] = [];
let wormById: Map<i32, Worm> = new Map<i32, Worm>();
let nextWormId: i32 = 0;

// Resolve a handle. Aborts on an unknown id, which is deliberate: the alternative is
// returning some other animal's state and calling it worm 3.
@inline function byId(id: i32): Worm { return wormById.get(id); }

// -------------------------------------------------------------------------- exported --

export function initWorld(): void { world = new World(); }
export function addFood(x: f64, y: f64, r: f64, d: f64, att: f64, ls: f64): void {
  world.addPatch(x, y, r, d, att, ls);
}
/* How many lawns the plate is carrying, and how many it turned away. A patch is a megabyte
 * of cached field shape now, so `addFood` can refuse (see MAX_FOOD_PATCHES); a caller that
 * draws a marker for every lawn it asked for -- the viewer does -- has to be able to find
 * out whether the plate actually took it, rather than painting food that is not there. */
export function foodPatchCount(): i32 { return world.patchAtt.length; }
export function foodPatchesRefused(): i32 { return world.patchesRefused; }
export function addRepellent(x: f64, y: f64, s: f64, ls: f64): void {
  world.addRepellent(x, y, s, ls);
}
/* Place an animal with its mouth at (x, y). `heading` is the direction its body *trails*,
 * so the animal faces -- and travels -- at `heading + PI`. The name reads the other way
 * and there is no getting around that without breaking every caller, so it is written
 * down here, in Body's docstring on the Python side, and in a check that fails: see
 * population.mjs case 11 and test_physics.py's heading test. Callers that translated "aim
 * at X" into the bearing of X aimed at its reflection, and two of them shipped. */
export function createWorm(seed: i32, x: f64, y: f64, heading: f64): i32 {
  const wm = new Worm(<u64>seed, x, y, heading);
  const id = nextWormId++;
  wm.id = id;
  worms.push(wm);
  wormById.set(id, wm);
  return id;
}
export function wormCount(): i32 { return worms.length; }
/* Enumerate the population. Ids are not contiguous once anything has been culled, so a
 * caller that wants every animal has to ask rather than counting from zero. */
export function wormIdAt(k: i32): i32 {
  return k >= 0 && k < worms.length ? unchecked(worms[k]).id : -1;
}
export function hasWorm(id: i32): i32 { return wormById.has(id) ? 1 : 0; }

/* The genome. Slot numbering comes from tools/export_model.py and is emitted into
 * model_gen.ts, so the browser and the runtime cannot disagree about what gene 7 is.
 *
 * No validation of the *value* here on purpose: what counts as a survivable gain is a
 * question for whatever is doing the selecting, and a runtime that silently clamped would
 * hide the answer. An animal given a lethal genome should behave lethally where it can be
 * measured, not quietly behave like a healthy one. */
export function geneCount(): i32 { return G.N_GENES; }
export function setGene(w: i32, slot: i32, v: f64): void {
  if (slot >= 0 && slot < G.N_GENES) unchecked(byId(w).genes[slot] = v);
}
export function getGene(w: i32, slot: i32): f64 {
  return slot >= 0 && slot < G.N_GENES ? unchecked(byId(w).genes[slot]) : NaN;
}
// Put an animal back to the unmutated model, which is also what a fresh worm starts as.
export function resetGenes(w: i32): void { byId(w).resetGenes(); }
export function clearWorms(): void { worms = []; wormById = new Map<i32, Worm>(); }
/* Remove one animal, whoever it is. Returns 1 if it was there.
 *
 * Swap-with-last, so removal is O(1) and the array stays dense -- the moved animal keeps
 * its id, which is the whole point of having one. The population is allowed to reach
 * zero: a generation boundary that clears and repopulates should not have to keep one
 * arbitrary survivor alive to satisfy the container. */
export function removeWorm(id: i32): i32 {
  if (!wormById.has(id)) return 0;
  const wm = wormById.get(id);
  const n = worms.length;
  for (let k = 0; k < n; k++) {
    if (unchecked(worms[k]) === wm) {
      unchecked(worms[k] = unchecked(worms[n - 1]));
      worms.pop();
      break;
    }
  }
  wormById.delete(id);
  return 1;
}
export function popWorm(): void {
  if (worms.length > 0) removeWorm(unchecked(worms[worms.length - 1]).id);
}
export function resetWorld(): void { world = new World(); }

/* Ablation. The caller passes a list of neuron indices; passing none restores everything,
 * which is why this replaces the set rather than adding to it. */
export function setAblated(w: i32, ptr: usize, count: i32): void {
  const wm = byId(w);
  for (let i = 0; i < G.N_NEURONS; i++) unchecked(wm.alive[i] = 1);
  for (let k = 0; k < count; k++) {
    const idx = load<i32>(ptr + (<usize>k << 2));
    if (idx >= 0 && idx < G.N_NEURONS) unchecked(wm.alive[idx] = 0);
  }
  wm.rebuildGap();
  for (let i = 0; i < G.N_NEURONS; i++) {
    if (!unchecked(wm.alive[i])) {
      unchecked(wm.V[i] = m(G.OFF_E_leak, 0));
      unchecked(wm.sv[i] = 0.0);
    }
  }
}
export function isAlive(w: i32, i: i32): i32 { return byId(w).alive[i]; }
export function setMedium(ct: f64, cn: f64): void {
  for (let i = 0; i < worms.length; i++) { worms[i].cT = ct; worms[i].cN = cn; }
}

// Drive the body directly, which is what the conformance test for the mechanics needs:
// a prescribed moment, no biology, the same numbers on both sides.
export function setMoment(w: i32, j: i32, v: f64): void { unchecked(byId(w).moment[j] = v); }
export function stepBodyOnly(w: i32, dt: f64, steps: i32): void {
  const wm = byId(w);
  for (let i = 0; i < steps; i++) { wm.contact(); wm.stepBody(dt); wm.t += dt; }
}

export function setNoise(on: i32): void { noiseOn = on != 0; }
// One animal, and the plate goes with it -- this is the conformance path, where there is
// only ever one worm and it has to match a Python Simulation exactly. Do not use it to
// step several worms in a loop: the plate would age once per animal per step. Use stepAll.
//
// That the two agree for one animal is checked in wasm/conform.mjs. That the *ordering*
// is right for several is checked in wasm/population.mjs, and it has to be checked there
// because with a single worm the correct implementation and the once-per-animal one are
// byte-identical -- conform.mjs claimed to cover it for a while and could not.
export function step(w: i32, n: i32): void {
  const wm = byId(w);
  for (let i = 0; i < n; i++) { wm.step(); world.stepFields(G.DT); }
}
/* Scratch for the batch settlement, grown when the population does. Allocating per step
 * would mean 2000 allocations a second; these are reused. */
let fWant: StaticArray<f64> = new StaticArray<f64>(0);
let fGot: StaticArray<f64> = new StaticArray<f64>(0);
let fRem: StaticArray<f64> = new StaticArray<f64>(0);
let fR: StaticArray<f64> = new StaticArray<f64>(0);
let fLoI: StaticArray<i32> = new StaticArray<i32>(0);
let fLoJ: StaticArray<i32> = new StaticArray<i32>(0);
let fHiI: StaticArray<i32> = new StaticArray<i32>(0);
let fHiJ: StaticArray<i32> = new StaticArray<i32>(0);
function feedingCapacity(n: i32): void {
  if (fWant.length >= n) return;
  fWant = new StaticArray<f64>(n); fGot = new StaticArray<f64>(n);
  fRem = new StaticArray<f64>(n); fR = new StaticArray<f64>(n);
  fLoI = new StaticArray<i32>(n); fLoJ = new StaticArray<i32>(n);
  fHiI = new StaticArray<i32>(n); fHiJ = new StaticArray<i32>(n);
}

/* Settle every animal's feeding demand against one snapshot of the plate.
 *
 * Order used to decide this. Each animal captured and debited inside its own step, so on
 * a contested lawn worm 0 sampled a full neighbourhood and worm 3 sampled what three
 * others had already been served from -- a systematic advantage in array order, measured
 * at 0.09% per four seconds, and heritable-ish once culling moves animals between slots.
 * Selecting on `food_eaten` therefore partly selected for array position.
 *
 * The rule is the one `World.eat` already uses, applied to everyone at once and then
 * repeated on what is left. An animal wanting `take` from a neighbourhood holding `avail`
 * withdraws `food_c * take/avail` from each cell, so the total fraction demanded of a cell
 * is the sum of `take/avail` over the animals reaching it; where that exceeds one, every
 * withdrawal from that cell is scaled by its reciprocal. One pass is order-independent and
 * conservative but under-serves an animal blocked on a shared cell while it still has
 * untouched cells of its own, so the pass repeats on the remainder until nothing moves.
 *
 * That iteration is not an approximation of the Python: checked against `World.eat_batch`
 * on seven configurations -- one animal, two and four sharing a spot, far apart, starving,
 * offset by one cell, three staggered, and asymmetric demand -- it agrees exactly, to
 * 0.00e+00, including the max-min case a single pass gets wrong.
 */
function settleFeeding(n: i32): void {
  const g = world.g;
  for (let k = 0; k < n; k++) {
    const wm = unchecked(worms[k]);
    let j = <i32>Math.floor((unchecked(wm.nodesX[0]) + world.extent) / world.h);
    let i = <i32>Math.floor((unchecked(wm.nodesY[0]) + world.extent) / world.h);
    i = i < 0 ? 0 : (i > g - 1 ? g - 1 : i);
    j = j < 0 ? 0 : (j > g - 1 ? g - 1 : j);
    unchecked(fLoI[k] = i > 0 ? i - 1 : 0);
    unchecked(fHiI[k] = i < g - 1 ? i + 1 : g - 1);
    unchecked(fLoJ[k] = j > 0 ? j - 1 : 0);
    unchecked(fHiJ[k] = j < g - 1 ? j + 1 : g - 1);
    unchecked(fGot[k] = 0.0);
    unchecked(fRem[k] = unchecked(fWant[k]));
  }

  // Eight passes is far more than the two or three any real configuration needs; the loop
  // exits as soon as a pass moves nothing, and the bound is only there so a pathological
  // field cannot spin.
  for (let pass = 0; pass < 8; pass++) {
    // What fraction of its own neighbourhood each animal is asking for this pass.
    for (let k = 0; k < n; k++) {
      const want = unchecked(fRem[k]);
      if (want <= 0.0) { unchecked(fR[k] = 0.0); continue; }
      let avail = 0.0;
      for (let a = unchecked(fLoI[k]); a <= unchecked(fHiI[k]); a++)
        for (let b = unchecked(fLoJ[k]); b <= unchecked(fHiJ[k]); b++)
          avail += unchecked(world.food[a * g + b]);
      unchecked(fR[k] = avail > 0.0 ? (want < avail ? want / avail : 1.0) : 0.0);
    }

    // Each animal's share, all read from the same field before any of it is withdrawn.
    let moved = 0.0;
    for (let k = 0; k < n; k++) {
      const r = unchecked(fR[k]);
      if (r <= 0.0) continue;
      let got = 0.0;
      for (let a = unchecked(fLoI[k]); a <= unchecked(fHiI[k]); a++) {
        for (let b = unchecked(fLoJ[k]); b <= unchecked(fHiJ[k]); b++) {
          const have = unchecked(world.food[a * g + b]);
          if (have <= 0.0) continue;
          const claimed = claimOn(n, a, b);
          got += have * r / (claimed > 1.0 ? claimed : 1.0);
        }
      }
      unchecked(fGot[k] += got);
      unchecked(fRem[k] -= got);
      moved += got;
    }

    /* Then take it off the plate. A cell loses `have * min(1, claimed)` however many
     * animals are on it, so the new value depends only on the cell -- but it must be
     * written exactly once, or the second writer would scale an already-reduced value.
     * The lowest-indexed claimant does it, which is a deterministic choice and not an
     * order-dependent one: every animal's share was fixed in the sweep above. */
    for (let k = 0; k < n; k++) {
      if (unchecked(fR[k]) <= 0.0) continue;
      for (let a = unchecked(fLoI[k]); a <= unchecked(fHiI[k]); a++) {
        for (let b = unchecked(fLoJ[k]); b <= unchecked(fHiJ[k]); b++) {
          if (firstClaimant(n, a, b) != k) continue;
          const cell = a * g + b;
          const have = unchecked(world.food[cell]);
          if (have <= 0.0) continue;
          const claimed = claimOn(n, a, b);
          const left = have * (1.0 - (claimed > 1.0 ? 1.0 : claimed));
          unchecked(world.food[cell] = left > 0.0 ? left : 0.0);
        }
      }
    }
    if (moved <= 1e-18) break;
  }
}

// Total fraction of cell (a,b) claimed this pass, summed over every animal reaching it.
@inline function claimOn(n: i32, a: i32, b: i32): f64 {
  let claimed = 0.0;
  for (let m = 0; m < n; m++) {
    if (unchecked(fR[m]) <= 0.0) continue;
    if (a >= unchecked(fLoI[m]) && a <= unchecked(fHiI[m])
     && b >= unchecked(fLoJ[m]) && b <= unchecked(fHiJ[m])) claimed += unchecked(fR[m]);
  }
  return claimed;
}
@inline function firstClaimant(n: i32, a: i32, b: i32): i32 {
  for (let m = 0; m < n; m++) {
    if (unchecked(fR[m]) <= 0.0) continue;
    if (a >= unchecked(fLoI[m]) && a <= unchecked(fHiI[m])
     && b >= unchecked(fLoJ[m]) && b <= unchecked(fHiJ[m])) return m;
  }
  return -1;
}

export function stepAll(n: i32): void {
  for (let i = 0; i < n; i++) {
    const count = worms.length;
    feedingCapacity(count);
    for (let k = 0; k < count; k++) unchecked(fWant[k] = unchecked(worms[k]).prepareStep());
    settleFeeding(count);
    for (let k = 0; k < count; k++) unchecked(worms[k]).finishStep(unchecked(fGot[k]));
    // The plate is shared, so it advances once per step and not once per animal.
    world.stepFields(G.DT);
  }
}
export function ptrAct(w: i32): usize { return changetype<usize>(byId(w).act); }
export function ptrV(w: i32): usize { return changetype<usize>(byId(w).V); }
export function ptrTension(w: i32): usize { return changetype<usize>(byId(w).mTen); }
export function getPumpRate(w: i32): f64 { return byId(w).phRate; }
export function getPumping(w: i32): f64 { return byId(w).phPumping ? 1.0 : 0.0; }
export function getLumen(w: i32): f64 { return byId(w).lumen; }
export function getEaten(w: i32): f64 { return byId(w).eaten; }
// What reached the intestine, as opposed to what left the plate. The two differ by
// whatever is still in the lumen, and an M4-ablated animal is the case that separates
// them: it captures until full, then starves with its mouth loaded.
export function getIngested(w: i32): f64 { return byId(w).ingested; }
export function getEggsHeld(w: i32): f64 { return byId(w).eglEggs; }
export function getEggsLaid(w: i32): f64 { return <f64>byId(w).eglLaid; }
export function getVulvalMuscle(w: i32): f64 { return byId(w).eglVm; }
export function getEglActive(w: i32): f64 { return byId(w).eglInPhase ? 1.0 : 0.0; }
export function getEglResource(w: i32): f64 { return byId(w).eglResource; }
export function eggCount(): i32 { return world.nEggs; }
/* Eggs the plate refused because it was full. Never silently non-zero: anything reading
 * eggs as a record of what a population did should check this before believing it. */
export function eggsDropped(): i32 { return world.eggsDropped; }
export function eggParent(i: i32): i32 {
  return i >= 0 && i < world.nEggs ? unchecked(world.eggParent[i]) : -1;
}
export function eggTime(i: i32): f64 {
  return i >= 0 && i < world.nEggs ? unchecked(world.eggT[i]) : NaN;
}
export function eggGene(i: i32, slot: i32): f64 {
  if (i < 0 || i >= world.nEggs || slot < 0 || slot >= G.N_GENES) return NaN;
  return unchecked(world.eggGene[i * G.N_GENES + slot]);
}
/* Hatch an egg into an animal, and take it off the plate. Returns the new worm's id, or
 * -1 if there is no such egg.
 *
 * The animal starts where the egg was lying and carries the genome the egg carries --
 * which is a *copy* taken at laying, so a parent that has since been culled or had its own
 * genes changed cannot affect what hatches. Mutation is deliberately not done here: the
 * runtime provides the mechanism and the caller owns the policy, so a hatchling starts as
 * a clone of its parent and whatever is driving the population mutates it with setGene. */
export function hatchEgg(i: i32, seed: i32, heading: f64): i32 {
  if (i < 0 || i >= world.nEggs) return -1;
  const x = unchecked(world.eggX[i]), y = unchecked(world.eggY[i]);
  const id = createWorm(seed, x, y, heading);
  const wm = wormById.get(id);
  const base = i * G.N_GENES;
  for (let g = 0; g < G.N_GENES; g++) {
    unchecked(wm.genes[g] = unchecked(world.eggGene[base + g]));
  }
  world.takeEgg(i);
  return id;
}
export function ptrEggX(): usize { return changetype<usize>(world.eggX); }
export function ptrEggY(): usize { return changetype<usize>(world.eggY); }
export function getGateForward(w: i32): f64 { return byId(w).goingForward ? 1.0 : 0.0; }
export function getOmega(w: i32): f64 { return byId(w).omega * byId(w).omegaSign; }
export function getSensed(w: i32, which: i32): f64 {
  const wm = byId(w);
  if (which == 0) return wm.sensedAtt;
  if (which == 1) return wm.sensedT;
  if (which == 2) return wm.sensedO2;
  if (which == 3) return wm.sensedFood;
  if (which == 4) return wm.touchA + wm.touchP;
  if (which == 5) return wm.sensedRep;
  if (which == 6) return 0.5 * (wm.availA + wm.availP);
  if (which == 7) return wm.modSER;
  if (which == 8) return wm.modDA;
  return 0.0;
}
export function pokeWorm(w: i32, anterior: i32, strength: f64): void {
  const wm = byId(w);
  if (anterior != 0) wm.pokeA += strength; else wm.pokeP += strength;
}
export function ptrNodesX(w: i32): usize { return changetype<usize>(byId(w).nodesX); }
export function ptrNodesY(w: i32): usize { return changetype<usize>(byId(w).nodesY); }
export function ptrKappa(w: i32): usize { return changetype<usize>(byId(w).kappa); }
export function ptrTheta(w: i32): usize { return changetype<usize>(byId(w).theta); }
export function ptrFood(): usize { return changetype<usize>(world.food); }
export function ptrAttractant(): usize { return changetype<usize>(world.attractant); }
export function ptrRepellent(): usize { return changetype<usize>(world.repellent); }
export function ptrO2(): usize { return changetype<usize>(world.o2); }

export function getX(w: i32): f64 { return byId(w).bx; }
export function getY(w: i32): f64 { return byId(w).by; }
export function getTime(w: i32): f64 { return byId(w).t; }
export function sampleFood(x: f64, y: f64): f64 { return world.sample(world.food, x, y); }
export function sampleO2(x: f64, y: f64): f64 { return world.oxygen(x, y); }
