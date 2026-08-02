/* The viewer's two rate readouts, driven by a clock this file owns.
 *
 *   node --test tools/sim_rate.test.mjs
 *
 * What is being tested is arithmetic about time, so the one thing the test must not do is
 * ask the machine it is running on what time it is. Every millisecond here is scripted:
 * `rig.ms` is simultaneously the animation-frame timestamp handed to advance(), the clock
 * local.js measures its 7 ms stepping budget against, and the cost of the stepping itself
 * (`stepAll` moves it forward). That is why LocalEngine takes a clock -- see its
 * constructor. A CI runner having a slow morning changes nothing below.
 *
 * The claim under test, from #56: Sim rate is simulated seconds per *wall* second, over
 * the whole frame, including the time nobody stepped in. It used to be simulated seconds
 * per second spent inside the stepping loop, which is a different and much flatteringer
 * number: 1.43x for a run that was advancing at 0.600x, and 20x during a second in which
 * the animal advanced 140 ms. That number still exists, as `computeRate`, under a label
 * that says what it is.
 *
 * It lives in tools/ rather than beside web/local.js because web/ is served verbatim to
 * every visitor and nothing test-only belongs in it.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { LocalEngine } from '../web/local.js';

const DT = 0.0005;              // s -- NeuralParams.dt, the timestep the .model exports
const CHUNK = 20;               // steps between clock checks, from local.js
const CHUNK_T = DT * CHUNK;     // 10 ms of animal per chunk
const BUDGET_MS = 7;            // per-frame stepping budget, from local.js
const FRAME_MS = 1000 / 60;     // one 60 Hz animation frame

/* A LocalEngine with the WASM replaced by a stopwatch.
 *
 * `chunkCostMs` is what one 20-step chunk costs to compute, which is the single knob that
 * decides whether this machine keeps up: 0.5 ms is a laptop with headroom, 7 ms is a chunk
 * that eats the entire frame budget on its own.
 *
 * The rig also keeps its own totals for simulated and wall time, accumulated from the
 * clock rather than from anything local.js reports, and checks the published rate against
 * them every time a window closes. That check is the whole test: everything below it is
 * about arranging interesting time.
 */
function rig({ rate = 1, chunkCostMs = 0.5 } = {}) {
  const r = {
    ms: 0,                      // the clock: rAF timestamps, budget, and cost of stepping
    prev: 0,                    // the previous frame's timestamp
    frames: 0,
    stepsTaken: 0,              // steps the engine actually asked the runtime for
    sim: 0, wall: 0,            // this window's totals, measured here, not read from there
    asked: 0, ran: 0,           // simulated seconds the rate slider wanted, and got
    flushes: [],                // one entry per rate window the engine published
  };

  const eng = new LocalEngine(() => r.ms);
  eng.ready = true;             // no .wasm and no .model: advance() needs neither
  eng.dt = DT;
  eng.rate = rate;
  eng.E = {
    stepAll(n) {
      r.stepsTaken += n;
      r.ms += (n / CHUNK) * chunkCostMs;   // stepping costs wall time, as it does in a tab
    },
  };
  r.eng = eng;

  /* One animation frame. The engine is called with the frame's timestamp and steps, which
   * moves the clock; then the rest of the frame -- drawing the dish, the six panels,
   * compositing, and waiting for the next vsync -- is charged to the clock as well. That
   * remainder is exactly the time the old accounting threw away. If stepping overran the
   * frame the next one starts late rather than early, which is what a browser does. */
  r.frame = (frameMs = FRAME_MS) => {
    const start = r.ms;
    const elapsed = (start - r.prev) / 1000;
    r.prev = start;
    const windowBefore = eng._window.wall;
    const ran = eng.advance(start);
    r.frames++;
    if (eng.running) {
      r.sim += ran; r.wall += elapsed;
      r.asked += elapsed * eng.rate; r.ran += ran;
    } else {
      // A pause is a boundary, not a slow patch: neither side of the ratio may cross it.
      r.sim = 0; r.wall = 0;
    }
    /* Two claims about the window, and they are the load-bearing ones.
     *
     * First: a running frame either adds its whole wall time to the open window or closes
     * it. There is no third option, and every way of losing time that #56 lists -- the
     * frames that stepped nothing, the seconds a stall dropped, a denominator counting
     * something other than the clock -- shows up here as a window that did neither.
     *
     * Second: what it publishes is the simulated time over the wall time of exactly the
     * frames that went into it, both measured out here from the scripted clock.
     *
     * Reaching into _window is deliberate. This test is checking the window's arithmetic,
     * and re-deriving *when* it closes from the 0.4 s policy would make the test a copy of
     * the code it is checking rather than a check on it. */
    const after = eng._window.wall;
    if (eng.running && elapsed > 0) {
      const published = after === 0;                 // local.js zeroes it when it closes
      assert.ok(published || Math.abs(after - (windowBefore + elapsed)) < 1e-12,
                `frame ${r.frames}: the rate window went ${windowBefore} -> ${after} across `
                + `a frame of ${elapsed} s, so it neither took the frame's wall time nor `
                + 'published');
      if (published) {
        assert.ok(r.wall > 0, 'a rate window published with no wall time in its denominator');
        assert.ok(
          Math.abs(eng.achieved - r.sim / r.wall) < 1e-9,
          `Sim rate ${eng.achieved} is not this window's ${r.sim} simulated seconds over `
          + `its ${r.wall} wall seconds (${r.sim / r.wall})`,
        );
        r.flushes.push({ achieved: eng.achieved, compute: eng.computeRate,
                         sim: r.sim, wall: r.wall, frame: r.frames });
        r.sim = 0; r.wall = 0;
      }
    }
    // Whatever is left of the frame after the stepping: render, composite, idle.
    r.ms = start + Math.max(frameMs, r.ms - start);
    return ran;
  };

  r.frames_ = (n, frameMs) => { for (let i = 0; i < n; i++) r.frame(frameMs); };
  r.until = (pred, cap = 100000) => {
    for (let i = 0; i < cap && !pred(); i++) r.frame();
    assert.ok(pred(), 'the rig never reached the state the test was waiting for');
  };
  return r;
}

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

/* ---------------------------------------------------------------- normal stepping ---- */
/* The numbers in this one are the issue's own: 0.600 simulated seconds advanced over
 * 1.000 wall second, of which 0.420 s was spent stepping.
 *
 * A chunk that costs the whole 7 ms budget produces them exactly. At 0.6x a 16.67 ms frame
 * asks for one 10 ms chunk; the chunk costs 7 ms and the budget then stops the loop, so
 * every frame steps 10 ms of animal for 7 ms of CPU. Sixty frames later that is 0.600 s of
 * animal, 0.420 s of stepping, and 1.000 s of clock.
 */
test('normal stepping: 0.600 s of animal per wall second reads 0.6x, not 1.43x', () => {
  const r = rig({ rate: 0.6, chunkCostMs: BUDGET_MS });
  r.frames_(360);                                    // 6.0 s of wall clock

  assert.ok(r.flushes.length >= 12, `only ${r.flushes.length} rate windows in 6 s`);
  assert.ok(r.stepsTaken > 0, 'the engine never stepped, so nothing here is about stepping');

  for (const f of r.flushes) {
    assert.ok(f.sim > 0, 'a window published with no simulated time in its numerator');
    assert.ok(Math.abs(f.achieved - 0.6) < 0.03,
              `Sim rate ${f.achieved.toFixed(4)}x for a run advancing at 0.600x`);
    // And explicitly not the old number. 10/7 is what dividing by stepping time gives.
    assert.ok(Math.abs(f.achieved - 10 / 7) > 0.5,
              `Sim rate ${f.achieved.toFixed(4)}x is the compute throughput again`);
  }
  assert.ok(Math.abs(mean(r.flushes.map((f) => f.achieved)) - 0.6) < 0.01,
            `mean Sim rate ${mean(r.flushes.map((f) => f.achieved))}, expected 0.600`);

  /* The old number was not wrong about anything except its name, so it is still here:
   * 10 ms of animal per 7 ms of stepping is 1.4286x of compute throughput, and the header
   * shows it under Compute. Exact, not approximate -- every frame in this scenario steps
   * one chunk and spends the same 7 ms doing it. */
  for (const f of r.flushes) {
    assert.ok(Math.abs(f.compute - 10 / 7) < 1e-6,
              `compute rate ${f.compute}, expected ${10 / 7}`);
  }
});

/* -------------------------------------------------------------------- a long frame ---- */
/* One 1000 ms frame -- a garbage collection, a backgrounded tab, a resize that relaid the
 * whole page out. The animal advances by whatever the 7 ms budget buys and the rest of the
 * backlog is dropped, so that second is a second in which the run fell behind. The readout
 * has to say so; the old one could not, because the stalled second was never in it.
 */
test('a long frame is a second the run did not keep up with', () => {
  const r = rig({ rate: 1.0, chunkCostMs: 0.5 });
  r.until(() => r.flushes.length >= 3);              // settle into a steady 1.0x
  const settled = r.eng.achieved;
  assert.ok(Math.abs(settled - 1.0) < 0.05,
            `the rig was not keeping up before the stall: ${settled}x`);

  const before = r.flushes.length;
  r.frame(1000);                                     // this frame takes a full second
  const stalled = r.frame();                         // ...which the next one is told about

  assert.ok(stalled > 0, 'nothing stepped in the stalled frame, so it measures nothing');
  assert.ok(Math.abs(stalled - 0.14) < 1e-9,
            `the stalled frame stepped ${stalled} s of animal, expected 0.14 (14 chunks `
            + `of ${CHUNK_T} s at 0.5 ms each, until the ${BUDGET_MS} ms budget stopped it)`);
  assert.ok(r.flushes.length > before, 'the stalled second did not publish a rate at all');

  const f = r.flushes[r.flushes.length - 1];
  assert.ok(f.wall > 1.0, `the stalled second is not in the denominator: ${f.wall} s`);
  assert.ok(f.achieved > 0.1 && f.achieved < 0.2,
            `Sim rate ${f.achieved.toFixed(4)}x across a second that advanced `
            + `${f.sim.toFixed(3)} s of animal`);
  // A denominator capped at half a second the way the accumulator is would report 0.29x
  // here, and stepping time alone reports 20x. Both are above this line.
  assert.ok(f.achieved < 0.25, `the stall was discounted: ${f.achieved.toFixed(4)}x`);

  /* Compute is unmoved, and that is the point of having both: nothing was wrong with the
   * machine during that second. 10 ms of animal per 0.5 ms of stepping is 20x, before the
   * stall and during it. */
  assert.ok(Math.abs(f.compute - CHUNK_T / 0.0005) < 1e-6,
            `compute rate ${f.compute}, expected 20`);
  assert.ok(f.compute > 50 * f.achieved,
            'the two readouts agreed across a stall, so one of them is not measuring it');
});

/* ------------------------------------------------------------------ pause / resume ---- */
/* Paused wall time belongs to neither side of the ratio. The viewer keeps calling advance()
 * on every animation frame while paused -- that is how the pump lamp and the panels keep
 * drawing -- so those frames must contribute nothing at all, and the window they interrupt
 * must not survive them.
 */
test('pause and resume: paused time is not slow time, and does not leak across', () => {
  const r = rig({ rate: 1.0, chunkCostMs: 0.5 });
  r.until(() => r.flushes.length >= 3);
  assert.ok(Math.abs(r.eng.achieved - 1.0) < 0.05,
            `not keeping up before the pause: ${r.eng.achieved}x`);

  // Pause with a window nearly full, which is where a leak would do the most damage.
  r.until(() => r.eng._window.wall > 0.35);
  const stale = r.eng._window.wall;

  r.eng.running = false;
  const before = { flushes: r.flushes.length, steps: r.stepsTaken };
  let paused = 0, ranWhilePaused = 0;
  for (let i = 0; i < 300; i++) {                    // 5 s of wall clock, paused
    ranWhilePaused += r.frame();
    paused++;
    assert.equal(r.eng.achieved, 0, 'a paused run reported a rate');
    assert.equal(r.eng.computeRate, 0, 'a paused run reported compute throughput');
  }
  assert.ok(paused > 100, 'not enough paused frames for the assertions above to mean much');
  assert.equal(ranWhilePaused, 0, 'the animal advanced while paused');
  assert.equal(r.stepsTaken, before.steps, 'the runtime was stepped while paused');
  assert.equal(r.flushes.length, before.flushes, 'a rate window published while paused');

  /* Resume, but slower than before. The first window on the far side has to describe the
   * far side: if the ~0.4 s of 1.0x frames from before the pause survive it, it reports
   * something close to 1.0x for a run that is plainly doing 0.2x. */
  assert.ok(stale > 0.35, 'the pre-pause window was empty, so nothing could have leaked');
  r.eng.running = true;
  r.eng.rate = 0.2;
  const at = r.flushes.length;
  r.until(() => r.flushes.length > at);
  const f = r.flushes[at];

  assert.ok(f.sim > 0, 'the first window after the resume stepped nothing');
  assert.ok(f.wall > 0.4, `the first window after the resume covered only ${f.wall} s`);
  assert.ok(Math.abs(f.achieved - 0.2) < 0.03,
            `Sim rate ${f.achieved.toFixed(4)}x for the first window after resuming at 0.2x`);
  // A window that survives the pause reports 0.90x here. Counting only the frames that
  // stepped reports 0.60x for a steady 0.2x run -- two frames in three step nothing at
  // 0.2x, and dropping them drops their wall time with them. Both are above this line.
  assert.ok(f.achieved < 0.5, `the pause leaked into the resumed run: ${f.achieved}x`);
});

/* --------------------------------------------------------------- dropped backlog ---- */
/* Ask for 8x on a machine that can afford 1.2x. Every frame the budget stops the loop with
 * most of the requested animal unstepped, and local.js drops it rather than owing it
 * forward. The wall time of the frame stays in the denominator regardless -- dropping the
 * work does not drop the second it happened in, which is the last of the four places the
 * old readout leaked.
 */
test('dropped backlog stays in the denominator', () => {
  const r = rig({ rate: 8.0, chunkCostMs: 4 });      // two chunks and the budget is gone
  r.frames_(360);                                    // 6.0 s of wall clock

  assert.ok(r.flushes.length >= 12, `only ${r.flushes.length} rate windows in 6 s`);
  assert.ok(r.ran > 0, 'nothing was stepped, so nothing was dropped either');
  assert.ok(r.ran < 0.25 * r.asked,
            `only ${(r.asked - r.ran).toFixed(2)} s of the ${r.asked.toFixed(2)} s asked `
            + 'for was dropped -- this scenario is not exercising backlog dropping');

  for (const f of r.flushes) {
    assert.ok(f.sim > 0, 'a window published with no simulated time in its numerator');
    // 2 chunks per 16.67 ms frame is 1.2x of real time, whatever the slider says.
    assert.ok(Math.abs(f.achieved - 1.2) < 0.05,
              `Sim rate ${f.achieved.toFixed(4)}x, expected 1.2x`);
    assert.ok(f.achieved < 2.0,
              `Sim rate ${f.achieved.toFixed(4)}x claims more progress than the run made`);
    // 20 ms of animal per 8 ms of stepping. Reporting *this* as the sim rate -- which is
    // what #56 is -- doubles the run's apparent progress.
    assert.ok(Math.abs(f.compute - 2.5) < 1e-6, `compute rate ${f.compute}, expected 2.5`);
    assert.ok(f.compute > 2 * f.achieved,
              'compute throughput and Sim rate agree, so one of them is the other');
  }
});
