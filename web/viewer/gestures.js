/* The dish's hands: every gesture the plate itself answers, and the pipette.
 *
 * Split out of controls.js when that file reached nine hundred lines wearing four hats.
 * This module owns exactly what happens ON the dish canvas -- wheel and pinch zoom,
 * drag-to-pan, both tweezers (mouse shift-drag, touch long-press), the pipette's whole
 * arm/drop/rack contract and its refusal flashes. Everything else the user can touch
 * stays in controls.js, which calls wireGestures() once and passes the two helpers the
 * gestures need but do not own: focusWorm (selection is viewer state) and coarse (the
 * pointer-type probe the whole file shares).
 *
 * Dependency direction: state, dish, transport -- never controls. The one export going
 * the other way is flashHint, because the dish's hint line is the natural place for any
 * dish-adjacent control (the share button) to speak.
 */

import { S, el } from './state.js';
import { setCam, zoom, worldAt } from './dish.js';
import { send } from './transport.js';

/* The dish-hint machinery. Lazy on two axes (review finding): the element is looked up
 * on first use, and the resting text is captured at the first moment this module
 * replaces it -- wire() runs before app.js's ?server block rewrites the hint for the
 * socket dish, and an eager snapshot would restore local-mode text (a hidden rack,
 * tweezers the protocol lacks) after any server-mode flash. */
let hintEl = null;
let hintBase = null;
let hintTimer = 0;
const hint = () => (hintEl ??= el('dish-hint'));
const keepBase = () => { if (hintBase === null) hintBase = hint().innerHTML; };
const restingHint = () => {
  hint().classList.remove('flash');
  hint().innerHTML = S.pipette
    ? `click to drop ${DROP_NOUN[S.dropper]} &middot; bottle again to put the pipette away`
    : hintBase ?? hint().innerHTML;
};
export function flashHint(msg) {
  keepBase();
  clearTimeout(hintTimer);
  hint().textContent = msg;
  hint().classList.add('flash');
  hintTimer = setTimeout(restingHint, 1800);
}

/* THE PIPETTE. A bottle click picks it up; one click or tap on the dish drops that
 * source; clicking the armed bottle again -- or Esc -- puts it away. The armed state
 * is visible three ways at once (the pressed bottle, the pipette cursor over the
 * dish, the hint line), because the old contract -- an unlabelled double-click on an
 * always-armed bottle -- was invisible, and its failures were silent: the 16-patch
 * cap refusing, or a drop landing outside the glass, both read as "the dropper
 * didn't fire". Refusals FLASH their reason now. */
const DROP_CMD = { food: 'drop_food', crumbs: 'drop_crumbs',
                   scent: 'drop_scent', repellent: 'drop_repellent' };
const DROP_NOUN = { food: 'a lawn', crumbs: 'crumbs',
                    scent: 'a scent plume', repellent: 'repellent' };

function armPipette(name) {
  keepBase();
  S.pipette = !!name;
  if (name) S.dropper = name;
  document.querySelectorAll('[data-drop]').forEach((o) =>
    o.setAttribute('aria-pressed', String(S.pipette && o.dataset.drop === S.dropper)));
  el('dish').classList.toggle('pipette', S.pipette);
  clearTimeout(hintTimer);
  restingHint();
}

function dropAt(x, y) {
  if (!S.meta) return;
  if (Math.hypot(x, y) > S.meta.world.radius - 1) {
    flashHint('that landed outside the glass');
    return;
  }
  const ok = send({ cmd: DROP_CMD[S.dropper] || 'drop_food', x, y, r: 2.5 });
  if (ok === false) flashHint('the plate is full — 16 colonies is the cap');
  /* The socket dish: send() returns nothing over the wire, and the server ships
   * world.patches only in its hello -- so the marker the local engine would have
   * pushed has to be pushed here, or a server-mode lawn lands invisibly on the
   * minimap (review finding: the exact silent-dropper failure, reintroduced for
   * one transport). The socket protocol only has the lawn bottle. */
  if (!S.engine && ok === undefined && (DROP_CMD[S.dropper] || 'drop_food') === 'drop_food') {
    S.meta.world.patches.push({ x, y, r: 2.5, kind: 'food' });
  }
}

export function wireGestures({ focusWorm, coarse }) {
  const dish = el('c-dish');

  dish.addEventListener('wheel', (e) => {
    e.preventDefault();
    const [wx, wy] = worldAt(dish, e);
    zoom(Math.exp(e.deltaY * 0.0016), wx, wy);
  }, { passive: false });

  // Drag to pan. Dragging is how you detach the camera, so it switches to Free itself
  // rather than making you find a button first -- and a drag must not also be read as a
  // click, or every pan would drop a lawn.
  //
  // Shift-drag on an animal is the TWEEZERS: pick it up and put it down somewhere else.
  // The runtime translates the pose rigidly (translateWorm) -- gait phase, neurons and
  // every internal state ride along -- so this is moving the animal, not resetting it.
  // Local engines only: the socket protocol has no such command, and the ?server dish
  // simply pans as before.
  let drag = null;
  let tweeze = null;               // { i } while an animal is held
  let lastMoved = 0;               // how far the finished drag travelled, for click's guard
  let longPress = null;            // pending touch-tweezers timer
  let justTweezed = false;         // a long-press release must not also drop or select
  /* How close a grab has to land. A mouse points precisely; a fingertip covers about
   * two millimetres of a phone's dish at plate zoom, so the touch radius scales with
   * the view instead of demanding mouse accuracy from a thumb. */
  const grabIndex = (x, y, coarseGrab) => {
    const grab = coarseGrab ? Math.max(1.2, S.view.span / 12) : 1.2;
    let best = -1, bd = grab * grab;
    S.worms.forEach((o, i) => {
      const d = (o.cx - x) ** 2 + (o.cy - y) ** 2;
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  };
  /* The pinch. touch-action: none hands every touch gesture to this file, so the one
   * the browser used to provide -- pinch-to-zoom -- has to be provided back. Two
   * fingers zoom the DISH (not the page), anchored at their midpoint, through the same
   * zoom() the wheel uses. A second finger landing cancels any pan, pending grab or
   * held animal: two fingers mean the camera, whatever one finger was doing. */
  const touches = new Map();       // active touch pointers, clientX/Y by pointerId
  let pinchD = 0;                  // finger distance at the last pinch step
  const pinchPts = () => [...touches.values()];
  dish.addEventListener('pointerdown', (e) => {
    justTweezed = false;
    if (e.pointerType === 'touch') {
      touches.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });
      if (touches.size === 2) {
        if (longPress) { clearTimeout(longPress); longPress = null; }
        drag = null;
        tweeze = null;
        const [a, b] = pinchPts();
        pinchD = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        return;
      }
      if (touches.size > 2) return;
    }
    if (e.shiftKey && S.engine && S.worms.length) {
      const [x, y] = worldAt(dish, e);
      const best = grabIndex(x, y, false);
      if (best >= 0) {
        tweeze = { i: best };
        try { dish.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ }
        dish.classList.add('dragging');
        return;
      }
    }
    drag = { x: e.clientX, y: e.clientY, moved: 0 };
    try { dish.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ }
    dish.classList.add('dragging');
    /* The touch tweezers: hold a fingertip on an animal for half a second and it is in
     * your grip -- the shift-drag contract for hands that have no shift key. A finger
     * that starts panning cancels the hold; a hold that fires cancels the pan. */
    if (e.pointerType === 'touch' && S.engine && S.worms.length) {
      const [x, y] = worldAt(dish, e);
      const best = grabIndex(x, y, true);
      if (best >= 0) {
        longPress = setTimeout(() => {
          longPress = null;
          drag = null;
          tweeze = { i: best };
          justTweezed = true;
          if (navigator.vibrate) navigator.vibrate(30);
        }, 450);
      }
    }
  });
  dish.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch' && touches.has(e.pointerId)) {
      touches.set(e.pointerId, { clientX: e.clientX, clientY: e.clientY });
      if (touches.size >= 2) {
        const [a, b] = pinchPts();
        const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        if (pinchD > 0 && d > 0) {
          const mid = { clientX: (a.clientX + b.clientX) / 2,
                        clientY: (a.clientY + b.clientY) / 2 };
          const [wx, wy] = worldAt(dish, mid);
          zoom(pinchD / d, wx, wy);
        }
        pinchD = d;
        return;
      }
    }
    if (tweeze) {
      const eng = S.engine, f = S.worms[tweeze.i];
      if (!eng || !f) { tweeze = null; return; }
      const [x, y] = worldAt(dish, e);
      // Hold the body where the pointer is, kept inside the glass. The clamp is on the
      // *destination* so a fling at the rim lands at the rim rather than outside it.
      const R = S.meta.world.radius - 0.8;
      const d = Math.hypot(x, y);
      const tx = d > R ? x * (R / d) : x, ty = d > R ? y * (R / d) : y;
      eng.E.translateWorm(eng.worms[tweeze.i], tx - f.cx, ty - f.cy);
      // The trail would draw the teleport as a stroke across the dish; the animal's
      // history restarts where it was put down.
      if (S.trails[tweeze.i]) S.trails[tweeze.i].length = 0;
      return;
    }
    if (!drag) return;
    const r = dish.getBoundingClientRect();
    const scale = Math.min(r.width, r.height) / S.view.span;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.moved += Math.abs(dx) + Math.abs(dy);
    drag.x = e.clientX; drag.y = e.clientY;
    // A finger on its way somewhere is panning, not holding: the pending grab lets go.
    if (longPress && drag.moved > 6) { clearTimeout(longPress); longPress = null; }
    if (drag.moved > 3) {
      if (S.cam !== 'free') setCam('free');
      S.view.cx -= dx / scale;
      S.view.cy += dy / scale;
    }
  });
  const endDrag = (e) => {
    if (e.pointerType === 'touch') {
      touches.delete(e.pointerId);
      /* A finger lifting out of a pinch re-bases the distance on the SURVIVING pair:
       * left stale, the next move compares the new pair against the old pair's
       * spacing and the dish jumps a zoom factor nobody asked for (review finding). */
      if (touches.size >= 2) {
        const [a, b] = pinchPts();
        pinchD = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      } else {
        pinchD = 0;
      }
    }
    if (longPress) { clearTimeout(longPress); longPress = null; }
    if (drag || tweeze) {
      try { dish.releasePointerCapture?.(e.pointerId); } catch (err) { /* synthetic */ }
    }
    /* A released grab -- mouse shift-drag as much as a touch long-press -- must not be
     * read as a click: the browser fires one after pointerup however far the pointer
     * travelled, and with the pipette armed that click would plant a source exactly
     * where the animal was put down (review finding). */
    if (tweeze) justTweezed = true;
    lastMoved = drag ? drag.moved : 0;
    drag = null;
    tweeze = null;
    dish.classList.remove('dragging');
  };
  dish.addEventListener('pointerup', endDrag);
  dish.addEventListener('pointercancel', endDrag);

  // A plain click: drops, if the pipette is in hand; otherwise selects the animal
  // nearest the pointer, so with several on the plate you can just point at the one
  // you mean. Never after a pan, and never on the release of a long-press grab.
  dish.addEventListener('click', (e) => {
    const jt = justTweezed;
    justTweezed = false;
    if (jt || lastMoved > 3) return;
    const [x, y] = worldAt(dish, e);
    if (S.pipette) { dropAt(x, y); return; }
    if (!S.engine || S.worms.length < 2) return;
    const best = grabIndex(x, y, coarse());
    if (best >= 0 && best !== S.focus) focusWorm(best);
  });

  // The old double-click contract still drops the pipette's current bottle for hands
  // that learned it -- but only while the pipette is racked, or a double-click while
  // armed would stack three drops (two clicks and this).
  dish.addEventListener('dblclick', (e) => {
    if (S.pipette || !S.meta) return;
    const [x, y] = worldAt(dish, e);
    dropAt(x, y);
  });

  document.querySelectorAll('[data-drop]').forEach((b) => b.addEventListener('click', () => {
    armPipette(S.pipette && S.dropper === b.dataset.drop ? null : b.dataset.drop);
  }));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && S.pipette) armPipette(null);
  });
}
