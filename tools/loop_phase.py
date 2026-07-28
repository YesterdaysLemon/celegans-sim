"""Open the head loop and measure it, stage by stage, at two step sizes.

Everything about the gait's step dependence has so far been inferred from the gait: sweep
a parameter, look at the frequency, guess. Twenty-five configurations later the drift has
never gone below 38% and the suspects -- the body integrator, the head time constant, the
segmental oscillators, the reflex gains, the transport delay, the gap-junction solve --
have been ruled out one at a time without a replacement. This looks at the loop itself.

A negative-feedback loop oscillates where its open-loop gain reaches 1 with 180 degrees of
phase. Every parameter tried moves that crossing indirectly; the crossing is what actually
decides the frequency, and it is measurable.

The method is a lock-in. Silence the head reflex (`head_proprio_gain = 0`), inject in its
place a pure sinusoid with the reflex's own dorsoventral sign pattern, and record what
comes back round the loop:

    injected current  ->  head motor neuron voltage (ventral minus dorsal)
                      ->  synaptic release          (ventral minus dorsal)
                      ->  head muscle tension       (dorsal minus ventral)
                      ->  head curvature

Each arrow is a stage with its own gain and phase at the drive frequency, extracted by
correlating against exp(-2 pi i f t). The product of the four is the plant; multiplying by
the receptor's own transfer function -- the transport delay and the first-order lag, both
of which are known analytically -- gives the loop gain, and the frequency at which its
phase reaches 180 degrees is the gait.

Run it at dt = 0.5 and 0.125 ms and the stage that differs is the one responsible. If they
all differ a little, the step dependence is distributed and no single fix exists. Either
answer ends the guessing.

What it found, which was not a phase problem at all.

The stage columns settled it in one pass. At dt = 0.5 and 0.125 ms the neurons agree to
0.3 degrees, the synapses to 0.1, and the muscle transfer to 1 -- while tension-to-curvature
differed by 10 to 31 degrees with the plant gain differing by up to 86%. The nervous system
was never the problem.

Then four eliminations, each ruling out the obvious reading of that:

  * substepping the mechanics 16x at dt = 0.5 reproduced dt = 0.5 exactly, not dt = 0.125,
    so the body's own integration was already converged;
  * ca_ratio 0, removing the Hopf bifurcation the B class sits on, left the gap unchanged;
  * opening every feedback path (proprio_gain 0) left it unchanged, so it was feedforward;
  * with the noise off, the joint-moment profile along the *whole* body was identical to
    0.1%, mean and oscillating alike, while head curvature differed by 18% in amplitude and
    24 degrees in phase.

Same moment field, same body, different answer -- and driving `Body` alone with an analytic
moment showed it converged to 0.05% in amplitude and 0.01 degrees in phase over a 32-fold
range of dt. Those two facts cannot both be true of a correctly coupled model, which is
what finally pointed at the coupling rather than at either end of it.

**`BodyParams.dt` was not shared with the neural step, and its comment said it was.** `Body`
kept its own timestep; `Simulation` used `NeuralParams.dt`; nothing synchronised them. So
changing the neural step left the body advancing 0.5 ms per call while the rest of the
animal believed it had advanced by the neural step -- at dt = 0.125 ms the body ran four
times fast relative to its own nervous system.

Every timestep-convergence result in this project was therefore measuring that
desynchronisation and not any numerical error, and the conclusion drawn from them -- that
the gait exists at one step size and is otherwise incoherent -- is withdrawn.

Run:  PYTHONPATH=. .venv/bin/python tools/loop_phase.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import bare_world
from worm.engine import Simulation
from worm.params import Params

SETTLE_CYCLES = 6.0        # cycles of the drive discarded before measuring
MEASURE_CYCLES = 10.0      # cycles used for the lock-in
SAMPLE_HZ = 400.0          # fixed, so both step sizes are sampled identically
DRIVE = 60.0               # pA, the amplitude injected in place of the reflex
FREQS = (0.2, 0.35, 0.5, 0.8, 1.2, 2.0)


def _lockin(x, t, f):
    """Amplitude and phase of x at frequency f. Phase in degrees, lag negative."""
    x = np.asarray(x) - np.mean(x)
    w = np.exp(-2j * np.pi * f * np.asarray(t))
    c = 2.0 * np.sum(x * w) / len(x)
    return float(np.abs(c)), float(np.degrees(np.angle(c)))


def _job(job):
    freq, dt_ms, sub, ca, seed = job
    p = Params()
    p = dataclasses.replace(
        p,
        neural=dataclasses.replace(p.neural, dt=dt_ms * 1e-3),
        body=dataclasses.replace(p.body, substeps=sub),
        # head_proprio_gain 0 opens the head loop; `ca` here doubles as the *body* reflex
        # gain, so the 0.0 rows have every feedback path in the animal opened and the
        # measurement is purely feedforward: current -> neuron -> muscle -> body.
        sensory=dataclasses.replace(p.sensory, head_proprio_gain=0.0,
                                    proprio_gain=ca))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    dt = p.neural.dt

    sgn = sim.senses.W_head_sign * sim.senses.g_scale_head
    dorsal = np.flatnonzero(sim.senses.W_head_sign < 0)
    ventral = np.flatnonzero(sim.senses.W_head_sign > 0)
    head_win = sim.senses._head_window

    base = sim.senses.sense
    clock = {"t": 0.0}

    def wrapped(*a, **k):
        I = base(*a, **k)
        I += sgn * (DRIVE * np.sin(2 * np.pi * freq * clock["t"]))
        return I

    sim.senses.sense = wrapped

    n_settle = int(SETTLE_CYCLES / freq / dt)
    n_meas = int(MEASURE_CYCLES / freq / dt)
    every = max(1, int(round(1.0 / (SAMPLE_HZ * dt))))

    for _ in range(n_settle):
        clock["t"] = sim.t
        sim.step()

    t0 = sim.t
    ts, drive, volt, rel, tens, curv = [], [], [], [], [], []
    for i in range(n_meas):
        clock["t"] = sim.t
        sim.step()
        if i % every:
            continue
        ts.append(sim.t - t0)
        drive.append(np.sin(2 * np.pi * freq * (sim.t - dt)))
        v, s = sim.nervous.V, sim.nervous.s
        volt.append(float(v[ventral].mean() - v[dorsal].mean()))
        rel.append(float(s[ventral].mean() - s[dorsal].mean()))
        d, ven = sim.muscles.row_tension()
        tens.append(float(d[:5].mean() - ven[:5].mean()))
        kk = np.clip(sim.body.curvature() / 5.0, -2.0, 2.0)
        curv.append(float(np.dot(head_win, kk)))

    out = {}
    for name, sig in (("drive", drive), ("volt", volt), ("rel", rel),
                      ("tens", tens), ("curv", curv)):
        amp, ph = _lockin(sig, ts, freq)
        out[name + "_a"] = amp
        out[name + "_p"] = ph
    out.update(freq=freq, dt_ms=dt_ms, sub=sub, ca=ca, seed=seed)
    return out


def main():
    # dt 0.5 with n substeps has the same mechanical resolution as dt 0.5/n, at a
    # quarter of the neural cost. If the phase follows the mechanical resolution rather
    # than the neural one, the body is confirmed as the whole story.
    # Substepping the mechanics changed nothing, so the body integrator is not it. What
    # remains inside the "tension to curvature" stage is the body reflex, which is still
    # closed, and the B-class units it drives -- held *at* their Hopf bifurcation, which is
    # the most perturbation-sensitive place a dynamical system can sit. ca_ratio 0 removes
    # the regenerative conductance and makes them passive relays. If the two step sizes
    # then agree, the bifurcation is the whole story.
    CONFIGS = ((0.5, 1, 30.0), (0.125, 1, 30.0), (0.5, 1, 0.0), (0.125, 1, 0.0))
    jobs = [(f, d, sb, ca, s) for f in FREQS for d, sb, ca in CONFIGS for s in (0, 3)]
    print("LOOP PHASE -- %d trials, lock-in on the open head loop" % len(jobs))
    print("  reflex silenced, %.0f pA injected in its place\n" % DRIVE)
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["freq"], r["ca"], r["dt_ms"]), []).append(r)
    m = lambda g, k: float(np.mean([x[k] for x in g]))              # noqa: E731

    def wrap(d):
        return (d + 180.0) % 360.0 - 180.0

    p = Params().sensory
    print("  stage phases in degrees, relative to the injected sinusoid.")
    print("  'plant' is the whole open loop from current to head curvature.\n")
    print("   f Hz | body gain  dt ms |  neuron  release  muscle  curvature | plant gain")
    for key in sorted(agg):
        g = agg[key]
        print("  %5.2f |   %5.1f    %5.3f | %+7.1f %+7.1f %+7.1f  %+8.1f  |  %.3e"
              % (key[0], key[1], key[2], wrap(m(g, "volt_p") - m(g, "drive_p")),
                 wrap(m(g, "rel_p") - m(g, "volt_p")),
                 wrap(m(g, "tens_p") - m(g, "rel_p")),
                 wrap(m(g, "curv_p") - m(g, "tens_p")),
                 m(g, "curv_a") / DRIVE))

    print()
    print("  body gain 0 opens every feedback path: the measurement is then purely")
    print("  feedforward. If the two step sizes still disagree there, the difference is in")
    print("  the forward mechanics; if they agree, it is the body reflex loop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
