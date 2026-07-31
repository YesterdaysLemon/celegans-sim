/* Shared viewer state, and the two DOM helpers everything else is built on.
 *
 * This module imports nothing. Every other viewer module may import it, which is what
 * keeps the dependency graph a tree rather than a knot: state flows down, never sideways.
 * If you find yourself wanting to import a renderer from here, the thing you want is
 * probably a field on S.
 */

const css = getComputedStyle(document.documentElement);
export const C = (name) => css.getPropertyValue(name).trim();
export const SERIES = [C('--series-1'), C('--series-2'), C('--series-3'),
                       C('--series-4'), C('--series-5'), C('--series-6')];

export const S = {
  meta: null, frame: null, field: null,
  theme: 'digital',
  layers: { food: true, attractant: true, repellent: true, eggs: true, grid: true, trail: true },
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
  engine: null,        // the local WASM engine, when running client-side
  eggs: null,          // every egg on the plate; shared, because the dish is
  worms: [],           // every animal's frame, for the dish
  trails: [],          // one track per animal
  focus: 0,            // which animal the camera and the panels are about
};

export const el = (id) => document.getElementById(id);

export function fitCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: r.width, h: r.height };
}

// A collapsed panel has a zero-height body; drawing into it wastes work and, worse, makes
// fitCanvas resize the backing store to 1px and throw away the layout.
export function visible(cv) {
  const r = cv.getBoundingClientRect();
  return r.width > 4 && r.height > 4;
}
