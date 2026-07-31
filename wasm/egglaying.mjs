/* The egg-laying clustering measurement, run on the WebAssembly runtime.
 *
 * This exists because of a wall-clock fact rather than a modelling one. The behaviour
 * being measured has a twenty-minute period -- that is `resource_tau`, calibrated to
 * Waggoner et al.'s animals -- and clustering is a claim about several complete cycles, so
 * a job has to be an hour long whatever it runs on. A twenty-minute run catches one active
 * phase and looks Poisson no matter what the circuit is doing. Shortening the time
 * constant to make the test finish sooner would be fitting the animal to my patience.
 *
 * What *can* change is which implementation pays for it. The Python steps at about 1x real
 * time, so an hour of animal costs an hour of wall clock. This runtime measures 2.28x in
 * one process on an idle machine -- but about 1.5x with ten of them running, because ten
 * workers do not each get a core. An hour of animal costs roughly forty minutes under a
 * full sweep. Still worth having, and not the 2.3x the single-process number suggests.
 *
 * `wasm/conform.mjs` shows the two agree on all four pieces of egg-laying state to
 * 0.000e+0 over 4000 steps -- vulval muscle, eggs held, the resource and the count. Same
 * model, same numbers.
 *
 * Only the arms that need length live here: clustering is about `on_food` and `hsn`. The
 * rate and rescue arms in tools/egglaying.py are five-minute questions and stay there.
 *
 *   node wasm/egglaying.mjs                       # driver: runs the jobs in parallel
 *   node wasm/egglaying.mjs <seed> <arm> <mins>   # one job, prints JSON
 */

import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';
import { fork } from 'child_process';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const at = (...p) => path.join(ROOT, ...p);
const SELF = fileURLToPath(import.meta.url);

const SEEDS = Number(process.env.EGG_SEEDS || 5);
const MINUTES = Number(process.env.EGG_MINUTES || 60);
const ARMS = (process.env.EGG_ARMS || 'on_food,hsn').split(',');
// The refractory is 6 s, so a tenth of a second is far finer than any two events can be
// apart. Polling rather than instrumenting the runtime keeps the hot loop untouched.
const POLL_S = 0.1;

/* ----------------------------------------------------------------------- one job ---- */

function runJob(seed, arm, minutes) {
  const modelBuf = fs.readFileSync(at('web', 'worm.model'));
  const wasmBuf = fs.readFileSync(at('web', 'worm.wasm'));
  const dv = new DataView(modelBuf.buffer, modelBuf.byteOffset, modelBuf.byteLength);
  const headLen = dv.getUint32(8, true);
  const head = JSON.parse(new TextDecoder().decode(modelBuf.subarray(12, 12 + headLen)));
  const payload = modelBuf.subarray(12 + headLen);
  const DT = head.scalars.dt;

  const E = new WebAssembly.Instance(new WebAssembly.Module(wasmBuf), {
    env: { abort(_m, _f, l, c) { throw new Error(`wasm abort ${l}:${c}`); } },
  }).exports;
  const raw = E.alloc(payload.length + 8);
  const base = (raw + 7) & ~7;
  new Uint8Array(E.memory.buffer).set(payload, base);
  E.setPayload(base);
  E.initWorld();
  E.setNoise(1);

  // A lawn covering the dish, for the same reason tools/egglaying.py uses one: laying is
  // food-gated, so an animal that wanders off a small lawn makes the rate a statement
  // about foraging. Whether it can hold a lawn is chemotaxis' question.
  if (arm !== 'off_food') E.addFood(0, 0, head.scalars.world_extent + 4, 1.0, 1.0, 30.0);
  const w = E.createWorm(seed, 0, 0, 0);

  if (arm === 'hsn' || arm === 'vc') {
    const names = arm === 'hsn' ? ['HSNL', 'HSNR']
                                : ['VC01', 'VC02', 'VC03', 'VC04', 'VC05'];
    const all = (head.strings.neuron_names || '').split('\n');
    const idx = names.map((n) => all.indexOf(n)).filter((i) => i >= 0);
    const ptr = E.alloc(idx.length * 4);
    new Int32Array(E.memory.buffer, ptr, idx.length).set(idx);
    E.setAblated(w, ptr, idx.length);
  }

  const chunk = Math.round(POLL_S / DT);
  const polls = Math.round((minutes * 60) / POLL_S);
  const times = [];
  let seen = 0;
  for (let i = 0; i < polls; i++) {
    E.step(w, chunk);
    const laid = E.getEggsLaid(w);
    while (seen < laid) { times.push(+((i + 1) * POLL_S).toFixed(2)); seen++; }
  }
  return { seed, arm, minutes, laid: E.getEggsLaid(w), held: E.getEggsHeld(w), times };
}

/* ------------------------------------------------------------------------ driver ---- */

if (process.argv.length > 2) {
  const [seed, arm, mins] = [Number(process.argv[2]), process.argv[3], Number(process.argv[4])];
  process.stdout.write(JSON.stringify(runJob(seed, arm, mins)));
} else {
  const jobs = [];
  for (const arm of ARMS) for (let s = 0; s < SEEDS; s++) jobs.push([s, arm, MINUTES]);
  const workers = Math.max(1, Math.min(10, os.cpus().length - 2));
  const out = new Array(jobs.length);
  let next = 0, done = 0;

  const launch = () => {
    if (next >= jobs.length) return;
    const i = next++;
    const [seed, arm, mins] = jobs[i];
    const child = fork(SELF, [String(seed), arm, String(mins)], { stdio: ['ignore', 'pipe', 'inherit', 'ipc'] });
    let buf = '';
    child.stdout.on('data', (d) => { buf += d; });
    child.on('exit', () => {
      if (buf.trim()) out[i] = JSON.parse(buf);
      done++;
      process.stderr.write(`    [${done}/${jobs.length}]\n`);
      if (done === jobs.length) finish();
      else launch();
    });
  };

  const finish = () => {
    const rows = out.filter(Boolean);
    fs.writeFileSync(at('web', 'egg-events.json'), JSON.stringify(rows));
    console.error(`wrote web/egg-events.json (${rows.length} of ${jobs.length} jobs)`);
  };

  console.error(`${jobs.length} jobs, ${MINUTES} simulated minutes each, ${workers} at a time`);
  for (let k = 0; k < workers; k++) launch();
}
