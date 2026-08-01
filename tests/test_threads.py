"""The BLAS helper is explicit and must run before NumPy."""

import os
import subprocess
import sys

import pytest

from worm.threads import BLAS_THREAD_ENV, pin_blas_threads


def test_pin_blas_threads_in_fresh_interpreter():
    code = (
        "from worm.threads import BLAS_THREAD_ENV, pin_blas_threads; "
        "old = pin_blas_threads(1); import os, numpy; "
        "print(','.join(os.environ[x] for x in BLAS_THREAD_ENV))"
    )
    env = os.environ.copy()
    for name in BLAS_THREAD_ENV:
        env[name] = "8"
    result = subprocess.run([sys.executable, "-c", code], cwd=os.getcwd(), env=env,
                            check=True, capture_output=True, text=True)
    assert result.stdout.strip() == ",".join("1" for _ in BLAS_THREAD_ENV)


def test_late_pin_fails_instead_of_claiming_to_change_loaded_blas():
    import numpy  # noqa: F401 -- the loaded state is the condition under test

    assert "numpy" in sys.modules
    with pytest.raises(RuntimeError, match="before importing numpy"):
        pin_blas_threads(1)


@pytest.mark.parametrize("threads", [0, -1, 1.5, True])
def test_pin_rejects_invalid_thread_counts(threads):
    with pytest.raises(ValueError):
        pin_blas_threads(threads)
