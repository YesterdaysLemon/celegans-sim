/* Colour scales, aware of the surface they will be drawn on.
 *
 * Follows the data-viz reference palette. Magnitudes (activation, tension) use one
 * sequential hue; signed curvature uses the diverging blue-red pair with a neutral grey
 * midpoint, so "straight" reads as nothing rather than as a colour.
 *
 * THEME-AWARE SINCE #157, which measured why fixed ramps cannot serve two grounds: the
 * old sequential ramp ran pale-to-dark, which on the DARK panels put fully-active cells
 * at 1.46:1 against the surface -- the most important value on the panel was the least
 * visible thing on it -- and on paper it was the idle cells that vanished (1.25:1). The
 * neutral curvature grey had the same disease in mirror image.
 *
 * The cure keeps the data's meaning and fixes only its projection:
 *
 *   - ORDER IS SALIENCE, in both modes. More activation always moves away from the
 *     surface -- toward bright on the terminal, toward ink on the paper. Same hue
 *     family, same 13-swatch reference ramp, same domain; only the direction of travel
 *     through it flips with the ground it sits on.
 *   - EXTREMA ARE CLAMPED to at least 3:1 against the live --surface-1, found by
 *     walking the ramp in from each end at rebuild time. "Near zero recedes" survives
 *     -- 3:1 is quiet -- but nothing on a panel is invisible any more.
 *   - THE NEUTRAL is computed, not picked: the grey nearest the quiet side of 3.2:1
 *     on the current surface, so "straight" stays the least assertive mark that still
 *     definitely exists.
 *
 * The mode is read from html[data-mode] on every call and the palette rebuilt only when
 * it changes, so a theme switch recolours the very next frame with no caller involved.
 */

function hexToRgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function lerp(a, b, t) { return a + (b - a) * t; }

// WCAG relative luminance and contrast ratio -- the same arithmetic #157 measured with.
function lum([r, g, b]) {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(a, b) {
  const la = lum(a), lb = lum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// The reference sequential blue, light to dark. Both modes sample this same ramp.
const BLUE = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec',
              '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab',
              '#184f95', '#104281', '#0d366b'].map(hexToRgb);
const WARM = hexToRgb('#e66767'), COOL = hexToRgb('#3987e5');
const MIN_CONTRAST = 3.0;

function rampRgb(ramp, t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (ramp.length - 1), i = Math.floor(x), f = x - i;
  const a = ramp[i], b = ramp[Math.min(i + 1, ramp.length - 1)];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}

/* The active palette: rebuilt when html[data-mode] changes, cached otherwise. */
let mode = null;
let ordered = BLUE, tLo = 0, tHi = 1, MID = hexToRgb('#383835');

function rebuild() {
  const m = document.documentElement.dataset.mode === 'light' ? 'light' : 'dark';
  if (m === mode) return;
  mode = m;
  const surfStr = getComputedStyle(document.documentElement)
    .getPropertyValue('--surface-1').trim() || (m === 'light' ? '#fbf8f0' : '#1a1a19');
  const surface = hexToRgb(surfStr);

  // Low end nearest the surface: pale on paper, dark on the terminal.
  ordered = m === 'light' ? BLUE : [...BLUE].reverse();

  // Clamp both extrema to the contrast floor by walking in from each end.
  tLo = 0; tHi = 1;
  while (tLo < 0.5 && contrast(rampRgb(ordered, tLo), surface) < MIN_CONTRAST) tLo += 0.01;
  while (tHi > 0.5 && contrast(rampRgb(ordered, tHi), surface) < MIN_CONTRAST) tHi -= 0.01;

  // The neutral: the grey closest to the quiet side of 3.2:1 on this surface. Lighter
  // than a dark surface, darker than a light one -- receding is the point, invisible
  // is the bug.
  const dir = lum(surface) < 0.5 ? 1 : -1;
  let g = Math.round(lum(surface) < 0.5 ? 40 : 200);
  while (g > 0 && g < 255 && contrast([g, g, g], surface) < 3.2) g += dir;
  MID = [g, g, g];
}

// Sequential: magnitude reads as distance from the surface, whichever surface that is.
export function seq(t) {
  rebuild();
  const [r, g, b] = rampRgb(ordered, tLo + (tHi - tLo) * Math.max(0, Math.min(1, t)));
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}

// Diverging: warm for dorsal, cool for ventral, computed neutral at zero.
export function divRgb(v) {
  rebuild();
  const t = Math.max(-1, Math.min(1, v));
  const end = t >= 0 ? WARM : COOL, a = Math.abs(t);
  return [lerp(MID[0], end[0], a), lerp(MID[1], end[1], a), lerp(MID[2], end[2], a)];
}
export function div(v) {
  const c = divRgb(v);
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}

// For checks and curious consumers: the current extrema and neutral, as drawn.
export function paletteReport() {
  rebuild();
  return { mode, lo: seq(0), hi: seq(1), mid: `rgb(${MID[0]},${MID[1]},${MID[2]})` };
}
