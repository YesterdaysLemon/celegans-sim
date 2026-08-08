"""The shipped defaults stay on the side of the branch the runtime implements.

`worm/` is a research superset and `wasm/assembly/index.ts` is the canonical browser
animal. Several model paths therefore exist in Python and nowhere else, and that is a
design decision rather than a defect -- counterfactuals, retired mechanisms and half-tested
ideas belong on the Python side.

What is not a design decision is a Python-only path becoming the *default*. That produces a
divergence with no detector:

    Python gains an experimental path, off by default
      -> it measures better, so someone flips the default
      -> the reference animal changes
      -> the runtime keeps implementing the old path, having never implemented the new one
      -> `tools/conform.py` builds from `Params()` and the runtime has no branch to
         disagree about, so conformance passes
      -> the browser and the reference are different animals, and nothing says so

Conformance cannot see it because conformance compares two implementations of one
configuration, and here the second implementation does not exist. This file is that
detector, and it is the whole of it: `tools/export_model.py::RUNTIME_UNSUPPORTED` names each
path and the value the runtime is equivalent to, and the assertion below is that `Params()`
still sits there.

WHAT THIS DOES NOT CONSTRAIN, because a guard that blocked research would be the wrong
trade: it pins the shipped default only. Every tool, test and sweep that constructs a
modified tree is untouched -- `tools/force_velocity.py` passes `fv_vmax=1000` and will keep
passing it. Nothing here looks at a `replace()`d `Params`.

A failure here does not mean the change is wrong. It means it is unfinished, and the
message says what finishing looks like. Removing an entry from the registry is the last step
of porting a path, not a way to make a red test green.

See docs/runtime-parity.md for what each path does and why it is where it is.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tools.export_model import RUNTIME_UNSUPPORTED
from worm.params import Params


def _resolve(params: Params, dotted: str):
    """`"sensory.head_stages"` -> the value, raising rather than returning a default."""
    node = params
    for part in dotted.split("."):
        if not hasattr(node, part):
            raise AttributeError(
                "RUNTIME_UNSUPPORTED names %r, and %r has no attribute %r. A registry entry "
                "that resolves to nothing pins nothing, which is the failure this test "
                "would otherwise have." % (dotted, type(node).__name__, part))
        node = getattr(node, part)
    return node


# An empty registry would make every assertion below vacuous while still reporting a pass --
# exactly the shape of hollow green this repository has shipped three times and now audits
# for. If the last Python-only path is ever ported, delete this file along with the registry
# rather than leaving a check that validates thin air.
def test_the_registry_is_not_empty():
    assert RUNTIME_UNSUPPORTED, (
        "RUNTIME_UNSUPPORTED is empty. If every Python-only path has genuinely been ported, "
        "remove this test file and the registry together; an empty registry passes every "
        "assertion in it while covering nothing.")


@pytest.mark.parametrize("dotted,shipped", sorted(RUNTIME_UNSUPPORTED.items()))
def test_python_only_paths_are_still_off_by_default(dotted, shipped):
    actual = _resolve(Params(), dotted)
    assert actual == shipped, (
        "%s defaults to %r, but the WebAssembly runtime implements only %r.\n"
        "\n"
        "wasm/assembly/index.ts has no branch for this path, so re-exporting cannot carry "
        "it: the browser would keep running the old model while worm/ runs the new one, and "
        "conformance would stay green because both sides are built from this same Params().\n"
        "\n"
        "If you meant to adopt this path, the change is unfinished rather than wrong:\n"
        "  1. implement it in wasm/assembly/index.ts\n"
        "  2. export the constant that selects it from tools/export_model.py\n"
        "  3. extend tools/conform.py and wasm/conform.mjs to cover both sides\n"
        "  4. rebuild web/worm.model and web/worm.wasm as a pair, and run conformance\n"
        "  5. drop %r from RUNTIME_UNSUPPORTED, in this commit\n"
        "\n"
        "If you meant to experiment, pass it to the tool instead of moving the default -- "
        "nothing here looks at a replace()d tree. See docs/runtime-parity.md."
        % (dotted, actual, shipped, dotted))


def test_the_guard_would_actually_fire():
    """A check nobody has watched fail is not known to work. This watches it.

    `tools/audit.py`'s whole premise, applied to the check itself: flip each registered
    default on a copy of the tree and assert the comparison rejects it. Without this, a
    registry entry that silently resolved to the wrong object -- or a comparison that
    coerced `1` to `True` -- would pass forever against an unchanged repository.
    """
    for dotted, shipped in RUNTIME_UNSUPPORTED.items():
        section, field = dotted.split(".", 1)
        params = Params()
        moved = 1.0 if isinstance(shipped, bool) or shipped != 1 else 4
        patched = replace(params, **{section: replace(getattr(params, section), **{field: moved})})
        assert _resolve(patched, dotted) != shipped, (
            "flipping %s to %r did not move it away from the shipped %r, so the assertion "
            "above cannot detect that change" % (dotted, moved, shipped))
