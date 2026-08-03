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

Every mutation and generated build runs in a detached temporary worktree at the caller's
committed HEAD. Staged, unstaged, and untracked caller work stays outside it; the caller's
HEAD, status, staged index diff, final working-tree diff, and non-ignored untracked bytes
are fingerprinted before and verified after cleanup. Ignored dependency trees are not
recursively hashed; only the identity of the node_modules links/directories shared with
the worktree is fingerprinted.

Exit 0 means the selected battery was conclusive and had no executed survivor. Exit 1 is
reserved for a defect that survived detectors which actually ran. Exit 2 is an incomplete
audit (red baseline, stale mutation, command/workspace failure), and 130 is interruption.
Fast mode reports pytest-only mutations as skipped/not-selected; omission is not a miss.

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
import hashlib
import os
import signal
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
FINDING_EXIT_CODE = 10


class CommandState(Enum):
    """Whether a detector command ran, not whether it caught a mutation."""

    PASS = "pass"
    NONZERO = "nonzero"
    FAILED = "command-failed"


@dataclass(frozen=True)
class CommandResult:
    state: CommandState
    message: str = ""


def _tail(output):
    lines = output.decode("utf8", "replace").strip().splitlines()
    return lines[-1] if lines else ""


def _terminate_process_tree(process):
    """Terminate a detector and the descendants in its process group."""
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP gives the detector its own group, while taskkill /T
        # is the reliable non-interactive way to include descendants on Windows.
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            if result.returncode:
                # If the direct process exited while a descendant kept our pipes open,
                # taskkill cannot find the old parent PID. The process-group identifier
                # remains usable for CTRL_BREAK while group members still exist.
                try:
                    os.kill(process.pid, signal.CTRL_BREAK_EVENT)
                except (OSError, ValueError):
                    pass
                if process.poll() is None:
                    process.kill()
        except (OSError, subprocess.SubprocessError):
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        process.wait(timeout=5)
    finally:
        if os.name != "nt":
            # The group can outlive its leader if a descendant ignores SIGTERM. Ensure
            # the whole group is gone even when the direct detector exited promptly.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass


def command(args, root, timeout=2400, stdout_path=None, detector_exit_codes=()):
    """Run one detector command without a shell.

    Only an explicitly declared exit code is evidence that a detector noticed a mutation.
    All other non-zero exits, failure to start, abnormal termination, and timeout are
    infrastructure failures; counting one of those as a catch would turn a broken runner
    into false coverage. Pytest's detector code is 1 (test failures); its 2--5 exits are
    usage, interruption, collection, or no-tests failures and therefore infrastructure.
    The repository's Node detectors reserve 10 for completed assertion findings, leaving
    Node's ordinary startup, parse, WASM, and uncaught-failure codes as infrastructure.
    """
    root = Path(root)
    output_path = None
    if stdout_path is not None:
        output_path = _safe_repo_path(root, stdout_path)
    env = dict(os.environ, PYTHONPATH=str(root))
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    p = None
    try:
        p = subprocess.Popen(
            args,
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_kwargs,
        )
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if p is not None:
            _terminate_process_tree(p)
        return CommandResult(CommandState.FAILED, "timed out")
    except KeyboardInterrupt:
        if p is not None:
            _terminate_process_tree(p)
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        if p is not None:
            _terminate_process_tree(p)
        return CommandResult(CommandState.FAILED, str(exc))
    output = stderr if stdout_path is not None else stdout + stderr
    if p.returncode:
        state = (CommandState.NONZERO if p.returncode in detector_exit_codes
                 else CommandState.FAILED)
        detail = _tail(output)
        message = "exit %d" % p.returncode
        if detail:
            message += ": " + detail
        return CommandResult(state, message)
    if stdout_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(stdout)
    return CommandResult(CommandState.PASS, _tail(output))


PYTHON = sys.executable
NODE = shutil.which("node") or "node"


def _asc_command():
    """Prefer the caller's installed compiler while compiling source in the worktree."""
    installed = ROOT / "wasm" / "node_modules" / "assemblyscript" / "bin" / "asc.js"
    if installed.is_file():
        return [NODE, str(installed), "assembly/index.ts", "--target", "release"]
    return [shutil.which("npx") or "npx", "asc", "assembly/index.ts", "--target", "release"]


# --------------------------------------------------------------------------- checks ---
# `rebuild` says what has to happen before a check is meaningful, and the ordering here is
# the one that cost an hour once: the reference has to be regenerated whenever the *Python*
# moves, or the port is measured against a model that no longer exists.

def _conform(rebuild, root):
    if rebuild == "full":
        result = command([PYTHON, "tools/export_model.py"], root)
        if result.state is not CommandState.PASS:
            return CommandResult(result.state, "export: " + result.message)
    if rebuild in ("full", "asc"):
        result = command(_asc_command(), Path(root) / "wasm")
        if result.state is not CommandState.PASS:
            return CommandResult(result.state, "compile: " + result.message)
    # Regenerated every time. A stale reference does not weaken this check, it inverts it.
    result = command([PYTHON, "tools/conform.py"], root, stdout_path="web/conform.json")
    if result.state is not CommandState.PASS:
        return CommandResult(result.state, "reference: " + result.message)
    return command(
        [NODE, "wasm/conform.mjs"], root,
        detector_exit_codes=(FINDING_EXIT_CODE,),
    )


CHECKS = {
    "graph":  lambda rb, root: command([NODE, "tools/check_web.mjs"], root,
                                        detector_exit_codes=(FINDING_EXIT_CODE,)),
    "viewer": lambda rb, root: command([NODE, "tools/smoke_web.mjs"], root,
                                         detector_exit_codes=(FINDING_EXIT_CODE,)),
    "conform": _conform,
    "tests":  lambda rb, root: command(
        [PYTHON, "-m", "pytest", "tests/", "-x", "-q"], root,
        detector_exit_codes=(1,),
    ),
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

    # The two multi-animal defects. Both are invisible to every single-animal check by
    # construction -- with one worm, `stepAll` and a loop over `step` are the same
    # arithmetic -- so until conform.mjs grew its MULTI-ANIMAL case there was nothing in
    # this battery either of them could have been put in front of. Both were watched to
    # fail before being written down here, and with both of them applied every one of the
    # five single-animal cases still passed, which is the measurement that says the new
    # case is doing the work rather than riding along with the old ones.
    dict(name="wasm/feeding-per-animal", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="the real bug #63 and #71 chased: each animal captured and debited "
                  "inside its own step, so worm 3 sampled a lawn three others had already "
                  "been served from. Measured, eaten in array order: 0.016047241, "
                  "0.016038848, 0.016025892, 0.016025215 -- monotonic in the array index, "
                  "1.2e-05 past a feeding tolerance of 1e-08. Node positions move only "
                  "2.2e-08, so the feeding comparison is what catches this and not the "
                  "trajectory.",
         find="    for (let k = 0; k < count; k++) unchecked(fWant[k] = unchecked(worms[k]).prepareStep());\n"
              "    settleFeeding(count);\n"
              "    for (let k = 0; k < count; k++) unchecked(worms[k]).finishStep(unchecked(fGot[k]));",
         repl="    for (let k = 0; k < count; k++) unchecked(worms[k]).step();",
         expect=["conform"]),

    dict(name="wasm/plate-per-animal", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="the plate aged once per animal per step instead of once per step -- the "
                  "mistake stepAll's shape invites, and the one the comment on `step` warns "
                  "against in words rather than in a check. Four animals diffuse the "
                  "chemistry four times as fast; measured, 6.4e-06 mm on node positions and "
                  "5.5e-01 mV on membrane potentials against tolerances of 1e-06 on both, "
                  "and the very first sampled frame is already out.",
         find="    for (let k = 0; k < count; k++) unchecked(worms[k]).finishStep(unchecked(fGot[k]));\n"
              "    // The plate is shared, so it advances once per step and not once per animal.\n"
              "    world.stepFields(G.DT);",
         repl="    for (let k = 0; k < count; k++) {\n"
              "      unchecked(worms[k]).finishStep(unchecked(fGot[k]));\n"
              "      world.stepFields(G.DT);\n"
              "    }",
         expect=["conform"]),

    dict(name="wasm/frozen-sources", file="wasm/assembly/index.ts", rebuild="asc",
         imitates="#48 put back: eating moves the food array and nothing else, so a lawn "
                  "grazed to bare agar goes on smelling and respiring exactly like a full "
                  "one. Measured, 8.359e-05 mm on node positions and 3.731e-01 mV on "
                  "membrane potentials against tolerances of 1e-06 on both, first out of "
                  "tolerance at step 3200 of the four-animal case.\n"
                  "\n"
                  "Only the four-animal case catches it, and that is the whole reason this "
                  "entry is worth having: in the 2 s the single-animal cases run, one worm "
                  "takes so little off the plate that every field stays inside tolerance. "
                  "The defect that shipped for the life of this model is invisible to five "
                  "of the six conformance cases.",
         find="      this.refreshSources();\n",
         repl="",
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

class DetectorState(Enum):
    CAUGHT = "caught"
    MISSED = "executed-but-missed"
    COMMAND_FAILED = "command-failed"
    SKIPPED = "skipped/not-selected"


@dataclass(frozen=True)
class DetectorResult:
    state: DetectorState
    message: str = ""


@dataclass
class MutationResult:
    mutation: dict
    detectors: dict
    error: str | None = None
    elapsed: float = 0.0

    @property
    def caught_by(self):
        return [name for name, result in self.detectors.items()
                if result.state is DetectorState.CAUGHT]

    @property
    def command_failures(self):
        return [name for name, result in self.detectors.items()
                if result.state is DetectorState.COMMAND_FAILED]


@dataclass(frozen=True)
class CallerSnapshot:
    head: str
    status: bytes
    index_hash: str
    working_tree_hash: str
    untracked_hash: str
    dependency_state_hash: str

    @property
    def identity(self):
        digest = hashlib.sha256()
        digest.update(self.head.encode("ascii"))
        digest.update(self.status)
        digest.update(self.index_hash.encode("ascii"))
        digest.update(self.working_tree_hash.encode("ascii"))
        digest.update(self.untracked_hash.encode("ascii"))
        digest.update(self.dependency_state_hash.encode("ascii"))
        return digest.hexdigest()


class WorkspaceError(RuntimeError):
    pass


def _git(args, root, timeout=120):
    try:
        return subprocess.run(["git", *args], cwd=root, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("git %s failed: %s" % (" ".join(args), exc)) from exc


def _git_output(args, root):
    result = _git(args, root)
    if result.returncode:
        raise WorkspaceError("git %s failed: %s"
                             % (" ".join(args), _tail(result.stderr + result.stdout)))
    return result.stdout


def _hash_file(path, digest):
    try:
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.fsencode(os.readlink(path)))
            return
        if not path.is_file():
            digest.update(b"non-regular\0")
            digest.update(str(path.lstat().st_mode).encode("ascii"))
            return
        digest.update(b"file\0")
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise WorkspaceError("could not fingerprint %s: %s" % (path, exc)) from exc


def _untracked_content_hash(root):
    """Hash the names, types, and bytes of every non-ignored untracked file."""
    raw_paths = _git_output(
        ["ls-files", "--others", "--exclude-standard", "-z", "--full-name"], root
    )
    digest = hashlib.sha256()
    for raw_path in raw_paths.split(b"\0"):
        if not raw_path:
            continue
        path = _safe_repo_path(root, os.fsdecode(raw_path), follow_final=False)
        digest.update(raw_path)
        digest.update(b"\0")
        _hash_file(path, digest)
        digest.update(b"\0")
    return digest.hexdigest()


def _dependency_state_hash(root):
    """Fingerprint dependency link/directory identity without traversing its contents."""
    digest = hashlib.sha256()
    for rel in ("node_modules", "wasm/node_modules"):
        path = _safe_repo_path(root, rel, follow_final=False)
        digest.update(rel.encode("ascii") + b"\0")
        if not os.path.lexists(path):
            digest.update(b"missing\0")
            continue
        try:
            stat = path.lstat()
            digest.update(
                ("mode=%d;dev=%d;ino=%d\0" % (stat.st_mode, stat.st_dev, stat.st_ino))
                .encode("ascii")
            )
            if path.is_symlink():
                digest.update(b"target=")
                digest.update(os.fsencode(os.readlink(path)))
                digest.update(b"\0")
            # realpath captures a symlink/junction retarget without walking or hashing the
            # dependency tree. Ordinary edits below these ignored directories are outside
            # the integrity claim and intentionally do not make snapshots expensive.
            digest.update(os.fsencode(os.path.realpath(path)))
            digest.update(b"\0")
        except OSError as exc:
            raise WorkspaceError(
                "could not fingerprint dependency path %s: %s" % (path, exc)
            ) from exc
    return digest.hexdigest()


def caller_snapshot(root):
    """Record the caller state without requiring it to be clean.

    The audit runs the committed HEAD in isolation. Existing staged, unstaged, and
    untracked work is allowed to remain in the caller checkout and is fingerprinted here.
    The index and final tracked working-tree state are hashed separately, so changing an
    MM file's staged blob while leaving its working bytes fixed is observable. Non-ignored
    untracked file bytes are hashed, not merely their status paths. The two ignored
    dependency directories are fingerprinted only by their link/directory identity; their
    potentially huge contents are deliberately not traversed.
    """
    root = Path(root)
    head = _git_output(["rev-parse", "HEAD"], root).decode("ascii").strip()
    status = _git_output(["status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    index_diff = _git_output(["diff", "--cached", "--binary", "HEAD", "--"], root)
    working_tree_diff = _git_output(["diff", "--binary", "HEAD", "--"], root)
    return CallerSnapshot(
        head,
        status,
        hashlib.sha256(index_diff).hexdigest(),
        hashlib.sha256(working_tree_diff).hexdigest(),
        _untracked_content_hash(root),
        _dependency_state_hash(root),
    )


def _remove_dependency_link(path):
    if not os.path.lexists(path):
        return
    if Path(path).is_symlink():
        Path(path).unlink()
    else:
        # On Windows a directory junction is not consistently reported as a symlink.
        # rmdir removes the reparse point itself and never traverses its target.
        os.rmdir(path)


def _link_dependency(source, destination):
    """Expose ignored installed dependencies to the isolated checkout, if present."""
    source, destination = Path(source), Path(destination)
    if not source.is_dir():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.symlink_to(source, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            return False
        result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J",
                                 str(destination), str(source)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            return False
    return True


def _is_within(path, parent, allow_equal=False):
    path, parent = os.path.abspath(path), os.path.abspath(parent)
    try:
        return (allow_equal or path != parent) and os.path.commonpath([path, parent]) == parent
    except ValueError:
        return False


def _safe_repo_path(root, relative, follow_final=True):
    """Resolve a non-empty repo-relative path and reject traversal or symlink escape."""
    root = Path(root).resolve()
    if not isinstance(relative, (str, os.PathLike)):
        raise WorkspaceError("audit path is not path-like: %r" % (relative,))
    raw = os.fspath(relative)
    if not raw:
        raise WorkspaceError("audit path must not be empty")
    relative_path = Path(raw)
    if relative_path.is_absolute() or relative_path.drive:
        raise WorkspaceError("audit path must be repo-relative: %s" % raw)
    if ".." in relative_path.parts:
        raise WorkspaceError("audit path must not contain '..': %s" % raw)
    candidate = root / relative_path
    try:
        resolved_parent = candidate.parent.resolve(strict=False)
        resolved = (candidate.resolve(strict=False) if follow_final
                    else resolved_parent / candidate.name)
    except OSError as exc:
        raise WorkspaceError("could not resolve audit path %s: %s" % (raw, exc)) from exc
    if not _is_within(resolved_parent, root, allow_equal=True):
        raise WorkspaceError("audit path parent escapes isolated root: %s" % raw)
    if follow_final and not _is_within(resolved, root):
        raise WorkspaceError("audit path escapes isolated root: %s" % raw)
    return resolved


@contextmanager
def isolated_worktree(caller_root=ROOT, temp_base=None):
    """Yield a detached temporary worktree and always remove it again.

    Cleanup targets are created here and lexically checked against their private temp
    directory. No reset, checkout, clean, or restore command is ever run in caller_root.
    """
    caller_root = Path(caller_root).resolve()
    before = caller_snapshot(caller_root)
    temp_root = Path(temp_base or tempfile.gettempdir()).resolve()
    temp_parent = Path(tempfile.mkdtemp(prefix="celegans-audit-", dir=temp_root)).resolve()
    if not _is_within(temp_parent, temp_root):
        raise WorkspaceError("temporary workspace escaped its parent: %s" % temp_parent)
    worktree = temp_parent / "worktree"
    links = []
    added = False
    cleanup_errors = []
    try:
        added_result = _git(["worktree", "add", "--detach", str(worktree), before.head],
                            caller_root)
        if added_result.returncode:
            raise WorkspaceError("could not create isolated worktree: "
                                 + _tail(added_result.stderr + added_result.stdout))
        added = True
        for rel in ("node_modules", os.path.join("wasm", "node_modules")):
            destination = worktree / rel
            if _link_dependency(caller_root / rel, destination):
                links.append(destination)
        yield worktree, before
    finally:
        pending_exception = sys.exc_info()[0] is not None
        for link in reversed(links):
            try:
                _remove_dependency_link(link)
            except OSError as exc:
                cleanup_errors.append("could not remove dependency link %s: %s" % (link, exc))
        if added:
            try:
                result = _git(["worktree", "remove", "--force", str(worktree)], caller_root)
                if result.returncode:
                    cleanup_errors.append("could not remove worktree: "
                                          + _tail(result.stderr + result.stdout))
            except WorkspaceError as exc:
                cleanup_errors.append("could not remove worktree: %s" % exc)
        if temp_parent.exists():
            if not _is_within(temp_parent, temp_root):
                cleanup_errors.append("refusing to remove unexpected path %s" % temp_parent)
            elif not worktree.exists() or not added:
                try:
                    if added:
                        temp_parent.rmdir()
                    else:
                        shutil.rmtree(temp_parent)
                except OSError as exc:
                    cleanup_errors.append("could not remove temporary directory: %s" % exc)
        try:
            after = caller_snapshot(caller_root)
            if after != before:
                cleanup_errors.append(
                    "caller checkout changed during audit (before %s, after %s)"
                    % (before.identity[:12], after.identity[:12]))
        except WorkspaceError as exc:
            cleanup_errors.append("could not verify caller checkout: %s" % exc)
        if cleanup_errors:
            message = "; ".join(cleanup_errors)
            if pending_exception:
                print("audit cleanup warning: " + message, file=sys.stderr)
            else:
                raise WorkspaceError(message)


GENERATED_PATHS = (
    "web/worm.model",
    "web/worm.wasm",
    "wasm/assembly/model_gen.ts",
    "web/conform.json",
)


def _capture_paths(root, paths):
    resolved = [(rel, _safe_repo_path(root, rel)) for rel in paths]
    captured = {}
    for rel, path in resolved:
        captured[rel] = path.read_bytes() if path.is_file() else None
    return captured


def _restore_paths(root, captured):
    resolved = [(_safe_repo_path(root, rel), content) for rel, content in captured.items()]
    for path, content in resolved:
        if content is None:
            if os.path.lexists(path):
                if path.is_dir():
                    raise WorkspaceError("refusing to unlink generated directory %s" % path)
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def apply(mut, root):
    """Apply one or more find/replace pairs. Several, because a defect is not always one
    line: two sites that clear the same state are redundant with each other, and removing
    either alone is an equivalent mutant. Asking whether the *behaviour* is covered means
    breaking every site that provides it."""
    path = _safe_repo_path(root, mut["file"])
    original = io.open(path, encoding="utf8").read()
    edits = mut.get("edits") or [(mut["find"], mut["repl"])]
    text = original
    for find, repl in edits:
        if find not in text:
            return None, "PATTERN NOT FOUND -- the mutation is stale, not the code"
        text = text.replace(find, repl, 1)
    io.open(path, "w", encoding="utf8").write(text)
    return original, None


def restore(mut, original, root):
    if original is not None:
        io.open(_safe_repo_path(root, mut["file"]), "w", encoding="utf8").write(original)


def _detector_result(command_result):
    if command_result.state is CommandState.PASS:
        return DetectorResult(DetectorState.MISSED, command_result.message)
    if command_result.state is CommandState.NONZERO:
        return DetectorResult(DetectorState.CAUGHT, command_result.message)
    return DetectorResult(DetectorState.COMMAND_FAILED, command_result.message)


def _run_detector(name, rebuild, root, checks):
    try:
        result = checks[name](rebuild, root)
    except Exception as exc:
        return DetectorResult(DetectorState.COMMAND_FAILED, str(exc))
    if not isinstance(result, CommandResult):
        return DetectorResult(DetectorState.COMMAND_FAILED,
                              "detector returned an invalid result")
    return _detector_result(result)


def _status_label(result):
    return {
        DetectorState.CAUGHT: "CAUGHT",
        DetectorState.MISSED: "executed-but-missed",
        DetectorState.COMMAND_FAILED: "command-failed",
        DetectorState.SKIPPED: "skipped/not-selected",
    }[result.state]


def _validate_audit_request(mutations, battery, root, checks):
    if not battery:
        raise WorkspaceError("audit battery is empty")
    unknown_battery = [name for name in battery if name not in checks]
    if unknown_battery:
        raise WorkspaceError(
            "unknown battery detector(s): %s" % ", ".join(unknown_battery)
        )
    if not mutations:
        raise WorkspaceError("audit selection contains no mutations")
    known_detectors = set(checks)
    for generated in GENERATED_PATHS:
        _safe_repo_path(root, generated)
    for mutation in mutations:
        if not isinstance(mutation, dict):
            raise WorkspaceError("mutation entry is not a mapping")
        if "file" not in mutation or "expect" not in mutation:
            raise WorkspaceError("mutation entry is missing file or expect")
        _safe_repo_path(root, mutation["file"])
        unknown_expected = [
            name for name in mutation["expect"] if name not in known_detectors
        ]
        if unknown_expected:
            raise WorkspaceError(
                "mutation %s names unknown expected detector(s): %s"
                % (mutation.get("name", "<unnamed>"), ", ".join(unknown_expected))
            )


def run_audit(mutations, battery, root, checks=None, out=sys.stdout, err=sys.stderr):
    """Run an audit in an already-isolated root and return its documented exit code.

    0 means the selected audit was conclusive and had no surviving defect; 1 means at
    least one mutation survived detectors that actually ran; 2 means baseline,
    infrastructure, or mutation-catalogue failure. Omitted owners are reported but never
    promoted to a survivor.
    """
    checks = CHECKS if checks is None else checks
    root = Path(root)
    try:
        _validate_audit_request(mutations, battery, root, checks)
    except (OSError, TypeError, WorkspaceError) as exc:
        print("Audit request error: %s" % exc, file=err)
        return 2
    all_detectors = list(dict.fromkeys([*SLOW, *checks]))
    print("COVERAGE AUDIT -- %d deliberate defects against %s\n"
          % (len(mutations), ", ".join(battery)), file=out)
    print("  Each entry imitates a class of bug this repository has actually shipped.", file=out)
    print("  Statuses distinguish caught, executed-but-missed, command-failed, and", file=out)
    print("  skipped/not-selected. Only an executed survivor is a coverage hole.\n", file=out)

    print("  baseline (no mutation):", end=" ", flush=True, file=out)
    baseline = {}
    for name in battery:
        if name not in checks:
            baseline[name] = DetectorResult(DetectorState.COMMAND_FAILED,
                                            "unknown detector")
        else:
            baseline[name] = _run_detector(name, None, root, checks)
        result = baseline[name]
        label = "pass" if result.state is DetectorState.MISSED else (
            "FAIL" if result.state is DetectorState.CAUGHT else "command-failed")
        if result.message:
            label += "[%s]" % result.message
        print("%s=%s" % (name, label), end=" ", flush=True, file=out)
    print(file=out)
    if any(result.state is not DetectorState.MISSED for result in baseline.values()):
        print("\n  baseline is not green. Fix that first -- a red or unavailable check "
              "cannot catch anything.", file=err)
        return 2

    rows = []
    for mutation in mutations:
        started = time.time()
        print("\n  %-24s %s" % (mutation["name"], mutation["imitates"][:70]), file=out)
        applicable = list(battery_for(mutation, list(battery)))
        selected_owners = [name for name in mutation["expect"] if name in applicable]
        detectors = {
            name: DetectorResult(DetectorState.SKIPPED, "not selected by this battery")
            for name in all_detectors
        }

        # An inert control has no owner and is intentionally run. A real mutation whose
        # only owner is outside this battery is explicitly skipped: running unrelated
        # detectors cannot turn deliberately omitted coverage into a survivor.
        if mutation["expect"] and not selected_owners:
            reason = "no owning detector selected (%s)" % ", ".join(mutation["expect"])
            for name in applicable:
                detectors[name] = DetectorResult(DetectorState.SKIPPED, reason)
            row = MutationResult(mutation, detectors, elapsed=time.time() - started)
            rows.append(row)
            print("      -> skipped/not-selected: %s" % reason, file=out)
            continue

        capture = _capture_paths(root, [mutation["file"], *GENERATED_PATHS])
        original = None
        error = None
        try:
            original, error = apply(mutation, root)
            if error:
                print("      %s" % error, file=out)
            else:
                for name in applicable:
                    result = _run_detector(name, mutation.get("rebuild"), root, checks)
                    detectors[name] = result
                    suffix = (": " + result.message) if result.message else ""
                    print("      %-8s %s%s"
                          % (name, _status_label(result), suffix), flush=True, file=out)
        finally:
            # Exact path restoration is useful even inside the disposable worktree: it
            # prevents one generated model/reference from contaminating the next mutant.
            if original is not None:
                restore(mutation, original, root)
            _restore_paths(root, capture)
        row = MutationResult(mutation, detectors, error, time.time() - started)
        rows.append(row)
        if error:
            continue
        if row.command_failures:
            outcome = "INCONCLUSIVE: " + ", ".join(row.command_failures)
        elif row.caught_by:
            outcome = ", ".join(row.caught_by)
        elif mutation["expect"]:
            outcome = "EXECUTED SURVIVOR"
        else:
            outcome = "control correctly ignored"
        print("      -> %s   (%.0fs)" % (outcome, row.elapsed), file=out)

    print("\n\n  %-24s %s" %
          ("defect", "  ".join("%-20s" % name for name in all_detectors)), file=out)
    for row in rows:
        if row.error:
            print("  %-24s  %s" % (row.mutation["name"], row.error), file=out)
            continue
        print("  %-24s %s" %
              (row.mutation["name"], "  ".join(
                  "%-20s" % _status_label(row.detectors[name]) for name in all_detectors)),
              file=out)

    stale = [row for row in rows if row.error]
    failed = [row for row in rows if row.command_failures]
    failure_count = sum(len(row.command_failures) for row in failed)
    survivors = []
    controls_ok = []
    surprises = []
    skipped = []
    for row in rows:
        mutation = row.mutation
        if row.error or row.command_failures:
            continue
        selected_owners = [name for name in mutation["expect"]
                           if row.detectors.get(name, DetectorResult(DetectorState.SKIPPED)).state
                           is not DetectorState.SKIPPED]
        if mutation["expect"] and not selected_owners:
            skipped.append(row)
            continue
        if not row.caught_by and mutation["expect"]:
            survivors.append(row)
        if not row.caught_by and not mutation["expect"]:
            controls_ok.append(row)
        if row.caught_by and not mutation["expect"]:
            surprises.append((row, row.caught_by[0],
                              "control fired -- the battery is reacting to noise"))
        for name in mutation["expect"]:
            result = row.detectors.get(name)
            if result and result.state is DetectorState.MISSED:
                surprises.append((row, name, "expected to catch it and did not"))
        for name in row.caught_by:
            if name not in mutation["expect"] and mutation["expect"]:
                surprises.append((row, name, "caught it unexpectedly"))

    print(file=out)
    if survivors:
        print("  %d EXECUTED SURVIVOR(S) -- these are coverage holes:"
              % len(survivors), file=out)
        for row in survivors:
            print("    %-24s %s" % (row.mutation["name"], row.mutation["imitates"]), file=out)
    else:
        print("  No defect survived a detector that actually ran.", file=out)
    if skipped:
        print("  %d mutation(s) skipped because no owning detector was selected: %s"
              % (len(skipped), ", ".join(row.mutation["name"] for row in skipped)), file=out)
    if controls_ok:
        print("  %d control(s) correctly ignored: %s"
              % (len(controls_ok), ", ".join(row.mutation["name"] for row in controls_ok)), file=out)
    if surprises:
        print("\n  %d surprise(s) against the written-down prediction:" % len(surprises), file=out)
        for row, name, what in surprises:
            print("    %-24s %-8s %s" % (row.mutation["name"], name, what), file=out)
    if stale or failed:
        print("\n  Audit incomplete: %d stale mutation(s), %d command failure(s)."
              % (len(stale), failure_count), file=err)
        return 2
    return 1 if survivors else 0


def _parse_args(argv):
    slow = False
    only = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--slow":
            slow = True
            index += 1
            continue
        if arg == "--only":
            if only is not None:
                raise ValueError("--only may only be specified once")
            if index + 1 == len(argv):
                raise ValueError("--only requires a name fragment")
            only = argv[index + 1]
            if not only.strip():
                raise ValueError("--only requires a non-empty name fragment")
            index += 2
            continue
        raise ValueError("unrecognized argument: %s" % arg)
    return (SLOW if slow else FAST), only


def main(argv):
    try:
        battery, only = _parse_args(argv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    mutations = [m for m in MUTATIONS if not only or only in m["name"]]
    if only is not None and not mutations:
        print("--only matched no mutations: %s" % only, file=sys.stderr)
        return 2
    try:
        with isolated_worktree(ROOT) as (audit_root, caller):
            print("Auditing committed HEAD %s in isolated worktree; caller snapshot %s."
                  % (caller.head[:12], caller.identity[:12]))
            result = run_audit(mutations, battery, audit_root)
        print("Caller checkout verified unchanged (%s)." % caller.identity[:12])
        return result
    except KeyboardInterrupt:
        print("\nAudit interrupted; isolated worktree cleanup was attempted.", file=sys.stderr)
        return 130
    except WorkspaceError as exc:
        print("Audit workspace error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
