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

// Width and height are CSS pixels; `dpr` is the display density, which changes none of
// them. It is here because the viewer draws into backing stores scaled by devicePixelRatio
// and hit-tests against layouts that are not, and a mistake about which of the two a
// coordinate is in is invisible at dpr 1 -- the factor is 1, so the wrong conversion and
// the right one agree. Every developer monitor that is not a laptop screen is dpr 1, and
// so is a default headless Chrome, which is how a hit test that only worked on the top-left
// quadrant of the panel shipped and survived this file.
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'hidpi',   width: 1440, height: 900, dpr: 2 },
  { name: 'tablet',  width: 768,  height: 1024 },
  { name: 'mobile',  width: 390,  height: 844 },
];

// Ids that must exist and be visible at every viewport. These are the controls, not the
// readouts: a missing readout is a bug, a missing control is an unusable page.
const REQUIRED = [
  'c-dish', 'b-play', 'b-reset', 'r-rate', 'r-scrub', 'b-poke-a', 'b-poke-p',
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
    await page.setViewport({
      width: vp.width, height: vp.height, deviceScaleFactor: vp.dpr || 1 });

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

      /* Pausing must not keep costing anything.
       *
       * The animation loop runs on requestAnimationFrame whether or not the engine
       * stepped, and both telemetry buffers -- the frequency history in stats.js and the
       * speed window here -- are trimmed by *simulated* time, so with the clock frozen
       * nothing in them ever ages out. They grew by sixty entries a second for as long as
       * the tab was left paused, and the frequency estimate rescans its buffer twice a
       * frame, so a paused viewer got steadily slower while the animal did nothing.
       *
       * A property, not a size: "a frozen clock adds no samples" fails immediately, where
       * a size check passes for however long the buffer takes to reach it. */
      const paused = await page.evaluate(async () => {
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const b = document.getElementById('b-play');
        if (b.getAttribute('aria-pressed') === 'true') b.click();   // pause
        await sleep(250);                                           // let the clock settle
        const S = window.__sim;
        const before = { t: S.frame.t, freq: S.freqBuf.length, speed: S.speedWin.length };
        await sleep(500);                                           // ~30 animation frames
        const after = { t: S.frame.t, freq: S.freqBuf.length, speed: S.speedWin.length };
        b.click();                                                  // back to playing
        return { before, after };
      });
      check(vp.name, paused.after.t === paused.before.t,
            `the clock advanced while paused: ${paused.before.t} -> ${paused.after.t}`);
      check(vp.name, paused.after.freq === paused.before.freq,
            `the frequency buffer grew ${paused.before.freq} -> ${paused.after.freq} `
            + 'with the clock frozen');
      check(vp.name, paused.after.speed === paused.before.speed,
            `the speed window grew ${paused.before.speed} -> ${paused.after.speed} `
            + 'with the clock frozen');

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

      /* Pointing at a neuron finds that neuron, at any display density.
       *
       * `neuronAt` converted the pointer by the ratio of the canvas's backing store to its
       * CSS box, but the layout it compares against is built in CSS pixels -- fitCanvas
       * scales the backing store by devicePixelRatio and puts the same factor into the
       * context transform, so it hands buildLayout the CSS size. The conversion was
       * therefore a multiplication by devicePixelRatio against coordinates that never had
       * it: a no-op at dpr 1, and a factor of two out on a HiDPI display, which is most
       * laptops. All 302 cells stayed reachable -- crammed into the top-left quadrant --
       * so nothing was missing, it was in the wrong place, and clicks in ablate mode
       * killed a neuron other than the one under the cursor.
       *
       * The claim is that the answer does not depend on the display. Which is exactly
       * right for a panel laid out in CSS pixels, and it is the only formulation of "the
       * hit test is correct" that does not need a second copy of the grid in this file:
       * probe the same fractions of the same panel at dpr 2 and dpr 1 and the two runs
       * must agree cell for cell. Coverage will not do it -- a uniform scale error moves
       * every cell without losing any, so sweeping still finds all 302.
       *
       * Only the CSS box has to hold still across the switch, and it does: dpr changes no
       * layout. It is asserted rather than assumed, because a probe comparison between two
       * differently-sized panels would be measuring the wrong disagreement.
       *
       * Driven through the real mousemove listener and read back from S.hover, which is
       * the viewer's actual cursor -- the one the highlight, the tooltip and Enter share.
       *
       * The same probe carries `neuronCentre`, the inverse of the hit test and the only
       * thing that knows where to put a tooltip for a cell reached by the arrow keys. It
       * held the *reciprocal* of the same mistake, which is why nothing caught it: fed
       * into neuronAt the two errors cancelled and the round trip came out right, so only
       * the tooltip's position on screen was wrong. Nothing else here reaches it -- it is
       * called from a keyboard path whose only visible effect is a tooltip the viewport
       * clamp can move -- but panels.js is a module the page has already imported, and
       * importing it again is the same instance and the same layout the panel is drawn
       * from. Density-independence is the claim for it too, so it rides the comparison.
       */
      const probeHover = () => page.evaluate(async () => {
        const S = window.__sim;
        const nc = document.getElementById('c-neurons');
        const { neuronCentre } = await import('/viewer/panels.js');
        // The collapse check above closed and reopened this very panel, and both the
        // layout and the backing store are resized in the render loop, not on the event.
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        const r = nc.getBoundingClientRect();
        const out = { dpr: window.devicePixelRatio, w: Math.round(r.width),
                      h: Math.round(r.height), sig: [], centres: [] };
        if (r.width < 4 || r.height < 4) return out;          // collapsed; nothing to hit
        // Fractions of the panel rather than pixel steps, so the probe is the same set of
        // points whatever the panel measures and two runs are comparable term by term.
        const COLS = 41, ROWS = 21;
        for (let b = 0; b < ROWS; b++) {
          for (let a = 0; a < COLS; a++) {
            nc.dispatchEvent(new MouseEvent('mousemove', {
              clientX: r.left + r.width * (a / (COLS - 1)),
              clientY: r.top + r.height * (b / (ROWS - 1)), bubbles: true }));
            out.sig.push(S.hover == null ? -1 : S.hover);
          }
        }
        // Relative to the panel, because the claim is about where in it a cell sits. And
        // pointing at the place it names has to come back to the cell it named, which is
        // the one way the two functions can be checked against each other rather than
        // against a copy of the grid -- but only one way, since it passes when both are
        // wrong by reciprocal factors, which is exactly how they were.
        out.roundTrip = 0;
        for (let i = 0; i < S.meta.neurons.length; i += 37) {
          const at = neuronCentre(nc, i);
          out.centres.push(at ? [Math.round(at.clientX - r.left),
                                 Math.round(at.clientY - r.top)] : null);
          if (!at) continue;
          nc.dispatchEvent(new MouseEvent('mousemove', {
            clientX: at.clientX, clientY: at.clientY, bubbles: true }));
          if (S.hover !== i) out.roundTrip++;
        }
        nc.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));
        return out;
      });

      const hover = await probeHover();
      check(vp.name, hover.w >= 4 && hover.h >= 4,
            `the neuron panel measured ${hover.w}x${hover.h} -- it never reopened`);
      /* Much of the panel answers at all. A floor, not a measurement: it is here so the
       * comparison below is between two live hit tests rather than two silent ones, and
       * so an error that is the *same* at both densities is not invisible to both checks.
       *
       * 0.4 is placed by what the two states look like, not by what a healthy panel
       * scores. A uniform scale error of k confines every answer to 1/k^2 of the panel --
       * a quarter of it at dpr 2, and 0.19 was measured -- while a panel whose hit test
       * agrees with its drawing answers wherever there is a cell, which was 0.64 at the
       * widest, shortest panel here and 0.79 at the rest. Anything between separates them;
       * the rest of the gap is grid packing, which is not what this is asking about.
       */
      const answered = hover.sig.filter((i) => i >= 0).length;
      check(vp.name, hover.sig.length > 0 && answered > hover.sig.length * 0.4,
            `only ${answered} of ${hover.sig.length} points across the neuron panel `
            + 'named a neuron: most of the panel is not hit-testing at all');
      check(vp.name, hover.roundTrip === 0,
            `${hover.roundTrip} of ${hover.centres.length} neurons did not answer at the `
            + 'position neuronCentre puts them: the tooltip a keyboard cursor raises is '
            + 'not over the cell it describes');
      // neuronCentre answers from the module's own `layout`, so a second instance of the
      // module -- a moved file, an import specifier that no longer resolves to the one the
      // page loaded -- would return null for every cell, and both of the checks that use
      // it would pass by asking nothing. That has to fail rather than go quiet.
      check(vp.name, hover.centres.length > 0 && hover.centres.every((c) => c),
            `${hover.centres.filter((c) => !c).length} of ${hover.centres.length} neurons `
            + 'have no position at all: the panels.js this imported is not the one the '
            + 'page is drawing from, and the two checks above are inspecting nothing');

      if (vp.dpr) {
        await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 });
        const lo = await probeHover();
        await page.setViewport({
          width: vp.width, height: vp.height, deviceScaleFactor: vp.dpr });
        check(vp.name, lo.w === hover.w && lo.h === hover.h,
              `the panel changed size with the density (${hover.w}x${hover.h} at dpr `
              + `${hover.dpr}, ${lo.w}x${lo.h} at dpr ${lo.dpr}) -- nothing below is `
              + 'comparing what it means to');
        const moved = hover.centres.reduce(
          (k, c, j) => k + (String(c) === String(lo.centres[j]) ? 0 : 1), 0);
        check(vp.name, moved === 0,
              `${moved} of ${hover.centres.length} neurons sit somewhere else in the panel `
              + `at dpr ${hover.dpr} than at dpr ${lo.dpr} (${hover.centres[1]} vs `
              + `${lo.centres[1]}): neuronCentre is anchoring tooltips in the wrong units`);
        const differ = hover.sig.reduce((k, v, j) => k + (v === lo.sig[j] ? 0 : 1), 0);
        check(vp.name, differ === 0,
              `${differ} of ${hover.sig.length} points across the neuron panel named a `
              + `different neuron at dpr ${hover.dpr} than at dpr ${lo.dpr}: the hit test `
              + 'is reading the pointer in backing-store pixels against a CSS-pixel layout');
      }

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

      /* Focus survives a removal that did not come from the delete button.
       *
       * `#b-worm-del` clamps `S.focus` itself, so every path a person can click keeps the
       * controls honest. The renderer's own clamp did not -- it moved focus without
       * rebuilding the selector, the neuron hint or Restore, leaving all three describing
       * the animal that had just left. Unreachable through the UI, and reachable the
       * moment anything else changes the population, which is what a generational loop is.
       *
       * So this removes an animal the way such a loop would: `engine.removeWorm()`
       * directly, never touching the button. Two frames are waited on because the clamp
       * runs inside the render loop, not inside the removal.
       */
      const cull = await page.evaluate(async () => {
        const S = window.__sim;
        const $ = (id) => document.getElementById(id);
        const buttons = () => [...document.querySelectorAll('#worm-sel button')];
        const out = { ran: false };
        if (!S.engine || S.engine.worms.length < 2) return out;

        /* Start from three animals so the population is still plural after one leaves. The
         * neuron hint appends "in worm K" only when more than one animal is on the plate,
         * so a 2 -> 1 removal changes the wording for a reason that has nothing to do with
         * focus, and the comparison below would be reading that instead. */
        $('b-worm-add').click();

        /* What the controls say when worm 0 is focused *deliberately*, through the button
         * that already does this correctly. That is the answer the clamp has to arrive at,
         * and taking it by measurement rather than by assumption keeps this independent of
         * whatever the checks above left ablated. */
        buttons()[0].click();
        out.deliberate = { hint: $('neuron-hint').textContent,
                           restore: $('b-restore').disabled };

        // Now focus the last animal and ablate a cell in it, so the panels are saying
        // something specific about an animal that is about to stop existing.
        const last = S.engine.worms.length - 1;
        buttons()[last].click();
        $('b-ablate').click();
        S.hover = 12;
        $('c-neurons').dispatchEvent(
          new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        $('b-ablate').click();
        out.before = { focus: S.focus, hint: $('neuron-hint').textContent,
                       restore: $('b-restore').disabled };

        S.engine.removeWorm();                     // <- not the button. This is the point.
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

        const bs = buttons();
        out.ran = true;
        out.n = S.engine.worms.length;
        out.focus = S.focus;
        out.inRange = S.focus >= 0 && S.focus < out.n;
        out.buttons = bs.length;
        // The selector must mark exactly the focused animal, and no other.
        out.pressed = bs.map((b) => b.getAttribute('aria-pressed') === 'true');
        out.hint = $('neuron-hint').textContent;
        out.restore = $('b-restore').disabled;
        return out;
      });
      check(vp.name, cull.ran, 'the focus-clamp check did not run: fewer than two worms');
      if (cull.ran) {
        /* The two animals have to be *distinguishable* through the controls, or every
         * assertion below would pass whether or not the clamp rebuilt anything. This is
         * the check on the check: the departing animal must say something the remaining
         * one does not. */
        check(vp.name, cull.before.hint !== cull.deliberate.hint,
              `both animals report the same neuron hint ("${cull.before.hint}"), so this`
              + ' check cannot tell whether the panels were rebuilt');
        check(vp.name, cull.inRange, `focus ${cull.focus} is outside 0..${cull.n - 1}`);
        check(vp.name, cull.buttons === cull.n,
              `${cull.buttons} worm buttons for ${cull.n} animals -- the selector was not`
              + ' rebuilt after a removal from outside the controls');
        check(vp.name, cull.pressed.filter(Boolean).length === 1 && cull.pressed[cull.focus],
              `aria-pressed is ${JSON.stringify(cull.pressed)} with focus ${cull.focus}:`
              + ' the highlighted animal is not the focused one');
        /* And the panels have to land where focusing that animal on purpose lands. Before
         * the fix they kept describing the animal that had just been removed. */
        check(vp.name, cull.hint === cull.deliberate.hint,
              `after the removal the neuron hint reads "${cull.hint}"; focusing the same`
              + ` animal through the selector gives "${cull.deliberate.hint}"`);
        check(vp.name, cull.restore === cull.deliberate.restore,
              `after the removal Restore disabled=${cull.restore}; focusing the same animal`
              + ` through the selector gives ${cull.deliberate.restore}`);
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

    /* The scrubber shows the past, and not an alias of the present.
     *
     * Desktop only, because it needs several seconds of history and the assertion is about
     * the ring rather than about the layout.
     *
     * The failure this is really guarding is subtle and would look exactly like success.
     * `LocalEngine.frame(i)` returns `act`, `V`, `tension` and `kappa` as Float64Array
     * *views into WASM linear memory*, so a ring that stored those objects rather than
     * copies would hold N aliases of one live animal, and every scrubber position would
     * show the current neurons and muscles.
     *
     * Which array this asserts on is the whole check, and the first version of it was
     * wrong. Asserting on `nodes` proves nothing: `frame(i)` already allocates a fresh
     * Float32Array for the centreline on every call, so the body positions are copies
     * whether or not this ring copies anything. Removing the copy step entirely and
     * re-running left every assertion here passing. `t` is no better -- a plain number is
     * copied either way.
     *
     * So it asserts on `V`, which is one of the four genuine views. Watched to fail with
     * `copy` replaced by the identity function, which is the bug in question.
     */
    if (vp.name === 'desktop') {
      const scrub = await page.evaluate(async () => {
        const H = await import('./viewer/history.js');
        const S = window.__sim;
        const slider = document.getElementById('r-scrub');
        const frameNow = () => ({
          t: S.frame ? S.frame.t : null,
          x: S.worms[0] ? S.worms[0].nodes[0] : null,
          // One of the four arrays the engine hands out as a view into WASM memory. This
          // is the field that can tell a copied ring from an aliased one.
          v: S.worms[0] ? S.worms[0].V[0] : null,
        });
        const settle = () => new Promise((r) =>
          requestAnimationFrame(() => requestAnimationFrame(r)));

        const live = frameNow();
        const held = H.count();
        const budget = H.BUDGET_BYTES;
        const bytes = H.stats().bytes;

        slider.value = '0';
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        await settle();
        const past = frameNow();
        const parked = S.playhead;
        const playText = document.getElementById('b-play').textContent;

        slider.value = String(slider.max);
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        await settle();
        return { live, past, held, parked, playText, bytes, budget,
                 backToLive: S.playhead };
      });

      // A floor, not a target. By the time this runs the page has been up for a second or
      // so, which is tens of frames, and the assertions that matter are the ones below --
      // this one only catches a ring that is not recording at all, where "the scrubbed
      // frame equals the live frame" would pass for the trivial reason that there is only
      // one frame in it.
      check(vp.name, scrub.held > 20, `the history ring holds only ${scrub.held} frames`);
      check(vp.name, scrub.parked === 0, 'dragging the scrubber did not park the playhead');
      check(vp.name, scrub.past.t !== null && scrub.past.t < scrub.live.t,
        `scrubbing back showed t=${scrub.past.t}, not before the live t=${scrub.live.t}`);
      check(vp.name, scrub.past.v !== scrub.live.v,
        `the scrubbed frame reports the live membrane potential (${scrub.live.v}): the ring `
        + 'is holding views into WASM memory rather than copies, so every scrubber position '
        + 'shows the current neurons and muscles');
      check(vp.name, scrub.past.x !== scrub.live.x,
        'the scrubbed body is at the live body\'s coordinates');
      check(vp.name, scrub.playText === 'Play', 'scrubbing did not pause the engine');
      check(vp.name, scrub.bytes <= scrub.budget,
        `the ring holds ${scrub.bytes} bytes, over its ${scrub.budget} budget`);
      check(vp.name, scrub.backToLive === null,
        'dragging the scrubber to the end did not return the viewer to live');
    }

    console.log(`  ${vp.name.padEnd(8)} ${vp.width}x${vp.height}@${vp.dpr || 1}x  ` +
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
