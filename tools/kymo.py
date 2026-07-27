"""Print an ASCII kymograph of body curvature, plus the phase relationships that matter.

Summary statistics hide standing waves, saturation and dead segments. Looking at the
kymograph does not.
"""

from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np

from worm.engine import Simulation
from worm.params import MEDIA, Params
from tools.diagnose_loop import bare_world

SHADE = " .:-=+*#"


def main(argv) -> int:
    over = {}
    medium = "agar"
    for a in argv:
        k, _, v = a.partition("=")
        if k == "medium":
            medium = v
        else:
            over[k] = float(v)

    p = Params()
    p = replace(
        p,
        neural=replace(p.neural,
                       ca_g=over.get("gca", p.neural.ca_g),
                       adapt_g=over.get("gk", p.neural.adapt_g),
                       adapt_tau=over.get("tau", p.neural.adapt_tau)),
        muscle=replace(p.muscle,
                       g_nmj=over.get("gnmj", p.muscle.g_nmj),
                       peak_moment=over.get("moment", p.muscle.peak_moment)),
        sensory=replace(p.sensory,
                        proprio_gain=over.get("pg", p.sensory.proprio_gain),
                        head_proprio_gain=over.get("head", p.sensory.head_proprio_gain),
                        proprio_reach=over.get("reach", p.sensory.proprio_reach)),
    )
    sim = Simulation(p, seed=3, world=bare_world(p))
    sim.body.medium = MEDIA[medium]
    sim.run(6.0)

    conn = sim.conn
    seconds, sample = 18.0, 100
    kap, rows, traces = [], [], {n: [] for n in ("RMDd", "RMDv", "DB03", "VB05", "AVBL", "AVAL")}
    ix = {"RMDd": conn.select("RMDDL", "RMDDR"), "RMDv": conn.select("RMDVL", "RMDVR"),
          "DB03": conn.select("DB03"), "VB05": conn.select("VB05"),
          "AVBL": conn.select("AVBL"), "AVAL": conn.select("AVAL")}
    for i in range(int(seconds / sim.dt)):
        sim.step()
        if i % sample == 0:
            kap.append(sim.body.curvature().copy())
            d, v = sim.muscles.row_tension()
            rows.append((d[11], v[11]))
            for n, idx in ix.items():
                traces[n].append(float(sim.nervous.V[idx].mean()))
    kap = np.array(kap)
    rows = np.array(rows)

    print("curvature kymograph  (head at top, %.0f s across; # dorsal bend, . ventral)"
          % seconds)
    for r in range(0, kap.shape[1], 2):
        line = "".join("#" if kap[t, r] > 1.0 else "." if kap[t, r] < -1.0 else " "
                       for t in range(kap.shape[0]))
        print("  %4.2f |%s|" % ((r + 1) / (kap.shape[1] + 1), line))

    print("\nmembrane potential")
    for n, a in traces.items():
        a = np.array(a)
        s = "".join(SHADE[min(7, max(0, int((x + 75) / 95 * 7)))] for x in a)
        print("  %-5s [%6.1f %6.1f] %s" % (n, a.min(), a.max(), s))

    def corr(a, b):
        a, b = np.asarray(a), np.asarray(b)
        return float(np.corrcoef(a, b)[0, 1]) if a.std() > 1e-9 and b.std() > 1e-9 else 0.0

    print("\n  corr(RMDd, RMDv)       %+.2f   (want negative: head antagonists)"
          % corr(traces["RMDd"], traces["RMDv"]))
    print("  corr(dorsal, ventral)  %+.2f   (want negative: muscle antagonists)"
          % corr(rows[:, 0], rows[:, 1]))
    print("  speed %.4f mm/s   kappa rms %.2f   max %.2f"
          % (sim.speed, float(np.sqrt((kap ** 2).mean())), float(np.abs(kap).max())))
    print("  gates: forward %.3f backward %.3f"
          % (sim.senses.readout["gate_forward"], sim.senses.readout["gate_backward"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
