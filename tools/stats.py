"""Error bars, and the paired comparison that makes them affordable.

This exists because of a run of decisions made on differences that were inside the noise.
The chemotaxis assay is sixteen animals whose approach distances scatter by +-12 mm about
a mean of -10, and a chemotaxis index quoted as "+0.070" from that sample carries an
uncertainty of roughly +-0.09 -- which is to say it is not distinguishable from zero, and
certainly not from "+0.014". Several days of this project compared two such numbers and
believed the difference.

Two things fix it, and only one of them costs anything.

**Confidence intervals.** Bootstrapped rather than assumed normal, because the samples are
small, several of the headline statistics are *ratios* of noisy quantities (the pirouette
ratio is the obvious one) and a ratio of two things that straddle zero has no useful
standard error. Resampling animals with replacement and recomputing the whole statistic
handles all of that without anyone having to derive anything.

**Common random numbers.** This is the free one, and it matters more. Comparing two
configurations by running each on its own seeds throws away the fact that most of the
variance is *which animal you got*, not which configuration it ran under. Run both arms on
the same seeds and that variance cancels in the difference: what is left is the treatment
effect and whatever the treatment did to the trajectory. Measured on this model, the paired
standard error on the chemotaxis index is several times smaller than the unpaired one, so
the same wall clock buys a much sharper answer -- and the wall clock is the binding
constraint, at half an hour a run.

The bootstrap is seeded, so a reported interval is reproducible. That is not a detail: an
error bar that moves when you look at it again is worse than no error bar, because it
invites exactly the "run it until it agrees" search these intervals exist to prevent.
"""

from __future__ import annotations

import numpy as np

BOOTSTRAP = 20000
CONF = 0.95


def _resample(rng, n, reps):
    return rng.integers(0, n, size=(reps, n))


def bootstrap_ci(values, stat=np.mean, conf: float = CONF,
                 reps: int = BOOTSTRAP, seed: int = 0):
    """(point estimate, low, high) for any statistic of one sample.

    `stat` is applied to a resampled copy of `values`, so it may be anything -- a mean, a
    median, a fraction above a threshold. Returns NaNs rather than raising on an empty
    sample, because a missing assay row should not take the whole report down.
    """
    v = np.asarray([x for x in np.atleast_1d(values) if np.isfinite(x)], dtype=float)
    if v.size == 0:
        return float("nan"), float("nan"), float("nan")
    if v.size == 1:
        return float(stat(v)), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = np.array([stat(v[i]) for i in _resample(rng, v.size, reps)])
    lo, hi = np.percentile(draws, [100 * (1 - conf) / 2, 100 * (1 + conf) / 2])
    return float(stat(v)), float(lo), float(hi)


def ratio_ci(num, den, conf: float = CONF, reps: int = BOOTSTRAP, seed: int = 0):
    """(ratio of means, low, high), resampling *animals* rather than the two rates.

    For statistics like the pirouette ratio, which is one rate divided by another and where
    both are measured on the same animal. Resampling the pair together keeps that pairing,
    which a separate interval on each rate would throw away.
    """
    a = np.asarray(num, dtype=float)
    b = np.asarray(den, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if a.size == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(a.mean() / b.mean()) if b.mean() > 1e-12 else float("nan")
    if a.size == 1:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = _resample(rng, a.size, reps)
    bm = b[idx].mean(axis=1)
    draws = np.where(bm > 1e-12, a[idx].mean(axis=1) / np.where(bm > 1e-12, bm, 1.0),
                     np.nan)
    draws = draws[np.isfinite(draws)]
    if draws.size == 0:
        return point, float("nan"), float("nan")
    lo, hi = np.percentile(draws, [100 * (1 - conf) / 2, 100 * (1 + conf) / 2])
    return point, float(lo), float(hi)


def paired_ci(before, after, conf: float = CONF, reps: int = BOOTSTRAP, seed: int = 0):
    """(mean difference, low, high) for two arms run on the *same* seeds.

    `before` and `after` must be aligned element by element -- same animal, same plate,
    same starting bearing, differing only in the configuration under test. Resampling is
    over animals, so each draw keeps a pair together and the between-animal variance
    cancels exactly as it does in the point estimate.
    """
    a = np.asarray(before, dtype=float)
    b = np.asarray(after, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired arms have different shapes: %r vs %r" % (a.shape, b.shape))
    d = b - a
    d = d[np.isfinite(d)]
    return bootstrap_ci(d, np.mean, conf=conf, reps=reps, seed=seed)


def spread(values) -> float:
    """Standard error of the mean, for reporting how noisy a sample was."""
    v = np.asarray([x for x in np.atleast_1d(values) if np.isfinite(x)], dtype=float)
    return float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else float("nan")


def mde(values, conf: float = CONF) -> float:
    """Roughly the smallest effect this sample size could have detected.

    Two standard errors, which is the usual rule of thumb for a difference of means to
    clear a 95% interval. Reported alongside a null result so that "no effect" can be read
    as "no effect larger than this", which is the only thing the measurement supports.
    """
    return 2.0 * spread(values) * (1.0 if conf == CONF else 1.0)


def fmt(point, lo, hi, spec: str = "%+.3f") -> str:
    """`+0.083 [-0.021, +0.180]`, or the point alone when there is no interval."""
    if not np.isfinite(point):
        return "n/a"
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return spec % point
    return "%s [%s, %s]" % (spec % point, spec % lo, spec % hi)


def clears_zero(lo, hi) -> bool:
    """Does the interval exclude zero? The only question a difference has to answer."""
    return bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0.0 or hi < 0.0))


def verdict(point, lo, hi) -> str:
    """A one-word reading of a paired difference, so reports do not have to editorialise."""
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "single sample"
    if lo > 0.0:
        return "better"
    if hi < 0.0:
        return "worse"
    return "no effect detected"
