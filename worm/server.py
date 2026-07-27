"""Serve the simulation to a browser: static files over HTTP, live state over a WebSocket.

The simulation runs in its own thread at a requested multiple of real time and publishes
snapshots at a fixed frame rate. State goes out as packed float32 rather than JSON --
302 neuron voltages, 302 activations, 95 muscle tensions and the body outline, thirty
times a second, is about 3 kB a frame packed and roughly five times that as text.

The chemical fields are much larger and change slowly, so they go out separately as
downsampled 8-bit images every couple of seconds.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import os
import socketserver
import struct
import threading
import time

import numpy as np

from .engine import Simulation
from .params import MEDIA, Params

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

MAGIC = 0x574F524D            # "WORM"
FIELD_MAGIC = 0x574F524E      # one greater, for the field frames
FIELD_SIZE = 128


class Runner:
    """Owns the simulation and steps it on a background thread."""

    def __init__(self, params: Params | None = None, seed: int = 0):
        self.params = params or Params()
        self.seed = seed
        self.sim = Simulation(self.params, seed=seed)
        self.lock = threading.Lock()
        self.running = True
        self.rate = 1.0                # requested multiple of real time
        self.achieved = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        dt = self.sim.dt
        chunk = 25                     # steps between clock checks
        next_t = time.perf_counter()
        window_steps, window_start = 0, time.perf_counter()
        while not self._stop.is_set():
            if not self.running:
                time.sleep(0.02)
                next_t = time.perf_counter()
                window_start, window_steps = next_t, 0
                self.achieved = 0.0
                continue
            with self.lock:
                for _ in range(chunk):
                    self.sim.step()
            window_steps += chunk
            next_t += chunk * dt / max(self.rate, 1e-6)
            slack = next_t - time.perf_counter()
            if slack > 0:
                time.sleep(slack)
            else:
                # Running slower than requested: give up on catching up rather than
                # spiralling, and report the rate actually achieved. Sleep anyway, briefly.
                # Without this the thread never blocks, holds the GIL continuously, and
                # starves the asyncio thread badly enough that new WebSocket connections
                # time out during the opening handshake.
                next_t = time.perf_counter()
                time.sleep(0.001)
            now = time.perf_counter()
            if now - window_start > 0.5:
                self.achieved = window_steps * dt / (now - window_start)
                window_start, window_steps = now, 0

    # ------------------------------------------------------------------------- commands
    def command(self, msg: dict) -> None:
        kind = msg.get("cmd")
        with self.lock:
            if kind == "play":
                self.running = True
            elif kind == "pause":
                self.running = False
            elif kind == "rate":
                self.rate = float(np.clip(float(msg.get("value", 1.0)), 0.05, 12.0))
            elif kind == "medium":
                name = str(msg.get("value", "agar"))
                if name in MEDIA:
                    self.sim.body.medium = MEDIA[name]
                    self.sim.p = self.sim.p.with_medium(name)
            elif kind == "poke":
                self.sim.poke(str(msg.get("where", "anterior")),
                              float(msg.get("strength", 1.0)))
            elif kind == "reset":
                self.seed = int(msg.get("seed", self.seed + 1))
                self.sim = Simulation(self.params, seed=self.seed)
            elif kind == "drop_food":
                self.sim.world.add_food_patch(
                    float(msg["x"]), float(msg["y"]), float(msg.get("r", 3.0)),
                    density=1.0, attractant=1.0, length_scale=7.0)
            elif kind == "ablate":
                names = msg.get("neurons", [])
                self._ablate(names)

    def _ablate(self, names) -> None:
        """Silence neurons, the way a laser ablation experiment does."""
        ns = self.sim.nervous
        for name in names:
            i = self.sim.conn.index.get(name)
            if i is None:
                continue
            ns.G_gap[i, :] = 0.0
            ns.G_syn[i, :] = 0.0
            ns.G_syn[:, i] = 0.0
            self.sim.muscles.G[:, i] = 0.0
        ns.G_gap[:, [self.sim.conn.index[n] for n in names
                     if n in self.sim.conn.index]] = 0.0
        ns.gap_total = ns.G_gap.sum(axis=1)

    # -------------------------------------------------------------------------- framing
    def hello(self) -> str:
        sim = self.sim
        c = sim.conn
        w = sim.world
        return json.dumps({
            "type": "hello",
            "neurons": [
                {"name": c.names[i], "cls": c.cls[i], "pos": round(float(c.soma_pos[i]), 4),
                 "kind": c.kind[i], "ganglion": c.ganglion[i],
                 "inh": bool(c.inhibitory[i]), "modality": c.modality[i],
                 "tx": c.transmitter[i]}
                for i in range(c.n)
            ],
            "muscles": [{"name": c.muscle_names[i],
                         "side": "D" if c.muscle_side[i] > 0 else "V",
                         "lr": "R" if c.muscle_lr[i] > 0 else "L",
                         "pos": round(float(c.muscle_pos[i]), 4)}
                        for i in range(c.n_muscles)],
            "n_nodes": sim.p.body.n_links + 1,
            "n_joints": sim.p.body.n_links - 1,
            "radius": np.round(sim.body.radius, 4).tolist(),
            "world": {
                "radius": w.extent,
                "patches": w.patches,
                "obstacles": w.obstacles,
                "temp_cold": sim.p.world.temp_cold,
                "temp_warm": sim.p.world.temp_warm,
            },
            "media": sorted(MEDIA),
            "counts": {"gap": int((c.gap > 0).sum() // 2),
                       "chem": int((c.syn > 0).sum()),
                       "nmj": int((c.nmj > 0).sum())},
        })

    def frame(self) -> bytes:
        with self.lock:
            sim = self.sim
            nodes = sim._nodes.astype(np.float32).ravel()
            act = sim.nervous.activation().astype(np.float32)
            volt = sim.nervous.V.astype(np.float32)
            tension = sim.muscles.tension.astype(np.float32)
            kappa = sim.body.curvature().astype(np.float32)
            r = sim.senses.readout
            direction = {"forward": 1.0, "backward": -1.0, "still": 0.0}[sim.direction()]
            header = struct.pack(
                "<6I12f",
                MAGIC, len(nodes) // 2, len(act), len(tension), len(kappa),
                1 if self.running else 0,
                sim.t, sim.speed, sim.food_eaten, direction, self.achieved,
                r.get("attractant", 0.0), r.get("temperature", 20.0),
                r.get("oxygen", 0.21), r.get("food", 0.0), r.get("touch", 0.0),
                r.get("gate_forward", 0.0), r.get("gate_backward", 0.0),
            )
        return b"".join([header, nodes.tobytes(), act.tobytes(), volt.tobytes(),
                         tension.tobytes(), kappa.tobytes()])

    def field_frame(self) -> bytes:
        with self.lock:
            w = self.sim.world
            step = max(1, -(-w.g // FIELD_SIZE))     # ceil, so we actually downsample
            att = w.attractant[::step, ::step]
            food = w.food[::step, ::step]
            rep = w.repellent[::step, ::step]
        n = att.shape[0]
        def q(a, hi):
            return np.clip(a / max(hi, 1e-9) * 255.0, 0, 255).astype(np.uint8)
        payload = np.stack([q(att, 1.2), q(food, 1.0), q(rep, 1.0)], axis=-1)
        return struct.pack("<2I", FIELD_MAGIC, n) + payload.tobytes()


def serve_static(port: int) -> threading.Thread:
    handler = functools.partial(_QuietHandler, directory=WEB)
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    httpd.allow_reuse_address = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return t


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):        # the console belongs to the simulation
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


async def _client(runner: Runner, websocket) -> None:
    await websocket.send(runner.hello())
    await websocket.send(runner.field_frame())

    async def pump_commands():
        async for message in websocket:
            try:
                runner.command(json.loads(message))
            except Exception as exc:                      # a bad message must not kill it
                print("bad command: %r (%s)" % (message, exc))

    reader = asyncio.create_task(pump_commands())
    last_field = time.monotonic()
    try:
        while True:
            # frame() takes the simulation lock and packs a few hundred kB of numpy, so it
            # runs on a worker thread rather than on the event loop.
            await websocket.send(await asyncio.to_thread(runner.frame))
            now = time.monotonic()
            if now - last_field > 2.0:
                await websocket.send(await asyncio.to_thread(runner.field_frame))
                last_field = now
            await asyncio.sleep(1.0 / 30.0)
    except Exception:
        pass
    finally:
        reader.cancel()


async def _main(runner: Runner, ws_port: int) -> None:
    from websockets.asyncio.server import serve
    handler = functools.partial(_client, runner)
    async with serve(handler, "127.0.0.1", ws_port, max_queue=4):
        await asyncio.Future()


def run(http_port: int = 8080, ws_port: int = 8081, seed: int = 0,
        params: Params | None = None) -> None:
    runner = Runner(params, seed=seed)
    runner.start()
    serve_static(http_port)
    print("celegans-sim")
    print("  viewer     http://127.0.0.1:%d/" % http_port)
    print("  telemetry  ws://127.0.0.1:%d/" % ws_port)
    try:
        asyncio.run(_main(runner, ws_port))
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()
