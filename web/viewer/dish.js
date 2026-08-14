/* The dish: plate, grid, chemical fields, obstacles, trails, the animals, and the two
 * overlays that make the picture readable (minimap and scale bar). Also the camera
 * transforms, because they are the same world-to-screen mapping the renderer uses and
 * splitting them apart would mean maintaining it twice.
 */

import { S, C, el, fitCanvas } from './state.js';
import { theme, getNoise } from './themes.js';
import { geometry, PAINTERS, identityHalo } from './worm.js';

let fieldCanvas = null;

export function drawDish() {
  const { ctx, w, h } = fitCanvas(el('c-dish'));
  const T = theme();
  const paint = PAINTERS[S.theme];
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

  // Eggs, under the trails and under the animals: they were put there first, and an egg
  // drawn over the worm that laid it reads as something the worm is carrying.
  if (S.layers.eggs && S.eggs && S.eggs.n) drawEggs(ctx, X, Y, scale);

  // Corpse markers, arena only: a fading amber bloom where a body became food. The food
  // itself is real and stays in the food field until eaten -- only the marker fades.
  if (S.layers.corpses && S.corpses && S.corpses.length) {
    const now = S.frame ? S.frame.t : 0;
    for (const c of S.corpses) {
      const age = now - c.t;
      if (age < 0 || age > 90) continue;
      const a = 0.5 * (1 - age / 90);
      const R = 2.0 * scale;
      const g = ctx.createRadialGradient(X(c.x), Y(c.y), 0, X(c.x), Y(c.y), R);
      g.addColorStop(0, `rgba(217,164,65,${a})`);
      g.addColorStop(1, 'rgba(217,164,65,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(X(c.x), Y(c.y), R, 0, Math.PI * 2); ctx.fill();
    }
  }

  if (S.layers.trail) {
    for (const tr of S.trails) {
      if (!tr || tr.length < 2) continue;
      ctx.strokeStyle = T.trail;
      ctx.lineWidth = S.theme === 'cartoon' ? 1.6 : 1.2;
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      tr.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))));
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }
  if (S.layers.trail && S.trail.length > 1) {
    ctx.strokeStyle = T.trail;
    ctx.lineWidth = S.theme === 'cartoon' ? 2 : 1.5;
    ctx.lineJoin = ctx.lineCap = 'round';
    ctx.beginPath();
    S.trail.forEach((p, i) => (i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))));
    ctx.stroke();
  }

  // Every animal in the dish. They share the plate and the anatomy; only the state
  // differs, which is why a second one costs almost nothing. The focused animal is drawn
  // last so it is never hidden under another, and carries a ring: with more than one
  // worm on the plate the panels have to say *which* worm they are about.
  // A worm with `style` (the arena's) gets its dynasty halo under the body and its
  // energy as body alpha -- the fade you see is the fade the muscles feel. Reference
  // animals carry no style and paint exactly as before.
  const paintOne = (o, G) => {
    if (o.style) {
      identityHalo(ctx, G, o.style);
      ctx.save();
      if (S.layers.energy !== false) ctx.globalAlpha = 0.40 + 0.60 * (o.style.dim ?? 1);
      paint(ctx, G, o, scale);
      ctx.restore();
    } else {
      paint(ctx, G, o, scale);
    }
  };
  for (let i = 0; i < S.worms.length; i++) {
    if (i === S.focus) continue;
    const o = S.worms[i];
    if (o) paintOne(o, geometry(o, X, Y, scale));
  }
  const fw = S.worms[S.focus];
  if (fw) {
    const Gf = geometry(fw, X, Y, scale);
    if (S.worms.length > 1) {
      let cx = 0, cy = 0;
      for (let i = 0; i < Gf.n; i++) { cx += Gf.px[i]; cy += Gf.py[i]; }
      cx /= Gf.n; cy /= Gf.n;
      ctx.strokeStyle = theme().dark ? 'rgba(43,39,34,0.45)' : 'rgba(255,255,255,0.42)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.arc(cx, cy, 0.62 * scale, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
    }
    paintOne(fw, Gf);
  }
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
let fieldKey = '';
function drawFields(ctx, X, Y, scale) {
  const n = S.field.n, T = theme();
  const on = Object.keys(CHAN).filter((k) => S.layers[k]);
  if (!on.length) return;
  if (!fieldCanvas) fieldCanvas = document.createElement('canvas');
  if (fieldCanvas.width !== n) { fieldCanvas.width = fieldCanvas.height = n; }
  // Rebuilding a 128x128 image per channel every frame is 50k operations for a picture
  // that changes about once a second. Rebuild only when the field, the visible layers or
  // the palette actually change.
  const key = `${S.field.stamp || 0}|${on.join(',')}|${S.theme}`;
  if (key === fieldKey) {
    const R0 = S.meta.world.radius;
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(fieldCanvas, X(-R0), Y(R0), 2 * R0 * scale, 2 * R0 * scale);
    return;
  }
  fieldKey = key;
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

// An egg is about 50 x 30 um, so at any sensible zoom it is a couple of pixels. Drawn at
// a floor of 1.4 px it stays visible when the whole dish is in frame -- which is the view
// where a scatter of eggs actually says something, because it is the record of where the
// animal has been laying rather than a picture of one egg.
function drawEggs(ctx, X, Y, scale) {
  const T = theme(), e = S.eggs;
  const r = Math.max(1.4, 0.025 * scale);
  ctx.fillStyle = T.egg[0];
  ctx.strokeStyle = T.egg[1];
  ctx.lineWidth = r > 3 ? 1 : 0.6;
  for (let i = 0; i < e.n; i++) {
    const cx = X(e.x[i]), cy = Y(e.y[i]);
    ctx.beginPath();
    // An ellipse, because an egg is one, and the long axis reads at high zoom.
    ctx.ellipse(cx, cy, r * 1.45, r, 0, 0, Math.PI * 2);
    ctx.fill();
    if (r > 2) ctx.stroke();
  }
}

let grainPat = null, grainCtx = null;
function drawGrain(ctx, w, h) {
  // createPattern is not free, and the tile never changes.
  if (!grainPat || grainCtx !== ctx) { grainPat = ctx.createPattern(getNoise(), 'repeat'); grainCtx = ctx; }
  const pat = grainPat;
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
  if (S.layers.eggs && S.eggs && S.eggs.n) {
    ctx.fillStyle = T.dark ? 'rgba(120,105,70,0.75)' : 'rgba(240,235,215,0.75)';
    for (let i = 0; i < S.eggs.n; i++) {
      ctx.beginPath();
      ctx.arc(cx + S.eggs.x[i] * s, cy - S.eggs.y[i] * s, 1.0, 0, Math.PI * 2);
      ctx.fill();
    }
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
  for (let i = 0; i < S.worms.length; i++) {
    const o = S.worms[i];
    if (!o) continue;
    ctx.fillStyle = i === S.focus ? (T.dark ? '#c2401f' : '#fff')
                                  : (T.dark ? 'rgba(43,39,34,0.45)' : 'rgba(255,255,255,0.45)');
    ctx.beginPath();
    ctx.arc(cx + o.nodes[0] * s, cy - o.nodes[1] * s, i === S.focus ? 2.6 : 1.8, 0, Math.PI * 2);
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

/* --------------------------------------------------------------------- camera ----- */

export function setCam(mode) {
  S.cam = mode;
  document.querySelectorAll('[data-cam]').forEach((b) =>
    b.setAttribute('aria-pressed', String(b.dataset.cam === mode)));
}

export function zoom(factor, ax, ay) {
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

export function worldAt(cv, ev) {
  const r = cv.getBoundingClientRect();
  const scale = Math.min(r.width, r.height) / S.view.span;
  return [S.view.cx + (ev.clientX - r.left - r.width / 2) / scale,
          S.view.cy - (ev.clientY - r.top - r.height / 2) / scale];
}

// Track the focused animal's centroid. Shared by both transports, which is the whole
// reason it lives here: the WebSocket path and the local path had two copies of this
// dead-zone follow and they had already started to drift apart.
export function follow(cx, cy) {
  if (S.recentre) { S.view.cx = cx; S.view.cy = cy; S.recentre = false; }
  if (S.cam !== 'follow') return;
  // Follow the centroid, not the head, and only once the animal has drifted out of the
  // middle of the frame. Locking the camera rigidly to the head was actively misleading:
  // the head swings from side to side once per undulation, so the camera swung with it
  // and cancelled out the very motion it was supposed to show.
  const dead = S.view.span * 0.18;
  const dx = cx - S.view.cx, dy = cy - S.view.cy;
  const d = Math.hypot(dx, dy);
  if (d > dead) {
    const pull = (d - dead) / d;
    S.view.cx += dx * pull;
    S.view.cy += dy * pull;
  }
}
