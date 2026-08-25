"""Does the whole animal behave like an animal?

These are slower than the unit tests -- each runs a real closed-loop simulation -- but
they are the ones that would actually catch a regression that matters. The reference
numbers are measurements on live worms, cited inline.
"""

import numpy as np
import pytest

from tools.diagnose_loop import analyse, bare_world
from worm import senses as senses_module
from worm.engine import Simulation
from worm.params import MEDIA, Params
from worm.world import World


@pytest.fixture(scope="module")
def crawl():
    p = Params()
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.body.medium = MEDIA["agar"]
    return analyse(sim, seconds=20.0)


def test_undulation_frequency_on_agar(crawl):
    """Measured crawl: 0.30 +- 0.02 Hz (Fang-Yen 2010); swim 1.76 +- 0.07 Hz.

    This lands at about 0.65 Hz, and the bound below brackets the *self-consistent* animal
    rather than the quoted 0.30 Hz, because those two numbers cannot both be right. A
    travelling wave runs along the body at V = f * L and an inextensible body in a viscous
    medium cannot advance faster than its own wave, so 0.219 mm/s (Ramot et al.) with a
    0.65 L wavelength needs U/V = 1.12, above the physical bound of 1. At the animal's own
    curvature the mechanics here cap U/V near 0.51, which puts an animal doing 0.219 mm/s
    at about 0.66 Hz. See tools/thrust.py for the measurement and the arithmetic.
    """
    assert 0.35 <= crawl["freq"] <= 0.85, crawl["freq"]


def test_wavelength_on_agar(crawl):
    """Measured: 0.65 +- 0.03 body lengths (Fang-Yen 2010); 0.58 +- 0.02 (Berri 2009).

    This lands, at 0.64 L, and the bound is tight because it is now a real result rather
    than a shrug. The earlier version of this docstring said the wavelength was "almost
    completely insensitive to the proprioceptive reach", on a measurement made when the
    wave was mostly standing; with a travelling wave it is the one thing reach does
    control, running 0.49 to 0.64 L as reach goes 0.08 to 0.30 while leaving the frequency
    flat to within 1%. See SensoryParams.proprio_reach for the table.
    """
    assert 0.55 <= crawl["wavelength"] <= 0.95, crawl["wavelength"]


def test_wave_travels_head_to_tail(crawl):
    """Forward locomotion means the undulation propagates posteriorly."""
    assert crawl["direction"] == "head->tail"


def test_curvature_amplitude(crawl):
    """Mean 4.3 +- 0.3 /mm, max 9.8 +- 1.1 /mm (Krajacic et al. 2012).

    Runs low on the r.m.s. and slightly high on the peak, meaning the bend is more
    concentrated along the body than a real worm's. That got worse when the stretch
    receptor was given its adaptation: the curvature amplitude fell from 4.1 to 2.4 while
    net displacement rose twenty-fold and the net-to-path ratio went from 0.07 to 0.72.
    It is a trade worth making -- a worm with textbook curvature that goes nowhere is not
    a better worm -- but it is a trade, and this is where it shows up.
    """
    assert 1.5 <= crawl["kappa_rms"] <= 7.0, crawl["kappa_rms"]
    assert 5.0 <= crawl["kappa_max"] <= 18.0, crawl["kappa_max"]


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

    Measured over 24 s rather than the 16 s this used before the animal could turn. An
    omega turn perturbs the head oscillation for about 3 s, and in a 16 s record that is a
    fifth of the data -- enough to drag the spectral peak onto a sub-harmonic. Seed 0 read
    0.1875 Hz that way while seeds 3 and 7 read 0.6875, and the gait was not the problem:
    the same seed reads 0.6667 Hz over 60 s, its travelling-wave index is +0.83 even in
    the bad window, and turning the omega drive off restores 0.6875 at 16 s. The
    assertion is unchanged; only the window is long enough to survive a turn landing in
    it. At 24 s all three seeds agree exactly.
    """
    freqs, dirs = [], []
    for seed in (0, 3, 7):
        p = Params()
        sim = Simulation(p, seed=seed, world=bare_world(p))
        r = analyse(sim, seconds=24.0)
        freqs.append(r["freq"])
        dirs.append(r["direction"])
    assert all(d == "head->tail" for d in dirs), dirs
    assert max(freqs) / max(min(freqs), 1e-9) < 1.6, freqs


def test_medium_changes_the_gait(crawl):
    """The medium, and nothing else, must change how the animal moves.

    Fang-Yen et al. (2010) measured 0.30 Hz / 0.65 L crawling and 1.76 Hz / 1.54 L
    swimming, with nothing changed but the fluid. Nothing differs between these two runs
    either, except the two drag coefficients -- so a mechanical coupling from medium to
    gait exists here and this test pins it down.

    What it asserts is that the *size* of that coupling is not nothing. What it does not
    assert is the direction, and the reason has changed since this was written.

    It used to read "the model currently gets it backwards: ~1.25 Hz on agar and ~0.55 Hz
    in buffer". That is no longer true and had not been for some time. Re-measured through
    this test's own configuration -- `analyse`, 20 s, seeds 3, 5 and 11 -- the model runs
    0.65-0.70 Hz on agar and 0.85 Hz in buffer at every seed: buffer faster, which is the
    animal's direction. It agrees with the README's limitations section ("gait modulation
    points the right way now, and is far too small", 0.66 Hz against 0.85 Hz) and with the
    three-medium sweep in the research log.

    So the remaining failure is magnitude, not sign: 1.21-1.31x here against the animal's
    0.30 -> 1.76 Hz, roughly sixfold.

    The assertion is directional, and the direction got its own seed count before the
    criterion changed (16 seeds, this exact protocol, 2026-08-13): buffer faster than agar
    at 16 of 16, buffer/agar 1.214-1.308, mean 1.285, sd 0.039. The FFT grid at 20 s is
    0.05 Hz, so the weakest seed's directional margin is three bins -- not near the noise.
    The bound is 1.15 *directional*: about 5% under the weakest measured seed, so a
    one-bin drift at some future seed cannot flip the suite, and strictly stronger than
    the old direction-free `ratio > 1.2` -- that bound accepted an animal modulating
    backwards, which is exactly how this test once coexisted with a docstring claiming the
    model ran backwards. This one refuses it.
    """
    # The module's crawl fixture is this exact seed, medium and duration.  Reusing it
    # avoids another 40,000 whole-animal steps without changing either assay.
    results = {"agar": crawl}
    p = Params()
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.body.medium = MEDIA["buffer"]
    results["buffer"] = analyse(sim, seconds=20.0)
    ratio = results["buffer"]["freq"] / max(results["agar"]["freq"], 1e-9)
    assert ratio > 1.15, (
        "gait modulation missing or backwards: %.3f Hz agar vs %.3f Hz buffer"
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

    Anterior touch excites ALM/AVM, which reach the backward command interneurons AVA/AVD.
    Every step of that is in the connectome; none of it is scripted here.

    Measured as a *paired* difference: two runs from the same seed, identical in every
    respect except that one gets the poke, compared at the same instant. The unpaired
    version of this test compared AVA before and after the touch in a single run, which
    measures the tap response plus whatever the gait was doing anyway -- and the tap
    response here is about +0.02 in activation against spontaneous swings several times
    that, so it passed or failed on the phase of the undulation. Pairing cancels the gait
    exactly and leaves only the stimulus.
    """
    def ava_after(poke):
        p = Params()
        sim = Simulation(p, seed=5, world=bare_world(p))
        sim.run(8.0)
        for _ in range(int(0.05 / sim.dt)):
            if poke:
                sim.poke("anterior", strength=2.0)
            sim.step()
        sim.run(0.6)
        return float(np.mean(sim.nervous.activation()[sim.senses.ava]))

    quiet, touched = ava_after(False), ava_after(True)
    assert touched > quiet, (
        "an anterior touch did not depolarise the backward command pool "
        "(%.4f without the touch, %.4f with it)" % (quiet, touched))


def test_the_tail_feels_repellent_and_bag_feels_the_downshift():
    """The two ends of the animal are different sensors, and oxygen has two edges.

    PHA/PHB sample the repellent field at the tail (Hilliard et al. 2002): a drop that
    exists only under the tail must drive the phasmid pool and leave ASH, a body-length
    away at the nose, silent. BAG carries the *falling* edge of oxygen (Zimmer et al.
    2009) where URX carries the level and the rising edge: a downshift must drive BAG,
    an upshift must not, and the rectification is what this test pins.

    Tested at the current level, on a plate built for the purpose -- repellent present
    only where the tail is, oxygen stepped up and down at will -- because that is where
    the claim is unambiguous. What the animal *does* with the phasmid current is the
    escape-direction question, measured separately.
    """
    p = Params()
    sim = Simulation(p, seed=0, world=bare_world(p))
    s = sim.senses
    nodes = sim.body.nodes()
    tail = nodes[-1]

    class Plate:
        """Only what Senses.sense touches; fields are identity tokens."""
        attractant, repellent, food = object(), object(), object()

        def __init__(self, o2):
            self.o2 = o2

        def sample(self, field, x, y):
            if field is Plate.repellent:
                return 0.5 if np.hypot(x - tail[0], y - tail[1]) < 0.1 else 0.0
            return 0.0

        def temperature(self, x, y):
            return p.sensory.cultivation_temp

        def oxygen(self, x, y):
            return self.o2

    contact = np.zeros((len(nodes), 2))
    curv = np.zeros(len(nodes) - 2)
    act = sim.nervous.activation()
    plate = Plate(0.10)

    # First contact seeds every adapting baseline at the stimulus, so the differential
    # parts are exactly zero and only the tonic parts remain.
    I0 = s.sense(plate, nodes, contact, curv, act)
    assert np.allclose(I0[s.phasmid], p.sensory.phasmid_gain * 0.5), (
        "a drop under the tail did not produce the tonic phasmid current")
    assert np.all(I0[s.ash] == 0.0), (
        "the tail's drop leaked into ASH: the nose is sensing the wrong end")
    assert np.all(I0[s.bag] == 0.0), "BAG fired with oxygen at its own baseline"

    # A downshift: BAG takes the rectified negative deviation, URX loses the same amount.
    plate.o2 = 0.08
    I1 = s.sense(plate, nodes, contact, curv, act)
    assert np.allclose(I1[s.bag], p.sensory.bag_gain * 0.02), (
        "an oxygen downshift did not drive BAG")
    assert np.allclose(I1[s.phasmid], p.sensory.phasmid_gain * 0.5), (
        "an unchanged tail concentration moved the phasmid current")

    # An upshift: the deviation is positive, the rectifier holds, BAG stays silent.
    plate.o2 = 0.12
    I2 = s.sense(plate, nodes, contact, curv, act)
    assert np.all(I2[s.bag] == 0.0), (
        "BAG fired on an oxygen *upshift*: the rectifier is missing and the downshift "
        "channel has become a second URX")


def test_improvement_is_chloride_on_aib_and_worsening_is_not():
    """The ASE opponency at its second synapse, pinned where it is a fact of wiring.

    ASEL (rising attractant, "better") answers glutamate with chloride on AIB, the
    reversal-promoting interneuron; ASER (falling attractant, "worse") keeps the
    excitatory receptor on the same cell -- worsening SHOULD reverse. One transmitter,
    two receptors, decided postsynaptically per presynaptic partner, the shape
    Chalasani et al. 2007 mapped for AWC's targets. NeuralParams.glucl_pre has both
    measurements: with the pair symmetric-excitatory, driving ASEL *promoted* reversals
    (+0.67/min) and the pirouette ratio sat at 0.52; with this asymmetry the wrong-way
    route reads +0.00 and the ratio 0.87. Losing either half silently un-does that, so
    both halves are asserted.
    """
    p = Params()
    sim = Simulation(p, seed=0, world=bare_world(p))
    ix = sim.conn.index
    E = sim.nervous.E_syn                     # (N, N), [post, pre]
    for post in ("AIBL", "AIBR"):
        assert E[ix[post], ix["ASEL"]] == p.neural.E_inh, (
            "%s hears ASEL through an excitatory receptor: 'better' will command "
            "reversals again" % post)
        assert E[ix[post], ix["ASER"]] == p.neural.E_exc, (
            "%s hears ASER through chloride: 'worse' can no longer command the "
            "reversal it is supposed to" % post)


def _sleepy(seed=0):
    """A fed animal on a lawn with the sleep clock compressed for testing.

    flp11_tau drops to 1 s so the quiescence gate follows the bout within a couple of
    seconds instead of ten, and tau_sleep stretches so the bout outlasts the test. The
    homeostat's *rates* are what is compressed -- the circuit under test is untouched.
    """
    import dataclasses

    p = Params()
    p = dataclasses.replace(p, sleep=dataclasses.replace(
        p.sleep, flp11_tau=1.0, tau_sleep=60.0))
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 1.2, density=1.0, attractant=1.0, length_scale=4.0)
    return Simulation(p, seed=seed, world=w, placement=(0.0, 0.0, 0.0))


def _mid_speed(sim, seconds):
    n = len(sim.body.nodes())
    a = sim.body.nodes()[n // 2].copy()
    sim.run(seconds)
    return float(np.hypot(*(sim.body.nodes()[n // 2] - a))) / seconds


def test_a_worm_with_sleep_pressure_stops_and_a_poke_wakes_it():
    """Sleep is a state, and rapid reversibility is what separates it from paralysis.

    RIS drive quiets the command and head circuits through its own GABAergic wiring and
    FLP-11 gates the cords, the head oscillator and the pump (worm/sleep.py; Turek et
    al. 2013, 2016). Driven above threshold the animal must actually stop moving and
    stop pumping -- and a strong touch must wake it within seconds, because arousal
    keeps full gain through the sleeping state. Measured on one seed with the pressure
    seeded directly: the homeostat's slow build is the clock, not the circuit, and the
    circuit is what this test pins.
    """
    sim = _sleepy()
    sim.run(6.0)
    v_awake = _mid_speed(sim, 2.0)

    sim.sleep.pressure = 0.95
    sim.run(4.0)      # bout fires at once; the peptide gate follows within seconds
    assert sim.sleep.bout, "pressure above threshold did not start a bout"
    assert sim.sleep.quiescence() > 0.9, (
        "the bout is on but FLP-11 never closed the gate (quiescence %.3f)"
        % sim.sleep.quiescence())
    assert sim.pharynx.rate < 0.2, (
        "a sleeping animal is still pumping at %.2f Hz" % sim.pharynx.rate)
    v_asleep = _mid_speed(sim, 3.0)
    assert v_asleep < 0.5 * v_awake, (
        "quiescence did not slow the animal: %.4f mm/s asleep against %.4f awake"
        % (v_asleep, v_awake))

    for _ in range(int(0.3 / sim.dt)):
        sim.poke("anterior", strength=3.0)
        sim.step()
    assert not sim.sleep.bout, "a strong anterior touch did not interrupt the bout"
    assert sim.sleep.refractory > 0.0
    v_woken = _mid_speed(sim, 2.0)
    assert v_woken > 2.0 * v_asleep, (
        "the poked animal did not move off: %.4f mm/s woken against %.4f asleep"
        % (v_woken, v_asleep))


def test_sleep_needs_ris():
    """Ablate RIS and the animal cannot sleep -- Turek et al. 2013, reproduced.

    The homeostat still crosses its threshold (it is upstream of the cell), but the
    switch it closes is RIS itself: a dead RIS reads activation zero, releases no
    FLP-11 -- exactly none, which is asserted exactly -- and every quiescence gate
    stays wide open. The pump keeps running and the animal keeps its speed, on the
    same seed and plate where the intact animal stops.
    """
    sim = _sleepy()
    sim.nervous.set_ablated(sim.sleep.ris)
    sim.run(6.0)
    sim.sleep.pressure = 0.95
    sim.run(4.0)
    assert sim.sleep.flp11 == 0.0, (
        "an ablated RIS released FLP-11 (%.4f): the peptide is not coming from the "
        "cell, and the ablation experiment this circuit is built on would not "
        "reproduce" % sim.sleep.flp11)
    assert sim.sleep.quiescence() == 0.0
    assert sim.pharynx.rate > 0.5, (
        "the pump stopped (%.2f Hz) without any FLP-11 to stop it" % sim.pharynx.rate)
    v = _mid_speed(sim, 3.0)
    assert v > 0.02, (
        "the RIS-ablated animal stopped moving anyway (%.4f mm/s): quiescence is "
        "reaching the motor circuit by some route that is not the sleep neuron" % v)


def test_a_repellent_at_the_tail_does_not_command_a_reversal():
    """Escape direction is a head-versus-tail comparison, and this is the comparison.

    Hilliard et al. 2002: a repellent at the head drives reversal, the same repellent at
    the tail drives forward acceleration. The model's half of that is PHB answering
    glutamate with chloride on AVA (NeuralParams.glucl_pre has the measurements): as
    reconstructed, with every synapse excitatory, a current step into the phasmids
    depolarised AVA *more* than the same step into ASH (+0.714 mV against +0.566) --
    danger behind the animal out-commanded danger ahead of it, and routing the tail
    measurably worsened escape. With the chloride the tail's backward command collapses
    to a fraction of the head's while PHB -> PVC stays excitatory to carry the forward
    half.

    Measured the way the anterior-touch test measures: paired runs from one seed, noise
    off, identical except for a 2 s current step into one pool, compared as the change
    in mean AVA potential against the unstimulated twin. One baseline serves both
    stimuli.
    """
    import dataclasses
    from worm.params import Params as P

    def ava_after(pool):
        p = P()
        p = dataclasses.replace(p, neural=dataclasses.replace(p.neural, noise_sigma=0.0))
        sim = Simulation(p, seed=5, world=bare_world(p))
        sim.run(6.0)
        s = sim.senses
        if pool is not None:
            target = {"ash": s.ash, "phasmid": s.phasmid}[pool]
            base = s.sense

            def wrapped(*a, **k):
                I = base(*a, **k)
                I[target] += 25.0
                return I

            s.sense = wrapped
        sim.run(2.0)
        return float(sim.nervous.V[sim.conn.group("AVA")].mean())

    quiet = ava_after(None)
    d_head = ava_after("ash") - quiet
    d_tail = ava_after("phasmid") - quiet

    assert d_head > 0.3, (
        "a repellent step at the nose no longer depolarises the backward command pool "
        "(dAVA %+0.3f mV): the escape response itself is broken" % d_head)
    assert d_tail < 0.5 * d_head, (
        "a repellent step at the tail commands reversal like one at the nose "
        "(dAVA %+0.3f mV at the tail against %+0.3f at the head): the phasmid "
        "antagonism is gone and the animal will back into what it is fleeing"
        % (d_tail, d_head))

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


def test_ablation_silences_a_neuron_and_is_reversible():
    """Killing a cell must remove its drive, and restoring must put it back.

    This guards a failure mode that is silent rather than loud. The step reads the
    precomputed product of conductance and reversal potential, `GE_syn`, not `G_syn`, so
    an ablation that zeroes only `G_syn` removes a cell's conductance while leaving its
    driving potential in place -- the neuron looks dead in every matrix anyone inspects
    and still drives its targets. Checked on a GABAergic cell because for an excitatory
    one `GE_syn` is zero anyway (E_exc is 0 mV) and the test would pass without testing.
    """
    from worm.server import Runner
    r = Runner()
    i = r.sim.conn.index["DD01"]
    out = lambda: (float(r.sim.nervous.G_syn[:, i].sum()),          # noqa: E731
                   float(np.abs(r.sim.nervous.GE_syn[:, i]).sum()),
                   float(r.sim.nervous.G_gap[i].sum()))
    before = out()
    assert before[0] > 0 and before[1] > 0 and before[2] > 0, "DD01 has no output to remove"

    r.command({"cmd": "ablate", "neurons": ["DD01"]})
    assert out() == (0.0, 0.0, 0.0), "ablation left drive behind: %r" % (out(),)

    r.command({"cmd": "restore"})
    assert out() == pytest.approx(before), "restore did not put the cell back"


def test_ablating_the_forward_command_ends_forward_locomotion():
    """The classic experiment: without AVB the animal stops going forwards.

    Measured as *signed* progress along the body axis, which matters here -- the first
    version of this test used unsigned speed and passed the ablated animal at 0.24 mm/s,
    faster than the intact one, because silencing the forward command hands the cord to
    the backward generator and the animal crawls away tail-first. Speed alone cannot see
    that; the sign is the whole phenotype.
    """
    from worm.server import Runner
    r = Runner()
    r.sim = Simulation(r.params, seed=3, world=bare_world(r.params))
    r.sim.run(8.0)

    def along(seconds):
        start = r.sim.body.centroid().copy()
        axis = r.sim.body.body_direction().copy()
        r.sim.run(seconds)
        return float(np.dot(r.sim.body.centroid() - start, axis)) / seconds

    intact = along(12.0)
    r.command({"cmd": "ablate", "neurons": ["AVBL", "AVBR", "PVCL", "PVCR"]})
    r.sim.run(4.0)                       # let the cord fall off its bifurcation
    ablated = along(12.0)

    assert intact > 0.05, (
        "the intact animal was not crawling forwards to begin with (%.4f mm/s)" % intact)
    # Roughly halved, not abolished, and the bound says so rather than flattering the
    # model. In a real worm losing AVB ends forward locomotion; here it removes about half
    # of it, because the head reflex propels the animal on its own and is untouched by the
    # ablation. That share grew when head_delay went in -- the threshold used to be 0.25 --
    # so this number is a fair measure of how much of the gait the command layer actually
    # commands, and it should get stricter, not looser, as that improves.
    assert ablated < 0.65 * intact, (
        "ablating the forward command barely changed anything: "
        "%.4f -> %.4f mm/s along the body axis" % (intact, ablated))


def test_habituation_depletes_recovers_and_prefers_short_intervals():
    """The one thing in this model that remembers anything.

    Three properties, all out of the one resource equation in SensoryParams rather than
    fitted separately: repeated stimulation depletes the receptor, rest refills it, and a
    shorter interval habituates deeper than a longer one for the same number of taps.
    That last one is what distinguishes habituation from fatigue, so it is the one worth
    guarding. Run with a short recovery constant so the test costs seconds rather than the
    three real minutes a 60 s constant would need to demonstrate the same thing, and on a
    dish wide enough that the animal cannot reach the wall during it -- sustained wall
    contact is real touch and re-depletes the receptor, which is correct behaviour and a
    confound here. That only started mattering when the animal got fast enough to cross a
    plate.
    """
    import dataclasses
    from worm.params import Params as P

    def taps(isi, n=6, tau=8.0):
        base = P()
        p = dataclasses.replace(base, sensory=dataclasses.replace(
            base.sensory, touch_habituation_use=6.0, touch_habituation_tau=tau))
        p = dataclasses.replace(p, world=dataclasses.replace(p.world, radius=200.0))
        sim = Simulation(p, seed=1, world=bare_world(p))
        sim.run(2.0)
        for _ in range(n):
            for _ in range(int(0.05 / sim.dt)):
                sim.poke("anterior", strength=1.4)
                sim.step()
            sim.run(isi)
        depleted = float(sim.senses.touch_avail[0])
        sim.run(3 * tau)
        return depleted, float(sim.senses.touch_avail[0])

    short_depleted, short_recovered = taps(1.0)
    long_depleted, _ = taps(6.0)

    assert short_depleted < 0.75, (
        "repeated taps did not deplete the receptor (%.3f)" % short_depleted)
    assert short_recovered > 0.9, (
        "the receptor did not recover with rest (%.3f)" % short_recovered)
    assert short_depleted < long_depleted - 0.05, (
        "the short interval did not habituate deeper than the long one: %.3f vs %.3f"
        % (short_depleted, long_depleted))


def test_habituation_is_independent_of_the_timestep():
    """How much an animal learns must not depend on how finely it is simulated.

    The resource is integrated exactly rather than by an Euler step, so this holds across
    a range of dt that would otherwise change the answer -- which is the same failure two
    other sensory time constants had before they were fixed, and the reason this is a test
    rather than a comment.
    """
    import dataclasses
    from worm.params import Params as P

    def depleted(dt_ms):
        base = P()
        p = dataclasses.replace(
            base,
            neural=dataclasses.replace(base.neural, dt=dt_ms * 1e-3),
            sensory=dataclasses.replace(base.sensory, touch_habituation_use=6.0))
        sim = Simulation(p, seed=1, world=bare_world(p))
        sim.run(2.0)
        for _ in range(4):
            for _ in range(int(0.05 / sim.dt)):
                sim.poke("anterior", strength=1.4)
                sim.step()
            sim.run(2.0)
        return float(sim.senses.touch_avail[0])

    coarse, fine = depleted(2.0), depleted(0.5)
    assert abs(coarse - fine) < 0.02, (
        "habituation depends on the timestep: %.4f at 2.0 ms vs %.4f at 0.5 ms"
        % (coarse, fine))


def test_rising_attractant_inhibits_aiy():
    """The sign of chemotaxis, tested where it is unambiguous.

    C. elegans chemotaxis is a biased random walk: the animal does not steer up a
    gradient, it suppresses turns while things improve (Pierce-Shimomura, Morse & Lockery
    1999). In this connectome the route from the nose to that decision is ASE onto AIY
    (19 contacts), AIY onto AIZ (21), and AIZ onto the backward command pool (10) -- AIY
    reaches the command layer only through AIZ. So a rising attractant, which depolarises
    the ON cell ASEL, must *hyperpolarise* AIY. It used to depolarise it, because the
    model gave every glutamatergic synapse an excitatory reversal, and the measured
    consequence was an animal that reversed more often the better things got.

    Tested on the membrane potential rather than on the reversal rate: the behavioural
    effect is real but small against this animal's spontaneous rate, and a test that has
    to average several seeds to see it is a slow test that still fails sometimes.
    """
    import dataclasses
    from worm.params import Params as P

    def aiy_response(glucl):
        p = P()
        p = dataclasses.replace(p, neural=dataclasses.replace(
            p.neural, glucl_strength=glucl, noise_sigma=0.0))
        sim = Simulation(p, seed=3, world=bare_world(p))
        sim.run(6.0)
        aiy = sim.conn.group("AIY")
        before = float(sim.nervous.V[aiy].mean())
        on, off = sim.conn.select("ASEL"), sim.conn.select("ASER")
        base = sim.senses.sense

        def wrapped(*a, **k):
            # A rising attractant, delivered the way one actually arrives: the ON cell up
            # and the OFF cell down. Driving both the same way is not a gradient, and it
            # was what this test used to do -- which made it pass only while ASEL and ASER
            # shared a receptor, i.e. only while the opponent pair was cancelling itself.
            I = base(*a, **k)
            I[on] += 20.0
            I[off] -= 20.0
            return I

        sim.senses.sense = wrapped
        sim.run(3.0)
        return float(sim.nervous.V[aiy].mean()) - before

    uncorrected = aiy_response(0.0)
    chloride = aiy_response(1.0)

    assert chloride < uncorrected, (
        "the chloride receptor on the ON cell did not move AIY in the hyperpolarising "
        "direction relative to leaving it excitatory (%.4f mV against %.4f): a rising "
        "attractant would not suppress turning, and chemotaxis would run backwards"
        % (chloride, uncorrected))


def test_omega_gain_of_one_changes_nothing():
    """The RIV phasic gain must be exactly inert at 1.0, not merely close to it.

    `SensoryParams.omega_gain` stays at 1.0 because RIV turned out to be the wrong cell
    to amplify (tools/omega.py), so the whole shipped model runs through the deviation
    formula in `Muscles.step`. If that formula were only approximately the identity, every
    gait number in this file would be measuring the rounding rather than the biology.
    s_eq + 1.0 * (s - s_eq) is the identity in exact arithmetic but not in floating point,
    so the guard is that the gain is not applied at all when nothing asks for it.
    """
    p = Params()
    sim = Simulation(p, seed=0, world=bare_world(p))
    assert sim.p.sensory.omega_gain == 1.0, "the shipped model is no longer the unmodified one"
    assert not sim.muscles._any_phasic, (
        "the deviation formula is being applied at unit gain, which perturbs every "
        "muscle drive in the last bits for no reason")
    assert np.all(sim.muscles.phasic_gain == 1.0)


def test_omega_gain_amplifies_only_the_phasic_part():
    """A gain on RIV must leave the resting posture alone and act only on deviations.

    This is the property that made the deviation form worth keeping even though RIV
    itself does not produce a turn: scaling RIV's *conductance* after the muscle balance
    amplifies its tonic release and curls the animal permanently -- measured, a gain of 5
    took net speed from 0.301 to 0.027 mm/s -- whereas scaling its deviation from s_eq
    leaves the balanced resting state untouched by construction. Whatever eventually
    drives the omega turn will need that guarantee.
    """
    import dataclasses

    def resting_tension(gain):
        p = dataclasses.replace(Params(), sensory=dataclasses.replace(
            Params().sensory, omega_gain=gain))
        sim = Simulation(p, seed=0, world=bare_world(p))
        # Hold the neurons at exactly the resting release the balance assumes, so the
        # only thing under test is what the gain does to a neuron sitting at s_eq.
        s = np.full(sim.conn.n, sim.muscles.s_eq)
        for _ in range(int(1.5 / sim.dt)):
            sim.muscles.step(s)
        return sim.muscles.row_tension()

    d1, v1 = resting_tension(1.0)
    d8, v8 = resting_tension(8.0)
    assert np.abs(d8 - d1).max() < 1e-9 and np.abs(v8 - v1).max() < 1e-9, (
        "an eightfold gain on RIV moved the resting posture (dorsal %.2e, ventral %.2e); "
        "it is amplifying tonic release, which is the failure mode the deviation form "
        "exists to avoid"
        % (np.abs(d8 - d1).max(), np.abs(v8 - v1).max()))

    # And it must not be inert: away from s_eq the gain has to do something.
    p = dataclasses.replace(Params(), sensory=dataclasses.replace(
        Params().sensory, omega_gain=8.0))
    sim = Simulation(p, seed=0, world=bare_world(p))
    riv = sim.conn.group("RIV")
    assert len(riv), "no RIV in this connectome"
    s = np.full(sim.conn.n, sim.muscles.s_eq)
    s[riv] += 0.02
    ref = np.full(sim.conn.n, sim.muscles.s_eq)
    ref[riv] += 0.02 * 8.0
    got = np.clip(sim.muscles.s_eq + sim.muscles.phasic_gain * (s - sim.muscles.s_eq),
                  0.0, 1.0)
    assert np.allclose(got, ref), "the gain is not reaching RIV's deviation"


def _omega_sim(current, seed=0, tau=1.5):
    import dataclasses
    p = Params()
    p = dataclasses.replace(p, sensory=dataclasses.replace(
        p.sensory, omega_current=current, omega_tau=tau))
    # These tests isolate the reversal/omega circuit for as long as 158 simulated
    # seconds. Start at the dish centre so that locomotion does not turn them into an
    # accidental boundary test now that out-of-dish coordinates correctly fail fast.
    return Simulation(p, seed=seed, world=bare_world(p), placement=(0.0, 0.0, 0.35))


@pytest.fixture(scope="module")
def omega_reversal_trace():
    """One deterministic long trace for the two assertions that used to repeat it."""
    sim = _omega_sim(300.0)
    sim.run(8.0)
    pairs, run_n, was = [], 0, sim.senses.going_forward
    fired_while_reversing = 0
    fired_after = 0
    edge_window = int(120.0 / sim.dt)
    for i in range(int(150.0 / sim.dt)):
        sim.step()
        now = sim.senses.going_forward
        if i < edge_window:
            if not now and abs(sim.senses.omega) > 1e-4:
                fired_while_reversing += 1
            if now and not was and abs(sim.senses.omega) > 1e-4:
                fired_after += 1
        if not now:
            run_n += 1
        elif not was:
            pairs.append((run_n * sim.dt, sim.senses.omega))
            run_n = 0
        was = now
    return dict(sim=sim, pairs=pairs,
                fired_while_reversing=fired_while_reversing,
                fired_after=fired_after)


def test_omega_fires_after_the_reversal_and_never_during_it(omega_reversal_trace):
    """The turn is locked to the reversal's trailing edge, which is the whole design.

    RIV failed as a driver because its output is 99.5% undulation and only 0.5%
    reversal-locked (tools/omega.py). The replacement is an edge: a transient triggered
    when the command returns to forward. If it ever fired *during* a reversal it would be
    a level again, and the animal would be bending while backing up rather than turning as
    it resumes -- which is not what the animal does and not what this is for.
    """
    fired_while_reversing = omega_reversal_trace["fired_while_reversing"]
    fired_after = omega_reversal_trace["fired_after"]

    assert fired_while_reversing == 0, (
        "the omega transient was active on %d steps while the animal was still reversing; "
        "it is meant to fire on the backward-to-forward edge" % fired_while_reversing)
    assert fired_after > 0, "no reversal in 120 s produced a turn at all"


def test_omega_amplitude_follows_reversal_duration(omega_reversal_trace):
    """A longer reversal must earn a deeper turn, as it does in the animal.

    This is not a fitted relationship -- the amplitude is the reversal's own duration
    against omega_ref_reversal -- and it is what produces the *distribution* of turn
    angles rather than one stereotyped turn. It is worth pinning because it is the part
    of the mechanism that predicts something beyond what it was built from.
    """
    sim = omega_reversal_trace["sim"]
    pairs = omega_reversal_trace["pairs"]

    assert len(pairs) >= 4, "too few reversals (%d) to test the relationship" % len(pairs)
    ref = sim.p.sensory.omega_ref_reversal
    decay = float(np.exp(-sim.dt / sim.p.sensory.omega_tau))
    # The rule itself rather than a correlation over it: with ref at 0.4 s and the model's
    # own reversals a median 0.41 s long, about half of them clip at full scale, which
    # caps any correlation statistic around 0.5 while the relationship is exact.
    for dur, amp in pairs:
        want = min(1.0, dur / ref) * decay
        amp = abs(amp)
        assert abs(amp - want) < 1e-6, (
            "a %.2f s reversal produced amplitude %.4f, not %.4f" % (dur, amp, want))
    assert max(a for _, a in pairs) <= 1.0 + 1e-9, "turn amplitude exceeded full scale"
    assert min(a for _, a in pairs) > 0.0, "some reversal earned no turn at all"


def test_omega_drive_is_a_differential_not_a_push():
    """Ventral up and dorsal down by the same amount.

    Driving the ventral pool alone saturates it without bending the animal -- 400 pA pins
    RIV and SMDV at an activation of 0.9999 and reaches a mean head curvature of -0.56 /mm
    against an undulation of 4.5. Releasing the dorsal antagonist instead reaches -6.4.
    The sign convention is what makes the turn work, so it is worth a guard.
    """
    p = Params().sensory
    sim = _omega_sim(300.0)
    v, d = sim.senses._omega_v, sim.senses._omega_d
    assert len(v) and len(d), "the omega pools are empty"
    assert not set(v.tolist()) & set(d.tolist()), "a cell is in both omega pools"

    # Every ventral cell must be ventral-dominant in the reconstruction, and likewise
    # dorsal: if the dataset is rebuilt and a cell flips, the turn would fight itself.
    nmj = sim.conn.nmj
    for i in v:
        dd = nmj[sim.conn.muscle_side > 0, i].sum()
        vv = nmj[sim.conn.muscle_side < 0, i].sum()
        assert vv > dd, "%s is in omega_ventral but is not ventral-dominant (D%.0f V%.0f)" \
            % (sim.conn.names[i], dd, vv)
    for i in d:
        dd = nmj[sim.conn.muscle_side > 0, i].sum()
        vv = nmj[sim.conn.muscle_side < 0, i].sum()
        assert dd > vv, "%s is in omega_dorsal but is not dorsal-dominant (D%.0f V%.0f)" \
            % (sim.conn.names[i], dd, vv)

    # And the current itself: equal and opposite while the transient is live.
    sim.run(6.0)
    sim.senses.omega = 1.0
    # Pin the direction: which way a given turn goes is drawn per event, and the claim
    # under test is the symmetry of the drive, not its sign on this particular turn.
    sim.senses.omega_sign = 1.0
    nodes = sim.body.nodes()
    contact = np.zeros((len(nodes), 2))
    I = sim.senses.sense(sim.world, nodes, contact,
                         sim.body.curvature(), sim.nervous.activation())
    # sense() rebuilds the whole current vector, so isolate the omega contribution by
    # taking the same step again with the transient switched off.
    sim.senses.omega = 0.0
    I0 = sim.senses.sense(sim.world, nodes, contact,
                          sim.body.curvature(), sim.nervous.activation())
    # Not exact: sense() also advances the adapting baselines and the head reflex's
    # delay buffer, so the non-omega part of the current differs by a fraction of a
    # percent between the two calls. The claim under test is the sign and the symmetry.
    delta = I - I0
    assert np.allclose(delta[v], p.omega_current, rtol=0.01), \
        "ventral pool did not receive the full drive: %r" % (delta[v],)
    assert np.allclose(delta[d], -p.omega_current, rtol=0.01), \
        "dorsal pool was not driven equally and oppositely: %r" % (delta[d],)
    assert abs(float(delta[v].mean() + delta[d].mean())) < 0.01 * p.omega_current, \
        "the drive is not balanced across the two pools"


def test_omega_wave_suppression_is_inert_between_turns_and_anterior_during_one():
    """The candidate must quiet the wave without changing the shipped gait.

    At its default zero it is exactly inert. At full suppression it acts only while the
    omega transient is live, and only on the head oscillator plus the anterior
    proprioceptive motor pool whose receptive fields overlap the turn pool.
    """
    import dataclasses

    base = Params()
    treatment = dataclasses.replace(
        base, sensory=dataclasses.replace(base.sensory, omega_wave_suppression=1.0))
    off = Simulation(base, seed=0, world=bare_world(base))
    on = Simulation(treatment, seed=0, world=bare_world(treatment))
    assert base.sensory.omega_wave_suppression == 0.0
    assert on.senses._omega_wave_body.any(), "no anterior proprioceptive cells were selected"

    def current(sim, omega):
        sim.senses.omega = omega
        sim.senses.omega_sign = 1.0
        nodes = sim.body.nodes()
        curvature = np.linspace(-4.0, 4.0, sim.p.body.n_links - 1)
        return sim.senses.sense(
            sim.world, nodes, np.zeros((len(nodes), 2)),
            curvature, sim.nervous.activation())

    # Identical fresh simulations, and no live turn: the candidate is a strict no-op.
    assert np.array_equal(current(off, 0.0), current(on, 0.0))

    # Fresh again so the first calls did not advance adaptation by one step.
    off = Simulation(base, seed=0, world=bare_world(base))
    on = Simulation(treatment, seed=0, world=bare_world(treatment))
    I0, I1 = current(off, 1.0), current(on, 1.0)
    head = np.abs(on.senses.W_head).sum(axis=1) > 0
    affected = on.senses._omega_wave_body | head
    delta = I1 - I0
    assert np.linalg.norm(delta[affected]) > 1e-3, "full suppression changed no wave drive"
    assert np.allclose(delta[~affected], 0.0, atol=1e-10), (
        "wave suppression leaked outside the head/anterior motor pool")
    assert 0.0 < on.senses.readout["omega_wave_gain"] < 0.01


def test_omega_turn_actually_turns_the_animal():
    """The drive must reorient the body, not merely bend the neck.

    Measured as a turning rate under a held drive rather than as a reorientation
    statistic, because that is deterministic and needs no reversal events: a bend that
    does not travel produces no heading change at all, which is exactly how the earlier
    RIV attempts failed.
    """
    def turn_rate(current, secs=18.0):
        sim = _omega_sim(0.0)
        sim.run(10.0)
        if current:
            v = sim.conn.select(*Params().sensory.omega_ventral)
            d = sim.conn.select(*Params().sensory.omega_dorsal)
            base = sim.senses.sense

            def wrapped(*a, **k):
                I = base(*a, **k)
                I[v] += current
                I[d] -= current
                return I

            sim.senses.sense = wrapped
        h, every = [], max(1, int(round(0.05 / sim.dt)))
        for i in range(int(secs / sim.dt)):
            sim.step()
            if i % every == 0:
                dirv = sim.body.body_direction()
                h.append(np.arctan2(dirv[1], dirv[0]))
        h = np.unwrap(np.array(h))
        return abs(float(np.degrees(h[-1] - h[0]))) / secs

    idle = turn_rate(0.0)
    driven = turn_rate(100.0)
    assert driven > 5.0 * max(idle, 1.0), (
        "a held omega drive turned the animal at %.1f deg/s against %.1f idle; the bend "
        "is not being carried into a heading change" % (driven, idle))


def _assert_gate_shift_within_bound(applied: float, limit: float) -> None:
    assert abs(applied) <= limit + 1e-12, (
        "the applied shift %.4f exceeded its own bound %.4f" % (applied, limit))


def test_a_modulator_cannot_latch_the_direction_gate():
    """No modulator may shift the gate's latch window clear of the operating point.

    The direction gate is a Schmitt trigger: it flips forward-to-backward below
    `gate_bias - gate_hysteresis` and back above `gate_bias + gate_hysteresis`. A
    modulator adds to `gate_bias`, and for a long time nothing bounded how much.

    On a dense lawn the serotonergic turn bias reached +0.103 against a hysteresis of
    0.09, which put *both* thresholds above the resting command difference. The trigger
    became a one-way latch: the animal fell into reversal and could not climb out, and
    spent 57% of its time reversing at 10 commanded reversals a minute against the
    animal's 0.7-1.25, with net-to-path 0.05. It thrashed in place on food.

    Keeping the shift strictly inside the hysteresis is exactly the condition for the
    window to keep straddling the operating point. This is a structural invariant, not a
    tuning choice, so it is asserted rather than measured -- including on the lawn that
    used to break it.
    """
    p = Params().sensory
    lim = p.turn_bias_limit * p.gate_hysteresis
    assert lim < p.gate_hysteresis, (
        "the bound (%.4f) does not sit inside the hysteresis (%.4f); a modulator could "
        "still push both thresholds past the operating point" % (lim, p.gate_hysteresis))

    world_p = Params().world
    w = World(world_p, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(Params(), seed=0, world=w, placement=(0.0, 0.0, 0.0))

    raw_peak, applied_peak = 0.0, 0.0
    for _ in range(int(20.0 / sim.dt)):
        sim.step()
        raw = abs(float(sim.modulators.turn_bias()))
        raw_peak = max(raw_peak, raw)
        # Observe what sense() actually applied. Computing min(raw, lim) here used to
        # test the assertion's own arithmetic while a deleted production clamp stayed
        # invisible.
        applied_peak = max(applied_peak, abs(sim.senses.readout["gate_shift"]))

    assert raw_peak > lim, (
        "the scenario never saturated the production clamp (raw %.4f, limit %.4f)"
        % (raw_peak, lim))
    _assert_gate_shift_within_bound(applied_peak, lim)


def test_direction_gate_guard_detects_a_bypassed_production_clamp(monkeypatch):
    """The bound guard must fail if the production ``np.clip`` is bypassed."""
    p = Params()
    lim = p.sensory.turn_bias_limit * p.sensory.gate_hysteresis
    raw = 2.0 * lim
    sim = Simulation(p, seed=0, world=bare_world(p), placement=(0.0, 0.0, 0.0))

    # Patch only the scalar clip used for the direction-gate shift. ``numpy`` is a shared
    # module object, so every unrelated clip still delegates to the captured implementation.
    real_clip = senses_module.np.clip

    def bypass_gate_clip(value, lower, upper, *args, **kwargs):
        if (np.isscalar(value) and float(value) == raw
                and lower == -lim and upper == lim):
            return value
        return real_clip(value, lower, upper, *args, **kwargs)

    monkeypatch.setattr(sim.modulators, "turn_bias", lambda: raw)
    monkeypatch.setattr(senses_module.np, "clip", bypass_gate_clip)
    sim.step()

    applied = sim.senses.readout["gate_shift"]
    assert applied == pytest.approx(raw), "the mutation did not reach the production shift"
    with pytest.raises(AssertionError, match="exceeded its own bound"):
        _assert_gate_shift_within_bound(applied, lim)


def test_the_worm_still_travels_on_a_lawn():
    """On food the animal must make progress, not thrash on the spot.

    The failure this guards against does not show up in any gait metric -- the wave was
    fine throughout -- only in where the animal ended up. Net-to-path was 0.05 on a lawn
    while the travelling-wave index was still healthy, because the animal was reversing
    every couple of seconds and retracing its own track.

    Measured on the sleepless control: on this wall-to-wall lawn the satiety homeostat
    crosses threshold at about a minute (worm/sleep.py), a sleeping animal makes no
    progress on purpose, and the claim under test is about the awake gait -- with sleep
    on, the margin would silently become a statement about bout timing instead.
    """
    import dataclasses
    p = dataclasses.replace(Params(), sleep=dataclasses.replace(
        Params().sleep, ris_drive=0.0))
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(0.0, 0.0, 22.0, density=1.0, attractant=0.0, length_scale=9.0)
    sim = Simulation(p, seed=0, world=w, placement=(0.0, 0.0, 0.0))
    sim.run(8.0)

    start = sim.body.centroid().copy()
    prev, path = start.copy(), 0.0
    every = max(1, int(round(0.05 / sim.dt)))
    for i in range(int(90.0 / sim.dt)):
        sim.step()
        if i % every == 0:
            c = sim.body.centroid()
            path += float(np.linalg.norm(c - prev))
            prev = c.copy()
    net = float(np.linalg.norm(sim.body.centroid() - start))
    net_path = net / max(path, 1e-9)
    assert net_path > 0.10, (
        "on a lawn the animal covered %.2f mm of track and got %.2f mm from where it "
        "started (net/path %.3f): it is thrashing rather than travelling"
        % (path, net, net_path))


def test_proprio_conductance_ships_off_and_replaces_the_current_when_on():
    """The clamp experiment (SensoryParams.proprio_conductance) ships off, and on is a
    mode switch, not a supplement.

    Off: the default is 0.0, sense() never sets a conductance, and the current path is
    the shipped one (the conformance gate holds the stronger claim -- the WASM runtime
    still matches freshly recorded Python trajectories, which it could not if the off
    state had moved). On: the body proprioceptive current is REMOVED from the returned
    vector and TWO channels appear in its place -- the preferred bend's excitatory
    conductance and the anti-preferred bend's inhibitory one, each half-wave rectified,
    exclusive per cell per instant -- touching only the cells the receptive fields name.
    """
    import dataclasses

    base = Params()
    assert base.sensory.proprio_conductance == 0.0
    treatment = dataclasses.replace(
        base, sensory=dataclasses.replace(base.sensory, proprio_conductance=5.0))

    def drive(sim):
        # A bent, forward-going animal: enough to make the proprioceptive term real.
        nodes = sim.body.nodes()
        curvature = np.linspace(-4.0, 4.0, sim.p.body.n_links - 1)
        return sim.senses.sense(
            sim.world, nodes, np.zeros((len(nodes), 2)),
            curvature, sim.nervous.activation())

    off = Simulation(base, seed=0, world=bare_world(base))
    on = Simulation(treatment, seed=0, world=bare_world(treatment))
    I_off, I_on = drive(off), drive(on)
    assert off.senses.prop_g is None, "the off state grew a conductance"
    assert off.senses.prop_g_inh is None
    g, g_inh = on.senses.prop_g, on.senses.prop_g_inh
    assert g is not None and np.all(g >= 0.0), "a conductance cannot be negative"
    assert g_inh is not None and np.all(g_inh >= 0.0)
    assert float(g.max()) > 0.0, "a bent body opened no excitatory channel at all"
    assert float(g_inh.max()) > 0.0, "a bent body opened no inhibitory channel at all"
    # Half-wave rectification: at one instant a cell hears its preferred bend or its
    # anti-preferred one, never both.
    assert float(np.minimum(g, g_inh).max()) == 0.0, (
        "some cell holds both channels open at once: the halves are not exclusive")

    prop_targets = (np.abs(on.senses.W_b).sum(axis=1)
                    + np.abs(on.senses.W_a).sum(axis=1)) > 0
    assert np.allclose(g[~prop_targets], 0.0, atol=1e-12), (
        "the stretch conductance leaked outside the proprioceptive pools")
    assert np.allclose(g_inh[~prop_targets], 0.0, atol=1e-12), (
        "the inhibitory arm leaked outside the proprioceptive pools")
    # The current the off animal injects into those pools is gone from the on animal --
    # replaced, not doubled up. Everyone else's current is untouched.
    assert np.allclose(I_on[~prop_targets], I_off[~prop_targets], atol=1e-10)
    assert not np.allclose(I_on[prop_targets], I_off[prop_targets]), (
        "the on state still injects the body proprioceptive current")


def test_proprio_conductance_cannot_pin_the_rail():
    """The clamp claim itself: a channel drives a cell towards its reversal and never
    past it, however strong, where a current at the same absurdity pins the v_clamp rail.

    Both arms get a 100x-absurd drive. The current animal reaches the upper rail --
    that is the saturation v_clamp's comment documents, made deliberate. The
    conductance animal's proprioceptive pool must stay at its reversal (0 mV) plus
    whatever the other inputs add, far short of the +45 mV rail: self-limiting by
    construction, with no tuning doing the limiting.
    """
    import dataclasses

    base = Params()
    hot_I = dataclasses.replace(
        base, sensory=dataclasses.replace(base.sensory, proprio_gain=3000.0))
    hot_g = dataclasses.replace(
        base, sensory=dataclasses.replace(base.sensory, proprio_conductance=500.0))

    def peak_pool_v(p):
        sim = Simulation(p, seed=0, world=bare_world(p))
        pool = np.unique(np.concatenate(
            (sim.senses.db, sim.senses.vb, sim.senses.da, sim.senses.va)))
        peak = -np.inf
        for _ in range(int(3.0 / sim.dt)):
            sim.step()
            peak = max(peak, float(sim.nervous.V[pool].max()))
        return peak

    rail_hi = base.neural.v_clamp[1]
    v_current = peak_pool_v(hot_I)
    v_conduct = peak_pool_v(hot_g)
    assert v_current >= rail_hi - 1e-6, (
        "the absurd current no longer pins the rail (%.1f mV): this test's premise "
        "changed, re-derive it" % v_current)
    assert v_conduct < 10.0, (
        "the stretch conductance drove its pool to %.1f mV, past its own 0 mV "
        "reversal: it is not self-limiting" % v_conduct)
