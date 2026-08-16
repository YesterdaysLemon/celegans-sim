"""The local check runner, pinned against the workflows it stands in for.

`tools/check_all.mjs` is the local equivalent of the hosted gates. That makes it the thing
you consult to answer "am I done" before a push, which makes its coverage a correctness
property rather than a convenience.

This is the test for the failure mode NEXT.md names as this project's most repeated bug:
a check that runs, passes, and covers less than its own comment claims. Three of the four
holes `tools/audit.py` found on its first run were that shape, including an egg-laying
conformance comparison that printed a perfect ``0.000e+0`` from comparing zero fields. A
local runner that prints a green summary having silently dropped the browser gate would be
the same bug one layer up, and the layer that hides the others.

So: every *named* step in any workflow must be claimed by some gate in `check_all.mjs`,
or be named in ``NOT_A_GATE`` below with the reason it is not one. The allowlist is
deliberate and per-step. It means that adding a CI step the local runner cannot do is a
decision somebody writes down, rather than a thing that happens.

Two directions are checked, because they fail differently:

  * a CI step no gate claims is **missing coverage** -- the runner is quietly smaller than
    CI, which is the bug above;
  * a gate claiming a step name that no workflow contains is a **stale gate** -- usually a
    renamed CI step, which leaves the runner running something under a label that no longer
    means what it says.

There is no PyYAML in `requirements.txt` and `tests/test_ci_policy.py` already declined to
add one for exactly this kind of parsing, so both files are read directly. That parser is
the weak point -- one that quietly returns nothing turns every assertion here into a
tautology -- so it refuses to return an empty result, and `test_the_parsers_are_not_lying`
pins its output against the literal text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RUNNER = ROOT / "tools" / "check_all.mjs"


# Named CI steps that are deliberately not gates, each with the reason. Setup steps that
# GitHub expresses as actions rather than as `run:` -- checkout, setup-python, setup-node --
# carry no `name:` at all and so never reach this list.
NOT_A_GATE = {
    "build the cost-aware test matrix":
        "discovery, not a gate: it validates and emits the simulation shards for the job "
        "that follows. Locally the same helper validates them before running pytest.",
    "snapshot the committed model/runtime set":
        "setup for the two comparison gates, not a check of its own. The local runner "
        "folds it into `model-artifacts`, because locally the snapshot has to happen "
        "before anything is overwritten rather than in a fresh checkout.",
    "prove this tree has all required CI coverage":
        "release coordination, not a code gate: it reads GitHub's workflow and production "
        "deployment history and therefore has no truthful offline equivalent.",
    "refuse a superseded release under the production lock":
        "release-state guard, not a code gate: it compares the queued SHA with live main "
        "only after GitHub grants the production concurrency lock.",
}


# --------------------------------------------------------------------------- the parsers
def _step_names(text: str) -> list[str]:
    """Every step label in a workflow, in file order.

    Four kinds of ``name:`` appear in these files and only one of them is a step, so this
    classifies by indentation rather than by the leading dash:

      * indent 0 -- the workflow's own name;
      * indent 4, no dash -- a job label. A job is not a step and has no command to stand
        in for;
      * directly below ``environment:`` -- a deployment-environment label;
      * anything deeper -- a step. Usually ``      - name:``, but not always: python.yml's
        discovery step leads with ``- id: files`` and puts ``name:`` on the next line at
        indent 8. Matching only the dashed form silently missed it, which is exactly the
        shape of bug this file is about, so it is worth the extra rule.

    A name containing ``${{ }}`` is a matrix label rather than a fixed step, and is dropped.
    """
    names = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(-\s+)?name:\s*(.+?)\s*$", line)
        if not match:
            continue
        indent, dashed = len(match.group(1)), match.group(2) is not None
        if indent == 0 or (indent == 4 and not dashed):
            continue
        if index and lines[index - 1].strip() == "environment:":
            continue
        name = match.group(3).strip().strip("'\"")
        if "${{" in name:
            continue
        names.append(name)
    return names


def _covered_steps(text: str) -> list[str]:
    """Every string inside a ``covers: [...]`` array in the runner, in file order.

    Walks from each ``covers:`` to its matching bracket rather than matching the contents
    with one regex, because the arrays wrap across lines. An unterminated array raises
    instead of being skipped -- a gate this misses is a gate this test would then declare
    uncovered, which is a confusing way to fail.
    """
    out = []
    for match in re.finditer(r"covers:\s*\[", text):
        start = text.index("[", match.start())
        depth, end = 0, None
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            raise AssertionError("unterminated covers: [ ... ] near offset %d" % start)
        quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", text[start + 1:end])
        out.extend(single or double for single, double in quoted)
    return out


def _gate_ids(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\s*id:\s*'([^']+)'", text, re.MULTILINE)]


@pytest.fixture(scope="module")
def workflow_steps() -> dict[str, str]:
    """Step name -> the workflow file it came from."""
    steps: dict[str, str] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        for name in _step_names(wf.read_text()):
            steps.setdefault(name, wf.name)
    assert steps, "parsed no step names out of any workflow; the parser is broken"
    return steps


@pytest.fixture(scope="module")
def runner_text() -> str:
    assert RUNNER.exists(), f"{RUNNER} is missing; the local check runner is the thing under test"
    return RUNNER.read_text()


# ----------------------------------------------------------------------------- the parser
def test_the_parsers_are_not_lying(workflow_steps, runner_text):
    """Pin both parsers against literal text, so neither can pass by returning nothing."""
    # Steps that are definitely in the workflows, spelled out here rather than derived.
    for known in ("every module parses",
                  "browser smoke test",
                  "the population behaves as a population",
                  "committed WASM matches its committed generated layout"):
        assert known in workflow_steps, f"the workflow parser missed {known!r}"

    # Job names must not leak in as steps.
    for job_label in ("static checks and browser smoke test",
                      "the port still reproduces the Python",
                      "discover Python test targets",
                      "production"):
        assert job_label not in workflow_steps, (
            f"{job_label!r} is a job name, not a step; the parser is matching too broadly"
        )

    covered = _covered_steps(runner_text)
    assert len(covered) >= 10, f"the runner parser found only {len(covered)} covered steps"
    assert "every module parses" in covered

    ids = _gate_ids(runner_text)
    assert len(ids) == len(set(ids)), f"duplicate gate ids in the runner: {ids}"


# -------------------------------------------------------------------------- the two directions
def test_every_named_ci_step_is_claimed_by_a_gate(workflow_steps, runner_text):
    """Missing coverage: a CI step the local runner silently does not do."""
    covered = set(_covered_steps(runner_text))
    unclaimed = {
        name: wf for name, wf in workflow_steps.items()
        if name not in covered and name not in NOT_A_GATE
    }
    assert not unclaimed, (
        "these CI steps have no gate in tools/check_all.mjs, so running it locally covers "
        "less than CI does and says nothing about them:\n"
        + "".join(f"  - {name!r}  ({wf})\n" for name, wf in sorted(unclaimed.items()))
        + "Add a gate, or add the step to NOT_A_GATE in this file with the reason."
    )


def test_no_gate_claims_a_step_that_no_longer_exists(workflow_steps, runner_text):
    """Stale gate: usually a renamed CI step, leaving a gate labelled with a dead name."""
    stale = sorted(set(_covered_steps(runner_text)) - set(workflow_steps))
    assert not stale, (
        "tools/check_all.mjs claims to cover CI steps that no workflow declares:\n"
        + "".join(f"  - {name!r}\n" for name in stale)
        + "A renamed CI step needs its `covers:` entry renamed to match, character for "
          "character, or the gate is running under a label that no longer means anything."
    )


def test_the_allowlist_only_excuses_steps_that_exist(workflow_steps):
    """An allowlist entry for a step CI no longer has is an excuse outliving its subject."""
    dead = sorted(set(NOT_A_GATE) - set(workflow_steps))
    assert not dead, (
        f"NOT_A_GATE excuses steps no workflow declares any more: {dead}. "
        "Delete the entry; leaving it makes the allowlist read as larger than it is."
    )


def test_a_skip_is_reported_separately_from_a_pass(runner_text):
    """The property the runner exists for, asserted rather than trusted to a comment.

    A local runner whose skips are indistinguishable from passes is worse than no runner,
    because it is the thing you consult to decide you are finished. Checked structurally --
    the summary counts skips in their own bucket, and reprints them afterwards.
    """
    assert "skipped.length" in runner_text, "the summary does not count skips at all"
    assert "A SKIP IS NOT A PASS" in runner_text, (
        "the runner no longer reprints skipped gates as a coverage gap"
    )
    # The pass count must be built from a `pass` filter, never from "not failed".
    assert re.search(r"passed\s*=\s*results\.filter\(\(r\)\s*=>\s*r\.state\s*===\s*'pass'\)",
                     runner_text), (
        "the pass count is not filtered on state === 'pass'; if it is computed as "
        "'everything that did not fail', a skipped gate counts as a pass"
    )
