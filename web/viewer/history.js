/* A bounded ring of past frames, so the transport bar can have a scrubber.
 *
 * The README opens by saying the worm is the project and the web app is a media player for
 * it. The transport bar had no scrubber, because there was no history to scrub -- every
 * frame was drawn once and dropped. This is the history.
 *
 * THE RING COPIES, AND THAT IS THE WHOLE CORRECTNESS ARGUMENT.
 *
 * `LocalEngine.frame(i)` hands out `Float64Array` *views into WASM linear memory* -- `act`,
 * `V`, `tension` and `kappa` are all windows onto the live animal, not snapshots of it.
 * (`nodes` is the exception; it is already copied into a Float32Array on the way out.) A
 * ring that stored those objects would hold several thousand aliases of the same four
 * buffers, and scrubbing would show the current frame at every position -- a bug that looks
 * exactly like the scrubber working, because the animal on screen does move when you drag.
 *
 * There is a second reason, and it is worse than wrong pixels: `memory.grow` detaches every
 * existing view. Adding an animal can grow the heap, at which point a stored view is not
 * stale, it throws. So every array is copied on the way in, into Float32Array -- half the
 * width of the engine's f64 and more than the canvas can show, since it all ends up in a
 * `lineTo` eventually.
 *
 * THE BUDGET IS IN BYTES, NOT IN FRAMES.
 *
 * A frame costs **3,376 bytes per animal**, measured off `stats()` on a two-animal plate
 * rather than estimated: 49 nodes, 302 activations, 302 potentials, 95 muscle tensions and
 * 47 curvatures, all as f32. So "a few thousand frames" is a different amount of memory for
 * one animal than for sixteen, and a fixed frame count would quietly mean a 27 MB ring on a
 * populated plate. NEXT.md sized the population the same way -- an animal is 234 kB,
 * `memory.grow` is one-way, size for the peak -- and this follows it: the ceiling is
 * `BUDGET_BYTES`, the frame count falls out of how many animals are in the dish, and
 * `stats()` reports what that worked out to so the number is visible rather than folklore.
 *
 * This paragraph is the reason the figure is measured at all. NEXT.md records that an
 * animal's own footprint was documented in three places and measured in none, and the
 * documented figure was out by a factor of a hundred (#33).
 *
 * Entries are evicted from the front until the total fits. Nothing is preallocated, because
 * the per-frame size changes whenever an animal is added or removed, and a fixed-stride
 * slab would have to be thrown away entirely each time that happened.
 */

/* 24 MB. Chosen against what it buys rather than as a round number: at 3,376 bytes per
 * animal per frame that is about 7,100 frames with one animal on the plate -- two minutes
 * of wall clock at 60 fps -- and about 930 with eight, which is fifteen seconds. Both are
 * worth having and neither is a page that gets killed on a phone. The viewer already holds
 * a ~2.6 MB World and 234 kB per animal, so this is the largest single thing in the tab,
 * which is the argument for it being a number written down here with a reason rather than
 * an array that grows until something else stops it. */
export const BUDGET_BYTES = 24 * 1024 * 1024;

const ring = [];
let bytes = 0;

const copy = (a) => {
  const out = new Float32Array(a.length);
  out.set(a);
  return out;
};

function sizeOf(entry) {
  let n = 0;
  for (const w of entry.worms) {
    n += w.nodes.byteLength + w.act.byteLength + w.V.byteLength
       + w.tension.byteLength + w.kappa.byteLength;
  }
  if (entry.eggs) n += entry.eggs.x.byteLength + entry.eggs.y.byteLength;
  return n;
}

/* Snapshot one displayed moment.
 *
 * Called with whatever the renderer is about to draw, from either feed -- the local engine
 * in loop.js or the WebSocket in transport.js. Both end up describing the same thing, an
 * array of per-animal frames plus the eggs on the plate, so both record through here and
 * neither needs to know the other exists.
 *
 * Scalars are kept per animal rather than only for the focused one, so that scrubbing back
 * and *then* changing focus shows that animal's past rather than a blank panel.
 */
export function record(worms, eggs) {
  if (!worms || !worms.length) return;
  const entry = {
    t: worms[0].t,
    worms: worms.map((w) => ({
      nodes: copy(w.nodes), act: copy(w.act), V: copy(w.V),
      tension: copy(w.tension), kappa: copy(w.kappa),
      cx: w.cx, cy: w.cy, t: w.t, food: w.food, dir: w.dir, running: w.running,
      pumpRate: w.pumpRate, pumping: w.pumping, lumen: w.lumen,
      vulva: w.vulva, eggsHeld: w.eggsHeld, eggsLaid: w.eggsLaid, eglActive: w.eglActive,
      // `sensed` is a plain object of numbers built fresh each frame, so a shallow copy is
      // a real copy. Spread rather than reference anyway: the local feed reuses one object
      // per animal on some paths and a reference would track it forward.
      sensed: { ...w.sensed },
    })),
    eggs: eggs && eggs.n ? { n: eggs.n, x: copy(eggs.x), y: copy(eggs.y) } : null,
  };
  entry.bytes = sizeOf(entry);
  ring.push(entry);
  bytes += entry.bytes;
  while (ring.length > 1 && bytes > BUDGET_BYTES) bytes -= ring.shift().bytes;
}

export const count = () => ring.length;
export const at = (i) => (i >= 0 && i < ring.length ? ring[i] : null);

export function reset() { ring.length = 0; bytes = 0; }

/* What the ring actually cost, for the readout. Reported rather than assumed, because the
 * whole point of a byte budget is that the frame count is a consequence you can look at. */
export function stats() {
  const span = ring.length > 1 ? ring[ring.length - 1].t - ring[0].t : 0;
  return {
    frames: ring.length,
    bytes,
    perFrame: ring.length ? Math.round(bytes / ring.length) : 0,
    seconds: span,
  };
}
