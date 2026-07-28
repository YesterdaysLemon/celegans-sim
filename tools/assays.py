"""Behavioural assays for the sensory half of the model.

Everything in `worm/senses.py` is wired -- chemosensory, thermosensory, oxygen and
nociceptive neurons all receive adapting input that reaches the connectome -- but until
now nothing measured whether any of it produces behaviour. The locomotion tests say the
worm crawls; they say nothing about whether it crawls anywhere on purpose.

Each assay here reproduces a standard plate experiment and scores it the way the original
papers do, so the numbers are comparable to something:

  chemotaxis    Chemotaxis index and up-gradient drift.  Ward (1973); Bargmann & Horvitz
                (1991).  CI = (time near source - time near control) / total.
  pirouettes    Reversal rate as a function of dC/dt.  Pierce-Shimomura, Morse & Lockery
                (1999) showed chemotaxis here is a biased random walk: the animal does not
                steer up the gradient, it suppresses sharp turns while things improve.
                This is the mechanism, and it is the measurement that can distinguish a
                real chemotactic circuit from a worm that drifted by luck.
  weathervaning Gradual curving of forward runs towards the gradient.  Iino & Yoshida
                (2009) -- the second, slower mechanism, independent of pirouettes.
  aerotaxis     Preferred oxygen.  Gray et al. (2004); N2 prefers 5-12% over ambient 21%.
  thermotaxis   Drift towards the cultivation isotherm.  Hedgecock & Russell (1975).
  nociception   Avoidance of a noxious chemical.  Kaplan & Horvitz (1993); Hilliard et al.
                (2002).  Deliberately built as brief, self-terminating encounters -- see
                the note on that assay.

Run one:   PYTHONPATH=. .venv/bin/python tools/assays.py chemotaxis
Run all:   PYTHONPATH=. .venv/bin/python tools/assays.py all
"""

from __future__ import annotations

import os

# Pin BLAS to one thread per worker. Measured effect on this model: none at all (0.58x
# real time whether pinned to 1, 2, or left alone) -- the body's matrices are 49x49 and
# too small for threaded BLAS to help. It is kept only so that N workers means N cores
# rather than something the runtime decides, which makes the timing arithmetic below
# predictable. Must be set before numpy is imported.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json  # noqa: E402
import multiprocessing as mp  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

from worm.engine import Simulation
from worm.params import Params
from worm.world import World

SAMPLE_DT = 0.05          # s between trajectory samples
SETTLE = 6.0              # s discarded at the start, while the gait establishes


# --------------------------------------------------------------------------- harness
def run_trial(build_world, placement, duration, seed, params=None):
    """One animal, one plate. Returns sampled trajectory and sensory readouts."""
    p = params or Params()
    world = build_world(p)
    sim = Simulation(p, seed=seed, world=world, placement=placement)
    dt = p.neural.dt
    every = max(1, int(round(SAMPLE_DT / dt)))

    rec = {k: [] for k in ("t", "x", "y", "nose_x", "nose_y", "dir_x", "dir_y",
                           "attractant", "d_attractant", "repellent",
                           "temperature", "oxygen", "gate_forward", "gate_backward")}
    for i in range(int(duration / dt)):
        sim.step()
        if i % every:
            continue
        if sim.t < SETTLE:
            continue
        c = sim.body.centroid()
        nose = sim.body.nodes()[0]
        d = sim.body.body_direction()
        r = sim.senses.readout
        rec["t"].append(sim.t)
        rec["x"].append(c[0]); rec["y"].append(c[1])
        rec["nose_x"].append(nose[0]); rec["nose_y"].append(nose[1])
        rec["dir_x"].append(d[0]); rec["dir_y"].append(d[1])
        for k in ("attractant", "d_attractant", "repellent",
                  "temperature", "oxygen", "gate_forward", "gate_backward"):
            rec[k].append(r.get(k, 0.0))
    return {k: np.asarray(v) for k, v in rec.items()}


def reversals(tr):
    """Boolean per sample: is the animal travelling tail-first?

    Defined mechanically rather than from the command interneurons, so that it measures
    what the body did rather than what the circuit intended.
    """
    vx = np.gradient(tr["x"], tr["t"])
    vy = np.gradient(tr["y"], tr["t"])
    # Smooth over one undulation cycle so side-to-side slosh does not read as reversal.
    w = max(3, int(round(1.0 / SAMPLE_DT)))
    k = np.ones(w) / w
    vx = np.convolve(vx, k, mode="same")
    vy = np.convolve(vy, k, mode="same")
    return (vx * tr["dir_x"] + vy * tr["dir_y"]) < 0


def onsets(mask):
    """Indices where a boolean run turns on -- one event per reversal, not per sample."""
    return np.flatnonzero(mask.astype(int) > 0 if mask.ndim == 0
                          else np.diff(mask.astype(int)) > 0)


RATE = 0.58        # x real time, one trial on one core -- measured, see module notes

# How many simulated seconds one trial of each assay costs. Used only for the estimate.
DURATIONS = {"triage": 60.0, "chemotaxis": 200.0, "aerotaxis": 200.0,
             "thermotaxis": 200.0, "nociception": 120.0}

# Workers, and the aggregate throughput they actually deliver.
#
# Both measured on the machine this was written on (Apple M2 Pro, 8 performance cores
# and 4 efficiency ones) and both are about the knee in that topology:
#
#   workers    ms/step each    aggregate steps/s    efficiency
#      1          0.570             1754              100%
#      4          0.579             6908             98.5%
#      8          0.677            11819             84.2%
#     10          0.803            12460             71.0%
#     12          0.926            12959             61.6%
#
# Past 8 the extra workers land on efficiency cores, and because a wave finishes when its
# slowest trial does, they drag everything with them: going 8 -> 12 buys 10% aggregate
# throughput while making each individual trial 37% slower. Eight is where the curve
# bends, and it leaves the machine usable while a run is going.
WORKERS = 8
THROUGHPUT = 11800     # steps/s summed over WORKERS workers


def estimate(n_trials, duration, procs=10):
    workers = max(1, min(procs, mp.cpu_count() - 2))
    batches = -(-n_trials // workers)
    return batches * duration / RATE


def pooled(fn, jobs, procs=10, timeout=2400):
    """Run each job in its own short-lived process. No pool, no shared state.

    This started as multiprocessing.Pool, became ProcessPoolExecutor, and is now neither,
    because both deadlocked. Four separate runs stalled with every worker at 0% CPU and
    the parent blocked on a lock -- at 10 of 12 trials, at 0 of 12, and twice more -- on an
    idle machine with 70% of memory free. The executor at least reported it instead of
    hanging silently, but reporting a hang is not the same as not hanging.

    So: one OS process per job, launched directly, results returned as JSON on stdout.
    Process startup costs a couple of seconds against trials that run for minutes, and in
    exchange there is no shared interpreter state, no IPC, no semaphores, and nothing that
    can deadlock -- a job either exits with output or it does not. Failures are reported
    per job and come back as absent rather than taking the run down.
    """
    workers = max(1, min(procs, mp.cpu_count() - 2))
    # Loaded by file path rather than module name: a tool run as a script has
    # fn.__module__ == "__main__", which a child process cannot import.
    source = sys.modules[fn.__module__].__file__
    runner = ("import json,sys,importlib.util as u;"
              "sp=u.spec_from_file_location('_shard', %r);m=u.module_from_spec(sp);"
              "sp.loader.exec_module(m);"
              "sys.stdout.write(json.dumps(getattr(m,%r)(json.loads(sys.argv[1]))))"
              % (source, fn.__name__))
    env = dict(os.environ, PYTHONPATH=os.environ.get("PYTHONPATH", "."))

    out, queue, running = [], list(enumerate(jobs)), {}
    done = 0
    deadline = time.monotonic() + timeout
    while queue or running:
        while queue and len(running) < workers:
            i, job = queue.pop(0)
            proc = subprocess.Popen(
                [sys.executable, "-c", runner, json.dumps(job)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            running[proc] = (i, job)
        for proc in list(running):
            if proc.poll() is None:
                continue
            i, job = running.pop(proc)
            done += 1
            stdout, stderr = proc.communicate()
            if proc.returncode == 0 and stdout.strip():
                out.append(json.loads(stdout))
                print("    [%d/%d]" % (done, len(jobs)), file=sys.stderr, flush=True)
            else:
                tail = stderr.decode("utf8", "replace").strip().splitlines()[-1:] or [""]
                print("    [%d/%d] FAILED %r: %s" % (done, len(jobs), job, tail[0]),
                      file=sys.stderr, flush=True)
        if time.monotonic() > deadline:
            for proc in running:
                proc.kill()
            print("    TIMED OUT with %d of %d unfinished" % (len(running), len(jobs)),
                  file=sys.stderr, flush=True)
            break
        time.sleep(0.2)
    return out


# ------------------------------------------------------------------------ chemotaxis
def _clean_plate(attractant=1.0):
    """A plate with one lawn and nothing else -- no obstacles, no repellent, no clutter."""
    def build(p):
        w = World(p.world, np.random.default_rng(0))
        if attractant > 0:
            w.add_food_patch(12.0, 0.0, 3.0, density=1.0,
                             attractant=attractant, length_scale=9.0)
        return w
    return build


def _chemo_job(seed):
    """One chemotaxis trial, scored three ways.

    Outcome, mechanism and second mechanism all come from the same run: they are three
    questions about one behaviour, and running the plate three times would only add noise.
    """
    ang = (seed % 8) * (2 * np.pi / 8)
    tr = run_trial(_clean_plate(), (0.0, 0.0, float(ang)), 200.0, seed)
    src = np.array([12.0, 0.0])

    # -- outcome: Ward's chemotaxis index, and how much closer it ended up ------------
    d0 = np.hypot(*(np.array([tr["x"][0], tr["y"][0]]) - src))
    d1 = np.hypot(*(np.array([tr["x"][-1], tr["y"][-1]]) - src))
    dist_src = np.hypot(tr["x"] - src[0], tr["y"] - src[1])
    dist_ctl = np.hypot(tr["x"] + src[0], tr["y"] + src[1])
    ci = ((dist_src < 4.0).sum() - (dist_ctl < 4.0).sum()) / max(len(dist_src), 1)

    # -- mechanism: pirouette rate conditioned on dC/dt ------------------------------
    rev = reversals(tr)
    ev = np.diff(rev.astype(int)) > 0
    dc = tr["d_attractant"][1:]
    up, down = dc > 0, dc < 0
    rate_up = ev[up].sum() / max(up.sum() * SAMPLE_DT, 1e-9) * 60.0
    rate_down = ev[down].sum() / max(down.sum() * SAMPLE_DT, 1e-9) * 60.0

    # -- second mechanism: do forward runs curve towards the source? ------------------
    hd = np.unwrap(np.arctan2(tr["dir_y"], tr["dir_x"]))
    w = max(3, int(round(2.0 / SAMPLE_DT)))
    hd = np.convolve(hd, np.ones(w) / w, mode="same")
    turn = np.gradient(hd, tr["t"]) * 180 / np.pi
    bearing = np.arctan2(src[1] - tr["y"], src[0] - tr["x"]) - np.arctan2(tr["dir_y"], tr["dir_x"])
    bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
    ok = ~rev & (np.abs(bearing) < np.pi / 2)
    slope = float(np.polyfit(bearing[ok], turn[ok], 1)[0]) if ok.sum() >= 20 else np.nan

    return dict(seed=seed, approach=d0 - d1, ci=ci, d_final=d1,
                drift=(d0 - d1) / (tr["t"][-1] - tr["t"][0]) * 60.0,
                c_end=tr["attractant"][-1],
                n_rev=int(ev.sum()), frac_reversing=float(rev.mean()),
                rate_up=rate_up, rate_down=rate_down,
                dc_rms=float(np.sqrt((dc ** 2).mean())),
                slope=slope, n_fwd=int(ok.sum()),
                heading_drift=float(np.abs(turn).mean()))


def chemotaxis(rows):
    app = np.array([r["approach"] for r in rows])
    ci = np.array([r["ci"] for r in rows])

    print("CHEMOTAXIS -- 16 animals, 200 s each, source 12 mm away, 8 start bearings")
    print("  seed  bearing   approach mm   final dist mm   C end   reversals")
    for r in rows:
        print("   %2d      %3.0f       %+7.2f        %5.1f        %.3f      %3d"
              % (r["seed"], (r["seed"] % 8) * 45, r["approach"],
                 r["d_final"], r["c_end"], r["n_rev"]))
    print()
    print("  OUTCOME")
    print("    approach  %+.2f +- %.2f mm  (positive = ended closer)"
          % (app.mean(), app.std()))
    print("    drift     %+.3f mm/min" % np.mean([r["drift"] for r in rows]))
    print("    CI        %+.3f            real animal: +0.5 or better" % ci.mean())
    print("    approached: %d/%d animals" % ((app > 0).sum(), len(app)))

    ru = np.mean([r["rate_up"] for r in rows])
    rd = np.mean([r["rate_down"] for r in rows])
    print()
    print("  MECHANISM 1 -- pirouettes (Pierce-Shimomura, Morse & Lockery 1999)")
    print("    reversals per animal in 200 s: %.1f +- %.1f"
          % (np.mean([r["n_rev"] for r in rows]), np.std([r["n_rev"] for r in rows])))
    print("    time spent reversing:          %.1f%%"
          % (100 * np.mean([r["frac_reversing"] for r in rows])))
    print("    |dC/dt| rms reaching ASE:      %.2e per s"
          % np.mean([r["dc_rms"] for r in rows]))
    print("    reversals/min while improving (dC/dt>0): %.2f" % ru)
    print("    reversals/min while worsening (dC/dt<0): %.2f" % rd)
    if ru + rd < 1e-9:
        print("    -> no reversals at all: this mechanism is unavailable to the animal")
    else:
        print("    -> worsening/improving ratio %.2f  (real animal ~2; >1 is chemotaxis)"
              % (rd / max(ru, 1e-9)))

    sl = np.array([r["slope"] for r in rows if np.isfinite(r["slope"])])
    print()
    print("  MECHANISM 2 -- weathervaning (Iino & Yoshida 2009)")
    print("    mean |turn rate| during forward runs: %.2f deg/s"
          % np.mean([r["heading_drift"] for r in rows]))
    if len(sl):
        t = sl.mean() / max(sl.std() / np.sqrt(len(sl)), 1e-9)
        print("    turn rate vs bearing-to-source: %+.3f +- %.3f deg/s per rad (t=%.1f)"
              % (sl.mean(), sl.std(), t))
        print("    -> positive means runs curve towards the source; ~0 means ballistic")
    return rows


# ---------------------------------------------------------------------------- aerotaxis
def _o2_plate(p):
    """Food with no attractant: an oxygen well with no competing chemical gradient."""
    w = World(p.world, np.random.default_rng(0))
    w.add_food_patch(12.0, 0.0, 6.0, density=1.0, attractant=0.0, length_scale=9.0)
    return w


def _o2_job(seed):
    ang = (seed % 8) * (2 * np.pi / 8)
    tr = run_trial(_o2_plate, (0.0, 0.0, float(ang)), 200.0, seed)
    return dict(seed=seed, o2_mean=float(tr["oxygen"].mean()),
                o2_start=float(tr["oxygen"][0]), o2_end=float(tr["oxygen"][-1]),
                o2_min=float(tr["oxygen"].min()))


def aerotaxis(rows):
    om = np.array([r["o2_mean"] for r in rows])
    oe = np.array([r["o2_end"] for r in rows])
    print("AEROTAXIS -- oxygen experienced, with the attractant switched off")
    print("  O2 at start:      %.1f%%" % (100 * np.mean([r["o2_start"] for r in rows])))
    print("  O2 occupied mean: %.1f%%" % (100 * om.mean()))
    print("  O2 at end:        %.1f%% +- %.1f" % (100 * oe.mean(), 100 * oe.std()))
    print("  lowest reached:   %.1f%%" % (100 * np.mean([r["o2_min"] for r in rows])))
    print("\n  ambient 21%, lawn floor 6%. N2 prefers 5-12%, so a working aerotaxis")
    print("  circuit ends well below 21% and spends its time near the lawn edge.")
    return rows


# -------------------------------------------------------------------------- thermotaxis
def _thermal_plate(p):
    return World(p.world, np.random.default_rng(0))     # bare plate: gradient only


def _thermo_job(job):
    seed, start_x = job
    ang = (seed % 8) * (2 * np.pi / 8)
    tr = run_trial(_thermal_plate, (start_x, 0.0, float(ang)), 200.0, seed)
    return dict(seed=seed, start_x=start_x,
                t_start=float(tr["temperature"][0]),
                t_end=float(tr["temperature"][-1]),
                t_mean=float(tr["temperature"].mean()),
                dx=float(tr["x"][-1] - tr["x"][0]))


def thermotaxis(rows):
    print("THERMOTAXIS -- cultivation temperature 20 C, plate ramps 17->25 C across x")
    print("  the 20 C isotherm is at x = -6.2 mm")
    for x in (-18.0, 6.0):
        g = [r for r in rows if r["start_x"] == x]
        dx = np.array([r["dx"] for r in g])
        want = "warmer (+x)" if x < -6.25 else "cooler (-x)"
        got = np.mean(dx)
        print("  start x %+5.1f mm (%.1f C): moved %+.2f +- %.2f mm, should move %s"
              % (x, np.mean([r["t_start"] for r in g]), got, dx.std(), want))
    print("\n  a working thermotaxis circuit moves both groups towards x = -6.2 mm")
    return rows


# -------------------------------------------------------------------------- nociception
def _noci_plate(p):
    """One small repellent drop, and nothing to hold the animal near it.

    Deliberately a *drop*, not a field: the exponential falls to a tenth within 12 mm, the
    plate is otherwise empty, and there is no barrier. Whatever the animal does, it can
    leave, and the assay scores how quickly it does.
    """
    w = World(p.world, np.random.default_rng(0))
    w.add_repellent_source(6.0, 0.0, strength=0.9, length_scale=5.0)
    return w


def _noci_job(seed):
    ang = (seed % 8) * (2 * np.pi / 8)
    tr = run_trial(_noci_plate, (0.0, 0.0, float(ang)), 120.0, seed)
    rev = reversals(tr)
    r = tr["repellent"]
    peak = float(r.max())
    # Time-weighted exposure, and how much of the run was spent above a tenth of peak.
    exposed = r > 0.1 * max(peak, 1e-9)
    # Reversal rate while exposed vs not: the avoidance signature.
    ev = np.diff(rev.astype(int)) > 0
    e = exposed[1:]
    rate_in = ev[e].sum() / max(e.sum() * SAMPLE_DT, 1e-9) * 60.0
    rate_out = ev[~e].sum() / max((~e).sum() * SAMPLE_DT, 1e-9) * 60.0
    return dict(seed=seed, peak=peak, frac_exposed=float(exposed.mean()),
                rate_in=rate_in, rate_out=rate_out,
                r_end=float(r[-1]), r_start=float(r[0]))


def nociception(rows):
    """See the module docstring and the printed note. Kept brief on purpose."""
    print("NOCICEPTION -- brief encounters with a repellent drop, 120 s, no barrier")
    print()
    print("  A note on how this is built. The model has no representation of affect: ASH")
    print("  input is a current that decays with a 0.35 s time constant, there is no")
    print("  accumulator, no persistent state, and no learning, so there is nothing here")
    print("  that could carry an aversive state forward. That is an argument about this")
    print("  implementation, not about the general question, so the assay is built to be")
    print("  cheap-to-be-careful anyway: a single drop the animal can always walk away")
    print("  from, no trapping geometry, 120 s rather than the 200 s used elsewhere, and")
    print("  no repeated dosing. It measures avoidance, which needs one encounter.")
    print()
    ri = np.array([r["rate_in"] for r in rows])
    ro = np.array([r["rate_out"] for r in rows])
    fe = np.array([r["frac_exposed"] for r in rows])
    print("  peak repellent met:        %.3f" % np.mean([r["peak"] for r in rows]))
    print("  time spent exposed:        %.0f%%" % (100 * fe.mean()))
    print("  reversals/min while exposed:     %.2f" % ri.mean())
    print("  reversals/min while clear:       %.2f" % ro.mean())
    print("  repellent at end vs start:  %.3f -> %.3f"
          % (np.mean([r["r_start"] for r in rows]), np.mean([r["r_end"] for r in rows])))
    print("\n  avoidance = more reversals while exposed, and a lower concentration at the")
    print("  end than at the peak. ASH drives reversal within 1-2 s in a real animal.")
    return rows


def _triage_job(seed):
    ang = (seed % 6) * (2 * np.pi / 6)
    tr = run_trial(_clean_plate(), (0.0, 0.0, float(ang)), 60.0, seed)
    rev = reversals(tr)
    ev = np.diff(rev.astype(int)) > 0
    return dict(seed=seed,
                c_min=float(tr["attractant"].min()), c_max=float(tr["attractant"].max()),
                dc_rms=float(np.sqrt((tr["d_attractant"] ** 2).mean())),
                dc_max=float(np.abs(tr["d_attractant"]).max()),
                n_rev=int(ev.sum()), frac_rev=float(rev.mean()),
                gate_f=float(tr["gate_forward"].mean()),
                gate_b=float(tr["gate_backward"].mean()))


def triage(rows):
    """Two-minute check: is anything reaching the chemosensors, and does he ever turn?

    Worth running before the full assay. A null chemotaxis index has three quite
    different causes -- flat sensors, no turns, or turns uncoupled from the sensors --
    and this separates them cheaply.
    """
    rows = sorted(rows, key=lambda r: r["seed"])
    print("TRIAGE -- %d animals, 60 s each" % len(rows))
    print(" seed   C range         |dC/dt| rms   |dC/dt| max   reversals   %rev   gate f/b")
    for r in rows:
        print("  %d   %.3f-%.3f     %.2e     %.2e       %2d      %4.1f%%   %.2f/%.2f"
              % (r["seed"], r["c_min"], r["c_max"], r["dc_rms"], r["dc_max"],
                 r["n_rev"], 100 * r["frac_rev"], r["gate_f"], r["gate_b"]))
    dc = np.mean([r["dc_rms"] for r in rows])
    dcx = np.mean([r["dc_max"] for r in rows])
    tot = sum(r["n_rev"] for r in rows)
    print()
    print("  chemo_gain is 26 pA per unit concentration, applied to the *adapted*")
    print("  derivative, and a sensory neuron's total conductance is a fraction of a nS,")
    print("  so roughly 1 pA is a millivolt or two.")
    print("    drive to ASE:  %.3f pA rms, %.3f pA peak" % (26 * dc, 26 * dcx))
    print("    reversals:     %d across 6 animals x 60 s" % tot)
    print()
    if 26 * dc < 0.5:
        print("  -> sensory drive is negligible: the gradient is too shallow for the")
        print("     speed the animal moves at. Fix the gain or the gradient, not the wiring.")
    if tot == 0:
        print("  -> he never reverses, so the biased-random-walk mechanism is unavailable")
        print("     regardless of what the sensors do.")
    return rows


# Each assay is a job function, the list of jobs it wants, and the reporter that prints
# them. Keeping those three apart is what lets every assay's jobs go into one queue.
ASSAYS = {
    "triage":      (_triage_job, lambda: list(range(6)), triage),
    "chemotaxis":  (_chemo_job, lambda: list(range(16)), chemotaxis),
    "aerotaxis":   (_o2_job, lambda: list(range(12)), aerotaxis),
    "thermotaxis": (_thermo_job,
                    lambda: [(s, x) for x in (-18.0, 6.0) for s in range(8)],
                    thermotaxis),
    "nociception": (_noci_job, lambda: list(range(12)), nociception),
}
ORDER = ["triage", "chemotaxis", "aerotaxis", "thermotaxis", "nociception"]


def _dispatch(job):
    """Run one job from any assay. The queue is flat, so each job says which it belongs to."""
    name, payload = job
    row = ASSAYS[name][0](payload)
    row["_assay"] = name
    return row


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which != "all" and which not in ASSAYS:
        print("unknown assay %r; choose from %s or 'all'" % (which, ", ".join(ASSAYS)))
        return 1

    names = ORDER if which == "all" else [which]

    # One queue for every job in every assay, rather than one pooled() call per assay.
    # The old arrangement ran each assay to completion before starting the next, so a
    # 12-job assay on N workers finished with a wave of 12 % N trials -- two of them, for
    # aerotaxis and nociception -- holding the whole machine for as long as a full wave
    # while using a sixth of it. Measured on this workload that tail was about 30% of the
    # wall clock. Flattening costs nothing and needs no numerical change; the only thing
    # given up is that the assays no longer print strictly as they finish, which is why
    # the reports are held and emitted in ORDER at the end.
    jobs = [[name, j] for name in names for j in ASSAYS[name][1]()]
    sim_s = sum(DURATIONS[name] * len(ASSAYS[name][1]()) for name in names)
    print("%d trials across %d assays, %d simulated seconds on %d workers"
          % (len(jobs), len(names), sim_s, WORKERS))
    print("estimated %.0f s\n" % (sim_s / Params().neural.dt / THROUGHPUT))

    rows = pooled(_dispatch, jobs, procs=WORKERS)

    by = {}
    for r in rows:
        by.setdefault(r.pop("_assay"), []).append(r)
    for i, name in enumerate(names):
        if i:
            print("\n" + "=" * 78 + "\n")
        got = by.get(name, [])
        if not got:
            print("%s -- no trials completed" % name.upper())
            continue
        ASSAYS[name][2](got)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
