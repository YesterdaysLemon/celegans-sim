"""Failures that an evolutionary evaluator should treat as lethal phenotypes.

These exceptions deliberately distinguish a bad candidate from infrastructure failure.
Population/evaluation code can catch either one and assign fitness zero without swallowing
unrelated programming errors.
"""


class InvalidGenome(ValueError):
    """A parameter set cannot describe a numerically or physically valid animal."""

    lethal = True


class DivergentSimulation(RuntimeError):
    """A once-valid animal has left the simulator's physical/numerical envelope."""

    lethal = True
