"""Fail when committed browser artifacts are stale against a fresh model export.

The model contains a linear solve and other floating-point setup work. Comparing its raw
bytes across BLAS/libm implementations would turn harmless last-bit differences into a CI
failure. This checker instead compares every header field and payload array, exactly for
layout/integer data and at a tight numerical tolerance for floats. The generated
``model_gen.ts`` layout is checked against each model as well as against its committed copy.

The workflow separately recompiles the committed layout and byte-compares that result with
the committed WASM. When a regenerated layout is byte-identical, the regenerated WASM must
also be byte-identical; otherwise conformance tests exercise the regenerated pair together.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


MAGIC = b"WORM\x01\x00\x00\x00"
RTOL = 5e-13
ATOL = 5e-13
_LAYOUT_LINE = re.compile(
    r"^export const ([A-Za-z_][A-Za-z0-9_]*): (usize|i32|f64) = ([^;]+);$"
)


class ArtifactMismatch(RuntimeError):
    """A committed model, generated layout, or runtime artifact is stale."""


@dataclass(frozen=True)
class ModelArtifact:
    path: Path
    header: dict
    arrays: dict[str, np.ndarray]
    payload_bytes: int


def load_model(path: str | Path) -> ModelArtifact:
    model_path = Path(path)
    raw = model_path.read_bytes()
    if len(raw) < 12 or raw[:8] != MAGIC:
        raise ArtifactMismatch(f"{model_path}: invalid model magic or truncated header")
    header_bytes = struct.unpack_from("<I", raw, 8)[0]
    payload_start = 12 + header_bytes
    if payload_start > len(raw):
        raise ArtifactMismatch(f"{model_path}: declared header extends beyond the file")
    try:
        header = json.loads(raw[12:payload_start])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactMismatch(f"{model_path}: invalid JSON header: {exc}") from exc
    required_sections = {"arrays", "scalars", "ints", "strings"}
    if not isinstance(header, dict) or not required_sections.issubset(header):
        found = sorted(header) if isinstance(header, dict) else type(header).__name__
        raise ArtifactMismatch(
            f"{model_path}: header sections are {found}; required {sorted(required_sections)}"
        )

    payload = memoryview(raw)[payload_start:]
    arrays: dict[str, np.ndarray] = {}
    final_byte = 0
    for name, spec in header["arrays"].items():
        try:
            dtype = np.dtype(spec["dtype"]).newbyteorder("<")
            shape = tuple(int(value) for value in spec["shape"])
            offset = int(spec["offset"])
            byte_count = int(spec["bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactMismatch(f"{model_path}: malformed array metadata for {name}") from exc
        expected_bytes = math.prod(shape) * dtype.itemsize
        if offset < 0 or byte_count != expected_bytes or offset + byte_count > len(payload):
            raise ArtifactMismatch(
                f"{model_path}: invalid payload range for {name}: offset={offset}, "
                f"bytes={byte_count}, expected-bytes={expected_bytes}"
            )
        arrays[name] = np.frombuffer(
            payload[offset:offset + byte_count], dtype=dtype
        ).reshape(shape)
        final_byte = max(final_byte, offset + byte_count)
    if final_byte != len(payload):
        raise ArtifactMismatch(
            f"{model_path}: payload has {len(payload)} bytes but arrays end at {final_byte}"
        )
    return ModelArtifact(model_path, header, arrays, len(payload))


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=RTOL, abs_tol=ATOL)


def _compare_float_map(label: str, expected: dict, actual: dict) -> None:
    if set(expected) != set(actual):
        raise ArtifactMismatch(
            f"{label}: keys differ: expected {sorted(expected)}, actual {sorted(actual)}"
        )
    for name, expected_value in expected.items():
        actual_value = actual[name]
        if not _close(float(expected_value), float(actual_value)):
            raise ArtifactMismatch(
                f"{label}.{name}: expected {expected_value!r}, actual {actual_value!r}"
            )


def compare_models(expected: ModelArtifact, actual: ModelArtifact) -> None:
    expected_arrays = expected.header["arrays"]
    actual_arrays = actual.header["arrays"]
    if expected_arrays != actual_arrays:
        raise ArtifactMismatch("model array layouts differ (dtype, shape, offset, or bytes)")
    for section in ("ints", "strings"):
        if expected.header[section] != actual.header[section]:
            raise ArtifactMismatch(f"model {section} differ")
    core_sections = {"arrays", "scalars", "ints", "strings"}
    expected_extra = {
        name: value for name, value in expected.header.items() if name not in core_sections
    }
    actual_extra = {
        name: value for name, value in actual.header.items() if name not in core_sections
    }
    if expected_extra != actual_extra:
        raise ArtifactMismatch("model extension metadata differs")
    _compare_float_map("model scalars", expected.header["scalars"], actual.header["scalars"])
    if expected.payload_bytes != actual.payload_bytes:
        raise ArtifactMismatch(
            f"model payload sizes differ: {expected.payload_bytes} != {actual.payload_bytes}"
        )

    for name, expected_array in expected.arrays.items():
        actual_array = actual.arrays[name]
        if expected_array.dtype.kind in "fc":
            close = np.isclose(expected_array, actual_array, rtol=RTOL, atol=ATOL)
            if not bool(np.all(close)):
                index = tuple(int(value) for value in np.argwhere(~close)[0])
                raise ArtifactMismatch(
                    f"model array {name}{index} differs: "
                    f"expected {expected_array[index]!r}, actual {actual_array[index]!r}"
                )
        elif not np.array_equal(expected_array, actual_array):
            index = tuple(int(value) for value in np.argwhere(expected_array != actual_array)[0])
            raise ArtifactMismatch(
                f"model array {name}{index} differs: "
                f"expected {expected_array[index]!r}, actual {actual_array[index]!r}"
            )


def load_layout(path: str | Path) -> tuple[str, dict[str, tuple[str, int | float]]]:
    layout_path = Path(path)
    text = layout_path.read_text(encoding="utf-8")
    values: dict[str, tuple[str, int | float]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        match = _LAYOUT_LINE.fullmatch(stripped)
        if match is None:
            raise ArtifactMismatch(f"{layout_path}:{line_number}: unrecognised generated line")
        name, kind, raw_value = match.groups()
        value: int | float = float(raw_value) if kind == "f64" else int(raw_value)
        if name in values:
            raise ArtifactMismatch(f"{layout_path}:{line_number}: duplicate constant {name}")
        values[name] = (kind, value)
    return text, values


def _layout_expected_by(model: ModelArtifact) -> dict[str, tuple[str, int | float]]:
    values: dict[str, tuple[str, int | float]] = {}
    for name, spec in model.header["arrays"].items():
        ident = name.replace("-", "_")
        shape = spec["shape"]
        values[f"OFF_{ident}"] = ("usize", int(spec["offset"]))
        values[f"LEN_{ident}"] = ("i32", math.prod(shape))
        if len(shape) == 2:
            values[f"ROWS_{ident}"] = ("i32", int(shape[0]))
            values[f"COLS_{ident}"] = ("i32", int(shape[1]))
    for name, value in model.header["scalars"].items():
        values[name.replace("-", "_").upper()] = ("f64", float(value))
    for name, value in model.header["ints"].items():
        values[name.replace("-", "_").upper()] = ("i32", int(value))
    if "genes" in model.header:
        for slot, name in enumerate(model.header["genes"]):
            ident = str(name).replace("-", "_").upper()
            values[f"GENE_{ident}"] = ("i32", slot)
        values["N_GENES"] = ("i32", len(model.header["genes"]))
    return values


def compare_layout_to_model(
    label: str,
    model: ModelArtifact,
    layout: dict[str, tuple[str, int | float]],
) -> None:
    expected = _layout_expected_by(model)
    if set(expected) != set(layout):
        raise ArtifactMismatch(
            f"{label}: constants differ: expected {sorted(expected)}, actual {sorted(layout)}"
        )
    for name, (expected_kind, expected_value) in expected.items():
        actual_kind, actual_value = layout[name]
        if actual_kind != expected_kind:
            raise ArtifactMismatch(
                f"{label}.{name}: expected type {expected_kind}, actual {actual_kind}"
            )
        if expected_kind == "f64":
            matches = float(expected_value) == float(actual_value)
        else:
            matches = int(expected_value) == int(actual_value)
        if not matches:
            raise ArtifactMismatch(
                f"{label}.{name}: model says {expected_value!r}, layout says {actual_value!r}"
            )


def compare_layouts(
    expected: dict[str, tuple[str, int | float]],
    actual: dict[str, tuple[str, int | float]],
) -> None:
    if set(expected) != set(actual):
        raise ArtifactMismatch("generated layout constant sets differ")
    for name, (expected_kind, expected_value) in expected.items():
        actual_kind, actual_value = actual[name]
        if actual_kind != expected_kind:
            raise ArtifactMismatch(
                f"generated layout {name}: expected type {expected_kind}, actual {actual_kind}"
            )
        if expected_kind == "f64":
            matches = _close(float(expected_value), float(actual_value))
        else:
            matches = int(expected_value) == int(actual_value)
        if not matches:
            raise ArtifactMismatch(
                f"generated layout {name}: expected {expected_value!r}, actual {actual_value!r}"
            )


def check_artifacts(
    expected_model_path: str | Path,
    actual_model_path: str | Path,
    expected_layout_path: str | Path,
    actual_layout_path: str | Path,
    expected_wasm_path: str | Path,
    actual_wasm_path: str | Path,
) -> bool:
    """Check artifacts and return whether layout/WASM bytes were exactly reproducible."""
    expected_model = load_model(expected_model_path)
    actual_model = load_model(actual_model_path)
    expected_layout_text, expected_layout = load_layout(expected_layout_path)
    actual_layout_text, actual_layout = load_layout(actual_layout_path)

    compare_layout_to_model("committed layout", expected_model, expected_layout)
    compare_layout_to_model("regenerated layout", actual_model, actual_layout)
    compare_models(expected_model, actual_model)
    compare_layouts(expected_layout, actual_layout)

    layout_exact = expected_layout_text == actual_layout_text
    if layout_exact:
        expected_wasm = Path(expected_wasm_path).read_bytes()
        actual_wasm = Path(actual_wasm_path).read_bytes()
        if expected_wasm != actual_wasm:
            raise ArtifactMismatch(
                "WASM bytes differ even though the generated layout is byte-identical"
            )
    return layout_exact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-model", required=True)
    parser.add_argument("--actual-model", required=True)
    parser.add_argument("--expected-layout", required=True)
    parser.add_argument("--actual-layout", required=True)
    parser.add_argument("--expected-wasm", required=True)
    parser.add_argument("--actual-wasm", required=True)
    args = parser.parse_args()
    try:
        exact = check_artifacts(
            args.expected_model,
            args.actual_model,
            args.expected_layout,
            args.actual_layout,
            args.expected_wasm,
            args.actual_wasm,
        )
    except (ArtifactMismatch, OSError, ValueError) as exc:
        raise SystemExit(f"model artifact check failed: {exc}") from None
    if exact:
        print("model, generated layout, and WASM reproduce the committed artifact set")
    else:
        print(
            "model and generated layout are semantically unchanged within cross-platform "
            "floating-point tolerance; regenerated pair passed conformance"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
