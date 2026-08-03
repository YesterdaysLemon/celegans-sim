"""Deterministic numeric genomes for the frozen :mod:`worm.params` tree.

``Params`` contains both candidate traits and fixed structure: measured electrophysiology,
anatomical class names, integration switches, and medium names. ``flatten`` exposes every
numeric scalar with a dotted path for inspection and reproducible serialisation, while
``BOUNDS`` is the explicit allow-list of fields an evolutionary driver may mutate.

Reconstruction always creates a new ``Params`` tree. Existing ``Simulation`` instances
have already handed each subsystem its parameters, so changing ``sim.p`` is not a supported
update mechanism; construct a new ``Simulation(unflatten(...), seed=...)`` instead.

The mutable key order deliberately matches the 15 runtime genes introduced by PR #35.
``EXPORT_GENES`` gives their current exporter spellings; the tests compare it directly
with ``tools.export_model.GENES`` so neither side can drift silently.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from numbers import Real
from types import MappingProxyType
from typing import NamedTuple

from .params import Params


class Bound(NamedTuple):
    """Inclusive mutation envelope and characteristic additive step, in native units."""

    low: float
    high: float
    scale: float


# These are conservative engineering search envelopes, not biological confidence
# intervals. The three fields already searched by tools/optimise.py retain that tool's
# ranges; the remaining gains are bounded around the shipped operating point. Crucially,
# this is an allow-list. Measured constants (C_m, reversal potentials, drag, length, EI),
# structural/discrete fields, and known dead parameters such as world.ingestion_rate,
# world.food_diffusion_scale, and body.dt are absent. (world.diffusion_oxygen was on that
# list; #48 deleted the parameter rather than leaving a dead one to name -- see the static
# oxygen note in WorldParams.)
BOUNDS: Mapping[str, Bound] = MappingProxyType({
    # Locomotion: how hard the reflexes drive the body.
    "sensory.proprio_gain": Bound(8.0, 80.0, 5.0),
    "sensory.head_proprio_gain": Bound(40.0, 280.0, 20.0),
    "sensory.cord_drive": Bound(2.0, 20.0, 1.0),
    # Forward/backward decision.
    "sensory.gate_bias": Bound(-0.10, 0.20, 0.01),
    "sensory.gate_hysteresis": Bound(0.02, 0.25, 0.01),
    "sensory.tonic_forward": Bound(10.0, 35.0, 2.0),
    # Steering.
    "sensory.omega_current": Bound(0.0, 800.0, 50.0),
    "sensory.omega_ventral_fraction": Bound(0.0, 1.0, 0.05),
    # Food-sensitive reversal suppression through the serotonin-gated MOD-1 channel.
    # The calibrated sweep in ModulatorParams spans 0.0 through 0.6; leave headroom for
    # selection while keeping the conductance coefficient in a conservative envelope.
    "modulator.serotonin_mod1": Bound(0.0, 1.0, 0.05),
    # One live gain per sensory channel.
    "sensory.chemo_gain": Bound(0.0, 100.0, 5.0),
    "sensory.thermo_gain": Bound(0.0, 40.0, 2.0),
    "sensory.oxygen_gain": Bound(0.0, 200.0, 10.0),
    "sensory.repellent_d_gain": Bound(0.0, 12000.0, 500.0),
    "sensory.food_gain": Bound(0.0, 50.0, 3.0),
    "sensory.touch_gain": Bound(0.0, 250.0, 15.0),
})

MUTABLE_KEYS = tuple(BOUNDS)


def _export_name(key: str) -> str:
    section, name = key.split(".", 1)
    prefix = {"sensory": "sen", "modulator": "mod"}.get(section, section)
    return "%s_%s" % (prefix, name)


EXPORT_GENES = tuple(_export_name(key) for key in MUTABLE_KEYS)


def _numeric_items(params: Params):
    """Yield numeric scalar leaves in dataclass declaration order."""
    if not isinstance(params, Params):
        raise TypeError("params must be a Params instance")
    for section_field in fields(params):
        section_name = section_field.name
        section = getattr(params, section_name)
        if not is_dataclass(section):
            continue
        for leaf_field in fields(section):
            value = getattr(section, leaf_field.name)
            # Bool is an int subclass, but switches are structural rather than continuous
            # genes and coercing them to 0.0/1.0 would lose that distinction.
            if isinstance(value, Real) and not isinstance(value, bool):
                yield "%s.%s" % (section_name, leaf_field.name), value


def flatten(params: Params, *, mutable_only: bool = False) -> dict[str, float]:
    """Return a deterministic dotted-key projection of numeric ``Params`` leaves.

    With ``mutable_only=True`` the result is the actual 15-value genome, in ``BOUNDS``
    order. Otherwise measured and diagnostic numeric fields are included for lossless
    numeric reconstruction, but their presence does not make them mutable.
    """
    numeric = {key: float(value) for key, value in _numeric_items(params)}
    if mutable_only:
        return {key: numeric[key] for key in MUTABLE_KEYS}
    return numeric


def validate(values: Mapping[str, Real], *, base: Params | None = None,
             mutable_only: bool = False,
             require_complete: bool = False) -> dict[str, float]:
    """Validate and canonically order a full or partial numeric parameter mapping.

    Mutable mappings are additionally restricted to ``BOUNDS`` and checked against their
    inclusive envelopes. Integer-valued configuration fields in a full mapping must remain
    integral. Unknown, structural, boolean, and non-finite values fail loudly.
    """
    if not isinstance(values, Mapping):
        raise TypeError("values must be a mapping of dotted keys to numbers")
    non_string = [key for key in values if not isinstance(key, str)]
    if non_string:
        raise TypeError("parameter keys must be strings, got %r" % non_string[0])
    params = Params() if base is None else base
    expected_values = dict(_numeric_items(params))
    expected = MUTABLE_KEYS if mutable_only else tuple(expected_values)

    unknown = sorted(set(values) - set(expected))
    if unknown:
        kind = "mutable" if mutable_only else "numeric"
        raise KeyError("unknown or non-%s parameter keys: %s" % (kind, ", ".join(unknown)))
    if require_complete:
        missing = [key for key in expected if key not in values]
        if missing:
            raise ValueError("missing parameter keys: %s" % ", ".join(missing))

    normalised = {}
    for key in expected:
        if key not in values:
            continue
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("%s must be a real number, got %r" % (key, value))
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("%s must be finite, got %r" % (key, value))
        current = expected_values[key]
        if isinstance(current, int) and not number.is_integer():
            raise ValueError("%s is integer-valued, got %r" % (key, value))
        if mutable_only:
            bound = BOUNDS[key]
            if number < bound.low or number > bound.high:
                raise ValueError("%s=%r is outside [%r, %r]"
                                 % (key, number, bound.low, bound.high))
        normalised[key] = number
    return normalised


def unflatten(values: Mapping[str, Real], *, base: Params | None = None,
              mutable_only: bool = False,
              require_complete: bool = False) -> Params:
    """Return a new ``Params`` with numeric dotted-key values applied.

    ``values`` may be partial. Non-numeric structure is inherited from ``base`` (or the
    shipped defaults), so callers serialising a configuration with different tuple/string
    structure should retain and pass that base explicitly. Use ``mutable_only=True`` for
    evolutionary input: it rejects fixed fields and enforces ``BOUNDS``.
    """
    params = Params() if base is None else base
    normalised = validate(values, base=params, mutable_only=mutable_only,
                          require_complete=require_complete)
    by_section: dict[str, dict[str, object]] = {}
    for key, number in normalised.items():
        section_name, leaf_name = key.split(".", 1)
        current = getattr(getattr(params, section_name), leaf_name)
        integer_field = isinstance(current, int) and not isinstance(current, bool)
        value = int(number) if integer_field else number
        by_section.setdefault(section_name, {})[leaf_name] = value

    sections = {
        name: replace(getattr(params, name), **updates)
        for name, updates in by_section.items()
    }
    return replace(params, **sections)
