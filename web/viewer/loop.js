/* The animation loop, and the local engine's per-frame read-out.
 *
 * When the animal runs in this tab there is no socket and no server: the loop steps the
 * WASM directly and reads its state out of linear memory. Everything downstream -- the
 * panels, the kymograph, the traces -- is unchanged, because it only ever wanted numbers.
 */

import { S, el } from './state.js';
import { drawDish, follow } from './dish.js';
import { drawNeurons, drawMuscles, drawKymo, drawTraces, drawSenses, drawLineage, pushKymo,
         invalidateLayout } from './panels.js';
import { updateFreq, updateStats, updatePump, updateEggs, updateDishStats } from './stats.js';
import { buildWormSel, clampFocus, syncScrub } from './controls.js';
import { record, at as historyAt } from './history.js';
import { samplePreserve } from './specimen.js';

let fieldClock = 0;

const SPEED_CAP = 512;    // hard bound on the speed window; see below

function localTick(now) {
  const eng = S.engine;
  if (!eng || !eng.ready) return;
  eng.advance(now);

  if (!S.meta) {
    S.meta = eng.meta;
    invalidateLayout();
    const want = ['DB01', 'VB01', 'AVBL'];
    S.selected = want.map((n) => S.meta.neurons.findIndex((x) => x.name === n))
                     .filter((i) => i >= 0);
    S.traces = S.selected.map(() => []);
    el('trace-hint').textContent = S.selected.map((k) => S.meta.neurons[k].name).join(', ');
    S.trails = eng.worms.map(() => []);
    S.recentre = true;
    buildWormSel();
    el('banner').classList.add('gone');
  }

  // Every animal, every frame: the dish needs them all. The panels, the camera and the
  // stats are about one of them -- S.focus -- because "the membrane potential" is not a
  // property of a dish, it is a property of an animal.
  // Focus may have gone out of range since the last frame: anything holding the engine can
  // remove an animal, and a generational loop does it wholesale. `clampFocus` moves focus
  // *and* rebuilds everything that names an animal, which is what this line used to skip.
  // It returns false for an empty dish, where there is no animal to read out at all.
  if (!clampFocus()) { S.worms = []; return; }
  S.worms = [];
  for (let i = 0; i < eng.worms.length; i++) S.worms.push(eng.frame(i));
  const f0 = S.worms[S.focus];
  S.frame = {
    t: f0.t, speed: 0, food: f0.food, dir: f0.dir, achieved: eng.achieved,
    sensed: f0.sensed, nodes: f0.nodes, act: f0.act, V: f0.V,
    tension: f0.tension, kappa: f0.kappa, running: f0.running,
  };

  /* Trails follow the ANIMAL, not the slot. The reference dish's population only
   * changes from the +/- buttons, so a positional S.trails[i] was safe; the arena
   * hatches and buries animals between any two frames, and a positional trail would
   * jump from a dead worm onto whoever inherited its index. Frames that carry an `id`
   * (the arena's do) get their trail from a persistent per-id map; frames that do not
   * keep the old positional behaviour, byte for byte. */
  const byId = S.worms.length && S.worms[0].id !== undefined;
  if (byId && !S._trailById) S._trailById = new Map();
  for (let i = 0; i < S.worms.length; i++) {
    const fi = S.worms[i];
    let cx = 0, cy = 0;
    const nn = fi.nodes.length / 2;
    for (let k = 0; k < nn; k++) { cx += fi.nodes[k * 2]; cy += fi.nodes[k * 2 + 1]; }
    cx /= nn; cy /= nn;
    fi.cx = cx; fi.cy = cy;
    let tr;
    if (byId) {
      tr = S._trailById.get(fi.id);
      if (!tr) S._trailById.set(fi.id, tr = []);
      S.trails[i] = tr;
    } else {
      tr = S.trails[i] || (S.trails[i] = []);
    }
    const last = tr[tr.length - 1];
    if (!last || Math.hypot(cx - last[0], cy - last[1]) > 0.02) {
      tr.push([cx, cy]);
      if (tr.length > 2200) tr.shift();
    }
    if (i === S.focus) follow(cx, cy);
  }
  if (byId) {
    S.trails.length = S.worms.length;
    // Buried animals take their trails with them, eventually: prune on population
    // change rather than every frame.
    if (S._trailById.size > S.worms.length) {
      const live = new Set(S.worms.map((w) => w.id));
      for (const k of S._trailById.keys()) if (!live.has(k)) S._trailById.delete(k);
    }
  }

  // Speed of the focused animal, over a window of *simulated* time. Dividing by anything
  // else makes the number a statement about the frame rate: an undulating worm slews its
  // centroid from side to side once a cycle, so a short window reports the slosh.
  if (S.speedWin === undefined || S.speedFocus !== S.focus) { S.speedWin = []; S.speedFocus = S.focus; }
  const c0 = S.trails[S.focus][S.trails[S.focus].length - 1];
  if (c0) {
    const w = S.speedWin;
    let lastT = w.length ? w[w.length - 1][0] : null;
    // The same fixed-timestamp trap the frequency buffer had, for the same reason: this
    // function runs on requestAnimationFrame whether or not the engine stepped, and the
    // window is trimmed in *simulated* seconds, so nothing in it ages out while the
    // animal is paused. It grew by 60 entries a second for as long as you left it.
    // Backwards is a reset, and its samples are another animal's. See updateFreq.
    if (lastT !== null && f0.t < lastT) { w.length = 0; lastT = null; }
    if (lastT === null || f0.t > lastT) {
      w.push([f0.t, c0[0], c0[1]]);
      while (w.length > 1 && f0.t - w[0][0] > 2.0) w.shift();
      // Two simulated seconds at the slowest rate the slider offers is forty wall-clock
      // seconds of frames, so the timestamp trim alone is not a bound. This is.
      if (w.length > SPEED_CAP) w.splice(0, w.length - SPEED_CAP);
    }
    const a = w[0], b = w[w.length - 1];
    const span = b[0] - a[0];
    S.frame.speed = span > 0.2 ? Math.hypot(b[1] - a[1], b[2] - a[2]) / span : 0;
  }

  const sensed = Object.assign({}, f0.sensed, {
    pumpNorm: f0.pumpRate / 6.0, lumenNorm: f0.lumen / 0.05,
    vulva: f0.vulva, eggsNorm: f0.eggsHeld / 15.0,
  });
  drawSenses(sensed);
  updatePump(f0.pumpRate, f0.pumping);
  updateEggs(f0.eggsLaid, f0.eggsHeld, f0.eglActive);

  pushKymo(f0.kappa, f0.t);
  S.selected.forEach((idx, k) => {
    const tr = S.traces[k] || (S.traces[k] = []);
    tr.push(f0.V[idx]);
    if (tr.length > 420) tr.shift();
  });
  updateFreq(f0.kappa[Math.floor(f0.kappa.length / 2)], f0.t);
  updateStats(f0.t, S.frame.speed, f0.food, f0.dir, eng.achieved, f0.running, eng.computeRate);

  // The dish's own tiles and overlays, for an engine that has them -- the arena's
  // population, births, deaths and energy. The reference engine has neither method and
  // pays nothing.
  if (eng.dishStats) updateDishStats(eng.dishStats());
  S.corpses = eng.corpses ? eng.corpses() : null;

  // Eggs arrive a handful an hour, so this is cheap, but it is read every frame anyway
  // because the alternative -- caching it on a clock like the fields -- would make a newly
  // laid egg appear up to a second after the animal laid it, and the whole point of
  // drawing them is that you see it happen.
  S.eggs = eng.eggs();

  // The fields change slowly; rebuilding the image every frame is wasted work.
  if (now - fieldClock > 1000) {
    S.field = eng.fieldImage();
    S.field.stamp = now;              // invalidates the field-image cache in drawFields
    fieldClock = now;
  }

  // A running capture samples the focused animal on dish time; inert otherwise.
  samplePreserve();

  // Last, because it snapshots what is about to be drawn and S.eggs is only settled above.
  record(S.worms, S.eggs);
}

/* Draw a moment out of the ring instead of out of the engine.
 *
 * Only the things that describe *this frame* are restored. The kymograph, the neuron
 * traces and the trails are accumulated histories of their own, and rewinding them to
 * match would mean either storing five more buffers per frame or truncating them
 * destructively -- so they keep showing the whole run, which is also what you want while
 * you are scrubbing to find a moment in them.
 */
function applyHistory() {
  const e = historyAt(S.playhead);
  if (!e || !e.worms.length) return;
  S.worms = e.worms;
  S.eggs = e.eggs;
  // Focus is a live setting, so it may name an animal that did not exist at this instant.
  const f = e.worms[Math.min(S.focus, e.worms.length - 1)];
  S.frame = f;
  drawSenses(f.sensed);
  updatePump(f.pumpRate, f.pumping);
  updateEggs(f.eggsLaid, f.eggsHeld, f.eglActive);
}

let lastTick = 0;

function tick(now) {
  // The flash decays in wall-clock time so it looks the same however fast the simulation
  // is being run, and however many frames arrive.
  const dt = lastTick ? Math.min(0.1, (now - lastTick) / 1000) : 0;
  lastTick = now;
  if (S.pumpFlash > 0) S.pumpFlash = Math.max(0, S.pumpFlash - dt * 6.5);
  // Parked in the past, the ring is the source of frames and the engine is paused, so
  // localTick would only overwrite what applyHistory just restored. The socket feed cannot
  // be stopped from here, but it records and returns without touching the display.
  if (S.playhead !== null) applyHistory();
  else if (S.engine) localTick(now);
  syncScrub(now);

  drawDish();
  drawNeurons();
  drawMuscles();
  drawKymo();
  drawTraces();
  drawLineage();
  requestAnimationFrame(tick);
}

export function start() { requestAnimationFrame(tick); }
