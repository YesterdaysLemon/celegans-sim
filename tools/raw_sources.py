"""Pinned raw-anatomy source manifest and fail-closed verification helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "raw_sources.json"
RAW = ROOT / "data" / "raw"
REQUIRED_FIELDS = {"url", "bytes", "sha256", "origin", "provenance"}


class SourceVerificationError(RuntimeError):
    """An anatomy input is missing, malformed, or different from its approved bytes."""


def sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: str | os.PathLike[str] = MANIFEST) -> dict:
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema") != 1:
        raise SourceVerificationError("raw source manifest schema must be 1")
    sources = manifest.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise SourceVerificationError("raw source manifest has no sources")
    for name, source in sources.items():
        if Path(name).name != name:
            raise SourceVerificationError("raw source name is not a basename: %r" % name)
        if not isinstance(source, dict):
            raise SourceVerificationError("%s manifest entry is not an object" % name)
        missing = REQUIRED_FIELDS - set(source)
        if missing:
            raise SourceVerificationError(
                "%s is missing manifest fields: %s" % (name, ", ".join(sorted(missing)))
            )
        expected = source["sha256"]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in "0123456789abcdef" for char in expected)):
            raise SourceVerificationError("%s has an invalid sha256" % name)
        if (not isinstance(source["bytes"], int) or isinstance(source["bytes"], bool)
                or source["bytes"] < 1):
            raise SourceVerificationError("%s has an invalid byte count" % name)
        if not isinstance(source["url"], str) or not source["url"].startswith("https://"):
            raise SourceVerificationError("%s does not use an HTTPS source URL" % name)
    return manifest


def verify_raw_sources(
    raw_dir: str | os.PathLike[str] = RAW,
    manifest_path: str | os.PathLike[str] = MANIFEST,
) -> dict[str, Path]:
    """Return approved raw paths, rejecting missing or byte-different inputs."""
    manifest = load_manifest(manifest_path)
    root = Path(raw_dir)
    verified: dict[str, Path] = {}
    for name, source in manifest["sources"].items():
        path = root / name
        if not path.is_file():
            raise SourceVerificationError(
                "missing raw input: %s (run tools/fetch_raw.py)" % path
            )
        size = path.stat().st_size
        if size != source["bytes"]:
            raise SourceVerificationError(
                "%s has %d bytes; expected %d" % (name, size, source["bytes"])
            )
        actual = sha256(path)
        if actual != source["sha256"]:
            raise SourceVerificationError(
                "%s sha256 is %s; expected %s" % (name, actual, source["sha256"])
            )
        verified[name] = path
    return verified


def dataset_source_metadata(manifest_path: str | os.PathLike[str] = MANIFEST) -> dict:
    """The reviewed provenance subset embedded in the generated dataset."""
    manifest = load_manifest(manifest_path)
    fields = ("sha256", "origin", "provenance", "url")
    return {
        name: {field: source[field] for field in fields}
        for name, source in manifest["sources"].items()
    }
