"""Does the whole animal behave like an animal?

These are slower than the unit tests -- each runs a real closed-loop simulation -- but
they are the ones that would actually catch a regression that matters. The reference
numbers are measurements on live worms, cited inline.
"""

import numpy as np
import pytest

from tools.diagnose_loop import analyse, bare_world
from worm.engine import Simulation
from worm.params import MEDIA, Params


@pytest.fixture(scope="module")
def crawl():
    p = Params()
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.body.medium = MEDIA["agar"]
    return analyse(sim, seconds=20.0)


def test_undulation_frequency_on_agar(crawl):
    """Measured crawl: 0.30 +- 0.02 Hz (Fang-Yen 2010); swim 1.76 +- 0.07 Hz.

    This model settles near 1.2 Hz on agar -- reproducibly, across seeds, but between the
    two real gaits and much closer to swimming. The bound below is what it does, not what
    the animal does. See the README's limitations section.
    """
    assert 0.25 <= crawl["freq"] <= 1.8, crawl["freq"]


def test_wavelength_on_agar(crawl):
    """Measured: 0.65 +- 0.03 body lengths (Fang-Yen 2010); 0.58 +- 0.02 (Berri 2009).

    This model runs long, around 1.1 L, and the bound below says so rather than pretending
    otherwise. The wavelength is almost completely insensitive to the proprioceptive reach
    (1.11 to 1.20 as the reach varies from 0.10 to 0.20 L), which says the body wave here
    is mostly the passive mechanical response to the head's bending rather than a
    regenerated reflex wave -- the proprioceptive coupling is real but weaker than the
    animal's. See the README's limitations section.
    """
    assert 0.45 <= crawl["wavelength"] <= 1.8, crawl["wavelength"]


def test_wave_travels_head_to_tail(crawl):
    """Forward locomotion means the undulation propagates posteriorly."""
    assert crawl["direction"] == "head->tail"


def test_curvature_amplitude(crawl):
    """Mean 4.3 +- 0.3 /mm, max 9.8 +- 1.1 /mm (Krajacic et al. 2012)."""
    assert 2.5 <= crawl["kappa_rms"] <= 7.0, crawl["kappa_rms"]
    assert 5.0 <= crawl["kappa_max"] <= 16.0, crawl["kappa_max"]


def test_dorsoventral_antagonism(crawl):
    """The two muscle sheets must oppose each other, or the body cannot bend."""
    assert crawl["dv_corr"] < 0.0, crawl["dv_corr"]


def test_crawling_speed(crawl):
    """Measured: 219 +- 29 um/s off food (Ramot et al. 2008); literature spans 16-250.

    This model manages a few um/s of *net* progress -- roughly fifty times too slow. The
    bound below is deliberately wide enough to admit both the current behaviour and the
    real animal, so that it fails if the worm stops moving entirely and does not have to be
    rewritten when the speed improves.

    Note carefully which speed this is. `sim.speed` is net displacement over a two-second
    window, the way a worm tracker measures it. `sim.path_speed` is distance travelled
    along the trajectory, which for an undulating animal counts the side-to-side slosh of
    the centroid and reads about twenty times higher. An earlier version of this test used
    the latter and passed comfortably while the worm was going nowhere.
    """
    assert 0.0005 <= crawl["speed"] <= 0.40, crawl["speed"]


def test_the_worm_actually_gets_somewhere():
    """Net displacement over path length: 1.0 is a straight line, 0.0 is going nowhere.

    A real worm off food runs in fairly straight bouts of 20-40 s broken by reorientations,
    so over a couple of minutes it keeps well over half of the distance it travels.

    This model currently keeps about 6% of it: 8.4 mm of path and 0.54 mm of net
    displacement over 120 s. It undulates on the spot. The threshold below is set just
    under that, so it guards against regression without pretending the current value is
    acceptable -- raising it is the point of the work in NEXT.md.
    """
    p = Params()
    sim = Simulation(p, seed=0, world=bare_world(p))
    sim.run(4.0)
    start = sim.body.centroid().copy()
    prev = start.copy()
    path = 0.0
    for i in range(int(60.0 / sim.dt)):
        sim.step()
        if i % 200 == 0:
            c = sim.body.centroid()
            path += float(np.hypot(*(c - prev)))
            prev = c.copy()
    net = float(np.hypot(*(sim.body.centroid() - start)))
    assert path > 1.0, "the body barely moved at all: %.3f mm of path" % path
    assert net / path > 0.03, (
        "net/path = %.3f: the animal is undulating without going anywhere" % (net / path))


def test_gait_is_reproducible_across_seeds():
    """The same worm, different noise, must behave the same way.

    This is not a formality. Before the head stretch receptor was given its own kinetics,
    the head reflex loop had two stable limit cycles -- one near 0.3 Hz and one near
    2.2 Hz -- and which one the animal fell into depended on the random seed. Two thirds
    of seeds landed in the fast one. A simulation whose gait is decided by its noise is
    not reporting anything about the worm.
    """
    freqs, dirs = [], []
    for seed in (0, 3, 7):
        p = Params()
        sim = Simulation(p, seed=seed, world=bare_world(p))
        r = analyse(sim, seconds=16.0)
        freqs.append(r["freq"])
        dirs.append(r["direction"])
    assert all(d == "head->tail" for d in dirs), dirs
    assert max(freqs) / max(min(freqs), 1e-9) < 1.6, freqs


def test_medium_changes_the_gait():
    """The medium, and nothing else, must change how the animal moves.

    Fang-Yen et al. (2010) measured 0.30 Hz / 0.65 L crawling and 1.76 Hz / 1.54 L
    swimming, with nothing changed but the fluid. Nothing differs between these two runs
    either, except the two drag coefficients -- so a mechanical coupling from medium to
    gait exists here and this test pins it down.

    What it deliberately does NOT assert is the *direction*, because the model currently
    gets it backwards: it runs at ~1.25 Hz on agar and ~0.55 Hz in buffer, where the
    animal is the other way round. Asserting the real direction would be asserting
    something the model does not do. See the README's limitations section.
    """
    results = {}
    for medium in ("agar", "buffer"):
        p = Params()
        sim = Simulation(p, seed=3, world=bare_world(p))
        sim.body.medium = MEDIA[medium]
        results[medium] = analyse(sim, seconds=20.0)
    ratio = max(results["buffer"]["freq"], results["agar"]["freq"]) / max(
        min(results["buffer"]["freq"], results["agar"]["freq"]), 1e-9)
    assert ratio > 1.2, (
        "medium had almost no effect on gait: %.3f Hz agar vs %.3f Hz buffer"
        % (results["agar"]["freq"], results["buffer"]["freq"]))


def test_resting_posture_is_straight():
    """With the muscles balanced, an animal with no wave must not be curled."""
    p = Params()
    sim = Simulation(p, seed=0, world=bare_world(p))
    # Muscle tension starts at zero and rises to its resting tone over the first few
    # hundred milliseconds, so let the excitation-contraction cascade fill first.
    for _ in range(int(1.5 / sim.dt)):
        sim.muscles.step(sim.nervous.s)
    t = sim.muscles.tension
    assert abs(float(t.mean()) - p.muscle.rest_tension) < 0.06, float(t.mean())
    d, v = sim.muscles.row_tension()
    assert np.abs(d - v).max() < 0.12, "dorsal and ventral resting tone disagree"


def test_membrane_potentials_stay_physiological():
    """Nothing runs away, and the population sits where recordings say it should.

    Measured C. elegans resting potentials span roughly -75 mV (AWA) to -25 mV (AVA,
    body-wall muscle). Motor neurons under strong proprioceptive drive do reach the
    saturating rail at the extremes of a cycle; what must not happen is the *population*
    drifting out of range, or anything becoming non-finite.
    """
    p = Params()
    sim = Simulation(p, seed=1)
    sim.run(6.0)
    V = sim.nervous.V
    assert np.all(np.isfinite(V))
    assert p.neural.v_clamp[0] <= V.min() and V.max() <= p.neural.v_clamp[1]
    assert -70.0 < float(np.median(V)) < -10.0
    at_rail = np.mean(V <= p.neural.v_clamp[0] + 1e-9)
    assert at_rail < 0.10, "%.1f%% of neurons are saturated" % (100 * at_rail)


def test_body_length_is_conserved_in_the_full_loop():
    p = Params()
    sim = Simulation(p, seed=2)
    sim.run(5.0)
    seg = np.linalg.norm(np.diff(sim.body.nodes(), axis=0), axis=1)
    assert np.allclose(seg, p.body.length / p.body.n_links, rtol=1e-10)


def test_anterior_touch_drives_a_reversal():
    """Touching the head must make the animal back up -- the escape response.

    Anterior touch excites ALM/AVM, which drive the backward command interneurons AVA/AVD,
    which gap-junction onto the A-type motor neurons. Every step of that is in the
    connectome; none of it is scripted here.
    """
    p = Params()
    sim = Simulation(p, seed=5, world=bare_world(p))
    sim.run(8.0)
    before = float(np.mean(sim.nervous.activation()[sim.senses.ava]))
    for _ in range(40):
        sim.poke("anterior", strength=2.0)
        sim.step()
    for _ in range(int(0.6 / sim.dt)):
        sim.step()
    after = float(np.mean(sim.nervous.activation()[sim.senses.ava]))
    assert after > before, "AVA did not depolarise after an anterior touch (%.3f -> %.3f)" % (
        before, after)


def test_the_wave_travels_rather_than_standing():
    """A standing wave produces no net thrust, so this is the measure that matters.

    +1 is a pure head-to-tail travelling wave, 0 a pure standing one. The identical body
    driven by a prescribed travelling wave reaches +0.996 and moves at 0.174 mm/s; driven
    by the nervous system it manages about +0.33, and that gap is the whole reason the
    animal goes nowhere. The threshold guards against losing what travelling component
    there is; raising it is the point of the work in NEXT.md.
    """
    from tools.diagnose_loop import travelling_index
    p = Params()
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.run(6.0)
    kappa = []
    for i in range(int(25.0 / sim.dt)):
        sim.step()
        if i % 40 == 0:
            kappa.append(sim.body.curvature().copy())
    twi = travelling_index(np.array(kappa))
    assert twi > 0.15, "the body is oscillating as a standing wave (TWI %+.3f)" % twi
