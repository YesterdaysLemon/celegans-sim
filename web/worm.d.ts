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
   * assembly/index/clearWorms
   */
  export function clearWorms(): void;
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
