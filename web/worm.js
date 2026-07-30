export async function instantiate(module, imports = {}) {
  const adaptedImports = {
    env: Object.setPrototypeOf({
      abort(message, fileName, lineNumber, columnNumber) {
        // ~lib/builtins/abort(~lib/string/String | null?, ~lib/string/String | null?, u32?, u32?) => void
        message = __liftString(message >>> 0);
        fileName = __liftString(fileName >>> 0);
        lineNumber = lineNumber >>> 0;
        columnNumber = columnNumber >>> 0;
        (() => {
          // @external.js
          throw Error(`${message} in ${fileName}:${lineNumber}:${columnNumber}`);
        })();
      },
    }, Object.assign(Object.create(globalThis), imports.env || {})),
  };
  const { exports } = await WebAssembly.instantiate(module, adaptedImports);
  const memory = exports.memory || imports.env.memory;
  const adaptedExports = Object.setPrototypeOf({
    alloc(nbytes) {
      // assembly/index/alloc(i32) => usize
      return exports.alloc(nbytes) >>> 0;
    },
    ptrNodesX(w) {
      // assembly/index/ptrNodesX(i32) => usize
      return exports.ptrNodesX(w) >>> 0;
    },
    ptrNodesY(w) {
      // assembly/index/ptrNodesY(i32) => usize
      return exports.ptrNodesY(w) >>> 0;
    },
    ptrKappa(w) {
      // assembly/index/ptrKappa(i32) => usize
      return exports.ptrKappa(w) >>> 0;
    },
    ptrTheta(w) {
      // assembly/index/ptrTheta(i32) => usize
      return exports.ptrTheta(w) >>> 0;
    },
    ptrFood() {
      // assembly/index/ptrFood() => usize
      return exports.ptrFood() >>> 0;
    },
    ptrAttractant() {
      // assembly/index/ptrAttractant() => usize
      return exports.ptrAttractant() >>> 0;
    },
    ptrRepellent() {
      // assembly/index/ptrRepellent() => usize
      return exports.ptrRepellent() >>> 0;
    },
    ptrO2() {
      // assembly/index/ptrO2() => usize
      return exports.ptrO2() >>> 0;
    },
  }, exports);
  function __liftString(pointer) {
    if (!pointer) return null;
    const
      end = pointer + new Uint32Array(memory.buffer)[pointer - 4 >>> 2] >>> 1,
      memoryU16 = new Uint16Array(memory.buffer);
    let
      start = pointer >>> 1,
      string = "";
    while (end - start > 1024) string += String.fromCharCode(...memoryU16.subarray(start, start += 1024));
    return string + String.fromCharCode(...memoryU16.subarray(start, end));
  }
  return adaptedExports;
}
