"""What sets the wave's phase velocity, and can it be set to the animal's?

Wavelength and frequency are not two problems. Their product is the phase velocity of the
undulation, and that is the quantity a reflex chain actually determines:

    model    0.52 L at 1.23 Hz  ->  0.64 L/s
    animal   0.65 L at 0.40 Hz  ->  0.26 L/s

Two and a half times too fast, and every attempt to fix the frequency alone has moved the
wavelength the wrong way in compensation, because the chain holds their product roughly
fixed and lets the pair slide along it.

There is a law to test. If each segment copies the curvature a distance D anterior to it
after a response delay T, then a travelling wave kappa = A sin(ks - wt) is self-consistent
only when the spatial offset and the temporal lag cancel:

    sin(ks - wt)  ~  sin(k(s - D) - w(t - T))   =>   kD = wT   =>   lambda * f = D / T

So the phase velocity is the proprioceptive reach divided by the loop's response delay,
and nothing else. If that holds here, the two knobs are `proprio_reach` and whatever sets
T -- and the prediction is sharp: **lambda * f should be proportional to reach**, with the
frequency and the wavelength free to trade against each other however they like.

If it does not hold, the wave is not being propagated by the reflex at all and the whole
reflex-chain account of this gait is wrong, which is worth knowing for its own sake.

What four passes of this actually found.

**The law is false here, and the reason is the useful part.** Sweeping reach over a
3.75-fold range moves the wavelength from 0.49 to 0.64 L and leaves the frequency flat at
1.167-1.178 Hz. So lambda and f are not two views of one phase velocity in this model:
reach sets the wavelength and nothing else, and the frequency belongs entirely to the head
loop. Every note in this project that treats the two as one problem is wrong on this
evidence, and the good news is that the wavelength is now right -- 0.64 L against the
animal's 0.65, at no cost to speed (0.218 against a measured 0.219).

**The frequency has no working setting.** Four sweeps, all at reach 0.30:

  * head_tau 0.22 -> 2.00 halves it, 1.178 -> 0.544 Hz, and takes curvature from 2.40 to
    1.12 and net speed from 0.218 to 0.038 with it. The filter buys phase by throwing
    away gain.
  * pairing that filter with a compensating head gain -- which nobody had tried, since
    every earlier sweep moved one at a time -- does recover the amplitude: head_tau 1.0
    with gain 400 gives 0.656 Hz, curvature 3.11, speed 0.228. And the wavelength blows
    out to 3.09 L, a third of a wave on the whole body.
  * doubling the body reflex gain, which is day two's queued and never-run experiment,
    destroys the wave outright at every head gain: TWI at or below zero, curvature 6.4 to
    8.1 against a measured 4.3, and a reported frequency of 0.100 Hz which is the bottom
    FFT bin and means no coherent oscillation at all.
  * backing the head off with the body reflex left alone reaches 0.544 Hz at net speed
    0.006 mm/s. Dead.

**And none of it converges.** The drift in frequency between dt = 0.5 and 0.125 ms is 44%
at the shipped setting and 67-86% everywhere else, in nineteen configurations spanning
reach, head_tau, head gain, body gain and ca_ratio. At the fine step *every* configuration
falls to 0.13-0.20 Hz with a wavelength of 2 to 6 L and a travelling index of 0.17 to 0.41.

That is the conclusion, and it is larger than a tuning result: **the coherent 1.2 Hz gait
exists at dt = 0.5 ms and nowhere else in the parameter space swept.** Integrated
accurately, this head-driven reflex chain does not produce C. elegans locomotion. The
mechanism is visible in the head pool's own numbers -- RMD, SMD and SMB have membrane time
constants of 0.93 to 2.34 ms, so the shipped step is 0.21 to 0.54 of a time constant and
the loop's fast dynamics are marginally resolved; at 0.125 ms they resolve, the fast mode
stops being damped for free, and the slow attractor that takes over is not a gait.

So the next move is not another parameter. It is either an explicit physical delay in the
loop to replace the numerical one it has been leaning on, or a rhythm generator that does
not depend on the head loop's phase crossover at all.

Run:  PYTHONPATH=. .venv/bin/python tools/wave_speed.py
"""

from __future__ import annotations

import dataclasses

import numpy as np

from tools.assays import pooled
from tools.diagnose_loop import analyse, bare_world
from worm.params import Params
from worm.engine import Simulation

MEASURE = 30.0
SEEDS = (0, 3, 7)
# Reach sets the wavelength and does nothing at all to the frequency (first pass, below).
# 0.30 is where the wavelength lands on the animal's 0.65 L, so it is held there while the
# frequency is attacked with the head loop's own time constant -- and checked at two step
# sizes, because a slower head loop should also be the one that stops the integrator
# choosing which limit cycle the animal falls into.
REACH = 0.30
# Day two queued this and never ran it: with the body reflex strong enough to carry the
# wave, back the head off and see whether the slow attractor becomes the robust one. The
# missing half was knowing what "strong enough" meant, and the reach pass above supplies
# it -- 0.30 is where the wavelength lands on the animal's 0.65 L.
# head_tau sets the *phase* of the head loop and therefore the frequency; it also
# attenuates the drive by 1/sqrt(1 + (2 pi f tau)^2), which at tau = 2 s and 0.5 Hz is a
# factor of six. Every sweep so far moved one or the other, so the frequency always came
# with a collapsed amplitude. These pair them: the filter picks the frequency, the gain
# pays for what the filter costs.
# A pure transport delay contributes phase 2*pi*f*delay exactly, at every frequency, and
# is specified in seconds -- so unlike every lag already in this loop, the crossover it
# sets cannot depend on the step size. The honest expectation is modest: at 1.18 Hz a
# physiological 50 ms is only 21 degrees, so it should shift the frequency by about a
# tenth. The reason to run it anyway is the drift column, not the frequency column.
HEAD_DELAY = (0.60,)
REACHES = (0.10, 0.13, 0.16)
STEPS_MS = (0.5, 0.125)


def _job(job):
    delay, reach, dt_ms, seed = job
    p = Params()
    p = dataclasses.replace(
        p,
        neural=dataclasses.replace(p.neural, dt=dt_ms * 1e-3),
        sensory=dataclasses.replace(p.sensory, proprio_reach=reach,
                                    head_delay=delay))
    sim = Simulation(p, seed=seed, world=bare_world(p))
    r = analyse(sim, seconds=MEASURE)
    lam = r["wavelength"]
    return dict(delay=delay, reach=reach, dt_ms=dt_ms, seed=seed,
                freq=r["freq"], wavelength=lam,
                phase_v=lam * r["freq"] if np.isfinite(lam) else float("nan"),
                twi=r["twi"], speed=r["speed"], k_rms=r["kappa_rms"],
                direction=r["direction"])


def main():
    jobs = [(dl, rc, d, s) for dl in HEAD_DELAY for rc in REACHES
            for d in STEPS_MS for s in SEEDS]
    print("WAVE SPEED -- %d trials x %.0f s" % (len(jobs), MEASURE))
    print("  testing  lambda * f  =  reach / delay\n")
    rows = pooled(_job, jobs, procs=8)
    if not rows:
        print("  no trials completed")
        return 1

    agg = {}
    for r in rows:
        agg.setdefault((r["delay"], r["reach"], r["dt_ms"]), []).append(r)
    f = lambda g, k: float(np.nanmean([x[k] for x in g]))          # noqa: E731

    print("  delay  reach |  dt ms |  freq Hz  wavelen L |   TWI    k_rms   speed mm/s")
    for key in sorted(agg):
        g = agg[key]
        print("   %.2f   %.2f  | %5.3f |  %6.3f   %6.2f   |  %+.3f  %5.2f   %.4f"
              % (key[0], key[1], key[2], f(g, "freq"), f(g, "wavelength"),
                 f(g, "twi"), f(g, "k_rms"), f(g, "speed")))
    print()
    print("  drift between the two step sizes:")
    for dl in HEAD_DELAY:
        for rc in REACHES:
            a, b = agg.get((dl, rc, 0.5)), agg.get((dl, rc, 0.125))
            if a and b:
                fa, fb = f(a, "freq"), f(b, "freq")
                print("    delay %.2f reach %.2f:  %.3f -> %.3f Hz   drift %4.0f%%   "
                      "TWI %+.2f -> %+.2f"
                      % (dl, rc, fa, fb, 100 * abs(fb - fa) / max(fa, 1e-9),
                         f(a, "twi"), f(b, "twi")))

    print()
    print("  want: 0.40 Hz at 0.65 L, phase velocity 0.26 L/s, curvature rms 4.3 /mm,")
    print("  net speed 0.219 mm/s, and a frequency that does not move with the step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
