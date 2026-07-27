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
    """An empty dish: no food, no gradients, nothing to react to but the body itself."""
    return World(p.world, np.random.default_rng(0))


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


def _dominant(x: np.ndarray, fs: float):
    if len(x) < 16:
        return 0.0, 0.0
    win = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * win))
    fr = np.fft.rfftfreq(len(x), 1.0 / fs)
    band = (fr > 0.08) & (fr < 5.0)
    if not np.any(band):
        return 0.0, 0.0
    k = np.argmax(spec[band])
    return float(fr[band][k]), float(spec[band][k] / (spec.sum() + 1e-12))


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
    print("  curvature     rms %.2f  max %.2f /mm" % (r["kappa_rms"], r["kappa_max"]))
    print("  D/V drive     %.4f       centroid speed %.4f mm/s" % (r["dv_drive"], r["speed"]))
    print("  V swing (mV)  " + "  ".join("%s %.1f" % (k, v) for k, v in r["swing"].items()))
    print("  mean V  (mV)  " + "  ".join("%s %.0f" % (k, v) for k, v in r["mean_V"].items()))
    print("  targets: crawl 0.30-0.50 Hz, wavelength 0.65 L, head->tail,"
          " curvature rms ~4.3 max ~9.8, speed ~0.15-0.22 mm/s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
