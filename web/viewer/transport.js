/* Where frames come from, and where commands go.
 *
 * Two paths. The default is the local WASM engine in this tab -- no server at all. The
 * `?server` path is the original WebSocket feed from `python run.py`, kept because it is
 * still how the Python model itself is driven and it is the only way to watch the
 * reference implementation rather than the port.
 *
 * `send()` is the seam: everything upstream issues commands without knowing which path is
 * live. Nothing in here imports the control wiring, which is what keeps the graph acyclic.
 */

import { S, el } from './state.js';
import { drawSenses, pushKymo, invalidateLayout } from './panels.js';
import { updateFreq, updateStats, updatePump, updateEggs } from './stats.js';
import { follow } from './dish.js';

/* The frame protocol, and its version. See worm/server.py, which is the other half.
 *
 * A frame is identified by its magic word, not by a version field: every field in the
 * header sits at a fixed offset, so any layout change moves the payload too, and a viewer
 * reading the old offsets draws confident nonsense. An unrecognised magic is dropped
 * instead. MAGIC_V1 is here so that a server from before the egg fields is *named* rather
 * than met with a silent, permanently frozen page. */
const PROTOCOL = 2;
const MAGIC = 0x574f5232;        // "WOR2", protocol 2
const MAGIC_V1 = 0x574f524d;     // "WORM", protocol 1: no egg state
const FIELD_MAGIC = 0x574f524e;
const HEADER_BYTES = 112;   // 7 uint32 + 21 float32

let ws = null;
let endpoint = null;    // resolved once, then reused across reconnects
let attempts = 0;       // consecutive failures since the last successful open
let stale = false;      // the server speaks an older protocol; stop, do not loop

export function send(msg) {
  const eng = S.engine;
  if (eng) {
    if (msg.cmd === 'play') eng.running = true;
    else if (msg.cmd === 'pause') eng.running = false;
    else if (msg.cmd === 'rate') eng.rate = msg.value;
    else if (msg.cmd === 'drop_food') eng.dropFood(msg.x, msg.y, msg.r);
    else if (msg.cmd === 'poke') eng.poke(msg.where, msg.strength);
    else if (msg.cmd === 'medium') {
      const h = eng.head.scalars;
      eng.setMedium(h[`med_${msg.value}_ct`], h[`med_${msg.value}_cn`]);
    }
    return;
  }
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
}

/* Where the socket is, most specific source first.
 *
 *   ?ws=…            an explicit port or a whole ws:// URL in the page's own query. The
 *                    only thing that can be right behind a reverse proxy, where the
 *                    server's port is an internal detail the browser must never see.
 *   transport.json   served by worm/server.py, which is the only party that knows which
 *                    --ws-port it was given.
 *   port + 1         the historical guess. It is still the right answer when web/ is
 *                    served by something that is not worm/server.py -- a bare
 *                    `python -m http.server`, tools/smoke_web.mjs, the nginx container --
 *                    and it was the *only* answer for long enough that `--port 9000`
 *                    quietly produced a viewer dialling 9001 at a server on 8081.
 *
 * wss when the page is https, because a secure page may not open an insecure socket, and
 * the browser's refusal to do so looks exactly like a server that is not running. */
function socketURL() {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = location.hostname || '127.0.0.1';
  const asked = new URLSearchParams(location.search).get('ws');
  const port = Number(asked);
  if (asked && /^wss?:\/\//.test(asked)) return Promise.resolve(asked);
  // A `?ws=` with nonsense in it falls through to the next source rather than being used:
  // `ws://host:NaN/` throws out of the WebSocket constructor, and a typo in a query string
  // should not leave a dead page behind an exception nobody reads.
  if (Number.isInteger(port) && port > 0 && port < 65536) {
    return Promise.resolve(`${scheme}//${host}:${port}/`);
  }
  return fetch('transport.json', { cache: 'no-store' })
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
    .then((cfg) => {
      const told = cfg && Number(cfg.ws_port);
      return `${scheme}//${host}:${told || Number(location.port || 8080) + 1}/`;
    });
}

export function connect() {
  if (stale) return;
  // Resolved once and remembered: a reconnect must not re-ask, or a server that has gone
  // away turns every retry into a failed fetch as well as a failed socket.
  if (endpoint !== null) { dial(endpoint); return; }
  socketURL().then((url) => { endpoint = url; dial(url); });
}

/* Keep endpoint diagnostics as text, even when the endpoint came from `?ws=`.
 *
 * A query-string value is untrusted page input. Building this banner with innerHTML made
 * a failed connection turn markup in a crafted WebSocket URL into live same-origin DOM.
 * Construct the three deliberately styled nodes instead, and give every value to the DOM
 * as text so the diagnostic can quote the exact endpoint without interpreting it. */
function showBanner(title, message, command) {
  const content = el('banner').firstElementChild;
  const heading = document.createElement('b');
  heading.textContent = title;
  const code = document.createElement('code');
  code.textContent = command;
  content.replaceChildren(heading, document.createTextNode(message), code);
}

function dial(url) {
  ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => { S.connected = true; attempts = 0; el('banner').classList.add('gone'); };
  ws.onclose = () => {
    S.connected = false;
    if (stale) return;                 // the banner already says something more useful
    attempts++;
    el('banner').classList.remove('gone');
    // Name the endpoint. A bare "Retrying…" is what made a wrong --ws-port an unexplained
    // loop: the one fact that identifies the misconfiguration was the one fact the page
    // would not say. After a few goes, say what to do about it as well.
    if (attempts < 3) {
      showBanner('Simulation disconnected', `Retrying ${endpoint}…`, 'python run.py');
    } else {
      showBanner(`Nothing is listening on ${endpoint}`,
        'Start the server, or point the viewer at the right port with ', '?server&ws=PORT');
    }
    setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') { onHello(JSON.parse(ev.data)); return; }
    const dv = new DataView(ev.data);
    const magic = dv.getUint32(0, true);
    if (magic === FIELD_MAGIC) {
      const n = dv.getUint32(4, true);
      S.field = { n, data: new Uint8Array(ev.data, 8, n * n * 3) };
    } else if (magic === MAGIC) {
      onFrame(ev.data, dv);
    } else if (magic === MAGIC_V1) {
      onStaleProtocol();
    }
  };
}

// An older server. Frames from it would parse at the wrong offsets, so they are dropped --
// which on its own is a page that connects, says nothing, and never updates. Say why, and
// stop reconnecting: retrying cannot fix a version skew.
function onStaleProtocol() {
  if (stale) return;
  stale = true;
  el('banner').classList.remove('gone');
  showBanner('The server is out of date',
    `This viewer reads frame protocol ${PROTOCOL}; the server is sending protocol 1, `
    + 'which carries no egg state. Restart it from this checkout.', 'python run.py');
  if (ws) ws.close();
}

function onHello(m) {
  S.meta = m;
  S.meta.muscleIndex = {};
  m.muscles.forEach((mu, i) => { S.meta.muscleIndex[mu.name] = i; });
  invalidateLayout(); S.kymo = null; S.trail = [];
  S.recentre = true;
  const want = ['DB01', 'VB01', 'AVBL'];
  S.selected = want.map((n) => m.neurons.findIndex((x) => x.name === n)).filter((i) => i >= 0);
  S.traces = S.selected.map(() => []);
  el('trace-hint').textContent = S.selected.map((k) => m.neurons[k].name).join(', ');
}

function onFrame(buf, dv) {
  const nNodes = dv.getUint32(4, true), nNeu = dv.getUint32(8, true);
  const nMus = dv.getUint32(12, true), nJoint = dv.getUint32(16, true);
  const running = dv.getUint32(20, true), nEggs = dv.getUint32(24, true);
  const o = 28;
  const t = dv.getFloat32(o, true), speed = dv.getFloat32(o + 4, true);
  const food = dv.getFloat32(o + 8, true), dir = dv.getFloat32(o + 12, true);
  const achieved = dv.getFloat32(o + 16, true);
  const pumpRate = dv.getFloat32(o + 56, true);
  const pumping = dv.getFloat32(o + 60, true);
  const lumen = dv.getFloat32(o + 64, true);
  const vulva = dv.getFloat32(o + 68, true);
  const eggsHeld = dv.getFloat32(o + 72, true);
  const eggsLaid = dv.getFloat32(o + 76, true);
  const eglActive = dv.getFloat32(o + 80, true);
  const sensed = {
    attractant: dv.getFloat32(o + 20, true),
    temperature: dv.getFloat32(o + 24, true),
    oxygen: dv.getFloat32(o + 28, true),
    food: dv.getFloat32(o + 32, true),
    touch: dv.getFloat32(o + 36, true),
    gateF: dv.getFloat32(o + 40, true),
    gateB: dv.getFloat32(o + 44, true),
    repellent: dv.getFloat32(o + 48, true),
    habituation: dv.getFloat32(o + 52, true),
    pumpNorm: pumpRate / 6.0,          // against PharynxParams.max_rate
    lumenNorm: lumen / 0.05,           // against PharynxParams.lumen_capacity
    // The same two rows loop.js fills from the WASM feed. Left out, they did not read as
    // missing: `sensed[key] ?? 0` gave both meters a live-looking zero.
    vulva,
    eggsNorm: eggsHeld / 15.0,         // against EggLayingParams.uterus_capacity
  };

  let p = HEADER_BYTES;
  const nodes = new Float32Array(buf, p, nNodes * 2); p += nNodes * 8;
  const act = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const V = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const tension = new Float32Array(buf, p, nMus); p += nMus * 4;
  const kappa = new Float32Array(buf, p, nJoint); p += nJoint * 4;
  // Two planes rather than interleaved pairs, because that is the shape local.js hands
  // the dish and drawEggs should not have to know which feed it is drawing.
  S.eggs = nEggs
    ? { n: nEggs, x: new Float32Array(buf, p, nEggs),
        y: new Float32Array(buf, p + nEggs * 4, nEggs) }
    : null;

  S.frame = { t, speed, food, dir, achieved, sensed, nodes, act, V, tension, kappa, running,
              vulva, eggsHeld, eggsLaid, eglActive };
  drawSenses(sensed);
  updatePump(pumpRate, pumping);
  updateEggs(eggsLaid, eggsHeld, eglActive);

  const cx = nodes.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0) / nNodes;
  const cy = nodes.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0) / nNodes;
  follow(cx, cy);

  const last = S.trail[S.trail.length - 1];
  if (!last || Math.hypot(cx - last[0], cy - last[1]) > 0.02) {
    S.trail.push([cx, cy]);
    if (S.trail.length > 2600) S.trail.shift();
  }

  pushKymo(kappa, t);
  S.selected.forEach((idx, k) => {
    const tr = S.traces[k] || (S.traces[k] = []);
    tr.push(V[idx]);
    if (tr.length > 420) tr.shift();
  });
  updateFreq(kappa[Math.floor(nJoint / 2)], t);
  updateStats(t, speed, food, dir, achieved, running);
}
