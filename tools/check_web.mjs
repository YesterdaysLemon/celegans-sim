/* Static checks on the viewer's module graph.
 *
 * The viewer has no build step, which is the point -- a static file server is enough to
 * run the animal. The cost is that nothing checks the imports: a renamed export or a
 * cycle is a blank page at runtime and nothing at all before it. This is the substitute,
 * and it is deliberately dependency-free so it stays runnable on a bare `node`.
 *
 * Checks:
 *   1. every module parses
 *   2. every relative import resolves to a file that exists
 *   3. every named import is actually exported by the module it names
 *   4. no import cycles
 *   5. no exports that nothing imports (a warning, not a failure -- an unused export is
 *      usually a leftover, but occasionally it is a deliberate seam)
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const WEB = path.join(ROOT, 'web');

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.js')) out.push(p);
  }
  return out;
}

const files = walk(WEB).sort();
const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
const problems = [];
const warnings = [];

/* --- 1. parse ---------------------------------------------------------------------- */
// No parser here, so lean on the one in the runtime: import() of a syntactically broken
// module rejects. It also executes the module, which is why this runs against a stub DOM.
// Cheaper and more honest: node --check, run by the caller. Here we only read text.
const src = new Map(files.map((f) => [f, fs.readFileSync(f, 'utf8')]));

/* --- 2 & 3. imports resolve, and name things that exist ---------------------------- */

const IMPORT_RE = /^\s*import\s+([^;]*?)\s+from\s+['"]([^'"]+)['"]/gm;
const EXPORT_RE = /^\s*export\s+(?:(const|let|var|function|class)\s+([A-Za-z_$][\w$]*)|\{([^}]*)\})/gm;

const exportsOf = new Map();
for (const [f, text] of src) {
  const names = new Set();
  for (const m of text.matchAll(EXPORT_RE)) {
    if (m[2]) names.add(m[2]);
    else if (m[3]) m[3].split(',').forEach((s) => {
      const n = s.trim().split(/\s+as\s+/).pop().trim();
      if (n) names.add(n);
    });
  }
  exportsOf.set(f, names);
}

const edges = new Map(files.map((f) => [f, []]));
const importedNames = new Map(files.map((f) => [f, new Set()]));

for (const [f, text] of src) {
  for (const m of text.matchAll(IMPORT_RE)) {
    const clause = m[1], spec = m[2];
    if (!spec.startsWith('.')) continue;              // bare specifiers: not ours to check
    const target = path.resolve(path.dirname(f), spec);
    if (!fs.existsSync(target)) {
      problems.push(`${rel(f)}: imports ${spec}, which does not exist`);
      continue;
    }
    edges.get(f).push(target);
    const braces = clause.match(/\{([^}]*)\}/);
    if (!braces) continue;                            // default or namespace import
    for (const piece of braces[1].split(',')) {
      const name = piece.trim().split(/\s+as\s+/)[0].trim();
      if (!name) continue;
      importedNames.get(target)?.add(name);
      if (!exportsOf.get(target)?.has(name)) {
        problems.push(`${rel(f)}: imports { ${name} } from ${spec}, which does not export it`);
      }
    }
  }
}

/* --- 4. cycles --------------------------------------------------------------------- */

const WHITE = 0, GREY = 1, BLACK = 2;
const colour = new Map(files.map((f) => [f, WHITE]));
const stack = [];
function visit(f) {
  colour.set(f, GREY);
  stack.push(f);
  for (const g of edges.get(f) || []) {
    if (colour.get(g) === GREY) {
      const at = stack.indexOf(g);
      problems.push(`import cycle: ${stack.slice(at).concat(g).map(rel).join(' -> ')}`);
    } else if (colour.get(g) === WHITE) {
      visit(g);
    }
  }
  stack.pop();
  colour.set(f, BLACK);
}
for (const f of files) if (colour.get(f) === WHITE) visit(f);

/* --- 5. unused exports ------------------------------------------------------------- */

for (const [f, names] of exportsOf) {
  if (rel(f).endsWith('web/app.js')) continue;        // the entry point exports nothing
  for (const n of names) {
    if (!importedNames.get(f)?.has(n)) {
      warnings.push(`${rel(f)}: exports ${n}, which nothing imports`);
    }
  }
}

/* --- report ------------------------------------------------------------------------ */

console.log(`checked ${files.length} modules under web/`);
for (const w of warnings) console.log(`  warn  ${w}`);
for (const p of problems) console.log(`  FAIL  ${p}`);
if (problems.length) {
  console.log(`\n${problems.length} problem(s). The viewer has no build step, so these are`
            + ` runtime blank pages rather than compile errors.`);
  process.exit(1);
}
console.log('  module graph is acyclic, and every import resolves.');
