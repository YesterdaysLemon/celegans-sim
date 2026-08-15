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
   * assembly/index/depositFood
   * @param x `f64`
   * @param y `f64`
   * @param r `f64`
   * @param amount `f64`
   * @returns `f64`
   */
  export function depositFood(x: number, y: number, r: number, amount: number): number;
  /**
   * assembly/index/depositRepellent
   * @param x `f64`
   * @param y `f64`
   * @param r `f64`
   * @param amount `f64`
   * @returns `f64`
   */
  export function depositRepellent(x: number, y: number, r: number, amount: number): number;
  /**
   * assembly/index/driftFields
   * @param dx `f64`
   * @param dy `f64`
   */
  export function driftFields(dx: number, dy: number): void;
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
   * assembly/index/checkBalance
   * @returns `f64`
   */
  export function checkBalance(): number;
  /** assembly/index/WFAM_SYN */
  export const WFAM_SYN: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/WFAM_GAP */
  export const WFAM_GAP: {
    /** @type `i32` */
    get value(): number
  };
  /** assembly/index/WFAM_MUS */
  export const WFAM_MUS: {
    /** @type `i32` */
    get value(): number
  };
  /**
   * assembly/index/weightCount
   * @param fam `i32`
   * @returns `i32`
   */
  export function weightCount(fam: number): number;
  /**
   * assembly/index/getWeight
   * @param w `i32`
   * @param fam `i32`
   * @param k `i32`
   * @returns `f64`
   */
  export function getWeight(w: number, fam: number, k: number): number;
  /**
   * assembly/index/hasOwnWeights
   * @param w `i32`
   * @returns `i32`
   */
  export function hasOwnWeights(w: number): number;
  /**
   * assembly/index/getWeight2
   * @param w `i32`
   * @param k `i32`
   * @returns `f64`
   */
  export function getWeight2(w: number, k: number): number;
  /**
   * assembly/index/gapMirror
   * @param k `i32`
   * @returns `i32`
   */
  export function gapMirror(k: number): number;
  /**
   * assembly/index/getVth
   * @param w `i32`
   * @param i `i32`
   * @returns `f64`
   */
  export function getVth(w: number, i: number): number;
  /**
   * assembly/index/forceLay
   * @param w `i32`
   * @returns `i32`
   */
  export function forceLay(w: number): number;
  /**
   * assembly/index/scaleWeight
   * @param w `i32`
   * @param fam `i32`
   * @param k `i32`
   * @param factor `f64`
   * @returns `f64`
   */
  export function scaleWeight(w: number, fam: number, k: number, factor: number): number;
  /**
   * assembly/index/developWorm
   * @param w `i32`
   * @returns `f64`
   */
  export function developWorm(w: number): number;
  /**
   * assembly/index/setHeadCascade
   * @param w `i32`
   * @param stages `i32`
   * @param stageDecay `f64`
   * @param delayN `i32`
   * @param stageTau `f64`
   */
  export function setHeadCascade(w: number, stages: number, stageDecay: number, delayN: number, stageTau: number): void;
  /**
   * assembly/index/setAminePath
   * @param w `i32`
   * @param loadGain `f64`
   * @param loadHalf `f64`
   * @param headLag `f64`
   * @param reachBlend `f64`
   * @param muscleRate `f64`
   */
  export function setAminePath(w: number, loadGain: number, loadHalf: number, headLag: number, reachBlend: number, muscleRate: number): void;
  /**
   * assembly/index/setMetabolism
   * @param w `i32`
   * @param cap `f64`
   * @param basal `f64`
   * @param work `f64`
   * @param floor `f64`
   * @param fadeFrac `f64`
   * @param initialFrac `f64`
   */
  export function setMetabolism(w: number, cap: number, basal: number, work: number, floor: number, fadeFrac: number, initialFrac: number): void;
  /**
   * assembly/index/getEnergy
   * @param w `i32`
   * @returns `f64`
   */
  export function getEnergy(w: number): number;
  /**
   * assembly/index/getMetabFade
   * @param w `i32`
   * @returns `f64`
   */
  export function getMetabFade(w: number): number;
  /**
   * assembly/index/getDragPower
   * @param w `i32`
   * @returns `f64`
   */
  export function getDragPower(w: number): number;
  /**
   * assembly/index/setMorphology
   * @param w `i32`
   * @param st0 `f64`
   * @param st1 `f64`
   * @param st2 `f64`
   * @param st3 `f64`
   * @param wd0 `f64`
   * @param wd1 `f64`
   * @param wd2 `f64`
   * @param wd3 `f64`
   * @param mu0 `f64`
   * @param mu1 `f64`
   * @param mu2 `f64`
   * @param mu3 `f64`
   */
  export function setMorphology(w: number, st0: number, st1: number, st2: number, st3: number, wd0: number, wd1: number, wd2: number, wd3: number, mu0: number, mu1: number, mu2: number, mu3: number): void;
  /**
   * assembly/index/setDevelopment
   * @param w `i32`
   * @param s `f64`
   */
  export function setDevelopment(w: number, s: number): void;
  /**
   * assembly/index/getDevelopment
   * @param w `i32`
   * @returns `f64`
   */
  export function getDevelopment(w: number): number;
  /**
   * assembly/index/clearMorphology
   * @param w `i32`
   */
  export function clearMorphology(w: number): void;
  /**
   * assembly/index/hasOwnMorphology
   * @param w `i32`
   * @returns `i32`
   */
  export function hasOwnMorphology(w: number): number;
  /**
   * assembly/index/getMorph
   * @param w `i32`
   * @param i `i32`
   * @returns `f64`
   */
  export function getMorph(w: number, i: number): number;
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
