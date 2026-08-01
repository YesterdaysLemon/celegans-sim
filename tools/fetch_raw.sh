#!/bin/sh
# Download only the immutable, hash-verified anatomical inputs approved in
# data/raw_sources.json. The Python helper is standard-library only.
set -eu
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" tools/fetch_raw.py "$@"
