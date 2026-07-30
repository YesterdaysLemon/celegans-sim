/* celegans-sim viewer.
 *
 * Receives packed float32 telemetry over a WebSocket and draws the dish, the nervous
 * system, the body-wall muscle sheets, a curvature kymograph and membrane traces.
 *
 * The dish has three looks and they are not a palette swap. Each is a different claim
 * about what you are looking at:
 *
 *   digital     this is data. Near-black plate, a fixed grid, the body tinted by signed
 *               curvature so the travelling wave reads as a wave.
 *   cartoon     this is a diagram. Flat fills, heavy outlines, one obvious eye. Nothing
 *               is shaded, so nothing suggests depth that the model does not have.
 *   realistic   this is an animal on a plate. Warm agar, a translucent amber body with a
 *               gut line and a specular edge, bacterial lawn as a mottled film.
 *
 * Only the dish changes. The panels stay in the data palette in every mode, because they
 * are measurements and should not be dressed up.
 *
 * Colour follows the data-viz reference palette. Magnitudes (activation, tension) use one
 * sequential hue; signed curvature uses the diverging blue-red pair with a neutral grey
 * midpoint, so "straight" reads as nothing rather than as a colour.
 */

const MAGIC = 0x574f524d;
const FIELD_MAGIC = 0x574f524e;
const HEADER_BYTES = 92;   // 6 uint32 + 17 float32

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
const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

/* ---------------------------------------------------------------------- state ----- */

const S = {
  meta: null, frame: null, field: null,
  theme: 'digital',
  layers: { food: true, attractant: true, repellent: true, grid: true, trail: true },
  view: { cx: 0, cy: 0, span: 6.5 },   // dish window, mm
  cam: 'follow',                        // 'follow' | 'free'
  trail: [],
  kymo: null,
  traces: [], selected: [],
  hover: null,
  ablateMode: false, ablated: new Set(),
  freq: 0, freqBuf: [],
  pumpFlash: 0, lastPumping: 0,
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

/* ---------------------------------------------------------------------- themes ---- */

// A speckle used by the realistic plate. Agar under a stereoscope is not a flat colour;
// without some grain the dish reads as a flat fill with a worm pasted on it.
let noiseTile = null;
function getNoise() {
  if (noiseTile) return noiseTile;
  const n = 128;
  const cv = document.createElement('canvas');
  cv.width = cv.height = n;
  const c = cv.getContext('2d');
  const img = c.createImageData(n, n);
  let seed = 7;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  for (let i = 0; i < n * n; i++) {
    const v = rnd();
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = 255;
    img.data[i * 4 + 3] = v * v * 40;
  }
  c.putImageData(img, 0, 0);
  noiseTile = cv;
  return cv;
}

const THEMES = {
  digital: {
    plate: '#141413',
    rim: () => C('--baseline'),
    gridMajor: 'rgba(195,194,183,0.16)',
    gridMinor: 'rgba(195,194,183,0.055)',
    trail: 'rgba(195,194,183,0.30)',
    obstacle: ['#3a3936', 'rgba(255,255,255,0.12)'],
    // Field tints, alpha and gamma per layer. Gamma > 1 keeps the low end near the
    // surface: a chemical gradient covers the whole plate at some concentration, so a
    // flatter mapping just washes the dish out and hides the structure.
    fields: {
      attractant: { tint: [57, 135, 229], alpha: 0.80, gamma: 2.1 },
      food:       { tint: [25, 158, 112], alpha: 0.80, gamma: 2.1 },
      repellent:  { tint: [208, 59, 59],  alpha: 0.80, gamma: 2.1 },
    },
    worm: drawWormDigital,
  },

  cartoon: {
    plate: '#f2ead8',
    rim: () => '#2b2722',
    gridMajor: 'rgba(43,39,34,0.20)',
    gridMinor: 'rgba(43,39,34,0.08)',
    trail: 'rgba(43,39,34,0.22)',
    obstacle: ['#cbbfa6', '#2b2722'],
    fields: {
      attractant: { tint: [120, 176, 240], alpha: 0.55, gamma: 1.3 },
      food:       { tint: [124, 196, 122], alpha: 0.80, gamma: 0.75 },
      repellent:  { tint: [232, 118, 108], alpha: 0.72, gamma: 0.9 },
    },
    worm: drawWormCartoon,
    dark: true,          // chrome-on-light: the scale bar and minimap need ink, not chalk
  },

  realistic: {
    plate: '#8d8676',
    rim: () => 'rgba(28,25,20,0.85)',
    gridMajor: 'rgba(40,35,28,0.10)',
    gridMinor: 'rgba(40,35,28,0.04)',
    trail: 'rgba(60,54,44,0.22)',
    obstacle: ['#6d6659', 'rgba(30,26,20,0.5)'],
    fields: {
      attractant: { tint: [150, 170, 190], alpha: 0.30, gamma: 1.6 },
      food:       { tint: [226, 220, 190], alpha: 0.85, gamma: 0.8 },
      repellent:  { tint: [150, 120, 150], alpha: 0.45, gamma: 1.2 },
    },
    worm: drawWormRealistic,
    dark: true,
    grain: true,
    vignette: true,
  },
};
const theme = () => THEMES[S.theme];

/* ----------------------------------------------------------------------- dish ----- */

let fieldCanvas = null;

function drawDish() {
  const { ctx, w, h } = fitCanvas(el('c-dish'));
  const T = theme();
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
  ctx.fillStyle = T.plate;
  ctx.fillRect(0, 0, w, h);

  if (S.layers.grid) drawGrid(ctx, X, Y, w, h);
  if (S.field) drawFields(ctx, X, Y, scale);
  if (T.grain) drawGrain(ctx, w, h);

  ctx.fillStyle = T.obstacle[0];
  ctx.strokeStyle = T.obstacle[1];
  ctx.lineWidth = S.theme === 'cartoon' ? 2 : 1;
  for (const [ox, oy, orad] of S.meta.world.obstacles) {
    ctx.beginPath(); ctx.arc(X(ox), Y(oy), orad * scale, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
  }

  if (S.layers.trail && S.trail.length > 1) {
    ctx.strokeStyle = T.trail;
    ctx.lineWidth = S.theme === 'cartoon' ? 2 : 1.5;
    ctx.lineJoin = ctx.lineCap = 'round';
    ctx.beginPath();
    S.trail.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))));
    ctx.stroke();
  }

  if (f) T.worm(ctx, geometry(f, X, Y, scale), f, scale);
  if (T.vignette) drawVignette(ctx, w, h);
  ctx.restore();

  // dish rim, drawn outside the clip so it is a crisp edge rather than a half-covered one
  ctx.strokeStyle = T.rim(); ctx.lineWidth = S.theme === 'cartoon' ? 3 : 2;
  ctx.beginPath(); ctx.arc(X(0), Y(0), R * scale, 0, Math.PI * 2); ctx.stroke();

  drawMinimap(ctx, w, h, R, f);
  drawScaleBar(ctx, w, h, scale);
}

// A grid fixed in the dish, not to the camera. Without a static reference an undulating
// worm on an empty background is genuinely impossible to tell apart from one swimming on
// the spot -- the eye has nothing to measure the translation against.
function drawGrid(ctx, X, Y, w, h) {
  const T = theme(), span = S.view.span;
  const step = span > 20 ? 5 : span > 8 ? 2 : span > 3 ? 1 : 0.5;
  const x0 = Math.ceil((S.view.cx - span) / step) * step;
  const y0 = Math.ceil((S.view.cy - span) / step) * step;
  ctx.lineWidth = 1;
  for (let x = x0; x < S.view.cx + span; x += step) {
    ctx.strokeStyle = Math.abs(x) < 1e-9 ? T.gridMajor : T.gridMinor;
    ctx.beginPath(); ctx.moveTo(X(x), 0); ctx.lineTo(X(x), h); ctx.stroke();
  }
  for (let y = y0; y < S.view.cy + span; y += step) {
    ctx.strokeStyle = Math.abs(y) < 1e-9 ? T.gridMajor : T.gridMinor;
    ctx.beginPath(); ctx.moveTo(0, Y(y)); ctx.lineTo(w, Y(y)); ctx.stroke();
  }
}

// All three chemical fields at once, each its own hue, composited in one pass. The
// previous viewer showed one at a time, which meant the two things the animal is
// actually choosing between -- a lawn to sit on and a drop to avoid -- could never be
// seen together.
const CHAN = { attractant: 0, food: 1, repellent: 2 };
function drawFields(ctx, X, Y, scale) {
  const n = S.field.n, T = theme();
  const on = Object.keys(CHAN).filter((k) => S.layers[k]);
  if (!on.length) return;
  if (!fieldCanvas) fieldCanvas = document.createElement('canvas');
  if (fieldCanvas.width !== n) { fieldCanvas.width = fieldCanvas.height = n; }
  const fc = fieldCanvas.getContext('2d');
  const img = fc.createImageData(n, n);
  const src = S.field.data;
  const specs = on.map((k) => [CHAN[k], T.fields[k]]);

  for (let i = 0; i < n * n; i++) {
    // Composite the visible layers by weight rather than painting one over another, so a
    // lawn sitting inside an attractant gradient shows as both instead of hiding one.
    let r = 0, g = 0, b = 0, wsum = 0;
    for (const [chan, spec] of specs) {
      const a = Math.pow(src[i * 3 + chan] / 255, spec.gamma) * spec.alpha;
      if (a <= 0.001) continue;
      r += spec.tint[0] * a; g += spec.tint[1] * a; b += spec.tint[2] * a;
      wsum += a;
    }
    const o = i * 4;
    if (wsum <= 0.001) { img.data[o + 3] = 0; continue; }
    img.data[o] = r / wsum; img.data[o + 1] = g / wsum; img.data[o + 2] = b / wsum;
    img.data[o + 3] = Math.min(1, wsum) * 235;
  }
  fc.putImageData(img, 0, 0);
  const R = S.meta.world.radius;
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(fieldCanvas, X(-R), Y(R), 2 * R * scale, 2 * R * scale);
}

function drawGrain(ctx, w, h) {
  const tile = getNoise();
  const pat = ctx.createPattern(tile, 'repeat');
  ctx.save();
  ctx.globalAlpha = 0.55;
  ctx.fillStyle = pat;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();
}

function drawVignette(ctx, w, h) {
  const g = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.22,
                                     w / 2, h / 2, Math.max(w, h) * 0.72);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, 'rgba(0,0,0,0.42)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
}

/* ------------------------------------------------------------------- the worm ----- */

// Shared geometry: screen-space centreline, outward normals and radii. Every painter
// works from this, so the three modes are guaranteed to draw the same animal.
function geometry(f, X, Y, scale) {
  const nodes = f.nodes, rad = S.meta.radius;
  const n = nodes.length / 2;
  const px = new Float32Array(n), py = new Float32Array(n);
  const nx = new Float32Array(n), ny = new Float32Array(n), r = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    px[i] = X(nodes[i * 2]); py[i] = Y(nodes[i * 2 + 1]);
  }
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - 1), b = Math.min(n - 1, i + 1);
    let tx = px[b] - px[a], ty = py[b] - py[a];
    const L = Math.hypot(tx, ty) || 1; tx /= L; ty /= L;
    nx[i] = -ty; ny[i] = tx;                      // screen-space normal
    r[i] = (i < rad.length ? rad[i] : rad[rad.length - 1]) * scale;
  }
  return { n, px, py, nx, ny, r, kappa: f.kappa };
}

function bodyPath(ctx, G, swell = 1) {
  ctx.beginPath();
  for (let i = 0; i < G.n; i++) {
    const R = G.r[i] * swell;
    const x = G.px[i] + G.nx[i] * R, y = G.py[i] + G.ny[i] * R;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  for (let i = G.n - 1; i >= 0; i--) {
    const R = G.r[i] * swell;
    ctx.lineTo(G.px[i] - G.nx[i] * R, G.py[i] - G.ny[i] * R);
  }
  ctx.closePath();
}

function centreline(ctx, G, from = 0, to = -1) {
  const end = to < 0 ? G.n : to;
  ctx.beginPath();
  for (let i = from; i < end; i++) (i > from ? ctx.lineTo(G.px[i], G.py[i]) : ctx.moveTo(G.px[i], G.py[i]));
}

// Data mode: each segment tinted by its own signed curvature, so the travelling wave is
// visible as a wave rather than as a wiggle.
function drawWormDigital(ctx, G) {
  const k = G.kappa;
  for (let i = 0; i < G.n - 1; i++) {
    const kv = k.length ? k[Math.min(k.length - 1, Math.max(0, i - 1))] / 7.0 : 0;
    ctx.beginPath();
    ctx.moveTo(G.px[i] + G.nx[i] * G.r[i], G.py[i] + G.ny[i] * G.r[i]);
    ctx.lineTo(G.px[i + 1] + G.nx[i + 1] * G.r[i + 1], G.py[i + 1] + G.ny[i + 1] * G.r[i + 1]);
    ctx.lineTo(G.px[i + 1] - G.nx[i + 1] * G.r[i + 1], G.py[i + 1] - G.ny[i + 1] * G.r[i + 1]);
    ctx.lineTo(G.px[i] - G.nx[i] * G.r[i], G.py[i] - G.ny[i] * G.r[i]);
    ctx.closePath();
    ctx.fillStyle = div(kv);
    ctx.fill();
  }
  bodyPath(ctx, G);
  ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(G.px[0], G.py[0], Math.max(1.6, G.r[0] * 0.45), 0, Math.PI * 2);
  ctx.fill();
  pumpMark(ctx, G, '#fff');
}

// Diagram mode: flat fill, heavy ink outline, segment ticks and one obvious eye. Nothing
// is shaded, because shading would imply a three-dimensional body this model does not have.
function drawWormCartoon(ctx, G, f) {
  const INK = '#2b2722';
  ctx.lineJoin = ctx.lineCap = 'round';

  // The outline is capped: it is a cartoon convention, not a physical rim, so letting it
  // scale freely with zoom turns the head into a blob and eventually fills the body in.
  const ink = Math.min(5, Math.max(1.6, G.r[Math.floor(G.n / 2)] * 0.42));
  bodyPath(ctx, G);
  ctx.fillStyle = '#f5d982';
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = ink;
  ctx.stroke();

  // Segment ticks: the body is visibly made of repeating units, and they make the wave
  // legible without colouring the animal by a quantity.
  ctx.strokeStyle = 'rgba(43,39,34,0.30)';
  ctx.lineWidth = Math.max(0.8, G.r[0] * 0.16);
  for (let i = 3; i < G.n - 2; i += 3) {
    const R = G.r[i] * 0.82;
    ctx.beginPath();
    ctx.moveTo(G.px[i] + G.nx[i] * R, G.py[i] + G.ny[i] * R);
    ctx.lineTo(G.px[i] - G.nx[i] * R, G.py[i] - G.ny[i] * R);
    ctx.stroke();
  }

  // Eye, set back from the nose onto the wider part of the head and offset to one side so
  // the animal has a facing. Drawn at the tip it sat inside the outline and disappeared.
  const e = Math.min(G.n - 1, 3);
  const eR = Math.max(1.6, G.r[e] * 0.46);
  const ex = G.px[e] + G.nx[e] * G.r[e] * 0.30;
  const ey = G.py[e] + G.ny[e] * G.r[e] * 0.30;
  ctx.fillStyle = '#fff';
  ctx.beginPath(); ctx.arc(ex, ey, eR, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = INK; ctx.lineWidth = Math.max(0.9, Math.min(2, eR * 0.28)); ctx.stroke();
  ctx.fillStyle = INK;
  ctx.beginPath(); ctx.arc(ex, ey, eR * 0.42, 0, Math.PI * 2); ctx.fill();

  pumpMark(ctx, G, '#e8564a');
}

// Plate mode: a translucent amber body with a darker gut running down it and a specular
// edge on one side. Soft edges, because nothing under a stereoscope has a 1px outline.
function drawWormRealistic(ctx, G, f) {
  ctx.save();
  ctx.lineJoin = ctx.lineCap = 'round';

  // Contact shadow: the animal sits on the agar rather than floating over it.
  ctx.save();
  ctx.translate(1.5, 2.0);
  bodyPath(ctx, G, 1.06);
  ctx.fillStyle = 'rgba(30,26,18,0.32)';
  ctx.filter = 'blur(2px)';
  ctx.fill();
  ctx.restore();

  bodyPath(ctx, G);
  ctx.fillStyle = 'rgba(226,203,158,0.90)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(120,100,70,0.55)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // The gut, a darker tube down the middle of the body.
  ctx.save();
  bodyPath(ctx, G);
  ctx.clip();
  centreline(ctx, G);
  ctx.strokeStyle = 'rgba(150,120,74,0.42)';
  ctx.lineWidth = Math.max(1, G.r[Math.floor(G.n / 2)] * 0.62);
  ctx.stroke();

  // Specular line along one flank, shifted with the local normal so it follows the bend.
  ctx.beginPath();
  for (let i = 0; i < G.n; i++) {
    const R = G.r[i] * 0.52;
    const x = G.px[i] + G.nx[i] * R, y = G.py[i] + G.ny[i] * R;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.strokeStyle = 'rgba(255,247,225,0.5)';
  ctx.lineWidth = Math.max(0.8, G.r[0] * 0.30);
  ctx.stroke();
  ctx.restore();

  // Pharynx: a paler bulb in the front fifth, which is where the pump actually is.
  const head = Math.max(2, Math.floor(G.n * 0.16));
  ctx.save();
  bodyPath(ctx, G);
  ctx.clip();
  centreline(ctx, G, 0, head);
  ctx.strokeStyle = 'rgba(246,236,210,0.75)';
  ctx.lineWidth = Math.max(1, G.r[0] * 0.9);
  ctx.stroke();
  ctx.restore();

  ctx.restore();
  pumpMark(ctx, G, 'rgba(255,255,255,0.95)');
}

// One flash per pharyngeal pump, at the animal's mouth. At 250 a minute on food this is a
// shimmer at the nose; off food it is an occasional twitch. It is the only part of the
// pharynx that was ever going to be visible from outside.
function pumpMark(ctx, G, colour) {
  if (S.pumpFlash <= 0) return;
  const a = Math.min(1, S.pumpFlash);
  const R = G.r[0] * (0.5 + 0.9 * a);
  ctx.save();
  ctx.globalAlpha = a * 0.85;
  ctx.strokeStyle = colour;
  ctx.lineWidth = Math.max(1, G.r[0] * 0.28);
  ctx.beginPath();
  ctx.arc(G.px[0], G.py[0], Math.max(1.5, R), 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

/* ------------------------------------------------------------------- overlays ----- */

function drawMinimap(ctx, w, h, R, f) {
  const T = theme();
  const size = 84, pad = 12;
  const cx = w - pad - size / 2, cy = h - pad - size / 2, s = (size / 2) / R;
  ctx.save();
  ctx.fillStyle = T.dark ? 'rgba(250,247,238,0.88)' : 'rgba(13,13,13,0.82)';
  ctx.strokeStyle = T.dark ? 'rgba(43,39,34,0.35)' : C('--border');
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, size / 2, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.arc(cx, cy, size / 2, 0, Math.PI * 2); ctx.clip();
  for (const p of S.meta.world.patches) {
    ctx.fillStyle = p.kind === 'food' ? 'rgba(25,158,112,0.55)' : 'rgba(208,59,59,0.5)';
    ctx.beginPath(); ctx.arc(cx + p.x * s, cy - p.y * s, Math.max(1.5, p.r * s), 0, Math.PI * 2);
    ctx.fill();
  }
  if (S.trail.length > 1) {
    ctx.strokeStyle = T.dark ? 'rgba(43,39,34,0.55)' : 'rgba(195,194,183,0.5)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    S.trail.forEach((p, i) => (i ? ctx.lineTo(cx + p[0] * s, cy - p[1] * s)
                                : ctx.moveTo(cx + p[0] * s, cy - p[1] * s)));
    ctx.stroke();
  }
  // The current camera window, so "where am I looking" is answerable at a glance once
  // the view can be detached from the animal.
  const half = S.view.span / 2 * s;
  ctx.strokeStyle = T.dark ? 'rgba(43,39,34,0.5)' : 'rgba(255,255,255,0.45)';
  ctx.lineWidth = 1;
  ctx.strokeRect(cx + S.view.cx * s - half, cy - S.view.cy * s - half, half * 2, half * 2);
  if (f) {
    ctx.fillStyle = T.dark ? '#c2401f' : '#fff';
    ctx.beginPath(); ctx.arc(cx + f.nodes[0] * s, cy - f.nodes[1] * s, 2.4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawScaleBar(ctx, w, h, scale) {
  const T = theme();
  const mm = S.view.span > 14 ? 5 : S.view.span > 4 ? 1 : 0.2;
  const px = mm * scale, x = 14, y = h - 16;
  const ink = T.dark ? 'rgba(30,26,20,0.85)' : C('--text-muted');
  ctx.strokeStyle = ink; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + px, y); ctx.stroke();
  ctx.fillStyle = ink; ctx.font = '11px system-ui';
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

function drawNeurons() {
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

/* -------------------------------------------------------------------- muscles ----- */

function drawMuscles() {
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

function pushKymo(kappa, t) {
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

function drawTraces() {
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

// A collapsed panel has a zero-height body; drawing into it wastes work and, worse, makes
// fitCanvas resize the backing store to 1px and throw away the layout.
function visible(cv) {
  const r = cv.getBoundingClientRect();
  return r.width > 4 && r.height > 4;
}

/* ----------------------------------------------------------------- interaction ---- */

function neuronAt(cv, ev) {
  if (!layout) return null;
  const r = cv.getBoundingClientRect();
  // The layout is built in the canvas's backing-store pixels, which are devicePixelRatio
  // times the CSS pixels a mouse event reports. Comparing the two directly meant that on
  // any HiDPI display the hit test was out by a factor of two.
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

function setCam(mode) {
  S.cam = mode;
  document.querySelectorAll('[data-cam]').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.cam === mode)));
}
function zoom(factor, ax, ay) {
  const before = S.view.span;
  S.view.span = Math.max(1.2, Math.min(58, S.view.span * factor));
  // Zoom about the cursor when there is one, so the thing under the pointer stays put.
  if (ax !== undefined) {
    const k = 1 - S.view.span / before;
    S.view.cx += (ax - S.view.cx) * k;
    S.view.cy += (ay - S.view.cy) * k;
  }
  el('o-zoom').textContent = `${S.view.span.toFixed(1)} mm`;
}
function worldAt(cv, ev) {
  const r = cv.getBoundingClientRect();
  const scale = Math.min(r.width, r.height) / S.view.span;
  return [S.view.cx + (ev.clientX - r.left - r.width / 2) / scale,
          S.view.cy - (ev.clientY - r.top - r.height / 2) / scale];
}

function wire() {
  const dish = el('c-dish');

  dish.addEventListener('wheel', (e) => {
    e.preventDefault();
    const [wx, wy] = worldAt(dish, e);
    zoom(Math.exp(e.deltaY * 0.0016), wx, wy);
  }, { passive: false });

  // Drag to pan. Dragging is how you detach the camera, so it switches to Free itself
  // rather than making you find a button first -- and a drag must not also be read as a
  // click, or every pan would drop a lawn.
  let drag = null;
  dish.addEventListener('pointerdown', (e) => {
    drag = { x: e.clientX, y: e.clientY, moved: 0 };
    dish.setPointerCapture(e.pointerId);
    dish.classList.add('dragging');
  });
  dish.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const r = dish.getBoundingClientRect();
    const scale = Math.min(r.width, r.height) / S.view.span;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.moved += Math.abs(dx) + Math.abs(dy);
    drag.x = e.clientX; drag.y = e.clientY;
    if (drag.moved > 3) {
      if (S.cam !== 'free') setCam('free');
      S.view.cx -= dx / scale;
      S.view.cy += dy / scale;
    }
  });
  const endDrag = (e) => {
    if (drag) dish.releasePointerCapture?.(e.pointerId);
    drag = null;
    dish.classList.remove('dragging');
  };
  dish.addEventListener('pointerup', endDrag);
  dish.addEventListener('pointercancel', endDrag);

  dish.addEventListener('dblclick', (e) => {
    if (!S.meta) return;
    const [x, y] = worldAt(dish, e);
    if (Math.hypot(x, y) > S.meta.world.radius - 1) return;
    send({ cmd: 'drop_food', x, y, r: 2.5 });
    S.meta.world.patches.push({ x, y, r: 2.5, kind: 'food' });
  });

  document.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('[data-view]').forEach((o) =>
      o.setAttribute('aria-pressed', String(o === b)));
    S.theme = b.dataset.view;
    // The floating controls invert on the light plates; see #dish[data-plate] in the CSS.
    el('dish').dataset.plate = theme().dark ? 'light' : 'dark';
    buildLegend();
  }));

  document.querySelectorAll('[data-layer]').forEach((b) => b.addEventListener('click', () => {
    const k = b.dataset.layer;
    S.layers[k] = !S.layers[k];
    b.setAttribute('aria-pressed', String(S.layers[k]));
  }));

  document.querySelectorAll('[data-cam]').forEach((b) => b.addEventListener('click', () => {
    setCam(b.dataset.cam);
    if (S.cam === 'follow') S.recentre = true;
  }));
  el('b-centre').addEventListener('click', () => { S.recentre = true; });
  el('b-zin').addEventListener('click', () => zoom(1 / 1.35));
  el('b-zout').addEventListener('click', () => zoom(1.35));

  // Collapsing a panel is a click on its whole header, not on a small chevron.
  document.querySelectorAll('.panel .phead').forEach((head) => {
    head.addEventListener('click', () => {
      head.parentElement.classList.toggle('collapsed');
      layout = null;                          // side panels resize; rebuild the neuron grid
    });
  });

  el('b-rail').addEventListener('click', (e) => {
    const on = el('app').classList.toggle('norail');
    e.target.setAttribute('aria-pressed', String(!on));
    e.target.textContent = on ? 'Hidden' : 'Shown';
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
      if (S.ablated.has(i)) return;              // ablation is not undone one cell at a time
      S.ablated.add(i);
      send({ cmd: 'ablate', neurons: [S.meta.neurons[i].name] });
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
  el('b-ablate').addEventListener('click', () => { S.ablateMode = !S.ablateMode; updateAblateUI(); });
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

  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'f') { setCam(S.cam === 'follow' ? 'free' : 'follow'); if (S.cam === 'follow') S.recentre = true; }
    if (e.key === 'h') el('b-rail').click();
    if (e.key === '1' || e.key === '2' || e.key === '3') {
      document.querySelectorAll('[data-view]')[Number(e.key) - 1]?.click();
    }
  });

  el('dish').dataset.plate = theme().dark ? 'light' : 'dark';
  buildLegend();
  zoom(1);
}

// The legend explains whatever the dish is currently saying, which is different in each
// mode: digital colours the body by curvature, the other two do not.
function buildLegend() {
  const rows = S.theme === 'digital'
    ? [['var(--dorsal)', 'dorsal bend'], ['var(--ventral)', 'ventral bend'],
       ['var(--series-3)', 'food'], ['var(--critical)', 'repellent']]
    : [['var(--series-3)', 'food'], ['var(--series-1)', 'attractant'],
       ['var(--critical)', 'repellent']];
  el('legend').innerHTML = rows
    .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join('');
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
}

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

function drawSenses(sensed) {
  const host = el('senses');
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

  // The pump lamp fires on the *rising edge* of a pump rather than while one is open.
  // A pump lasts 150 ms and the frame rate is 30 Hz, so lighting the lamp for the whole
  // open interval would have it on more often than off and read as a steady glow.
  if (pumping > 0.5 && S.lastPumping <= 0.5) S.pumpFlash = 1;
  S.lastPumping = pumping;
  el('s-pump').innerHTML = `${(pumpRate * 60).toFixed(0)}<small>/min</small>`;
  el('pump-dot').classList.toggle('on', S.pumpFlash > 0.35);

  const cx = nodes.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0) / nNodes;
  const cy = nodes.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0) / nNodes;

  // Follow the centroid, not the head, and only once the animal has drifted out of the
  // middle of the frame. Locking the camera rigidly to the head was actively misleading:
  // the head swings from side to side once per undulation, so the camera swung with it
  // and cancelled out the very motion it was supposed to show.
  if (S.recentre) { S.view.cx = cx; S.view.cy = cy; S.recentre = false; }
  if (S.cam === 'follow') {
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

let lastTick = 0;
function tick(now) {
  // The flash decays in wall-clock time so it looks the same however fast the simulation
  // is being run, and however many frames arrive.
  const dt = lastTick ? Math.min(0.1, (now - lastTick) / 1000) : 0;
  lastTick = now;
  if (S.pumpFlash > 0) S.pumpFlash = Math.max(0, S.pumpFlash - dt * 6.5);

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
