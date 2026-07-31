# The viewer

Native ES modules. No build step, no bundler, no runtime dependencies — the browser loads
`app.js` as a module and follows the imports. That constraint is deliberate: the whole
point of the WebAssembly port is that a static file server is enough to run the animal, and
a toolchain in front of the viewer would take that back.

## Where things live

Dependencies point **down** this list and never up. That is the whole design rule; if a
change would need an arrow pointing the other way, the thing being reached for probably
belongs on `S` instead.

| module | owns | imports |
|---|---|---|
| `viewer/state.js` | `S`, `el`, `fitCanvas`, `visible`, CSS custom-property lookup | *nothing* |
| `viewer/scales.js` | sequential and diverging colour ramps | — |
| `viewer/themes.js` | the three dish palettes, the agar noise tile | state |
| `viewer/worm.js` | body geometry, and the three body painters | state, scales |
| `viewer/dish.js` | plate, grid, chemical fields, obstacles, trails, minimap, scale bar, camera transforms | state, themes, worm |
| `viewer/panels.js` | neuron grid, muscle sheet, kymograph, membrane traces, receptor bars, neuron hit-testing | state, scales |
| `viewer/stats.js` | header readouts, undulation frequency, pump lamp, dish legend | state |
| `viewer/transport.js` | the WebSocket feed, and `send()` — the command seam | state, panels, stats, dish |
| `viewer/controls.js` | every event listener; worm selector, ablation mode, tooltip | state, themes, dish, panels, stats, transport |
| `viewer/loop.js` | the local-engine read-out and `requestAnimationFrame` | state, dish, panels, stats, controls |
| `app.js` | bootstrap: pick a transport, wire, start | all of the above |
| `local.js` | the WASM engine itself — model loading, stepping budget, frame extraction | — |

## Where a fix goes

- **It looks wrong** → the renderer that owns those pixels (`dish.js`, `worm.js`,
  `panels.js`).
- **It reacts wrong** → `controls.js`. Every listener in the viewer is registered there,
  so there is exactly one place to look for "what happens when I click this".
- **The number is wrong** → `stats.js` if it is in the header, `panels.js` if it is in a
  panel, `local.js` if it came out of the simulation.
- **It differs between `?server` and the default** → `transport.js` and `loop.js` are the
  two feeds. Anything that has to behave identically in both — the camera follow, the pump
  lamp, the frequency estimate — is deliberately factored out into a single function that
  both call, because the two copies had already started to drift apart before they were.
- **It is a palette** → `themes.js` for the dish, `scales.js` for the data. The panels stay
  in the data palette in all three dish modes; they are measurements and should not be
  dressed up.

## Two transports

Default is the local WASM engine in this tab: no server, no socket. `?server` falls back to
the WebSocket feed from `python run.py`, which is still how the *Python* model is driven and
therefore the only way to watch the reference implementation rather than the port.

`send()` in `transport.js` is the seam. Everything upstream issues commands — play, rate,
poke, ablate, drop a lawn — without knowing which path is live.

## Checks

```bash
npm ci                            # puppeteer-core; CI tooling only, nothing is served
node tools/check_web.mjs          # module graph: cycles, unresolved imports, leftovers
node tools/smoke_web.mjs          # a real browser, at 1440x900, 768x1024 and 390x844
```

Both run in CI on any change under `web/` or `wasm/`
([.github/workflows/viewer.yml](../.github/workflows/viewer.yml)). The smoke test fails on
a console error, a failed request, a missing or invisible control, a layer toggle that has
gone missing at some width, horizontal overflow, a touch target under 44 px, or a control
with no accessible name — the class of breakage a no-build-step viewer is otherwise wide
open to, since nothing else ever looks at this code between typing it and someone loading
it.

It deliberately asserts nothing about what the *animal* does. Those claims belong in
`tests/` and `wasm/conform.mjs`, where they can be made precisely; a smoke test that
depended on the worm's behaviour would start failing for reasons that were not its business.
