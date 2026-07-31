"""The error bars themselves have to be right, or they are worse than none.

These are cheap -- no simulation, just the statistics and the plumbing that carries a
parameter override into a trial. They exist because every behavioural conclusion this
project draws from here on is going to be read through tools/stats.py, and a bootstrap
that quietly returns the wrong interval would make the reports *more* confident and less
correct at the same time.
"""

from __future__ import annotations

import numpy as np
import pytest

from tools.assays import ASSAYS, apply_overrides, current_params
from tools.stats import (bootstrap_ci, clears_zero, fmt, mde, paired_ci, ratio_ci,
                         verdict)
from worm.params import Params


def test_bootstrap_interval_covers_the_truth_about_as_often_as_it_claims():
    """A 95% interval that covers the true mean 60% of the time is a lie with a number on.

    Coverage is the only property a confidence interval actually promises, so it is worth
    measuring rather than trusting. Sampled at the size the chemotaxis assay actually runs
    at -- sixteen animals -- because coverage degrades with small n and sixteen is what
    the conclusions rest on.
    """
    truth, hits, trials = 0.30, 0, 300
    for i in range(trials):
        rng = np.random.default_rng(1000 + i)
        sample = rng.normal(truth, 0.5, 16)
        _, lo, hi = bootstrap_ci(sample, reps=2000, seed=i)
        hits += lo <= truth <= hi
    cover = hits / trials
    assert 0.86 <= cover <= 0.99, (
        "nominal 95%% interval covered the true mean %.0f%% of the time" % (100 * cover))


def test_pairing_is_sharper_than_not_pairing():
    """The whole argument for common random numbers, checked rather than asserted.

    Two arms differing by a small constant, with animal-to-animal variance much larger
    than the effect. Paired, that variance cancels and the effect is visible; unpaired it
    is buried. If this ever stops being true the paired harness is pointless.
    """
    rng = np.random.default_rng(4)
    animal = rng.normal(0.0, 1.0, 16)          # the variance that pairing removes
    effect = 0.25
    a = animal + rng.normal(0, 0.05, 16)
    b = animal + effect + rng.normal(0, 0.05, 16)

    _, plo, phi = paired_ci(a, b)
    assert clears_zero(plo, phi), "paired comparison missed a %.2f effect" % effect
    assert plo < effect < phi, (plo, effect, phi)

    # The same data compared as two independent samples: the interval on the difference
    # of means is far wider, because it carries both arms' animal variance.
    unpaired = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    paired = (phi - plo) / 4.0                 # roughly one standard error
    assert paired < unpaired / 2.0, (
        "pairing bought less than a factor of two: %.4f against %.4f" % (paired, unpaired))


def test_a_null_result_reports_as_a_null():
    """No effect must read as 'no effect detected', never as a small effect."""
    rng = np.random.default_rng(7)
    a = rng.normal(0.0, 1.0, 16)
    b = a + rng.normal(0.0, 0.001, 16)         # identical up to noise far below any effect
    d, lo, hi = paired_ci(a, b)
    assert abs(d) < 0.01
    c = rng.normal(0.0, 1.0, 16)               # genuinely unrelated
    assert verdict(*paired_ci(a, c)) == "no effect detected"


def test_ratio_interval_survives_a_denominator_near_zero():
    """The pirouette ratio divides two reversal rates, and one of them can be zero.

    An animal that never reverses while conditions improve gives a zero denominator, and
    a naive standard error on the ratio is meaningless there. The interval must come back
    finite-or-NaN and must not raise, because one such animal should not take down the
    whole assay report.
    """
    num = np.array([2.0, 3.0, 1.5, 0.0, 2.5])
    den = np.array([1.0, 0.0, 1.2, 0.0, 2.0])
    point, lo, hi = ratio_ci(num, den)
    assert np.isfinite(point)
    assert not (np.isfinite(lo) and np.isfinite(hi)) or lo <= point <= hi

    allzero = ratio_ci(np.zeros(4), np.zeros(4))
    assert not np.isfinite(allzero[0]) or allzero[0] == 0.0

    assert bootstrap_ci([]) == pytest.approx((float("nan"),) * 3, nan_ok=True)


def test_intervals_are_reproducible():
    """An error bar that moves when you look again invites running it until it agrees."""
    x = np.random.default_rng(11).normal(0.1, 0.4, 20)
    assert bootstrap_ci(x) == bootstrap_ci(x)
    assert ratio_ci(x + 3, x + 4) == ratio_ci(x + 3, x + 4)


def test_formatting_says_what_it_knows():
    assert fmt(0.5, 0.1, 0.9) == "+0.500 [+0.100, +0.900]"
    assert fmt(0.5, float("nan"), float("nan")) == "+0.500"
    assert fmt(float("nan"), 0.0, 1.0) == "n/a"
    assert np.isfinite(mde([1.0, 2.0, 3.0, 4.0]))


# ------------------------------------------------------------------- parameter overrides
def test_overrides_reach_the_model_and_nothing_else():
    """tools/compare.py depends on this: two arms in one queue, differing only here."""
    p = apply_overrides(Params(), {"sensory.omega_current": 111.0,
                                   "modulator.serotonin_mod1": 0.7})
    assert p.sensory.omega_current == 111.0
    assert p.modulator.serotonin_mod1 == 0.7
    assert p.sensory.omega_tau == Params().sensory.omega_tau, "collateral damage"
    assert Params().sensory.omega_current != 111.0, "the default was mutated"
    assert apply_overrides(Params(), {}) is not None


def test_overrides_refuse_to_guess():
    """A typo must fail before a half-hour run, not silently do nothing."""
    for bad in ({"sensory.no_such_field": 1.0}, {"nogroup.x": 1.0}, {"omega_current": 1.0}):
        with pytest.raises(ValueError):
            apply_overrides(Params(), bad)


def test_current_params_is_the_shipped_model_by_default():
    """With no override set, every assay must be measuring the model we ship."""
    assert current_params().sensory.omega_current == Params().sensory.omega_current


def test_paired_cluster_interval_resamples_animals_not_turns():
    from tools.compare import _paired_cluster_ci

    before = [{"turn_mech": [10.0, 20.0]}, {"turn_mech": [30.0]}]
    after = [{"turn_mech": [15.0, 25.0]}, {"turn_mech": [35.0]}]
    a, b, difference, lo, hi = _paired_cluster_ci(
        before, after, np.mean, reps=1000, seed=7)
    assert a == 20.0 and b == 25.0 and difference == 5.0
    assert lo == 5.0 and hi == 5.0


def test_every_assay_reporter_survives_its_own_rows():
    """Formatting changes are the classic way to break a report after the run finishes.

    Each reporter is handed one synthetic row of the shape its job produces, which is
    enough to exercise every format string and every interval. It costs no simulation and
    it catches the failure mode where a thirty-minute assay completes and then dies while
    printing.
    """
    fields = dict(
        seed=0, approach=1.0, ci=0.05, d_final=10.0, c_end=0.3, drift=-1.0, n_rev=3,
        frac_reversing=0.02, dc_rms=0.02, rate_up=1.0, rate_down=2.0, slope=0.5,
        n_fwd=100, heading_drift=20.0,
        o2_mean=0.15, o2_start=0.16, o2_end=0.14, o2_min=0.10,
        start_x=-18.0, t_start=19.4, t_end=20.0, dx=2.0,
        peak=0.3, frac_exposed=0.5, rate_in=5.0, rate_out=0.5, r_end=0.1, r_start=0.2,
        c_min=0.1, c_max=0.5, dc_max=0.05, frac_rev=0.02, gate_f=0.9, gate_b=0.1,
        drive=0.5,
        with_drop=True, final=12.0, dmax=14.0, t_clear=30.0, cleared=True,
    )
    for name, (_job, _jobs, report) in ASSAYS.items():
        # Two shapes have to be satisfied at once. Thermotaxis splits its rows into two
        # starting groups, so give it both or its reporter averages an empty slice and the
        # test passes on a warning. Nociception is paired -- every seed appears twice, once
        # with the drop and once on plain agar -- and with only one arm present it finds no
        # pairs and returns before reaching the format strings this test exists to exercise.
        rows = [dict(fields, seed=i, start_x=(-18.0 if i % 2 else 6.0), with_drop=d,
                     final=12.0 if d else 10.0)
                for i in range(4) for d in (True, False)]
        report(rows)          # must not raise
