import json
import struct
from pathlib import Path

import pytest

from tools.check_model_artifacts import ATOL, ArtifactMismatch, check_artifacts


def _write_artifact_set(
    root: Path,
    *,
    floats: tuple[float, float] = (0.25, -2.0),
    indices: tuple[int, int] = (1, 2),
    gain: float = 1.25,
    layout_gain: float | None = None,
    layout_offset: int = 0,
    wasm: bytes = b"\x00asm\x01\x00\x00\x00tiny",
) -> dict[str, Path]:
    root.mkdir()
    header = {
        "arrays": {
            "float_values": {"dtype": "f8", "shape": [2], "offset": 0, "bytes": 16},
            "indices": {"dtype": "i4", "shape": [2], "offset": 16, "bytes": 8},
        },
        "scalars": {"gain": gain},
        "ints": {"count": 2},
        "strings": {"label": "tiny model"},
    }
    encoded_header = json.dumps(header, separators=(",", ":")).encode()
    payload = struct.pack("<2d2i", *floats, *indices)
    model = root / "worm.model"
    model.write_bytes(
        b"WORM\x01\x00\x00\x00"
        + struct.pack("<I", len(encoded_header))
        + encoded_header
        + payload
    )

    emitted_gain = gain if layout_gain is None else layout_gain
    layout = root / "model_gen.ts"
    layout.write_text(
        "\n".join([
            "// synthetic generated layout",
            f"export const OFF_float_values: usize = {layout_offset};",
            "export const LEN_float_values: i32 = 2;",
            "export const OFF_indices: usize = 16;",
            "export const LEN_indices: i32 = 2;",
            f"export const GAIN: f64 = {emitted_gain!r};",
            "export const COUNT: i32 = 2;",
            "",
        ]),
        encoding="utf-8",
    )
    runtime = root / "worm.wasm"
    runtime.write_bytes(wasm)
    return {"model": model, "layout": layout, "wasm": runtime}


def _check(expected: dict[str, Path], actual: dict[str, Path]) -> bool:
    return check_artifacts(
        expected["model"],
        actual["model"],
        expected["layout"],
        actual["layout"],
        expected["wasm"],
        actual["wasm"],
    )


def test_matching_model_artifact_sets_pass(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    actual = _write_artifact_set(tmp_path / "actual")

    assert _check(expected, actual) is True


def test_small_cross_platform_float_drift_passes(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    drift = ATOL / 10.0
    actual = _write_artifact_set(
        tmp_path / "actual",
        floats=(0.25 + drift, -2.0),
        gain=1.25 + drift,
        wasm=b"platform-specific but conforming wasm bytes",
    )

    # A semantically equal but text-different layout deliberately skips the WASM byte
    # comparison; the workflow exercises that regenerated pair through conformance.
    assert _check(expected, actual) is False


def test_float_drift_beyond_tolerance_fails(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    actual = _write_artifact_set(tmp_path / "actual", floats=(0.250001, -2.0))

    with pytest.raises(ArtifactMismatch, match="model array float_values"):
        _check(expected, actual)


def test_discrete_payload_mismatch_fails(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    actual = _write_artifact_set(tmp_path / "actual", indices=(1, 3))

    with pytest.raises(ArtifactMismatch, match="model array indices"):
        _check(expected, actual)


def test_layout_mismatch_fails(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    actual = _write_artifact_set(tmp_path / "actual", layout_offset=8)

    with pytest.raises(ArtifactMismatch, match=r"regenerated layout\.OFF_float_values"):
        _check(expected, actual)


def test_same_layout_with_changed_wasm_fails(tmp_path):
    expected = _write_artifact_set(tmp_path / "expected")
    actual = _write_artifact_set(tmp_path / "actual", wasm=b"different wasm bytes")

    with pytest.raises(ArtifactMismatch, match="WASM bytes differ"):
        _check(expected, actual)
