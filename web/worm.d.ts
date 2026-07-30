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
