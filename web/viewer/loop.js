/* The animation loop, and the local engine's per-frame read-out.
 *
 * When the animal runs in this tab there is no socket and no server: the loop steps the
 * WASM directly and reads its state out of linear memory. Everything downstream -- the
 * panels, the kymograph, the traces -- is unchanged, because it only ever wanted numbers.
 */

import { S, el } from './state.js';
import { drawDish, follow } from './dish.js';
import { drawNeurons, drawMuscles, drawKymo, drawTraces, drawSenses, pushKymo,
         invalidateLayout } from './panels.js';
import { updateFreq, updateStats, updatePump } from './stats.js';
import { buildWormSel } from './controls.js';

let fieldClock = 0;

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
  if (S.focus >= eng.worms.length) S.focus = 0;
  S.worms = [];
  for (let i = 0; i < eng.worms.length; i++) S.worms.push(eng.frame(i));
  const f0 = S.worms[S.focus];
  S.frame = {
    t: f0.t, speed: 0, food: f0.food, dir: f0.dir, achieved: eng.achieved,
    sensed: f0.sensed, nodes: f0.nodes, act: f0.act, V: f0.V,
    tension: f0.tension, kappa: f0.kappa, running: f0.running,
  };

  for (let i = 0; i < S.worms.length; i++) {
    const fi = S.worms[i];
    let cx = 0, cy = 0;
    const nn = fi.nodes.length / 2;
    for (let k = 0; k < nn; k++) { cx += fi.nodes[k * 2]; cy += fi.nodes[k * 2 + 1]; }
    cx /= nn; cy /= nn;
    fi.cx = cx; fi.cy = cy;
    const tr = S.trails[i] || (S.trails[i] = []);
    const last = tr[tr.length - 1];
    if (!last || Math.hypot(cx - last[0], cy - last[1]) > 0.02) {
      tr.push([cx, cy]);
      if (tr.length > 2200) tr.shift();
    }
    if (i === S.focus) follow(cx, cy);
  }

  // Speed of the focused animal, over a window of *simulated* time. Dividing by anything
  // else makes the number a statement about the frame rate: an undulating worm slews its
  // centroid from side to side once a cycle, so a short window reports the slosh.
  if (S.speedWin === undefined || S.speedFocus !== S.focus) { S.speedWin = []; S.speedFocus = S.focus; }
  const c0 = S.trails[S.focus][S.trails[S.focus].length - 1];
  if (c0) {
    S.speedWin.push([f0.t, c0[0], c0[1]]);
    while (S.speedWin.length > 1 && f0.t - S.speedWin[0][0] > 2.0) S.speedWin.shift();
    const a = S.speedWin[0], b = S.speedWin[S.speedWin.length - 1];
    const span = b[0] - a[0];
    S.frame.speed = span > 0.2 ? Math.hypot(b[1] - a[1], b[2] - a[2]) / span : 0;
  }

  const sensed = Object.assign({}, f0.sensed, {
    pumpNorm: f0.pumpRate / 6.0, lumenNorm: f0.lumen / 0.05,
  });
  drawSenses(sensed);
  updatePump(f0.pumpRate, f0.pumping);

  pushKymo(f0.kappa, f0.t);
  S.selected.forEach((idx, k) => {
    const tr = S.traces[k] || (S.traces[k] = []);
    tr.push(f0.V[idx]);
    if (tr.length > 420) tr.shift();
  });
  updateFreq(f0.kappa[Math.floor(f0.kappa.length / 2)], f0.t);
  updateStats(f0.t, S.frame.speed, f0.food, f0.dir, eng.achieved, f0.running);

  // The fields change slowly; rebuilding the image every frame is wasted work.
  if (now - fieldClock > 1000) {
    S.field = eng.fieldImage();
    S.field.stamp = now;              // invalidates the field-image cache in drawFields
    fieldClock = now;
  }
}

let lastTick = 0;

function tick(now) {
  // The flash decays in wall-clock time so it looks the same however fast the simulation
  // is being run, and however many frames arrive.
  const dt = lastTick ? Math.min(0.1, (now - lastTick) / 1000) : 0;
  lastTick = now;
  if (S.pumpFlash > 0) S.pumpFlash = Math.max(0, S.pumpFlash - dt * 6.5);
  if (S.engine) localTick(now);

  drawDish();
  drawNeurons();
  drawMuscles();
  drawKymo();
  drawTraces();
  requestAnimationFrame(tick);
}

export function start() { requestAnimationFrame(tick); }
