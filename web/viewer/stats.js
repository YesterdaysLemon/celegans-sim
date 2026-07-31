/* Derived numbers for the header, and the dish legend.
 *
 * Both transports feed these the same arguments, which is the point: the frequency
 * estimate and the header readouts should not be able to differ between the local engine
 * and the socket.
 */

import { S, C, el } from './state.js';

// Undulation frequency from zero crossings of midbody curvature, about its own mean.
// A worm holding a turn has a large standing offset in its curvature; counting raw sign
// changes would call that "no undulation" while it is plainly still undulating.
export function updateFreq(k, t) {
  const b = S.freqBuf;
  b.push([t, k]);
  while (b.length && t - b[0][0] > 12) b.shift();
  if (b.length < 40) return;
  const mean = b.reduce((a, x) => a + x[1], 0) / b.length;
  const dev = Math.sqrt(b.reduce((a, x) => a + (x[1] - mean) ** 2, 0) / b.length);
  if (dev < 0.15) { S.freq = 0; return; }        // genuinely not undulating
  let crossings = 0;
  for (let i = 1; i < b.length; i++) {
    if ((b[i - 1][1] - mean < 0) !== (b[i][1] - mean < 0)) crossings++;
  }
  const span = b[b.length - 1][0] - b[0][0];
  S.freq = span > 0 ? crossings / (2 * span) : 0;
}

export function updateStats(t, speed, food, dir, achieved, running) {
  el('s-time').innerHTML = `${t.toFixed(1)}<small>s</small>`;
  el('s-speed').innerHTML = `${(speed * 1000).toFixed(0)}<small>µm/s</small>`;
  el('s-freq').innerHTML = S.freq > 0.02
    ? `${S.freq.toFixed(2)}<small>Hz</small>` : `—<small>Hz</small>`;
  el('s-dir').textContent = dir > 0.5 ? 'forward' : dir < -0.5 ? 'backward' : 'still';
  el('s-dir').style.color = dir < -0.5 ? C('--warning') : C('--text-primary');
  el('s-food').textContent = food.toFixed(1);
  el('s-rate').innerHTML = `${achieved.toFixed(1)}<small>×</small>`;
  const btn = el('b-play');
  if ((btn.getAttribute('aria-pressed') === 'true') !== !!running) {
    btn.setAttribute('aria-pressed', String(!!running));
    btn.textContent = running ? 'Pause' : 'Play';
  }
}

// The pharyngeal pump lamp. The flash fires on the *rising edge* of a pump rather than
// while one is open: a pump lasts 150 ms and frames arrive at 30 Hz, so lighting the lamp
// for the whole open interval would have it on more often than off and read as a glow.
export function updatePump(pumpRate, pumping) {
  if (pumping > 0.5 && S.lastPumping <= 0.5) S.pumpFlash = 1;
  S.lastPumping = pumping;
  el('s-pump').innerHTML = `${(pumpRate * 60).toFixed(0)}<small>/min</small>`;
  el('pump-dot').classList.toggle('on', S.pumpFlash > 0.35);
}

// The legend explains whatever the dish is currently saying, which is different in each
// mode: digital colours the body by curvature, the other two do not.
export function buildLegend() {
  const rows = S.theme === 'digital'
    ? [['var(--dorsal)', 'dorsal bend'], ['var(--ventral)', 'ventral bend'],
       ['var(--series-3)', 'food'], ['var(--critical)', 'repellent']]
    : [['var(--series-3)', 'food'], ['var(--series-1)', 'attractant'],
       ['var(--critical)', 'repellent']];
  el('legend').innerHTML = rows
    .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join('');
}
