/* What an animal costs, measured rather than asserted.
 *
 * This file exists because three separate places in this repository stated that a second
 * animal costs "a few kB" and it cost 372 kB -- off by a hundred, in the claim the whole
 * evolution plan rested on ("a population is no longer an architectural problem, it is a
 * throughput one"). Nobody had lied; nobody had measured. That is the failure mode a
 * comment cannot fix, because the comment *was* the failure. See #33.
 *
 * So the number is measured here, from the runtime's own exports and from the runtime's
 * own source, and the documents that quote it are checked for quoting this one. A drift in
 * either direction -- an array added to `class Worm`, or a document left behind -- goes
 * red.
 *
 *     node wasm/memory.mjs
 *
 * Needs only web/worm.wasm and web/worm.model, so it costs a second and runs on every push.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

/* The figures under test. Every one of these was measured by this file; none was estimated.
 *
 * PER_WORM_MEASURED is the allocator's real per-animal stride, block headers and 16-byte
 * granularity included. PER_WORM_DECLARED is the sum of the StaticArray dimensions in
 * `class Worm`; the difference between them is that overhead, 60 bytes an array.
 *
 * If AssemblyScript changes its object layout these move, and this check is meant to go red
 * when they do -- the point is that the number in the documents is a measurement of the
 * runtime that shipped, not a folk memory of one that did.
 */
const PER_WORM_MEASURED = 239952;   // bytes, ptrV stride between consecutive animals
const PER_WORM_DECLARED = 238486;   // bytes, summed StaticArray dimensions in class Worm
const SHARED_SCRATCH = 140776;      // bytes, module-level per-step scratch, paid once
const N_WORM_ARRAYS = 23;
const N_SCRATCH_ARRAYS = 37;

/* Documents that quote a per-animal memory figure. Each has to contain the measured byte
 * count *and* the rounded kB figure, so a document cannot be half-updated, and must not
 * still contain the phrases this whole issue was about.
 *
 * FORBIDDEN is deliberately literal, which means a document cannot quote the old claim even
 * to disown it -- say "a few kilobytes" in the history sentence instead. A blunt string test
 * that is occasionally inconvenient is worth more here than a clever one nobody can predict.
 *
 * A file appears here because it makes the claim, not because it mentions memory. Adding a
 * fifth place that makes the claim without adding it here is the drift this cannot catch,
 * which is why the runtime source is on the list: any new claim is downstream of that one.
 *
 * One further hole, stated rather than papered over: the research log is prose and sits
 * outside every workflow path filter, so an edit to *it alone* schedules nothing and this
 * check does not run. A drift there is caught by the next commit that touches wasm/ or
 * web/, which is later than it should be and blames the wrong change. See NO_CI_NEEDED in
 * tests/test_ci_policy.py for why that trade was taken.
 *
 * The first entry used to be NEXT.md, which is where the claim was made while NEXT.md was
 * also the research log. It is now docs/research-log/next-history-through-2026-08-04.md,
 * byte-for-byte the same document under a name that says what it is; the claim travelled
 * with the text and this list follows the claim rather than the filename. The live NEXT.md
 * is a roadmap and makes no memory claim, so listing it here would assert against a
 * document that has no business carrying the figure.
 */
const QUOTES = ['docs/research-log/next-history-through-2026-08-04.md',
                'web/local.js', 'wasm/README.md', 'wasm/assembly/index.ts'];
const FORBIDDEN = /a few kB|a few kb|nearly free/;

const results = [];
function report(name, ok, detail) {
  results.push(ok);
  console.log(`\n${name}`);
  if (detail) console.log(detail);
  console.log(ok ? '  PASS' : '  FAIL');
}

for (const [file, how] of [
  ['web/worm.wasm', 'cd wasm && npx asc assembly/index.ts --target release'],
  ['web/worm.model', 'PYTHONPATH=. python tools/export_model.py'],
]) {
  if (!fs.existsSync(at(file))) {
    console.error(`Missing ${file}; generate it with: ${how}`);
    process.exit(2);
  }
}

// ------------------------------------------------------------------ the runtime source --
/* Read the dimensions out of the source rather than hard-coding them a second time: the
 * numbers above are the claim, and the source is the thing the claim is about. */
/* Line endings are normalised on the way in, and the reason is a real failure rather than
 * defensive habit. Git for Windows checks out with `core.autocrlf=true` by default, so
 * index.ts arrives CRLF; the class-body scan below looks for a literal '\n}\n', which
 * cannot match '\n}\r\n', so classEnd came back -1 and this file exited 2 with
 * "cannot find class Worm in wasm/assembly/index.ts".
 *
 * That message is the interesting part. classStart *did* match -- '\nclass Worm {' finds
 * the \n of a \r\n quite happily -- so the diagnostic accused the runtime source of having
 * lost a class it had not lost, on a platform where every check downstream of this one
 * would then not run. A parser that reports the wrong subject is worse than one that
 * crashes, and this is the file whose whole point is that a claim nobody reads goes stale.
 *
 * Normalising once here keeps every literal-newline pattern below platform-independent.
 * Nothing downstream cares about \r: the constant regex uses \s*, and the document checks
 * are substring and \s-based. The .ts files themselves are not touched -- this is a
 * reader-side fix, and the repository stores LF. */
const readSource = (...parts) =>
  fs.readFileSync(at(...parts), 'utf8').replace(/\r\n/g, '\n');
const src = readSource('wasm', 'assembly', 'index.ts');
const gen = readSource('wasm', 'assembly', 'model_gen.ts');

const consts = {};
for (const m of gen.matchAll(/export const (\w+):\s*(?:i32|f64)\s*=\s*([-\d.]+)/g)) {
  consts[m[1]] = Number(m[2]);
}
const WIDTH = { f64: 8, f32: 4, i32: 4, u32: 4, u8: 1, i8: 1 };

// `class Worm {` up to the first line that is a lone closing brace: the class body.
const classStart = src.indexOf('\nclass Worm {');
const classEnd = src.indexOf('\n}\n', classStart);
if (classStart < 0 || classEnd < 0) {
  console.error('cannot find class Worm in wasm/assembly/index.ts');
  process.exit(2);
}
const classBody = src.slice(classStart, classEnd);

function dims(expr) {
  // Dimensions are written in terms of the generated constants, so substitute and evaluate.
  const substituted = expr.replace(/G\.(\w+)/g, (_, k) => {
    if (!(k in consts)) throw new Error(`unknown constant G.${k}`);
    return String(consts[k]);
  });
  if (!/^[\d\s+*()-]+$/.test(substituted)) throw new Error(`unsafe dimension "${expr}"`);
  return Function(`"use strict"; return (${substituted});`)();
}

function arrays(text, declPattern) {
  const out = [];
  for (const m of text.matchAll(declPattern)) {
    const [, name, ty, expr] = m;
    const n = dims(expr);
    if (n === 0) continue;                       // the feeding scratch, grown on demand
    out.push({ name, ty, n, bytes: n * WIDTH[ty] });
  }
  return out;
}

const wormArrays = arrays(
  classBody, /^ {2}(\w+): StaticArray<(\w+)> = new StaticArray<\w+>\((.*)\);$/gm);
const scratchArrays = arrays(
  src, /^let (\w+): StaticArray<(\w+)> = new StaticArray<\w+>\((.*)\);$/gm);

const declared = wormArrays.reduce((s, a) => s + a.bytes, 0);
const scratch = scratchArrays.reduce((s, a) => s + a.bytes, 0);

{
  const biggest = [...wormArrays].sort((a, b) => b.bytes - a.bytes).slice(0, 3);
  const ok = declared === PER_WORM_DECLARED && wormArrays.length === N_WORM_ARRAYS;
  report(
    `DECLARED -- ${wormArrays.length} StaticArrays in class Worm`,
    ok,
    `  summed dimensions             ${declared.toLocaleString()} B ` +
    `(${(declared / 1024).toFixed(1)} kB), documented ${PER_WORM_DECLARED.toLocaleString()} B\n` +
    `  arrays                        ${wormArrays.length}, documented ${N_WORM_ARRAYS}\n` +
    `  largest                       ` +
    biggest.map((a) => `${a.name} ${a.bytes.toLocaleString()} B ` +
      `(${(100 * a.bytes / declared).toFixed(0)}%)`).join(', '),
  );
}

{
  const ok = scratch === SHARED_SCRATCH && scratchArrays.length === N_SCRATCH_ARRAYS;
  // The saving is only a saving if the scratch is genuinely shared -- one copy at module
  // level, not one per animal. A name in both places would mean it had been copied back.
  const wormNames = new Set(wormArrays.map((a) => a.name));
  const duplicated = scratchArrays.filter((a) => wormNames.has(a.name));
  report(
    `SHARED SCRATCH -- ${scratchArrays.length} module-level arrays, paid once`,
    ok && duplicated.length === 0,
    `  summed dimensions             ${scratch.toLocaleString()} B ` +
    `(${(scratch / 1024).toFixed(1)} kB), documented ${SHARED_SCRATCH.toLocaleString()} B\n` +
    `  arrays                        ${scratchArrays.length}, documented ${N_SCRATCH_ARRAYS}\n` +
    `  also declared per-worm        ${duplicated.length}` +
    (duplicated.length ? `  [${duplicated.map((a) => a.name).join(', ')}]` : ''),
  );
}

/* Nothing per-animal is written and never read.
 *
 * `qdot` was 416 bytes an animal that the runtime filled every step and nobody ever looked
 * at -- dead since the port, and invisible to every behavioural check by construction,
 * because a value nothing reads cannot change a result. A scan is the only thing that finds
 * that class of waste, so here is the scan.
 *
 * "Read" means: mentioned as a whole array -- passed to a function, or handed to
 * `changetype` for an exported pointer -- or indexed anywhere that is not the bare
 * left-hand side of `=`. A compound assignment counts as a read, because `+=` loads before
 * it stores.
 *
 * Comments and the declarations themselves are stripped first, and that is not tidiness:
 * without it every array reads itself. A declaration mentions its own name, and the first
 * draft of this check passed on a deliberately reinstated `qdot` for exactly that reason --
 * the scan found `qdot:` in `qdot: StaticArray<f64> = ...` and called it a use. The comment
 * block above this file's scratch declarations names half of them in prose, which would
 * have done the same. Watched failing on both.
 */
{
  const scan = src
    .replace(/\/\*[\s\S]*?\*\//g, ' ')                        // block comments
    .replace(/(^|[^:])\/\/.*$/gm, '$1')                       // line comments
    .replace(/^\s*\w+: StaticArray<\w+> = new StaticArray<\w+>\(.*\);$/gm, '')
    .replace(/^let \w+: StaticArray<\w+> = new StaticArray<\w+>\(.*\);$/gm, '');

  const dead = [];
  for (const [group, list] of [['.', wormArrays], ['', scratchArrays]]) {
    for (const a of list) {
      // Worm fields are always reached through a receiver (`this.`, `wm.`, `byId(w).`), so
      // requiring the dot keeps a same-named local from standing in for a use. Module-level
      // scratch is always bare.
      const prefix = group === '.' ? '\\.' : '\\b';
      let read = false;
      for (const use of scan.matchAll(new RegExp(`${prefix}${a.name}\\b(\\s*\\[)?`, 'g'))) {
        if (!use[1]) { read = true; break; }       // the whole array, passed or exported
        let depth = 0, k = use.index + use[0].length - 1;
        for (; k < scan.length; k++) {
          if (scan[k] === '[') depth++;
          else if (scan[k] === ']' && --depth === 0) break;
        }
        if (!/^\s*=[^=]/.test(scan.slice(k + 1, k + 4))) { read = true; break; }
      }
      if (!read) dead.push(a);
    }
  }
  report(
    'NOTHING IS WRITE-ONLY -- every array is read somewhere',
    dead.length === 0,
    `  arrays scanned                ${wormArrays.length + scratchArrays.length}\n` +
    `  written and never read        ${dead.length}` +
    (dead.length
      ? `  [${dead.map((a) => `${a.name} ${a.bytes} B`).join(', ')}]\n` +
        '  A write-only array is pure cost, and no behavioural check can see it.'
      : ''),
  );
}

// ------------------------------------------------------------------------ the runtime ---
const modelBuf = fs.readFileSync(at('web', 'worm.model'));
const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
const headLen = dv.getUint32(8, true);
const payload = modelBuf.subarray(12 + headLen);
const compiled = new WebAssembly.Module(wasmBuf);

function engine() {
  const E = new WebAssembly.Instance(compiled, {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  return E;
}

/* The measurement. `ptrV(id)` is the runtime's own address for animal `id`'s membrane
 * potentials, so the gap between two consecutively created animals is exactly what the
 * allocator handed out for one Worm -- every array, every block header, every byte of
 * 16-byte rounding.
 *
 * The median, not the mean, because a handful of the gaps are not per-worm cost at all: the
 * `worms` backing array and the id Map are reallocated as the population grows, and the
 * heap itself is grown by doubling, so a few strides carry a megabyte of somebody else's
 * business. Those are the outliers; the mode of the rest is the per-worm figure and it is
 * dead flat.
 *
 * `memory.buffer.byteLength` is checked too, and separately, because it answers the
 * question a browser actually asks -- how much did the tab grow -- but it answers it
 * loosely: WebAssembly heaps grow in pages and this one grows by doubling, so it can only
 * bound the per-animal cost, not measure it. Both are here because the loose one is the one
 * a reader will believe and the tight one is the one that can be asserted.
 */
const N = 64;
{
  const E = engine();
  const ids = [];
  for (let i = 0; i < N; i++) ids.push(E.createWorm(1000 + i, 0.0, 0.0, 0.0));
  const ptrs = ids.map((id) => E.ptrV(id));
  const strides = [];
  for (let i = 1; i < ptrs.length; i++) strides.push(ptrs[i] - ptrs[i - 1]);
  const sorted = [...strides].sort((a, b) => a - b);
  const median = sorted[sorted.length >> 1];
  const clean = strides.filter((s) => Math.abs(s - median) < 4096).length;

  const overhead = median - declared;
  // Consistent with per-object bookkeeping rather than with an array having come back:
  // 16-byte block headers plus up to 15 bytes of rounding on each array, plus the Worm
  // object's own fields. The smallest array that could hide in here is `genes` at 120 B.
  const plausible = overhead > 0 && overhead < 64 * wormArrays.length;

  report(
    `MEASURED -- ptrV stride across ${N} animals`,
    median === PER_WORM_MEASURED && plausible,
    `  per animal                    ${median.toLocaleString()} B ` +
    `(${(median / 1024).toFixed(1)} kB), documented ${PER_WORM_MEASURED.toLocaleString()} B\n` +
    `  strides agreeing with it      ${clean} of ${strides.length}   ` +
    `(the rest are the population array and the heap growing)\n` +
    `  allocator overhead            ${overhead.toLocaleString()} B over the declared ` +
    `${declared.toLocaleString()} B, ${(overhead / wormArrays.length).toFixed(0)} B an array\n` +
    `  a population of 100           ${(median * 100 / 1048576).toFixed(1)} MB`,
  );
}

{
  const E = engine();
  E.createWorm(1, 0.0, 0.0, 0.0);                 // the first one pays any one-off cost
  const before = E.memory.buffer.byteLength;
  for (let i = 0; i < 512; i++) E.createWorm(2000 + i, 0.0, 0.0, 0.0);
  const grew = E.memory.buffer.byteLength - before;
  const per = grew / 512;
  // A doubling heap overshoots by up to 2x and never undershoots, so this is an envelope.
  // It is wide, and it is still two orders of magnitude away from "a few kB", which is the
  // error it exists to catch.
  const ok = per >= PER_WORM_MEASURED && per <= 2.2 * PER_WORM_MEASURED;
  report(
    'LINEAR MEMORY -- what the tab actually grows by, for 512 animals',
    ok,
    `  memory.buffer grew            ${grew.toLocaleString()} B ` +
    `(${(grew / 1048576).toFixed(1)} MB)\n` +
    `  per animal                    ${per.toFixed(0)} B, ` +
    `${(per / PER_WORM_MEASURED).toFixed(2)}x the measured ${PER_WORM_MEASURED.toLocaleString()} B\n` +
    `  bound                         1.00x to 2.20x   ` +
    `(the heap doubles, so it overshoots and never undershoots)\n` +
    `  and memory.grow is one-way: a run that peaks at 512 keeps this for the life of the tab`,
  );
}

// ------------------------------------------------------------------------- the claims ---
/* The part of this that is actually about #33. The runtime was never wrong about its own
 * memory; the documents were, and they stayed wrong because nothing read them. */
{
  const kB = (PER_WORM_MEASURED / 1024).toFixed(0);
  const withCommas = PER_WORM_MEASURED.toLocaleString('en-US');
  const rows = QUOTES.map((f) => {
    const text = fs.readFileSync(at(f), 'utf8');
    return {
      f,
      bytes: text.includes(withCommas) || text.includes(String(PER_WORM_MEASURED)),
      kB: new RegExp(`${kB}\\s*kB`).test(text),
      forbidden: FORBIDDEN.test(text),
    };
  });
  const ok = rows.every((r) => r.bytes && r.kB && !r.forbidden);
  report(
    `THE DOCUMENTS QUOTE THE MEASUREMENT -- ${withCommas} B / ${kB} kB in ${QUOTES.length} files`,
    ok,
    rows.map((r) =>
      `  ${r.f.padEnd(24)} bytes ${r.bytes ? 'yes' : 'NO '}   ` +
      `${kB} kB ${r.kB ? 'yes' : 'NO '}   ` +
      `${r.forbidden ? 'STILL SAYS "a few kB"/"nearly free"' : 'no stale claim'}`).join('\n'),
  );
}

/* The same question one level down: the documents also quote a *share*, and nothing read
 * that either.
 *
 * The total was checked above and was right everywhere. The share was not, and it was
 * wrong in two places: NEXT.md and index.ts both said `headHist` was 55% of an animal
 * where it measures 89%. That figure was not invented -- it was true when a worm cost
 * 372 kB, before the per-step scratch was hoisted to module level. Hoisting shrank the
 * animal by a third, which *raised* every remaining array's share, and the sentence that
 * quoted the share was not among the things updated.
 *
 * So it is the #33 failure in miniature: a number that was measured once, went stale for a
 * reason nobody was tracking, and survived because the check next to it was looking at a
 * different number. Any percentage written within a couple of lines of `headHist` now has
 * to be the measured one.
 *
 * That rule is deliberately blunt, and the cost is worth stating because it caught the
 * commit that introduced it: a document *recording* the correction -- "89%, not the 55% we
 * used to say" -- reads to this check exactly like a document still claiming 55%, and
 * fails. There is no way to tell those apart by looking at the digits, and the alternative
 * is a check that can be talked out of firing by nearby prose, which is the weaker of the
 * two mistakes. So the history goes in words and the measurement goes in digits: say what
 * the animal used to cost, not what share it used to imply.
 */
{
  const largest = [...wormArrays].sort((a, b) => b.bytes - a.bytes)[0];
  const share = Math.round(100 * largest.bytes / declared);
  const rows = QUOTES.map((f) => {
    const text = fs.readFileSync(at(f), 'utf8');
    // Every percentage appearing near a mention of the array, in either order -- the claim
    // is written as "89% of an animal is headHist" in one file and "headHist ... is also
    // 89% of what a worm costs" in another.
    const near = [];
    for (const m of text.matchAll(new RegExp(largest.name, 'g'))) {
      const window = text.slice(Math.max(0, m.index - 220), m.index + 220);
      for (const p of window.matchAll(/(\d+)\s*%/g)) near.push(Number(p[1]));
    }
    return { f, quoted: [...new Set(near)], wrong: [...new Set(near)].filter((p) => p !== share) };
  });
  const ok = rows.every((r) => !r.wrong.length);
  report(
    `THE DOCUMENTS QUOTE THE SHARE -- ${largest.name} is ${share}% of ${declared.toLocaleString()} B`,
    ok,
    rows.map((r) =>
      `  ${r.f.padEnd(24)} ${r.quoted.length ? `quotes ${r.quoted.map((p) => p + '%').join(', ')}` : 'quotes no share'}` +
      `${r.wrong.length ? `   STALE: ${r.wrong.map((p) => p + '%').join(', ')} against a measured ${share}%` : ''}`)
      .join('\n'),
  );
}

const ok = results.every(Boolean);
console.log(ok
  ? `\nAn animal costs ${PER_WORM_MEASURED.toLocaleString()} B, and every document says so.`
  : '\nThe memory claim is NOT honest.');
process.exit(ok ? 0 : 1);
