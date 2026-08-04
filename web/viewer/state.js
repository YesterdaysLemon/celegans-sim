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
  ablateMode: false,
  ablations: new Map(),                 // one record per animal; see ablated() below
  freq: 0, freqBuf: [],
  pumpFlash: 0, lastPumping: 0,
  connected: false,
  engine: null,        // the local WASM engine, when running client-side
  eggs: null,          // every egg on the plate; shared, because the dish is
  worms: [],           // every animal's frame, for the dish
  trails: [],          // one track per animal
  focus: 0,            // which animal the camera and the panels are about
  /* Where the scrubber is, as an index into viewer/history.js, or null for live.
   *
   * null rather than "the last index" on purpose: those are different states. Live means
   * the renderer takes whatever the engine last produced and the ring keeps growing under
   * it; parked on the newest frame means the display is pinned to one moment that happens
   * to be the newest, and eviction will slide out from under it. A single index cannot
   * express the first, and code that tried would resume playback every time the ring
   * turned over. */
  playhead: null,
};

export const el = (id) => document.getElementById(id);

/* The cells ablated in the animal the panels are about.
 *
 * Ablation applies to one worm -- kill AVB in this one and watch it next to an intact one
 * in the same dish -- so there is no such thing as "the ablated cells" of a plate. The
 * viewer kept one set anyway, and it was wrong in the way a shared record always is:
 * Restore emptied it while restoring whichever animal happened to be focused, so an
 * ablated worm you had focused away from stayed ablated with nothing left that knew it.
 *
 * The record is keyed by the runtime's worm id, which is handed out monotonically and
 * never reused -- so a key names one animal for as long as it exists and nothing at all
 * afterwards. S.focus is a *position* in S.engine.worms and is not an identity: removing
 * an animal renumbers everyone after it, and a record kept by position would follow the
 * slot rather than the worm. The socket feed drives a single animal and issues no ids, so
 * it gets one fixed key of its own.
 *
 * Callers ask every time rather than copying the set when focus changes, which is what
 * keeps what is drawn and what is simulated in step: there is no second notion of "which
 * cells are ablated" for something to forget to update.
 */
export function ablated() {
  const worms = S.engine ? S.engine.worms : null;
  const key = worms ? worms[S.focus] : 'socket';
  // A focus naming no animal is a moment mid-change -- between a removal and the clamp
  // that follows it. A throwaway set keeps the renderer drawing rather than filing an
  // ablation under the key `undefined`, where the next lookup would not find it.
  if (key === undefined) return new Set();
  let cells = S.ablations.get(key);
  if (!cells) S.ablations.set(key, cells = new Set());
  return cells;
}

/* Forget the animals that have left the plate.
 *
 * Ids are never reused, so a stale record cannot be inherited by a future worm -- this is
 * housekeeping, not correctness. Without it a session spent adding and removing animals
 * accumulates records for worms that no longer exist. No engine means the socket feed,
 * whose single record is not addressed by a handle and must survive.
 */
export function pruneAblations() {
  if (!S.engine) return;
  const live = new Set(S.engine.worms);
  for (const key of S.ablations.keys()) if (!live.has(key)) S.ablations.delete(key);
}

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
