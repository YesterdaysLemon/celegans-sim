"""Break things on purpose, and see what notices.

Every check in this repository is a claim: *if X were wrong, this would fail.* None of
those claims had ever been tested. That is not a hypothetical worry -- it is the single
most expensive failure mode this project has had, three times over:

    the conformance plate was an empty dish, so the browser's chemical fields did not
    diffuse for weeks and nothing disagreed, because a field of zeros diffuses to zeros;

    ablation had eleven branches in the runtime and zero coverage, behind a button in the
    viewer and underneath every published pharynx phenotype;

    the noisy path -- the only path anything actually runs in -- was documented as checked
    when no code checked it.

In all three the suite was green and the green meant nothing. A check that passes is
indistinguishable from a check that is correct, unless you have watched it fail.

So: apply a deliberate defect, run the battery, record who caught it, put the file back.
A defect nothing catches is a coverage hole and is the output worth having. A defect caught
by something other than the check that should own it is worth knowing too -- it usually
means the owning check is weaker than it looks and something downstream is doing its job.

The catalogue below is not a random sample. Each entry imitates a class of bug this
repository has actually shipped, which is the only defensible way to choose mutations:
mutation testing against arbitrary edits measures how brittle the code is, and mutation
testing against real historical defects measures whether you would catch them next time.

    PYTHONPATH=. .venv/bin/python tools/audit.py            # the fast battery
    PYTHONPATH=. .venv/bin/python tools/audit.py --slow     # include the pytest suite
    PYTHONPATH=. .venv/bin/python tools/audit.py --only egl # a subset, by name fragment
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cmd, timeout=2400):
    """Run a command. Returns (ok, tail-of-output)."""
    env = dict(os.environ, PYTHONPATH=ROOT)
    try:
        p = subprocess.run(cmd, shell=True, cwd=ROOT, env=env, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired:
        return False, "TIMED OUT"
    out = p.stdout.decode("utf8", "replace").strip().splitlines()
    return p.returncode == 0, (out[-1] if out else "")


VENV = ".venv/bin/python"


# --------------------------------------------------------------------------- checks ---
# `rebuild` says what has to happen before a check is meaningful, and the ordering here is
# the one that cost an hour once: the reference has to be regenerated whenever the *Python*
# moves, or the port is measured against a model that no longer exists.

def _conform(rebuild):
    if rebuild == "full":
        ok, msg = sh("%s tools/export_model.py" % VENV)
        if not ok:
            return False, "export failed: " + msg
    if rebuild in ("full", "asc"):
        ok, msg = sh("cd wasm && npx asc assembly/index.ts --target release")
        if not ok:
            return False, "compile failed: " + msg
    # Regenerated every time. A stale reference does not weaken this check, it inverts it.
    ok, msg = sh("%s tools/conform.py > web/conform.json" % VENV)
    if not ok:
        return False, "reference failed: " + msg
    return sh("node wasm/conform.mjs")


CHECKS = {
    "graph":  lambda rb: sh("node tools/check_web.mjs"),
    "viewer": lambda rb: sh("node tools/smoke_web.mjs"),
    "conform": _conform,
    "tests":  lambda rb: sh("%s -m pytest tests/ -x -q" % VENV),
}
FAST = ["graph", "viewer", "conform"]
SLOW = FAST + ["tests"]

# `tests` is the Python model's owning check and it costs twenty-six minutes. Running it
# against a stylesheet edit to establish that pytest does not parse CSS is not a finding,
# it is an afternoon. So it runs only where it could plausibly fire -- and "plausibly" is
# decided by which tree the mutation lands in, not by what I expect, so a Python change I
# wrongly believed inert is still put in front of it.
TESTS_APPLY_TO = ("worm/", "tools/", "data/")


def battery_for(mut, battery):
    if "tests" not in battery:
        return battery
    if mut["file"].startswith(TESTS_APPLY_TO):
        return battery
    return [c for c in battery if c != "tests"]


# ------------------------------------------------------------------------ mutations ---
# find/replace pairs, applied to a single file. `expect` is the prediction: which checks
# *should* notice. Writing the prediction down before running is the point -- an audit that
# only records what happened cannot tell you that a check is weaker than you believed.

MUTATIONS = [
    dict(name="wasm/frozen-plate", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="the real bug: World.step was never ported, so the browser's chemistry "
                  "never diffused. Invisible for weeks because the conformance dish was empty.",
         find="    world.stepFields(G.DT);\n  }\n}\nexport function ptrAct",
         repl="  }\n}\nexport function ptrAct",
         expect=["conform"]),

    dict(name="wasm/release-unmasked", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="an ablated cell still releasing transmitter. Aimed first at the mask in "
                  "the release loop, which the audit could not catch -- correctly, because a "
                  "dead cell's sv is zeroed after every solve and never updated, so that "
                  "mask is redundant and removing it is an equivalent mutant. This targets "
                  "the line that actually enforces it.",
         # Both sites, not one. A dead cell's release is zeroed in two places -- at the
         # moment of ablation and again after every solve -- and they are redundant with
         # each other, so removing either alone changes nothing and the audit rightly could
         # not catch it. Twice this mutation was aimed at a single line and twice the miss
         # was the mutation's fault, not the coverage's. Breaking every site that provides
         # the behaviour is the question worth asking.
         edits=[("        unchecked(this.sv[i] = 0.0);\n        continue;",
                 "        continue;"),
                ("      unchecked(wm.sv[i] = 0.0);", "      // cleared elsewhere")],
         find=None, repl=None,
         expect=["conform"]),

    dict(name="wasm/modulator-unmasked", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="the modulator ablation bug, reintroduced: a dead source dropped from "
                  "the average instead of contributing resting release.",
         find="      if (this.anyDead && !unchecked(this.alive[c])) continue;   // deviation of zero\n      acc += unchecked(this.act[c]) - 0.5;\n    }\n    const target = acc / <f64>len;",
         repl="      if (this.anyDead && !unchecked(this.alive[c])) continue;\n      acc += unchecked(this.act[c]) - 0.5;\n    }\n    const target = acc / <f64>len;  // denominator unchanged\n    if (false) {}",
         expect=[]),      # deliberately inert: a control, see the report

    dict(name="wasm/gap-iters", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="a subtle numeric divergence rather than a structural one -- the kind a "
                  "'looks like a worm and wriggles' eyeball would never catch.",
         find="    for (let it = 0; it < G.GAP_ITERS; it++) {",
         repl="    for (let it = 0; it < G.GAP_ITERS - 1; it++) {",
         expect=["conform"]),

    dict(name="wasm/egg-resource", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="a slow state ported wrong. Three of egg-laying's four variables are "
                  "slow, so this looks fine for minutes.",
         find="      this.eglResource -= G.EGL_RESOURCE_COST;",
         repl="      this.eglResource -= G.EGL_RESOURCE_COST * 0.5;",
         expect=["conform"]),

    dict(name="py/proprio-reach", file="worm/params.py", rebuild="full",
         imitates="a gait-critical model constant moved. The wave should not survive it.",
         # Was proprio_reach_food, which the audit showed nothing caught -- correctly, since
         # that is the ON-FOOD reach and every gait test runs on a bare plate. The mutation
         # was wrong, not the coverage. This is the constant the tests actually exercise.
         find="    proprio_reach: float = 0.16",
         repl="    proprio_reach: float = 0.04",
         expect=["tests"]),

    dict(name="viewer/hidden-layers", file="web/style.css", rebuild=None,
         imitates="the real regression the smoke test was written for: layer toggles "
                  "display:none below 1080px, removing the only way to see the fields.",
         find="  .chips { flex-direction: row; flex-wrap: wrap; align-items: center; }",
         repl="  .chips { display: none; }",
         expect=["viewer"]),

    dict(name="viewer/broken-import", file="web/viewer/controls.js", rebuild=None,
         imitates="a renamed export. With no build step this is a blank page at runtime "
                  "and nothing at all before it.",
         find="import { buildLegend } from './stats.js';",
         repl="import { buildLegendd } from './stats.js';",
         expect=["graph", "viewer"]),

    dict(name="viewer/unnamed-control", file="web/index.html", rebuild=None,
         imitates="an accessible name dropped -- the '+' and '-' pairs were both literally "
                  "'+' and '-' before anyone looked.",
         find='<button id="b-worm-add" aria-label="Add a worm to the dish">+</button>',
         repl='<button id="b-worm-add">+</button>',
         expect=["viewer"]),

    dict(name="viewer/renderer-throws", file="web/viewer/panels.js", rebuild=None,
         imitates="a renderer that dies mid-frame. The dish keeps drawing, so the page "
                  "looks alive while a panel is silently dead.",
         find="export function drawMuscles() {",
         repl="export function drawMuscles() {\n  if (S.frame) throw new Error('audit');",
         expect=["viewer"]),
]


# --------------------------------------------------------------------------- driver ---

def apply(mut):
    """Apply one or more find/replace pairs. Several, because a defect is not always one
    line: two sites that clear the same state are redundant with each other, and removing
    either alone is an equivalent mutant. Asking whether the *behaviour* is covered means
    breaking every site that provides it."""
    path = os.path.join(ROOT, mut["file"])
    original = io.open(path, encoding="utf8").read()
    edits = mut.get("edits") or [(mut["find"], mut["repl"])]
    text = original
    for find, repl in edits:
        if find not in text:
            return None, "PATTERN NOT FOUND -- the mutation is stale, not the code"
        text = text.replace(find, repl, 1)
    io.open(path, "w", encoding="utf8").write(text)
    return original, None


def restore(mut, original):
    if original is not None:
        io.open(os.path.join(ROOT, mut["file"]), "w", encoding="utf8").write(original)


def main(argv):
    slow = "--slow" in argv
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    battery = SLOW if slow else FAST

    ok, _ = sh("git diff --quiet && git diff --cached --quiet")
    if not ok:
        print("working tree is dirty. This tool edits files in place and puts them back;\n"
              "refusing to run where a failure would be indistinguishable from your work.",
              file=sys.stderr)
        return 2

    muts = [m for m in MUTATIONS if not only or only in m["name"]]
    print("COVERAGE AUDIT -- %d deliberate defects against %s\n"
          % (len(muts), ", ".join(battery)))
    print("  Each entry imitates a class of bug this repository has actually shipped.")
    print("  `expect` was written down before the run; a check that misses what it was")
    print("  built for is the finding, and so is a defect nothing catches at all.\n")

    # A clean baseline, or every result below is meaningless.
    print("  baseline (no mutation):", end=" ", flush=True)
    base = {}
    for c in battery:
        good, msg = CHECKS[c](None)
        base[c] = good
        print("%s=%s" % (c, "pass" if good else "FAIL"), end=" ", flush=True)
    print()
    if not all(base.values()):
        print("\n  baseline is not green. Fix that first -- a red check cannot catch anything.",
              file=sys.stderr)
        return 2

    rows, misses, surprises, controls_ok = [], [], [], []
    for m in muts:
        t0 = time.time()
        print("\n  %-24s %s" % (m["name"], m["imitates"][:70]))
        original, err = apply(m)
        if err:
            print("      %s" % err)
            rows.append((m, {}, err))
            continue
        caught = {}
        mine = battery_for(m, battery)
        try:
            for c in mine:
                good, msg = CHECKS[c](m["rebuild"])
                caught[c] = not good
                print("      %-8s %s" % (c, "CAUGHT" if not good else "missed"), flush=True)
        finally:
            restore(m, original)

        who = [c for c in mine if caught.get(c)]
        # `expect=[]` marks a deliberately inert mutation -- a control, there to show the
        # battery does not fire at random. Not catching it is the correct result, so it is
        # not a hole, and counting it as one would train the reader to ignore the list.
        if not who and m["expect"]:
            misses.append(m)
        if not who and not m["expect"]:
            controls_ok.append(m)
        if who and not m["expect"]:
            surprises.append((m, who[0], "control fired -- the battery is reacting to noise"))
        for c in m["expect"]:
            if c in mine and not caught.get(c):
                surprises.append((m, c, "expected to catch it and did not"))
        for c in who:
            if c not in m["expect"] and m["expect"]:
                surprises.append((m, c, "caught it unexpectedly"))
        rows.append((m, caught, None))
        print("      -> %s   (%.0fs)" % (", ".join(who) or "NOTHING CAUGHT IT", time.time() - t0))

    # Put everything back, belt and braces: a half-applied mutation left on disk would be
    # a far worse bug than any this tool is looking for.
    sh("git checkout -- .")
    sh("cd wasm && npx asc assembly/index.ts --target release")

    print("\n\n  %-24s %s" % ("defect", "  ".join("%-8s" % c for c in battery)))
    for m, caught, err in rows:
        if err:
            print("  %-24s  %s" % (m["name"], err))
            continue
        print("  %-24s %s" % (m["name"],
              "  ".join("%-8s" % ("CAUGHT" if caught.get(c) else "-") for c in battery)))

    print()
    if misses:
        print("  %d DEFECT(S) NOTHING CAUGHT -- these are coverage holes:" % len(misses))
        for m in misses:
            print("    %-24s %s" % (m["name"], m["imitates"]))
    else:
        print("  Every defect was caught by something.")
    if controls_ok:
        print("  %d control(s) correctly ignored: %s"
              % (len(controls_ok), ", ".join(m["name"] for m in controls_ok)))
    if surprises:
        print("\n  %d surprise(s) against the written-down prediction:" % len(surprises))
        for m, c, what in surprises:
            print("    %-24s %-8s %s" % (m["name"], c, what))
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
