"""Does the body ever pass through itself, and at what turn radius would it start?

The mechanics have no self-avoidance. `World.contact_force` repels the body from the dish
wall and from obstacles, and `Body.step` takes that as an external `node_forces` term, but
nothing anywhere compares the body against itself. A sufficiently deep bend is therefore
free to fold the animal through its own tail, and no assay in this repo would notice: a
reorientation earned by ghosting through the body reads as a clean turn in
`tools/compare.py ethogram`.

That is worth knowing about *before* the turn-depth project, not after. While turns are
shallow the constraint should be inert, which makes now the only moment it can be installed
and shown to change nothing. Added afterwards, a regression could never be separated into
"the turn was passing through the body" and "the contact model is too stiff".

So this measures two things.

**How close the animal actually gets**, over seeds and both food conditions. Clearance is
the centre-line distance between two body nodes minus the sum of their radii, so zero is
skin contact and negative is interpenetration.

Which pairs count is not a free choice, and it is not one number. Two nodes a few segments
apart sit inside each other's contact distance on a perfectly straight worm -- that is the
body being a continuous tube, not a collision -- so any pair separated along the body by
less than its own contact distance has to be dropped. But the pairs just past that
threshold then sit permanently at a hair above zero clearance, which makes a single
"minimum clearance" number pinned near zero and carrying no information at all. The
quantity is genuinely scale-dependent, so it is reported as a sweep over how far apart
along the body a pair must be, each row printed next to the clearance a *straight* worm
would give at that separation. A row at its straight-body baseline means the body never
approached itself at that scale; the signal is a row falling below its own baseline.

**Where the geometry actually bites.** The turn the roadmap wants needs a 0.22 mm radius
(NEXT.md, "the one problem worth solving first"). Coiling the body's own radius profile
into a uniform arc and shrinking it until clearance reaches zero says whether a turn that
deep would have self-intersected at all -- that is, whether self-avoidance is a
prerequisite for the turn project or an independent gap.

Node positions are sampled rather than segment-to-segment distances computed. Node spacing
is 0.021 mm against a midbody contact distance near 0.07 mm, so the discretisation misses
a true closest approach by under half a segment, which does not change any conclusion here.

This covers one animal folding onto itself. Two animals in one dish never interact at all:
`stepAll` in wasm/assembly/index.ts steps each worm independently and they share only the
plate they eat from. That is a separate gap, and it lives on the WASM side only.

Run:  PYTHONPATH=. .venv/bin/python tools/self_contact.py
"""

from __future__ import annotations

import argparse

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from worm.body import radius_profile
from worm.engine import Simulation
from worm.params import Params
from worm.world import default_world

SECONDS = 60.0
SEEDS = (0, 1, 3, 5, 7)
WARMUP = 4.0

# How far apart two nodes must be along the body to count, as a fraction of body length.
# The smallest is above the widest contact distance (0.07 mm on a 1 mm body), below which
# a straight worm reports overlap and the measurement means nothing.
CUTS = (0.10, 0.15, 0.20, 0.30, 0.50)

# The turn radius NEXT.md says an omega needs, for the geometric arm to be measured against.
OMEGA_RADIUS = 0.22


def node_radii(p) -> np.ndarray:
    """(n+1,) body radius at each node."""
    return radius_profile(np.arange(p.n_links + 1) / p.n_links, p.radius_max)


def geometry(p) -> tuple[np.ndarray, np.ndarray]:
    """(n+1, n+1) contact distance for every node pair, and their separation along the body."""
    n = p.n_links
    r = node_radii(p)
    contact = r[:, None] + r[None, :]
    sep = np.abs(np.arange(n + 1)[:, None] - np.arange(n + 1)[None, :]) * (p.length / n)
    return contact, sep


def cut_mask(contact: np.ndarray, sep: np.ndarray, cut: float, length: float) -> np.ndarray:
    """Pairs at least `cut` of the body apart, and never closer along the body than they
    are wide -- the second condition is what stops a straight worm reporting overlap."""
    return (sep >= cut * length) & (sep > contact)


def baseline(contact: np.ndarray, sep: np.ndarray, mask: np.ndarray) -> float:
    """Clearance a perfectly straight worm gives at this cut. The measurement's zero."""
    return float((sep - contact)[mask].min())


def clearances(nodes: np.ndarray, contact: np.ndarray) -> np.ndarray:
    """(n+1, n+1) centre-line distance minus contact distance, for every node pair."""
    d = nodes[:, None, :] - nodes[None, :, :]
    return np.sqrt((d * d).sum(axis=2)) - contact


# ------------------------------------------------------------------ the geometric arm

def coil_clearance(p, radius: float, cut: float = 0.20) -> float:
    """Min clearance when the whole body is bent into a uniform arc of the given radius."""
    contact, sep = geometry(p)
    mask = cut_mask(contact, sep, cut, p.length)
    phi = np.arange(p.n_links + 1) * (p.length / p.n_links) / radius
    nodes = np.stack([radius * np.cos(phi), radius * np.sin(phi)], axis=1)
    return float(clearances(nodes, contact)[mask].min())


def coil_threshold(p, cut: float = 0.20) -> float:
    """The largest turn radius at which a uniform coil first touches itself, in mm.

    Bisected: a tighter coil brings the ends together, so clearance is monotone in radius
    over this range.
    """
    lo, hi = 0.05, 1.0
    if coil_clearance(p, lo, cut) > 0.0:
        return float("nan")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if coil_clearance(p, mid, cut) > 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------- the empirical arm

def _job(job):
    condition, seed, seconds = job
    p = Params()
    rng = np.random.default_rng(seed)
    world = bare_world(p) if condition == "off food" else default_world(p.world, rng)
    sim = Simulation(p, seed=seed, world=world)

    contact, sep = geometry(p.body)
    masks = [cut_mask(contact, sep, c, p.body.length) for c in CUTS]
    sim.run(WARMUP)

    every = max(1, int(round(0.05 / sim.dt)))
    n = int(seconds / sim.dt)
    worst = [np.inf] * len(CUTS)
    hits = [0] * len(CUTS)
    samples = 0
    worst_pair = (0, 0)
    heading = []

    for i in range(n):
        sim.step()
        if i % every:
            continue
        samples += 1
        c = clearances(sim.body.nodes(), contact)
        for k, m in enumerate(masks):
            v = float(c[m].min())
            if v < worst[k]:
                worst[k] = v
                if k == 0:
                    flat = np.where(m, c, np.inf)
                    worst_pair = tuple(int(x) for x in
                                       np.unravel_index(flat.argmin(), flat.shape))
            if v < 0.0:
                hits[k] += 1
        d = sim.body.body_direction()
        heading.append(float(np.arctan2(d[1], d[0])))

    # Deepest reorientation over any two-second window, for context on how hard the body
    # was being asked to bend while these clearances were measured.
    h = np.unwrap(np.array(heading))
    span = max(1, int(round(2.0 / (every * sim.dt))))
    turn = float(np.abs(h[span:] - h[:-span]).max()) if h.size > span else 0.0

    return dict(condition=condition, seed=seed, samples=samples,
                worst=worst, frac=[x / max(samples, 1) for x in hits],
                worst_i=worst_pair[0], worst_j=worst_pair[1],
                max_turn=float(np.degrees(turn)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=SECONDS)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    ap.add_argument("--procs", type=int, default=8)
    args = ap.parse_args()

    p = Params()
    seg = p.body.length / p.body.n_links
    r = node_radii(p.body)
    contact, sep = geometry(p.body)

    print("SELF-CONTACT -- does the body pass through itself\n")
    print("  body %.2f mm over %d links, segment %.4f mm"
          % (p.body.length, p.body.n_links, seg))
    print("  radius %.4f mm at the nose, %.4f at its widest, %.4f at the tail"
          % (r[0], r.max(), r[-1]))
    print("  widest contact distance %.4f mm, which is %.1f segments\n"
          % (2 * r.max(), 2 * r.max() / seg))

    # ---- geometry first: it costs nothing and it frames the measurement.
    thresh = coil_threshold(p.body)
    print("  GEOMETRY -- the whole body bent into a uniform arc")
    print("  %-16s %16s   %s" % ("turn radius mm", "clearance mm", ""))
    for radius in (0.50, 0.35, OMEGA_RADIUS, 0.18, 0.16, 0.14):
        cl = coil_clearance(p.body, radius)
        note = "<- the omega NEXT.md wants" if radius == OMEGA_RADIUS else ""
        note = note or ("touching" if cl <= 0 else "")
        print("  %-16.2f %16.4f   %s" % (radius, cl, note))
    print()
    print("  a uniform coil first touches itself at radius %.3f mm, which is the body" % thresh)
    print("  closed into a circle (L/2pi = %.3f). The omega needs %.2f mm, %.1fx clear of it."
          % (p.body.length / (2 * np.pi), OMEGA_RADIUS, OMEGA_RADIUS / thresh))
    print("  So a turn at the depth the roadmap asks for does NOT require self-avoidance."
          if OMEGA_RADIUS > thresh else
          "  So a turn at the depth the roadmap asks for DOES self-intersect.")

    # ---- then the animal itself.
    jobs = [(c, s, args.seconds) for c in ("off food", "on food") for s in args.seeds]
    print()
    print("  MEASURED -- %d seeds x %.0f s in each condition, sampled every 50 ms"
          % (len(args.seeds), args.seconds))
    rows = pooled(_job, jobs, procs=args.procs)
    if not rows:
        print("  no trials completed")
        return 1

    print("  %-10s %8s %14s %14s %10s"
          % ("condition", "cut", "min clearance", "straight-body", "overlap %"))
    live = False
    for cond in ("off food", "on food"):
        g = [r_ for r_ in rows if r_["condition"] == cond]
        if not g:
            continue
        for k, cut in enumerate(CUTS):
            w = np.array([r_["worst"][k] for r_ in g])
            f = np.array([r_["frac"][k] for r_ in g])
            live = live or bool((f > 0).any())
            base = baseline(contact, sep, cut_mask(contact, sep, cut, p.body.length))
            print("  %-10s %7.0f%% %6.4f +- %.4f %14.4f %10.2f"
                  % (cond if k == 0 else "", 100 * cut, w.mean(), w.std(), base,
                     100 * f.mean()))

    tn = np.array([r_["max_turn"] for r_ in rows])
    worst = min(rows, key=lambda r_: r_["worst"][0])
    print()
    print("  deepest 2 s reorientation seen: %.1f deg (mean over runs %.1f)"
          % (tn.max(), tn.mean()))
    print("  closest approach at the 10%% cut: %.4f mm, nodes %d and %d, %s seed %d"
          % (worst["worst"][0], worst["worst_i"], worst["worst_j"],
             worst["condition"], worst["seed"]))
    print()
    if live:
        print("  VERDICT: live. The body is interpenetrating in the current model, so every")
        print("  reorientation measured since is suspect. Self-avoidance is not cleanup --")
        print("  it is a correctness fix, and it blocks the turn work rather than following it.")
        return 1

    # How much of the straight-body margin the undulation actually consumes at the widest
    # cut. Reported because a statistic that only ever echoes its own baseline would look
    # identical to this one, and could not be told apart from a broken measurement.
    wide = np.mean([r_["worst"][-1] for r_ in rows])
    wide_base = baseline(contact, sep, cut_mask(contact, sep, CUTS[-1], p.body.length))
    tight = min(r_["worst"][k] for r_ in rows for k in range(len(CUTS)))

    print("  VERDICT: latent. Nothing goes negative in any run. The tightest approach")
    print("  anywhere is %.4f mm, which is %.1f body diameters of daylight."
          % (tight, tight / (2 * r.max())))
    print("  The statistic is not simply echoing its baseline: undulation consumes %.0f%% of"
          % (100 * (1 - wide / wide_base)))
    print("  the straight-body margin at the %.0f%% cut, and the geometry arm above drives the"
          % (100 * CUTS[-1]))
    print("  same number negative at 0.14 mm, so it would fire if the body ever folded.")
    print("  The omega the roadmap wants coils to %.2f mm where contact begins at %.3f, so"
          % (OMEGA_RADIUS, thresh))
    print("  self-avoidance is a real gap but it is not what caps turn depth, and closing")
    print("  it will not deepen a single turn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
