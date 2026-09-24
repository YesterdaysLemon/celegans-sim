/* celegans-sim viewer -- bootstrap.
 *
 * The viewer is a set of native ES modules under ./viewer/, with no build step and no
 * dependencies. This file does one thing: choose a transport, wire the controls, and start
 * the animation loop. If you are looking for the code that draws or handles something, the
 * module boundaries are documented in web/README.md; the short version is
 *
 *   viewer/state.js       shared state, DOM helpers, canvas fitting   (imports nothing)
 *   viewer/scales.js      colour ramps
 *   viewer/themes.js      the two dish palettes
 *   viewer/worm.js        body geometry and the two body painters
 *   viewer/dish.js        plate, fields, overlays, camera transforms
 *   viewer/panels.js      neurons, muscle, kymograph, traces, receptor bars
 *   viewer/stats.js       header readouts, undulation frequency, legend
 *   viewer/history.js     the bounded ring of past frames the scrubber reads (imports nothing)
 *   viewer/gestures.js    the dish canvas's gestures and the pipette
 *   viewer/controls.js    every other event listener, and the UI state that goes with them
 *   viewer/transport.js   the WebSocket feed and the command seam, send()
 *   viewer/loop.js        the local engine read-out and requestAnimationFrame
 *
 * Dependencies point down that list, never up.
 */

import { LocalEngine } from './local.js';
import { loadSeed } from './deal.js';
import { ArenaEngine } from './arena-engine.js';
import { S, el, esc } from './viewer/state.js';
import { wire, goLive } from './viewer/controls.js';
import { setCam } from './viewer/dish.js';
import { flashHint } from './viewer/gestures.js';
import { connect } from './viewer/transport.js';
import { start } from './viewer/loop.js';
import { reset as historyReset } from './viewer/history.js';

/* Local by default: the point of the WASM port is that no server is involved. `?server`
 * falls back to the WebSocket feed, which is still how the Python model is driven. */
// Parameters, not substrings: `?utm_source=discord-server` used to put a visitor into
// socket mode, facing "Nothing is listening".
const query = new URLSearchParams(location.search);
if (query.has('debug')) window.__sim = S;   // for poking from the console
/* The deal this load plays, shared by both dishes: ?dish=N replays it, the Share
 * button writes it (web/deal.js). */
S.dealSeed = loadSeed();
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
/* Per-dish view defaults, re-applied on every switch so each dish opens the same way
 * each time. The attractant layer is on in BOTH dishes -- it used to open off in the
 * arena (three plumes flooded the plate blue at 26 mm), which read as the layer being
 * broken when you switched dishes; the flood is now handled where it lives, in the
 * renderer, which fades the attractant with zoom instead of turning it off. */
const DISH_VIEW = { animal: { span: 6.5, cam: 'follow', layers: { attractant: true } },
                    arena: { span: 26, cam: 'free', layers: { attractant: true } } };

const loading = {};
const pressTab = (name) => document.querySelectorAll('#dish-tabs [data-dish]').forEach((o) =>
  o.setAttribute('aria-pressed', String(o.dataset.dish === name)));

async function switchDish(name) {
  if (S.playhead !== null) goLive();
  // The last dish asked for wins. The engine is assigned after an await, so a second
  // click during the arena's load used to finish with the arena on stage under a pressed
  // "The Animal" -- and a double click built two arenas. One load per dish, shared.
  S.wantDish = name;
  if (!engines[name]) {
    el('banner').classList.remove('gone');
    el('banner').firstElementChild.innerHTML = name === 'arena'
      ? '<b>Opening the arena&hellip;</b>a second dish, its own world'
      : '<b>Loading the animal&hellip;</b>302 neurons, compiled to WebAssembly';
    try {
      loading[name] ??= name === 'arena'
        ? new ArenaEngine(undefined, { dealSeed: S.dealSeed }).init()
        : new LocalEngine(undefined, { dealSeed: S.dealSeed }).init(2);
      engines[name] = await loading[name];
    } catch (err) {
      delete loading[name];
      console.error(err);
      if (S.engine) {
        // Another dish is running under the banner: give it back rather than leaving a
        // full-screen notice over it that nothing dismisses.
        el('banner').classList.add('gone');
        pressTab(el('app').dataset.dish);
        flashHint(`could not open the ${name} dish`);
      } else {
        el('banner').firstElementChild.innerHTML =
          `<b>Could not start the ${name} engine</b>${esc(err)}`;
      }
      return;
    }
    if (S.wantDish !== name) return;
    el('banner').classList.add('gone');
  }
  if (S.wantDish !== name) return;
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
  S.focusHandle = undefined;    // handles are per engine, and both number from 0
  historyReset();
  const v = DISH_VIEW[name];
  S.view.span = v.span; S.view.cx = 0; S.view.cy = 0;
  setCam(v.cam);                // not S.cam directly: the Follow/Free buttons say it too
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
  // The footer's controls are one set over two dishes: whatever they read, the dish now
  // on stage obeys -- otherwise switching silently forks a knob from what it drives.
  // Re-firing each control's own handler applies it exactly as a touch would. (Only
  // Weather used to be re-applied: the arena ran at 1x under a Rate reading 3.2x.)
  for (const id of ['r-rate', 'r-weather']) el(id)?.dispatchEvent(new Event('input'));
  document.querySelector('[data-medium][aria-pressed="true"]')?.click();
  pressTab(name);
  // The address names the dish on stage, so Share (which copies it) and a reload land here.
  try {
    history.replaceState(null, '',
      `${location.pathname}${location.search}${name === 'arena' ? '#arena' : ''}`);
  } catch (e) { /* file:// */ }
  // The arena tab's discovery dot has done its job once the dish has been seen.
  if (name === 'arena') {
    try { localStorage.setItem('celegans-arena-seen', '1'); } catch (e) { /* private mode */ }
    document.querySelector('#dish-tabs [data-dish="arena"] .new-dot')?.remove();
  }
}

if (query.has('server')) {
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
  const bp = el('b-pipette');
  if (bp) bp.style.display = 'none';   // a disclosure over an empty tray is a trick door
  // The deal is a local-engine concept; the socket dish plays the server's world.
  el('b-share').style.display = 'none';
  el('b-wiring').style.display = 'none';   // drift reads the local engine's weight tables
  // Weather is a local-engine field pass; the socket protocol has no wind command.
  const wg = el('r-weather');
  if (wg) wg.closest('.group').style.display = 'none';
  // One animal, and no command to add or remove one: +/- were enabled and did nothing,
  // with an empty selector beside them. The group goes the way Preserve's reasoning says.
  el('b-worm-add').closest('.group').style.display = 'none';
  el('dish-hint').innerHTML =
    'drag to pan &middot; scroll to zoom &middot; double&#8209;click to drop a lawn';
  connect();
} else {
  S.switchDish = switchDish;
  el('app').dataset.dish = 'animal';
  const first = location.hash === '#arena' ? 'arena' : 'animal';
  if (first === 'arena') pressTab('arena');
  el('banner').firstElementChild.innerHTML =
    '<b>Loading the animal&hellip;</b>302 neurons, compiled to WebAssembly';
  switchDish(first).catch((err) => {
    el('banner').firstElementChild.innerHTML =
      `<b>Could not start the local engine</b>${esc(err)}<code>?server</code>`;
    console.error(err);
  });
}
start();
