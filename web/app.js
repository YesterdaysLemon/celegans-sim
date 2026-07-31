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
 *   viewer/controls.js    every event listener, and the UI state that goes with them
 *   viewer/transport.js   the WebSocket feed and the command seam, send()
 *   viewer/loop.js        the local engine read-out and requestAnimationFrame
 *
 * Dependencies point down that list, never up.
 */

import { LocalEngine } from './local.js';
import { S, el } from './viewer/state.js';
import { wire } from './viewer/controls.js';
import { connect } from './viewer/transport.js';
import { start } from './viewer/loop.js';

/* Local by default: the point of the WASM port is that no server is involved. `?server`
 * falls back to the WebSocket feed, which is still how the Python model is driven. */
if (location.search.includes('debug')) window.__sim = S;   // for poking from the console
wire();
if (location.search.includes('server')) {
  connect();
} else {
  el('banner').firstElementChild.innerHTML =
    '<b>Loading the animal&hellip;</b>302 neurons, compiled to WebAssembly';
  new LocalEngine().init(2).then((eng) => { S.engine = eng; })
    .catch((err) => {
      el('banner').firstElementChild.innerHTML =
        `<b>Could not start the local engine</b>${err}<code>?server</code>`;
      console.error(err);
    });
}
start();
