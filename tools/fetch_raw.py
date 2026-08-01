"""Download the exact anatomy bytes approved in data/raw_sources.json."""

from __future__ import annotations

import argparse
import os
import time
import urllib.request
from pathlib import Path

try:
    from .raw_sources import MANIFEST, RAW, SourceVerificationError, load_manifest, sha256
except ImportError:  # Executed as ``python tools/fetch_raw.py``.
    from raw_sources import MANIFEST, RAW, SourceVerificationError, load_manifest, sha256


def fetch(
    raw_dir: str | os.PathLike[str] = RAW,
    manifest_path: str | os.PathLike[str] = MANIFEST,
    *,
    check_only: bool = False,
) -> None:
    manifest = load_manifest(manifest_path)
    root = Path(raw_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, source in manifest["sources"].items():
        destination = root / name
        if destination.is_file():
            if (destination.stat().st_size == source["bytes"]
                    and sha256(destination) == source["sha256"]):
                print("verified %s" % name)
                continue
        if check_only:
            raise SourceVerificationError("%s is missing or does not match the manifest" % name)

        temporary = destination.with_suffix(destination.suffix + ".download")
        request = urllib.request.Request(
            source["url"], headers={"User-Agent": "celegans-sim-source-fetch/1"}
        )
        print("fetching %s" % name)
        try:
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=45) as response:
                        with open(temporary, "wb") as handle:
                            while chunk := response.read(1 << 20):
                                handle.write(chunk)
                    last_error = None
                    break
                except Exception as exc:  # Network errors are retried, verification is not.
                    last_error = exc
                    if attempt < 2:
                        time.sleep(1 << attempt)
            if last_error is not None:
                raise SourceVerificationError("could not fetch %s: %s" % (name, last_error))
            size = temporary.stat().st_size
            actual = sha256(temporary)
            if size != source["bytes"] or actual != source["sha256"]:
                raise SourceVerificationError(
                    "%s download did not match manifest: %d bytes, sha256 %s"
                    % (name, size, actual)
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        print("verified %s" % name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify existing inputs without downloading"
    )
    args = parser.parse_args()
    fetch(check_only=args.check)
    print("done. now run: python tools/build_dataset.py")


if __name__ == "__main__":
    try:
        main()
    except SourceVerificationError as exc:
        raise SystemExit("raw source verification failed: %s" % exc) from None
