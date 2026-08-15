# Contributing

Three documents orient every change, and reading them first is the whole onboarding:
[`docs/project-architecture.md`](docs/project-architecture.md) for the two-track rule
(reconstruction claims and digital-life results must never blur — it is the project's
founding constraint), [`NEXT.md`](NEXT.md) for what is actually being worked on, and
[`docs/runtime-parity.md`](docs/runtime-parity.md) before touching any model default.

Two working conventions with teeth:

- **Measured, then pinned.** A claim without a number is a to-do; a number without a
  reproducible home (a test, a tool docstring, an issue) is a rumour. The bug reports on
  this repository's tracker are the standard to match, and
  [`web/museum.md`](web/museum.md) shows the house style for recording defects.
- **Watch a check fail before trusting it.** `tools/audit.py` exists because seven checks
  here were once wrong before they were right.

## Running the checks yourself

**CI is paused, at the jobs rather than at the triggers.** This account's Actions minutes
are exhausted, so every push was starting a run that died in seconds having executed no
steps at all — the API reports `steps: []` with no failed step, because the job never got
a runner. A permanent red cross that says nothing about the code is worse than no signal:
a check that always fails is exactly as uninformative as one that always passes, and it
teaches you to ignore the one time it means something.

So every job in both workflows is gated on the repository variable `CI_ENABLED`. A job
whose `if` is false is skipped by the Actions service before a runner is allocated, so it
burns no minutes and reports `skipped` instead of failing. Re-enable everything by setting
`CI_ENABLED` to `true` under Settings → Secrets and variables → Actions → Variables.
Nothing else needs editing, and nothing in the jobs was weakened to make anything pass.

The triggers themselves stay live, and that is deliberate. The first version of this
change commented out `push` and `pull_request` and left only `workflow_dispatch`, which
`tests/test_ci_policy.py` rejects — a workflow that does not trigger produces no status at
all, which reads on a pull request as "nothing to report", and #44 was filed because a PR
merged with exactly that empty rollup. Removing the triggers is the defect that test exists
to detect, so it is not available as a way to stop the runs. Leaving `paths:` in place keeps
the filters declared and keeps that test able to pin them.

Until then the gates are local, and there is one command for them:

```bash
npm ci && (cd wasm && npm ci)
npm run check                  # every gate that does not rewrite a tracked file
npm run check -- --rebuild     # ...plus the ones that regenerate .model/.wasm/celegans.json
npm run check -- --python      # ...plus the ~37 minute pytest suite
npm run check -- --list        # what the gates are, and which CI step each stands in for
```

`tools/check_all.mjs` runs them in the workflows' own order, because the order inside a job
is load-bearing: `every module parses` comes before the browser check so that a syntax error
arrives as a syntax error rather than as a blank rectangle. It probes for what each gate
needs — Docker for the nginx cache boundary, Chrome for the smoke tests, a Python with numpy
— and where something is missing it **skips the gate and says so**, separately from the pass
count and again at the bottom with the reason and the fix. That is the whole design. A local
runner that folded an unrunnable gate into a green summary would be this project's most
repeated bug — a check that passes while covering less than it claims — installed in the one
place you consult to decide you are finished. `--strict` turns any skip into a non-zero exit.

Gates that rewrite tracked files are held back behind `--rebuild`, because regenerating
`web/worm.model` and `web/worm.wasm` underneath a viewer you have open, or an
`evolve.mjs` run in another terminal, hands it a torn artifact set.

`tests/test_local_checks.py` pins the runner against both workflows: a named CI step that no
gate claims fails the suite, and so does a gate claiming a step name no workflow declares.
The list is allowed to be smaller than CI only where someone wrote down why.

The individual commands, if you want one of them on its own:

```bash
node tools/check_cache_headers.mjs        # every served asset has a deliberate cache policy
node tools/check_web.mjs                  # module graph: cycles, unresolved imports, leftovers
node --test tools/sim_rate.test.mjs       # the rate readouts measure what their labels claim
node --test wasm/conform-inputs.test.mjs  # the conformance inputs are present and not stale
node --test wasm/invariants.test.mjs      # the runtime's physics guard still fires
node --test wasm/solve.test.mjs           # the runtime's resting-potential solve vs the exporter's
node --test wasm/eggs-fitness.test.mjs    # what the egg measure actually measures
node wasm/memory.mjs                      # an animal costs what the documents say it costs
node wasm/population.mjs                  # animals do not perturb one another
node tools/smoke_web.mjs                  # the viewer in a real browser, desktop and mobile
node tools/smoke_server.mjs               # the ?server transport, against a live Python model
```

The Python model suite, which is not fast — it is about 37 minutes of simulation, which is
why it never ran in CI even when CI ran:

```bash
.venv/bin/python -m pip install -e '.[test]'
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

And the pinned-anatomy gate, which checks that the committed dataset is what the pinned
inputs actually rebuild to:

```bash
.venv/bin/python tools/fetch_raw.py
.venv/bin/python tools/build_dataset.py
git diff --exit-code -- data/celegans.json
