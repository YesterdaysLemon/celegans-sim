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
const FINDING_EXIT = 10;

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

      /* Ablation, with two animals on the plate.
       *
       * The one exception to "nothing here asserts what the animal does", and it is not
       * really an exception: the claim is that the controls describe the animal they name.
       * Ablation is applied to one worm, so a viewer that keeps a single ablated-cell set
       * silently ablates, displays and restores the wrong subject -- which is what #46
       * was: Restore emptied the shared record while restoring whichever animal happened
       * to be focused, leaving the ablated one ablated with nothing that knew it. That is
       * invisible to every other check in this file, because the page loads, the buttons
       * respond, and only the *subject* is wrong.
       *
       * Driven through the real listeners -- the Ablate toggle, the worm selector, the
       * Restore button, the neuron panel's Enter -- with one concession: the keyboard
       * cursor is placed by writing S.hover rather than by clicking a cell, because
       * hit-testing the neuron canvas from out here would mean keeping a second copy of
       * the panel's grid layout in this file. S.hover *is* that cursor; the handler under
       * test is the same one a keypress reaches.
       *
       * Read back from E.isAlive, not from the viewer's own record: the bug being caught
       * is precisely the two disagreeing.
       */
      const abl = await page.evaluate(() => {
        const S = window.__sim;
        const $ = (id) => document.getElementById(id);
        const worm = (k) => document.querySelectorAll('#worm-sel button')[k];
        const nc = $('c-neurons');
        const kill = (i) => {                       // ablate cell i in the focused animal
          $('b-ablate').click();
          S.hover = i;
          nc.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
          $('b-ablate').click();
        };
        const dead = (k, i) => S.engine.E.isAlive(S.engine.worms[k], i) === 0;
        const hint = () => $('neuron-hint').textContent;
        const out = { worms: S.engine ? S.engine.worms.length : 0 };
        if (out.worms < 2 || !worm(1)) return out;

        worm(0).click();
        kill(4);
        out.ablated = { one: dead(0, 4), two: dead(1, 4), hint: hint(),
                        restore: $('b-restore').disabled };

        worm(1).click();                            // an intact animal has nothing to undo
        out.switched = { hint: hint(), restore: $('b-restore').disabled };

        kill(9);
        out.both = { one: dead(0, 4), two: dead(1, 9), restore: $('b-restore').disabled };

        $('b-restore').click();                     // ...restores worm 2, and only worm 2
        out.restored = { one: dead(0, 4), two: dead(1, 9), restore: $('b-restore').disabled };

        worm(0).click();                            // and worm 1's record survived all of it
        out.back = { one: dead(0, 4), hint: hint(), restore: $('b-restore').disabled };

        /* Then the other half of "per animal": an animal that leaves takes its ablations
         * with it. Worm 2 is ablated, removed, and a replacement added into the position
         * it vacated -- a different animal, so it starts intact and the controls have to
         * say so. Keying the record by position rather than by the runtime's id passes
         * everything above and fails here, which is the point of testing it: the two
         * schemes are indistinguishable until the population changes.
         */
        worm(1).click();
        kill(7);
        $('b-worm-del').click();
        $('b-worm-add').click();                    // adding focuses the new animal
        out.replaced = { n: S.engine.worms.length, focus: S.focus, hint: hint(),
                         restore: $('b-restore').disabled,
                         intact: !dead(S.focus, 7), records: S.ablations.size };
        return out;
      });
      check(vp.name, abl.worms >= 2, `the dish started with ${abl.worms} worms, not two`);
      if (abl.ablated) {
        check(vp.name, abl.ablated.one && !abl.ablated.two,
              `ablating worm 1 left worm 1 ${abl.ablated.one ? 'dead' : 'alive'}`
              + ` and worm 2 ${abl.ablated.two ? 'dead' : 'alive'}`);
        // The wording is not the claim; naming a count for the focused animal is.
        check(vp.name, /ablated/.test(abl.ablated.hint) && !abl.ablated.restore,
              `after ablating: hint "${abl.ablated.hint}", Restore disabled=${abl.ablated.restore}`);
        check(vp.name, abl.switched.restore && !/ablated/.test(abl.switched.hint),
              `focusing the intact worm still offered Restore ("${abl.switched.hint}")`
              + ' -- the ablation record is not per animal');
        check(vp.name, abl.both.one && abl.both.two && !abl.both.restore,
              'ablating in worm 2 did not stick, or disturbed worm 1');
        check(vp.name, abl.restored.one && !abl.restored.two && abl.restored.restore,
              `Restore on worm 2 left worm 1 ${abl.restored.one ? 'dead' : 'restored'}`
              + ` and worm 2 ${abl.restored.two ? 'dead' : 'restored'}`);
        check(vp.name, abl.back.one && !abl.back.restore && /ablated/.test(abl.back.hint),
              `back on worm 1: still dead=${abl.back.one}, hint "${abl.back.hint}",`
              + ` Restore disabled=${abl.back.restore}`);
        check(vp.name, abl.replaced.intact && abl.replaced.restore
                       && !/ablated/.test(abl.replaced.hint),
              `the worm added after a removal arrived ablated: intact=${abl.replaced.intact},`
              + ` hint "${abl.replaced.hint}", Restore disabled=${abl.replaced.restore}`);
        // And the records do not outlive the animals. Nothing looks wrong on screen when
        // they do -- ids are never reused, so a leftover is inert -- but a viewer left
        // open through a few hundred add/removes should not be keeping a set per animal
        // that ever lived.
        check(vp.name, abl.replaced.records <= abl.replaced.n,
              `${abl.replaced.records} ablation records for ${abl.replaced.n} worms`);
      }

      // Touch targets, on the layouts that are touch-oriented.
      if (vp.width <= 1080) {
        const small = await page.evaluate(() =>
          [...document.querySelectorAll('button, input[type=range], [tabindex]')]
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0; })
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width < 44 || r.height < 44; })
            .map((e) => e.id || e.textContent.trim().slice(0, 12)));
        check(vp.name, small.length === 0, `targets under 44px: ${small.join(', ')}`);
      }

      // Every control needs a name a screen reader can read out, and the name has to
      // identify it. Those are different requirements and this check used to test only
      // the first: stripped of its aria-label, `<button id="b-worm-add">+</button>` has
      // the accessible name "+", which is non-empty and therefore passed -- while being
      // the same name as the zoom-in button, which is the exact ambiguity the label was
      // added to remove. A coverage audit caught it by deleting the label and watching
      // nothing happen.
      const names = await page.evaluate(() =>
        [...document.querySelectorAll('button, input')]
          .filter((e) => e.getBoundingClientRect().width > 0)
          .map((e) => ({
            id: e.id || e.outerHTML.slice(0, 40),
            name: (e.getAttribute('aria-label')
                   || (e.labels && e.labels.length ? e.labels[0].textContent : '')
                   || e.textContent || '').trim(),
          })));
      const unnamed = names.filter((e) => !e.name).map((e) => e.id);
      check(vp.name, unnamed.length === 0, `controls with no accessible name: ${unnamed.join(', ')}`);

      // And the name has to be words. A button whose entire accessible name is "+" or "-"
      // or "x" is a button that has been labelled with its own glyph, which tells a screen
      // reader nothing -- it is the icon, read aloud. Requiring a letter is the cheapest
      // rule that separates "Zoom in" from "+", and it is what the two `+`/`-` pairs in the
      // footer and the dish needed in the first place.
      const glyphOnly = names.filter((e) => e.name && !/\p{L}/u.test(e.name))
                             .map((e) => `${e.id}="${e.name}"`);
      check(vp.name, glyphOnly.length === 0,
            `controls named only by their glyph: ${glyphOnly.join(', ')}`);

      // Uniqueness, over the controls that have a name at all. Two buttons that read out
      // identically are two buttons nobody can tell apart without seeing the screen.
      const seen = new Map();
      for (const e of names) {
        if (!e.name) continue;
        seen.set(e.name.toLowerCase(), (seen.get(e.name.toLowerCase()) || []).concat(e.id));
      }
      const dupes = [...seen.entries()].filter(([, ids]) => ids.length > 1)
        .map(([n, ids]) => `"${n}" x${ids.length} (${ids.join('/')})`);
      check(vp.name, dupes.length === 0, `controls sharing an accessible name: ${dupes.join('; ')}`);
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
  // Keep assertion findings distinct from Puppeteer, Chrome, server, and script crashes.
  process.exit(FINDING_EXIT);
}
console.log('\nThe viewer loads, runs and responds at every viewport checked.');
