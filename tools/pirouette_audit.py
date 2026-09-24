"""Pirouette audit: was the 0.79 pirouette ratio the detector, or the animal? The detector.

(#218 follow-up.) `tools/chemo_power.py` measured the deep-turn animal (omega_tau 2.5)
against the pre-#215 one (1.5) on 16 paired seeds, and the pirouette rows flipped: the
up-gradient reversal rate doubled (1.82 -> 3.44/min) while the down rate barely moved,
taking the pooled down/up ratio from 1.41 to 0.79. NEXT.md asked for two explanations to
be separated before anything else was built on that number:

  CONTAMINATION  the reversal detector is mechanical -- `assays.reversals` calls a sample
                 a reversal when the 1 s smoothed centroid velocity points against the
                 mid-body->nose vector. An omega turn swings the nose round towards the
                 tail while the centroid is still carried along the old heading, so a
                 deep enough omega reads as tail-first travel with no backward command
                 behind it. Every omega follows a reversal (it fires on the
                 backward->forward edge), and a pirouette that works leaves the animal
                 pointing up-gradient -- so a phantom would land preferentially in the
                 "improving" bin, which is exactly the bin that doubled.
  DILUTION       the detector is honest, and the deeper turn really does add
                 sensory-independent reorientation (or changes the sensory stream so the
                 command fires more often while things improve).

METHOD. The audit re-runs the same 32 trials -- same plate, placements, seeds and arms --
recording one readout the shipped assay does not keep (the omega amplitude) beside one it
records and never scores (`gate_backward`, the circuit's own backward command). Each
trial is scored twice. First by `assays._chemo_score` itself, which must reproduce the
chemo_power record exactly or nothing below is trusted. Then every mechanical onset is
matched to its PARENT command, or left an orphan (see `audit`), and the pirouette ratio is
recomputed four ways: every mechanical onset (the shipped definition); the first onset
per command only; those, labelled with dC/dt when their command began; and the circuit's
own command onsets -- the definition that nothing about the body can move.

The classification was revised twice, both times before the old arm existed and before
any ratio had been compared. The first draft padded each episode symmetrically; a 60 s
smoke trial showed an omega onset 0.1 s after a 0.35 s command falling inside any
reasonable pad. The second classed onsets by phase (during the command / in the omega /
neither); the first two shipped trials put *every* onset after its command had ended --
the model's commands are too brief to register through a 1 s boxcar while they are on --
which makes phase describe timing rather than cause. Parent matching counts the ways a
mechanical tally can differ from the circuit's, whatever the timing: missed commands,
repeated ones, orphan onsets, and moved labels.

PREDICTIONS, written before the run (in the phase vocabulary of the second draft):

  If CONTAMINATION: the shipped arm carries a large OMEGA-phase fraction, much larger
  than the old arm's; those onsets sit within a few seconds of a command's end, did not
  back up, and swing the heading fast; they are labelled "improving" more often than
  not; and the command-onset ratio of the shipped arm is back above 1 and within noise
  of the old arm's.

  If DILUTION: few OMEGA-phase onsets in either arm, and the command-onset ratio of the
  shipped arm stays below 1 -- the circuit itself fires more while improving.

  Mixed outcomes are possible (some phantoms, and a real drop in conditioning); the
  up-gradient budget line says how much of the 1.82 -> 3.44/min rise each explains.

THE RECORD (2026-09-24, 16/16 paired seeds, 200 s each; the reproduction is exact --
CI 0.026 / 0.072, reversals 8.94 / 7.19, up-rate 3.44 / 1.82, onset sets identical):

                                       shipped (tau 2.5)         old (tau 1.5)
  backward commands (median 0.35 s)          170                      204
  seen by the detector                  100 (59%)                 72 (35%)
    ...promptly (<= 0.5 s after it ends)       43                       62
    ...late, in the omega                      57                       10
  repeat onsets for a command already seen     40 (28% of onsets)       36 (31%)
  orphan onsets                                 3                        7

  pirouette ratio (down/up)        shipped                   old
    every mechanical onset         0.79 [0.46, 1.58]         1.41 [0.96, 2.17]
    first onset per command        0.88 [0.51, 1.81]         1.55 [1.10, 2.39]
    ...labelled at the command     0.90 [0.59, 1.57]         1.28 [0.87, 2.07]
    the circuit's command onsets   0.98 [0.77, 1.27]         1.15 [0.95, 1.40]

  up-gradient budget, +1.62/min: late firsts +0.99, repeats +0.44, prompt firsts +0.22,
  orphans -0.04. The circuit's own up-gradient command rate: 3.65 -> 3.51/min.

  paired conditioning contrast (down - up, /min), shipped - old:
    mechanical   -1.46 [-3.36, +0.03]      command onsets   -0.63 [-1.42, +0.15]

CONTAMINATION, though not by the route predicted. The doubling of the up-gradient rate is
the detector's and not the circuit's: the circuit commanded no more up-gradient reversals
in the deep-turn animal (3.65 -> 3.51/min), and 88% of the rise is late first detections
and repeats, onsets that arrive after the command is over. Scored against the
predictions: the omega-period share IS much larger in the shipped arm (onsets >= 0.5 s
after their command: 66% against 35%), and those onsets DO swing the heading fast (median
50-77 deg against 16-18 for prompt ones) -- but they DID back up (see the counterfactual:
no trick of the chord), they are NOT labelled "improving" more often than not (33%), and
the shipped command-onset ratio is NOT back above 1 (0.98), only within noise of the old
arm's. Labels barely move (9 of 100 first detections change bin) and repeats are no
commoner in the shipped arm (28% of onsets against 31%). DILUTION fails outright: the
circuit does not fire more while improving.

What moved is VISIBILITY. The model's reversal commands last ~0.35 s, too brief to
register through the detector's 1 s boxcar, so the detector sees a command mostly when
something after it pushes the body tail-first -- and the longer-lived omega does exactly
that (the counterfactual below), lifting what the detector sees from 35% to 59% of
commands. Three further readings, none of them new mechanism:

  - The 1.41 -> 0.79 flip was never resolved: the paired contrast straddles zero.
  - NEITHER animal's circuit conditions its reversals on dC/dt detectably: command-onset
    ratios 0.98 and 1.15, both intervals across 1. The old arm's 1.41 overstated a
    conditioning that its circuit barely has; the animal's is ~2.
  - Any pirouette ratio from `assays.reversals` is a statement about the omega as much as
    the circuit, so a turn change moves it without touching the decision. Measure
    conditioning with command onsets (`gate_backward` rising edges); `arc_slip` below is
    the body-side reading if a mechanical one is wanted.

THE OMEGA COUNTERFACTUAL (`omega`, 2026-09-24; 27 command ends on seeds 0-3, shipped
animal). The simulation is cloned at the end of each backward command and both copies run
on for 4 s, one untouched and one with the omega zeroed -- same state, same noise stream.
Uncommanded tail-first sliding along the body's own arc (`arc_slip`, which a curl cannot
fool): 1.12 s with the omega against 0.24 s without, +0.88 s [+0.56, +1.22]; backward
slide +0.076 mm [+0.028, +0.127]. Dose-dependent -- full-amplitude omegas (|omega| ~ 1)
add 1.49 s (median 1.80 s), those below 0.8 add 0.44 s (median 0.19), r = 0.58 -- and,
unexplained, much stronger late in a trial (t > 100 s: 1.41 s; earlier: 0.31 s). So the
repeat onsets are not a trick of the mid-body->nose chord: THE MODEL'S OMEGA BACKS THE
BODY UP, for seconds, with the command reading forward. A real omega is a forward
manoeuvre. That is a defect in the turn, and NEXT.md carries it.

Run:      PYTHONPATH=. .venv/bin/python tools/pirouette_audit.py
Summary:  PYTHONPATH=. .venv/bin/python tools/pirouette_audit.py report
Omega:    PYTHONPATH=. .venv/bin/python tools/pirouette_audit.py omega

Trajectories are cached as .npz files in `.pirouette_audit_cache/` (gitignored), one per
trial, so an interrupted run resumes and the scoring can be re-read without simulating.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from tools.assays import SAMPLE_DT, reversals
from tools.stats import fmt, paired_ci, ratio_ci, verdict

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".pirouette_audit_cache")
ARMS = {0: {}, 1: {"sensory.omega_tau": 1.5}}
ARM_LABEL = {0: "shipped (tau 2.5)", 1: "old (tau 1.5)"}
SEEDS = range(16)
DURATION = 200.0

# What tools/chemo_power.py recorded on these 32 trials (2026-08-28). The reproduction
# check compares against these before any new number is printed.
RECORD = {0: dict(ci=0.026, n_rev=8.94, rate_up=3.44),
          1: dict(ci=0.072, n_rev=7.19, rate_up=1.82)}


def _path(seed, arm):
    return os.path.join(CACHE, "seed%02d_arm%d.npz" % (seed, arm))


def _trial(job):
    seed, arm = job
    from tools import assays
    assays.OVERRIDE = ARMS[arm]          # one process per trial, as in assays._dispatch
    tr = assays.run_trial(assays._clean_plate(), assays._chemo_placement(seed), DURATION,
                          seed, extra=("omega",))
    tmp = _path(seed, arm) + ".tmp"
    with open(tmp, "wb") as f:
        np.savez_compressed(f, **tr)
    os.replace(tmp, _path(seed, arm))
    return job


def run():
    os.makedirs(CACHE, exist_ok=True)
    jobs = [(s, a) for a in ARMS for s in SEEDS if not os.path.exists(_path(s, a))]
    print("%d of %d trials cached; running %d"
          % (len(ARMS) * len(SEEDS) - len(jobs), len(ARMS) * len(SEEDS), len(jobs)),
          flush=True)
    with ProcessPoolExecutor(max_workers=max(1, min(4, os.cpu_count() or 1))) as ex:
        futs = {ex.submit(_trial, j): j for j in jobs}
        for fut in as_completed(futs):
            try:
                seed, arm = fut.result()
                print("  done seed %2d arm %d" % (seed, arm), flush=True)
            except Exception as e:                   # a dead trial is a note, not a stop
                print("  trial %r failed: %s" % (futs[fut], e), flush=True)
    return report()


# ------------------------------------------------------------ the omega counterfactual
BRANCH = 4.0                # s run on from each command's end, in both branches
EDGES = 8                   # command ends per seed
OMEGA_SEEDS = range(4)
OMEGA_CACHE = os.path.join(CACHE, "omega_branches.json")


def arc_slip(body):
    """Head-first slip along the body's own arc, mm/s.

    Minus the mean tangential velocity of the segment midpoints (the tangents point
    tailwards; midpoint velocities exactly as `Body.drag_load` builds them). Positive
    while the body crawls forwards in any posture, a curl included, and negative only
    when it actually slides tail-first -- so unlike `assays.reversals`, which reads the
    centroid against the mid-body->nose chord, it cannot be fooled by the shape of a
    turn. It needs the body's velocities, so it is read live, not from a trajectory.
    """
    u = np.stack([np.cos(body.theta), np.sin(body.theta)], axis=1)
    nvec = np.stack([-u[:, 1], u[:, 0]], axis=1)
    contrib = body.l * nvec * body.qdot[2:, None]
    csum = np.cumsum(contrib, axis=0)
    vmid = body.qdot[:2] + np.vstack([np.zeros((1, 2)), csum[:-1]]) + 0.5 * contrib
    return -float(np.einsum("mi,mi->m", vmid, u).mean())


def _branch_job(seed):
    """Clone the shipped animal at the end of each backward command and run both copies
    on for BRANCH s: one untouched, one with the omega zeroed at the edge. Same state,
    same noise stream; the only difference between the two is the turn."""
    import copy
    from tools import assays
    from worm.engine import Simulation
    p = assays.current_params()
    sim = Simulation(p, seed=seed, world=assays._clean_plate()(p),
                     placement=assays._chemo_placement(seed))
    dt = p.neural.dt
    out, was_back = [], False
    while len(out) < EDGES and sim.t < DURATION:
        sim.step()
        back = sim.senses.readout["gate_backward"] >= 0.5
        if was_back and not back and sim.t > assays.SETTLE:
            row = dict(seed=seed, t=sim.t, omega=abs(sim.senses.omega))
            for arm in ("on", "zeroed"):
                s = copy.deepcopy(sim)
                if arm == "zeroed":
                    s.senses.omega = 0.0
                tail, slid = 0.0, 0.0
                for _ in range(int(round(BRANCH / dt))):
                    s.step()
                    v = arc_slip(s.body)
                    # uncommanded only: a fresh reversal inside the window is not the turn
                    if v < 0.0 and s.senses.readout["gate_backward"] < 0.5:
                        tail += dt
                        slid -= v * dt
                row[arm] = dict(tail_s=tail, slid_mm=slid)
            out.append(row)
        was_back = back
    return out


def omega():
    """Run (or re-read) the counterfactual, and print it."""
    if os.path.exists(OMEGA_CACHE):
        with open(OMEGA_CACHE) as f:
            rows = json.load(f)
    else:
        os.makedirs(CACHE, exist_ok=True)
        with ProcessPoolExecutor(max_workers=max(1, min(4, os.cpu_count() or 1))) as ex:
            rows = [r for part in ex.map(_branch_job, OMEGA_SEEDS) for r in part]
        with open(OMEGA_CACHE, "w") as f:
            json.dump(rows, f, indent=1)
    print("\nTHE OMEGA COUNTERFACTUAL -- %d command ends on seeds %s, shipped animal; each"
          " cloned\nand run on %.0f s with the omega untouched and with it zeroed at the"
          " edge\n" % (len(rows), list(OMEGA_SEEDS), BRANCH))
    print("   seed    t (s)  |omega|   uncommanded tail-first s   slid back along arc, mm")
    print("                             omega on    zeroed         omega on    zeroed")
    for r in rows:
        print("   %3d  %7.1f   %5.2f     %6.2f    %6.2f          %6.3f    %6.3f"
              % (r["seed"], r["t"], r["omega"], r["on"]["tail_s"], r["zeroed"]["tail_s"],
                 r["on"]["slid_mm"], r["zeroed"]["slid_mm"]))
    for key, label, spec in (("tail_s", "tail-first seconds", "%+.2f"),
                             ("slid_mm", "backward slide, mm", "%+.3f")):
        on = [r["on"][key] for r in rows]
        off = [r["zeroed"][key] for r in rows]
        d = paired_ci(off, on)
        print("   %-19s omega on %s  zeroed %s   on - zeroed %s"
              % (label, spec % np.mean(on), spec % np.mean(off), fmt(*d, spec=spec)))
    print("   (intervals resample command ends, which are not independent within a seed)")
    return 0


# ---------------------------------------------------------------------------- scoring
LEAD = 0.5          # s: the centred 1 s boxcar can call a reversal half a window early
MATCH = 5.0         # s after a command ends within which an onset is that command's child
PROMPT = 0.5        # s: a child this soon after its command ends is the command's own backing
LAGS = ((-np.inf, 0.0, "during"), (0.0, 0.5, "0-0.5 s"), (0.5, 1.0, "0.5-1 s"),
        (1.0, 2.0, "1-2 s"), (2.0, np.inf, "2-5 s"))


def episodes(mask):
    """(start, stop) sample indices of every run of True, stop exclusive."""
    m = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(m == 1), np.flatnonzero(m == -1)))


def _clock(tr):
    """Minutes spent improving and worsening, on `assays._chemo_score`'s own clock."""
    dc = tr["d_attractant"][1:]
    return (max((dc > 0).sum() * SAMPLE_DT, 1e-9) / 60.0,
            max((dc < 0).sum() * SAMPLE_DT, 1e-9) / 60.0)


def _rates(tr, labels):
    """(per minute while improving, per minute while worsening) for a list of labels,
    True = improving. With labels read at the onset sample this is exactly the shipped
    rate_up/rate_down."""
    t_up, t_dn = _clock(tr)
    lab = np.asarray(labels, dtype=bool)
    return lab.sum() / t_up, (~lab).sum() / t_dn


def audit(tr, seed, lead=LEAD, match=MATCH):
    """One trajectory, scored the shipped way and then taken apart.

    Every mechanical onset (the shipped event set: `reversals` rising edges) is matched
    to a PARENT -- the latest backward command (`gate_backward`) that starts no more than
    `lead` after the onset and ended no more than `match` before it -- or left an
    ORPHAN. That gives the four ways a mechanical count can differ from the circuit's:
    commands it never sees, commands it counts more than once, onsets no command
    explains, and onsets whose dC/dt label, read at the onset, disagrees with the one
    the circuit acted on, read when the command started.
    """
    from tools.assays import _chemo_score
    shipped = _chemo_score(tr, seed)

    rev = reversals(tr)
    cmd = tr["gate_backward"] >= 0.5
    n = len(rev)
    improving = tr["d_attractant"] > 0
    mech = [(a, b) for a, b in episodes(rev) if a > 0]     # the shipped onset set
    cmd_eps = episodes(cmd)
    starts = np.array([a for a, _ in cmd_eps], dtype=int)
    ends = np.array([b for _, b in cmd_eps], dtype=int)
    om = np.abs(tr["omega"])
    hd = np.unwrap(np.arctan2(tr["dir_y"], tr["dir_x"]))
    k_lead = int(round(lead / SAMPLE_DT))
    k_match = int(round(match / SAMPLE_DT))

    children = {}
    events = []
    for a, b in mech:
        k = np.flatnonzero(starts <= a + k_lead)
        parent = int(k[-1]) if k.size and a <= ends[k[-1]] + k_match else None
        e = min(b, n - 1)
        ev = dict(onset=int(a), parent=parent, dur=(b - a) * SAMPLE_DT,
                  omega=float(om[a]), swing=float(abs(hd[e] - hd[a])) * 180 / np.pi,
                  improving=bool(improving[a]))
        if parent is not None:
            ev["lag"] = (a - ends[parent]) * SAMPLE_DT
            ev["cmd_improving"] = bool(improving[starts[parent]])
            ev["first"] = parent not in children
            children.setdefault(parent, []).append(ev)
        events.append(ev)

    real = [i for i, a in enumerate(starts) if a > 0]      # same edge rule as `mech`
    return dict(
        seed=seed, shipped=shipped, events=events,
        n_cmd=len(real),
        cmd_dur_seen=[(ends[i] - starts[i]) * SAMPLE_DT for i in real if i in children],
        cmd_dur_missed=[(ends[i] - starts[i]) * SAMPLE_DT for i in real if i not in children],
        # the shipped definition, and the three repairs, each as (up, down) per minute
        mech_rates=_rates(tr, [e["improving"] for e in events]),
        dedup_rates=_rates(tr, [e["improving"] for e in events if e.get("first")]),
        relabel_rates=_rates(tr, [e["cmd_improving"] for e in events if e.get("first")]),
        cmd_rates=_rates(tr, [bool(improving[starts[i]]) for i in real]))


# ---------------------------------------------------------------------------- report
def _load(seed, arm):
    with np.load(_path(seed, arm)) as z:
        return {k: z[k] for k in z.files}


def _ratio_cell(rates):
    up = [x[0] for x in rates]
    dn = [x[1] for x in rates]
    return "%s  (%.2f / %.2f)" % (fmt(*ratio_ci(dn, up), spec="%.2f"),
                                  np.mean(dn), np.mean(up))


def _per_min(rows, pick):
    """Pooled improving-bin rate of the events `pick` selects (per animal, then mean)."""
    return np.mean([sum(1 for e in r["events"] if pick(e) and e["improving"])
                    / r["t_up"] for r in rows])


def report():
    have = {(s, a) for a in ARMS for s in SEEDS if os.path.exists(_path(s, a))}
    paired = [s for s in SEEDS if all((s, a) in have for a in ARMS)]
    print("\nPIROUETTE AUDIT -- %d paired seeds of %d, %.0f s each\n"
          % (len(paired), len(SEEDS), DURATION))
    if not paired:
        return 1
    trs = {a: {s: _load(s, a) for s in paired} for a in ARMS}
    rows = {a: [audit(trs[a][s], s) for s in paired] for a in ARMS}
    for a in ARMS:
        for r in rows[a]:
            r["t_up"] = _clock(trs[a][r["seed"]])[0]

    # -- 1. reproduce the record before believing anything else -----------------------
    print("1. REPRODUCTION -- assays._chemo_score on the audit's own trajectories")
    ok = True
    for a in ARMS:
        sh = [r["shipped"] for r in rows[a]]
        got = dict(ci=np.mean([r["ci"] for r in sh]),
                   n_rev=np.mean([r["n_rev"] for r in sh]),
                   rate_up=np.mean([r["rate_up"] for r in sh]))
        same = np.allclose([r["mech_rates"] for r in rows[a]],
                           [(r["rate_up"], r["rate_down"]) for r in sh])
        match = (all(abs(got[k] - RECORD[a][k]) < 0.006 for k in RECORD[a])
                 if len(paired) == len(SEEDS) else None)
        ok &= same and match is not False
        print("   %-18s CI %.3f  reversals %.2f  up %.2f/min   record %s   onset set %s"
              % (ARM_LABEL[a], got["ci"], got["n_rev"], got["rate_up"],
                 {True: "MATCHES", False: "DIFFERS", None: "(partial run)"}[match],
                 "identical" if same else "DIFFERS"))
    if not ok:
        print("   !! the audit is not measuring what chemo_power measured -- read no further")

    # -- 2. what the detector counted, against what the circuit commanded --------------
    print("\n2. ONSETS AGAINST COMMANDS (a child starts <= %.1f s before its command, or"
          " <= %.0f s after it ends)" % (LEAD, MATCH))
    for a in ARMS:
        ev = [e for r in rows[a] for e in r["events"]]
        kids = [e for e in ev if e["parent"] is not None]
        seen = [d for r in rows[a] for d in r["cmd_dur_seen"]]
        missed = [d for r in rows[a] for d in r["cmd_dur_missed"]]
        nc = len(seen) + len(missed)
        print("   %s" % ARM_LABEL[a])
        print("     %d commands (median %.2f s long); the detector saw %d (%.0f%%) and"
              " never saw %d"
              % (nc, np.median(seen + missed), len(seen), 100.0 * len(seen) / max(nc, 1),
                 len(missed)))
        print("     %d mechanical onsets = %d first children + %d REPEATS of a command"
              " already counted + %d ORPHANS"
              % (len(ev), sum(e["first"] for e in kids),
                 sum(not e["first"] for e in kids), len(ev) - len(kids)))
        print("     first children: %d PROMPT (before the command ends, or < %.1f s after),"
              " %d LATE"
              % (sum(e["first"] and e["lag"] < PROMPT for e in kids), PROMPT,
                 sum(e["first"] and e["lag"] >= PROMPT for e in kids)))
        print("     %-9s %6s %7s %9s %8s %8s   (children by lag after the command ends)"
              % ("lag", "onsets", "repeat", "episode", "|omega|", "swing"))
        for lo, hi, label in LAGS:
            g = [e for e in kids if lo <= e["lag"] < hi]
            if g:
                print("     %-9s %6d %6.0f%% %7.2f s %8.2f %5.0f deg"
                      % (label, len(g), 100 * np.mean([not e["first"] for e in g]),
                         np.median([e["dur"] for e in g]),
                         np.median([e["omega"] for e in g]),
                         np.median([e["swing"] for e in g])))

    # -- 3. whose dC/dt? ------------------------------------------------------------------
    print("\n3. THE LABEL -- dC/dt when the circuit decided vs when the detector noticed"
          " (first children)")
    for a in ARMS:
        first = [e for r in rows[a] for e in r["events"] if e.get("first")]
        m = {(c, d): sum(1 for e in first if e["cmd_improving"] == c and e["improving"] == d)
             for c in (True, False) for d in (True, False)}
        print("   %-18s command worsening -> onset reads improving %2d, worsening %2d;"
              "  command improving -> improving %2d, worsening %2d"
              % (ARM_LABEL[a], m[(False, True)], m[(False, False)],
                 m[(True, True)], m[(True, False)]))

    # -- 4. the ratio, four ways ---------------------------------------------------------
    print("\n4. THE PIROUETTE RATIO, down/up (pooled over animals; 95% bootstrap over"
          " animals; per-min rates)")
    cols = (("mech_rates", "all mechanical (shipped)"),
            ("dedup_rates", "first children only"),
            ("relabel_rates", "...labelled at the command"),
            ("cmd_rates", "command onsets"))
    for key, label in cols:
        print("   %-26s %s" % (label, "   ".join(
            "%s %s" % (ARM_LABEL[a].split()[0], _ratio_cell([r[key] for r in rows[a]]))
            for a in ARMS)))
    print("   ('labelled at the command' = the detector's first children, with dC/dt read"
          " when their command\n    began; the animal's ratio is ~2)")

    # -- 5. the up-gradient budget ------------------------------------------------------
    print("\n5. THE UP-GRADIENT BUDGET -- where did the extra 'improving' onsets come from?")
    parts = (("prompt firsts", lambda e: e.get("first", False) and e["lag"] < PROMPT),
             ("late firsts", lambda e: e.get("first", False) and e["lag"] >= PROMPT),
             ("repeats", lambda e: e["parent"] is not None and not e["first"]),
             ("orphans", lambda e: e["parent"] is None))
    up = {a: np.mean([r["mech_rates"][0] for r in rows[a]]) for a in ARMS}
    rise = up[0] - up[1]
    print("   improving-bin rate %.2f -> %.2f/min (%+.2f)" % (up[1], up[0], rise))
    for label, pick in parts:
        d = _per_min(rows[0], pick) - _per_min(rows[1], pick)
        print("     %-15s %+.2f/min  (%4.0f%% of the rise)"
              % (label, d, 100 * d / rise if abs(rise) > 1e-9 else float("nan")))
    cu = {a: np.mean([r["cmd_rates"][0] for r in rows[a]]) for a in ARMS}
    print("   the circuit's own improving-bin command rate: %.2f -> %.2f/min (%+.2f)"
          % (cu[1], cu[0], cu[0] - cu[1]))

    # -- 6. paired: did the circuit's own conditioning change? ---------------------------
    print("\n6. PAIRED, per animal: conditioning contrast = down rate - up rate (/min)")
    for label, key in (("all mechanical", "mech_rates"), ("command onsets", "cmd_rates")):
        c = {a: np.array([r[key][1] - r[key][0] for r in rows[a]]) for a in ARMS}
        d = paired_ci(c[1], c[0])
        print("   %-15s shipped %+.2f  old %+.2f  shipped-old %s  %s"
              % (label, c[0].mean(), c[1].mean(), fmt(*d, spec="%+.2f"), verdict(*d)))

    # -- 7. how much of this is the two windows -------------------------------------------
    print("\n7. SENSITIVITY to the matching windows (repeats and orphans as a share of all"
          " mechanical onsets)")
    for lead, match in ((0.25, MATCH), (1.0, MATCH), (LEAD, 2.0), (LEAD, 3.0), (LEAD, 8.0)):
        line = []
        for a in ARMS:
            rs = [audit(trs[a][s], s, lead=lead, match=match) for s in paired]
            ev = [e for r in rs for e in r["events"]]
            rep = sum(1 for e in ev if e["parent"] is not None and not e["first"])
            orph = sum(1 for e in ev if e["parent"] is None)
            line.append("%s repeats %2.0f%% orphans %2.0f%% ratio(-rep,-orph) %s"
                        % (ARM_LABEL[a].split()[0], 100.0 * rep / max(len(ev), 1),
                           100.0 * orph / max(len(ev), 1),
                           fmt(*ratio_ci([r["dedup_rates"][1] for r in rs],
                                         [r["dedup_rates"][0] for r in rs]), spec="%.2f")))
        print("   lead %.2f s, match %.0f s:  %s" % (lead, match, "  |  ".join(line)))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    sys.exit({"run": run, "report": report, "omega": omega}[cmd]())
