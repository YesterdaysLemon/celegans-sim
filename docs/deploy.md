# Running it, serving it, watching it

How the browser runtime works, how to put it on a server, and what the viewer gives
you. Moved intact from the README when the repository went public.

## It runs in the browser

The animal itself is compiled to WebAssembly, so the page needs no simulation server: open
it and you get *your own* worm — two of them, in fact, sharing a dish. `wasm/README.md` has
the details; the short version is that **Python is the compiler and WebAssembly is the
runtime**. Everything expensive that happens once at construction stays in Python and is
exported as a block of arrays; the WASM implements only the step functions.

`tools/conform.py` and `wasm/conform.mjs` check the two implementations against each other
step by step with the noise off, in **six cases** — the mechanics alone, the whole loop on
a plate with food and a noxious drop, the same loop with seven cells ablated mid-run, the
serotonin-gated chloride channel at the coefficient `params.py` documents, the browser's
own `stepAll` path against the single-worm one, and four animals contesting one lawn
against a Python `Population`. They agree to the precision the reference file stores: 5e-13
mm on node positions, 5e-11 mV on membrane potentials, the direction gate never disagrees,
ablated cells are silent rather than merely quiet, and four animals contesting one lawn
agree on what each of them ate and on what is left in the cells they were eating it from.
The Docker build runs that check and **fails if the port has drifted**.

The sixth case disagreed the first time it ran, and **the model moved rather than the
port**. The two settled contested feeding onto identical allocations and then took the food
out of different cells: 7.5e-04 apart on the plate at the moment it happened, 4.7e-02 mV on
membrane potentials four seconds later. Python spread each withdrawal with a linear program
so that every cell in the union lost the same fraction; the runtime, which has to settle
this at 2 kHz inside a browser tab and cannot run a linear program, grazes each animal's
neighbourhood proportionally and lets shared ground be grazed twice. Two animals eating the
same bacteria really do take more out of the ground they share, so `World.eat_batch` now
runs the runtime's rule — at the cost of the maximum-throughput and max-min-fairness
guarantees the linear program bought. `wasm/README.md` has the account.

Five of those six cases exist because a coverage audit found the earlier ones passing
without covering anything. `tools/audit.py` breaks things on purpose and reports which
check notices; `wasm/README.md` has the account.

One worm runs at **2.36× real time** in the browser and two at 1.20× — faster than the
numpy it was ported from — and the whole animal is **~55 kB gzipped**. Both numbers come
from storing the connectome sparsely: every matrix is between 0.3% and 2.5% non-zero, so
the dense version was doing 556,000 mul-adds a step to accumulate about 4,500 that were
not zero.

```bash
docker build -t celegans-sim . && docker run --rm -p 8080:8080 celegans-sim
```

### Putting it on a server

**There is no backend to deploy.** The image is `nginx:alpine` with a directory of static
files in it, because the animal runs in the visitor's browser. One instance serves as many
people as the bandwidth allows, the CPU cost is theirs rather than yours, and there is no
database, no queue, no session and nothing to scale. A 1 GB VPS is generous.

The build is two stages and the first one is the reason to use it rather than copying `web/`
somewhere by hand. It regenerates `worm.model` from the Python and recompiles `worm.wasm`
from source, then runs the conformance check and **fails the build if the port has drifted**
from the model. A container that quietly shipped a diverged animal would be worse than no
container. It also runs `tools/manifest.py`, which content-hashes the assets so the cache
policy below is safe.

```bash
docker run -d --restart=unless-stopped -p 127.0.0.1:8080:8080 --name celegans celegans-sim
```

Bind to loopback and put your own TLS terminator in front — Caddy, Traefik, or nginx with
certbot; anything that speaks HTTP to an upstream will do. Two things to keep in mind if you
do put a proxy in front of it:

- **Do not let the proxy rewrite `Content-Type`.** `docker/nginx.conf` has a long comment
  about why, and it is the sharpest failure mode this repo has had in production shape: a
  browser refuses an ES module served with a non-JavaScript MIME type, so the page can fail
  before it runs a line of its own code.
- **Keep the caching split.** Hashed assets are immutable and cached hard; the viewer's
  source modules are deliberately unhashed — there is no build step to rewrite their import
  specifiers — so they are revalidated instead. That is what stops a redeploy serving
  modules from two different commits at once. `npm run check` exercises the real nginx
  config against that policy, in a container, rather than trusting the local dev server.

Redeploying is `docker build` and `docker run` again; there is no state to migrate, and the
only thing that changes for a visitor is which files their browser revalidates.


## The viewer

`web/` is a set of native ES modules — no build step, no bundler, no dependencies. There
are **two ways to feed it**, and the default is the one with no server in it:

- **Local (default).** The animal runs in the tab. `web/local.js` loads `worm.wasm` and
  `worm.model`, steps the WebAssembly against a wall-clock budget and reads the state
  straight out of linear memory. No socket, no backend, no round trip — a static file
  server is the whole deployment. See [wasm/README.md](../wasm/README.md).
- **`?server`.** The original WebSocket feed from `python run.py`: packed float32 at 30 Hz,
  302 voltages, 302 activations, 95 muscle tensions, the body outline, the curvature
  profile and the pharyngeal pump, about 3 kB a frame, with the chemical fields going
  separately as downsampled 8-bit images every two seconds. This is still how the *Python*
  model is driven, so it is the only way to watch the reference implementation rather than
  the port.

Everything downstream of `send()` is shared: the two paths differ in where the numbers come
from and in nothing else. [web/README.md](../web/README.md) has the module map.

**The viewer has two modes**, and each binds a dish painter to a chrome language — a
different claim about what you are looking at, spoken consistently from plate to panel:

- **Dark** — this is data, on an instrument. Near-black plate, a fixed grid, the body
  tinted by signed curvature so the travelling wave reads as a wave rather than a wiggle;
  around it, terminal chrome — monospace, phosphor-green actives, corner-ticked panels.
- **Light** — this is an animal, in a paper. Grainy warm agar with a vignette, a
  translucent amber body with a gut line, a specular flank, a contact shadow, the pharynx
  a paler bulb behind the nose; around it, paper chrome — serif, ink rules, small-caps
  panel titles.

The *data* does not change with the mode: series colours, the diverging curvature ramp
and the sequential activation ramp are identical in both, because a measurement should
not change meaning with the decor. The choice persists in the browser and the museum page
follows it. (A third look, cartoon, was retired when the modes landed.)

All three chemical fields draw **in the dish** and composite by weight rather than
painting over one another, so a lawn sitting inside an attractant gradient shows as both —
and the two things the animal is actually choosing between, somewhere to sit and something
to avoid, can finally be seen at the same time. Each layer is a chip that carries its own
swatch, so the legend is the control.

The camera **follows** the animal with a deadzone, or you can **drag to pan** and it
detaches by itself; scroll or the zoom buttons change the window, and the minimap shows
where that window sits in the dish. Every side panel collapses from its header, and the
whole rail folds away for a full-width view of the animal. `f` toggles follow, `h` hides
the rail, `1`/`2` switch the mode.

Four measurement views: all 302 neurons ordered head to tail and coloured by activation,
hover for identity and click to plot; the four muscle quadrants; a scrolling curvature
kymograph; live membrane traces. Transport controls change the medium under the animal
live, poke it at either end, and ablate neurons by clicking them. A lamp in the header
flashes once per pharyngeal pump — at 250 a minute on food that is a flicker, and off
food an occasional blink.

And you can reach into the dish. A **dropper** on the plate chooses what a double-click
puts down — a bacterial lawn, or a dose of repellent that diffuses, decays and blows
around like anything else on the plate. **Shift-drag an animal** to pick it up with the
tweezers and put it down somewhere else: the runtime translates the pose rigidly, so
gait phase and every neuron ride along — moving the animal, not resetting it. On the
arena dish a **Weather** slider scales the wind live, from a still room to a gusty one
(all three are local-engine tools; the `?server` feed keeps plain lawn-dropping).

**And the transport bar scrubs.** The media-player metaphor at the top of this file was
missing the one control that makes it one, because there was no history to scrub — every
frame was drawn once and dropped. `viewer/history.js` keeps a ring of past frames and the
slider walks it; dragging pauses, and dragging to the right-hand end resumes live.

Two things about that ring are worth stating because both were bugs first. It **copies**:
`LocalEngine.frame(i)` hands out `act`, `V`, `tension` and `kappa` as views into WASM linear
memory, so storing those objects would hold thousands of aliases of one live animal, and
`memory.grow` detaches them outright. And its budget is in **bytes, not frames** — a frame
costs **3,376 B per animal**, measured, so a fixed frame count would quietly mean a 27 MB
ring on a populated plate. 24 MB buys about 7,100 frames with one animal and about 930 with
eight, and the readout says how many seconds are actually held.

## Layout

## Layout

```
worm/params.py      every tunable constant, with its provenance and its unit
worm/dataset.py     loads the built connectome into numpy
worm/nervous.py     302 graded neurons
worm/muscle.py      95 body-wall muscle cells and their bending moment
worm/body.py        the elastica and resistive force theory
worm/world.py       dish, food, chemical fields, obstacles
worm/senses.py      sensory transduction and proprioception
worm/engine.py      the closed loop
worm/pharynx.py     feeding: a myogenic pump the pharyngeal neurons modulate
worm/server.py      WebSocket telemetry and static file serving
tools/build_dataset.py  raw anatomy -> validated dataset, assertion-heavy
tools/kymo.py           ASCII kymograph — the fastest way to see what the body is doing
tools/diagnose_loop.py  frequency, wavelength, phase and antagonism metrics
tools/command_probe.py  what each input is worth to the forward/backward decision
tools/command_sweep.py  behavioural and locomotor scores side by side, for the command layer
tools/ethogram.py       reversal rate, run lengths and reorientation, off food and on
tools/assays.py         chemotaxis, aerotaxis, thermotaxis, nociception
tools/calibrate_body.py mechanics checks, independent of the biology
tools/timestep_convergence.py  is the gait converged at the step size it runs at?
tools/head_mode.py      which of the head loop's limit cycles the animal lands in, and why
tools/habituation.py    tap habituation — decrement, interval dependence, recovery
tools/loop_phase.py     open the head loop and measure each stage's gain and phase
tools/wave_speed.py     what sets the wavelength and the frequency
tools/body_oscillator.py  can the body carry the rhythm instead of the head?
tools/head_circuit.py   lumped against distributed head reflex, scored on the wave
tools/thrust.py         what speed the mechanics allow, and what the circuit collects
tools/ase_opponency.py  which way round the ON and OFF chemosensors should push
tools/omega.py          can the omega turn be bought by amplifying RIV? (no, and why)
tools/pharynx.py        pump rate on and off food, and five ablation phenotypes
tools/stats.py          bootstrap intervals, and the paired comparison behind compare.py
tools/compare.py        A/B two configurations on identical seeds, with paired intervals
tools/scorecard.py      every headline number at once, across seeds, in three media
tools/export_model.py   freeze the model into web/worm.model + the runtime's constants
tools/conform.py        reference trajectories the WebAssembly port is checked against
tools/parity.py         the same two implementations compared statistically, noise ON
wasm/trajectories.mjs   raw trajectories out of the browser runtime, for parity.py
tools/check_web.mjs     the viewer's module graph: cycles, unresolved imports, leftovers
tools/smoke_web.mjs     the viewer in a real browser, desktop and mobile
tools/smoke_server.mjs  the ?server transport, against a live Python model
tools/check_cache_headers.mjs  every served asset has a deliberate cache policy
tools/audit.py          break each check on purpose and see which one notices
tools/self_contact.py   does the body pass through itself, and when would it start
tools/moment_ceiling.py can the mechanics make the turn the circuit cannot? (no)
tools/turn_scaling.py   what sets that ceiling: the medium, or the body? (neither)
worm/egglaying.py       vulval muscle, the uterus, and the resource that clusters it
tools/egglaying.py      rate, retention, the HSN and serotonin phenotypes
wasm/egglaying.mjs      the hour-long clustering runs, on the runtime
wasm/population.mjs     the invariants that exist only when several animals share a plate
wasm/memory.mjs         what an animal costs, measured, against what the documents claim
web/app.js              viewer bootstrap; the modules it composes are in web/viewer/
web/local.js            the WebAssembly engine: model loading, stepping budget, frames
wasm/assembly/index.ts  the runtime — the same model, in the browser
```
