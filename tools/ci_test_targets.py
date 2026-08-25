"""Build and run the CI test matrix without wasting runners on tiny files.

Most of the suite finishes in seconds, while behaviour and pharynx contain long,
single-threaded simulations.  CI therefore keeps the small files together, leaves the
medium world assay alone, and selects explicit node IDs for the dense files.  The
explicit lists are validated against the source AST before they are emitted so adding or
renaming a test cannot silently drop it from CI.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def _nodeids(path: str, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{path}::{name}" for name in names)


BEHAVIOUR = "tests/test_behaviour.py"
PHARYNX = "tests/test_pharynx.py"
WORLD = "tests/test_world_depletion.py"

# Keep tests that share an expensive module fixture in the same target.  The groups are
# ordered roughly by observed simulation cost so GitHub starts the slow work first.
SPECIAL_TARGETS: "OrderedDict[str, tuple[str, ...]]" = OrderedDict([
    ("behaviour-gait", _nodeids(BEHAVIOUR, (
        "test_undulation_frequency_on_agar",
        "test_wavelength_on_agar",
        "test_wave_travels_head_to_tail",
        "test_curvature_amplitude",
        "test_dorsoventral_antagonism",
        "test_crawling_speed",
        "test_the_worm_actually_gets_somewhere",
        "test_medium_changes_the_gait",
    ))),
    ("behaviour-physiology", _nodeids(BEHAVIOUR, (
        "test_gait_is_reproducible_across_seeds",
        "test_resting_posture_is_straight",
        "test_membrane_potentials_stay_physiological",
        "test_body_length_is_conserved_in_the_full_loop",
        "test_anterior_touch_drives_a_reversal",
        "test_the_tail_feels_repellent_and_bag_feels_the_downshift",
        "test_the_wave_travels_rather_than_standing",
    ))),
    ("behaviour-learning", _nodeids(BEHAVIOUR, (
        "test_ablation_silences_a_neuron_and_is_reversible",
        "test_ablating_the_forward_command_ends_forward_locomotion",
        "test_habituation_depletes_recovers_and_prefers_short_intervals",
        "test_habituation_is_independent_of_the_timestep",
        "test_rising_attractant_inhibits_aiy",
        "test_improvement_is_chloride_on_aib_and_worsening_is_not",
        "test_a_repellent_at_the_tail_does_not_command_a_reversal",
        "test_a_worm_with_sleep_pressure_stops_and_a_poke_wakes_it",
        "test_sleep_needs_ris",
        "test_omega_gain_of_one_changes_nothing",
        "test_omega_gain_amplifies_only_the_phasic_part",
        "test_proprio_conductance_ships_off_and_replaces_the_current_when_on",
        "test_proprio_conductance_cannot_pin_the_rail",
    ))),
    ("behaviour-omega-trace", _nodeids(BEHAVIOUR, (
        "test_omega_fires_after_the_reversal_and_never_during_it",
        "test_omega_amplitude_follows_reversal_duration",
        "test_omega_drive_is_a_differential_not_a_push",
        "test_omega_wave_suppression_is_inert_between_turns_and_anterior_during_one",
    ))),
    ("behaviour-turning", _nodeids(BEHAVIOUR, (
        "test_omega_turn_actually_turns_the_animal",
        "test_a_modulator_cannot_latch_the_direction_gate",
        "test_direction_gate_guard_detects_a_bypassed_production_clamp",
        "test_the_worm_still_travels_on_a_lawn",
    ))),
    ("pharynx-pump", _nodeids(PHARYNX, (
        "test_pump_rate_matches_a_feeding_animal",
        "test_killing_the_pacemaker_reproduces_eat_2",
    ))),
    ("pharynx-transport", _nodeids(PHARYNX, (
        "test_killing_m4_stops_feeding_without_stopping_pumping",
        "test_killing_m3_lengthens_the_pump",
    ))),
    ("pharynx-accounting", _nodeids(PHARYNX, (
        "test_the_pharynx_is_what_empties_the_lawn",
        "test_food_is_conserved_when_the_animal_moves_between_capture_and_transport",
        "test_an_ablated_source_falls_silent_rather_than_reversing",
    ))),
])


def test_functions(path: str) -> tuple[str, ...]:
    """Return top-level pytest function names without importing simulation code."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    return tuple(
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _validate_special_targets() -> None:
    for path in (BEHAVIOUR, PHARYNX):
        actual = {f"{path}::{name}" for name in test_functions(path)}
        listed = [nodeid for nodes in SPECIAL_TARGETS.values()
                  for nodeid in nodes if nodeid.startswith(path + "::")]
        duplicates = sorted({nodeid for nodeid in listed if listed.count(nodeid) > 1})
        missing = sorted(actual - set(listed))
        unknown = sorted(set(listed) - actual)
        if duplicates or missing or unknown:
            raise AssertionError(
                f"{path} shard manifest is not exact; duplicates={duplicates}, "
                f"missing={missing}, unknown={unknown}"
            )


def target_map() -> "OrderedDict[str, tuple[str, ...]]":
    """Return every CI target and the pytest arguments it owns."""
    _validate_special_targets()
    files = tuple(path.relative_to(ROOT).as_posix()
                  for path in sorted(TESTS.glob("test_*.py")))
    if not files:
        raise AssertionError("no Python tests found")

    dedicated = {BEHAVIOUR, PHARYNX, WORLD}
    unit_files = tuple(path for path in files if path not in dedicated)
    if not unit_files:
        raise AssertionError("unit target parsed to no files")

    targets = OrderedDict(SPECIAL_TARGETS)
    targets["world-depletion"] = (WORLD,)
    targets["unit"] = unit_files
    return targets


def _run(target: str) -> int:
    targets = target_map()
    if target not in targets:
        raise SystemExit(
            "unknown CI test target %r; expected one of %s"
            % (target, ", ".join(targets))
        )
    command = [sys.executable, "-m", "pytest", *targets[target], "-q", "--durations=10"]
    return subprocess.call(command, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", action="store_true", help="print the matrix target IDs")
    group.add_argument("--run", metavar="TARGET", help="run one matrix target")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps(list(target_map()), separators=(",", ":")))
        return 0
    return _run(args.run)


if __name__ == "__main__":
    raise SystemExit(main())
