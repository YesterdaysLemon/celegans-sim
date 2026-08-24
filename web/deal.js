/* The deal, made shareable.
 *
 * Both dishes deal their worlds per load -- lawn count, placement, drops, seeds. Fun,
 * until someone gets a beautiful deal and has no way to hand it to anyone: the deal
 * lived in Math.random and died with the tab. So the deal is SEEDED now. A plain load
 * draws a fresh seed (nothing changes for the casual visitor); `?dish=1234` replays
 * that exact deal -- same lawns, same drops, same founders, same weather clocks -- and
 * the Share button in the camera tray writes that link for whatever dish you are
 * looking at.
 *
 * Node imports the engines too (the scripted-clock rate test), so nothing here touches
 * `location` except behind a guard.
 */

/* mulberry32: the same tiny generator the arena policy trusts for its recorded runs. */
export function mulberry(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* The seed this load plays: ?dish=N replays a shared deal, anything else is fresh. */
export function loadSeed() {
  try {
    const m = /[?&]dish=(\d+)/.exec(location.search);
    if (m) return Number(m[1]) >>> 0;
  } catch (e) { /* no location: a node test drives the engine directly */ }
  return (Math.random() * 0x7fffffff) | 0;
}

/* Each dish takes its own stream from the one seed, so the animal plate and the arena
 * are different worlds that still travel together in one link. */
export const DISH_STREAM = { animal: 0, arena: 0x5bf03635 };
