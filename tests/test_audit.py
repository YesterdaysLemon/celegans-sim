import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from tools import audit


def _make_directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as exc:
        if os.name != "nt":
            pytest.skip("directory symlinks unavailable: %s" % exc)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    if result.returncode:
        pytest.skip("directory junctions unavailable")


def _remove_directory_link(link):
    if link.is_symlink():
        link.unlink()
    else:
        # On Windows this removes the junction itself without traversing its target.
        os.rmdir(link)


@pytest.mark.parametrize(
    ("exit_code", "expected_state"),
    [
        (0, audit.CommandState.PASS),
        (1, audit.CommandState.FAILED),
        (2, audit.CommandState.FAILED),
        (5, audit.CommandState.FAILED),
        (audit.FINDING_EXIT_CODE, audit.CommandState.NONZERO),
        (17, audit.CommandState.FAILED),
    ],
)
def test_command_classifies_real_subprocess_exit_codes(
    tmp_path, exit_code, expected_state
):
    result = audit.command(
        [sys.executable, "-c", "import sys; sys.exit(%d)" % exit_code],
        tmp_path,
        detector_exit_codes=(audit.FINDING_EXIT_CODE,),
    )

    assert result.state is expected_state
    if exit_code:
        assert "exit %d" % exit_code in result.message


@pytest.mark.parametrize(
    ("exit_code", "expected_state"),
    [(1, audit.CommandState.NONZERO), (2, audit.CommandState.FAILED),
     (3, audit.CommandState.FAILED), (4, audit.CommandState.FAILED),
     (5, audit.CommandState.FAILED)],
)
def test_pytest_exit_policy_only_treats_test_failures_as_findings(
    tmp_path, exit_code, expected_state
):
    result = audit.command(
        [sys.executable, "-c", "import sys; sys.exit(%d)" % exit_code],
        tmp_path,
        detector_exit_codes=(1,),
    )

    assert result.state is expected_state


def test_production_node_detectors_only_accept_dedicated_finding_code(
    tmp_path, monkeypatch
):
    calls = []

    def fake_command(args, root, timeout=2400, stdout_path=None, detector_exit_codes=()):
        calls.append((list(args), stdout_path, detector_exit_codes))
        return audit.CommandResult(audit.CommandState.PASS)

    monkeypatch.setattr(audit, "command", fake_command)
    audit.CHECKS["graph"](None, tmp_path)
    audit.CHECKS["viewer"](None, tmp_path)
    audit.CHECKS["conform"](None, tmp_path)

    assert calls[0][2] == (audit.FINDING_EXIT_CODE,)
    assert calls[1][2] == (audit.FINDING_EXIT_CODE,)
    assert calls[2][1] == "web/conform.json"
    assert calls[2][2] == ()  # malformed/missing Python reference generation is infra
    assert calls[3][0][-1] == "wasm/conform.mjs"
    assert calls[3][2] == (audit.FINDING_EXIT_CODE,)


def _node_or_skip():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable")
    return node


def test_graph_detector_uses_dedicated_exit_for_asserted_problem(tmp_path):
    node = _node_or_skip()
    (tmp_path / "tools").mkdir()
    (tmp_path / "web").mkdir()
    shutil.copyfile(audit.ROOT / "tools" / "check_web.mjs",
                    tmp_path / "tools" / "check_web.mjs")
    (tmp_path / "web" / "a.js").write_text(
        "import { missing } from './b.js';\n", encoding="utf8"
    )
    (tmp_path / "web" / "b.js").write_text(
        "export const present = 1;\n", encoding="utf8"
    )

    result = audit.command(
        [node, "tools/check_web.mjs"], tmp_path,
        detector_exit_codes=(audit.FINDING_EXIT_CODE,),
    )

    assert result.state is audit.CommandState.NONZERO
    assert "exit %d" % audit.FINDING_EXIT_CODE in result.message


@pytest.mark.parametrize("reference", [None, "{"])
def test_conform_missing_or_malformed_reference_is_command_failure(
    tmp_path, reference
):
    node = _node_or_skip()
    (tmp_path / "wasm").mkdir()
    shutil.copyfile(audit.ROOT / "wasm" / "conform.mjs",
                    tmp_path / "wasm" / "conform.mjs")
    if reference is not None:
        (tmp_path / "web").mkdir()
        (tmp_path / "web" / "worm.wasm").write_bytes(b"")
        (tmp_path / "web" / "worm.model").write_bytes(b"")
        (tmp_path / "web" / "conform.json").write_text(reference, encoding="utf8")

    result = audit.command(
        [node, "wasm/conform.mjs"], tmp_path,
        detector_exit_codes=(audit.FINDING_EXIT_CODE,),
    )

    assert result.state is audit.CommandState.FAILED
    assert "exit 2" in result.message if reference is None else "exit 1" in result.message


def _mutation(expect):
    return {
        "name": "py/example",
        "file": "worm/example.py",
        "rebuild": None,
        "imitates": "a deliberately small test mutation",
        "find": "VALUE = 1",
        "repl": "VALUE = 2",
        "expect": expect,
    }


def _source_tree(tmp_path):
    root = tmp_path / "source"
    (root / "worm").mkdir(parents=True)
    (root / "worm" / "example.py").write_text("VALUE = 1\n", encoding="utf8")
    return root


@pytest.mark.parametrize("path_kind", ["parent", "absolute"])
def test_unsafe_mutation_path_is_rejected_before_any_detector_or_write(
    tmp_path, path_kind
):
    root = _source_tree(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf8")
    mutation = _mutation(["graph"])
    mutation["file"] = "../outside.py" if path_kind == "parent" else str(outside.resolve())
    calls = 0

    def graph(rebuild, check_root):
        nonlocal calls
        calls += 1
        return audit.CommandResult(audit.CommandState.PASS)

    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [mutation], ["graph"], root, {"graph": graph}, stdout, stderr
    )

    assert exit_code == 2
    assert calls == 0
    assert outside.read_text(encoding="utf8") == "VALUE = 1\n"
    assert "Audit request error" in stderr.getvalue()


def test_unsafe_generated_path_is_rejected_before_baseline(tmp_path, monkeypatch):
    root = _source_tree(tmp_path)
    calls = 0

    def graph(rebuild, check_root):
        nonlocal calls
        calls += 1
        return audit.CommandResult(audit.CommandState.PASS)

    monkeypatch.setattr(audit, "GENERATED_PATHS", ("../escaped.bin",))
    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [_mutation(["graph"])], ["graph"], root, {"graph": graph}, stdout, stderr
    )

    assert exit_code == 2
    assert calls == 0
    assert not (tmp_path / "escaped.bin").exists()
    assert "Audit request error" in stderr.getvalue()


def test_mutation_directory_link_escape_is_rejected_before_baseline(tmp_path):
    root = _source_tree(tmp_path)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf8")
    link = root / "worm" / "external"
    _make_directory_link(link, outside_dir)
    mutation = _mutation(["graph"])
    mutation["file"] = "worm/external/outside.py"
    calls = 0

    def graph(rebuild, check_root):
        nonlocal calls
        calls += 1
        return audit.CommandResult(audit.CommandState.PASS)

    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [mutation], ["graph"], root, {"graph": graph}, stdout, stderr
    )

    assert exit_code == 2
    assert calls == 0
    assert outside.read_text(encoding="utf8") == "VALUE = 1\n"
    assert "escapes isolated root" in stderr.getvalue()


def test_command_rejects_unsafe_stdout_path_before_starting_process(tmp_path):
    marker = tmp_path / "started.txt"
    code = "from pathlib import Path; Path(%r).write_text('started')" % str(marker)

    with pytest.raises(audit.WorkspaceError, match="repo-relative|contain"):
        audit.command(
            [sys.executable, "-c", code], tmp_path, stdout_path="../escaped.json"
        )

    assert not marker.exists()


@pytest.mark.parametrize(
    ("mutations", "battery", "checks", "message"),
    [
        ([_mutation(["graph"])], ["grapph"], {"graph": lambda rb, root: None},
         "unknown battery detector"),
        ([_mutation(["tesst"])], ["graph"], {"graph": lambda rb, root: None},
         "unknown expected detector"),
        ([], ["graph"], {"graph": lambda rb, root: None},
         "contains no mutations"),
    ],
)
def test_invalid_detector_or_empty_selection_returns_two_without_running(
    tmp_path, mutations, battery, checks, message
):
    root = _source_tree(tmp_path)
    stdout, stderr = io.StringIO(), io.StringIO()

    exit_code = audit.run_audit(mutations, battery, root, checks, stdout, stderr)

    assert exit_code == 2
    assert message in stderr.getvalue()
    assert "baseline" not in stdout.getvalue()


@pytest.mark.parametrize(
    "argv", [["--only", ""], ["--only", "definitely-not-a-mutation"], ["--onyl", "egl"]]
)
def test_empty_mistyped_or_unmatched_only_returns_two_before_workspace(
    argv, monkeypatch
):
    def forbidden_workspace(*args, **kwargs):
        raise AssertionError("workspace must not be created for invalid selection")

    monkeypatch.setattr(audit, "isolated_worktree", forbidden_workspace)
    assert audit.main(argv) == 2


def test_fast_mode_skips_pytest_only_mutation_without_failing(tmp_path):
    root = _source_tree(tmp_path)
    calls = []

    def graph(rebuild, check_root):
        calls.append((rebuild, check_root))
        return audit.CommandResult(audit.CommandState.PASS)

    def tests(rebuild, check_root):
        raise AssertionError("pytest must not run in the fast battery")

    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [_mutation(["tests"])], ["graph"], root,
        {"graph": graph, "tests": tests}, stdout, stderr
    )

    assert exit_code == 0
    assert len(calls) == 1  # baseline only; the unowned mutation was not applied
    assert (root / "worm" / "example.py").read_text(encoding="utf8") == "VALUE = 1\n"
    assert "skipped/not-selected" in stdout.getvalue()
    assert "1 mutation(s) skipped because no owning detector was selected" in stdout.getvalue()
    assert "EXECUTED SURVIVOR" not in stdout.getvalue()
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    ("mutation_state", "expected_exit", "expected_status"),
    [
        (audit.CommandState.NONZERO, 0, "CAUGHT"),
        (audit.CommandState.PASS, 1, "executed-but-missed"),
        (audit.CommandState.FAILED, 2, "command-failed"),
    ],
)
def test_full_mode_exit_code_matches_executed_detector_status(
    tmp_path, mutation_state, expected_exit, expected_status
):
    root = _source_tree(tmp_path)
    calls = 0

    def tests(rebuild, check_root):
        nonlocal calls
        calls += 1
        state = audit.CommandState.PASS if calls == 1 else mutation_state
        return audit.CommandResult(state, "detector detail")

    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [_mutation(["tests"])], ["tests"], root, {"tests": tests}, stdout, stderr
    )

    assert exit_code == expected_exit
    assert calls == 2
    assert expected_status in stdout.getvalue()
    assert (root / "worm" / "example.py").read_text(encoding="utf8") == "VALUE = 1\n"
    if mutation_state is audit.CommandState.FAILED:
        assert "Audit incomplete" in stderr.getvalue()


def test_detector_exception_is_command_failure_and_generated_files_are_restored(tmp_path):
    root = _source_tree(tmp_path)
    generated = root / "web" / "worm.wasm"
    generated.parent.mkdir()
    generated.write_bytes(b"original")
    calls = 0

    def tests(rebuild, check_root):
        nonlocal calls
        calls += 1
        if calls == 1:
            return audit.CommandResult(audit.CommandState.PASS)
        generated.write_bytes(b"partial-build")
        raise RuntimeError("runner disappeared")

    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = audit.run_audit(
        [_mutation(["tests"])], ["tests"], root, {"tests": tests}, stdout, stderr
    )

    assert exit_code == 2
    assert generated.read_bytes() == b"original"
    assert "command-failed" in stdout.getvalue()
    assert "runner disappeared" in stdout.getvalue()
    assert "Audit incomplete" in stderr.getvalue()


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def _repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "audit-test@example.invalid")
    _git(repo, "config", "user.name", "Audit Test")
    (repo / "tracked.txt").write_text("committed\n", encoding="utf8")
    (repo / "notes.txt").write_text("initial\n", encoding="utf8")
    (repo / ".gitignore").write_text("node_modules/\nwasm/node_modules/\n", encoding="utf8")
    _git(repo, "add", "tracked.txt", "notes.txt", ".gitignore")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    return repo


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_failure_or_interruption_cleans_workspace_and_preserves_dirty_caller(
    tmp_path, failure
):
    repo = _repository(tmp_path)
    (repo / "notes.txt").write_text("unrelated caller edit\n", encoding="utf8")
    (repo / "untracked-notes.txt").write_text("untracked caller edit\n", encoding="utf8")
    before = audit.caller_snapshot(repo)
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    isolated_path = None

    with pytest.raises(failure):
        with audit.isolated_worktree(repo, temp_base=workspaces) as (isolated, snapshot):
            isolated_path = isolated
            assert snapshot == before
            (isolated / "tracked.txt").write_text("deliberate mutant\n", encoding="utf8")
            (isolated / "generated.bin").write_bytes(b"partial build")
            raise failure("forced audit stop")

    assert isolated_path is not None and not isolated_path.exists()
    assert list(workspaces.iterdir()) == []
    assert (repo / "tracked.txt").read_text(encoding="utf8") == "committed\n"
    assert (repo / "notes.txt").read_text(encoding="utf8") == "unrelated caller edit\n"
    assert (repo / "untracked-notes.txt").read_text(encoding="utf8") == "untracked caller edit\n"
    assert audit.caller_snapshot(repo) == before


def test_caller_integrity_change_is_detected_after_workspace_cleanup(tmp_path):
    repo = _repository(tmp_path)
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()

    with pytest.raises(audit.WorkspaceError, match="caller checkout changed during audit"):
        with audit.isolated_worktree(repo, temp_base=workspaces):
            (repo / "notes.txt").write_text("concurrent caller edit\n", encoding="utf8")

    assert list(workspaces.iterdir()) == []


def test_caller_snapshot_detects_changed_untracked_bytes_at_same_path(tmp_path):
    repo = _repository(tmp_path)
    untracked = repo / "scratch.txt"
    untracked.write_bytes(b"before")
    before = audit.caller_snapshot(repo)

    untracked.write_bytes(b"after!")
    after = audit.caller_snapshot(repo)

    assert before.status == after.status
    assert before.untracked_hash != after.untracked_hash
    assert before != after


def test_caller_snapshot_separately_detects_changed_mm_index_blob(tmp_path):
    repo = _repository(tmp_path)
    tracked = repo / "tracked.txt"
    fixed_worktree = "working tree stays fixed\n"

    tracked.write_text("first staged blob\n", encoding="utf8")
    _git(repo, "add", "tracked.txt")
    tracked.write_text(fixed_worktree, encoding="utf8")
    before = audit.caller_snapshot(repo)

    tracked.write_text("second staged blob\n", encoding="utf8")
    _git(repo, "add", "tracked.txt")
    tracked.write_text(fixed_worktree, encoding="utf8")
    after = audit.caller_snapshot(repo)

    assert tracked.read_text(encoding="utf8") == fixed_worktree
    assert before.status == after.status
    assert before.working_tree_hash == after.working_tree_hash
    assert before.index_hash != after.index_hash
    assert before != after


def test_caller_snapshot_detects_ignored_dependency_link_retarget(tmp_path):
    repo = _repository(tmp_path)
    first = tmp_path / "deps-one"
    second = tmp_path / "deps-two"
    first.mkdir()
    second.mkdir()
    link = repo / "node_modules"
    _make_directory_link(link, first)
    before = audit.caller_snapshot(repo)

    _remove_directory_link(link)
    _make_directory_link(link, second)
    after = audit.caller_snapshot(repo)

    assert before.status == after.status == b""
    assert before.untracked_hash == after.untracked_hash
    assert before.dependency_state_hash != after.dependency_state_hash


def test_changed_untracked_bytes_are_reported_after_workspace_cleanup(tmp_path):
    repo = _repository(tmp_path)
    untracked = repo / "scratch.txt"
    untracked.write_bytes(b"before")
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()

    with pytest.raises(audit.WorkspaceError, match="caller checkout changed during audit"):
        with audit.isolated_worktree(repo, temp_base=workspaces):
            # Keep the same path and byte length, so status alone cannot detect this.
            untracked.write_bytes(b"after!")

    assert list(workspaces.iterdir()) == []


def _pid_is_running(pid):
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return ('"%d"' % pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat_path = Path("/proc") / str(pid) / "stat"
    if stat_path.is_file():
        fields = stat_path.read_text(encoding="ascii").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    return True


def _child_tree_command(child_pid_path):
    parent_code = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "pathlib.Path(sys.argv[2]).write_text(str(child.pid)); "
        "time.sleep(60)"
    )
    return [
        sys.executable,
        "-c",
        parent_code,
        "--audit-tree-parent",
        str(child_pid_path),
    ]


def test_timed_out_detector_kills_child_tree(tmp_path):
    child_pid_path = tmp_path / "timed-out-child.pid"

    result = audit.command(
        _child_tree_command(child_pid_path), tmp_path, timeout=2
    )

    assert result.state is audit.CommandState.FAILED
    assert result.message == "timed out"
    assert child_pid_path.is_file()
    child_pid = int(child_pid_path.read_text(encoding="ascii"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _pid_is_running(child_pid):
        time.sleep(0.05)
    assert not _pid_is_running(child_pid)


def test_interrupted_detector_kills_child_tree_and_cleans_worktree(
    tmp_path, monkeypatch
):
    repo = _repository(tmp_path)
    workspaces = tmp_path / "workspaces"
    workspaces.mkdir()
    child_pid_path = tmp_path / "child.pid"
    command_args = _child_tree_command(child_pid_path)
    original_communicate = subprocess.Popen.communicate

    def interrupt_parent(self, *args, **kwargs):
        if isinstance(self.args, (list, tuple)) and "--audit-tree-parent" in self.args:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not child_pid_path.exists():
                time.sleep(0.02)
            raise KeyboardInterrupt
        return original_communicate(self, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupt_parent)
    isolated_path = None
    with pytest.raises(KeyboardInterrupt):
        with audit.isolated_worktree(repo, temp_base=workspaces) as (isolated, _snapshot):
            isolated_path = isolated
            audit.command(command_args, isolated, timeout=60)

    assert child_pid_path.is_file()
    child_pid = int(child_pid_path.read_text(encoding="ascii"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _pid_is_running(child_pid):
        time.sleep(0.05)
    assert not _pid_is_running(child_pid)
    assert isolated_path is not None and not isolated_path.exists()
    assert list(workspaces.iterdir()) == []
