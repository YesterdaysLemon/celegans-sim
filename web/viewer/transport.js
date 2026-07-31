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
import { updateFreq, updateStats, updatePump } from './stats.js';
import { follow } from './dish.js';

const MAGIC = 0x574f524d;
const FIELD_MAGIC = 0x574f524e;
const HEADER_BYTES = 92;   // 6 uint32 + 17 float32

let ws = null;

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

export function connect() {
  const port = Number(location.port || 8080) + 1;
  ws = new WebSocket(`ws://${location.hostname || '127.0.0.1'}:${port}/`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => { S.connected = true; el('banner').classList.add('gone'); };
  ws.onclose = () => {
    S.connected = false;
    el('banner').classList.remove('gone');
    el('banner').firstElementChild.innerHTML =
      '<b>Simulation disconnected</b>Retrying…<code>python run.py</code>';
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
    }
  };
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
  const running = dv.getUint32(20, true);
  const o = 24;
  const t = dv.getFloat32(o, true), speed = dv.getFloat32(o + 4, true);
  const food = dv.getFloat32(o + 8, true), dir = dv.getFloat32(o + 12, true);
  const achieved = dv.getFloat32(o + 16, true);
  const pumpRate = dv.getFloat32(o + 56, true);
  const pumping = dv.getFloat32(o + 60, true);
  const lumen = dv.getFloat32(o + 64, true);
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
  };

  let p = HEADER_BYTES;
  const nodes = new Float32Array(buf, p, nNodes * 2); p += nNodes * 8;
  const act = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const V = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const tension = new Float32Array(buf, p, nMus); p += nMus * 4;
  const kappa = new Float32Array(buf, p, nJoint);

  S.frame = { t, speed, food, dir, achieved, sensed, nodes, act, V, tension, kappa, running };
  drawSenses(sensed);
  updatePump(pumpRate, pumping);

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
