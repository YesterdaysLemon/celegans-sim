/* The measurement panels: nervous system, body-wall muscle, curvature kymograph,
 * membrane traces, and the receptor bars.
 *
 * These are measurements, so they stay in the data palette in every dish mode. They know
 * nothing about themes and nothing about transports -- they are handed numbers.
 */

import { S, C, el, seriesColor, fitCanvas, visible, ablated } from './state.js';
import { seq, divRgb } from './scales.js';
import { driftOf } from '../weight-drift.js';

/* Wiring drift of the FOCUSED animal, cached by worm id -- weights are set at hatch and
 * never after, so a computed drift is good for the animal's whole life. Null means
 * wild-type wiring (or no local engine), and the view says so rather than painting it. */
const driftCache = new Map();
export function wiringDrift() {
  if (!S.engine || !S.meta || !S.meta.wiring) return null;
  const id = S.engine.worms[S.focus];
  if (id === undefined) return null;
  if (!driftCache.has(id)) {
    if (driftCache.size > 64) driftCache.clear();
    const d = driftOf(S.engine.E, id, S.meta.wiring);
    if (d) {
      // Normalised per-neuron loads for the colour ramp, computed once with the drift.
      let m = 0;
      for (const v of d.perNeuron) if (v > m) m = v;
      d.perNorm = Float32Array.from(d.perNeuron, (v) => (m > 0 ? v / m : 0));
    }
    driftCache.set(id, d);
  }
  return driftCache.get(id);
}

/* ------------------------------------------------------------------- neurons ------ */

let layout = null;

// The neuron grid is derived from the panel's pixel size, so anything that resizes a panel
// -- collapsing one, a new connectome, a window resize -- has to throw it away.
export function invalidateLayout() { layout = null; }

function buildLayout(w, h) {
  // Ordered head to tail by soma position and packed into an even grid. Binning on the
  // raw position instead would be more literally anatomical but unreadable: half of the
  // 302 neurons have their cell bodies inside the nerve ring, so they pile into the first
  // few columns and leave the rest of the panel empty. Rank order keeps the anatomy
  // monotonic while giving every neuron the same amount of room.
  const N = S.meta.neurons;
  const padL = 10, padR = 10, padT = 8, padB = 16;
  const availW = w - padL - padR, availH = h - padT - padB;
  const n = N.length;
  let cols = Math.max(1, Math.round(Math.sqrt(n * availW / Math.max(availH, 1))));
  let rows = Math.ceil(n / cols);
  const dx = availW / cols, dy = availH / rows;
  const r = Math.max(1.6, Math.min(dx, dy) * 0.40);
  const pts = new Array(n);
  N.forEach((_, i) => {
    const c = i % cols, rr = Math.floor(i / cols);
    pts[i] = { x: padL + dx * (c + 0.5), y: padT + dy * (rr + 0.5), r };
  });
  return { pts, cols };
}

// Step a keyboard cursor through the grid the panel is actually drawn in, so Down really
// does go down a row rather than 20 cells along the connectome.
export function neuronStep(i, dx, dy) {
  if (!layout) return null;
  const n = layout.pts.length, cols = layout.cols || 1;
  const from = i == null ? 0 : i;
  const next = from + dx + dy * cols;
  return next >= 0 && next < n ? next : from;
}

export function drawNeurons() {
  const cv = el('c-neurons');
  if (!visible(cv)) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  if (!S.meta) return;
  if (!layout || layout.w !== w || layout.h !== h) {
    layout = buildLayout(w, h); layout.w = w; layout.h = h;
  }
  const act = S.frame ? S.frame.act : null;
  // The wiring view recolours the same dots by mutation load instead of activity; a
  // wild-type animal shows the whole grid at zero, which is the honest picture of it.
  const drift = S.wiringView ? wiringDrift() : null;
  const wiringOn = S.wiringView;
  const pts = layout.pts;
  // Which cells are dead is a fact about the focused animal, so it is looked up once for
  // the panel rather than once for each of the 302 cells in it.
  const dead = ablated();

  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], a = act ? act[i] : 0.5;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    if (dead.has(i)) {
      ctx.fillStyle = C('--plane'); ctx.fill();
      ctx.strokeStyle = C('--text-muted'); ctx.lineWidth = 1; ctx.stroke();
      const q = p.r * 0.75;
      ctx.beginPath();
      ctx.moveTo(p.x - q, p.y - q); ctx.lineTo(p.x + q, p.y + q);
      ctx.moveTo(p.x + q, p.y - q); ctx.lineTo(p.x - q, p.y + q);
      ctx.stroke();
    } else {
      ctx.fillStyle = seq(wiringOn ? (drift ? drift.perNorm[i] : 0) : a); ctx.fill();
    }
    const sel = S.selected.indexOf(i);
    if (sel >= 0) {
      ctx.strokeStyle = seriesColor(sel); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r + 2.2, 0, Math.PI * 2); ctx.stroke();
    } else if (S.hover === i) {
      // The cursor ring in the chrome's own foreground colour: white on the terminal,
      // ink on the paper. A literal '#fff' disappeared in light mode.
      ctx.strokeStyle = C('--text-primary'); ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r + 2.2, 0, Math.PI * 2); ctx.stroke();
    }
  }
  ctx.fillStyle = C('--text-muted'); ctx.font = C('--font-canvas');
  ctx.fillText('head', 12, h - 4);
  ctx.textAlign = 'right'; ctx.fillText('tail', w - 10, h - 4); ctx.textAlign = 'left';

  /* The activity legend (#165): what the colour MEANS, drawn by sampling the same live
   * seq() the dots were just painted with -- one pixel-column per step -- so it cannot
   * drift from the renderer and it re-answers on the next frame when the mode flips
   * the luminance direction. That flip is exactly why it exists: high activity is
   * lighter than the surface in dark mode and darker in light mode, both correct, and
   * only a labelled scale makes both readable as the same fact. */
  const lw = Math.min(90, Math.floor(w * 0.3)), lh = 5;
  const lx = Math.round((w - lw) / 2), ly = h - 10;
  for (let i = 0; i < lw; i++) {
    ctx.fillStyle = seq(i / (lw - 1));
    ctx.fillRect(lx + i, ly, 1, lh);
  }
  ctx.fillStyle = C('--text-muted');
  ctx.textAlign = 'right'; ctx.fillText('low', lx - 5, h - 4);
  ctx.textAlign = 'left'; ctx.fillText('high', lx + lw + 5, h - 4);
  legend = { x0: lx, x1: lx + lw - 1, y: ly + Math.floor(lh / 2) };
}

/* Where the legend was last drawn, in the canvas's CSS pixels -- for the smoke check
 * that reads the endpoint pixels back and compares them with seq(0)/seq(1). */
let legend = null;
export function activityLegend() { return legend; }

// Hit-test in the neuron panel. Returns an index or null.
//
// `radius` is the acceptance distance in CSS px: 9 by default (about twice the dot, the
// mouse's target), and callers with a finger pass more -- a fingertip is a ~16 px
// instrument and holding it to 9 made the grid a dexterity test (#158). Nearest-wins
// keeps a bigger radius from stealing a cell that another dot is closer to, and a tap
// farther than the radius from everything returns null rather than silently choosing a
// distant neuron.
export function neuronAt(cv, clientX, clientY, radius = 9) {
  if (!layout) return null;
  const r = cv.getBoundingClientRect();
  // The layout is built in CSS pixels: fitCanvas scales the backing store by
  // devicePixelRatio but puts the same factor into the context transform, so it hands
  // buildLayout the element's CSS size and every pts[i] is in those units -- the same
  // units a mouse event reports. So the offset into the element is the whole conversion.
  // Scaling it by the ratio of the two sizes, as this did, is a no-op at dpr 1 and puts
  // the hit test out by a factor of two on every HiDPI display, which is most laptops.
  const x = clientX - r.left, y = clientY - r.top;
  let best = null, bd = radius * radius;
  layout.pts.forEach((p, i) => {
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d < bd) { bd = d; best = i; }
  });
  return best;
}

// Where a neuron sits on screen, in client coordinates. Keyboard focus has no pointer to
// anchor a tooltip to, so it has to ask.
export function neuronCentre(cv, i) {
  if (!layout || !layout.pts[i]) return null;
  const r = cv.getBoundingClientRect();
  // Same units as neuronAt, and the exact inverse of it: add the element's origin, nothing
  // else. It had the reciprocal of that function's error, so feeding one into the other
  // came out right and only the tooltip's position on screen was wrong.
  return { clientX: r.left + layout.pts[i].x, clientY: r.top + layout.pts[i].y };
}

/* -------------------------------------------------------------------- lineage ----- */

/* The family tree, live: one horizontal life-line per animal (born -> died-or-now),
 * coloured by dynasty, dropped a vertical stroke from its parent's lane at birth. A
 * sweep to fixation is legible here as the tree collapsing to one colour, which no
 * census line can show. Draws only what touches the trailing window, because a long
 * dish's full pedigree is an archive, not a picture. Arena only -- the reference dish
 * has no descent to draw. */
const LINEAGE_WINDOW = 240;      // seconds of trailing history on screen

export function drawLineage() {
  const cv = el('c-lineage');
  if (!cv || !visible(cv)) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  const arena = S.engine && S.engine.arena;
  if (!arena || !arena.pedigree || !S.worms.length) return;
  const now = arena.simT || 0;
  const t0 = Math.max(0, now - LINEAGE_WINDOW);
  const hue = S.engine.dynastyHue || (() => 40);

  // Everything alive in the window, oldest first so lanes read as generations.
  const rows = [...arena.pedigree.entries()]
    .filter(([, v]) => (v.died === null || v.died >= t0) && v.born <= now)
    .sort((a, b) => a[1].born - b[1].born || a[0] - b[0]);
  if (!rows.length) return;
  const lane = new Map();
  rows.forEach(([id], i) => lane.set(id, i));
  const rowH = Math.min(14, (h - 18) / rows.length);
  const X = (t) => 8 + (w - 16) * (Math.max(t, t0) - t0) / Math.max(now - t0, 1e-9);
  const Y = (i) => 8 + i * rowH + rowH / 2;

  for (const [id, v] of rows) {
    const y = Y(lane.get(id));
    const alive = v.died === null;
    ctx.strokeStyle = `hsl(${hue(v.dyn)} 70% ${alive ? 62 : 38}%)`;
    ctx.globalAlpha = alive ? 1 : 0.65;
    ctx.lineWidth = alive ? 2 : 1.2;
    ctx.beginPath();
    ctx.moveTo(X(v.born), y);
    ctx.lineTo(X(alive ? now : v.died), y);
    ctx.stroke();
    // The stroke of descent: parent's lane down to this one, at the moment of birth.
    if (v.parent >= 0 && lane.has(v.parent) && v.born >= t0) {
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(X(v.born), Y(lane.get(v.parent)));
      ctx.lineTo(X(v.born), y);
      ctx.stroke();
    }
    if (alive) {
      ctx.globalAlpha = 1;
      ctx.fillStyle = `hsl(${hue(v.dyn)} 75% 65%)`;
      ctx.beginPath(); ctx.arc(X(now), y, Math.min(3, rowH * 0.4), 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = C('--text-muted'); ctx.font = C('--font-canvas');
  ctx.fillText(`${Math.round(now - t0)} s`, 8, h - 4);
  ctx.textAlign = 'right'; ctx.fillText('now', w - 8, h - 4); ctx.textAlign = 'left';
}

/* -------------------------------------------------------------------- muscles ----- */

export function drawMuscles() {
  const cv = el('c-muscle');
  if (!visible(cv)) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  if (!S.meta || !S.frame) return;
  const quads = ['MDL', 'MDR', 'MVL', 'MVR'];
  const padL = 40, padT = 6, padB = 14, gap = 2;
  const rowH = (h - padT - padB) / 4;
  const cellW = (w - padL - 10) / 24;
  ctx.font = C('--font-canvas');
  quads.forEach((q, r) => {
    ctx.fillStyle = C('--text-muted');
    ctx.fillText(q, 8, padT + rowH * r + rowH / 2 + 3);
    for (let c = 0; c < 24; c++) {
      const idx = S.meta.muscleIndex[q + String(c + 1).padStart(2, '0')];
      if (idx === undefined) continue;      // MVL has only 23 cells
      ctx.fillStyle = seq(S.frame.tension[idx]);
      ctx.fillRect(padL + cellW * c, padT + rowH * r, cellW - gap, rowH - gap);
    }
  });
  ctx.fillStyle = C('--text-muted');
  ctx.fillText('anterior', padL, h - 2);
  ctx.textAlign = 'right'; ctx.fillText('posterior', w - 10, h - 2); ctx.textAlign = 'left';
}

/* ------------------------------------------------------------------ kymograph ----- */

const KYMO_W = 600;

export function pushKymo(kappa, t) {
  // A ring buffer of raw curvature, converted to pixels only when drawn. Scrolling a
  // canvas by blitting it onto itself reads back pixels it has already overwritten, so
  // the history smears instead of sliding; keeping the numbers and rebuilding the image
  // avoids the question entirely, and 600 x 47 is nothing to redraw.
  if (!S.kymo || S.kymo.rows !== kappa.length) {
    S.kymo = {
      rows: kappa.length,
      data: new Float32Array(KYMO_W * kappa.length),
      head: 0, filled: 0,
      canvas: document.createElement('canvas'),
    };
    S.kymo.canvas.width = KYMO_W;
    S.kymo.canvas.height = kappa.length;
    S.kymo.ctx = S.kymo.canvas.getContext('2d');
    S.kymo.img = S.kymo.ctx.createImageData(KYMO_W, kappa.length);
  }
  // Advance by simulated time, not by frames received, so the axis stays 20 s wide
  // whatever the frame rate or the speed multiplier happens to be.
  const k = S.kymo;
  const dt = 20.0 / KYMO_W;
  if (k.lastT === undefined) k.lastT = t - dt;
  let steps = Math.floor((t - k.lastT) / dt);
  if (steps < 1) return;
  steps = Math.min(steps, KYMO_W);
  k.lastT += steps * dt;
  for (let s = 0; s < steps; s++) {
    for (let i = 0; i < k.rows; i++) k.data[i * KYMO_W + k.head] = kappa[i];
    k.head = (k.head + 1) % KYMO_W;
  }
  k.filled = Math.min(k.filled + steps, KYMO_W);
}

function renderKymo() {
  const k = S.kymo;
  if (!k) return null;
  // 600 x 47 is 28k pixels, and rebuilding all of them every animation frame is most of
  // the panel cost for a picture that only changes when a new column is pushed. The
  // buffer advances a handful of columns a second; the rest of the time this is a redraw
  // of pixels that already say the right thing.
  if (k.drawnHead === k.head && k.drawnFilled === k.filled) return k.canvas;
  k.drawnHead = k.head; k.drawnFilled = k.filled;
  const d = k.img.data;
  for (let r = 0; r < k.rows; r++) {
    for (let x = 0; x < KYMO_W; x++) {
      const src = (k.head + x) % KYMO_W;              // oldest column first
      const age = KYMO_W - x;
      const o = (r * KYMO_W + x) * 4;
      if (age > k.filled) { d[o + 3] = 0; continue; }
      const c = divRgb(k.data[r * KYMO_W + src] / 7.0);
      d[o] = c[0]; d[o + 1] = c[1]; d[o + 2] = c[2]; d[o + 3] = 255;
    }
  }
  k.ctx.putImageData(k.img, 0, 0);
  return k.canvas;
}

export function drawKymo() {
  const cv = el('c-kymo');
  if (!visible(cv)) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  const img = renderKymo();
  if (!img) return;
  const padT = 6, padL = 34, padB = 6;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, padL, padT, w - padL - 8, h - padT - padB);
  ctx.fillStyle = C('--text-muted'); ctx.font = C('--font-canvas');
  ctx.fillText('head', 4, padT + 8);
  ctx.fillText('tail', 6, h - padB - 1);
}

/* --------------------------------------------------------------------- traces ----- */

export function drawTraces() {
  const cv = el('c-trace');
  if (!visible(cv)) return;
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  if (!S.traces.length || !S.selected.length) return;
  const padL = 34, padT = 8, padB = 8, padR = 8;
  const lo = -80, hi = 20;
  const Y = (v) => padT + (hi - v) / (hi - lo) * (h - padT - padB);

  ctx.strokeStyle = C('--gridline'); ctx.lineWidth = 1;
  for (const v of [0, -40, -80]) {
    ctx.beginPath(); ctx.moveTo(padL, Y(v)); ctx.lineTo(w - padR, Y(v)); ctx.stroke();
    ctx.fillStyle = C('--text-muted'); ctx.font = C('--font-canvas');
    ctx.fillText(`${v}`, 6, Y(v) + 3);
  }

  const n = S.traces[0].length;
  const X = (i) => padL + (i / Math.max(1, n - 1)) * (w - padL - padR);
  const labels = [];
  S.selected.forEach((idx, k) => {
    const t = S.traces[k];
    if (!t || !t.length) return;
    ctx.strokeStyle = seriesColor(k); ctx.lineWidth = 2;
    ctx.lineJoin = 'round'; ctx.beginPath();
    for (let i = 0; i < t.length; i++) (i ? ctx.lineTo(X(i), Y(t[i])) : ctx.moveTo(X(i), Y(t[i])));
    ctx.stroke();
    labels.push({ k, idx, y: Y(t[t.length - 1]) });
  });
  // Direct label at the live end of each line, so identity never rests on colour alone.
  labels.sort((a, b) => a.y - b.y);
  let prev = -1e9;
  ctx.font = `600 ${C('--font-canvas')}`;
  ctx.textAlign = 'right';
  for (const L of labels) {
    const y = Math.max(prev + 11, Math.max(padT + 9, Math.min(h - padB - 2, L.y)));
    prev = y;
    ctx.fillStyle = seriesColor(L.k);
    ctx.fillText(S.meta.neurons[L.idx].name, w - padR - 2, y - 3);
  }
  ctx.textAlign = 'left';
}

/* --------------------------------------------------------------------- senses ----- */

// Receptor readings, drawn as labelled bars. Ranges are the physiological span of each
// field in this dish, not the observed min/max, so a flat bar means the animal is
// genuinely sitting at one end rather than that the scale collapsed.
const SENSE_ROWS = [
  ['Attractant', 'attractant', 0, 1.1, 'var(--series-1)'],
  ['Food',       'food',       0, 1.0, 'var(--series-3)'],
  ['Repellent',  'repellent',  0, 0.9, 'var(--series-2)'],
  ['Oxygen',     'oxygen',     0.05, 0.21, 'var(--series-4)'],
  ['Temperature','temperature', 17, 25, 'var(--series-5)'],
  ['Touch',      'touch',      0, 3.0, 'var(--series-6)'],
  ['Forward gate', 'gateF',    0, 1.0, 'var(--text-secondary)'],
  // 1.0 is a fully stocked mechanoreceptor; it falls as the animal habituates to repeated
  // taps and refills over minutes of quiet. The only state in the model that outlives a
  // modulator, and the only thing here that is memory rather than filtering.
  ['Touch memory', 'habituation', 0, 1.0, 'var(--series-2)'],
  // Feeding. The lumen fills when the pharynx captures and empties when M4 moves it on,
  // so a rising bar with a normal pump rate is what an M4-ablated animal looks like.
  ['Pump rate',  'pumpNorm',   0, 1.0, 'var(--series-3)'],
  ['Lumen',      'lumenNorm',  0, 1.0, 'var(--series-4)'],
  // Egg-laying. The vulval muscle is the output; the uterus is what it has to work with.
  // Both are here rather than in the header because they are state of the animal, and the
  // header is for what it is doing.
  ['Vulval muscle', 'vulva',   0, 1.0, 'var(--series-5)'],
  ['Eggs held',  'eggsNorm',   0, 1.0, 'var(--series-6)'],
];
const SENSE_FMT = {
  eggsNorm: v => (v * 15).toFixed(0),
  oxygen: v => (100 * v).toFixed(1) + '%',
  temperature: v => v.toFixed(1) + '°C',
  habituation: v => (100 * v).toFixed(0) + '%',
  pumpNorm: v => (v * 360).toFixed(0) + '/min',
  lumenNorm: v => (100 * v).toFixed(0) + '%',
};

export function drawSenses(sensed) {
  const host = el('senses');
  if (!host) return;
  if (!host.dataset.built) {
    host.innerHTML = SENSE_ROWS.map(([label, key, , , colour]) => `
      <span class="s-name" id="s-lbl-${key}">${label}</span>
      <span class="s-bar" role="meter" aria-labelledby="s-lbl-${key}"
            data-meter="${key}"><span class="s-fill" data-fill="${key}"
            style="background:${colour}"></span></span>
      <span class="s-val" data-val="${key}">&mdash;</span>`).join('');
    host.dataset.built = '1';
  }
  for (const [, key, lo, hi] of SENSE_ROWS) {
    const v = sensed[key] ?? 0;
    const frac = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    const text = (SENSE_FMT[key] || (x => x.toFixed(2)))(v);
    host.querySelector(`[data-fill="${key}"]`).style.width = (100 * frac) + '%';
    host.querySelector(`[data-val="${key}"]`).textContent = text;
    // A bar with no text alternative is invisible to a screen reader, and these are the
    // only live readout of what the animal is actually sensing.
    const meter = host.querySelector(`[data-meter="${key}"]`);
    meter.setAttribute('aria-valuenow', String(Math.round(frac * 100)));
    meter.setAttribute('aria-valuetext', text);
  }
}
