#!/bin/sh
# Re-download the primary anatomical sources. The checksums of whatever this pulls are
# recorded in data/celegans.json under meta.sources, so a silent upstream change is
# visible in the built dataset's diff.
set -eu
cd "$(dirname "$0")/.."
mkdir -p data/raw
cd data/raw

fetch() {
  echo "fetching $1"
  curl -fsSL --retry 3 -o "$(basename "$1")" "$1"
}

fetch "https://raw.githubusercontent.com/openworm/c302/master/c302/data/CElegansNeuronTables.xls"
fetch "https://raw.githubusercontent.com/openworm/c302/master/c302/data/herm_full_edgelist.csv"
fetch "https://www.wormatlas.org/images/NeuronType.xls"

echo "done. now run: .venv/bin/python tools/build_dataset.py"
