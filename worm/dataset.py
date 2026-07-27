"""Load the built connectome dataset into dense numpy arrays."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "celegans.json")


@dataclass
class Connectome:
    names: list                 # neuron names, ordered nose -> tail
    index: dict                 # name -> row
    soma_pos: np.ndarray        # (N,)   0 = nose, 1 = tail
    kind: list                  # sensory / inter / motor / sensory-motor / pharyngeal
    cls: list                   # anatomical class, e.g. AVA
    ganglion: list
    modality: list
    transmitter: list
    inhibitory: np.ndarray      # (N,) bool

    gap: np.ndarray             # (N,N) symmetric gap-junction contact counts
    syn: np.ndarray             # (N,N) syn[post, pre] chemical contact counts
    syn_reversal: np.ndarray    # (N,)  reversal potential of synapses *made by* neuron j

    muscle_names: list
    muscle_index: dict
    muscle_side: np.ndarray     # (M,) +1 dorsal, -1 ventral
    muscle_lr: np.ndarray       # (M,) +1 right, -1 left
    muscle_pos: np.ndarray      # (M,) 0..1 along the body
    nmj: np.ndarray             # (M,N) neuromuscular contact counts
    nmj_reversal: np.ndarray    # (N,)  same convention as syn_reversal

    meta: dict

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


def load(path: str = DATA, e_exc: float = 0.0, e_inh: float = -48.0) -> Connectome:
    if not os.path.exists(path):
        raise FileNotFoundError(
            "%s not found -- run tools/fetch_raw.sh then tools/build_dataset.py" % path)
    with open(path) as fh:
        d = json.load(fh)

    neurons = d["neurons"]
    n = len(neurons)
    names = [x["name"] for x in neurons]
    index = {name: i for i, name in enumerate(names)}
    inhibitory = np.array([x["inhibitory"] for x in neurons], dtype=bool)

    gap = np.zeros((n, n))
    for i, j, w in d["gap_junctions"]:
        gap[i, j] = w
        gap[j, i] = w

    syn = np.zeros((n, n))
    for pre, post, w, _pol in d["chemical_synapses"]:
        syn[post, pre] += w

    reversal = np.where(inhibitory, e_inh, e_exc)

    muscles = d["muscles"]
    m = len(muscles)
    muscle_names = [x["name"] for x in muscles]
    nmj = np.zeros((m, n))
    mindex = {name: i for i, name in enumerate(muscle_names)}
    for pre, mus, w, _pol in d["neuromuscular_junctions"]:
        nmj[mus, pre] += w

    return Connectome(
        names=names,
        index=index,
        soma_pos=np.array([x["soma_pos"] for x in neurons]),
        kind=[x["kind"] for x in neurons],
        cls=[x["cls"] for x in neurons],
        ganglion=[x["ganglion"] for x in neurons],
        modality=[x["modality"] for x in neurons],
        transmitter=[x["transmitter"] for x in neurons],
        inhibitory=inhibitory,
        gap=gap,
        syn=syn,
        syn_reversal=reversal,
        muscle_names=muscle_names,
        muscle_index=mindex,
        muscle_side=np.array([1.0 if x["side"] == "D" else -1.0 for x in muscles]),
        muscle_lr=np.array([1.0 if x["lr"] == "R" else -1.0 for x in muscles]),
        muscle_pos=np.array([x["body_pos"] for x in muscles]),
        nmj=nmj,
        nmj_reversal=reversal,
        meta=d["meta"],
    )
