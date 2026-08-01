import hashlib
import json
from pathlib import Path

import pytest

from tools.raw_sources import (
    MANIFEST,
    SourceVerificationError,
    load_manifest,
    verify_raw_sources,
)


ROOT = Path(__file__).resolve().parent.parent


def _write_manifest(path: Path, name: str, payload: bytes) -> None:
    path.write_text(json.dumps({
        "schema": 1,
        "sources": {
            name: {
                "url": "https://example.invalid/source",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "origin": "test fixture",
                "provenance": "test fixture",
            }
        },
    }), encoding="utf-8")


def test_raw_source_manifest_uses_immutable_locations():
    sources = load_manifest(MANIFEST)["sources"]
    assert set(sources) == {
        "CElegansNeuronTables.xls",
        "NeuronType.xls",
        "herm_full_edgelist.csv",
    }
    for name in ("CElegansNeuronTables.xls", "herm_full_edgelist.csv"):
        url = sources[name]["url"]
        assert "/master/" not in url
        assert "aad88a80aa7f217fe109a89f4b68ccb043430722" in url
    assert "/web/20101129153859id_/" in sources["NeuronType.xls"]["url"]


def test_dataset_embeds_the_reviewed_source_manifest():
    sources = load_manifest(MANIFEST)["sources"]
    with open(ROOT / "data" / "celegans.json", encoding="utf-8") as handle:
        embedded = json.load(handle)["meta"]["sources"]
    assert embedded == {
        name: {
            "sha256": source["sha256"],
            "origin": source["origin"],
            "provenance": source["provenance"],
            "url": source["url"],
        }
        for name, source in sources.items()
    }


def test_raw_source_verification_accepts_only_exact_bytes(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    manifest = tmp_path / "manifest.json"
    expected = b"reviewed anatomy bytes"
    _write_manifest(manifest, "source.bin", expected)
    (raw / "source.bin").write_bytes(expected)

    assert verify_raw_sources(raw, manifest) == {"source.bin": raw / "source.bin"}

    (raw / "source.bin").write_bytes(b"unexpected upstream replacement")
    with pytest.raises(SourceVerificationError, match="bytes; expected"):
        verify_raw_sources(raw, manifest)

    (raw / "source.bin").write_bytes(b"x" * len(expected))
    with pytest.raises(SourceVerificationError, match="sha256 is"):
        verify_raw_sources(raw, manifest)
