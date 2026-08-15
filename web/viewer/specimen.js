/* Preserving a worm: the focused animal, captured as a SPECIMEN -- a few seconds of its
 * walk cycle, its genes, its morphology and its colours, serialised to JSON. No live
 * simulation rides along: a specimen is a recording, which is what lets the museum
 * shelve it as a looping close-up with no engine behind the glass.
 *
 * Two destinations, both local: a downloaded .json file (the durable copy, and the
 * future sharing format -- a deployed site's specimens/ directory serves exactly these
 * files), and localStorage (the browser's own shelf, so the museum page shows the catch
 * immediately). Sharing infrastructure is explicitly out of scope; the file format is
 * the contract that makes it possible later.
 *
 * Frames store nodes RELATIVE TO THE CENTROID, so the museum replays a body wriggling
 * in place -- a walk cycle, not a journey. Rounded to 4 decimals (0.1 um) because a
 * specimen jar does not need conformance-grade precision at twenty times the bytes. */

import { S, el } from './state.js';

const CAPTURE_FRAMES = 90;      // at one sample per 0.05 s of dish time: a 4.5 s cycle
const SAMPLE_DT = 0.05;
const SHELF_KEY = 'celegans-specimens';
const SHELF_CAP = 20;           // localStorage is ~5 MB; a specimen is ~60 kB

let active = null;              // { frames, lastT } while a capture is running

function preserving() { return active !== null; } // kept private until a caller exists
void preserving;

export function startPreserve() {
  if (active || !S.engine || !S.worms.length) return false;
  active = { frames: [], lastT: -1 };
  const b = el('b-preserve');
  if (b) { b.disabled = true; b.textContent = 'Preserving…'; }
  return true;
}

/* Called from the animation loop each frame; samples on dish time, finishes itself. */
export function samplePreserve() {
  if (!active) return;
  const f = S.worms[S.focus];
  if (!f) { finish(null); return; }                    // the subject died mid-capture
  if (f.t < active.lastT) { active.frames = []; }      // dish was reset under us
  if (active.lastT >= 0 && f.t - active.lastT < SAMPLE_DT) return;
  active.lastT = f.t;

  const nn = f.nodes.length / 2;
  let cx = 0, cy = 0;
  for (let k = 0; k < nn; k++) { cx += f.nodes[k * 2]; cy += f.nodes[k * 2 + 1]; }
  cx /= nn; cy /= nn;
  const pts = new Array(nn * 2);
  for (let k = 0; k < nn; k++) {
    pts[k * 2] = Math.round((f.nodes[k * 2] - cx) * 1e4) / 1e4;
    pts[k * 2 + 1] = Math.round((f.nodes[k * 2 + 1] - cy) * 1e4) / 1e4;
  }
  active.frames.push(pts);
  if (active.frames.length >= CAPTURE_FRAMES) finish(f);
}

function finish(f) {
  const done = active;
  active = null;
  const b = el('b-preserve');
  if (b) { b.disabled = false; b.textContent = 'Preserve'; }
  if (!f || done.frames.length < 10) return;           // nothing worth jarring

  const eng = S.engine, E = eng.E;
  const id = f.id !== undefined ? f.id : (eng.worms ? eng.worms[S.focus] : null);
  const spec = {
    kind: 'celegans-sim specimen',
    version: 1,
    name: `${S.meta && S.meta.arena ? 'arena' : 'animal'}-t${Math.round(f.t)}s-`
      + Math.random().toString(36).slice(2, 6),
    captured: new Date().toISOString(),
    dish: S.meta && S.meta.arena ? 'arena' : 'animal',
    dishTime: Math.round(f.t * 10) / 10,
    sampleDt: SAMPLE_DT,
    style: f.style || null,
    widthScale: f.widthScale ? Array.from(f.widthScale, (v) => Math.round(v * 1e3) / 1e3)
                             : null,
    genes: id !== null && E && E.getGene && eng.head && eng.head.genes
      ? eng.head.genes.map((g, i) => [g, Math.round(E.getGene(id, i) * 1e6) / 1e6])
      : null,
    morphology: id !== null && E && E.hasOwnMorphology && E.hasOwnMorphology(id)
      ? { controls: Array.from({ length: 12 }, (_, j) => E.getMorph(id, j)),
          development: E.getDevelopment(id) }
      : null,
    frames: done.frames,
  };

  // The browser shelf, newest last, oldest evicted.
  try {
    const shelf = JSON.parse(localStorage.getItem(SHELF_KEY) || '[]');
    shelf.push(spec);
    while (shelf.length > SHELF_CAP) shelf.shift();
    localStorage.setItem(SHELF_KEY, JSON.stringify(shelf));
  } catch (e) {
    console.warn('specimen shelf (localStorage) refused the jar:', e);
  }

  // The durable copy: a file the user actually holds.
  const blob = new Blob([JSON.stringify(spec)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `specimen-${spec.name}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
