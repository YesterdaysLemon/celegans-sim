declare namespace __AdaptedExports {
  /** Exported memory */
  export const memory: WebAssembly.Memory;
  // Exported runtime interface
  export function __new(size: number, id: number): number;
  export function __pin(ptr: number): number;
  export function __unpin(ptr: number): void;
  export function __collect(): void;
  export const __rtti_base: number;
  /**
   * assembly/index/alloc
   * @param nbytes `i32`
   * @returns `usize`
   */
  export function alloc(nbytes: number): number;
  /**
   * assembly/index/setPayload
   * @param ptr `usize`
   */
  export function setPayload(ptr: number): void;
  /**
   * assembly/index/initWorld
   */
  export function initWorld(): void;
  /**
   * assembly/index/addFood
   * @param x `f64`
   * @param y `f64`
   * @param r `f64`
   * @param d `f64`
   * @param att `f64`
   * @param ls `f64`
   */
  export function addFood(x: number, y: number, r: number, d: number, att: number, ls: number): void;
  /**
   * assembly/index/foodPatchCount
   * @returns `i32`
   */
  export function foodPatchCount(): number;
  /**
   * assembly/index/foodPatchesRefused
   * @returns `i32`
   */
  export function foodPatchesRefused(): number;
  /**
   * assembly/index/addRepellent
   * @param x `f64`
   * @param y `f64`
   * @param s `f64`
   * @param ls `f64`
   */
  export function addRepellent(x: number, y: number, s: number, ls: number): void;
  /**
   * assembly/index/createWorm
   * @param seed `i32`
   * @param x `f64`
   * @param y `f64`
   * @param heading `f64`
   * @returns `i32`
   */
  export function createWorm(seed: number, x: number, y: number, heading: number): number;
  /**
   * assembly/index/wormCount
   * @returns `i32`
   */
  export function wormCount(): number;
  /**
   * assembly/index/wormIdAt
   * @param k `i32`
   * @returns `i32`
   */
  export function wormIdAt(k: number): number;
  /**
   * assembly/index/hasWorm
   * @param id `i32`
   * @returns `i32`
   */
  export function hasWorm(id: number): number;
  /**
   * assembly/index/geneCount
   * @returns `i32`
   */
  export function geneCount(): number;
  /**
   * assembly/index/setGene
   * @param w `i32`
   * @param slot `i32`
   * @param v `f64`
   */
  export function setGene(w: number, slot: number, v: number): void;
  /**
   * assembly/index/getGene
   * @param w `i32`
   * @param slot `i32`
   * @returns `f64`
   */
  export function getGene(w: number, slot: number): number;
  /**
   * assembly/index/resetGenes
   * @param w `i32`
   */
  export function resetGenes(w: number): void;
  /**
   * assembly/index/clearWorms
   */
  export function clearWorms(): void;
  /**
   * assembly/index/removeWorm
   * @param id `i32`
   * @returns `i32`
   */
  export function removeWorm(id: number): number;
  /**
   * assembly/index/popWorm
   */
  export function popWorm(): void;
  /**
   * assembly/index/resetWorld
   */
  export function resetWorld(): void;
  /**
   * assembly/index/setAblated
   * @param w `i32`
   * @param ptr `usize`
   * @param count `i32`
   */
  export function setAblated(w: number, ptr: number, count: number): void;
  /**
   * assembly/index/isAlive
   * @param w `i32`
   * @param i `i32`
   * @returns `i32`
   */
  export function isAlive(w: number, i: number): number;
  /**
   * assembly/index/setMedium
   * @param ct `f64`
   * @param cn `f64`
   */
  export function setMedium(ct: number, cn: number): void;
  /**
   * assembly/index/getMediumCT
   * @returns `f64`
   */
  export function getMediumCT(): number;
  /**
   * assembly/index/getMediumCN
   * @returns `f64`
   */
  export function getMediumCN(): number;
  /**
   * assembly/index/setMoment
   * @param w `i32`
   * @param j `i32`
   * @param v `f64`
   */
  export function setMoment(w: number, j: number, v: number): void;
  /**
   * assembly/index/stepBodyOnly
   * @param w `i32`
   * @param dt `f64`
   * @param steps `i32`
   */
  export function stepBodyOnly(w: number, dt: number, steps: number): void;
  /** assembly/index/INVARIANT_OK */
  export const INVARIANT_OK: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/INVARIANT_ANGLES_NOT_FINITE */
  export const INVARIANT_ANGLES_NOT_FINITE: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/INVARIANT_POTENTIALS_NOT_FINITE */
  export const INVARIANT_POTENTIALS_NOT_FINITE: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/INVARIANT_CURVATURE_OVER_LIMIT */
  export const INVARIANT_CURVATURE_OVER_LIMIT: {
    /** @type `i32` */
    get value(): number
  };
  /**
   * assembly/index/computeRestingPotentials
   * @returns `usize`
   */
  export function computeRestingPotentials(): number;
  /**
   * assembly/index/ptrExportedVth
   * @returns `usize`
   */
  export function ptrExportedVth(): number;
  /** assembly/index/INVARIANT_NODES_NOT_FINITE */
  export const INVARIANT_NODES_NOT_FINITE: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/INVARIANT_LEFT_THE_DISH */
  export const INVARIANT_LEFT_THE_DISH: {
    /** @type `i32` */
    get value(): number
  };
  /**
   * assembly/index/checkInvariants
   * @param w `i32`
   * @returns `i32`
   */
  export function checkInvariants(w: number): number;
  /**
   * assembly/index/setNoise
   * @param on `i32`
   */
  export function setNoise(on: number): void;
  /**
   * assembly/index/step
   * @param w `i32`
   * @param n `i32`
   */
  export function step(w: number, n: number): void;
  /**
   * assembly/index/stepAll
   * @param n `i32`
   */
  export function stepAll(n: number): void;
  /**
   * assembly/index/ptrAct
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrAct(w: number): number;
  /**
   * assembly/index/ptrV
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrV(w: number): number;
  /**
   * assembly/index/ptrTension
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrTension(w: number): number;
  /**
   * assembly/index/getPumpRate
   * @param w `i32`
   * @returns `f64`
   */
  export function getPumpRate(w: number): number;
  /**
   * assembly/index/getPumping
   * @param w `i32`
   * @returns `f64`
   */
  export function getPumping(w: number): number;
  /**
   * assembly/index/getLumen
   * @param w `i32`
   * @returns `f64`
   */
  export function getLumen(w: number): number;
  /**
   * assembly/index/getEaten
   * @param w `i32`
   * @returns `f64`
   */
  export function getEaten(w: number): number;
  /**
   * assembly/index/getIngested
   * @param w `i32`
   * @returns `f64`
   */
  export function getIngested(w: number): number;
  /**
   * assembly/index/getEggsHeld
   * @param w `i32`
   * @returns `f64`
   */
  export function getEggsHeld(w: number): number;
  /**
   * assembly/index/getEggsLaid
   * @param w `i32`
   * @returns `f64`
   */
  export function getEggsLaid(w: number): number;
  /**
   * assembly/index/getVulvalMuscle
   * @param w `i32`
   * @returns `f64`
   */
  export function getVulvalMuscle(w: number): number;
  /**
   * assembly/index/getEglActive
   * @param w `i32`
   * @returns `f64`
   */
  export function getEglActive(w: number): number;
  /**
   * assembly/index/getEglResource
   * @param w `i32`
   * @returns `f64`
   */
  export function getEglResource(w: number): number;
  /**
   * assembly/index/eggCount
   * @returns `i32`
   */
  export function eggCount(): number;
  /**
   * assembly/index/eggsDropped
   * @returns `i32`
   */
  export function eggsDropped(): number;
  /**
   * assembly/index/eggParent
   * @param i `i32`
   * @returns `i32`
   */
  export function eggParent(i: number): number;
  /**
   * assembly/index/eggTime
   * @param i `i32`
   * @returns `f64`
   */
  export function eggTime(i: number): number;
  /**
   * assembly/index/eggGene
   * @param i `i32`
   * @param slot `i32`
   * @returns `f64`
   */
  export function eggGene(i: number, slot: number): number;
  /**
   * assembly/index/hatchEgg
   * @param i `i32`
   * @param seed `i32`
   * @param heading `f64`
   * @returns `i32`
   */
  export function hatchEgg(i: number, seed: number, heading: number): number;
  /**
   * assembly/index/ptrEggX
   * @returns `usize`
   */
  export function ptrEggX(): number;
  /**
   * assembly/index/ptrEggY
   * @returns `usize`
   */
  export function ptrEggY(): number;
  /**
   * assembly/index/getGateForward
   * @param w `i32`
   * @returns `f64`
   */
  export function getGateForward(w: number): number;
  /**
   * assembly/index/getOmega
   * @param w `i32`
   * @returns `f64`
   */
  export function getOmega(w: number): number;
  /**
   * assembly/index/getSensed
   * @param w `i32`
   * @param which `i32`
   * @returns `f64`
   */
  export function getSensed(w: number, which: number): number;
  /**
   * assembly/index/pokeWorm
   * @param w `i32`
   * @param anterior `i32`
   * @param strength `f64`
   */
  export function pokeWorm(w: number, anterior: number, strength: number): void;
  /**
   * assembly/index/ptrNodesX
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrNodesX(w: number): number;
  /**
   * assembly/index/ptrNodesY
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrNodesY(w: number): number;
  /**
   * assembly/index/ptrKappa
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrKappa(w: number): number;
  /**
   * assembly/index/ptrTheta
   * @param w `i32`
   * @returns `usize`
   */
  export function ptrTheta(w: number): number;
  /**
   * assembly/index/ptrFood
   * @returns `usize`
   */
  export function ptrFood(): number;
  /**
   * assembly/index/ptrAttractant
   * @returns `usize`
   */
  export function ptrAttractant(): number;
  /**
   * assembly/index/ptrRepellent
   * @returns `usize`
   */
  export function ptrRepellent(): number;
  /**
   * assembly/index/ptrO2
   * @returns `usize`
   */
  export function ptrO2(): number;
  /**
   * assembly/index/getX
   * @param w `i32`
   * @returns `f64`
   */
  export function getX(w: number): number;
  /**
   * assembly/index/getY
   * @param w `i32`
   * @returns `f64`
   */
  export function getY(w: number): number;
  /**
   * assembly/index/getTime
   * @param w `i32`
   * @returns `f64`
   */
  export function getTime(w: number): number;
  /**
   * assembly/index/sampleFood
   * @param x `f64`
   * @param y `f64`
   * @returns `f64`
   */
  export function sampleFood(x: number, y: number): number;
  /**
   * assembly/index/sampleO2
   * @param x `f64`
   * @param y `f64`
   * @returns `f64`
   */
  export function sampleO2(x: number, y: number): number;
}
/** Instantiates the compiled WebAssembly module with the given imports. */
export declare function instantiate(module: WebAssembly.Module, imports: {
  env: unknown,
}): Promise<typeof __AdaptedExports>;
