"""Where along the chain does the phase gradient get lost?

The body's curvature has a phase gradient along it -- a wavelength of about 1.4 body
lengths, so across the stretch the B-type motor neurons act on (0.32 to 0.86) there should
be roughly 140 degrees of phase change. Their output has none: the dorsoventral drive
leaving them is a pure standing wave.

So either the proprioceptive input they receive has already lost the gradient, or it has
the gradient and something else in their input swamps it. This measures the phase of each
signal at each stage, against the body position the neuron acts on:

    curvature at the neuron's receptive field
    the proprioceptive current it receives
    its own release

A gradient present in the current but absent from the release means a common input is
dominating. A gradient absent from the current means the receptive fields are averaging it
away before it ever reaches a neuron.

    PYTHONPATH=. python tools/phase_profile.py
"""

from __future__ import annotations

import sys

import numpy as np

from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.params import Params
from worm.senses import _output_position


def phase_of(sig: np.ndarray, freq: float, fs: float) -> np.ndarray:
    """Phase of each column of `sig` at frequency `freq`, in degrees, relative to column 0."""
    w = np.exp(-2j * np.pi * freq * np.arange(sig.shape[0]) / fs)
    comp = (sig - sig.mean(axis=0)).T @ w
    ph = np.angle(comp)
    ph = np.unwrap(ph - ph[0])
    return np.degrees(ph), np.abs(comp) / sig.shape[0]


def main() -> int:
    p = Params()
    sim = Simulation(p, seed=3, world=bare_world(p))
    conn = sim.conn
    db = conn.group("DB")
    order = np.argsort([_output_position(conn, int(i)) for i in db])
    db = db[order]
    pos = np.array([_output_position(conn, int(i)) for i in db])

    sim.run(6.0)
    stride = 40
    rel, cur, kap = [], [], []
    for i in range(int(40.0 / sim.dt)):
        # The proprioceptive current actually delivered on this step.
        I = sim.senses.sense(sim.world, sim._nodes, sim._contact,
                             sim.body.curvature(), sim.nervous.activation())
        sim.step()
        if i % stride == 0:
            rel.append(sim.nervous.s[db].copy())
            cur.append(I[db].copy())
            kap.append(sim.body.curvature().copy())
    rel, cur, kap = np.array(rel), np.array(cur), np.array(kap)
    fs = 1.0 / (sim.dt * stride)

    mid = kap[:, kap.shape[1] // 2]
    spec = np.abs(np.fft.rfft((mid - mid.mean()) * np.hanning(len(mid))))
    fr = np.fft.rfftfreq(len(mid), 1.0 / fs)
    band = (fr > 0.1) & (fr < 3.0)
    freq = float(fr[band][np.argmax(spec[band])])

    # Curvature sampled at each neuron's own receptive field.
    joint_s = sim.muscles.joint_s
    reach = p.sensory.proprio_reach
    field = np.stack([kap[:, (joint_s >= s0 - reach) & (joint_s <= s0)].mean(axis=1)
                      for s0 in pos], axis=1)

    ph_k, amp_k = phase_of(field, freq, fs)
    ph_i, amp_i = phase_of(cur, freq, fs)
    ph_s, amp_s = phase_of(rel, freq, fs)

    print("oscillating at %.2f Hz; phases in degrees relative to the most anterior DB\n" % freq)
    print("%-7s %8s | %9s %9s | %9s %9s | %9s %9s"
          % ("neuron", "body pos", "kappa deg", "amp", "current deg", "amp",
             "release deg", "amp"))
    for j in range(len(db)):
        print("%-7s %8.2f | %9.1f %9.3f | %9.1f %9.2f | %9.1f %9.4f"
              % (conn.names[db[j]], pos[j], ph_k[j], amp_k[j], ph_i[j], amp_i[j],
                 ph_s[j], amp_s[j]))
    span = pos[-1] - pos[0]
    print("\nphase change across %.2f body lengths of cord:" % span)
    print("   curvature in the receptive fields  %+8.1f deg" % (ph_k[-1] - ph_k[0]))
    print("   proprioceptive current             %+8.1f deg" % (ph_i[-1] - ph_i[0]))
    print("   motor neuron release               %+8.1f deg" % (ph_s[-1] - ph_s[0]))
    print("\nA travelling wave needs this to grow steadily along the body. Zero is a")
    print("standing wave. For a 0.65 L wavelength it would need about -300 deg here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
