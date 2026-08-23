/* The two looks of the dish, one per mode.
 *
 * They are not a palette swap. Each is a different claim about what you are looking at:
 *
 *   digital     this is data. Near-black plate, a fixed grid, the body tinted by signed
 *               curvature so the travelling wave reads as a wave. The dark mode's dish,
 *               and deliberately untouched by the mode work: the plate rendering is the
 *               project's face and is locked.
 *   realistic   this is an animal on a plate. Warm agar, a translucent amber body with a
 *               gut line and a specular edge, bacterial lawn as a mottled film. The
 *               light mode's dish.
 *
 * A third look, cartoon, lived here until the modes landed -- flat fills, heavy
 * outlines, one obvious eye. It was retired by the owner (least favourite, and a
 * two-mode world has no middle slot); the painter went with it. See worm.js.
 *
 * Only the dish changes with the mode. The panels stay in the data palette in both,
 * because they are measurements and should not be dressed up.
 *
 * This module holds the *palettes* only. The body painters live in worm.js and are keyed
 * by the same names; keeping them apart is what lets dish.js depend on both without
 * either depending on the other.
 */

import { S, C } from './state.js';

// A speckle used by the realistic plate. Agar under a stereoscope is not a flat colour;
// without some grain the dish reads as a flat fill with a worm pasted on it.
let noiseTile = null;
export function getNoise() {
  if (noiseTile) return noiseTile;
  const n = 128;
  const cv = document.createElement('canvas');
  cv.width = cv.height = n;
  const c = cv.getContext('2d');
  const img = c.createImageData(n, n);
  let seed = 7;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  for (let i = 0; i < n * n; i++) {
    const v = rnd();
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = 255;
    img.data[i * 4 + 3] = v * v * 40;
  }
  c.putImageData(img, 0, 0);
  noiseTile = cv;
  return cv;
}

const THEMES = {
  digital: {
    plate: '#141413',
    rim: () => C('--baseline'),
    gridMajor: 'rgba(195,194,183,0.16)',
    gridMinor: 'rgba(195,194,183,0.055)',
    trail: 'rgba(195,194,183,0.30)',
    obstacle: ['#3a3936', 'rgba(255,255,255,0.12)'],
    egg: ['rgba(226,220,190,0.85)', 'rgba(255,255,255,0.35)'],
    // Field tints, alpha and gamma per layer. Gamma > 1 keeps the low end near the
    // surface: a chemical gradient covers the whole plate at some concentration, so a
    // flatter mapping just washes the dish out and hides the structure.
    fields: {
      /* Attractant keeps the steep 2.1 gamma on purpose, twice tried otherwise: dealt
       * attractant above the image clamp made a flat blue wall, and easing gamma to
       * 1.6 washed the whole dish at animal zoom (the plume's 9 mm length scale fills
       * a 6.5 mm frame, so the low end must stay near the surface). The plume reads
       * now because the DEAL guarantees a lawn near the spawn -- presence in frame,
       * not a hotter mapping, is what fixed the invisible field. */
      attractant: { tint: [57, 135, 229], alpha: 0.80, gamma: 2.1 },
      food:       { tint: [25, 158, 112], alpha: 0.85, gamma: 1.8 },
      repellent:  { tint: [208, 59, 59],  alpha: 0.85, gamma: 1.8 },
    },
  },

  realistic: {
    plate: '#8d8676',
    rim: () => 'rgba(28,25,20,0.85)',
    gridMajor: 'rgba(40,35,28,0.10)',
    gridMinor: 'rgba(40,35,28,0.04)',
    trail: 'rgba(60,54,44,0.22)',
    obstacle: ['#6d6659', 'rgba(30,26,20,0.5)'],
    egg: ['rgba(238,232,214,0.92)', 'rgba(90,80,62,0.55)'],
    fields: {
      attractant: { tint: [150, 170, 190], alpha: 0.30, gamma: 1.6 },
      food:       { tint: [226, 220, 190], alpha: 0.85, gamma: 0.8 },
      repellent:  { tint: [150, 120, 150], alpha: 0.45, gamma: 1.2 },
    },
    dark: true,
    grain: true,
    vignette: true,
  },
};

export const theme = () => THEMES[S.theme];
