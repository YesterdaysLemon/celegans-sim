/* celegans-sim viewer.
 *
 * Receives packed float32 telemetry over a WebSocket and draws four views: the dish, the
 * nervous system, the body-wall muscle sheets and a curvature kymograph.
 *
 * Colour follows the data-viz reference palette. Magnitudes (activation, tension) use one
 * sequential hue; signed curvature uses the diverging blue-red pair with a neutral grey
 * midpoint, so "straight" reads as nothing rather than as a colour.
 */

const MAGIC = 0x574f524d;
const FIELD_MAGIC = 0x574f524e;
const HEADER_BYTES = 80;   // 6 uint32 + 14 float32

const css = getComputedStyle(document.documentElement);
const C = (name) => css.getPropertyValue(name).trim();
const SERIES = [C('--series-1'), C('--series-2'), C('--series-3'),
                C('--series-4'), C('--series-5'), C('--series-6')];

/* ------------------------------------------------------------------ colour ramps --- */

// Sequential blue, the reference ramp, sampled 100 -> 700. On a dark surface the low end
// recedes into the surface, which is exactly what "near zero" should do.
const BLUE = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec',
              '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab',
              '#184f95', '#104281', '#0d366b'].map(hexToRgb).reverse();

function hexToRgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function lerp(a, b, t) { return a + (b - a) * t; }
function rampRgb(ramp, t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (ramp.length - 1), i = Math.floor(x), f = x - i;
  const a = ramp[i], b = ramp[Math.min(i + 1, ramp.length - 1)];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}
// Sequential: dark surface -> saturated blue, so magnitude reads as luminance.
function seq(t) {
  const [r, g, b] = rampRgb(BLUE, 1 - Math.max(0, Math.min(1, t)));
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}
// Diverging: warm for dorsal, cool for ventral, neutral grey at zero.
const MID = hexToRgb('#383835'), WARM = hexToRgb('#e66767'), COOL = hexToRgb('#3987e5');
function divRgb(v) {
  const t = Math.max(-1, Math.min(1, v));
  const end = t >= 0 ? WARM : COOL, a = Math.abs(t);
  return [lerp(MID[0], end[0], a), lerp(MID[1], end[1], a), lerp(MID[2], end[2], a)];
}
function div(v) { const c = divRgb(v); return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`; }

/* ---------------------------------------------------------------------- state ----- */

const S = {
  meta: null, frame: null, field: null,
  overlay: 'attractant',
  view: { cx: 0, cy: 0, span: 6.5 },   // dish window, mm
  follow: true,
  trail: [],
  kymo: null, kymoCtx: null,
  traces: [], selected: [],
  hover: null,
  ablateMode: false, ablated: new Set(),
  freq: 0, freqBuf: [],
  connected: false,
};

const el = (id) => document.getElementById(id);
const tooltip = el('tooltip');

/* --------------------------------------------------------------------- canvas ----- */

function fitCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: r.width, h: r.height };
}

/* ----------------------------------------------------------------------- dish ----- */

let fieldCanvas = null;

function drawDish() {
  const { ctx, w, h } = fitCanvas(el('c-dish'));
  ctx.clearRect(0, 0, w, h);
  if (!S.meta) return;
  const f = S.frame;
  const R = S.meta.world.radius;

  // world -> screen
  const scale = Math.min(w, h) / S.view.span;
  const X = (x) => (x - S.view.cx) * scale + w / 2;
  const Y = (y) => (S.view.cy - y) * scale + h / 2;

  ctx.save();
  ctx.beginPath();
  ctx.arc(X(0), Y(0), R * scale, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = '#141413';
  ctx.fillRect(0, 0, w, h);

  drawGrid(ctx, X, Y, scale, w, h, R);
  if (S.field && S.overlay !== 'none') drawField(ctx, X, Y, scale);

  // obstacles
  ctx.fillStyle = '#3a3936';
  ctx.strokeStyle = 'rgba(255,255,255,0.12)';
  for (const [ox, oy, orad] of S.meta.world.obstacles) {
    ctx.beginPath(); ctx.arc(X(ox), Y(oy), orad * scale, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
  }
  ctx.restore();

  // dish rim
  ctx.strokeStyle = C('--baseline'); ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(X(0), Y(0), R * scale, 0, Math.PI * 2); ctx.stroke();

  // trail
  if (S.trail.length > 1) {
    ctx.strokeStyle = 'rgba(195,194,183,0.30)'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    S.trail.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))));
    ctx.stroke();
  }

  if (f) drawWorm(ctx, f, X, Y, scale);
  drawMinimap(ctx, w, h, R, f);
  drawScaleBar(ctx, w, h, scale);
}

// A grid fixed in the dish, not to the camera. Without a static reference an undulating
// worm on an empty dark background is genuinely impossible to tell apart from one
// swimming on the spot -- the eye has nothing to measure the translation against.
function drawGrid(ctx, X, Y, scale, w, h, R) {
  const span = S.view.span;
  const step = span > 20 ? 5 : span > 8 ? 2 : span > 3 ? 1 : 0.5;
  const x0 = Math.ceil((S.view.cx - span) / step) * step;
  const y0 = Math.ceil((S.view.cy - span) / step) * step;
  ctx.lineWidth = 1;
  for (let x = x0; x < S.view.cx + span; x += step) {
    ctx.strokeStyle = Math.abs(x) < 1e-9 ? 'rgba(195,194,183,0.16)' : 'rgba(195,194,183,0.055)';
    ctx.beginPath(); ctx.moveTo(X(x), 0); ctx.lineTo(X(x), h); ctx.stroke();
  }
  for (let y = y0; y < S.view.cy + span; y += step) {
    ctx.strokeStyle = Math.abs(y) < 1e-9 ? 'rgba(195,194,183,0.16)' : 'rgba(195,194,183,0.055)';
    ctx.beginPath(); ctx.moveTo(0, Y(y)); ctx.lineTo(w, Y(y)); ctx.stroke();
  }
}

function drawField(ctx, X, Y, scale) {
  const n = S.field.n;
  if (!fieldCanvas) { fieldCanvas = document.createElement('canvas'); }
  if (fieldCanvas.width !== n) { fieldCanvas.width = fieldCanvas.height = n; }
  const fc = fieldCanvas.getContext('2d');
  const img = fc.createImageData(n, n);
  const chan = { attractant: 0, food: 1, repellent: 2 }[S.overlay];
  // Each overlay is its own single-hue ramp: blue for the attractant gradient, aqua for
  // the bacterial lawn, red for the noxious drop.
  const tint = [[57, 135, 229], [25, 158, 112], [208, 59, 59]][chan];
  const src = S.field.data;
  // Gamma > 1 keeps the low end of the ramp near the surface. A chemical gradient covers
  // the whole plate at some concentration, so a flatter mapping just washes the dish out
  // and hides the very structure the gradient is there to show.
  for (let i = 0; i < n * n; i++) {
    const v = src[i * 3 + chan] / 255;
    const a = Math.pow(v, 2.1);
    img.data[i * 4] = tint[0]; img.data[i * 4 + 1] = tint[1]; img.data[i * 4 + 2] = tint[2];
    img.data[i * 4 + 3] = a * 205;
  }
  fc.putImageData(img, 0, 0);
  const R = S.meta.world.radius;
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(fieldCanvas, X(-R), Y(R), 2 * R * scale, 2 * R * scale);
}

function drawWorm(ctx, f, X, Y, scale) {
  const nodes = f.nodes, rad = S.meta.radius, k = f.kappa;
  const n = nodes.length / 2;

  // Outward normals at each node, from the local tangent.
  const nx = new Float32Array(n), ny = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - 1), b = Math.min(n - 1, i + 1);
    let tx = nodes[b * 2] - nodes[a * 2], ty = nodes[b * 2 + 1] - nodes[a * 2 + 1];
    const L = Math.hypot(tx, ty) || 1; tx /= L; ty /= L;
    nx[i] = -ty; ny[i] = tx;
  }
  const rOf = (i) => (i === 0 ? rad[0] : i >= rad.length ? rad[rad.length - 1] : rad[i]) * 1.0;

  // Body drawn as a ribbon of quads, each tinted by its local curvature. A worm's shape
  // is the readable thing about it, and colouring by signed curvature makes the
  // travelling wave visible as a wave rather than as a wiggle.
  for (let i = 0; i < n - 1; i++) {
    const kv = k.length ? k[Math.min(k.length - 1, Math.max(0, i - 1))] / 7.0 : 0;
    const r0 = rOf(i) * scale, r1 = rOf(i + 1) * scale;
    const x0 = X(nodes[i * 2]), y0 = Y(nodes[i * 2 + 1]);
    const x1 = X(nodes[(i + 1) * 2]), y1 = Y(nodes[(i + 1) * 2 + 1]);
    ctx.beginPath();
    ctx.moveTo(x0 + nx[i] * r0, y0 - ny[i] * r0);
    ctx.lineTo(x1 + nx[i + 1] * r1, y1 - ny[i + 1] * r1);
    ctx.lineTo(x1 - nx[i + 1] * r1, y1 + ny[i + 1] * r1);
    ctx.lineTo(x0 - nx[i] * r0, y0 + ny[i] * r0);
    ctx.closePath();
    const c = divRgb(kv);
    ctx.fillStyle = `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
    ctx.fill();
  }

  // Outline and head marker.
  ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const r = rOf(i) * scale, x = X(nodes[i * 2]), y = Y(nodes[i * 2 + 1]);
    const px = x + nx[i] * r, py = y - ny[i] * r;
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  for (let i = n - 1; i >= 0; i--) {
    const r = rOf(i) * scale, x = X(nodes[i * 2]), y = Y(nodes[i * 2 + 1]);
    ctx.lineTo(x - nx[i] * r, y + ny[i] * r);
  }
  ctx.closePath(); ctx.stroke();

  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(X(nodes[0]), Y(nodes[1]), Math.max(1.6, rOf(0) * scale * 0.45), 0, Math.PI * 2);
  ctx.fill();
}

function drawMinimap(ctx, w, h, R, f) {
  const size = 84, pad = 12;
  const cx = w - pad - size / 2, cy = h - pad - size / 2, s = (size / 2) / R;
  ctx.save();
  ctx.fillStyle = 'rgba(13,13,13,0.82)';
  ctx.strokeStyle = C('--border'); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, size / 2, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.arc(cx, cy, size / 2, 0, Math.PI * 2); ctx.clip();
  for (const p of S.meta.world.patches) {
    ctx.fillStyle = p.kind === 'food' ? 'rgba(25,158,112,0.55)' : 'rgba(208,59,59,0.5)';
    ctx.beginPath(); ctx.arc(cx + p.x * s, cy - p.y * s, Math.max(1.5, p.r * s), 0, Math.PI * 2);
    ctx.fill();
  }
  if (S.trail.length > 1) {
    ctx.strokeStyle = 'rgba(195,194,183,0.5)'; ctx.lineWidth = 1;
    ctx.beginPath();
    S.trail.forEach((p, i) => (i ? ctx.lineTo(cx + p[0] * s, cy - p[1] * s)
                                : ctx.moveTo(cx + p[0] * s, cy - p[1] * s)));
    ctx.stroke();
  }
  if (f) {
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(cx + f.nodes[0] * s, cy - f.nodes[1] * s, 2.4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawScaleBar(ctx, w, h, scale) {
  const mm = S.view.span > 14 ? 5 : S.view.span > 4 ? 1 : 0.2;
  const px = mm * scale, x = 14, y = h - 16;
  ctx.strokeStyle = C('--text-muted'); ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + px, y); ctx.stroke();
  ctx.fillStyle = C('--text-muted'); ctx.font = '11px system-ui';
  ctx.fillText(mm >= 1 ? `${mm} mm` : `${mm * 1000} µm`, x, y - 5);
}

/* ------------------------------------------------------------------- neurons ------ */

let layout = null;

function buildLayout(w, h) {
  // Ordered head to tail by soma position and packed into an even grid. Binning on the
  // raw position instead would be more literally anatomical but unreadable: half of the
  // 302 neurons have their cell bodies inside the nerve ring, so they pile into the first
  // few columns and leave the rest of the panel empty. Rank order keeps the anatomy
  // monotonic while giving every neuron the same amount of room.
  const N = S.meta.neurons;
  const padL = 10, padR = 10, padT = 24, padB = 16;
  const availW = w - padL - padR, availH = h - padT - padB;
  const n = N.length;
  let cols = Math.max(1, Math.round(Math.sqrt(n * availW / Math.max(availH, 1))));
  let rows = Math.ceil(n / cols);
  while (rows * (availH / rows) > availH && rows > 1) rows--;
  const dx = availW / cols, dy = availH / rows;
  const r = Math.max(1.6, Math.min(dx, dy) * 0.40);
  const order = N.map((_, i) => i);
  const pts = new Array(n);
  order.forEach((i, k) => {
    const c = k % cols, rr = Math.floor(k / cols);
    pts[i] = { x: padL + dx * (c + 0.5), y: padT + dy * (rr + 0.5), r };
  });
  return { pts };
}

function drawNeurons() {
  const cv = el('c-neurons');
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
    const dead = S.ablated.has(i);
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    if (dead) {
      ctx.fillStyle = C('--bg'); ctx.fill();
      ctx.strokeStyle = C('--text-muted'); ctx.lineWidth = 1;
      ctx.stroke();
      const q = p.r * 0.75;
      ctx.beginPath();
      ctx.moveTo(p.x - q, p.y - q); ctx.lineTo(p.x + q, p.y + q);
      ctx.moveTo(p.x + q, p.y - q); ctx.lineTo(p.x - q, p.y + q);
      ctx.stroke();
    } else {
      ctx.fillStyle = seq(a);
      ctx.fill();
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

/* -------------------------------------------------------------------- muscles ----- */

function drawMuscles() {
  const { ctx, w, h } = fitCanvas(el('c-muscle'));
  ctx.clearRect(0, 0, w, h);
  if (!S.meta || !S.frame) return;
  const quads = ['MDL', 'MDR', 'MVL', 'MVR'];
  const padL = 40, padT = 24, padB = 8, gap = 2;
  const rowH = (h - padT - padB) / 4;
  const cellW = (w - padL - 10) / 24;
  ctx.font = '10px system-ui';
  quads.forEach((q, r) => {
    ctx.fillStyle = C('--text-muted');
    ctx.fillText(q, 8, padT + rowH * r + rowH / 2 + 3);
    for (let c = 0; c < 24; c++) {
      const name = q + String(c + 1).padStart(2, '0');
      const idx = S.meta.muscleIndex[name];
      if (idx === undefined) continue;      // MVL has only 23 cells
      ctx.fillStyle = seq(S.frame.tension[idx]);
      ctx.fillRect(padL + cellW * c, padT + rowH * r, cellW - gap, rowH - gap);
    }
  });
  ctx.fillStyle = C('--text-muted');
  ctx.fillText('anterior', padL, h - 1);
  ctx.textAlign = 'right'; ctx.fillText('posterior', w - 10, h - 1); ctx.textAlign = 'left';
}

/* ------------------------------------------------------------------ kymograph ----- */

const KYMO_W = 600;

function pushKymo(kappa, t) {
  // A ring buffer of raw curvature, converted to pixels only when drawn. Scrolling a
  // canvas by blitting it onto itself reads back pixels it has already overwritten, so
  // the history smears instead of sliding; keeping the numbers and rebuilding the image
  // avoids the question entirely, and 600 x 47 is nothing to redraw.
  if (!S.kymo || S.kymo.rows !== kappa.length) {
    S.kymo = {
      rows: kappa.length,
      data: new Float32Array(KYMO_W * kappa.length),
      head: 0,
      filled: 0,
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

function drawKymo() {
  const { ctx, w, h } = fitCanvas(el('c-kymo'));
  ctx.clearRect(0, 0, w, h);
  const img = renderKymo();
  if (!img) return;
  const padT = 24, padL = 34, padB = 6;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, padL, padT, w - padL - 8, h - padT - padB);
  ctx.fillStyle = C('--text-muted'); ctx.font = '10px system-ui';
  ctx.fillText('head', 4, padT + 8);
  ctx.fillText('tail', 6, h - padB - 1);
}

/* --------------------------------------------------------------------- traces ----- */

function drawTraces() {
  const { ctx, w, h } = fitCanvas(el('c-trace'));
  ctx.clearRect(0, 0, w, h);
  if (!S.traces.length || !S.selected.length) return;
  const padL = 34, padT = 24, padB = 16, padR = 8;
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
  // The three traces usually sit within a few millivolts of each other, so nudge the
  // labels apart rather than letting them overprint.
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
  ctx.fillStyle = C('--text-muted'); ctx.font = '10px system-ui';
  ctx.fillText('mV', 6, padT - 6);
}

/* ----------------------------------------------------------------- interaction ---- */

function neuronAt(cv, ev) {
  if (!layout) return null;
  const r = cv.getBoundingClientRect();
  // The layout is built in the canvas's backing-store pixels, which are devicePixelRatio
  // times the CSS pixels a mouse event reports. Comparing the two directly meant that on
  // any HiDPI display -- which is to say on most machines this has ever run on -- the hit
  // test was out by a factor of two and no neuron could be hovered or clicked at all.
  const sx = cv.width / Math.max(r.width, 1), sy = cv.height / Math.max(r.height, 1);
  const x = (ev.clientX - r.left) * sx, y = (ev.clientY - r.top) * sy;
  let best = null, bd = 81;
  layout.pts.forEach((p, i) => {
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d < bd) { bd = d; best = i; }
  });
  return best;
}

function showTip(ev, html) {
  tooltip.innerHTML = html;
  tooltip.classList.add('on');
  const pad = 14;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
  tooltip.style.left = `${x}px`; tooltip.style.top = `${y}px`;
}
const hideTip = () => tooltip.classList.remove('on');

function wire() {
  const dish = el('c-dish');
  dish.addEventListener('wheel', (e) => {
    e.preventDefault();
    S.view.span = Math.max(1.6, Math.min(52, S.view.span * Math.exp(e.deltaY * 0.0016)));
  }, { passive: false });
  dish.addEventListener('click', (e) => {
    if (!S.meta) return;
    const r = dish.getBoundingClientRect();
    const scale = Math.min(r.width, r.height) / S.view.span;
    const x = S.view.cx + (e.clientX - r.left - r.width / 2) / scale;
    const y = S.view.cy - (e.clientY - r.top - r.height / 2) / scale;
    if (Math.hypot(x, y) > S.meta.world.radius - 1) return;
    send({ cmd: 'drop_food', x, y, r: 2.5 });
    S.meta.world.patches.push({ x, y, r: 2.5, kind: 'food' });
  });

  const nc = el('c-neurons');
  nc.addEventListener('mousemove', (e) => {
    const i = neuronAt(nc, e);
    S.hover = i;
    if (i == null || !S.frame) { hideTip(); el('neuron-hint').textContent = 'hover a neuron'; return; }
    const n = S.meta.neurons[i];
    showTip(e, `<b>${n.name}</b> &middot; ${n.cls}<br>
      <span class="k">kind</span> ${n.kind}${n.modality ? ' &middot; ' + n.modality : ''}<br>
      <span class="k">ganglion</span> ${n.ganglion}<br>
      <span class="k">transmitter</span> ${n.tx}${n.inh ? ' (inhibitory)' : ''}<br>
      <span class="k">V</span> ${S.frame.V[i].toFixed(1)} mV &nbsp;
      <span class="k">activity</span> ${(S.frame.act[i] * 100).toFixed(0)}%`);
    el('neuron-hint').textContent = 'click to plot';
  });
  nc.addEventListener('mouseleave', () => { S.hover = null; hideTip(); });
  nc.addEventListener('click', (e) => {
    const i = neuronAt(nc, e);
    if (i == null) return;
    if (S.ablateMode) {
      const name = S.meta.neurons[i].name;
      if (S.ablated.has(i)) return;              // ablation is not undone one cell at a time
      S.ablated.add(i);
      send({ cmd: 'ablate', neurons: [name] });
      updateAblateUI();
      return;
    }
    const at = S.selected.indexOf(i);
    if (at >= 0) S.selected.splice(at, 1);
    else { S.selected.push(i); if (S.selected.length > 3) S.selected.shift(); }
    S.traces = S.selected.map(() => []);
    el('trace-hint').textContent = S.selected.map((k) => S.meta.neurons[k].name).join(', ') || '—';
  });

  el('b-play').addEventListener('click', (e) => {
    const playing = e.target.getAttribute('aria-pressed') === 'true';
    e.target.setAttribute('aria-pressed', String(!playing));
    e.target.textContent = playing ? 'Play' : 'Pause';
    send({ cmd: playing ? 'pause' : 'play' });
  });
  el('b-reset').addEventListener('click', () => {
    S.ablated.clear(); updateAblateUI();
    S.trail = []; S.kymo = null; S.traces = S.selected.map(() => []);
    send({ cmd: 'reset' });
  });
  el('r-rate').addEventListener('input', (e) => {
    const v = Math.pow(10, parseFloat(e.target.value) / 2);
    el('o-rate').textContent = `${v.toFixed(v < 1 ? 2 : 1)}×`;
    send({ cmd: 'rate', value: v });
  });
  el('b-follow').addEventListener('click', (e) => {
    S.follow = !S.follow;
    e.target.setAttribute('aria-pressed', String(S.follow));
    e.target.textContent = S.follow ? 'Follow' : 'Fixed';
    if (S.follow) S.recentre = true;
  });
  el('b-ablate').addEventListener('click', () => {
    S.ablateMode = !S.ablateMode;
    updateAblateUI();
  });
  el('b-restore').addEventListener('click', () => {
    if (!S.ablated.size) return;
    S.ablated.clear();
    send({ cmd: 'restore' });
    updateAblateUI();
  });

  el('b-poke-a').addEventListener('click', () => send({ cmd: 'poke', where: 'anterior', strength: 1.4 }));
  el('b-poke-p').addEventListener('click', () => send({ cmd: 'poke', where: 'posterior', strength: 1.4 }));

  document.querySelectorAll('[data-medium]').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('[data-medium]').forEach((o) => o.setAttribute('aria-pressed', 'false'));
    b.setAttribute('aria-pressed', 'true');
    send({ cmd: 'medium', value: b.dataset.medium });
  }));
  document.querySelectorAll('[data-field]').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('[data-field]').forEach((o) => o.setAttribute('aria-pressed', 'false'));
    b.setAttribute('aria-pressed', 'true');
    S.overlay = b.dataset.field;
  }));
}

/* ------------------------------------------------------------------- transport ---- */

let ws = null;
function updateAblateUI() {
  const b = el('b-ablate');
  b.setAttribute('aria-pressed', String(S.ablateMode));
  b.textContent = S.ablateMode ? 'Click a cell' : 'Ablate';
  el('b-restore').disabled = S.ablated.size === 0;
  const n = S.ablated.size;
  el('neuron-hint').textContent = S.ablateMode
    ? 'click a neuron to silence it'
    : (n ? n + ' ablated' : 'hover a neuron');
}

function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }

function connect() {
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
  layout = null; S.kymo = null; S.trail = [];
  S.recentre = true;
  const want = ['DB01', 'VB01', 'AVBL'];
  S.selected = want.map((n) => m.neurons.findIndex((x) => x.name === n)).filter((i) => i >= 0);
  S.traces = S.selected.map(() => []);
  el('trace-hint').textContent = S.selected.map((k) => m.neurons[k].name).join(', ');
  el('dish-hint').textContent = `${m.neurons.length} neurons · ${m.counts.chem} synapses · ${m.counts.gap} gap junctions`;
}

// Seven receptor readings, drawn as labelled bars. Ranges are the physiological span of
// each field in this dish, not the observed min/max, so a flat bar means the animal is
// genuinely sitting at one end rather than that the scale collapsed.
const SENSE_ROWS = [
  ['Attractant', 'attractant', 0, 1.1, 'var(--series-1)'],
  ['Food',       'food',       0, 1.0, 'var(--series-3)'],
  ['Repellent',  'repellent',  0, 0.9, 'var(--series-2)'],
  ['Oxygen',     'oxygen',     0.05, 0.21, 'var(--series-4)'],
  ['Temperature','temperature', 17, 25, 'var(--series-5)'],
  ['Touch',      'touch',      0, 3.0, 'var(--series-6)'],
  ['Forward gate', 'gateF',    0, 1.0, 'var(--text-secondary)'],
  // 1.0 is a fully stocked mechanoreceptor; it falls as the animal habituates to
  // repeated taps and refills over minutes of quiet. The only state in the model that
  // outlives a modulator, and the only thing here that is memory rather than filtering.
  ['Touch memory', 'habituation', 0, 1.0, 'var(--series-2)'],
];
const SENSE_FMT = { oxygen: v => (100 * v).toFixed(1) + '%',
                    temperature: v => v.toFixed(1) + '\u00b0C',
                    habituation: v => (100 * v).toFixed(0) + '%' };

function drawSenses(sensed) {
  let host = el('senses');
  if (!host) return;
  if (!host.dataset.built) {
    host.innerHTML = SENSE_ROWS.map(([label, key, , , colour]) => `
      <span class="s-name">${label}</span>
      <span class="s-bar"><span class="s-fill" data-fill="${key}"
            style="background:${colour}"></span></span>
      <span class="s-val" data-val="${key}">&mdash;</span>`).join('');
    host.dataset.built = '1';
  }
  for (const [, key, lo, hi] of SENSE_ROWS) {
    const v = sensed[key] ?? 0;
    const frac = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    host.querySelector(`[data-fill="${key}"]`).style.width = (100 * frac) + '%';
    host.querySelector(`[data-val="${key}"]`).textContent =
      (SENSE_FMT[key] || (x => x.toFixed(2)))(v);
  }
}

function onFrame(buf, dv) {
  const nNodes = dv.getUint32(4, true), nNeu = dv.getUint32(8, true);
  const nMus = dv.getUint32(12, true), nJoint = dv.getUint32(16, true);
  const running = dv.getUint32(20, true);
  let o = 24;
  const t = dv.getFloat32(o, true), speed = dv.getFloat32(o + 4, true);
  const food = dv.getFloat32(o + 8, true), dir = dv.getFloat32(o + 12, true);
  const achieved = dv.getFloat32(o + 16, true);
  // What the animal is actually sensing.
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
  };

  let p = HEADER_BYTES;
  const nodes = new Float32Array(buf, p, nNodes * 2); p += nNodes * 8;
  const act = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const V = new Float32Array(buf, p, nNeu); p += nNeu * 4;
  const tension = new Float32Array(buf, p, nMus); p += nMus * 4;
  const kappa = new Float32Array(buf, p, nJoint);

  S.frame = { t, speed, food, dir, achieved, sensed, nodes, act, V, tension, kappa, running };
  drawSenses(sensed);

  const cx = nodes.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0) / nNodes;
  const cy = nodes.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0) / nNodes;

  // Follow the centroid, not the head, and only once the animal has drifted out of the
  // middle of the frame. Locking the camera rigidly to the head was actively misleading:
  // the head swings from side to side once per undulation, so the camera swung with it and
  // cancelled out the very motion it was supposed to show. With a deadzone the worm
  // visibly crawls across the frame before the view catches up.
  if (S.recentre) { S.view.cx = cx; S.view.cy = cy; S.recentre = false; }
  if (S.follow) {
    const dead = S.view.span * 0.18;
    const dx = cx - S.view.cx, dy = cy - S.view.cy;
    const d = Math.hypot(dx, dy);
    if (d > dead) {
      const pull = (d - dead) / d;
      S.view.cx += dx * pull;
      S.view.cy += dy * pull;
    }
  }
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

// Undulation frequency from zero crossings of midbody curvature, about its own mean.
// A worm holding a turn has a large standing offset in its curvature; counting raw sign
// changes would call that "no undulation" while it is plainly still undulating.
function updateFreq(k, t) {
  const b = S.freqBuf;
  b.push([t, k]);
  while (b.length && t - b[0][0] > 12) b.shift();
  if (b.length < 40) return;
  const mean = b.reduce((a, x) => a + x[1], 0) / b.length;
  const dev = Math.sqrt(b.reduce((a, x) => a + (x[1] - mean) ** 2, 0) / b.length);
  if (dev < 0.15) { S.freq = 0; return; }        // genuinely not undulating
  let crossings = 0;
  for (let i = 1; i < b.length; i++) {
    if ((b[i - 1][1] - mean < 0) !== (b[i][1] - mean < 0)) crossings++;
  }
  const span = b[b.length - 1][0] - b[0][0];
  S.freq = span > 0 ? crossings / (2 * span) : 0;
}

function updateStats(t, speed, food, dir, achieved, running) {
  el('s-time').innerHTML = `${t.toFixed(1)}<small>s</small>`;
  el('s-speed').innerHTML = `${(speed * 1000).toFixed(0)}<small>µm/s</small>`;
  el('s-freq').innerHTML = S.freq > 0.02
    ? `${S.freq.toFixed(2)}<small>Hz</small>` : `—<small>Hz</small>`;
  el('s-dir').textContent = dir > 0.5 ? 'forward' : dir < -0.5 ? 'backward' : 'still';
  el('s-dir').style.color = dir < -0.5 ? C('--warning') : C('--text-primary');
  el('s-food').textContent = food.toFixed(1);
  el('s-rate').innerHTML = `${achieved.toFixed(1)}<small>×</small>`;
  const btn = el('b-play');
  if ((btn.getAttribute('aria-pressed') === 'true') !== !!running) {
    btn.setAttribute('aria-pressed', String(!!running));
    btn.textContent = running ? 'Pause' : 'Play';
  }
}

/* ----------------------------------------------------------------------- loop ----- */

function tick() {
  drawDish();
  drawNeurons();
  drawMuscles();
  drawKymo();
  drawTraces();
  requestAnimationFrame(tick);
}

wire();
connect();
requestAnimationFrame(tick);
