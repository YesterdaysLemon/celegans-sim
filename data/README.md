# Anatomical source updates

`raw_sources.json` is the reviewed allowlist for every byte used to build
`celegans.json`. GitHub inputs use commit-addressed URLs; the WormAtlas workbook uses a
timestamped archival URL. Both byte count and SHA-256 must match before the builder opens
an input.

To reproduce the committed dataset:

```bash
python tools/fetch_raw.py
python tools/build_dataset.py
git diff --exit-code -- data/celegans.json
```

To update a source deliberately:

1. Choose an immutable upstream revision and document its provenance in
   `raw_sources.json`.
2. Update the reviewed byte count and SHA-256, then run the commands above without
   `--exit-code` and inspect the semantic dataset diff.
3. Run the Python tests. If anatomy or exported model values changed, coordinate the
   binary-export lane and regenerate `web/worm.model` and `web/worm.wasm` together; never
   commit only one of that pair.

The `python` GitHub Actions workflow repeats the clean download and dataset rebuild, then
exports and compiles the model/runtime pair together. It compares discrete layout data
exactly and floating-point payloads within a tight tolerance because the exported resting
potential solve can differ in its last bits across BLAS implementations; the regenerated
pair must also pass Python/WASM conformance. A stale dataset, model, layout, or runtime
therefore fails without making cross-platform byte noise look like a scientific change.
