/* celegans-sim viewer -- bootstrap.
 *
 * The viewer is a set of native ES modules under ./viewer/, with no build step and no
 * dependencies. This file does one thing: choose a transport, wire the controls, and start
 * the animation loop. If you are looking for the code that draws or handles something, the
 * module boundaries are documented in web/README.md; the short version is
 *
 *   viewer/state.js       shared state, DOM helpers, canvas fitting   (imports nothing)
 *   viewer/scales.js      colour ramps
 *   viewer/themes.js      the three dish palettes
 *   viewer/worm.js        body geometry and the three body painters
 *   viewer/dish.js        plate, fields, overlays, camera transforms
 *   viewer/panels.js      neurons, muscle, kymograph, traces, receptor bars
 *   viewer/stats.js       header readouts, undulation frequency, legend
 *   viewer/history.js     the bounded ring of past frames the scrubber reads (imports nothing)
 *   viewer/controls.js    every event listener, and the UI state that goes with them
 *   viewer/transport.js   the WebSocket feed and the command seam, send()
 *   viewer/loop.js        the local engine read-out and requestAnimationFrame
 *
 * Dependencies point down that list, never up.
 */

import { LocalEngine } from './local.js';
import { ArenaEngine } from './arena-engine.js';
import { S, el } from './viewer/state.js';
import { wire, goLive } from './viewer/controls.js';
import { connect } from './viewer/transport.js';
import { start } from './viewer/loop.js';
import { reset as historyReset } from './viewer/history.js';

/* Local by default: the point of the WASM port is that no server is involved. `?server`
 * falls back to the WebSocket feed, which is still how the Python model is driven. */
if (location.search.includes('debug')) window.__sim = S;   // for poking from the console
wire();

/* One instrument, two plates. Each dish is its own engine -- its own WebAssembly
 * instance, its own world -- and the tabs swap which one feeds the loop. The hidden dish
 * simply stops being advanced (loop.js only steps S.engine), so it holds its state and
 * resumes mid-evolution when you tab back; that it PAUSES rather than runs hidden is a
 * deliberate choice, because both engines share one main thread and one 7 ms budget.
 *
 * The arena engine is built lazily on first visit: most sessions are about the animal,
 * and the second instance costs real megabytes. */
const engines = { animal: null, arena: null };
/* Per-dish view and layer defaults. The arena opens with the whole economy in frame and
 * the attractant layer off -- three lawns' plumes tint the entire plate blue at dish
 * zoom and drown the food that the dish is actually about; the chip turns it back on.
 * Defaults are re-applied on every switch so each dish opens the same way each time. */
const DISH_VIEW = { animal: { span: 6.5, cam: 'follow', layers: { attractant: true } },
                    arena: { span: 26, cam: 'free', layers: { attractant: false } } };

async function switchDish(name) {
  if (S.playhead !== null) goLive();
  if (!engines[name]) {
    el('banner').classList.remove('gone');
    el('banner').firstElementChild.innerHTML = name === 'arena'
      ? '<b>Opening the arena&hellip;</b>a second dish, its own world'
      : '<b>Loading the animal&hellip;</b>302 neurons, compiled to WebAssembly';
    try {
      engines[name] = name === 'arena'
        ? await new ArenaEngine().init()
        : await new LocalEngine().init(2);
    } catch (err) {
      el('banner').firstElementChild.innerHTML =
        `<b>Could not start the ${name} engine</b>${err}`;
      console.error(err);
      return;
    }
    el('banner').classList.add('gone');
  }
  /* Everything accumulated is about the other dish's animals: panels, trails, ring,
   * frequency and speed windows all start over. S.meta = null is the reset signal
   * loop.js already honours -- it rebuilds the selector, the traces and the trails on
   * the next frame, exactly as it does on first boot. */
  S.engine = engines[name];
  S.meta = null;
  S.worms = []; S.trails = []; S.trail = [];
  if (S._trailById) S._trailById.clear();
  S.kymo = null; S.freqBuf = []; S.speedWin = [];
  S.corpses = null; S.field = null;
  S.focus = 0;
  historyReset();
  const v = DISH_VIEW[name];
  S.view.span = v.span; S.view.cx = 0; S.view.cy = 0;
  S.cam = v.cam;
  S.recentre = v.cam === 'follow';
  for (const [k, on] of Object.entries(v.layers)) {
    S.layers[k] = on;
    const chip = document.querySelector(`.chip[data-layer="${k}"]`);
    if (chip) chip.setAttribute('aria-pressed', String(on));
  }
  el('app').dataset.dish = name;
  el('brand-sub').innerHTML = name === 'arena'
    ? 'descent with modification on a finite plate'
    : '<em>C.&nbsp;elegans</em> &mdash; 302 neurons, 95 muscles, one dish';
  el('o-zoom').textContent = `${S.view.span.toFixed(1)} mm`;
}

if (location.search.includes('server')) {
  el('dish-tabs').style.display = 'none';    // the socket feeds one animal; no second dish
  // Preserve needs the local engine to read genes and morphology; over the socket there
  // is none, and an enabled button that silently does nothing is worse than a disabled
  // one that says why (#138).
  const pv = el('b-preserve');
  pv.disabled = true;
  pv.title = 'Preserving needs the local engine; the ?server feed has no worm state '
    + 'to read. Load the viewer without ?server to preserve specimens.';
  // The dropper's repellent bottle and the tweezers are local-engine tools too: the
  // socket protocol has neither command. The dropper hides (double-click still drops a
  // lawn, which the protocol does have) and the hint stops advertising the tweezers.
  el('dropper').style.display = 'none';
  el('dish-hint').innerHTML =
    'drag to pan &middot; scroll to zoom &middot; double&#8209;click to drop a lawn';
  connect();
} else {
  S.switchDish = switchDish;
  el('app').dataset.dish = 'animal';
  const first = location.hash === '#arena' ? 'arena' : 'animal';
  if (first === 'arena') {
    document.querySelectorAll('[data-dish]').forEach((o) =>
      o.setAttribute('aria-pressed', String(o.dataset.dish === 'arena')));
  }
  el('banner').firstElementChild.innerHTML =
    '<b>Loading the animal&hellip;</b>302 neurons, compiled to WebAssembly';
  switchDish(first).catch((err) => {
    el('banner').firstElementChild.innerHTML =
      `<b>Could not start the local engine</b>${err}<code>?server</code>`;
    console.error(err);
  });
}
start();
