/* The body, painted two ways -- digital for dark mode, realistic for light.
 *
 * Both painters work from one shared `geometry()` result -- screen-space centreline,
 * outward normals and radii -- so the two modes are guaranteed to be drawing the same
 * animal rather than two approximations of it. (A third painter, cartoon, was retired
 * with the mode work; see themes.js for the note.)
 *
 * PAINTERS is keyed by the same names as THEMES in themes.js. dish.js looks the painter up
 * by S.theme; neither module has to know about the other.
 */

import { S } from './state.js';
import { div } from './scales.js';

// Shared geometry: screen-space centreline, outward normals and radii. Every painter
// works from this, so the three modes are guaranteed to draw the same animal.
//
// `f.widthScale`, when present, is a per-node multiplier on the anatomy's radius
// profile -- the arena's heritable width made visible. Absent (every reference animal),
// the radii are exactly what they always were.
export function geometry(f, X, Y, scale) {
  const nodes = f.nodes, rad = S.meta.radius, ws = f.widthScale;
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
    if (ws) r[i] *= i < ws.length ? ws[i] : 1;
  }
  return { n, px, py, nx, ny, r, kappa: f.kappa };
}

/* Dynasty identity, drawn UNDER the body: a soft halo along the centreline in the
 * lineage's hue, dimmed with the animal's energy store. Under rather than over, so all
 * three painters keep their own look and the halo reads as light on the plate around
 * the animal -- at arena zoom it is what makes ten small bodies tell apart at a
 * glance. */
export function identityHalo(ctx, G, style) {
  ctx.save();
  ctx.globalAlpha = 0.28 + 0.30 * (style.dim ?? 1);
  ctx.strokeStyle = `hsl(${style.hue} 75% 60%)`;
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(3, G.r[Math.floor(G.n / 2)] * 2.6);
  ctx.beginPath();
  for (let i = 0; i < G.n; i++) {
    (i ? ctx.lineTo(G.px[i], G.py[i]) : ctx.moveTo(G.px[i], G.py[i]));
  }
  ctx.stroke();
  ctx.restore();
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

// Plate mode: a translucent amber body with a darker gut running down it and a specular
// edge on one side. Soft edges, because nothing under a stereoscope has a 1px outline.
function drawWormRealistic(ctx, G, f) {
  ctx.save();
  ctx.lineJoin = ctx.lineCap = 'round';

  // Contact shadow: the animal sits on the agar rather than floating over it. Two
  // offset fills rather than a blur -- canvas filters are re-created per call and cost
  // several milliseconds a frame, which is a lot to spend on a shadow.
  ctx.save();
  ctx.translate(1.5, 2.0);
  bodyPath(ctx, G, 1.10);
  ctx.fillStyle = 'rgba(30,26,18,0.16)';
  ctx.fill();
  bodyPath(ctx, G, 1.04);
  ctx.fillStyle = 'rgba(30,26,18,0.20)';
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

export const PAINTERS = {
  digital: drawWormDigital,
  realistic: drawWormRealistic,
};
