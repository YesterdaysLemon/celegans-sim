/* Run the gates CI would run, locally, in the workflows' own order.
 *
 *     node tools/check_all.mjs               # everything that does not rewrite a tracked file
 *     node tools/check_all.mjs --rebuild     # ...plus the gates that regenerate .model/.wasm
 *     node tools/check_all.mjs --python      # ...plus the ~37 minute pytest suite
 *     node tools/check_all.mjs --list        # what the gates are, and where each comes from
 *     node tools/check_all.mjs --only web    # one gate, by id
 *
 * CI is paused at the jobs -- this account's Actions minutes are exhausted, so every job is
 * gated on the repository variable CI_ENABLED while the triggers stay live so
 * tests/test_ci_policy.py can keep pinning the path filters. The gates themselves were not
 * weakened; they just have nowhere to run. This is that somewhere.
 *
 * WHY THIS FILE EXISTS AT ALL, GIVEN README ALREADY LISTS THE COMMANDS.
 *
 * Because the list is in three places -- two workflow files and a README section -- and the
 * order inside a job is load-bearing rather than decorative. `every module parses` runs
 * before the browser check because a module that does not parse reaches the browser as
 * nothing but a blank rectangle, and the parse error is the message you want. Rebuilding
 * that order by hand from YAML is exactly the kind of thing that gets done wrong quietly.
 *
 * A SKIP IS NOT A PASS, AND THIS FILE IS BUILT AROUND SAYING SO.
 *
 * NEXT.md names this project's most repeated bug: a check that runs, passes, and covers
 * less than its own comment claims. The empty conformance dish that hid the missing field
 * diffusion, the lawn-less plate that hid the food skirt, and an egg-laying comparison that
 * printed a perfect 0.000e+0 from comparing zero fields are all one mistake. A local runner
 * that prints a green summary having quietly not run the browser gate, because this machine
 * has no Chrome, would be a new instance of it -- and a worse one, because it would be the
 * tool you trust to tell you whether you are done.
 *
 * So: skipped gates are counted separately, never folded into the pass count, and reprinted
 * at the bottom with the reason and the fix. `--strict` makes a skip an exit failure, which
 * is what a release check wants and what an iterating developer does not.
 *
 * WHAT IT DOES NOT DO. It does not re-enable CI -- setting CI_ENABLED to `true` is still the
 * one switch for that -- and it does not weaken a gate to make it runnable here. A gate this
 * machine cannot honestly run is skipped and named, not softened.
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);

const argv = process.argv.slice(2);
const has = (f) => argv.includes(f);
const OPT = {
  rebuild: has('--rebuild'),
  python: has('--python'),
  strict: has('--strict'),
  list: has('--list'),
  only: (() => { const i = argv.indexOf('--only'); return i >= 0 ? argv[i + 1] : null; })(),
};

/* --- prerequisites, probed once ------------------------------------------------------
 *
 * Each probe answers "can this machine honestly run that gate", and returns the reason it
 * cannot in a form that tells you what to install. A probe never installs anything: a check
 * runner that mutates the machine to make itself pass is the same failure as one that
 * lowers a threshold to make a test pass.
 */
/* PATH walk in Node rather than `sh -c command -v` (#167): the probe must not itself
 * require the POSIX shell whose absence it may be about to report. PATHEXT covers the
 * Windows spelling of executability. */
function which(bin) {
  const exts = process.platform === 'win32'
    ? (process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';') : [''];
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (!dir) continue;
    for (const ext of exts) {
      const p = path.join(dir, bin + ext.toLowerCase());
      try { fs.accessSync(p, fs.constants.X_OK); return p; } catch { /* keep walking */ }
    }
  }
  return null;
}

function findChrome() {
  if (process.env.CHROME && fs.existsSync(process.env.CHROME)) return process.env.CHROME;
  const candidates = [
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    '/opt/pw-browsers/chromium/chrome-linux/chrome',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  // Playwright's browser pool names its directories by build number, so glob the one level.
  const pool = '/opt/pw-browsers';
  if (fs.existsSync(pool)) {
    for (const d of fs.readdirSync(pool)) {
      const c = path.join(pool, d, 'chrome-linux', 'chrome');
      if (fs.existsSync(c)) return c;
    }
  }
  return which('google-chrome') || which('chromium');
}

function findPython() {
  for (const p of [at('.venv', 'bin', 'python'), which('python3'), which('python')]) {
    if (!p || !fs.existsSync(p)) continue;
    // numpy is the real prerequisite -- a bare interpreter runs none of these gates.
    const r = spawnSync(p, ['-c', 'import numpy'], { encoding: 'utf8' });
    if (r.status === 0) return p;
  }
  return null;
}

const PY = findPython();
const CHROME = findChrome();
const DOCKER = which('docker')
  && spawnSync('docker', ['info'], { encoding: 'utf8' }).status === 0 ? 'docker' : null;
const NODE_MODULES = fs.existsSync(at('node_modules'));
const WASM_MODULES = fs.existsSync(at('wasm', 'node_modules'));

const NEED = {
  python: () => PY ? null : 'no Python with numpy; run: python3 -m venv .venv && .venv/bin/python -m pip install -e .',
  chrome: () => CHROME ? null : 'no Chrome/Chromium found; set CHROME=/path/to/chrome',
  docker: () => DOCKER ? null : 'no working Docker daemon; the production cache boundary lives in nginx and is only honest against that exact config',
  npm: () => NODE_MODULES ? null : 'no node_modules; run: npm ci --no-audit --no-fund',
  asc: () => WASM_MODULES ? null : 'no wasm/node_modules; run: cd wasm && npm ci --no-audit --no-fund',
  model: () => fs.existsSync(at('web', 'worm.model')) && fs.existsSync(at('web', 'worm.wasm'))
    ? null : 'no web/worm.model + web/worm.wasm pair; build with --rebuild',
};

/* --- how a gate runs ----------------------------------------------------------------- */

/* Does this command string actually need a shell? Most gates are a plain `node ...`
 * invocation, and those spawn directly on every platform. The ones that use variable
 * expansion, pipes, redirects or `cd` genuinely want POSIX `sh`; on a platform without
 * one they must FAIL SAYING SO rather than with the empty output an ENOENT spawn used
 * to produce (#167). */
const NEEDS_SHELL = /[&|<>$;`"'\\]|(?:^|\s)cd\s/;

function sh(cmd, env = {}) {
  const opts = () => ({
    cwd: ROOT, encoding: 'utf8',
    env: { ...process.env, ...env },
    maxBuffer: 64 * 1024 * 1024,
  });
  return () => {
    let r;
    if (!NEEDS_SHELL.test(cmd)) {
      const [file, ...args] = cmd.split(/\s+/);
      r = spawnSync(file, args, opts());
    } else if (process.platform !== 'win32' || which('sh')) {
      r = spawnSync('sh', ['-c', cmd], opts());
    } else {
      return { status: 1, stdout: '',
               stderr: `this gate's command needs a POSIX sh, and none is on PATH:\n  ${cmd}\n`
                 + 'Install Git Bash or run the gate under WSL.' };
    }
    // A spawn that never ran (ENOENT and kin) reports status null and empty streams --
    // the "immediate failure with empty output" #167 hit. Name the culprit instead.
    if (r.error) {
      return { status: r.status ?? 1, stdout: r.stdout || '',
               stderr: (r.stderr || '') + `\nspawn failed for: ${cmd}\n${r.error.message}` };
    }
    return r;
  };
}

/* --selftest: the portability contract (#167), asserted without running any gate.
 * Focused on the two things that broke Windows: temp-directory selection must come
 * from the platform API, and the shell classifier must keep plain node invocations
 * shell-free while routing genuinely-POSIX commands to sh. */
if (has('--selftest')) {
  const assert = (ok, what) => {
    if (!ok) { console.error(`selftest FAIL: ${what}`); process.exit(1); }
    console.log(`  ok  ${what}`);
  };
  assert(path.isAbsolute(os.tmpdir()), 'os.tmpdir() is absolute on this platform');
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'celegans-selftest-'));
  fs.rmdirSync(d);
  assert(true, 'mkdtemp under os.tmpdir() works');
  const simple = ['node tools/check_web.mjs', 'node --test wasm/medium.test.mjs'];
  const posix = ['"$PY" tools/conform.py > web/conform.json',
                 'cp a b && cd wasm && npx asc', 'docker run --rm -d --name x \\'];
  for (const c of simple) assert(!NEEDS_SHELL.test(c), `shell-free: ${c}`);
  for (const c of posix) assert(NEEDS_SHELL.test(c), `needs sh: ${c.slice(0, 30)}...`);
  console.log('selftest passed');
  process.exit(0);
}

// The one gate CI expresses as an inline shell loop rather than as a script. Reproduced
// rather than referenced, because it has no file of its own to call.
function everyModuleParses() {
  return () => {
    const files = [];
    const walk = (d) => {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) walk(p);
        else if (e.name.endsWith('.js')) files.push(p);
      }
    };
    walk(at('web'));
    for (const d of ['tools', 'wasm']) {
      for (const e of fs.readdirSync(at(d))) {
        if (e.endsWith('.mjs')) files.push(at(d, e));
      }
    }
    for (const f of files) {
      const r = spawnSync(process.execPath, ['--check', f], { encoding: 'utf8' });
      if (r.status !== 0) {
        return { status: r.status, stdout: r.stdout, stderr: `${path.relative(ROOT, f)}\n${r.stderr}` };
      }
    }
    const n = files.filter((f) => f.startsWith(at('web'))).length;
    return { status: 0, stdout: `${n} viewer modules parse (${files.length} files checked)`, stderr: '' };
  };
}

/* --- the gates, in the workflows' own order -------------------------------------------
 *
 * `job` names the CI job each one comes from, and `covers` lists the CI step names it
 * stands in for, character for character. That is not documentation:
 * tests/test_local_checks.py reads both workflow files and fails if a named CI step is
 * claimed by no gate here, which is what stops this runner from drifting into covering less
 * than its own header claims. A gate covering two names is a step CI spells twice --
 * `rebuild the model and the runtime` and `rebuild the model and runtime as one set` are
 * the same command in two workflows.
 *
 * `mutates` lists tracked files a gate rewrites. Those are held behind --rebuild because
 * regenerating web/worm.model and web/worm.wasm in a dirty working tree is a surprise, and
 * because anything else reading that pair -- wasm/evolve.mjs, a viewer you have open -- gets
 * a torn artifact set underneath it.
 */
const GATES = [
  // ---- viewer.yml : viewer -----------------------------------------------------------
  {
    id: 'headers', job: 'viewer', step: 'every viewer asset has a deliberate cache policy',
    covers: ['every viewer asset has a deliberate cache policy'],
    needs: ['docker'],
    run: sh(`docker run --rm -d --name celegans-cache-policy -p 127.0.0.1:8080:8080 \
      -v "${ROOT}/web:/usr/share/nginx/html:ro" \
      -v "${ROOT}/docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine \
      && sleep 2 && node tools/check_cache_headers.mjs http://127.0.0.1:8080; \
      rc=$?; docker stop celegans-cache-policy >/dev/null 2>&1; exit $rc`),
  },
  {
    id: 'parse', job: 'viewer', step: 'every module parses',
    covers: ['every module parses'],
    needs: [], run: everyModuleParses(),
  },
  {
    id: 'web', job: 'viewer', step: 'module graph resolves and is acyclic',
    covers: ['module graph resolves and is acyclic'],
    needs: [], run: sh('node tools/check_web.mjs'),
  },
  {
    id: 'rate', job: 'viewer', step: 'the rate readouts measure what their labels claim',
    covers: ['the rate readouts measure what their labels claim'],
    needs: [], run: sh('node --test tools/sim_rate.test.mjs'),
  },
  {
    id: 'smoke-web', job: 'viewer', step: 'browser smoke test',
    covers: ['browser smoke test'],
    needs: ['npm', 'chrome'], run: sh('node tools/smoke_web.mjs', { CHROME }),
  },

  // ---- viewer.yml : server-transport --------------------------------------------------
  {
    id: 'smoke-server', job: 'server-transport', step: 'Python server transport smoke test',
    covers: ['Python server transport smoke test'],
    needs: ['npm', 'chrome', 'python'],
    run: sh('node tools/smoke_server.mjs', { CHROME }),
  },

  // ---- viewer.yml : conformance -------------------------------------------------------
  {
    id: 'conform-inputs', job: 'conformance', step: 'conformance input diagnostics',
    covers: ['conformance input diagnostics'],
    needs: [], run: sh('node --test wasm/conform-inputs.test.mjs'),
  },
  {
    id: 'rebuild', job: 'conformance', step: 'rebuild the model and the runtime',
    covers: ['rebuild the model and the runtime'],
    needs: ['python', 'asc'], mutates: ['web/worm.model', 'web/worm.wasm', 'wasm/assembly/model_gen.ts'],
    run: sh('python tools/export_model.py && cd wasm && npx asc assembly/index.ts --target release',
            { PYTHONPATH: '.', PATH: `${PY ? path.dirname(PY) : ''}:${process.env.PATH}` }),
  },
  {
    id: 'energy-fitness', job: 'conformance', step: 'a bigger pharynx buys no fitness',
    covers: ['a bigger pharynx buys no fitness'],
    needs: ['model'], run: sh('node --test wasm/energy-fitness.test.mjs'),
  },
  {
    id: 'medium', job: 'conformance', step: 'the dish remembers what it is filled with',
    covers: ['the dish remembers what it is filled with'],
    needs: ['model'], run: sh('node --test wasm/medium.test.mjs'),
  },
  {
    id: 'conform', job: 'conformance', step: 'reference trajectories, then compare',
    covers: ['reference trajectories, then compare', 'regenerated pair conforms to the Python model'],
    needs: ['python', 'model'], mutates: ['web/conform.json'],
    run: sh('"$PY" tools/conform.py > web/conform.json && node wasm/conform.mjs',
            { PYTHONPATH: '.', PY: PY || 'python3' }),
  },
  {
    id: 'invariants', job: 'conformance', step: 'the physics guard still fires',
    covers: ['the physics guard still fires'],
    needs: ['model'], run: sh('node --test wasm/invariants.test.mjs'),
  },
  {
    id: 'solve', job: 'conformance', step: 'the runtime solves for its own resting potentials',
    covers: ['the runtime solves for its own resting potentials'],
    needs: ['model'], run: sh('node --test wasm/solve.test.mjs'),
  },
  {
    id: 'eggs-fitness', job: 'conformance', step: 'the egg measure says what it is',
    covers: ['the egg measure says what it is'],
    needs: ['model'], run: sh('node --test wasm/eggs-fitness.test.mjs'),
  },
  {
    id: 'population', job: 'conformance', step: 'the population behaves as a population',
    covers: ['the population behaves as a population'],
    needs: ['model'], run: sh('node wasm/population.mjs'),
  },
  {
    id: 'memory', job: 'conformance', step: 'an animal costs what the documents say it costs',
    covers: ['an animal costs what the documents say it costs'],
    needs: ['model'], run: sh('node wasm/memory.mjs'),
  },

  // ---- python.yml : dataset -----------------------------------------------------------
  //
  // The dataset job's first three steps are unnamed `run:` lines in the YAML, so there is no
  // CI step name for this gate to claim; it is here because the job is, and the job's own
  // name is what it stands for.
  {
    id: 'dataset', job: 'dataset', step: 'pinned anatomy rebuilds the committed dataset',
    covers: [],
    needs: ['python'], mutates: ['data/celegans.json'],
    run: sh('"$PY" tools/fetch_raw.py && "$PY" tools/build_dataset.py '
          + '&& git diff --exit-code -- data/celegans.json', { PY: PY || 'python3' }),
  },
  {
    id: 'artifacts', job: 'dataset', step: 'committed WASM matches its committed generated layout',
    covers: ['committed WASM matches its committed generated layout'],
    needs: ['asc', 'model'], mutates: ['web/worm.wasm'],
    run: sh('cp web/worm.wasm "$SNAP/worm.wasm" && cd wasm '
          + '&& npx asc assembly/index.ts --target release && cmp "$SNAP/worm.wasm" ../web/worm.wasm',
            { SNAP: fs.mkdtempSync(path.join(os.tmpdir(), 'celegans-')) }),
  },
  /* Snapshot, regenerate, compare -- one gate, because the comparison is meaningless
   * without the snapshot that precedes it. CI can afford to split them across steps because
   * a job is a fresh checkout; locally the snapshot has to happen before anything is
   * overwritten, so the three CI steps collapse into one command here.
   *
   * Raw model bytes include a linear solve and libm-derived setup values, so exact
   * cross-platform comparison would make last-bit BLAS differences a flaky gate.
   * check_model_artifacts.py compares every layout field and payload array, exactly for
   * discrete data and within 5e-13 for floats. */
  {
    id: 'model-artifacts', job: 'dataset',
    step: 'regenerated model/runtime set matches the committed set',
    covers: ['rebuild the model and runtime as one set',
             'regenerated model/runtime set matches the committed set'],
    needs: ['python', 'asc', 'model'],
    mutates: ['web/worm.model', 'web/worm.wasm', 'wasm/assembly/model_gen.ts'],
    run: sh('cp web/worm.model "$SNAP/worm.model" && cp web/worm.wasm "$SNAP/worm.wasm" '
          + '&& cp wasm/assembly/model_gen.ts "$SNAP/model_gen.ts" '
          + '&& "$PY" tools/export_model.py '
          + '&& (cd wasm && npx asc assembly/index.ts --target release) '
          + '&& "$PY" tools/check_model_artifacts.py '
          + '  --expected-model "$SNAP/worm.model" --actual-model web/worm.model '
          + '  --expected-layout "$SNAP/model_gen.ts" --actual-layout wasm/assembly/model_gen.ts '
          + '  --expected-wasm "$SNAP/worm.wasm" --actual-wasm web/worm.wasm',
            { PYTHONPATH: '.', PY: PY || 'python3',
              SNAP: fs.mkdtempSync(path.join(os.tmpdir(), 'celegans-')) }),
  },

  // ---- python.yml : tests -------------------------------------------------------------
  //
  // CI fans this out one file per runner via a matrix, so the step is unnamed there too.
  // Locally it is one pytest invocation and about 37 minutes of simulation, which is why it
  // is behind --python rather than in the default set.
  {
    id: 'pytest', job: 'tests', step: 'the Python model suite', slow: true,
    covers: [],
    needs: ['python'],
    run: sh('"$PY" -m pytest tests/ -q', {
      PYTHONPATH: '.', PY: PY || 'python3',
      OMP_NUM_THREADS: '1', OPENBLAS_NUM_THREADS: '1', MKL_NUM_THREADS: '1',
      VECLIB_MAXIMUM_THREADS: '1', NUMEXPR_NUM_THREADS: '1',
    }),
  },
];

/* --- selection ----------------------------------------------------------------------- */

const C = process.stdout.isTTY
  ? { pass: '\x1b[32m', fail: '\x1b[31m', skip: '\x1b[33m', dim: '\x1b[2m', off: '\x1b[0m' }
  : { pass: '', fail: '', skip: '', dim: '', off: '' };

if (OPT.list) {
  console.log('gate             job               rewrites tracked files   step');
  for (const g of GATES) {
    console.log(`${g.id.padEnd(16)} ${g.job.padEnd(17)} `
              + `${(g.mutates ? 'yes' : '').padEnd(24)} ${g.step}`);
  }
  process.exit(0);
}

const selected = GATES.filter((g) => {
  if (OPT.only) return g.id === OPT.only;
  if (g.slow && !OPT.python) return false;
  return true;
});

if (OPT.only && !selected.length) {
  console.error(`no gate with id "${OPT.only}"; run --list to see them`);
  process.exit(2);
}

/* --- run ------------------------------------------------------------------------------ */

console.log('celegans-sim -- the gates CI would run, in its order.');
console.log(`${C.dim}CI is paused at the jobs (CI_ENABLED); nothing below is weakened to run here.${C.off}\n`);

const results = [];
let lastJob = null;

for (const g of selected) {
  if (g.job !== lastJob) { console.log(`${C.dim} ${g.job}${C.off}`); lastJob = g.job; }

  // Why a gate would not run, cheapest reason first: an unmet prerequisite is a property of
  // the machine, holding back a rewrite is a choice this runner made.
  let skip = null;
  for (const n of g.needs || []) { skip = NEED[n](); if (skip) break; }
  if (!skip && g.mutates && !OPT.rebuild && !OPT.only) {
    skip = `rewrites ${g.mutates.join(', ')}; pass --rebuild to run it`;
  }

  const label = g.step.padEnd(56);
  if (skip) {
    console.log(`  ${C.skip}-${C.off} ${label} ${C.skip}SKIPPED${C.off}`);
    results.push({ g, state: 'skip', why: skip });
    continue;
  }

  // Only on a terminal. Piped into a file or a pager there is no cursor to rewind, and the
  // half-erased "running" would end up interleaved with the result it was replaced by.
  if (process.stdout.isTTY) process.stdout.write(`  ${C.dim}·${C.off} ${label} ${C.dim}running${C.off}`);
  const t0 = Date.now();
  const r = g.run();
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const ok = r.status === 0;
  if (process.stdout.isTTY) process.stdout.write('\r\x1b[2K');
  console.log(`  ${ok ? `${C.pass}✓${C.off}` : `${C.fail}✗${C.off}`} ${label} `
            + `${ok ? C.pass + 'passed' : C.fail + 'FAILED'}${C.off} ${C.dim}${secs}s${C.off}`);
  results.push({ g, state: ok ? 'pass' : 'fail', out: r });
}

/* --- report --------------------------------------------------------------------------- */

const passed = results.filter((r) => r.state === 'pass');
const failed = results.filter((r) => r.state === 'fail');
const skipped = results.filter((r) => r.state === 'skip');

for (const f of failed) {
  console.log(`\n${C.fail}--- ${f.g.job} / ${f.g.step} ---${C.off}`);
  const body = `${f.out.stdout || ''}${f.out.stderr || ''}`.trimEnd();
  const lines = body.split('\n');
  console.log(lines.length > 40 ? [...lines.slice(0, 12), `  ${C.dim}... ${lines.length - 32} lines ...${C.off}`, ...lines.slice(-20)].join('\n') : body);
}

console.log(`\n  ${passed.length} passed, ${failed.length} failed, ${skipped.length} skipped`);

// The part this file exists for. A skip is reported as a gap in coverage, with the reason
// and the fix, and never quietly folded into the pass count.
if (skipped.length) {
  console.log(`\n  ${C.skip}A SKIP IS NOT A PASS.${C.off} ${skipped.length} gate(s) did not run, so nothing here`);
  console.log('  says anything about what they cover:');
  for (const s of skipped) console.log(`    ${C.skip}·${C.off} ${s.g.step}\n      ${C.dim}${s.why}${C.off}`);
}

if (!failed.length && !skipped.length) {
  console.log(`\n  ${C.pass}Every gate in scope ran and passed.${C.off}`);
}

const exit = failed.length ? 1 : (OPT.strict && skipped.length ? 1 : 0);
if (OPT.strict && skipped.length && !failed.length) {
  console.log(`\n  ${C.fail}--strict: exiting non-zero because gates were skipped.${C.off}`);
}
process.exit(exit);
