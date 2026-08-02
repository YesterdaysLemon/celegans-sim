"""Exported rate constants must be a function of the repository, not of the machine.

`web/worm.model` and `wasm/assembly/model_gen.ts` are the reason the port's central claim
holds: whatever the two implementations disagree about, it cannot be the *setup*, because
both read the same numbers out of one file. That is only true while re-running the exporter
on an unmodified checkout gives the same file.

It did not. Every rate of the form "one minus a decay" was computed as `1 - exp(-dt/tau)`,
and dt/tau here runs from 5.6e-07 to 1.4e-03, so `exp(-x)` sits a hair under 1 and the
subtraction throws away most of the mantissa -- roughly 12 good digits kept out of 16. Any
last-ulp difference in the platform's `exp` lands squarely in that gap, and #58 recorded it
happening: `MOD_RATE_DOPAMINE` moved from ...751507e-05 to ...762609e-05 with nothing in
the repository changed.

`-expm1(-x)` is exact for small x and identical for large, so this costs nothing and buys
a reproducible artefact. What is asserted here is that nobody quietly puts the other form
back -- which would not fail any behavioural test, because 1e-12 on an adaptation rate
changes no result. That is exactly why it needs its own check.
"""

from __future__ import annotations

import numpy as np
import pytest

from worm import dataset
from worm.egglaying import EggLaying
from worm.modulators import Modulators
from worm.params import Params
from worm.senses import Senses


@pytest.fixture(scope="module")
def rates():
    """Every exported rate of the form 1 - exp(-dt/tau), with the tau it comes from.

    Taken off constructed objects rather than recomputed here, so this compares what the
    exporter would actually write rather than a second implementation of it.
    """
    p = Params()
    dt = p.neural.dt
    conn = dataset.load()
    sen = Senses(conn, p.sensory, p.world, p.body.n_links, p.sensory.proprio_reach, dt)
    mod = Modulators(conn, p.modulator, dt)
    egl = EggLaying(conn, p.egglaying, dt)
    s, m, e = p.sensory, p.modulator, p.egglaying
    out = [
        ("prop_adapt_rate", sen._prop_adapt_rate, dt / s.proprio_tau_adapt),
        ("odour_rate", sen._odour_rate, dt / (2.0 * s.chemo_tau_adapt)),
        ("o2_rate", sen._o2_rate, dt / s.oxygen_tau_adapt),
        ("rep_rate", sen._rep_rate, dt / s.repellent_tau_adapt),
        ("touch_rate", sen._touch_rate, dt / s.touch_tau),
        ("mod_rate_dopamine", mod._rate["dopamine"], dt / m.dopamine_tau),
        ("mod_rate_serotonin", mod._rate["serotonin"], dt / m.serotonin_tau),
        ("mod_rate_octopamine", mod._rate["octopamine"], dt / m.octopamine_tau),
        ("mod_rate_pdf", mod._rate["pdf"], dt / m.pdf_tau),
        ("egl_resource_recover", egl._recover, dt / e.resource_tau),
    ]
    # If a rate stops being constructed this way the list silently shrinks and every
    # assertion below passes over fewer things than it claims to cover.
    assert len(out) == 10, "expected ten exported rates, found %d" % len(out)
    return out


def test_rates_use_expm1(rates):
    """Each rate is exactly `-expm1(-dt/tau)`, bit for bit."""
    for name, value, x in rates:
        want = float(-np.expm1(-x))
        assert value == want, (
            "%s is %.17g; -expm1(-%.6g) is %.17g. The lossy form gives %.17g."
            % (name, value, x, want, 1.0 - np.exp(-x)))


def test_the_two_forms_are_actually_distinguishable(rates):
    """...and the check above can tell the difference, on every one of them.

    Without this, `test_rates_use_expm1` would pass for free on any rate where the two
    expressions happen to agree to the last bit -- and it would keep passing if someone
    reverted that rate to `1 - exp`. Each one has to be a case where the forms genuinely
    differ, or it is not being tested.
    """
    for name, _value, x in rates:
        lossy = 1.0 - np.exp(-x)
        exact = float(-np.expm1(-x))
        assert lossy != exact, (
            "%s: 1 - exp and -expm1 agree bit-for-bit at dt/tau = %.6g, so nothing here"
            " distinguishes them" % (name, x))
        # And the gap is the cancellation the issue describes, not noise: the relative
        # error should be far above the 1.1e-16 of a single rounding.
        rel = abs(lossy - exact) / exact
        assert rel > 1e-14, "%s: relative gap %.2e is too small to be cancellation" % (name, rel)


def test_no_one_reintroduces_one_minus_exp():
    """The source itself, because the values above cannot see a newly added rate.

    A rate added later in the lossy form would not be in the fixture, so the two tests
    above would pass while the artefact went back to being machine-dependent. This reads
    the files instead.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for rel in ("worm/senses.py", "worm/modulators.py", "worm/egglaying.py",
                "worm/nervous.py", "worm/muscle.py", "worm/pharynx.py"):
        for n, line in enumerate((root / rel).read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if "1.0 - np.exp(" in code or "1 - np.exp(" in code:
                offenders.append("%s:%d %s" % (rel, n, line.strip()))
    assert not offenders, (
        "these compute a rate as 1 - exp(-x), which loses most of the mantissa to"
        " cancellation and makes the exported model machine-dependent; use -np.expm1(-x):"
        "\n  " + "\n  ".join(offenders))
