/* The three looks of the dish.
 *
 * They are not a palette swap. Each is a different claim about what you are looking at:
 *
 *   digital     this is data. Near-black plate, a fixed grid, the body tinted by signed
 *               curvature so the travelling wave reads as a wave.
 *   cartoon     this is a diagram. Flat fills, heavy outlines, one obvious eye. Nothing
 *               is shaded, so nothing suggests depth that the model does not have.
 *   realistic   this is an animal on a plate. Warm agar, a translucent amber body with a
 *               gut line and a specular edge, bacterial lawn as a mottled film.
 *
 * Only the dish changes. The panels stay in the data palette in every mode, because they
 * are measurements and should not be dressed up.
 *
 * This module holds the *palettes* only. The body painters live in worm.js and are keyed
 * by the same three names; keeping them apart is what lets dish.js depend on both without
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

export const THEMES = {
  digital: {
    plate: '#141413',
    rim: () => C('--baseline'),
    gridMajor: 'rgba(195,194,183,0.16)',
    gridMinor: 'rgba(195,194,183,0.055)',
    trail: 'rgba(195,194,183,0.30)',
    obstacle: ['#3a3936', 'rgba(255,255,255,0.12)'],
    // Field tints, alpha and gamma per layer. Gamma > 1 keeps the low end near the
    // surface: a chemical gradient covers the whole plate at some concentration, so a
    // flatter mapping just washes the dish out and hides the structure.
    fields: {
      attractant: { tint: [57, 135, 229], alpha: 0.80, gamma: 2.1 },
      food:       { tint: [25, 158, 112], alpha: 0.80, gamma: 2.1 },
      repellent:  { tint: [208, 59, 59],  alpha: 0.80, gamma: 2.1 },
    },
  },

  cartoon: {
    plate: '#f2ead8',
    rim: () => '#2b2722',
    gridMajor: 'rgba(43,39,34,0.20)',
    gridMinor: 'rgba(43,39,34,0.08)',
    trail: 'rgba(43,39,34,0.22)',
    obstacle: ['#cbbfa6', '#2b2722'],
    fields: {
      attractant: { tint: [120, 176, 240], alpha: 0.55, gamma: 1.3 },
      food:       { tint: [124, 196, 122], alpha: 0.80, gamma: 0.75 },
      repellent:  { tint: [232, 118, 108], alpha: 0.72, gamma: 0.9 },
    },
    dark: true,          // chrome-on-light: the scale bar and minimap need ink, not chalk
  },

  realistic: {
    plate: '#8d8676',
    rim: () => 'rgba(28,25,20,0.85)',
    gridMajor: 'rgba(40,35,28,0.10)',
    gridMinor: 'rgba(40,35,28,0.04)',
    trail: 'rgba(60,54,44,0.22)',
    obstacle: ['#6d6659', 'rgba(30,26,20,0.5)'],
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
