/* End-to-end smoke test for the viewer's Python/WebSocket transport.
 *
 * This is deliberately separate from smoke_web.mjs. The default smoke test stays a fast
 * check of the local WASM path; this one starts the reference Python model, loads
 * `?server`, and proves that metadata, packed frames, field images, and commands cross the
 * socket intact.
 *
 *   node tools/smoke_server.mjs
 *   PYTHON=/path/to/python CHROME=/path/to/chrome node tools/smoke_server.mjs
 */

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const guesses = [
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ];
  for (const guess of guesses) if (fs.existsSync(guess)) return guess;
  return null;
}

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', resolve);
  });
}

function close(server) {
  return new Promise(resolve => server.close(resolve));
}

/* Two free ports that are deliberately *not* consecutive.
 *
 * This used to hunt for a consecutive pair, because the viewer used to require one: it
 * built the socket URL as the page's port plus one, so `--ws-port` was decorative and a
 * test that arranged the ports to match the guess could not possibly notice. Adjacent is
 * the one layout the bug is invisible in, and it is not the layout the CLI offers -- a
 * reverse proxy, an occupied port or a hosted environment all produce this one.
 *
 * Nothing is listening on httpPort + 1, so a viewer that goes back to guessing gets
 * ECONNREFUSED and the connect wait below times out naming what never came true.
 */
async function freePorts() {
  for (let attempt = 0; attempt < 20; attempt++) {
    const a = net.createServer(), b = net.createServer();
    try {
      await listen(a, 0);
      await listen(b, 0);
      const http = a.address().port, ws = b.address().port;
      await close(a);
      await close(b);
      if (http < 65535 && ws < 65535 && Math.abs(http - ws) > 1) return { http, ws };
    } catch {
      if (a.listening) await close(a);
      if (b.listening) await close(b);
    }
  }
  throw new Error('could not find two free nonconsecutive ports');
}

function pythonCommand() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const local = process.platform === 'win32'
    ? path.join(ROOT, '.venv', 'Scripts', 'python.exe')
    : path.join(ROOT, '.venv', 'bin', 'python');
  return fs.existsSync(local) ? local : 'python';
}

async function waitForServer(url, child) {
  let last;
  for (let attempt = 0; attempt < 300; attempt++) {
    if (child.exitCode !== null) {
      throw new Error(`Python server exited before listening (exit ${child.exitCode})`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
      last = new Error(`HTTP ${response.status}`);
    } catch (error) {
      last = error;
    }
    await delay(100);
  }
  throw new Error(`Python server did not become ready: ${last}`);
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.kill();
  await Promise.race([exited, delay(3000)]);
  if (child.exitCode === null) {
    child.kill('SIGKILL');
    await exited;
  }
}

const chrome = findChrome();
if (!chrome) {
  console.error('no Chrome found. Set CHROME=/path/to/chrome.');
  process.exit(2);
}

const { http: httpPort, ws: wsPort } = await freePorts();
assert.notEqual(wsPort, httpPort + 1,
  'the ports must not be consecutive, or this test cannot see --ws-port being ignored');
const python = pythonCommand();
const serverOutput = [];
const child = spawn(
  python,
  ['run.py', '--port', String(httpPort), '--ws-port', String(wsPort), '--seed', '1701'],
  {
    cwd: ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
child.stdout.on('data', chunk => serverOutput.push(chunk.toString()));
child.stderr.on('data', chunk => serverOutput.push(chunk.toString()));

let browser;
try {
  const base = `http://127.0.0.1:${httpPort}/`;
  await waitForServer(base, child);

  browser = await puppeteer.launch({
    executablePath: chrome,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const errors = [];
  const failed = [];
  page.on('console', message => {
    const text = message.text();
    // Edge asks for /favicon.ico even without a link element. It is not a viewer asset,
    // and the Python static server correctly returns 404.
    if (message.type() === 'error' && !text.startsWith('Failed to load resource:')) {
      errors.push(text);
    }
  });
  page.on('pageerror', error => errors.push(String(error)));
  page.on('response', response => {
    if (response.status() >= 400 && !response.url().endsWith('/favicon.ico')) {
      failed.push(`${response.url()} -> ${response.status()}`);
    }
  });

  /* The server has to tell the browser where the socket is, because only the server knows.
   * `--port` and `--ws-port` are independent options; the viewer used to add one to the
   * page's port and hope, which meant `--port 9000` served a page dialling 9001 at a
   * server on 8081 and nothing but a reconnect loop to show for it. */
  const advertised = await (await fetch(`${base}transport.json`)).json();
  assert.equal(advertised.ws_port, wsPort,
    `the server advertises ws_port ${advertised.ws_port} but was given --ws-port ${wsPort}`);

  await page.goto(`${base}?server&debug`, { waitUntil: 'load' });
  try {
    await page.waitForFunction(
      () => window.__sim?.connected && window.__sim?.meta && window.__sim?.frame
        && window.__sim?.field && document.getElementById('banner').classList.contains('gone'),
      { timeout: 30000 },
    );
  } catch {
    // The banner names the endpoint the viewer chose, which is the whole diagnosis when
    // this fails: page on httpPort, server on wsPort, viewer dialling something else.
    const banner = await page.evaluate(() =>
      document.getElementById('banner').textContent.replace(/\s+/g, ' ').trim());
    throw new Error(
      `the viewer never connected to the server on ws port ${wsPort} `
      + `(page served on ${httpPort}). Banner says: ${banner}`);
  }

  const transport = await page.evaluate(() => {
    const S = window.__sim;
    const f = S.frame;
    return {
      connected: S.connected,
      neurons: S.meta.neurons.length,
      muscles: S.meta.muscles.length,
      muscleIndex: Object.keys(S.meta.muscleIndex).length,
      worldRadius: S.meta.world.radius,
      radius: S.meta.radius.length,
      nNodes: S.meta.n_nodes,
      nJoints: S.meta.n_joints,
      nodes: f.nodes.length,
      act: f.act.length,
      volts: f.V.length,
      tension: f.tension.length,
      kappa: f.kappa.length,
      finite: [...f.nodes, ...f.act, ...f.V, ...f.tension, ...f.kappa]
        .every(Number.isFinite),
      fieldN: S.field.n,
      fieldBytes: S.field.data.length,
      // Egg-laying, which the local WASM feed has published since it was written and this
      // one did not. Read off the frame rather than the DOM, because the header's egg
      // readout is markup in index.html until something overwrites it -- and a placeholder
      // that happens to agree with the model is exactly how this stayed unnoticed.
      eggsHeld: f.eggsHeld,
      eggsLaid: f.eggsLaid,
      vulva: f.vulva,
      eglActive: f.eglActive,
      eggsNorm: f.sensed.eggsNorm,
      plate: S.eggs && { n: S.eggs.n, x: S.eggs.x.length, y: S.eggs.y.length,
                         finite: [...S.eggs.x, ...S.eggs.y].every(Number.isFinite) },
      // Bytes after the last array the client parses. The frame is one buffer whose
      // length the server decides, so this is the client's layout checked against the
      // server's, with no slack: anything the server appends and the client forgets to
      // read shows up here as a nonzero remainder.
      tail: f.kappa.buffer.byteLength - (f.kappa.byteOffset + f.kappa.byteLength),
    };
  });
  assert.equal(transport.connected, true);
  assert.equal(transport.neurons, 302);
  assert.equal(transport.muscles, 95);
  assert.equal(transport.muscleIndex, transport.muscles);
  assert.ok(transport.worldRadius > 0);
  assert.equal(transport.radius, transport.nNodes - 1);
  assert.equal(transport.nodes, transport.nNodes * 2);
  assert.equal(transport.act, transport.neurons);
  assert.equal(transport.volts, transport.neurons);
  assert.equal(transport.tension, transport.muscles);
  assert.equal(transport.kappa, transport.nJoints);
  assert.equal(transport.finite, true);
  assert.equal(transport.fieldBytes, transport.fieldN * transport.fieldN * 3);

  /* Egg parity. The claim is not that the animal lays an egg during a smoke test -- it
   * lays a handful an hour and this runs for seconds -- it is that every piece of egg
   * state the other transport publishes arrives over this one as a number rather than
   * being absent. Absent was indistinguishable from zero: `sensed[key] ?? 0` handed the
   * "Eggs held" meter a live-looking 0 and the header kept index.html's placeholder, so
   * the `?server` viewer showed a frozen egg count that read as authoritative. */
  assert.ok(Number.isFinite(transport.eggsHeld),
    `the frame carries no eggs-held (got ${transport.eggsHeld})`);
  assert.ok(Number.isFinite(transport.eggsLaid),
    `the frame carries no eggs-laid (got ${transport.eggsLaid})`);
  assert.ok(Number.isFinite(transport.vulva) && transport.vulva >= 0 && transport.vulva <= 1,
    `vulval muscle activation out of range: ${transport.vulva}`);
  assert.ok(transport.eglActive === 0 || transport.eglActive === 1,
    `the egg-laying phase flag is not a flag: ${transport.eglActive}`);
  // A young adult starts with eggs in the uterus (EggLayingParams.eggs_initial), so an
  // empty one this early means the field is missing rather than the animal being spent.
  assert.ok(transport.eggsHeld > 0, 'the uterus reads empty seconds into the run');
  assert.ok(transport.eggsNorm > 0, 'the "Eggs held" meter is being fed a placeholder zero');
  assert.equal(transport.tail, (transport.plate ? transport.plate.n : 0) * 8,
    `${transport.tail} bytes of frame the viewer never parses`);
  if (transport.plate) {
    assert.equal(transport.plate.x, transport.plate.n);
    assert.equal(transport.plate.y, transport.plate.n);
    assert.equal(transport.plate.finite, true, 'an egg on the plate has no position');
  }

  /* Wait for the panels to have live data in them.
   *
   * One condition per wait, so a timeout names what never came true. Rolled into a single
   * predicate these produced a bare `TimeoutError: Waiting failed: 15000ms exceeded`
   * pointing at puppeteer's internals, which is how this test stayed red on main for five
   * runs without anyone learning what it was complaining about.
   */
  const settle = async (what, fn, arg) => {
    try {
      await page.waitForFunction(fn, { timeout: 15000 }, arg);
    } catch {
      throw new Error(`timed out waiting for ${what}`);
    }
  };
  await settle('the kymograph to take a column', () => window.__sim.kymo?.filled > 0);
  await settle('three membrane traces with samples in them',
    () => window.__sim.traces?.length >= 3
      && window.__sim.traces.every(trace => trace.length >= 5));
  /* Every sense meter the panel declares must have been given a live value.
   *
   * This used to assert an exact count of 10, which was true when it was written and
   * stopped being true when the pharynx and egg-laying work added four rows -- so the
   * check failed for a year of days over an accounting difference rather than a defect.
   * The number was also the weaker of the two things it could have asserted: `=== 10`
   * passes just as happily with ten of twelve meters live and two silently dead, which is
   * the failure actually worth catching. Counting is now the panel's business; this
   * asserts the property. */
  await settle('every sense meter to carry a live value', () => {
    const meters = [...document.querySelectorAll('#senses [role="meter"]')];
    return meters.length > 0 && meters.every(m => m.hasAttribute('aria-valuenow'));
  });

  const rendered = await page.evaluate(() => {
    function ink(id) {
      const canvas = document.getElementById(id);
      const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] !== 0) return true;
      return false;
    }
    return {
      kymoFilled: window.__sim.kymo.filled,
      traceSamples: window.__sim.traces.map(trace => trace.length),
      senseRows: document.querySelectorAll('#senses [role="meter"]').length,
      senseLive: document.querySelectorAll('#senses [role="meter"][aria-valuenow]').length,
      // By key rather than by count. A new row must not break this test -- that is what
      // broke it last time -- but a sense quietly disappearing from the panel should.
      senseKeys: [...document.querySelectorAll('#senses [role="meter"]')]
        .map(m => m.dataset.meter),
      fieldBytes: window.__sim.field.data.length,
      canvases: ['c-dish', 'c-neurons', 'c-muscle', 'c-kymo', 'c-trace'].map(ink),
    };
  });
  assert.ok(rendered.kymoFilled > 0);
  assert.ok(rendered.traceSamples.every(samples => samples >= 5));
  assert.equal(rendered.senseLive, rendered.senseRows,
    `${rendered.senseRows - rendered.senseLive} sense meters never got a value`);
  for (const key of ['attractant', 'food', 'repellent', 'oxygen', 'temperature', 'touch']) {
    assert.ok(rendered.senseKeys.includes(key), `the ${key} meter is missing from #senses`);
  }
  assert.ok(rendered.fieldBytes > 0);
  assert.ok(rendered.canvases.every(Boolean), 'one or more viewer canvases rendered blank');

  await page.click('#b-play');
  await page.waitForFunction(() => window.__sim.frame?.running === 0, { timeout: 5000 });
  const held = await page.evaluate(() => ({
    t: window.__sim.frame.t, freq: window.__sim.freqBuf.length,
  }));
  const pausedAt = held.t;
  await delay(500);
  const still = await page.evaluate(() => ({
    t: window.__sim.frame.t, freq: window.__sim.freqBuf.length,
  }));
  const stillAt = still.t;
  assert.ok(Math.abs(stillAt - pausedAt) < 1e-6, `clock advanced while paused: ${pausedAt} -> ${stillAt}`);

  /* Pausing the simulation must not keep costing anything.
   *
   * Frames do not stop when the clock does -- the server keeps sending thirty a second so
   * the viewer stays live and controllable -- and the telemetry buffers are trimmed by
   * *simulated* time, so while the clock is frozen nothing in them can ever age out. They
   * grew for as long as you left the tab paused, and the frequency estimate rescans the
   * whole buffer twice every frame, so the page got steadily slower while the animal did
   * nothing at all. An hour paused was about 216,000 samples.
   *
   * Asserted as a property -- "a frozen clock adds no samples" -- rather than as a size,
   * because a size passes for as long as the buffer takes to reach it. */
  assert.equal(still.freq, held.freq,
    `the frequency buffer grew by ${still.freq - held.freq} entries in 500 ms `
    + `with the clock frozen at ${pausedAt}`);

  /* And the same claim under stress, since 500 ms of real frames is only fifteen of them.
   * This calls the viewer's own updateFreq -- the same module instance the page is
   * running, imported by URL -- three thousand times at the frozen timestamp, which is
   * what fifty seconds of paused tab looks like. Per-update work is bounded by the same
   * assertion: the estimate is a linear scan of this buffer. */
  const stress = await page.evaluate(async (n) => {
    const stats = await import(new URL('./viewer/stats.js', location.href).href);
    const S = window.__sim;
    const before = S.freqBuf.length;
    const t = S.frame.t;
    // Real-looking curvature, so this is not accidentally testing a degenerate path.
    for (let i = 0; i < n; i++) stats.updateFreq(0.9 * Math.sin(i * 0.21), t);
    const after = S.freqBuf.length;
    // Reset, which is what a clock going *backwards* means. The button clears these
    // buffers itself, but a reconnect to a restarted server does not -- and refusing a
    // sample older than the newest one held would then refuse every sample there will
    // ever be, leaving the readout frozen until the clock climbed back past a run that
    // is over. Backwards has to empty the buffer, and the next sample has to land.
    stats.updateFreq(0.4, t - 100);
    const rewound = S.freqBuf.length;
    stats.updateFreq(0.4, t - 99);
    return { calls: n, before, after, rewound, resumed: S.freqBuf.length };
  }, 3000);
  assert.ok(stress.after <= stress.before + 1,
    `${stress.calls} stats updates at one simulated timestamp grew the frequency buffer `
    + `from ${stress.before} to ${stress.after}`);
  assert.equal(stress.rewound, 1, 'a rewound clock did not clear the frequency buffer');
  assert.equal(stress.resumed, 2, 'the frequency buffer stopped accepting samples after a reset');

  await page.click('#b-play');
  await page.waitForFunction(
    t => window.__sim.frame?.running === 1 && window.__sim.frame.t > t + 0.01,
    { timeout: 5000 },
    stillAt,
  );
  const resumedAt = await page.evaluate(() => window.__sim.frame.t);
  assert.ok(resumedAt > stillAt);
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);

  console.log(
    `Python transport: ${transport.neurons} neurons, ${transport.muscles} muscles, ` +
    `${transport.fieldN}x${transport.fieldN} field, ${rendered.kymoFilled} kymograph columns.`,
  );
  console.log(
    `HTTP on ${httpPort}, socket on ${wsPort} (not ${httpPort + 1}); ` +
    `uterus holds ${transport.eggsHeld.toFixed(1)}, ${transport.eggsLaid.toFixed(0)} laid, ` +
    `${transport.plate ? transport.plate.n : 0} on the plate.`,
  );
  console.log(`Pause held at ${pausedAt.toFixed(3)} s; resume reached ${resumedAt.toFixed(3)} s.`);
  console.log(
    `Frequency buffer stayed at ${still.freq} entries through 500 ms of paused frames ` +
    `and ${stress.calls} stats calls at one timestamp.`,
  );
  console.log('The ?server viewer receives, renders, and controls the Python model.');
} catch (error) {
  const output = serverOutput.join('').trim();
  if (output) console.error(`Python server output:\n${output.slice(-4000)}`);
  throw error;
} finally {
  if (browser) await browser.close();
  await stopChild(child);
}
