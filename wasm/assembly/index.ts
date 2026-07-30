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
 * animals eat from), and N independent Worms. That last part is why two worms in one dish
 * is nearly free -- the 302x302 matrices are anatomy, identical for every animal, so only
 * the state is duplicated.
 */

import * as G from "./model_gen";

// ---------------------------------------------------------------------------- payload --

let B: usize = 0;

export function alloc(nbytes: i32): usize { return heap.alloc(<usize>nbytes); }
export function setPayload(ptr: usize): void { B = ptr; }

@inline function m(off: usize, i: i32): f64 { return load<f64>(B + off + (<usize>i << 3)); }
@inline function mi(off: usize, i: i32): i32 { return load<i32>(B + off + (<usize>i << 2)); }

@inline function sigmoid(x: f64): f64 {
  if (x >= 0) return 1.0 / (1.0 + Math.exp(-x));
  const e = Math.exp(x);
  return e / (1.0 + e);
}
@inline function clamp(v: f64, lo: f64, hi: f64): f64 {
  return v < lo ? lo : (v > hi ? hi : v);
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
  addPatch(cx: f64, cy: f64, r: f64, density: f64, att: f64, ls: f64): void {
    for (let i = 0; i < this.g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < this.g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const dx = x - cx, dy = y - cy;
        const d = Math.sqrt(dx * dx + dy * dy);
        const inside = d <= r ? 1.0 : Math.exp(-(d - r) / ls);
        const k = i * this.g + j;
        if (density > 0.0) {
          const v = density * inside;
          if (v > unchecked(this.food[k])) unchecked(this.food[k] = v);
          // A lawn respires, and the deficit has a longer skirt than the bacteria because
          // oxygen is resupplied from the air above the agar as well as laterally.
          const o = G.WORLD_O2_DEPTH * (d <= r ? 1.0
                    : Math.exp(-(d - r) / G.WORLD_O2_LENGTH_SCALE));
          if (o > unchecked(this.o2[k])) unchecked(this.o2[k] = o);
        }
        if (att > 0.0) {
          const v = att * inside;
          if (v > unchecked(this.attractant[k])) unchecked(this.attractant[k] = v);
        }
      }
    }
  }
  addRepellent(cx: f64, cy: f64, strength: f64, ls: f64): void {
    for (let i = 0; i < this.g; i++) {
      const y = -this.extent + (<f64>i + 0.5) * this.h;
      for (let j = 0; j < this.g; j++) {
        const x = -this.extent + (<f64>j + 0.5) * this.h;
        const dx = x - cx, dy = y - cy;
        const v = strength * Math.exp(-Math.sqrt(dx * dx + dy * dy) / ls);
        const k = i * this.g + j;
        if (v > unchecked(this.repellent[k])) unchecked(this.repellent[k] = v);
      }
    }
  }
}

let world: World = new World();

// ------------------------------------------------------------------------------- worm --

class Worm {
  rng: Rng = new Rng(0);
  bx: f64 = 0.0; by: f64 = 0.0;
  theta: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  qdot: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 2);
  ux: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  uy: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  nxv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  nyv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS);
  Dm: StaticArray<f64> = new StaticArray<f64>((G.N_LINKS + 2) * (G.N_LINKS + 2));
  Qv: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 2);
  Pm: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
  Qm: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
  As: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
  Bs: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS * G.N_LINKS);
  nodesX: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  nodesY: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  contactX: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  contactY: StaticArray<f64> = new StaticArray<f64>(G.N_LINKS + 1);
  kappa: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);
  moment: StaticArray<f64> = new StaticArray<f64>(G.N_JOINTS);
  cT: f64 = G.MED_AGAR_CT; cN: f64 = G.MED_AGAR_CN;
  t: f64 = 0.0;

  constructor(seed: u64, x: f64, y: f64, heading: f64) {
    this.rng = new Rng(seed);
    this.bx = x; this.by = y;
    for (let i = 0; i < G.N_LINKS; i++) unchecked(this.theta[i] = heading);
    this.updateNodes();
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
    const D = this.Dm;
    for (let i = 0; i < N * N; i++) unchecked(D[i] = 0.0);

    for (let i = 0; i < n; i++) {
      const th = unchecked(this.theta[i]);
      const c = Math.cos(th), s = Math.sin(th);
      unchecked(this.ux[i] = c); unchecked(this.uy[i] = s);
      unchecked(this.nxv[i] = -s); unchecked(this.nyv[i] = c);
    }
    // P[m,k] = n_m . u_k,  Q[m,k] = n_m . n_k, and the two masked copies.
    for (let mm = 0; mm < n; mm++) {
      const nx = unchecked(this.nxv[mm]), ny = unchecked(this.nyv[mm]);
      for (let k = 0; k < n; k++) {
        const p = nx * unchecked(this.ux[k]) + ny * unchecked(this.uy[k]);
        const q = nx * unchecked(this.nxv[k]) + ny * unchecked(this.nyv[k]);
        const idx = mm * n + k;
        unchecked(this.Pm[idx] = p); unchecked(this.Qm[idx] = q);
        // The rotational block multiplies two lever arms that must *share* one factor of
        // rho_k between them, so it uses the square-root mask -- (A A^T)[m,p] then sums
        // rho_k rather than rho_k^2.
        unchecked(this.As[idx] = p * m(G.OFF_body_mask_sqrt, idx));
        unchecked(this.Bs[idx] = q * m(G.OFF_body_mask_sqrt, idx));
      }
    }

    // translation / translation
    let txx: f64 = 0.0, txy: f64 = 0.0, tyy: f64 = 0.0;
    for (let k = 0; k < n; k++) {
      const rho = m(G.OFF_body_rho, k);
      const ux = unchecked(this.ux[k]), uy = unchecked(this.uy[k]);
      const nx = unchecked(this.nxv[k]), ny = unchecked(this.nyv[k]);
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
        const a = unchecked(this.Pm[idx]) * mr;
        const b2 = unchecked(this.Qm[idx]) * mr;
        cx += cT * a * unchecked(this.ux[k]) + cN * b2 * unchecked(this.nxv[k]);
        cy += cT * a * unchecked(this.uy[k]) + cN * b2 * unchecked(this.nyv[k]);
      }
      const rho = m(G.OFF_body_rho, mm);
      cx = l2 * (cx + 0.5 * cN * rho * unchecked(this.nxv[mm]));
      cy = l2 * (cy + 0.5 * cN * rho * unchecked(this.nyv[mm]));
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
          acc += cT * unchecked(this.As[a * n + k]) * unchecked(this.As[b2 * n + k])
               + cN * unchecked(this.Bs[a * n + k]) * unchecked(this.Bs[b2 * n + k]);
        }
        acc += cN * 0.5 * unchecked(this.Qm[a * n + b2]) * m(G.OFF_body_rho_max_off, a * n + b2);
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
    const Q = this.Qv;
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
      unchecked(Q[2 + mm] += l * (unchecked(this.nxv[mm]) * sx + unchecked(this.nyv[mm]) * sy));
    }

    for (let a = 0; a < n; a++) {
      for (let b2 = 0; b2 < n; b2++) {
        const idx = a * n + b2;
        unchecked(this.Dm[(2 + a) * N + (2 + b2)] +=
          m(G.OFF_body_B_mat, idx) + dt * m(G.OFF_body_K_mat, idx));
      }
    }
    if (!solveInPlace(this.Dm, Q, N)) return;
    for (let i = 0; i < N; i++) unchecked(this.qdot[i] = unchecked(Q[i]));
    this.bx += unchecked(Q[0]) * dt;
    this.by += unchecked(Q[1]) * dt;
    for (let i = 0; i < n; i++) unchecked(this.theta[i] += unchecked(Q[2 + i]) * dt);
    this.updateNodes();
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

let worms: Worm[] = [];

// -------------------------------------------------------------------------- exported --

export function initWorld(): void { world = new World(); }
export function addFood(x: f64, y: f64, r: f64, d: f64, att: f64, ls: f64): void {
  world.addPatch(x, y, r, d, att, ls);
}
export function addRepellent(x: f64, y: f64, s: f64, ls: f64): void {
  world.addRepellent(x, y, s, ls);
}
export function createWorm(seed: i32, x: f64, y: f64, heading: f64): i32 {
  worms.push(new Worm(<u64>seed, x, y, heading));
  return worms.length - 1;
}
export function wormCount(): i32 { return worms.length; }
export function setMedium(ct: f64, cn: f64): void {
  for (let i = 0; i < worms.length; i++) { worms[i].cT = ct; worms[i].cN = cn; }
}

// Drive the body directly, which is what the conformance test for the mechanics needs:
// a prescribed moment, no biology, the same numbers on both sides.
export function setMoment(w: i32, j: i32, v: f64): void { unchecked(worms[w].moment[j] = v); }
export function stepBodyOnly(w: i32, dt: f64, steps: i32): void {
  const wm = worms[w];
  for (let i = 0; i < steps; i++) { wm.contact(); wm.stepBody(dt); wm.t += dt; }
}

export function ptrNodesX(w: i32): usize { return changetype<usize>(worms[w].nodesX); }
export function ptrNodesY(w: i32): usize { return changetype<usize>(worms[w].nodesY); }
export function ptrKappa(w: i32): usize { return changetype<usize>(worms[w].kappa); }
export function ptrTheta(w: i32): usize { return changetype<usize>(worms[w].theta); }
export function ptrFood(): usize { return changetype<usize>(world.food); }
export function ptrAttractant(): usize { return changetype<usize>(world.attractant); }
export function ptrRepellent(): usize { return changetype<usize>(world.repellent); }
export function ptrO2(): usize { return changetype<usize>(world.o2); }

export function getX(w: i32): f64 { return worms[w].bx; }
export function getY(w: i32): f64 { return worms[w].by; }
export function getTime(w: i32): f64 { return worms[w].t; }
export function sampleFood(x: f64, y: f64): f64 { return world.sample(world.food, x, y); }
export function sampleO2(x: f64, y: f64): f64 { return world.oxygen(x, y); }
