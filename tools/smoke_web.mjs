/* A browser smoke test for the viewer.
 *
 * The viewer has no build step and no unit tests, which means the failure mode it is most
 * exposed to is the one nothing catches: a typo in a module, a renamed id, a stylesheet
 * rule that hides a control, and the page loads to a black rectangle. `tools/check_web.mjs`
 * catches the graph errors statically; this catches the rest by actually loading the page
 * in Chrome and looking at it.
 *
 * Deliberately *not* a behavioural test of the simulation. It asserts that the viewer
 * loads, that the controls exist and respond, and that nothing logged an error -- claims
 * that stay true whatever the animal happens to do. The science is tested in tests/ and in
 * wasm/conform.mjs, which is where a behavioural assertion belongs.
 *
 *   node tools/smoke_web.mjs
 *   CHROME=/path/to/chrome node tools/smoke_web.mjs
 */

import fs from 'fs';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';
import puppeteer from 'puppeteer-core';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const WEB = path.join(ROOT, 'web');

/* --- find a Chrome --------------------------------------------------------------- */
// CI runners have one preinstalled; a developer machine usually has one of these. The
// point of puppeteer-core over puppeteer is that nothing downloads 150 MB of browser on
// `npm ci`.
function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const guesses = [
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ];
  for (const g of guesses) if (fs.existsSync(g)) return g;
  // Playwright's cache, which many machines already have.
  const pw = path.join(process.env.HOME || '', 'Library/Caches/ms-playwright');
  const lin = path.join(process.env.HOME || '', '.cache/ms-playwright');
  for (const base of [pw, lin]) {
    if (!fs.existsSync(base)) continue;
    for (const d of fs.readdirSync(base)) {
      for (const rel of ['chrome-headless-shell-mac-arm64/chrome-headless-shell',
                         'chrome-headless-shell-mac-x64/chrome-headless-shell',
                         'chrome-headless-shell-linux/chrome-headless-shell',
                         'chrome-mac/Chromium.app/Contents/MacOS/Chromium',
                         'chrome-linux/chrome']) {
        const p = path.join(base, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return null;
}

/* --- serve web/ ------------------------------------------------------------------ */

const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.wasm': 'application/wasm', '.model': 'application/octet-stream',
};

function serve() {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split('?')[0]);
    const rel = url === '/' ? 'index.html' : url.replace(/^\/+/, '');
    const file = path.join(WEB, rel);
    if (!file.startsWith(WEB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end('not found'); return;
    }
    res.writeHead(200, {
      'content-type': TYPES[path.extname(file)] || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((r) => server.listen(0, '127.0.0.1', () => r(server)));
}

/* --- the checks ------------------------------------------------------------------ */

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet',  width: 768,  height: 1024 },
  { name: 'mobile',  width: 390,  height: 844 },
];

// Ids that must exist and be visible at every viewport. These are the controls, not the
// readouts: a missing readout is a bug, a missing control is an unusable page.
const REQUIRED = [
  'c-dish', 'b-play', 'b-reset', 'r-rate', 'b-poke-a', 'b-poke-p',
  'b-ablate', 'b-restore', 'b-worm-add', 'b-worm-del', 'b-rail',
  'b-centre', 'b-zin', 'b-zout',
];

const failures = [];
function check(where, ok, msg) {
  if (!ok) failures.push(`${where}: ${msg}`);
}

const chrome = findChrome();
if (!chrome) {
  console.error('no Chrome found. Set CHROME=/path/to/chrome.');
  process.exit(2);
}

const server = await serve();
const base = `http://127.0.0.1:${server.address().port}/`;
const browser = await puppeteer.launch({
  executablePath: chrome,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

try {
  for (const vp of VIEWPORTS) {
    const page = await browser.newPage();
    await page.setViewport({ width: vp.width, height: vp.height });

    const errors = [], failed = [];
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('requestfailed', (r) => failed.push(`${r.url()} ${r.failure()?.errorText}`));
    page.on('response', (r) => { if (r.status() >= 400) failed.push(`${r.url()} -> ${r.status()}`); });

    await page.goto(base + '?debug', { waitUntil: 'load' });

    // The engine has to come up. This is not a behavioural assertion -- it is "the WASM
    // loaded and the loop is running", which is the thing a blank page fails.
    const started = await page.waitForFunction(
      () => window.__sim && window.__sim.meta && !!document.getElementById('s-time'),
      { timeout: 30000 },
    ).then(() => true).catch(() => false);
    check(vp.name, started, 'the local engine never produced a frame');

    check(vp.name, errors.length === 0, `console errors: ${errors.slice(0, 3).join(' | ')}`);
    check(vp.name, failed.length === 0, `failed requests: ${failed.slice(0, 3).join(' | ')}`);

    const missing = await page.evaluate((ids) => ids.filter((id) => {
      const e = document.getElementById(id);
      if (!e) return true;
      const r = e.getBoundingClientRect();
      return r.width < 1 || r.height < 1;
    }), REQUIRED);
    check(vp.name, missing.length === 0, `controls missing or invisible: ${missing.join(', ')}`);

    // Every layer toggle stays reachable at every width. This is the regression that
    // prompted the check: they used to be display:none below 1080px.
    //
    // Counted against however many the page declares, not against a fixed number. The
    // invariant is "none of them is hidden", and hardcoding the count meant that adding a
    // layer failed the check for the one reason it is not looking for.
    const layers = await page.evaluate(() => {
      const all = [...document.querySelectorAll('[data-layer]')];
      return { total: all.length, shown: all.filter((e) => e.getBoundingClientRect().width > 0).length };
    });
    check(vp.name, layers.total > 0, 'no layer toggles in the page at all');
    check(vp.name, layers.shown === layers.total,
          `${layers.shown} of ${layers.total} layer toggles visible`);

    // Nothing may push the page sideways.
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(vp.name, overflow <= 0, `${overflow}px of horizontal overflow`);

    if (started) {
      // Playback: the button is a toggle and has to say so.
      const play = await page.evaluate(() => {
        const b = document.getElementById('b-play');
        const before = b.getAttribute('aria-pressed');
        b.click();
        const after = b.getAttribute('aria-pressed');
        b.click();
        return { before, after, label: b.textContent.trim() };
      });
      check(vp.name, play.before !== play.after, 'Pause did not change aria-pressed');

      // Theme: three looks, and the pressed state follows.
      const themed = await page.evaluate(() => {
        const out = [];
        for (const v of ['cartoon', 'realistic', 'digital']) {
          const b = document.querySelector(`[data-view="${v}"]`);
          b.click();
          out.push(window.__sim.theme === v && b.getAttribute('aria-pressed') === 'true');
        }
        return out;
      });
      check(vp.name, themed.every(Boolean), 'a view mode did not take');

      // Collapsing a panel has to report its state, not just look different.
      const panel = await page.evaluate(() => {
        const h = document.querySelector('.panel .phead');
        const a = h.getAttribute('aria-expanded');
        h.click();
        const b = h.getAttribute('aria-expanded');
        h.click();
        return { a, b, c: h.getAttribute('aria-expanded') };
      });
      check(vp.name, panel.a === 'true' && panel.b === 'false' && panel.c === 'true',
            `aria-expanded went ${panel.a} -> ${panel.b} -> ${panel.c}`);

      // Touch targets, on the layouts that are touch-oriented.
      if (vp.width <= 1080) {
        const small = await page.evaluate(() =>
          [...document.querySelectorAll('button, input[type=range], [tabindex]')]
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0; })
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width < 44 || r.height < 44; })
            .map((e) => e.id || e.textContent.trim().slice(0, 12)));
        check(vp.name, small.length === 0, `targets under 44px: ${small.join(', ')}`);
      }

      // Every control has to have a name a screen reader can read out.
      const unnamed = await page.evaluate(() =>
        [...document.querySelectorAll('button, input')]
          .filter((e) => e.getBoundingClientRect().width > 0)
          .filter((e) => !(e.getAttribute('aria-label') || e.textContent.trim()
                           || (e.labels && e.labels.length)))
          .map((e) => e.id || e.outerHTML.slice(0, 40)));
      check(vp.name, unnamed.length === 0, `controls with no accessible name: ${unnamed.join(', ')}`);
    }

    console.log(`  ${vp.name.padEnd(8)} ${vp.width}x${vp.height}  ` +
                `${errors.length} console errors, ${failed.length} failed requests, ` +
                `${layers.shown}/${layers.total} layers, ${overflow}px overflow`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}

if (failures.length) {
  console.log('');
  for (const f of failures) console.log(`  FAIL  ${f}`);
  console.log(`\n${failures.length} smoke failure(s).`);
  process.exit(1);
}
console.log('\nThe viewer loads, runs and responds at every viewport checked.');
