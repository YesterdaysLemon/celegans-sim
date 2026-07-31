/* The measurement panels: nervous system, body-wall muscle, curvature kymograph,
 * membrane traces, and the receptor bars.
 *
 * These are measurements, so they stay in the data palette in every dish mode. They know
 * nothing about themes and nothing about transports -- they are handed numbers.
 */

import { S, C, el, SERIES, fitCanvas, visible } from './state.js';
import { seq, divRgb } from './scales.js';

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
  return { pts };
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
  const pts = layout.pts;

  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], a = act ? act[i] : 0.5;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    if (S.ablated.has(i)) {
      ctx.fillStyle = C('--plane'); ctx.fill();
      ctx.strokeStyle = C('--text-muted'); ctx.lineWidth = 1; ctx.stroke();
      const q = p.r * 0.75;
      ctx.beginPath();
      ctx.moveTo(p.x - q, p.y - q); ctx.lineTo(p.x + q, p.y + q);
      ctx.moveTo(p.x + q, p.y - q); ctx.lineTo(p.x - q, p.y + q);
      ctx.stroke();
    } else {
      ctx.fillStyle = seq(a); ctx.fill();
    }
    const sel = S.selected.indexOf(i);
    if (sel >= 0) {
      ctx.strokeStyle = SERIES[sel]; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r + 2.2, 0, Math.PI * 2); ctx.stroke();
    } else if (S.hover === i) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r + 2.2, 0, Math.PI * 2); ctx.stroke();
    }
  }
  ctx.fillStyle = C('--text-muted'); ctx.font = '10px system-ui';
  ctx.fillText('head', 12, h - 4);
  ctx.textAlign = 'right'; ctx.fillText('tail', w - 10, h - 4); ctx.textAlign = 'left';
}

// Hit-test in the neuron panel. Returns an index or null.
export function neuronAt(cv, clientX, clientY) {
  if (!layout) return null;
  const r = cv.getBoundingClientRect();
  // The layout is built in the canvas's backing-store pixels, which are devicePixelRatio
  // times the CSS pixels a mouse event reports. Comparing the two directly meant that on
  // any HiDPI display the hit test was out by a factor of two.
  const sx = cv.width / Math.max(r.width, 1), sy = cv.height / Math.max(r.height, 1);
  const x = (clientX - r.left) * sx, y = (clientY - r.top) * sy;
  let best = null, bd = 81;
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
  const sx = Math.max(r.width, 1) / cv.width, sy = Math.max(r.height, 1) / cv.height;
  return { clientX: r.left + layout.pts[i].x * sx, clientY: r.top + layout.pts[i].y * sy };
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
  ctx.font = '10px system-ui';
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
  ctx.fillStyle = C('--text-muted'); ctx.font = '10px system-ui';
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
    ctx.fillStyle = C('--text-muted'); ctx.font = '10px system-ui';
    ctx.fillText(`${v}`, 6, Y(v) + 3);
  }

  const n = S.traces[0].length;
  const X = (i) => padL + (i / Math.max(1, n - 1)) * (w - padL - padR);
  const labels = [];
  S.selected.forEach((idx, k) => {
    const t = S.traces[k];
    if (!t || !t.length) return;
    ctx.strokeStyle = SERIES[k]; ctx.lineWidth = 2;
    ctx.lineJoin = 'round'; ctx.beginPath();
    for (let i = 0; i < t.length; i++) (i ? ctx.lineTo(X(i), Y(t[i])) : ctx.moveTo(X(i), Y(t[i])));
    ctx.stroke();
    labels.push({ k, idx, y: Y(t[t.length - 1]) });
  });
  // Direct label at the live end of each line, so identity never rests on colour alone.
  labels.sort((a, b) => a.y - b.y);
  let prev = -1e9;
  ctx.font = '600 10px system-ui';
  ctx.textAlign = 'right';
  for (const L of labels) {
    const y = Math.max(prev + 11, Math.max(padT + 9, Math.min(h - padB - 2, L.y)));
    prev = y;
    ctx.fillStyle = SERIES[L.k];
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
];
const SENSE_FMT = {
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
