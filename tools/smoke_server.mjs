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

async function freePortPair() {
  for (let attempt = 0; attempt < 20; attempt++) {
    const http = net.createServer();
    try {
      await listen(http, 0);
      const port = http.address().port;
      if (port >= 65535) {
        await close(http);
        continue;
      }
      const ws = net.createServer();
      try {
        await listen(ws, port + 1);
        await close(ws);
        await close(http);
        return port;
      } catch {
        if (ws.listening) await close(ws);
        await close(http);
      }
    } catch {
      if (http.listening) await close(http);
    }
  }
  throw new Error('could not find a free consecutive HTTP/WebSocket port pair');
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

const httpPort = await freePortPair();
const wsPort = httpPort + 1;
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

  await page.goto(`${base}?server&debug`, { waitUntil: 'load' });
  await page.waitForFunction(
    () => window.__sim?.connected && window.__sim?.meta && window.__sim?.frame
      && window.__sim?.field && document.getElementById('banner').classList.contains('gone'),
    { timeout: 30000 },
  );

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
  const pausedAt = await page.evaluate(() => window.__sim.frame.t);
  await delay(500);
  const stillAt = await page.evaluate(() => window.__sim.frame.t);
  assert.ok(Math.abs(stillAt - pausedAt) < 1e-6, `clock advanced while paused: ${pausedAt} -> ${stillAt}`);

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
  console.log(`Pause held at ${pausedAt.toFixed(3)} s; resume reached ${resumedAt.toFixed(3)} s.`);
  console.log('The ?server viewer receives, renders, and controls the Python model.');
} catch (error) {
  const output = serverOutput.join('').trim();
  if (output) console.error(`Python server output:\n${output.slice(-4000)}`);
  throw error;
} finally {
  if (browser) await browser.close();
  await stopChild(child);
}
