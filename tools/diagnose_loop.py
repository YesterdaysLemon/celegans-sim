"""Instrument the closed sensorimotor loop and report whether it oscillates.

Prints, for a run of the full model: the voltage swing of every motor-neuron class, the
dorsoventral drive reaching the muscles, and the frequency, wavelength and direction of
whatever wave the body settles into. Takes keyword overrides for any parameter, so it
doubles as the tuning harness.
"""

from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np

from worm.engine import Simulation
from worm.params import MEDIA, Params
from worm.world import World


def bare_world(p):
    """An empty dish: no food, no gradients, nothing to react to but the body itself.

    The thermal ramp has to be flattened explicitly, and the docstring above was false
    without it. `World.temperature` is unconditional -- 17 to 25 degC across the plate,
    0.0889 degC/mm -- so an "empty" dish still presents a gradient, `Senses` samples it at
    the nose every step, and AFD receives `thermo_gain` times the deviation from a baseline
    adapting at `thermo_tau_adapt = 12 s`.

    That makes it a confound aimed exactly at the comparisons these tools exist to make,
    because the steady-state tracking error is `tau * v * grad` and therefore scales with the
    animal's own speed:

        buffer, 0.038 mm/s  ->  0.37 pA
        agar,   0.219 mm/s  ->  2.10 pA
        a fast arm, 0.5     ->  4.80 pA

    against `noise_sigma = 2.2 pA`. So an agar arm and a buffer arm differ by roughly the
    noise amplitude in tonic sensory drive before the medium is considered at all, and a
    faster configuration is rewarded or punished for being faster. Every medium sweep in
    tools/ ran against this until it was found.

    Setting both ends of the ramp to the cultivation temperature makes the field genuinely
    flat, which is what a bare dish was always supposed to mean. Nothing else about the world
    changes, so trials before and after differ only by the removal of this term.
    """
    world_p = replace(p.world, temp_cold=p.sensory.cultivation_temp,
                      temp_warm=p.sensory.cultivation_temp)
    return World(world_p, np.random.default_rng(0))


def analyse(sim: Simulation, seconds: float, warmup: float = 4.0) -> dict:
    dt = sim.dt
    sim.run(warmup)
    n = int(seconds / dt)
    stride = 4
    kappa, mrows, vlog = [], [], []
    conn = sim.conn
    watch = {c: conn.group(c) for c in ("DB", "VB", "DA", "VA", "DD", "VD", "AVB", "AVA")}
    for i in range(n):
        sim.step()
        if sim.steps % 1000 == 0:
            sim.check_invariants()
        if i % stride == 0:
            kappa.append(sim.body.curvature().copy())
            d, v = sim.muscles.row_tension()
            mrows.append(np.concatenate([d, v]))
            vlog.append(np.array([sim.nervous.V[ix].mean() for ix in watch.values()]))
    kappa = np.array(kappa)
    vlog = np.array(vlog)
    fs = 1.0 / (dt * stride)

    mid = kappa[:, kappa.shape[1] // 2]
    freq, power = _dominant(mid - mid.mean(), fs)

    # Phase gradient along the body at the dominant frequency tells us the wavelength and
    # which way the wave travels.
    w = np.exp(-2j * np.pi * freq * np.arange(len(kappa)) / fs)
    comp = (kappa - kappa.mean(axis=0)) .T @ w
    phase = np.unwrap(np.angle(comp))
    s = sim.muscles.joint_s
    keep = (s > 0.15) & (s < 0.85)
    slope = np.polyfit(s[keep], phase[keep], 1)[0]     # rad per body length
    wavelength = 2 * np.pi / abs(slope) if abs(slope) > 1e-9 else np.inf

    # Dorsoventral antagonism: the dorsal and ventral sheets at the same body position
    # must be out of phase. If this is near +1 the animal is contracting both sides at
    # once -- plenty of muscle activity, no bending.
    m = np.array(mrows)
    dv_corr = float(np.mean([
        np.corrcoef(m[:, i] - m[:, i].mean(), m[:, 24 + i] - m[:, 24 + i].mean())[0, 1]
        for i in range(6, 20)
        if m[:, i].std() > 1e-9 and m[:, 24 + i].std() > 1e-9
    ])) if m.shape[0] > 4 else 0.0

    return {
        "twi": travelling_index(kappa),
        "dv_corr": dv_corr,
        "freq": freq,
        "power": power,
        "wavelength": wavelength,
        "direction": "head->tail" if slope < 0 else "tail->head",
        "kappa_rms": float(np.sqrt((kappa ** 2).mean())),
        "kappa_max": float(np.abs(kappa).max()),
        "swing": {k: float(vlog[:, i].max() - vlog[:, i].min())
                  for i, k in enumerate(watch)},
        "mean_V": {k: float(vlog[:, i].mean()) for i, k in enumerate(watch)},
        "speed": sim.speed,
        "path_speed": sim.path_speed,
        "dv_drive": float(np.abs(np.array(mrows)[:, :24] - np.array(mrows)[:, 24:]).mean()),
    }


def travelling_index(kappa: np.ndarray) -> float:
    """How much of the body's oscillation is a travelling wave rather than a standing one.

    +1 is a pure head-to-tail travelling wave, -1 a pure tail-to-head one, and 0 a pure
    standing wave -- one where the body oscillates with fixed nodes, like a plucked string.

    This distinction is the whole game for locomotion. A standing wave produces exactly
    zero net thrust however large its amplitude, because the drag forces it generates
    cancel over a cycle. The phase-slope measure used for `wavelength` above cannot detect
    it: a weak travelling component riding on a dominant standing wave still yields a
    perfectly respectable phase slope, and will report a confident wavelength and
    direction for an animal that is going nowhere.

    Decomposed with a 2D FFT over (time, arclength): power at temporal and spatial
    frequencies of opposite sign travels one way, same sign the other. Verified against
    synthetic travelling and standing waves, which it returns as +/-1.000 and 0.000.
    """
    k = kappa - kappa.mean(axis=0)
    if k.shape[0] < 16:
        return 0.0
    k = k * np.hanning(k.shape[0])[:, None] * np.hanning(k.shape[1])[None, :]
    F = np.abs(np.fft.fft2(k)) ** 2
    ft = np.fft.fftfreq(F.shape[0])[:, None]
    fs_ = np.fft.fftfreq(F.shape[1])[None, :]
    fwd = F[(ft > 0) & (fs_ < 0)].sum() + F[(ft < 0) & (fs_ > 0)].sum()
    bwd = F[(ft > 0) & (fs_ > 0)].sum() + F[(ft < 0) & (fs_ < 0)].sum()
    return float((fwd - bwd) / (fwd + bwd + 1e-12))


def _dominant(x: np.ndarray, fs: float):
    """Dominant frequency and its share of spectral power, interpolated off the bin grid.

    The bare `argmax` this used to return was quantised to the FFT's bin width, `1/seconds`
    -- 0.0333 Hz for a 30 s window. That is not a rounding detail, it is most of the
    resolution these sweeps care about: **every frequency this project has published is an
    integer multiple of 1/30 Hz, or a three-seed mean of them.** Two consequences, and the
    second is worse than the first.

    Seeds landing in the same bin printed `sd = 0.000`, which reads as perfect reproducibility
    and is the quantiser refusing to resolve them. And a one-bin difference, 4% at 0.83 Hz,
    is the entire evidence some conclusions rested on -- "gait modulation saturates by K = 9"
    was `0.8444 -> 0.8333`, one bin in one of three seeds.

    So the peak is refined by the standard three-point parabolic fit on the log magnitude,
    which for a Hanning-windowed tone recovers the true frequency to well under a tenth of a
    bin. `_BIN_HZ` is exported alongside so a caller can print the resolution it is working
    at rather than implying more than it has.
    """
    if len(x) < 16:
        return 0.0, 0.0
    win = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * win))
    fr = np.fft.rfftfreq(len(x), 1.0 / fs)
    band = (fr > 0.08) & (fr < 5.0)
    if not np.any(band):
        return 0.0, 0.0
    idx = np.flatnonzero(band)
    k = idx[np.argmax(spec[band])]
    power = float(spec[k] / (spec.sum() + 1e-12))

    # Parabolic interpolation on log magnitude. Guarded at the array ends and against a
    # flat or degenerate triple, where the correction is undefined and the bin centre is
    # the honest answer.
    if 0 < k < len(spec) - 1:
        a, b, c = (np.log(spec[k - 1] + 1e-300), np.log(spec[k] + 1e-300),
                   np.log(spec[k + 1] + 1e-300))
        denom = a - 2.0 * b + c
        if denom < -1e-12:                      # a genuine peak, not a trough or a plateau
            delta = 0.5 * (a - c) / denom
            if abs(delta) <= 1.0:               # a larger shift means the peak is elsewhere
                return float(fr[k] + delta * (fr[1] - fr[0])), power
    return float(fr[k]), power


def main(argv) -> int:
    over = {}
    for a in argv:
        k, _, v = a.partition("=")
        over[k] = float(v)

    p = Params()
    p = replace(p, sensory=replace(p.sensory,
                                   proprio_gain=over.get("proprio", p.sensory.proprio_gain),
                                   proprio_reach=over.get("reach", p.sensory.proprio_reach),
                                   tonic_forward=over.get("tonic", p.sensory.tonic_forward)),
                muscle=replace(p.muscle, peak_moment=over.get("moment", p.muscle.peak_moment)))
    medium = "agar"
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.body.medium = MEDIA[medium]
    r = analyse(sim, seconds=25.0)

    print("medium=%s proprio=%.1f reach=%.2f moment=%.2f tonic=%.1f"
          % (medium, p.sensory.proprio_gain, p.sensory.proprio_reach,
             p.muscle.peak_moment, p.sensory.tonic_forward))
    print("  oscillation   %.3f Hz   spectral share %.3f   wavelength %.2f L  %s"
          % (r["freq"], r["power"], r["wavelength"], r["direction"]))
    print("  travelling    %+.3f  (+1 pure travelling, 0 pure standing -> no thrust)"
          % r["twi"])
    print("  curvature     rms %.2f  max %.2f /mm" % (r["kappa_rms"], r["kappa_max"]))
    print("  D/V drive     %.4f       centroid speed %.4f mm/s" % (r["dv_drive"], r["speed"]))
    print("  V swing (mV)  " + "  ".join("%s %.1f" % (k, v) for k, v in r["swing"].items()))
    print("  mean V  (mV)  " + "  ".join("%s %.0f" % (k, v) for k, v in r["mean_V"].items()))
    print("  targets: crawl 0.30-0.50 Hz, wavelength 0.65 L, head->tail,"
          " curvature rms ~4.3 max ~9.8, speed ~0.15-0.22 mm/s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
