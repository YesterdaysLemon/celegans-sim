"""Opt-in BLAS thread control for population and parameter-sweep drivers.

The resting-potential solve is only 302 by 302. On some OpenBLAS builds, starting a large
thread team costs far more than this small solve, turning construction of each animal from
milliseconds into hundreds of milliseconds. Environment variables are the portable way
to set the team size, but BLAS reads them when NumPy first loads.

Use this helper at the very top of an executable, before importing NumPy or any simulation
module::

    from worm.threads import pin_blas_threads
    pin_blas_threads(1)

    import numpy as np
    from worm.engine import Simulation

There is intentionally no import-time side effect in :mod:`worm`: a library must not
silently override the host application's threading policy.
"""

from __future__ import annotations

import os
import sys


BLAS_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def pin_blas_threads(threads: int = 1) -> dict[str, str | None]:
    """Set common BLAS thread limits before NumPy loads.

    Returns the previous values for logging. A late call raises instead of pretending to
    fix an already-initialised BLAS runtime. The caller opts in explicitly, so existing
    values are replaced rather than retained by ``setdefault``.
    """
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    if "numpy" in sys.modules:
        raise RuntimeError("pin_blas_threads() must be called before importing numpy")

    previous = {name: os.environ.get(name) for name in BLAS_THREAD_ENV}
    value = str(threads)
    for name in BLAS_THREAD_ENV:
        os.environ[name] = value
    return previous
