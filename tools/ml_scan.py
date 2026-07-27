"""Search the Morris-Lecar parameter space for a usable conditional oscillator.

Requirements, in order of importance:
  1. SILENT with no AVB drive (this is what makes it *conditional*: the oscillation
     must be gated by descending input, or the worm can never stop or reverse).
  2. Oscillating with AVB drive present.
  3. Frequency in the undulation band. Proprioception can entrain a nearby
     oscillator, but it cannot drag a 5 Hz unit down to 0.5 Hz.
  4. Voltage swing that straddles the synaptic release threshold with room to spare.
"""
import itertools
import numpy as np

C = 1.5e-3       # nF, matches NeuralParams.C_m
G_L = 0.25       # nS
E_L = -62.0
E_CA = 60.0
E_K = -70.0
V_AVB = -20.0

TARGET_F = (0.40, 0.60)      # Hz -- the real crawling band (Gray & Lissmann; Berri 2009)
TARGET_SWING = (18.0, 45.0)  # mV


def simulate(g_ca, g_k, g_avb, cvh, csl, kvh, ksl, tau, T=12.0, dt=2e-4):
    """Integrate every candidate at once. Each argument is an (M,) array."""
    V = np.full(g_ca.shape, E_L)
    n = np.zeros(g_ca.shape)
    steps = int(T / dt)
    keep = int(6.0 / dt)
    tr = np.empty((steps - keep,) + g_ca.shape)
    for i in range(steps):
        m = 0.5 * (1 + np.tanh((V - cvh) / csl))
        n_inf = 0.5 * (1 + np.tanh((V - kvh) / ksl))
        I = (G_L * (E_L - V) + g_ca * m * (E_CA - V)
             + g_k * n * (E_K - V) + g_avb * (V_AVB - V))
        V = np.clip(V + dt * I / C, -300.0, 300.0)
        n += dt * (n_inf - n) / tau
        if i >= keep:
            tr[i - keep] = V
    return tr


def describe(tr, dt=2e-4):
    """Swing and zero-crossing frequency, per candidate."""
    swing = tr.max(axis=0) - tr.min(axis=0)
    x = tr - tr.mean(axis=0)
    up = (x[:-1] < 0) & (x[1:] >= 0)
    idx = np.arange(x.shape[0] - 1)[:, None]
    counts = up.sum(axis=0)
    first = np.where(counts > 0, np.argmax(up, axis=0), 0)
    last = np.where(counts > 0, (x.shape[0] - 2) - np.argmax(up[::-1], axis=0), 0)
    span = (last - first) * dt
    f = np.where((counts >= 3) & (span > 0), (counts - 1) / np.maximum(span, 1e-9), 0.0)
    return swing, np.where(swing >= 2.0, f, 0.0)


def main():
    grid = dict(
        g_ca=[0.75, 1.00, 1.25, 1.50],
        g_k=[1.50, 2.00, 2.50, 3.00],
        g_avb=[0.60, 0.90, 1.20, 1.50],
        cvh=[-34.0, -32.0, -30.0, -28.0],
        csl=[6.0, 8.0, 10.0],
        kvh=[-36.0, -34.0, -32.0, -30.0],
        ksl=[8.0, 10.0, 12.0],
        tau=[0.60, 0.75, 0.90, 1.10],
    )
    keys = list(grid)
    combos = np.array(list(itertools.product(*(grid[k] for k in keys))), dtype=float)
    total = len(combos)
    kw = {k: combos[:, i] for i, k in enumerate(keys)}

    # Requirement 1: silent with the descending drive removed.
    quiet_swing, _ = describe(simulate(**{**kw, 'g_avb': np.zeros(total)}))
    swing, f = describe(simulate(**kw))

    ok = ((quiet_swing <= 3.0)
          & (f >= TARGET_F[0]) & (f <= TARGET_F[1])
          & (swing >= TARGET_SWING[0]) & (swing <= TARGET_SWING[1]))
    hits = [(f[i], swing[i], {k: kw[k][i] for k in keys}) for i in np.nonzero(ok)[0]]

    print("scanned %d combinations, %d satisfy all four requirements\n" % (total, len(hits)))
    # Prefer ~0.7 Hz (the sim's current undulation rate) and a generous swing.
    hits.sort(key=lambda h: (abs(h[0] - 0.45) / 0.45) - 0.02 * h[1])
    print("  f Hz  swing   g_ca  g_k  g_avb   ca_vh  ca_sl   k_vh  k_sl   tau")
    for f, swing, kw in hits[:14]:
        print("  %.2f  %5.1f   %.2f  %.2f  %.2f   %6.1f %5.1f  %6.1f %5.1f  %.2f"
              % (f, swing, kw['g_ca'], kw['g_k'], kw['g_avb'],
                 kw['cvh'], kw['csl'], kw['kvh'], kw['ksl'], kw['tau']))


if __name__ == "__main__":
    main()
