# Where this is, and what to do next

> ## Day seven. Four bugs, three refutations, one memory, and one thing left to fix.
>
> **State: 37 tests pass. Locomotion untouched. The model has a memory for the first time,
> and a clearer account of what is wrong with it than it has had.**
>
> ### Read this first: everything now fails at one junction
>
> Chemotaxis, aerotaxis, nociception, tap withdrawal and now learning all fail, and after
> today they all fail *for the same measured reason*. The direction gate sits **3.81
> standard deviations** from its own decision boundary. A physiological chemosensory signal
> moves it by 0.008 sigma. A tap moves the backward command pool by 0.02 in activation,
> against the 0.107 it would need. So:
>
> * the animal never spontaneously reverses (zero in six animals over sixty seconds),
> * a tap does not reverse it either (+0.675 mm of forward progress after a tap against
>   +0.686 with none, and +0.654 at three times the strength),
> * and habituation, which is now implemented and provably works at the receptor, has no
>   behaviour to decrement.
>
> There is no longer a list of separate sensory problems. There is one problem, it is
> measured, and it is `Senses.sense`'s direction gate. **Fix that before anything else.**
>
> The leading structural idea is unchanged from day six and is a small change: the gate
> still does two jobs -- it picks the direction *and* it apportions how much drive each
> cord receives -- which is the same conflation day five only half removed. Separating the
> latched, hysteretic choice of *which* cord from the constant *amount* is what would let
> the decision move without dragging the gait with it.
>
> ### Four bugs, in the order they were found
>
> **1. The gait is not converged at the timestep it ships at**, and two headline numbers
> change meaning. Halving the step from 0.25 to 0.125 ms still moves the frequency by 15%
> and net speed by 17%, against a seed spread of 0.03 Hz, monotonically across a sixteen-
> fold range. The frequency discrepancy is therefore *worse* than reported -- refine and it
> runs away from the animal, reaching 1.62 Hz at 0.125 ms -- and the crawling speed
> agreeing with the measured 0.219 mm/s is partly an artefact of this step size, since at
> 0.125 ms it does 0.3245. `tools/timestep_convergence.py`, four minutes.
>
> **2. Mechanosensation scaled with the timestep.** `touch_state` accumulated one whole
> force per step and leaked with `touch_tau`, so its steady state was proportional to
> 1/dt -- touch was four times more sensitive at 0.125 ms than at 0.5 ms. Now an
> exponential moving average, with the factor that used to hide in the integrator written
> into `touch_gain`.
>
> **3. The volatile odour pathway was deaf, and had been all along.** Its adaptation used
> `(1 - chem_decay * 0.5)` as a per-step rate, and `chem_decay` is very nearly 1, so the
> effective time constant was about 2 dt -- one millisecond, not the seven seconds
> intended. AWA and AWC adapted out any odour within two timesteps. AWC is the OFF cell
> that fires when an attractant is removed, one of the better characterised reversal
> triggers in this animal.
>
> **4. `touch_gain` was two hundred times too large.** A standard tap implied an **8745 mV**
> depolarisation of ALM, clamped by `v_clamp` to +45. The mechanosensory channel was not a
> sensor but a binary switch, and nothing graded downstream of it could show -- which is
> why the first attempt at habituation depleted the receptor to 52% and changed the
> response by 2%. Recalibrated to 75 pA/uN: the receptor stays off the clamp, and the
> current lands in the tens of pA that O'Hagan, Chalfie & Goodman (2005) measured.
>
> **And ablation was backwards.** Zeroing a cell's conductances leaves it still receiving
> whatever current the sensory layer injects, with only its leak to shunt it -- so ablating
> AVB, which carries a 22 pA tonic drive, took it to +34.8 mV and its activation from 0.84
> to **0.9994**. Silencing the forward command made it maximally active. `NervousSystem`
> now carries an explicit alive mask; it reads 0.0000, and restoring gives 0.833 back.
>
> ### Three refutations
>
> **`head_tau` does not suppress the fast mode. The coarse timestep was doing it.** At
> dt = 0.5 ms the power above 1.5 Hz is 1-2% at *every* `head_tau` from 0.22 to 1.20. At
> 0.125 ms with the shipped 0.22 it is **53%**. Refining further finds no `head_tau` at
> which the answer stops depending on the step: the frequency clusters near 0.15, 0.70 and
> 1.0-1.4 Hz and flips between clusters on changes too small to move any physical quantity.
> The head loop has several coexisting limit cycles and the integrator is selecting among
> them, so "the undulation frequency" is not currently a well-defined property of this
> model. That is a stronger statement than the frequency being wrong.
>
> **The body cannot be made the oscillator by turning the segmental gain up.** Raising
> `ca_ratio` does raise curvature -- 2.7 to about 6.3, against a measured 4.3, having been
> too low -- and destroys the wave doing it: TWI falls from +0.71 to zero and net speed to
> 0.02 mm/s. The units free-run and lock to each other instead of organising into a
> travelling wave, and weakening the head does not rescue it (the `ca_ratio` 0.40 rows are
> equally dead at head gains of 150, 60, 25 and 0), which was the obvious objection to the
> earlier version of this result. Proprioceptive coupling as built can carry phase to
> segments that have no rhythm of their own; it cannot impose a phase gradient on segments
> that do. Making it impose a phase *lag* -- an explicit propagation delay, or asymmetric
> coupling -- is a design change and is the next thing to try.
>
> **Presynaptic depression cannot habituate this connectome's tap response**, because the
> response is not chemical. Cutting ALM and AVM's entire chemical output leaves the AVA
> response unchanged at +0.18; cutting their gap junctions halves it. The machinery is
> kept, at zero, because it is the standard model and the refutation is specific to this
> pathway rather than to the idea.
>
> ### What was added
>
> * **Habituation** (`SensoryParams.touch_habituation_use`). A depleting resource on the
>   mechanoreceptor: taps consume it, rest refills it, and a shorter interval habituates
>   deeper. Three properties from one equation. The interval dependence is the one that
>   could have failed and it holds -- 0.25 resource at a 10 s interval against 0.45 at
>   30 s, same rate, same number of taps -- which is what separates habituation from
>   fatigue. Integrated exactly, so how much the animal learns does not depend on how
>   finely it is stepped, and there is a test for that.
> * **Reversible ablation**, on `Simulation`, with the alive mask above, plus a viewer UI:
>   an Ablate mode, a Restore button, and dead cells drawn hollow and crossed.
> * `tools/timestep_convergence.py`, `tools/head_mode.py`, `tools/body_oscillator.py`,
>   `tools/habituation.py`.
> * A **HiDPI fix in the viewer**: neuron hover and click have never worked on a Retina
>   display. The layout is built in backing-store pixels and the hit test compared them
>   against CSS pixels, so at devicePixelRatio 2 it was out by a factor of two and no cell
>   could be selected at all.
> * The assay runner uses one flat job queue instead of one `pooled()` call per assay, and
>   eight workers rather than ten. Both measured; see `tools/assays.py`.
>
> ### Do not repeat these
>
> * **Do not edit anything under `worm/` while a sweep is in flight.** `pooled()` launches
>   a fresh process per trial that imports the package from disk, so an edit part-way
>   through silently mixes two code versions in one result table.
> * **Do not score a response with a peak over a window.** A peak is a biased estimator of
>   a fluctuating signal -- it is positive with no stimulus at all -- and here that bias is
>   +0.070 against a real tap response of +0.020. The first habituation assay was measuring
>   almost entirely noise and reported the memory as absent when it was merely swamped. Use
>   a difference of means over matched windows.
> * **Do not measure locomotion with unsigned speed.** The first ablation test passed the
>   AVB-ablated animal at 0.24 mm/s, *faster* than intact, because it had handed over to
>   the backward generator and was crawling away tail-first. The sign is the phenotype.
> * **Do not trust a gait number without knowing the step size it was measured at**, until
>   item 1 above is resolved.

> ## Day six. The decision has no input, and that is now a number.
>
> **State: locomotion untouched, 33 tests pass. Everything below is diagnosis and four
> refuted fixes. Nothing shipped is changed -- every parameter added today is zero.**
>
> ### The finding
>
> The forward/backward decision sits **3.81 standard deviations** from its own boundary,
> and a physiological chemosensory signal moves it **0.008 of one standard deviation**.
>
> `tools/command_probe.py` drives named neurons with known currents and reports what the
> command difference does. Bare plate, three seeds:
>
> ```
>   probe          fwd act   bwd act   difference (sd)    gate    shift    crossings
>   baseline       0.792     0.582     +0.2100 (0.0315)   0.952   +0.0000   1
>   ASEL +1pA      0.793     0.583     +0.2097 (0.0315)   0.951   -0.0003   1
>   ASEL +10pA     0.794     0.585     +0.2087 (0.0314)   0.946   -0.0013   3
>   AVA +5pA       0.797     0.592     +0.2048 (0.0313)   0.944   -0.0051   3
>   AVA +20pA      0.809     0.619     +0.1903 (0.0314)   0.917   -0.0196  13
>   AVB -20pA      0.729     0.586     +0.1427 (0.0646)   0.744   -0.0672  153
> ```
>
> ASE at 10 pA is **seventeen times** what the pathway actually delivers -- the triage
> measures 0.58 pA rms on a real lawn gradient -- and it closes 1% of the distance to the
> boundary. At the physiological 1 pA it closes nothing measurable. Even 20 pA injected
> straight into the backward command pool gets 16% of the way.
>
> This is the day-four table's single cause, stated as a quantity. It is not a gain
> problem: no gain multiplies 0.008 into 3.81.
>
> ### Why: the two pools are a mutual amplifier
>
> They **correlate at +0.76**. Read the AVA +20 pA row again -- driving the backward pool
> raises it by 0.037 and drags the forward pool up by 0.017 at the same time. Nearly half
> the injected current crosses over, because every command interneuron here is cholinergic
> or glutamatergic and the model collapses both to a 0 mV reversal: the pools are wired to
> each other *excitatorily*, 70 reconstructed contacts one way, 33 the other, 10 gap
> junctions. The decision reads their difference, which is the one component that common
> drive cannot move.
>
> ### Four fixes tried. All four refuted, and the last two are the interesting ones.
>
> **1. Reciprocal inhibition between the pools does nothing.** `command_cross_inhibition`
> retargets the cross-pool synapses onto an inhibitory receptor -- licensed by the same
> argument this model already uses for AVL and DVB, whose GABA lands on the cation channel
> EXP-1, run in reverse: C. elegans glutamate opens the glutamate-gated chloride channels
> AVR-14, AVR-15 and GLC-1/2/3 as well as the AMPA-type GLR-1, so reversal potential is a
> property of the synapse rather than of the presynaptic cell.
>
> ```
>   cross  adapt |  corr   difference   margin   rev/min |  speed   net/path    TWI
>    0.00   0.00 | +0.744   +0.2128      3.83     1.67   |  0.1853   0.783    +0.767
>    0.25   0.00 | +0.748   +0.2174      3.99     1.67   |  0.1935   0.812    +0.767
>    0.50   0.00 | +0.746   +0.2221      4.10     1.00   |  0.1988   0.827    +0.770
>    1.00   0.00 | +0.737   +0.2316      4.30     1.00   |  0.2077   0.853    +0.774
> ```
>
> The correlation will not move and the margin gets *worse*. Both for the same reason: the
> forward pool makes 70 contacts onto the backward one against 33 coming back, so making
> the pair mutually inhibitory only lets the stronger side win harder -- and the pools were
> never correlated *by* those synapses in the first place. They are correlated by shared
> input, and retargeting a few percent of each pool's conductance cannot touch that.
>
> **2. Slow adaptation moves the margin and buys no behaviour.** `command_adapt_ratio`,
> 15 s time constant, so the winning side tires:
>
> ```
>   adapt |  corr   difference   margin   rev/min   dur s |  speed   net/path
>    0.00 | +0.744   +0.2128      3.83     1.67     0.06  |  0.1853   0.783
>    0.02 | +0.728   +0.2057      3.47     3.67     0.07  |  0.1855   0.790
>    0.05 | +0.694   +0.1957      2.95    12.00     0.06  |  0.1839   0.798
>    0.10 | +0.611   +0.1808      2.18    30.00     0.07  |  0.1752   0.783
>    0.30 | +0.473   +0.1220      0.42    82.33     0.22  |  0.0974   0.518
> ```
>
> The margin comes down monotonically at almost no cost to locomotion, and the reversals
> are not reversals. **Every episode lasts 0.06 to 0.08 s** -- one fifteenth of an
> undulation cycle -- at every setting, including the one producing thirty a minute. A body
> cannot reverse in 0.07 s. What is counted is the difference dipping below a threshold it
> still sits above and bouncing straight back. Turned up until the *rate* looks biological,
> the margin collapses into the noise and net speed halves.
>
> So fatigue is not the missing property. **Persistence is**: a reversal is a state the
> animal stays in for seconds. Adaptation lowers the mean of a noisy signal towards a
> threshold; it does nothing to make the far side of that threshold somewhere the animal
> can remain.
>
> **3. Bistability supplies both missing properties, and halves locomotion.**
> `command_ca_ratio` adds the regenerative limb -- the same Morris-Lecar construction the
> B-class motor neurons already carry, and where the recordings put it: AVA holds
> depolarised plateaus lasting seconds.
>
> ```
>    ca    adapt |  corr   difference   margin   rev/min   dur s |  speed  net/path   TWI
>    0.00   0.05 | +0.694   +0.1957      2.95    12.00    0.06  |  0.1839   0.798   +0.757
>    0.20   0.05 | +0.487   +0.2074      1.38    66.00    0.07  |  0.1111   0.537   +0.725
>    0.35   0.05 | -0.042   +0.2274      1.15   104.00    0.13  |  0.0853   0.427   +0.719
>    0.50   0.05 | -0.015   +0.3143      1.62    28.00    0.25  |  0.0851   0.385   +0.753
>    0.50   0.15 | +0.714   +0.2160      0.44    10.33    3.19  |  0.0404   0.233   -0.096
> ```
>
> **The correlation finally breaks** -- +0.69 to -0.04, the first thing all day to move it
> -- and episodes leave the flicker floor, reaching 3.19 s. Those are precisely the two
> properties that were missing. And every calcium row costs about half the locomotion.
>
> **4. Two explanations for that cost, both refuted.** This is where it stopped, and the
> refutations are worth having because both were plausible enough to act on.
>
> *It is not the reversals.* Holding `gate_bias` at 0.00 so that the animal reversed **not
> once** in the whole run still gave speed 0.091 and net/path 0.400, against 0.185 and
> 0.783 shipped. The cost is there with the behaviour switched off.
>
> *It is not the resting depolarisation.* At `ca_offset` 0 the calcium gate is half open at
> rest, a standing depolarising load on cells whose potential matters. Closing it at rest
> (`command_ca_offset` 8 and 16 mV) made locomotion slightly **worse**, 0.091 -> 0.063 ->
> 0.061.
>
> *And it is not AVB's gap junctions to the B cord*, which was the best structural guess:
> AVB and PVC gap-junction onto the B class with 58 contacts and AVB's resting potential is
> the bifurcation parameter that poises those units, whereas AVA/AVD/AVE put 102 contacts
> onto the A class, which carries no regenerative conductance at all (`a_class_scale` is
> 0) and is therefore poising nothing. Putting the calcium on AVA alone should then have
> been free. It was not -- if anything it was slightly worse than doing both pools:
>
> ```
>   where         ca   adapt  bias |  corr   difference  margin  rev/min  dur s | speed  net/path
>   AVA only     0.35   0.05   0.09 | +0.046   +0.1551     0.46    95.00   0.23 | 0.0749   0.388
>   AVA only     0.50   0.05   0.09 | +0.025   +0.2343     0.99    47.67   0.24 | 0.0678   0.313
>   both pools   0.35   0.05   0.09 | -0.042   +0.2274     1.15   104.00   0.13 | 0.0853   0.427
>   shipped      0.00   0.00   0.09 | +0.744   +0.2128     3.83     1.67   0.06 | 0.1853   0.783
> ```
>
> ### What this says the next move is
>
> The mechanism is right and the *place* is wrong. Something about carrying dynamics on the
> command interneurons costs the gait, and it is none of the three obvious routes. The
> leading remaining candidate, and the first thing to measure, is that depolarising AVA
> wakes the backward cord: `a_class_scale` is 0 precisely because "held at equal strength
> both cords amplify at once and fight over the same muscles", and a bistable AVA drives
> the A class through 102 gap contacts and its chemical synapses whether or not the
> direction gate ever flips. That is testable directly -- measure A-class calcium gate and
> muscle drive with and without the calcium, which needs no new parameter.
>
> There is also a structural reading worth taking seriously, because it is the same
> conflation day five only half removed. `tonic_forward` was split into a decision bias and
> a cord drive, but the *gate* still does both jobs: one scalar picks the direction **and**
> apportions how much drive each cord receives. Giving the decision dynamic range therefore
> necessarily modulates the gait. Separating "which cord" (a latched, hysteretic choice)
> from "how much" (a constant) is the change that would let the decision move freely, and
> it is a small change to `Senses.sense`.
>
> ### The gait is not converged at the timestep it ships at
>
> This started as a performance question -- everything costs 2000 steps per simulated
> second, so raising `dt` is the obvious lever -- and turned into something worth more than
> the speed. `tools/timestep_convergence.py`, five step sizes, three seeds, 60 s each,
> net displacement over the whole window rather than a trailing average:
>
> ```
>    dt ms   steps/s |   freq Hz (sd)    wavelen L      TWI     k_rms   speed mm/s
>    0.125     8000  |  1.622 (0.021)      0.61      +0.729     2.68    0.3245
>    0.250     4000  |  1.411 (0.034)      0.58      +0.771     2.64    0.2770
>    0.500     2000  |  1.233 (0.036)      0.54      +0.764     2.30    0.1918   <- shipped
>    1.000     1000  |  1.028 (0.042)      0.50      +0.708     1.80    0.0899
>    2.000      500  |  0.717 (0.083)      0.49      +0.524     1.42    0.0203
> ```
>
> Halving the step from 0.25 to 0.125 ms still moves the frequency by **15%** and the net
> speed by **17%**, against a seed spread of 0.03 Hz. The trend is monotonic across a
> sixteen-fold range and nowhere near flat at the finest step tried. Curvature amplitude is
> close to converged (2.64 -> 2.68, +1.5%); frequency, wavelength and speed are not.
>
> Two headline numbers in this project change meaning as a result.
>
> **The frequency discrepancy is worse than reported, not better.** The model is recorded as
> undulating at 1.2 Hz against the animal's 0.30-0.50 Hz. Refine the integrator and it goes
> *up*: 1.62 Hz at 0.125 ms and still climbing. Whatever the converged value is, it is
> further from the animal than the number we have been quoting, so every "the frequency is
> too high" note in this file understates the problem.
>
> **The speed agreement is partly an artefact of this timestep.** At 0.5 ms the animal
> crawls at roughly the measured 0.219 mm/s, which has been read as the model getting
> something right. At 0.125 ms it does 0.3245 mm/s, half again too fast. The model is not
> matching the animal's speed; it is matching it at one step size, on the way past.
>
> Those two are the same fact seen twice -- an undulation that is too fast drives a body
> that travels too fast -- and it makes the frequency the single problem to solve rather
> than one of several.
>
> **The likely cause is the body, not the neurons.** Integration is exponential Euler on the
> membrane equations, which is exact for their linear part. `Body.step` puts backward Euler
> on the constant elastic and damping matrices but evaluates the configuration-dependent
> drag metric explicitly and then takes `pos + qdot*dt`, so the mechanics are first-order.
> The gait is a limit cycle closed through that integrator, and a limit cycle's period is
> exactly what first-order phase error moves.
>
> So `dt` should come **down**, or the body should go to second order, and neither is a
> performance decision. Do not raise it: that would make an unresolved number cheaper to
> compute without making it truer. `tools/timestep_convergence.py` is the tool that settles
> it, and it takes four minutes.
>
> ### On the assay runner
>
> One flat job queue instead of one `pooled()` call per assay, and eight workers instead of
> ten. The old arrangement ran each assay to completion before starting the next, so a
> 12-job assay finished with a wave of two trials holding the machine for as long as a full
> wave -- about 30% of the wall clock across the suite. Workers past the eighth land on
> this machine's efficiency cores and, because a wave ends when its slowest trial does,
> drag the whole wave with them: going 8 -> 12 buys 10% aggregate throughput while making
> each individual trial 37% slower. Both measurements are recorded in `tools/assays.py`.
>
> Not done, and deliberately: **decimating the world field sampling.** It is 14.6% of every
> step and it is safe -- 99% of the power in what ASE actually reads sits below 1.23 Hz and
> 99.9% below 4.2 Hz, so a zero-order hold at 100 Hz costs 0.24% rms error in that signal.
> But it buys 14% in exchange for putting a second clock into a model that currently has
> exactly one, and it is worth much more after the timestep question is settled than
> before: at `dt` = 0.125 ms the same 100 Hz hold saves four times as much.
>
> ### Added
>
> * `tools/command_probe.py` -- what each input is worth, in units of the decision's own
>   fluctuation. This is the tool that turned "chemotaxis does not work" into a number.
> * `tools/command_sweep.py` -- scores the behavioural and locomotor halves side by side,
>   because either alone is easy to fake. The **duration** column is the one that matters;
>   it is what separates a reversal from a threshold flicker, and without it configurations
>   2 and 3 above both look like successes.
> * `tools/ethogram.py` -- reversal rate, run durations and reorientation off food and on,
>   against Zhao et al. Only smoke-tested so far, one animal for 20 s per condition, and
>   even that turned up something: **the food dependence runs backwards.** Off food the gate
>   never crosses at all; on a lawn it crosses 99 times a minute. The animal's ordering is
>   3.2-3.5 per minute off food and 0.7-1.25 on it, so the model is inverted as well as
>   mistimed. This is the serotonergic turning arm from day five doing exactly what it was
>   calibrated to do -- `serotonin_turning` shifts the gate towards reversal on food, and it
>   is the only reason the basal slowing response reproduces at all -- meeting a threshold
>   that cannot tell dwelling from a flicker. Worth a proper run before anything is
>   concluded from it, but it points at the same place everything else today does.
> * `NervousSystem.E_syn`, a per-synapse reversal potential (post, pre) instead of a
>   per-neuron one. Receptor identity belongs to the postsynaptic cell. Costs no arithmetic
>   -- `G_syn @ (s * E_pre)` becomes `(G_syn * E) @ s` with the product taken once at
>   construction -- and reproduces the previous model to 2e-15 relative, membrane potentials
>   and synaptic activations exactly.
> * Five zero-valued parameters in `NeuralParams`: `command_cross_inhibition`,
>   `command_adapt_ratio`, `command_adapt_tau`, `command_ca_ratio`, `command_ca_offset`,
>   `command_ca_classes`. All zero-safe, all with their measurements recorded next to them.
>
> ### Still outstanding from day five
>
> **The assay rerun did not complete.** Only `triage` finished before it had to be
> abandoned (see the hazard below), and its result is the one that mattered: **zero
> reversals across six animals in sixty seconds each**, gate pinned at 0.95 forward in every
> one. Chemotaxis, aerotaxis, thermotaxis and nociception are still un-rerun since the food
> fix. Aerotaxis remains the best bet.
>
> ### Do not repeat these
>
> * **Do not edit anything under `worm/` while a sweep is in flight.** `pooled()` launches
>   a fresh OS process per trial that imports the package from disk, so an edit part-way
>   through a run silently mixes two code versions in one result table. This cost a
>   45-minute assay run today. Finish the code, then start the sweep.
> * **Do not score a reversal by counting threshold crossings.** Every configuration in
>   section 2 above looks like progress on rate alone and is worthless on duration. Any
>   claim about reversals needs the episode length next to it.
> * **Do not read a sweep whose threshold was calibrated for a different operating point.**
>   `gate_bias` was placed against a difference of mean 0.21 and sd 0.032; calcium
>   quadruples that sd, so the same number means something else. Re-place it per
>   configuration or the rows are not comparable.

> ## Day five. Modulators, and two real bugs in the world.
>
> **State: locomotion 0.246 mm/s (animal 0.219), TWI +0.778, net/path 0.905, 33 tests pass.**
>
> ### What landed
>
> **The command decision is decoupled from the gait drive.** `tonic_forward` was doing two
> incompatible jobs -- choosing direction, and (since the Morris-Lecar work) deciding
> whether the animal could walk at all. Now `tonic_forward` (22 pA) only biases the
> decision, `cord_drive` (8 pA) feeds the gait to whichever cord the gate selects, and the
> gate reads the *difference* between command pools instead of cubing absolute activities.
> Worth +23% speed on its own, and the gate finally has dynamic range (sd 0.000 -> 0.038).
>
> **`worm/modulators.py`: the wireless connectome.** Four slow scalars -- dopamine,
> serotonin, octopamine, PDF -- produced by their real source neurons, decaying on their own
> time constants, acting by scaling gains rather than injecting current. Every coefficient
> is zero-safe; zero reproduces the previous model exactly. Basal slowing response
> calibrated to **0.50** against the animal's ~0.5.
>
> ### Two bugs that invalidated earlier results
>
> **Every bacterial lawn was inside-out.** Transposed `_smoothstep` arguments meant food was
> 0 at a patch's centre and 1 everywhere *outside* it, out to the dish wall -- a 9 mm lawn
> sampled 0.002 at its own centre while the dish held 26,000 units. Oxygen derives from that
> field, so **the aerotaxis null in the day-four notes is withdrawn**; it was scored against
> a backwards gradient. Now 6% on a lawn against 21% at the edge.
>
> **The animal ate a hole under itself in ~2 s.** `World.eat` subtracted the full requested
> amount from each of nine cells, removing 9x what was asked, and `ingestion_rate` was 45x
> too fast besides. "On food" was therefore a condition that decayed away during any
> measurement. Fixed to a proportional total withdrawal at 0.02 units/s, which matches
> `world.py`'s own stated intent of depletion mattering "over tens of minutes".
>
> ### The honest caveat on the slowing response
>
> We reproduce the behaviour by the wrong route. Dopamine scaling the cord drive turns out
> to be a *weak* lever -- pinned at its 0.25 floor the animal still only slows 23%, because
> speed here is set by the proprioceptive loop and the motor neurons' own dynamics, not by
> how hard the cord is driven. All of our slowing comes from the serotonergic turning arm.
> In the animal, cat-2 mutants that cannot make dopamine *fail to slow*, so dopamine is
> necessary. Ours does not need it. Worth fixing, and worth not forgetting.
>
> ### Next, in order
>
> 1. **Rerun every assay.** All of them predate the food fix; aerotaxis is known-invalid and
>    the rest are suspect. `PYTHONPATH=. .venv/bin/python tools/assays.py all`, ~45 min.
>    Oxygen is the best bet: URX/AQR/PQR make 44 direct contacts onto the backward command
>    pool, more than any other sensory pathway, and the gradient is now real.
> 2. **Does the modulator layer unblock chemotaxis?** The dwelling result is a small
>    existence proof -- food changed the gate's behaviour, which nothing sensory had managed
>    before. Modulators act slowly and scale gains, so the 70x ASE->AVA attenuation that
>    blocks the fast route may not apply to them.
> 3. **Habituation.** Cheap, and Rankin's decrement and spontaneous-recovery curves are
>    quantitative targets. First thing on the list that is memory rather than modulation.
> 4. Fix the dopamine route above.
>
> ### Do not repeat these
>
> * **Do not use a process pool for sweeps.** `multiprocessing.Pool` and
>   `ProcessPoolExecutor` both deadlocked -- four runs lost, every worker at 0% CPU, parent
>   blocked on a lock, on an idle machine with 70% memory free. `pooled()` now launches one
>   independent OS process per trial with results as JSON on stdout. It cannot deadlock and
>   it reports per-job failures. Do not "optimise" it back into a pool.
> * **Anything using `pooled()` must live in a real file.** Spawn cannot re-import
>   `__main__` from a heredoc. This trap was documented, then walked into anyway.
> * **Do not run sweeps and pytest together.** Not a correctness issue but the suite goes
>   from ~5 min to 23 min.
> * The reversal detector (centroid velocity vs body axis) is only meaningful when net/path
>   is above ~0.3. Below that it reports slosh as turns.
> * Timing: one trial of D simulated seconds costs ~1.7xD wall-seconds on one core (0.58x
>   real time, flat regardless of BLAS threads). `estimate()` prints the prediction.

> ## Day four. The senses are measured, and they do not work. One cause.
>
> `tools/assays.py` reproduces standard plate experiments and scores them the way the
> original papers do. Locomotion is untouched (33 tests pass, 0.19 mm/s, TWI +0.75).
>
> | assay | result | real animal |
> |---|---|---|
> | chemotaxis index | **−0.014**, 7/16 animals approached | +0.5 or better |
> | approach over 200 s | **−0.86 ± 5.35 mm** | — |
> | aerotaxis, O2 occupied | **20.2%** (start 20.2, ambient 21) | 5–12% |
> | reversals | **1 per 6 animal-minutes** | 1–2 per minute |
>
> **The cause is a single structural conflation, and it explains every row.**
> `tonic_forward` injects 90 pA into AVB, which does two incompatible jobs at once:
>
> 1. it sets *which direction the animal goes*, via the cubed winner-take-all in
>    `Senses.sense` (gate reads 0.91/0.25 → 98% forward, in every animal, all run); and
> 2. since day three it also sets *whether the animal can walk at all*, because AVB's
>    membrane potential is what holds the B-class motor neurons at their Hopf bifurcation.
>
> Lower it and the gait dies before the decision changes: at tonic 22 the gate has only
> moved from 98% to 90% forward, but net/path has collapsed from 0.76 to 0.05. We
> re-entered day two's failure through a different door.
>
> **What is NOT wrong, so nobody re-checks it:**
> - *The wiring.* ASE reaches AVA and AVB in two hops via AIY/AIB, which is the real circuit.
> - *The sensors.* Raising `chemo_gain` 46× does propagate: ASE moves 24.8 mV, AIY 5.1,
>   AIB 1.05, AVA 0.35, DB/VB 2.72. It is real, and it deflects the path by 0.157 mm out of
>   9.4 mm travelled — 1.7%. Gain alone cannot rescue this; sweeping it to 1200 pA/unit
>   (drive 60 pA, well past the 10–250 pA anyone has injected experimentally) changes the
>   chemotaxis outcome by less than the seed-to-seed spread.
> - *Signal-to-noise alone.* The drive is 0.48 pA against a 2.2 pA noise floor, which is
>   real but is not the binding constraint — see above.
>
> **The A-class mirror, tested and left off.** AVA makes 102 gap contacts onto 20 of 21
> A-class units (AVB: 55 onto 18), so the backward cord has the same architecture and
> should get the same regenerative treatment. It is implemented (`oscillator_classes` now
> includes DA/VA, gated by `a_class_scale`) and switched off at 0.0, because the command
> circuit does not separate the cords: during forward locomotion the B class sits at
> calcium gate 0.780 and the A class at 0.670, **both above the 0.5 bifurcation**, 2.2 mV
> apart. Both cords amplify at once and fight over the same muscles. Full sweep in
> `NeuralParams.a_class_scale`. This unblocks the moment (1) is fixed.
>
> **So the next job is to decouple those two roles**, and the pieces are already in place:
> the locomotor drive should come from the AVB→B gap junctions (real, in the connectome,
> and since day three genuinely doing that job), leaving the forward/backward decision as a
> separate contest between AVA and AVB that does not drag the gait's operating point with
> it. In the animal the A and B classes are antagonistic at the motor level, not gated by
> one scalar. Expect chemotaxis, aerotaxis, nociceptive escape and the A-class fix all to
> move together, because they are all downstream of the same missing dynamic range.
>
> Thermotaxis and nociception assays are written but not yet run.
>
> **Tooling notes for whoever picks this up.** One trial of D simulated seconds costs
> ~1.7 × D wall-seconds on one core (0.58× real time, flat regardless of BLAS threads --
> the body's matrices are 49×49). `estimate()` prints the prediction; `pooled()` streams
> per-trial progress, because a `pool.map` deadlocked silently at 0% CPU for thirteen
> minutes and looked exactly like a slow run. Anything using the pool must live in a real
> file: spawn cannot re-import `__main__` from a heredoc. And the reversal detector
> (centroid velocity vs body axis) is only meaningful when net/path is above ~0.3 — below
> that it reports slosh as turns, which is why an early sweep appeared to show 25 reversals
> in a worm that was going nowhere.

> ## Day three. The travelling wave is fixed. Read this part first.
>
> Two changes landed, and the control sweep separating them is `tools/osc_control.py`.
>
> **1. Sensory input is now scaled by each target's resting conductance.** A fixed current
> produces a voltage inversely proportional to the cell's input conductance, and across the
> B class that conductance spans 0.63 to 3.20 nS — so a uniform proprioceptive current was
> hitting the small posterior units five times harder than the large anterior ones. Worth
> +14% on its own.
>
> **2. The B-type motor neurons became Morris-Lecar regenerative units** (`ca_ratio`,
> `adapt_ratio` in `NeuralParams`), poised at a Hopf bifurcation by the descending AVB gap
> junctions that were already in the connectome. Worth a further +31%.
>
> | | TWI | net mm/s | net/path | amplitude head/mid/tail | tail coherence |
> |---|---|---|---|---|---|
> | day two | +0.60 | 0.105 | 0.70 | 2.5 / 1.3 / 1.0 | 0.03–0.05 |
> | conductance scaling only | +0.64 | 0.120 | 0.71 | 2.5 / 1.3 / 1.0 | 0.08 |
> | **today** | **+0.75** | **0.172** | **0.86** | **2.6 / 1.9 / 1.9** | **0.35** |
> | this body, prescribed wave | +0.996 | 0.174 | — | — | — |
> | real animal | — | 0.219 | — | roughly flat | — |
>
> Net speed is now at the prescribed-wave ceiling for this body, and 78% of the animal's.
> The exponential amplitude decay down the body — the thing the whole day-two analysis was
> about — is gone: 2.5/1.3/1.0 became 2.6/1.9/1.9. Coherence rose in *every* region
> (head 0.4→0.90, mid 0.4→0.84, tail 0.03→0.35).
>
> **The result that surprised me, and the reason to keep the tooling.** Net speed peaks at
> `ca_ratio` 0.20, where the Hopf margin is 0.94 — the units sit *at* the bifurcation, not
> past it. Pushed past (0.26, 0.32, 0.55) each segment free-runs, locks to itself, the tail
> reaches 4x the head's amplitude and **the wave runs backwards**. Xu et al.'s mechanism is
> right; "just past the bifurcation" is doing a lot of work in that sentence, and the
> useful regime is critically poised amplifier, not autonomous oscillator.
>
> **Still wrong, in priority order:**
> 1. **Frequency: 1.17–1.24 Hz against 0.4–0.5 Hz for a real animal.** Sweeping `adapt_tau`
>    over an eighteen-fold range moves it under 5%, so it is set by the body and the reflex
>    loop, not the neurons. Go after drag, `internal_damping`, and muscle activation
>    kinetics. This is now the biggest single discrepancy.
> 2. **Wavelength 0.52 L against 0.65 L.** Probably the same cause as (1).
> 3. **Curvature rms 2.3 against 4.3.** The worm undulates too shallowly.
> 4. **Backward locomotion is known-poor.** Clamping AVB off correctly hands over to the
>    A-class generator and the wave does reverse, but curvature rms goes to 7.5 and net
>    speed to 0.018 mm/s. The gate offsets are placed relative to a resting potential solved
>    with AVB intact and do not follow it down. Untested before today; do not cite it as
>    working.
> 5. Tail coherence is 0.35 — much better than 0.03, still the worst region.
>
> Everything below this line is from day two. The sections on *why* the wave decayed remain
> the correct analysis; the "what to try" lists are superseded by the above.

> **Day two. The big one is fixed, and here is the state.**
>
> Proprioception was the one sensory channel still responding to absolute value rather than
> to change. Making the stretch receptor adapt took net speed from 0.005 to **0.10 mm/s**
> and the net-to-path ratio from 0.07 to **0.66-0.72** — inside the real animal's range.
> The worm crawls. Details in the README; the rest of this file is what is still wrong.
>
> **Everything below now hangs off one number,** the travelling-wave index. A standing wave
> makes no net thrust at all, so this is the quantity that decides the speed:
>
> | | TWI | net mm/s |
> |---|---|---|
> | this body, prescribed travelling wave | **+0.996** | **0.174** |
> | the model today | +0.48 to +0.57 | 0.10 |
> | the model yesterday | +0.33 | 0.005 |
> | real animal | — | 0.219 |
>
> The relationship is close to linear, so closing the remaining gap gets to the animal's
> speed and takes the wavelength and frequency errors with it — they are the same standing
> wave seen from other angles.
>
> **Where the wave actually fails, measured by region** (`tools/twi_by_region.py`):
>
> ```
> head and neck   0.00-0.30    TWI -0.10    45-55% of all curvature power
> body behind it  0.30-1.00    TWI +0.24 to +0.50
> posterior half  0.45-1.00    TWI -0.02 to +0.18
> ```
>
> So the head is a strong standing oscillator carrying about half the total power, the
> mid-body travels weakly, and **the posterior half barely travels at all**. The wave is
> generated at the front and dies before it gets down the body. That is the single
> remaining problem, and it is the same one the per-segment reflex gain measures.
>
> **Four hypotheses tested and refuted today.** Do not redo these:
> 1. *Back off the head reflex.* Tested from 150 down to 0: TWI goes **negative** (the wave
>    reverses) and speed collapses. The head reflex is what makes the wave go head-to-tail.
> 2. *Push the head reflex harder.* Tested 150 up to 900: TWI saturates flat at +0.58.
>    Worth perhaps 15% more speed at a gain of 400, and nothing beyond that. The ceiling is
>    not set by head gain in either direction.
> 3. *Bending stiffness.* Swept over a 1600-fold range with muscle moment scaled to hold
>    curvature fixed. A shallow 25% effect peaking 4-8x **above** the measured value, and
>    the literature's low value (Sznitman) is much worse. Not the lever.
> 4. *AVB broadcasting a common rhythm through its gap junctions.* It swings 4 mV, and
>    clamping it to a constant potential changes nothing.
>
> **Fifth hypothesis, also refuted, and it discredits a tool.** The reflex-gain sweep was
> rerun with the adapting receptor and said `peak_moment = 3.2` beat the current 2.6 in all
> twelve pairings, with tail gains up to 19. In the closed loop it is clearly worse:
>
> ```
> moment   TWI     TWI posterior   amp tail   net mm/s   net/path
> 2.6     +0.48..+0.57   -0.02..+0.28    2.4-3.3     0.095-0.106   0.66-0.72   <- current
> 3.2     +0.33..+0.42   -0.08..-0.01    8.3-8.6     0.068-0.071   0.46-0.50
> 4.0     +0.14..+0.40   -0.14..+0.05   12.0-12.9    0.041-0.079   0.26-0.29
> ```
>
> Absolute tail amplitude more than triples while the posterior travelling index stays at
> zero. It is making a **bigger standing wave**, not a travelling one, and going slower for
> it. `reflex_gain.py`'s headline number is a ratio whose denominator dies towards the tail,
> so it cannot distinguish those two outcomes; the caveat is now written into the tool.
> **Decide with `tools/twi_by_region.py` and absolute amplitudes instead.**
>
> **Sixth hypothesis refuted, and it corrects the fifth.** After the adaptation fix the
> phase profile reads completely differently: the phase gradient along the cord is now
> **-379 degrees**, against the -300 a 0.65 L wavelength needs. It is clean, monotonic, and
> more than sufficient. The circuit generates a properly travelling pattern; earlier
> conclusions drawn from the pre-adaptation profile (-159 deg) are void.
>
> What decays sevenfold head to tail is the *coherent* component -- the amplitude at the
> wave frequency. Total curvature variance is roughly equal head and tail. So the posterior
> moves plenty; it just does not move in time with the wave. That is a different fault from
> "the wave is attenuated", and it took a second measurement to tell them apart.
>
> The muscle efficacy taper looked like the obvious cause, since this model copies Boyle's
> 1.0-to-0.41 head-to-tail ramp. Flattening it does raise posterior amplitude, dramatically
> -- the head/tail ratio goes from about 1.0 to 0.17, so the tail ends up six times the head
> -- and everything gets worse:
>
> ```
> eff_tail   TWI            TWI post        head/tail   net mm/s      k_max
> 0.41    +0.48..+0.57   -0.02..+0.28      1.0-1.4    0.095-0.106   12-14   <- current
> 0.70    +0.18..+0.28   -0.06..+0.00      0.27-0.29  0.032-0.039   29-30
> 1.00    -0.57..-0.21   -0.38..-0.26      0.20-0.21  0.009-0.017   38-40
> 1.40    -0.01..+0.12   -0.05..+0.08      0.16-0.17  0.012-0.028   54
> ```
>
> The taper is load-bearing: it is what stops the posterior thrashing incoherently. Boyle
> was right and 0.41 is the best of the range.
>
> **Six parameter directions have now been tested and every one confirms the current
> defaults sit at a local optimum**: head reflex weaker, head reflex stronger, bending
> stiffness, AVB gap-junction broadcast, muscle moment, muscle taper. The travelling index
> will not go above about +0.57 for any of them, and the failure mode is always the same --
> the posterior moves, but incoherently.
>
> **So the next thing to do** is not another parameter sweep. Five have now failed, and the
> pattern across all of them is that the posterior travelling index will not move off zero
> no matter what the parameters do. That points at structure rather than tuning -- most
> likely hypotheses H1 (the graded synapse cannot more than double its conductance, which
> caps how much a motor neuron can modulate its muscle) and H2 (proprioceptive input should
> be a conductance, not a current) in the list below. Those are the two that change the
> model rather than its numbers, and they are what is left.

## The one problem worth solving first

**The body wave is mostly passive.** The head oscillates, the body follows because it is
mechanically attached, and the proprioceptive reflex adds only a modest amount on top.
Everything else that is wrong follows from this:

| Symptom | Model | Real |
|---|---|---|
| Undulation frequency, agar | 1.2 Hz | 0.30 Hz |
| Wavelength | 1.4 L | 0.65 L |
| Crawling speed | 0.03–0.11 mm/s | 0.219 mm/s |
| Gait modulation direction | backwards | agar slow, water fast |

Three independent measurements say the same thing:

1. Wavelength is **insensitive to proprioceptive reach** — 1.11 → 1.20 L as the reach goes
   from 0.10 to 0.20 body lengths. If the reflex set the wavelength, this would be the
   single most sensitive knob in the model. It is nearly flat.
2. Driving the head externally and toggling the body reflex changes mid-body amplitude
   from 0.17 to 0.25 — a per-segment gain near **1.4**, where regenerating a wave needs
   something closer to a sustained 1.0 *per segment* over many segments.
3. If the wave were regenerated along the body, the medium would act on every segment and
   gait modulation would work. It acts mostly on the head, and gait modulation is inverted.

`tools/reflex_gain.py` measures (2) directly and sweeps it over gain, reach and muscle
strength. **Start there.**

### A first sweep already ran, and it changes the plan

Partial results (each row is the gain at five positions from head to tail; a row that
*rises* left to right is a reflex regenerating the wave rather than merely passing it on):

```
gain   reach  moment   s=0.25  s=0.40  s=0.55  s=0.70  s=0.85
45     0.10   1.6        1.11    1.50    0.84    0.19    0.34
45     0.10   3.2        1.25    1.28    1.42    2.33    2.58
45     0.20   1.6        1.11    1.23    2.79    1.31    2.93
45     0.20   3.2        1.30    2.03    2.99    2.00    3.58
45     0.30   1.6        0.99    1.04    3.14    1.69    3.55
45     0.30   3.2        1.43    2.04    4.45    3.76    5.92   <-- strongly regenerating
90     0.10   1.6        1.21    1.27    1.47    1.55    1.51
90     0.10   3.2        1.26    1.28    1.96    1.81    0.90
90     0.20   1.6        1.24    1.96    2.00    1.08    1.69
```

Three things fall out of this, and the first two were not what I expected:

1. **`proprio_gain` is not the main lever.** Going from 45 to 90 pA does not reliably help
   and sometimes hurts. I had been treating it as the knob; it is not. Every hour spent
   sweeping it was largely wasted, which is worth knowing before repeating it.
2. **`proprio_reach` and `peak_moment` are the levers**, and they compound. The best row so
   far is the *lowest* proprioceptive gain with the longest reach and the strongest muscle:
   gain rising monotonically to 5.9 by the tail. That is the signature the model needs.
3. The current defaults (gain 90, reach 0.20, moment 1.6) sit in the weak-reflex corner of
   this table. That is precisely why the wave is passive.

**So the concrete first experiment tomorrow is:** set `peak_moment ≈ 3.2` and
`proprio_reach ≈ 0.30`, *drop* `proprio_gain` to ~45, and then **reduce
`head_proprio_gain`** so the head stops dominating — the body should now be able to carry
the wave itself. Then check with `tools/diagnose_loop.py` across at least three seeds
whether the 0.31 Hz / 0.70 L attractor has become the robust one.

Note that `peak_moment = 3.0` was rejected earlier in the build for producing twice the
real curvature, but that was measured with the *old, unfiltered* head reflex at full gain.
With the head backed off, the balance is different and it deserves re-testing rather than
being ruled out. Watch `kappa_max` — it must stay near 10 /mm.

The sweep was still running when this was written; re-run
`PYTHONPATH=. python tools/reflex_gain.py --out scratch/reflex_gain.json` for the full
24-row table (about 50 minutes; the `gain=180` and `gain=360` rows are the missing ones,
and on this evidence they are the least interesting).

### I then tried that configuration in the closed loop. It is the right direction.

`peak_moment=3.2, proprio_reach=0.30, proprio_gain=45`, head reflex left at its current
150, three seeds:

```
seed   freq   wavelen  direction    k_rms  k_max   speed   dv_corr
0     1.111    1.00   head->tail     5.15  22.42   0.118    -0.80
3     1.222    0.62   head->tail     8.32  23.88   0.118    -0.76
7     0.111    1.09   tail->head     8.34  23.28   0.099    -0.80
```

Compare against the shipped defaults (1.2 Hz, 1.4 L, k_max ~10, speed 0.03–0.11,
dv_corr −0.31). What improved, and it is not subtle:

- **Dorsoventral antagonism goes from −0.31 to −0.80.** The two muscle sheets are now
  genuinely alternating instead of half-heartedly. This is the single biggest jump I saw
  from any parameter change in the whole build.
- **Wavelength drops** from 1.4 L towards the measured 0.65 L (seed 3 hits 0.62 exactly).
- **Speed rises** and becomes consistent across seeds at ~0.10–0.12 mm/s.

What broke, and both look tractable:

- **Peak curvature is 22–24 /mm against a measured 9.8.** The body is being over-bent by
  roughly 2.3×. The obvious response is to back `peak_moment` down from 3.2 towards
  ~2.0–2.4 and see how much of the dv_corr and wavelength gain survives. There may be a
  sweet spot; there may not, and if not, that itself is informative about whether moment
  and reflex gain are separable.
- **Seed 7 runs backwards and very slow.** Reproducibility regressed, which is expected —
  the head reflex is still at 150 and is now fighting a much stronger body reflex for
  control of the wave. **Backing the head off is the untested half of this experiment**
  and is the first thing to run. I had `head_proprio_gain` at 60 and 25 queued and did not
  get to them.

So the ordered plan is: (a) re-run this with `head_proprio_gain` at 60 and 25 across the
same three seeds; (b) scale `peak_moment` down until `k_max` lands near 10; (c) confirm
with `test_gait_is_reproducible_across_seeds`; (d) if frequency is still high, *then* look
at H1 and H2 below. Do not touch H1/H2 before (a)–(c) — they are much more invasive and
this cheaper change may make them unnecessary.

### Hypotheses for why the reflex gain is low, roughly in order of my confidence

- **H1 — the synaptic dynamic range is the ceiling.** With each neuron's release threshold
  placed at its own resting potential, `phi = 0.5` at rest, so `s_rest` is always ≥ 50% of
  `s_max` and **no graded synapse can more than double its conductance**. That is a
  structural consequence of the Kunert threshold trick, not a parameter. It caps how much
  a motor neuron can swing its muscle, which caps the moment, which caps the regenerated
  bend. Worth testing by biasing the thresholds a few mV *above* rest so the resting
  release is lower and the upward range larger — at the cost of the network being less
  responsive to hyperpolarisation. This is the deepest of the hypotheses and the one I
  would try first.
- **H2 — proprioceptive input should be a conductance, not a current.** Real stretch
  receptors are ion channels; opening one moves the cell towards a reversal potential and
  never past it. Injecting current instead is why motor neurons hit the voltage rail under
  strong drive, and why the drive has to be tuned so carefully to avoid a static bend.
  Switching to a rectified excitatory conductance (`g ∝ relu(stretch)`, reversal 0 mV) is
  more faithful, self-limiting, removes the clamp entirely, and makes the dorsal/ventral
  pair genuinely alternate rather than push-pull through one shared signed current.
  Moderate work: `Senses.sense` returns a conductance vector, `NervousSystem.step` accepts
  it. Sketch already in `worm/senses.py`'s structure.
- **H3 — the muscle is still leak-dominated.** After the per-cell balance, NMJ conductance
  is 1.45 nS against a 2.2 nS leak. Lowering muscle `g_leak` (keeping `tau_m` sensible by
  also lowering `C_m`) would give the motor neurons more authority per unit release. Cheap
  to test: it is two numbers in `MuscleParams`.
- **H4 — 48 segments coupled through a dense drag metric is too stiff.** The mechanical
  coupling between neighbouring segments may be washing out the local reflex. Test by
  running at `n_links = 96` and seeing whether the reflex gain per unit *length* holds up.
- **H5 — the B-type receptive fields are too wide.** A reach of 0.20 L is 10 joints; each
  neuron averages over a fifth of the body, which low-passes the very spatial structure it
  is meant to propagate. Wen et al.'s 200 µm is a *dendrite length*, not necessarily a
  flat averaging window. Try a weighted kernel peaked at the near end.

### The prize

The slow attractor is still in there. Before the head stretch receptor was given its own
kinetics, the head loop had two limit cycles and the slow one sat at **0.31 Hz with a
0.70 L wavelength** — almost exactly the real crawling gait. It was only reachable from
about a third of random seeds, which is why the filter is there. If the body reflex gets
strong enough to dominate, that attractor should become the robust one and four of the
table's five rows fix themselves at once.

---

## Second tier

- **Gait modulation direction.** Falls out of the above if the wave becomes reflex-driven.
  Do not tune it directly — it is a symptom.
- **Reversals and omega turns.** The machinery exists (A-type proprioception with a
  posterior field, AVA/AVB gating, touch → ALM/AVM → AVA) and `test_anterior_touch_drives_a_reversal`
  passes, but spontaneous reversal *statistics* have never been measured against the
  literature. Targets: 3.2–3.5 reversals/min off food and 0.7–1.25 on food (Zhao et al.
  2003); 35% of reversals terminate in an omega turn; omega reorientation ~160–170°.
  Needs a behavioural-statistics harness — count reversals over a 10-minute run and
  histogram the turn angles. This is a good self-contained next task.
- **Chemotaxis index.** The sensory circuitry is wired and adapting, and the animal does
  eat, but nothing yet measures whether it actually climbs a gradient better than chance.
  Standard assay: fraction of time within some radius of the peak, or the classic
  chemotaxis index over a fixed run. Should be easy and would be a strong validation of
  the whole sensory path. **Probably the highest value-per-hour item in this file.**
- **Speed on vs off food.** Real worms slow ~7× on a lawn (219 → 31 µm/s, Ramot et al.
  2008) via the dopaminergic basal slowing response. CEP/ADE/PDE already sense the lawn;
  check whether the connectome alone produces the slowing.

## Third tier / nice to have

- Pharyngeal pumping. The 20 pharyngeal neurons are simulated and drive nothing.
- Three dimensions, so left/right muscle quadrants separate and omega turns are real.
- A recorded-playback mode in the viewer — the transport bar has no scrubber because there
  is no history buffer on the server. A ring buffer of a few thousand frames would let the
  media-player metaphor actually be one.
- Neuron ablation is implemented in `Runner._ablate` and reachable over the WebSocket, but
  there is no UI for it. Clicking a neuron and killing it would be a good demo, and would
  reproduce classic ablation experiments (kill AVB → no forward locomotion).
- Multi-worm. The engine is one `Simulation` object; nothing prevents several.

---

## Things that will bite whoever picks this up

- **Do not trust a single seed.** The gait was bistable across seeds until very late, and
  two thirds of seeds went the wrong way. `test_gait_is_reproducible_across_seeds` guards
  it now. Any change to the head loop should be checked against at least three seeds.
- **Do not add intrinsic oscillators to the motor neurons.** It was tried. Dorsal and
  ventral members have identical dynamics and are gap-coupled, so they phase-lock to each
  other, and the animal contracts both sides at once with a measured input correlation of
  0.97. The rhythm has to come from something dorsoventrally antisymmetric. See the long
  comment in `NeuralParams`.
- **Reference receptive fields to the muscles a neuron drives, not to its soma.** DB and VB
  somas are interleaved along the cord in a way that does not line up dorsoventrally.
  `_output_position` in `worm/senses.py` handles this; do not "simplify" it back.
- **The muscle balance step is load-bearing.** Without it the heavier ventral innervation
  in the connectome holds the worm in a permanent C. Without the *per-cell* version, head
  muscles rest on the flat end of their tension curve and go deaf.
- **Watch the summary statistics.** A lot of time went into inferring behaviour from
  frequency/wavelength numbers that were hiding a statically bent worm. `tools/kymo.py`
  prints an ASCII kymograph in a few seconds and would have caught it immediately. Look at
  the picture first.
- **The server's simulation thread must yield.** It holds the GIL through a batch of steps;
  without the small unconditional sleep, new WebSocket connections time out during the
  opening handshake. Already fixed, but it is the kind of thing that gets "optimised" back.

---

## A ready-to-run first command for tomorrow

This is (a) from the plan above — the untested half of the promising experiment. Paste it
and go; it takes about six minutes.

```bash
PYTHONPATH=. .venv/bin/python -u - <<'EOF'
from dataclasses import replace
from worm.engine import Simulation
from worm.params import Params
from tools.diagnose_loop import analyse, bare_world
print("%-6s %5s %8s %9s %11s %7s %8s %8s %8s" % (
    "head","seed","freq","wavelen","direction","k_rms","k_max","speed","dvcorr"))
for hg in (60.0, 25.0):
    for seed in (0, 3, 7):
        p = Params()
        p = replace(p,
            muscle=replace(p.muscle, peak_moment=3.2),
            sensory=replace(p.sensory, proprio_gain=45.0, proprio_reach=0.30,
                            head_proprio_gain=hg))
        r = analyse(Simulation(p, seed=seed, world=bare_world(p)), seconds=18.0)
        print("%-6.0f %5d %8.3f %9.2f %11s %7.2f %8.2f %8.4f %8.2f" % (
            hg, seed, r["freq"], r["wavelength"], r["direction"],
            r["kappa_rms"], r["kappa_max"], r["speed"], r["dv_corr"]), flush=True)
EOF
```

Read it as: does backing the head off make all three seeds go head-to-tail again, and does
the wavelength stay near 0.65 L? If yes, move to scaling `peak_moment` down for `k_max`.
If the seeds still disagree, the head and body reflexes are competing for the wave and the
next question is whether the head reflex should be weakened much further or removed
entirely once the body can sustain itself.

## Useful commands

```bash
PYTHONPATH=. .venv/bin/python tools/kymo.py                 # look at the body, first
PYTHONPATH=. .venv/bin/python tools/diagnose_loop.py        # gait metrics
PYTHONPATH=. .venv/bin/python tools/command_probe.py        # can anything reach the decision?
PYTHONPATH=. .venv/bin/python tools/command_sweep.py        # ...and does the gait survive it
PYTHONPATH=. .venv/bin/python tools/ethogram.py             # reversal statistics, on food and off
PYTHONPATH=. .venv/bin/python tools/assays.py triage        # two minutes; run before the full assay
PYTHONPATH=. .venv/bin/python tools/reflex_gain.py          # the key measurement
PYTHONPATH=. .venv/bin/python tools/calibrate_body.py       # mechanics only, no biology
PYTHONPATH=. .venv/bin/python tools/head_mode.py            # which limit cycle, and why
PYTHONPATH=. .venv/bin/python tools/habituation.py          # the only memory in the model
PYTHONPATH=. .venv/bin/python tools/timestep_convergence.py # is the gait converged? (~4 min)
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q           # 33 tests, ~5 min
.venv/bin/python run.py --headless 60
```

Every tool takes `key=value` overrides for the parameters it cares about, e.g.
`tools/kymo.py pg=180 moment=3.0 medium=buffer`.

A full-suite run takes about two and a half minutes and each closed-loop probe is 30–50
seconds of wall time, so batch parameter sweeps and run them in the background rather than
one at a time.
