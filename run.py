#!/usr/bin/env python3
"""Run the worm.

    python run.py                      start the simulation and the web viewer
    python run.py --headless 60        run 60 simulated seconds and print a report
    python run.py --medium buffer      start it swimming instead of crawling
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="celegans-sim")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port for the viewer")
    ap.add_argument("--ws-port", type=int, default=8081, help="WebSocket telemetry port")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--medium", default="agar", choices=["agar", "viscous", "buffer"])
    ap.add_argument("--headless", type=float, default=None, metavar="SECONDS",
                    help="run without a viewer for this many simulated seconds")
    args = ap.parse_args()

    from worm.params import Params
    params = Params().with_medium(args.medium)

    if args.headless is not None:
        import numpy as np
        from worm.engine import Simulation
        sim = Simulation(params, seed=args.seed)
        sim.run(args.headless)
        k = sim.body.curvature()
        print("t=%.1f s" % sim.t)
        print("  centroid        (%.2f, %.2f) mm" % tuple(sim.body.centroid()))
        print("  net speed       %.4f mm/s (%s)" % (sim.speed, sim.direction()))
        print("  path speed      %.4f mm/s  (includes undulatory sloshing)" % sim.path_speed)
        print("  curvature       rms %.2f, max %.2f /mm" %
              (float(np.sqrt((k ** 2).mean())), float(np.abs(k).max())))
        print("  food eaten      %.2f" % sim.food_eaten)
        print("  membrane V      %.1f .. %.1f mV" % (sim.nervous.V.min(), sim.nervous.V.max()))
        return 0

    from worm import server
    server.run(http_port=args.port, ws_port=args.ws_port, seed=args.seed, params=params)
    return 0


if __name__ == "__main__":
    sys.exit(main())
