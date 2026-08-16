"""The optimized CI matrix must cover the same tests exactly once."""

from __future__ import annotations

from pathlib import Path

from tools.ci_test_targets import (
    BEHAVIOUR,
    PHARYNX,
    ROOT,
    SPECIAL_TARGETS,
    target_map,
    test_functions as source_test_functions,
)


def test_dense_test_functions_are_selected_exactly_once():
    for path in (BEHAVIOUR, PHARYNX):
        expected = {f"{path}::{name}" for name in source_test_functions(path)}
        selected = [nodeid for nodes in SPECIAL_TARGETS.values()
                    for nodeid in nodes if nodeid.startswith(path + "::")]
        assert set(selected) == expected
        assert len(selected) == len(set(selected)), "a dense test would run twice"


def test_every_test_file_belongs_to_exactly_one_kind_of_target():
    targets = target_map()
    all_files = {
        path.relative_to(ROOT).as_posix()
        for path in Path(ROOT / "tests").glob("test_*.py")
    }
    owners = {path: [] for path in all_files}
    for target, pytest_args in targets.items():
        for argument in pytest_args:
            path = argument.split("::", 1)[0]
            owners[path].append(target)

    assert set(owners) == all_files
    for path, target_names in owners.items():
        if path in (BEHAVIOUR, PHARYNX):
            assert len(set(target_names)) > 1
        else:
            assert len(target_names) == 1, (path, target_names)


def test_shared_simulations_stay_in_one_process():
    targets = target_map()

    def owner(nodeid: str) -> str:
        matches = [name for name, nodeids in targets.items() if nodeid in nodeids]
        assert len(matches) == 1, (nodeid, matches)
        return matches[0]

    assert owner(f"{BEHAVIOUR}::test_undulation_frequency_on_agar") == owner(
        f"{BEHAVIOUR}::test_medium_changes_the_gait")
    assert owner(f"{BEHAVIOUR}::test_omega_fires_after_the_reversal_and_never_during_it") == owner(
        f"{BEHAVIOUR}::test_omega_amplitude_follows_reversal_duration")
    assert owner(f"{PHARYNX}::test_killing_the_pacemaker_reproduces_eat_2") == owner(
        f"{PHARYNX}::test_pump_rate_matches_a_feeding_animal")


def test_dense_targets_are_scheduled_before_the_unit_batch():
    names = list(target_map())
    assert names[-2:] == ["world-depletion", "unit"]
