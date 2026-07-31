"""Content-hash the runtime assets, so `immutable` caching is actually safe.

The .wasm has the .model's byte offsets compiled into it (tools/export_model.py emits
model_gen.ts). They are a matched pair: serving a new .wasm against a cached .model would
not degrade gracefully, it would read the wrong offsets and produce garbage.

Both are served with a one-year immutable cache, which is right for files that never
change at a given URL and wrong for files that do. And they *do* change: the exported
model is not bit-reproducible across numpy builds, because `_resting_potentials` goes
through LAPACK. Rebuilding the container moved every resting potential by ~6e-14 -- nothing
numerically, but a different file at the same URL, which is all a cache cares about.

So the URLs carry a content hash and the manifest that names them does not get cached.

Run:  PYTHONPATH=. .venv/bin/python tools/manifest.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

ASSETS = ["worm.wasm", "worm.model"]


def main():
    web = sys.argv[1] if len(sys.argv) > 1 else "web"
    out = {}
    for name in ASSETS:
        path = os.path.join(web, name)
        if not os.path.exists(path):
            print("missing %s" % path, file=sys.stderr)
            return 1
        with open(path, "rb") as fh:
            out[name] = hashlib.sha256(fh.read()).hexdigest()[:12]
    with open(os.path.join(web, "build.json"), "w") as fh:
        json.dump(out, fh)
    print("build.json: " + "  ".join("%s=%s" % kv for kv in out.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
