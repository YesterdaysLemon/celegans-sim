"""The workflows' path filters, checked against the files they are supposed to guard.

Every other check in this repository asks whether the model is right. This one asks
whether the checks *run*, which is a different question and has been answered wrong
before: #44 was filed because PR #23 changed tests, Python tools, `worm/params.py` and
`worm/senses.py` and merged with an empty status-check rollup. The filters were widened
in #62, and nothing then pinned them, so the next edit that widens the tree past the
filters fails exactly the same way and just as silently.

Silently is the operative word. A workflow that does not run does not go red; it produces
no status at all, which reads on the pull-request page as "nothing to report". That makes
this the one class of defect in the project where the absence of a signal *is* the defect,
and the only way to catch it is to assert the trigger policy directly.

Two assertions, and they fail for different reasons:

  * representative edits under `worm/`, `tests/`, `data/` and `tools/` must schedule the
    workflows that would actually exercise them -- the acceptance criterion left open on
    #44;
  * and every tracked file must be claimed by some workflow, or be named here as needing
    none. A per-file allowlist is deliberate. It means adding a file that nothing checks
    is a decision someone writes down rather than a thing that happens.

There is no PyYAML in `requirements.txt` and one policy test is not worth a dependency, so
the `paths:` blocks are read directly. That parser is the weak point -- a parser that
quietly returns nothing turns every assertion below into a tautology -- so it refuses to
return an empty or partial result and `test_the_parser_is_not_lying` pins its output
against the literal text of the files.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

PYTHON_WF = "python.yml"
VIEWER_WF = "viewer.yml"


# --------------------------------------------------------------------------- the parser
def _path_blocks(text: str) -> list[list[str]]:
    """Every `paths: [...]` flow sequence in a workflow, as lists of literal globs.

    The blocks are flow sequences that wrap across lines, so this walks from each
    `paths:` to its closing bracket and pulls the quoted entries out of the span. It
    handles exactly what these two files use and nothing else; anything it cannot account
    for raises rather than being skipped, because a filter this misses is a filter this
    test would then declare fine.
    """
    blocks = []
    for match in re.finditer(r"^\s*paths:\s*\[", text, re.MULTILINE):
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
            raise AssertionError("unterminated paths: [ ... ] near offset %d" % start)
        span = text[start + 1:end]
        globs = re.findall(r"'([^']*)'", span)
        # Every non-space, non-comma character in the span has to belong to one of the
        # quoted entries. If it does not, the block contains something this parser does
        # not model -- a double-quoted entry, an anchor, a comment -- and reading it as
        # "just the single-quoted ones" would silently drop filters.
        residue = re.sub(r"'[^']*'", "", span)
        leftover = residue.replace(",", "").split()
        if leftover:
            raise AssertionError(
                "paths: block contains unparsed text %r; this parser models only "
                "single-quoted flow sequences" % (" ".join(leftover),))
        if not globs:
            raise AssertionError("paths: block parsed to nothing near offset %d" % start)
        blocks.append(globs)
    return blocks


def workflow_globs(name: str) -> list[str]:
    """The path filter for a workflow, with push and pull_request required to agree.

    They are separate keys in the file and are currently duplicated by hand, which is the
    kind of duplication that drifts. A workflow that gates pull requests on a narrower set
    than it gates pushes is a hole shaped exactly like #44.
    """
    text = (WORKFLOWS / name).read_text()
    blocks = _path_blocks(text)
    assert len(blocks) == 2, (
        "%s: expected a paths: filter under both push and pull_request, found %d"
        % (name, len(blocks)))
    assert blocks[0] == blocks[1], (
        "%s: push and pull_request path filters differ; the pull_request side is the one "
        "that gates merges.\n  only in push: %r\n  only in pull_request: %r"
        % (name, sorted(set(blocks[0]) - set(blocks[1])),
           sorted(set(blocks[1]) - set(blocks[0]))))
    return blocks[0]


# ---------------------------------------------------------------------- glob evaluation
def _to_regex(glob: str) -> re.Pattern:
    """GitHub's filter-pattern syntax, restricted to what these workflows actually use.

    `**` spans separators, `*` and `?` do not. The `!` negation and `+` forms are real
    GitHub syntax and are *not* implemented; a filter using one would be evaluated wrongly
    rather than approximately, so they raise.
    """
    if glob.startswith("!") or "+" in glob:
        raise AssertionError(
            "filter %r uses GitHub syntax this evaluator does not implement" % glob)
    out, i = [], 0
    while i < len(glob):
        c = glob[i]
        if c == "*":
            if glob[i + 1:i + 2] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out) + r"\Z")


def scheduled_by(path: str, name: str) -> bool:
    return any(_to_regex(g).match(path) for g in workflow_globs(name))


# ------------------------------------------------------------------------------- checks
def test_the_parser_is_not_lying():
    """Pin the parser's output against the literal text, so it cannot fail open.

    Everything else here is `assert scheduled_by(...)`, and a parser that returned an
    over-wide filter -- or that read the same block twice -- would make all of it pass.
    These are transcribed from the workflow files by hand on purpose.
    """
    py = workflow_globs(PYTHON_WF)
    assert py == ['worm/**', 'tests/**', 'tools/*.py', 'tools/check_all.mjs', 'data/**',
                  'pyproject.toml', 'requirements*.txt', 'web/worm.model', 'web/worm.wasm',
                  'wasm/assembly/**', 'wasm/asconfig.json', 'wasm/package*.json',
                  '.github/workflows/python.yml'], py

    viewer = workflow_globs(VIEWER_WF)
    assert viewer == ['web/**', 'wasm/**', 'worm/server.py', 'run.py', 'requirements.txt',
                      'docker/nginx.conf', 'tools/check_cache_headers.mjs',
                      'tools/check_web.mjs', 'tools/smoke_server.mjs',
                      'tools/smoke_web.mjs', 'tools/sim_rate.test.mjs', 'package.json',
                      'package-lock.json', '.github/workflows/viewer.yml'], viewer


@pytest.mark.parametrize("glob,path,expected", [
    ("worm/**", "worm/body.py", True),
    ("worm/**", "worm/sub/deep.py", True),          # ** spans separators
    ("worm/**", "wormy/body.py", False),
    ("tools/*.py", "tools/export_model.py", True),
    ("tools/*.py", "tools/nested/thing.py", False),  # * does not span separators
    ("tools/*.py", "tools/smoke_web.mjs", False),
    ("requirements*.txt", "requirements.txt", True),
    ("requirements*.txt", "requirements-dev.txt", True),
    ("requirements*.txt", "requirements/base.txt", False),
    ("package.json", "package-lock.json", False),   # a literal is a literal
    ("package.json", "wasm/package.json", False),   # ...and is anchored at the root
])
def test_glob_evaluator(glob, path, expected):
    """The evaluator itself, since every other assertion is expressed through it."""
    assert bool(_to_regex(glob).match(path)) is expected


# Each entry is a file an edit could plausibly land in, and the workflows that must be
# scheduled when it does. This is #44's remaining acceptance criterion stated as a table.
REPRESENTATIVE = [
    # The model and its tests: the Python suite is the only thing that reads these.
    ("worm/params.py", [PYTHON_WF]),
    ("worm/senses.py", [PYTHON_WF]),
    ("worm/egglaying.py", [PYTHON_WF]),
    ("tests/test_behaviour.py", [PYTHON_WF]),
    ("tests/test_physics.py", [PYTHON_WF]),
    ("data/connectome.xls", [PYTHON_WF]),
    # The exporter and the conformance reference decide what the runtime is compared
    # against, so an edit to either has to re-run the comparison.
    ("tools/export_model.py", [PYTHON_WF]),
    ("tools/conform.py", [PYTHON_WF]),
    ("tools/build_dataset.py", [PYTHON_WF]),
    # Committed artefacts. The dataset job regenerates these and compares, so a
    # hand-edited one has to be caught.
    ("web/worm.model", [PYTHON_WF, VIEWER_WF]),
    ("web/worm.wasm", [PYTHON_WF, VIEWER_WF]),
    # The runtime source, which both sides consume: the viewer runs it, and the Python
    # side compares against it.
    ("wasm/assembly/index.ts", [PYTHON_WF, VIEWER_WF]),
    ("wasm/population.mjs", [VIEWER_WF]),
    ("wasm/conform.mjs", [VIEWER_WF]),
    # The evolution driver, which is where the fitness measure lives, and #37's regression
    # property beside it. Both run in the conformance job rather than the viewer one,
    # because the property needs a .model and a .wasm built from the same tree: it varies
    # `volume_per_pump` by patching the compiled constant, that scalar being deliberately
    # absent from `GENES` and from the payload alike.
    ("wasm/evolve.mjs", [VIEWER_WF]),
    ("wasm/energy-fitness.test.mjs", [VIEWER_WF]),
    ("wasm/medium.test.mjs", [VIEWER_WF]),
    ("wasm/memory.mjs", [VIEWER_WF]),
    # The viewer, its server, and the checks that run against them.
    ("web/local.js", [VIEWER_WF]),
    ("web/viewer/dish.js", [VIEWER_WF]),
    ("worm/server.py", [PYTHON_WF, VIEWER_WF]),
    ("run.py", [VIEWER_WF]),
    ("tools/smoke_web.mjs", [VIEWER_WF]),
    ("tools/sim_rate.test.mjs", [VIEWER_WF]),
    ("docker/nginx.conf", [VIEWER_WF]),
    # Dependency inputs. `npm ci` installs the lock file, not the manifest, so a
    # dependency bump that touches only the lock file still changes what every viewer job
    # runs against.
    ("package.json", [VIEWER_WF]),
    ("package-lock.json", [VIEWER_WF]),
    ("requirements.txt", [PYTHON_WF, VIEWER_WF]),
    ("pyproject.toml", [PYTHON_WF]),
    ("wasm/package-lock.json", [PYTHON_WF, VIEWER_WF]),
    # A workflow gates on itself, or it can be broken by the commit that breaks it.
    (".github/workflows/python.yml", [PYTHON_WF]),
    (".github/workflows/viewer.yml", [VIEWER_WF]),
]


@pytest.mark.parametrize("path,wanted", REPRESENTATIVE)
def test_representative_edits_schedule_their_gates(path, wanted):
    for name in (PYTHON_WF, VIEWER_WF):
        got = scheduled_by(path, name)
        assert got is (name in wanted), (
            "editing %s %s schedule %s, and it %s.\n"
            "A workflow that is not scheduled does not go red -- it reports nothing at "
            "all, which is why this is asserted rather than watched for."
            % (path, "must" if name in wanted else "must not", name,
               "does" if got else "does not"))


# Files that legitimately need no workflow, each with the reason it needs none. Anything
# tracked and not matched by a filter has to appear here, so "nothing checks this" stays a
# decision somebody made rather than an oversight nobody noticed.
NO_CI_NEEDED = {
    "README.md": "prose",
    "NEXT.md": "prose -- the live roadmap. It carries no asserted figure: the per-worm "
               "memory claim that used to make this entry interesting moved to the "
               "research log along with the rest of the working log, and wasm/memory.mjs "
               "reads it there now.",
    "LICENSE": "prose",
    "docs/project-architecture.md": "prose -- the intent/architecture compass. It states "
                                    "invariants rather than implementing any, so there is "
                                    "nothing here for a job to execute.",
    "docs/research-log/README.md": "prose -- index and handling rules for the archive",
    "docs/architecture/bonsai-pass-1-report.md":
        "prose -- the record of a maintainability pass. Dated and closed; it describes what "
        "was done rather than asserting anything a job could re-check.",
    "docs/runtime-parity.md": "prose. The claim it documents IS gated: "
                              "tests/test_runtime_parity.py pins the same registry under "
                              "tests/**, so a default moving out from under this file "
                              "fails the Python suite even though the file itself "
                              "schedules nothing.",
    "tools/README.md": "prose -- the instrument index. The python filter is tools/*.py "
                       "plus tools/check_all.mjs, deliberately narrow, and widening it to "
                       "tools/** to catch a markdown file would schedule the model suite "
                       "on documentation edits.",
    "docs/research-log/next-history-through-2026-08-04.md":
        "prose -- the archived working log, preserved byte-for-byte. The same caveat the "
        "NEXT.md entry used to carry now applies here: wasm/memory.mjs asserts that this "
        "file quotes the measured per-worm figure, and an edit to it alone schedules "
        "nothing, so a drift is caught by the next commit that touches wasm/ or web/ "
        "rather than by the commit that causes it. Gating a 181 kB archive on a "
        "docker-and-puppeteer job was judged the worse trade; the check still fails, just "
        "later and blaming the wrong change. In practice the archive is append-only "
        "history and should not drift at all.",
    ".gitignore": "affects no job's inputs",
    ".github/FUNDING.yml": "the sponsor button; read by GitHub's UI, by no job",
    "CONTRIBUTING.md": "prose -- conventions plus the local-gates runbook, moved from the "
                       "README when the repository went public. The commands it quotes "
                       "are the workflows' own steps, which tests/test_local_checks.py "
                       "pins against both workflow files.",
    "docs/model.md": "prose -- the full model account, moved byte-for-byte from the "
                     "README at public launch. Every figure it quotes is asserted where "
                     "it always was: the scorecard values by the Python suite, the "
                     "conformance tolerances by tools/conform.py, the history-ring bytes "
                     "by wasm/memory.mjs against web/viewer/history.js.",
    "docs/deploy.md": "prose -- the runtime/serving/viewer account, moved from the README "
                      "at public launch; same indirection note as docs/model.md.",
    "docs/media/viewer-animal.png": "landing-page screenshot; an image gates nothing",
    "docs/media/viewer-arena.png": "landing-page screenshot; an image gates nothing",
    ".claude/settings.json": "agent-harness configuration -- registers the SessionStart "
                             "hook. Nothing in the suite or the viewer reads it; it "
                             "configures the tool that edits the repo, not the repo.",
    ".claude/hooks/session-start.sh": "agent-harness configuration -- the stale-checkpoint "
                                      "guard for remote containers. Runs before a session, "
                                      "never inside any job.",
    "docs/niche-museum.md": "prose -- a pointer to web/museum.md, where the catalogue "
                            "lives so the site can serve it. The content IS gated at the "
                            "new address: tools/smoke_web.mjs renders museum.html from "
                            "web/museum.md and fails if the wings do not appear, and "
                            "web/** schedules the viewer workflow.",
    "Dockerfile": "the production image is built by deploy.yml on pull requests and main; "
                  "tests/test_deploy_policy.py pins that separate release gate, while this "
                  "table models the Python and viewer path filters",
    ".github/workflows/deploy.yml":
        "the release workflow self-gates on pull requests and its trigger, image-build, "
        "current-SHA, opt-in, and signed-webhook contracts are pinned by "
        "tests/test_deploy_policy.py",
    "tools/fetch_raw.sh": "fetches the raw upstream sources by hand; the pinned copies "
                          "under data/ are what CI builds from",
}

# The design docket: an owner-commissioned exploration of five chrome languages, each a
# self-contained demo with fake data and no imports -- deliberately disconnected from the
# app precisely so that trying a look cannot break the viewer. Nothing a job could
# usefully execute; if one is ever adopted, the adoption lands in web/ where every gate
# already applies.
NO_CI_NEEDED.update({
    f"docs/design/{name}": "design-language demo; see the docket block comment above"
    for name in ("DOCKET.md", "01-monograph.html", "02-cathode.html", "03-poster.html",
                 "04-observatory.html", "05-fieldnotes.html")
})


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, "git ls-files failed: %s" % out.stderr
    files = [line for line in out.stdout.splitlines() if line]
    # A checkout that reports nothing would make the sweep below pass over an empty set.
    assert len(files) > 100, "git ls-files returned %d files; that is not this repository"
    return files


def test_every_tracked_file_is_claimed_or_excused():
    unclaimed = [f for f in _tracked_files()
                 if not scheduled_by(f, PYTHON_WF) and not scheduled_by(f, VIEWER_WF)]
    surprises = sorted(set(unclaimed) - set(NO_CI_NEEDED))
    assert not surprises, (
        "these tracked files schedule no workflow at all:\n  %s\n"
        "Either add them to a path filter or name them in NO_CI_NEEDED with the reason "
        "they need no gate." % "\n  ".join(surprises))

    # And the excuses have to stay honest: an entry that a filter has since grown to cover
    # is stale, and leaving it implies a hole that is no longer there.
    stale = sorted(f for f in NO_CI_NEEDED
                   if scheduled_by(f, PYTHON_WF) or scheduled_by(f, VIEWER_WF))
    assert not stale, (
        "NO_CI_NEEDED still excuses files that a workflow now covers: %s" % stale)
