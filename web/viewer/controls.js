/* Everything the user can touch: pointer and keyboard wiring for the dish, the panels and
 * the footer, plus the small pieces of UI state that go with them (worm selector, ablation
 * mode, tooltip).
 *
 * This module is allowed to reach into the renderers and the transport; nothing reaches
 * back into it except the bootstrap. If a UI fix does not belong here, it belongs in the
 * renderer that owns the pixels.
 */

import { S, el, ablated, pruneAblations } from './state.js';
import { theme } from './themes.js';
import { setCam, zoom, worldAt } from './dish.js';
import { neuronAt, neuronCentre, neuronStep, invalidateLayout } from './panels.js';
import { buildLegend } from './stats.js';
import { send } from './transport.js';

/* -------------------------------------------------------------------- tooltip ----- */

const tip = () => el('tooltip');

function showTip(at, html) {
  const tooltip = tip();
  tooltip.innerHTML = html;
  tooltip.classList.add('on');
  const pad = 14;
  let x = at.clientX + pad, y = at.clientY + pad;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > innerWidth - 8) x = at.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = at.clientY - r.height - pad;
  tooltip.style.left = `${x}px`; tooltip.style.top = `${y}px`;
}
const hideTip = () => tip().classList.remove('on');

/* ----------------------------------------------------------------- worm selector -- */

/* With more than one animal on the plate every panel has to say which animal it is about,
 * so focus is explicit and visible rather than implied by index 0. */
export function buildWormSel() {
  const host = el('worm-sel');
  if (!host) return;
  const n = S.engine ? S.engine.worms.length : 1;
  host.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const b = document.createElement('button');
    b.textContent = String(i + 1);
    b.setAttribute('aria-pressed', String(i === S.focus));
    // "1" is not a name. The label is what a screen reader reads; the digit is what the
    // eye reads.
    b.setAttribute('aria-label', `Focus worm ${i + 1}`);
    b.title = `Focus the camera and the panels on worm ${i + 1}`;
    b.addEventListener('click', () => focusWorm(i));
    host.appendChild(b);
  }
  el('b-worm-del').disabled = n <= 1;
}

function focusWorm(i) {
  if (!S.engine || i < 0 || i >= S.engine.worms.length) return;
  S.focus = i;
  S.recentre = true;
  // The panels are about one animal, so their history has to start again when it changes.
  S.kymo = null;
  S.traces = S.selected.map(() => []);
  S.freqBuf = [];
  buildWormSel();
  // Ablation is per animal too, so Restore and the cell count are about the new one from
  // here on. Nothing is copied -- updateAblateUI reads whichever record focus now names.
  updateAblateUI();
}

/* Bring focus back into range after the population changed from outside these controls,
 * and report whether there is an animal left to be focused on.
 *
 * The renderer used to do this itself, with `if (S.focus >= eng.worms.length) S.focus = 0`
 * -- which moves focus without rebuilding anything. Every other path that changes focus
 * goes through `focusWorm`, which also refreshes the selector's `aria-pressed`, the
 * neuron panel's "N ablated in worm K" hint, and Restore's disabled state. That one line
 * left all three describing the animal that *used* to be focused, so the panels would be
 * showing one animal's traces under another animal's label -- plausible-looking and about
 * the wrong worm, which is the same failure as the shared ablation record in #46.
 *
 * It has never fired, because `#b-worm-del` clamps `S.focus` before the renderer can see
 * an out-of-range value. It stops being unreachable the moment the population changes from
 * anywhere else, which is exactly what #35's `removeWorm`/`hatchEgg` exist to allow: a
 * generational loop culling between frames drives focus out of range at essentially every
 * generation boundary.
 *
 * Living in controls.js rather than in the loop is the point. The renderer should not be
 * deciding what the controls say, and when it did, it did not say it.
 */
export function clampFocus() {
  const n = S.engine ? S.engine.worms.length : 0;
  if (S.focus >= 0 && S.focus < n) return true;
  if (n > 0) { focusWorm(0); return true; }
  // An empty dish. #35 lets the population reach zero, so this needs a defined answer
  // rather than an index into nothing: keep focus somewhere valid for when an animal
  // arrives, and rebuild the controls so they stop claiming one that is not there.
  S.focus = 0;
  buildWormSel();
  updateAblateUI();
  return false;
}

function updateAblateUI() {
  const b = el('b-ablate');
  const many = S.engine && S.engine.worms.length > 1;
  b.setAttribute('aria-pressed', String(S.ablateMode));
  b.textContent = S.ablateMode ? 'Click a cell' : 'Ablate';
  const n = ablated().size;
  el('b-restore').disabled = n === 0;
  el('neuron-hint').textContent = S.ablateMode
    ? (many ? `click a neuron to silence it in worm ${S.focus + 1}` : 'click a neuron to silence it')
    : (n ? `${n} ablated${many ? ' in worm ' + (S.focus + 1) : ''}` : 'hover a neuron');
}

/* ----------------------------------------------------------------------- wiring --- */

export function wire() {
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

  // A plain click on the dish selects the animal nearest the pointer, so with several on
  // the plate you can just point at the one you mean.
  dish.addEventListener('click', (e) => {
    if (!S.engine || S.worms.length < 2 || (drag && drag.moved > 3)) return;
    const [x, y] = worldAt(dish, e);
    let best = -1, bd = 1.2 * 1.2;
    S.worms.forEach((o, i) => {
      const d = (o.cx - x) ** 2 + (o.cy - y) ** 2;
      if (d < bd) { bd = d; best = i; }
    });
    if (best >= 0 && best !== S.focus) focusWorm(best);
  });

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
      const collapsed = head.parentElement.classList.toggle('collapsed');
      head.setAttribute('aria-expanded', String(!collapsed));
      invalidateLayout();                     // side panels resize; rebuild the neuron grid
    });
    head.setAttribute('aria-expanded', String(!head.parentElement.classList.contains('collapsed')));
  });

  el('b-worm-add').addEventListener('click', () => {
    if (!S.engine) return;
    const i = S.engine.addWorm();
    S.trails[i] = [];
    focusWorm(i);
  });
  el('b-worm-del').addEventListener('click', () => {
    if (!S.engine || !S.engine.removeWorm()) return;
    S.trails.pop();
    pruneAblations();          // that animal is gone, and so is the record of what it lost
    if (S.focus >= S.engine.worms.length) S.focus = S.engine.worms.length - 1;
    focusWorm(S.focus);
  });

  el('b-rail').addEventListener('click', (e) => {
    const on = el('app').classList.toggle('norail');
    e.target.setAttribute('aria-pressed', String(!on));
    e.target.textContent = on ? 'Hidden' : 'Shown';
  });

  wireNeuronPanel();

  el('b-play').addEventListener('click', (e) => {
    const playing = e.target.getAttribute('aria-pressed') === 'true';
    e.target.setAttribute('aria-pressed', String(!playing));
    e.target.textContent = playing ? 'Play' : 'Pause';
    send({ cmd: playing ? 'pause' : 'play' });
  });
  el('b-reset').addEventListener('click', () => {
    // Reset repopulates the plate, so every record is about an animal that no longer
    // exists; over the socket it restores the one animal there is. Either way nothing is
    // ablated on the other side of this, so the whole map goes rather than being pruned.
    S.ablations.clear();
    S.trail = []; S.kymo = null; S.traces = S.selected.map(() => []);
    S.freqBuf = []; S.speedWin = [];
    if (S.engine) {
      S.engine.reset();
      S.trails = S.engine.worms.map(() => []);
      S.focus = 0; S.recentre = true;
      buildWormSel();
    } else {
      send({ cmd: 'reset' });
    }
    updateAblateUI();
  });
  el('r-rate').addEventListener('input', (e) => {
    const v = Math.pow(10, parseFloat(e.target.value) / 2);
    const label = `${v.toFixed(v < 1 ? 2 : 1)}×`;
    el('o-rate').textContent = label;
    e.target.setAttribute('aria-valuetext', `${label} real time`);
    send({ cmd: 'rate', value: v });
  });
  el('b-ablate').addEventListener('click', () => { S.ablateMode = !S.ablateMode; updateAblateUI(); });
  // Restore is about the focused animal and only that one: the others keep both their
  // dead cells and the record of them.
  el('b-restore').addEventListener('click', () => {
    const cells = ablated();
    if (!cells.size) return;
    cells.clear();
    if (S.engine) S.engine.setAblated(S.focus, []);
    else send({ cmd: 'restore' });
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

/* Neuron inspection. Hover and click for a pointer; arrow keys and Enter for a keyboard,
 * because 302 cells behind a hover is 302 cells nobody without a mouse can read. */
function wireNeuronPanel() {
  const nc = el('c-neurons');

  const describe = (i) => {
    const n = S.meta.neurons[i];
    return `<b>${n.name}</b> &middot; ${n.cls}<br>
      <span class="k">kind</span> ${n.kind}${n.modality ? ' &middot; ' + n.modality : ''}<br>
      <span class="k">ganglion</span> ${n.ganglion}<br>
      <span class="k">transmitter</span> ${n.tx}${n.inh ? ' (inhibitory)' : ''}<br>
      <span class="k">V</span> ${S.frame.V[i].toFixed(1)} mV &nbsp;
      <span class="k">activity</span> ${(S.frame.act[i] * 100).toFixed(0)}%`;
  };

  nc.addEventListener('mousemove', (e) => {
    const i = neuronAt(nc, e.clientX, e.clientY);
    S.hover = i;
    if (i == null || !S.frame) { hideTip(); el('neuron-hint').textContent = 'hover a neuron'; return; }
    showTip(e, describe(i));
    el('neuron-hint').textContent = 'click to plot';
  });
  nc.addEventListener('mouseleave', () => { S.hover = null; hideTip(); });

  const toggleTrace = (i) => {
    const at = S.selected.indexOf(i);
    if (at >= 0) S.selected.splice(at, 1);
    else { S.selected.push(i); if (S.selected.length > 3) S.selected.shift(); }
    S.traces = S.selected.map(() => []);
    el('trace-hint').textContent = S.selected.map((k) => S.meta.neurons[k].name).join(', ') || '—';
  };

  const activate = (i) => {
    if (i == null) return;
    if (S.ablateMode) {
      const cells = ablated();
      if (cells.has(i)) return;                  // ablation is not undone one cell at a time
      cells.add(i);
      if (S.engine) S.engine.setAblated(S.focus, [...cells]);
      else send({ cmd: 'ablate', neurons: [S.meta.neurons[i].name] });
      updateAblateUI();
      return;
    }
    toggleTrace(i);
  };

  nc.addEventListener('click', (e) => activate(neuronAt(nc, e.clientX, e.clientY)));

  // The keyboard drives the same cursor the mouse does -- S.hover -- so the highlight the
  // renderer already draws is the focus indicator, and there is no second notion of
  // "which neuron is selected" to keep in step.
  const STEP = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

  // Tabbing in has to land somewhere. Without this the panel takes focus showing nothing,
  // and the first arrow press looks like it jumped rather than moved.
  nc.addEventListener('focus', () => {
    if (!S.meta) return;
    if (S.hover == null) S.hover = 0;
    announce(S.hover);
  });

  const announce = (i) => {
    const at = neuronCentre(nc, i);
    if (at && S.frame) showTip(at, describe(i));
    // The canvas is one focus stop, so its accessible name has to carry which cell the
    // cursor is on; a screen reader has no way to see the ring.
    const n = S.meta.neurons[i];
    nc.setAttribute('aria-label',
      `${n.name}, ${n.cls}, ${n.kind}${n.modality ? ', ' + n.modality : ''}. ` +
      `Neuron ${i + 1} of ${S.meta.neurons.length}. Enter to ${S.ablateMode ? 'ablate' : 'plot'}.`);
    el('neuron-hint').textContent = S.ablateMode ? 'Enter to ablate' : 'Enter to plot';
  };

  nc.addEventListener('keydown', (e) => {
    if (!S.meta) return;
    if (e.key === 'Enter' || e.key === ' ') {
      if (S.hover != null) { e.preventDefault(); activate(S.hover); }
      return;
    }
    const d = STEP[e.key];
    if (!d) return;
    e.preventDefault();
    const i = neuronStep(S.hover, d[0], d[1]);
    if (i == null) return;
    S.hover = i;
    announce(i);
  });
  nc.addEventListener('blur', () => { S.hover = null; hideTip(); });
}
