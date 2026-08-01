"""Load the built connectome dataset into dense numpy arrays."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "celegans.json")


class FrozenDict(dict):
    """A small immutable, pickle-safe mapping for shared anatomy metadata."""

    @staticmethod
    def _immutable(*_args, **_kwargs):
        raise TypeError("shared connectome mappings are read-only")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __reduce__(self):
        return type(self), (dict(self),)


class _ImmutableArray(np.ndarray):
    """An ndarray view whose ultimate backing buffer is immutable ``bytes``.

    ``flags.writeable = False`` alone is reversible when an array owns mutable memory.
    Building the view from ``bytes`` makes NumPy itself reject re-enabling writes. The
    custom reducer restores that backing after pickle instead of NumPy allocating ordinary
    mutable storage. Explicit arithmetic results and ``copy()`` remain writable, which is
    exactly what per-animal copy-on-ablation needs.
    """

    def __new__(cls, value):
        array = np.ascontiguousarray(np.asarray(value))
        return np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape).view(cls)

    def __array_finalize__(self, _source):
        pass

    def __reduce_ex__(self, _protocol):
        return _rebuild_immutable_array, (self.dtype, self.shape, self.tobytes())

    def copy(self, order="C") -> np.ndarray:
        """Return an ordinary writable array for intentional per-animal state."""
        return np.array(self, copy=True, order=order, subok=False)


def _rebuild_immutable_array(dtype, shape, payload: bytes) -> _ImmutableArray:
    """Pickle constructor retaining an immutable backing buffer."""
    return np.frombuffer(payload, dtype=dtype).reshape(shape).view(_ImmutableArray)


@dataclass(frozen=True, eq=False)
class Connectome:
    """Immutable anatomy shared by every compatible :class:`Simulation`.

    ``eq=False`` deliberately keeps identity hashing.  The arrays are large and comparing
    two connectomes element by element is neither useful nor compatible with using the
    object as the key for caches of derived anatomy.  ``load`` canonicalises its arguments,
    so equal load requests return this same object instead.
    """

    names: tuple                # neuron names, ordered nose -> tail
    index: Mapping              # name -> row
    soma_pos: np.ndarray        # (N,)   0 = nose, 1 = tail
    kind: tuple                 # sensory / inter / motor / sensory-motor / pharyngeal
    cls: tuple                  # anatomical class, e.g. AVA
    ganglion: tuple
    modality: tuple
    transmitter: tuple
    inhibitory: np.ndarray      # (N,) bool

    gap: np.ndarray             # (N,N) symmetric gap-junction contact counts
    syn: np.ndarray             # (N,N) syn[post, pre] chemical contact counts
    syn_reversal: np.ndarray    # (N,)  reversal potential of synapses *made by* neuron j

    muscle_names: tuple
    muscle_index: Mapping
    muscle_side: np.ndarray     # (M,) +1 dorsal, -1 ventral
    muscle_lr: np.ndarray       # (M,) +1 right, -1 left
    muscle_pos: np.ndarray      # (M,) 0..1 along the body
    nmj: np.ndarray             # (M,N) neuromuscular contact counts
    nmj_reversal: np.ndarray    # (N,)  same convention as syn_reversal

    meta: Mapping

    @property
    def n(self) -> int:
        return len(self.names)

    @property
    def n_muscles(self) -> int:
        return len(self.muscle_names)

    def group(self, *classes: str) -> np.ndarray:
        """Row indices of every neuron in the given anatomical classes."""
        want = set(classes)
        return np.array([i for i, c in enumerate(self.cls) if c in want], dtype=np.intp)

    def select(self, *names: str) -> np.ndarray:
        """Row indices of the named neurons, skipping any that do not exist."""
        return np.array([self.index[n] for n in names if n in self.index], dtype=np.intp)


def _readonly(a: np.ndarray) -> np.ndarray:
    """Copy ``a`` onto immutable backing before it enters a shared cache."""
    if isinstance(a, _ImmutableArray) and not a.flags.writeable:
        return a
    return _ImmutableArray(a)


def _freeze(value):
    """Recursively freeze JSON metadata stored beside the shared arrays."""
    if isinstance(value, dict):
        return FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load(path: str = DATA, e_exc: float = 0.0, e_inh: float = -48.0) -> Connectome:
    """Load, validate once, and share anatomy for a canonical argument triple.

    The public wrapper normalises paths and numeric types before they become cache keys.
    This means ``load()``, ``load(DATA)`` and a relative spelling of the same file do not
    accidentally build independent 1.7 MB copies.  Returned arrays and collections are
    read-only; per-animal state belongs in the simulation subsystems, never here.
    """
    canonical = os.path.normcase(os.path.realpath(os.fspath(path)))
    return _load_cached(canonical, float(e_exc), float(e_inh))


@lru_cache(maxsize=8)
def _load_cached(path: str, e_exc: float, e_inh: float) -> Connectome:
    if not os.path.exists(path):
        raise FileNotFoundError(
            "%s not found -- run tools/fetch_raw.sh then tools/build_dataset.py" % path)
    with open(path) as fh:
        d = json.load(fh)

    neurons = d["neurons"]
    n = len(neurons)
    names = tuple(x["name"] for x in neurons)
    index = {name: i for i, name in enumerate(names)}
    inhibitory = _readonly(np.array([x["inhibitory"] for x in neurons], dtype=bool))

    gap = np.zeros((n, n))
    for i, j, w in d["gap_junctions"]:
        gap[i, j] = w
        gap[j, i] = w

    syn = np.zeros((n, n))
    for pre, post, w, _pol in d["chemical_synapses"]:
        syn[post, pre] += w

    reversal = _readonly(np.where(inhibitory, e_inh, e_exc))

    muscles = d["muscles"]
    m = len(muscles)
    muscle_names = tuple(x["name"] for x in muscles)
    nmj = np.zeros((m, n))
    mindex = {name: i for i, name in enumerate(muscle_names)}
    for pre, mus, w, _pol in d["neuromuscular_junctions"]:
        nmj[mus, pre] += w

    return Connectome(
        names=names,
        index=FrozenDict(index),
        soma_pos=_readonly(np.array([x["soma_pos"] for x in neurons])),
        kind=tuple(x["kind"] for x in neurons),
        cls=tuple(x["cls"] for x in neurons),
        ganglion=tuple(x["ganglion"] for x in neurons),
        modality=tuple(x["modality"] for x in neurons),
        transmitter=tuple(x["transmitter"] for x in neurons),
        inhibitory=inhibitory,
        gap=_readonly(gap),
        syn=_readonly(syn),
        syn_reversal=reversal,
        muscle_names=muscle_names,
        muscle_index=FrozenDict(mindex),
        muscle_side=_readonly(np.array(
            [1.0 if x["side"] == "D" else -1.0 for x in muscles])),
        muscle_lr=_readonly(np.array(
            [1.0 if x["lr"] == "R" else -1.0 for x in muscles])),
        muscle_pos=_readonly(np.array([x["body_pos"] for x in muscles])),
        nmj=_readonly(nmj),
        nmj_reversal=reversal,
        meta=_freeze(d["meta"]),
    )


def clear_cache() -> None:
    """Drop cached anatomy, primarily for tests rebuilding a dataset in place."""
    _load_cached.cache_clear()


def cache_info():
    """Expose cache statistics without making the private loader part of the API."""
    return _load_cached.cache_info()


# Match the familiar functools cache inspection API on the public loader as well as the
# named helpers above. The actual cached function remains private so argument
# canonicalisation happens before keying.
load.cache_clear = _load_cached.cache_clear
load.cache_info = _load_cached.cache_info
