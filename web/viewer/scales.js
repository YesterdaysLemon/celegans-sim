/* Colour scales.
 *
 * Follows the data-viz reference palette. Magnitudes (activation, tension) use one
 * sequential hue; signed curvature uses the diverging blue-red pair with a neutral grey
 * midpoint, so "straight" reads as nothing rather than as a colour.
 */

// Sequential blue, the reference ramp, sampled 100 -> 700. On a dark surface the low end
// recedes into the surface, which is exactly what "near zero" should do.
const BLUE = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec',
              '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab',
              '#184f95', '#104281', '#0d366b'].map(hexToRgb).reverse();

function hexToRgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function lerp(a, b, t) { return a + (b - a) * t; }
function rampRgb(ramp, t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (ramp.length - 1), i = Math.floor(x), f = x - i;
  const a = ramp[i], b = ramp[Math.min(i + 1, ramp.length - 1)];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}

// Sequential: dark surface -> saturated blue, so magnitude reads as luminance.
export function seq(t) {
  const [r, g, b] = rampRgb(BLUE, 1 - Math.max(0, Math.min(1, t)));
  return `rgb(${r | 0},${g | 0},${b | 0})`;
}

// Diverging: warm for dorsal, cool for ventral, neutral grey at zero.
const MID = hexToRgb('#383835'), WARM = hexToRgb('#e66767'), COOL = hexToRgb('#3987e5');
export function divRgb(v) {
  const t = Math.max(-1, Math.min(1, v));
  const end = t >= 0 ? WARM : COOL, a = Math.abs(t);
  return [lerp(MID[0], end[0], a), lerp(MID[1], end[1], a), lerp(MID[2], end[2], a)];
}
export function div(v) {
  const c = divRgb(v);
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}
export const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
