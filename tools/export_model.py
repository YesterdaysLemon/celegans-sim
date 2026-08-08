"""Freeze the model into one binary file the WebAssembly runtime can load.

The browser port does not rebuild the animal. Everything expensive and fiddly that
happens once at construction -- the resting-potential solve, the per-cell muscle balance,
the proprioceptive receptive fields, the drag masks, the receptor overrides -- stays here
in Python, and its *results* are written out as plain arrays. The WASM side implements
only the step functions.

That split is worth stating plainly, because it is what makes the port tractable and what
makes it trustworthy:

  * it removes roughly two thirds of the code that would otherwise have to be ported, and
    all of the parts most likely to drift -- `_balance`, `_receptive_fields`,
    `_resting_potentials`, `radius_profile`, the connectome loader;
  * whatever the two implementations disagree about, it cannot be the *setup*, because
    both are reading the same numbers out of this file. Any mismatch is in the stepping,
    which is where a conformance test can actually localise it.

The format is deliberately dull: a JSON header naming every array with its dtype, shape
and byte offset, then the raw little-endian payload. No schema, no versioning ceremony --
if the model changes, re-export. `tools/conform.py` reads the same file to check the two
implementations agree.

Run:  PYTHONPATH=. .venv/bin/python tools/export_model.py web/worm.model
"""

from __future__ import annotations

import json
import struct
import sys

import numpy as np

from worm.body import Body
from worm.engine import Simulation
from worm.params import MEDIA, Params

OUT = "web/worm.model"

# ------------------------------------------------------------------------------ genome --
#
# The scalars an individual animal is allowed to differ from its parents in.
#
# Every other number the runtime uses is shared by every worm in the dish, which is what
# makes a second animal cheap -- the 302x302 matrices are anatomy. These are the exception:
# each `Worm` carries its own copy, seeded from the value below, so a population can hold
# genuinely different animals rather than N clones of one.
#
# Three rules decide what may be on this list, and they are not stylistic.
#
#   * It has to be a scalar the *runtime* reads in a step function. Anything that fed the
#     Python construction instead -- `beta`, `C_m`, `E_K`, `s_eq` -- has had its results
#     baked into the payload by the resting-potential solve and the muscle balance, so
#     changing it here would move the operating point away from the solve rather than
#     re-doing it. Those want a re-export, not a gene.
#   * It has to survive the trip intact. Several parameters are folded into a derived rate
#     on the way out (`chemo_tau_adapt` leaves as `CHEM_DECAY = exp(-dt/tau)`), and the
#     runtime never sees the underlying constant. Those are recoverable -- the exporter
#     could emit tau alongside -- but until it does they cannot be genes.
#   * It must not be a unit conversion sitting in front of the fitness measure.
#     `volume_per_pump` and `lumen_capacity` multiply `food_eaten` about eightfold between
#     them while the animal forages slightly worse, so a population selected on intake
#     would spend its whole search there. They are deliberately absent.
#
# The list is here, in Python, because this is where the parameters live; both the runtime
# and the browser read the slot numbering out of what this file emits, so the two cannot
# drift about what gene 7 means.
GENES = (
    # locomotion -- how hard the reflexes drive the body
    "sen_proprio_gain",
    "sen_head_proprio_gain",
    "sen_cord_drive",
    # the forward/backward decision -- where the Schmitt trigger sits and how sticky it is
    "sen_gate_bias",
    "sen_gate_hysteresis",
    "sen_tonic_forward",
    # steering -- the omega turn's depth, and which way it bends
    "sen_omega_current",
    "sen_omega_ventral_fraction",
    # the wireless layer -- how strongly food shuts down reversals, via the serotonin-gated
    # chloride channel on the backward command pool. Shipped at zero and documented as the
    # best pirouette ratio this model has produced; it is a gene so a population can find
    # out what it is worth.
    "mod_serotonin_mod1",
    # the senses, one gain each
    "sen_chemo_gain",
    "sen_thermo_gain",
    "sen_oxygen_gain",
    "sen_repellent_d_gain",
    "sen_food_gain",
    "sen_touch_gain",
)

# ------------------------------------------------------------------ parameter groups --
#
# Every scalar this file lifts off a params dataclass is named in one of these tuples, and
# every one of them leaves through `_export_scalars`, which raises on a name that does not
# resolve. That is the whole of issue #31: two of these lists used to sit behind
# `if hasattr(sp, k)`, so a name that matched nothing produced no entry, no warning and no
# failure. `sen_nose_touch_gain` was lost that way and nobody noticed until the list was
# read against the dataclass by hand.
#
# The failure mode is quiet in proportion to how much it matters. `GENES` above is a list
# of names in this same file: a gene that is typo'd, renamed, or moved to a different
# dataclass would drop out of the export, the runtime would keep its compiled-in literal,
# and every mutation on that gene would do exactly nothing -- a flat dimension with no
# error anywhere, indistinguishable from a gene under no selection. `GENES` has been
# validated rather than filtered since it was written (see the KeyError in `export`); these
# lists now are too, which is the same claim applied one layer down.
#
# They are module level rather than inline in `export()` so that a test can resolve every
# name against a real `Params()` without building a simulation, and so `SCALAR_GROUPS`
# below can say which dataclass each list is read off.
# `ca_offset` is here for the resting-potential solve rather than for the step. The runtime
# never needs it while running -- `ca_vhalf` is exported ready-made -- but `m0`, the calcium
# gate's opening at rest, is `0.5 * (1 + tanh(-ca_offset / ca_slope))`, and that is one of
# the two constants the solve needs that the payload did not carry. The other, `s_half`, is
# already derivable: `0.5 * a_rise / (0.5 * a_rise + a_decay)`, both of which are here.
# See #96 -- the graph itself was already exported as CSR, so this pair was the whole gap.
NEURAL_SCALARS = ("beta", "ca_slope", "ca_offset", "k_slope", "E_K", "E_Ca", "E_inh",
                  "a_rise", "a_decay", "noise_tau", "noise_sigma", "depression_tau", "C_m")
MUSCLE_SCALARS = ("g_leak", "E_leak", "beta", "v_half", "rest_tension")
# `nose_touch_gain` was the last name on the sensory list below and has been removed rather
# than added, because there is nothing for it to carry yet. Both implementations drive nose
# touch with the *same* expression -- `worm/senses.py:284` uses `p.touch_gain * 0.5`
# and `wasm/assembly/index.ts:1035` uses `gene(GENE_SEN_TOUCH_GAIN) * 0.5` -- so the 0.5 is
# a shared literal, not a runtime constant standing in for a parameter Python has. Giving
# the nose its own gain is a new degree of freedom: it needs a field on `SensoryParams`, a
# use in `worm/senses.py`, a matching edit in the runtime, and it changes the .model
# payload, so it belongs in its own change with its own conformance run. Exporting a
# parameter nothing reads would only move the silence.
SENSORY_SCALARS = ("chemo_gain", "thermo_gain", "cultivation_temp", "oxygen_gain",
                   "oxygen_preferred", "oxygen_d_gain", "repellent_d_gain", "food_gain",
                   "proprio_gain", "head_proprio_gain", "tonic_forward", "tonic_backward",
                   "cord_drive", "gate_slope", "gate_bias", "gate_hysteresis",
                   "turn_bias_limit", "touch_gain", "omega_current",
                   "omega_ventral_fraction", "omega_reflex_suppression")
MODULATOR_SCALARS = ("dopamine_slowing", "serotonin_slowing", "dopamine_wavelength",
                     "serotonin_turning", "octopamine_speeding", "pdf_roaming",
                     "serotonin_mod1")
PHARYNX_SCALARS = ("myogenic_rate", "mc_rate_gain", "i2_rate_gain", "serotonin_to_mc",
                   "octopamine_to_mc", "max_rate", "pump_duration", "m3_duration_gain",
                   "volume_per_pump", "m4_transport", "m4_gain", "lumen_capacity")
EGGLAYING_SCALARS = ("myogenic", "hsn_gain", "serotonin_gain", "vc_gain", "vm_tau",
                     "vm_threshold", "off_food_floor", "eggs_per_food", "uterus_capacity",
                     "eggs_initial", "resource_tau", "resource_cost", "resource_off",
                     "resource_on", "refractory")
WORLD_SCALARS = ("radius", "diffusion_attractant", "diffusion_repellent",
                 "decay_attractant", "ingestion_rate", "field_dt", "temp_cold",
                 "temp_warm", "o2_ambient", "o2_depth", "o2_length_scale")

# (attribute on `Params`, exported prefix, names). The exporter does not loop over this --
# each group is emitted at the point in `export()` where its section belongs, because the
# order of `b.f` calls is the order of the JSON header and the order of the header is part
# of the file. This exists so a check can ask "does every name in every group resolve, and
# did every one of them reach the header under this prefix" without re-deriving the lists.
SCALAR_GROUPS = (
    ("neural", "neural_", NEURAL_SCALARS),
    ("muscle", "mus_", MUSCLE_SCALARS),
    ("sensory", "sen_", SENSORY_SCALARS),
    ("modulator", "mod_", MODULATOR_SCALARS),
    ("pharynx", "ph_", PHARYNX_SCALARS),
    ("egglaying", "egl_", EGGLAYING_SCALARS),
    ("world", "world_", WORLD_SCALARS),
)

# Exported names (prefix included) that are allowed to be absent from their dataclass.
#
# Empty, and the emptiness is the point: nothing in this model is optional today, so any
# name that fails to resolve is a mistake and gets an exception. The set exists so that the
# *next* genuinely optional parameter -- a field on a branch, a medium-specific constant --
# has somewhere to go that is not a `hasattr` guard. A name listed here still costs a line
# in the build log every time it is skipped, so an omission shows up somewhere rather than
# nowhere, which is the only difference that matters.
OPTIONAL_SCALARS = frozenset()

# Model paths that exist in Python and NOT in the runtime, with the value the runtime is
# equivalent to. See docs/runtime-parity.md; the assertion lives in tests/test_runtime_parity.py.
#
# Python is deliberately a research superset. A counterfactual that only `worm/` can run is
# not a defect, and this list is not a bug list -- it is the set of paths for which the
# sentence "the browser runs the same animal" is true only because the default is still on
# this side of the branch.
#
# The failure it exists to catch has no other detector. Flip one of these defaults and the
# Python animal changes; the runtime keeps implementing the old path because it never
# implemented the new one; conformance still passes, because both sides are built from the
# same `Params()` and the runtime simply has no branch to disagree about. The two animals
# diverge and every check stays green. That is the one shape of drift this repository's
# conformance lane structurally cannot see.
#
# This list is data. Nothing in the export reads it -- an exporter that refused to run
# would block the very experiments Python exists to host, and the export of an experimental
# tree is a legitimate thing to want. The check is on the *shipped* default instead.
#
# Removing an entry is the last step of porting a path, not a way to quiet a red test:
# implement it in wasm/assembly/index.ts, export the constant that selects it, extend
# tools/conform.py and wasm/conform.mjs to cover both sides, rebuild the pair, then delete
# the line here in the same commit.
RUNTIME_UNSUPPORTED = {
    # The head-reflex cascade. Read in Senses.__init__, but what it builds is a step-time
    # branch (`_head_chain`) rather than an array the payload could carry, so re-exporting
    # cannot help. `head_stages = 1` is the single-lag reflex the runtime implements.
    "sensory.head_stages": 1,
    "sensory.head_stage_tau": 0.0,
    # Muscle force-velocity. Measured under tools/force_velocity.py and not adopted: it
    # narrows the gait-modulation span instead of widening it, and it costs the crawl.
    # `fv_vmax = 0.0` disables the whole term, including the rate low-pass in engine.py,
    # which is why the other three fv_* constants need no entry of their own.
    "muscle.fv_vmax": 0.0,
    # Omega wave suppression -- stands the body wave down during a turn. Distinct from
    # `omega_reflex_suppression`, which acts only on the head gain and IS in the runtime.
    "sensory.omega_wave_suppression": 0.0,
}


def _export_scalars(b, obj, names, prefix, optional=OPTIONAL_SCALARS):
    """Write `prefix + name` for every name in `names`, read off `obj`.

    A name that `obj` does not define is an error, not an omission. Every missing name is
    reported at once rather than one exception per run, because these lists are edited in
    batches (a rename across a dataclass touches several) and finding them one rebuild at a
    time is how the last one survived.
    """
    # An empty group would report no missing names and export nothing, which is a pass
    # that means nothing -- exactly the shape of failure this function exists to remove.
    # No caller passes one; if some future refactor makes a group empty, say so loudly
    # instead of validating thin air.
    if not names:
        raise ValueError("no parameter names to export for prefix %r: an empty group "
                         "exports nothing and would validate clean" % prefix)
    missing = [k for k in names if not hasattr(obj, k)]
    hard = [k for k in missing if prefix + k not in optional]
    if hard:
        raise KeyError(
            "%s has no %s (would be exported as %s). Either the name is wrong or the "
            "parameter is gone; if it is genuinely optional, name it in OPTIONAL_SCALARS "
            "so the omission is at least printed."
            % (type(obj).__name__, ", ".join(hard),
               ", ".join(prefix + k for k in hard)))
    for k in names:
        if k in missing:
            print("export_model: optional %s absent from %s -- not exported"
                  % (prefix + k, type(obj).__name__))
            continue
        b.f(prefix + k, getattr(obj, k))
    return b


class Blob:
    """Collects named arrays and scalars, then writes header + payload."""

    def __init__(self):
        self.meta = {"arrays": {}, "scalars": {}, "ints": {}, "strings": {},
                     "genes": []}
        self.chunks = []
        self.offset = 0

    def arr(self, name, a, dtype="f8"):
        a = np.ascontiguousarray(np.asarray(a, dtype=np.dtype(dtype)))
        # Pad every array to an 8-byte boundary. WebAssembly loads tolerate misalignment,
        # but a JavaScript Float64Array view does not -- and the viewer reads several of
        # these straight out of linear memory. One u1 array (302 bytes) was enough to
        # throw everything after it off and take the whole page down at load.
        pad = (-self.offset) % 8
        if pad:
            self.chunks.append(b"\x00" * pad)
            self.offset += pad
        self.meta["arrays"][name] = {"dtype": dtype, "shape": list(a.shape),
                                     "offset": self.offset, "bytes": a.nbytes}
        self.chunks.append(a.tobytes())
        self.offset += a.nbytes
        return self

    def csr(self, name, M, extra=None):
        """Write a matrix in compressed sparse row form, and optionally a second matrix
        that shares its sparsity pattern.

        Every connectome matrix here is between 0.3% and 2.5% non-zero -- 2279 chemical
        synapses in a 302x302 grid, 552 gap junctions, 45 non-zeros in the head reflex map.
        Multiplying them densely does 556,000 mul-adds a step to accumulate about 4,500
        that are not zero, which is most of the runtime spent on arithmetic that cannot
        change the answer.

        G_syn and GE_syn are the same matrix scaled per element, so they share one index
        array between two value arrays rather than storing the pattern twice.
        """
        M = np.asarray(M)
        rows, cols = M.shape
        ptr = np.zeros(rows + 1, dtype=np.int32)
        idx, val, val2 = [], [], []
        for r in range(rows):
            nz = np.flatnonzero(M[r])
            idx.extend(nz.tolist())
            val.extend(M[r, nz].tolist())
            if extra is not None:
                val2.extend(np.asarray(extra)[r, nz].tolist())
            ptr[r + 1] = len(idx)
        self.arr(name + "_ptr", ptr, "i4")
        self.arr(name + "_idx", np.asarray(idx, dtype=np.int32), "i4")
        self.arr(name + "_val", np.asarray(val, dtype=np.float64))
        if extra is not None:
            self.arr(name + "_val2", np.asarray(val2, dtype=np.float64))
        return self

    def f(self, name, v):
        self.meta["scalars"][name] = float(v)
        return self

    def i(self, name, v):
        self.meta["ints"][name] = int(v)
        return self

    def s(self, name, v):
        self.meta["strings"][name] = str(v)
        return self

    def write(self, path):
        head = json.dumps(self.meta, separators=(",", ":")).encode()
        with open(path, "wb") as fh:
            fh.write(b"WORM\x01\x00\x00\x00")
            fh.write(struct.pack("<I", len(head)))
            fh.write(head)
            fh.write(b"".join(self.chunks))
        return 8 + 4 + len(head) + self.offset


def export(path=OUT, params=None):
    p = params or Params()
    sim = Simulation(p, seed=0)
    conn = sim.conn
    nrv, mus, sen, mod, ph = sim.nervous, sim.muscles, sim.senses, sim.modulators, sim.pharynx
    egl = sim.egglaying
    body = sim.body
    b = Blob()

    n, m = conn.n, conn.n_muscles
    b.i("n_neurons", n).i("n_muscles", m)
    b.i("n_links", p.body.n_links).i("n_nodes", p.body.n_links + 1)
    b.i("n_joints", p.body.n_links - 1)
    b.f("dt", p.neural.dt)

    # -- identity, for the viewer ------------------------------------------------------
    b.s("neuron_names", "\n".join(conn.names))
    b.s("neuron_cls", "\n".join(conn.cls))
    b.s("neuron_kind", "\n".join(conn.kind))
    b.s("neuron_ganglion", "\n".join(conn.ganglion))
    b.s("neuron_modality", "\n".join(conn.modality))
    b.s("neuron_tx", "\n".join(conn.transmitter))
    b.s("muscle_names", "\n".join(conn.muscle_names))
    b.arr("soma_pos", conn.soma_pos)
    b.arr("neuron_inh", conn.inhibitory, "u1")

    # -- nervous system: everything the step reads --------------------------------------
    # Sparse: see Blob.csr. G_syn and GE_syn share one pattern between two value arrays.
    b.csr("syn", nrv.G_syn, extra=nrv.GE_syn)
    b.csr("gap", nrv.G_gap)
    b.arr("gap_total", nrv.gap_total)
    b.arr("g_leak", nrv.g_leak).arr("E_leak", nrv.E_leak)
    b.arr("g_ca", nrv.g_ca).arr("g_adapt", nrv.g_adapt)
    b.arr("V_th", nrv.V_th).arr("ca_vhalf", nrv.ca_vhalf).arr("k_vhalf", nrv.k_vhalf)
    b.arr("adapt_decay", nrv._adapt_decay)
    b.arr("d_rest", nrv.d_rest).arr("depress_use", nrv._use)
    b.arr("V_init", nrv.V).arr("s_init", nrv.s).arr("a_init", nrv.a)
    b.f("n0", float(np.asarray(nrv.n0).ravel()[0]))
    np_ = p.neural
    _export_scalars(b, np_, NEURAL_SCALARS, "neural_")
    b.f("v_clamp_lo", np_.v_clamp[0]).f("v_clamp_hi", np_.v_clamp[1])
    b.i("gap_iters", np_.gap_iters)
    b.i("any_depress", 1 if nrv._any_depress else 0)

    # -- muscle -------------------------------------------------------------------------
    b.csr("mus", mus.G)
    b.arr("mus_E_pre", mus.E_pre)
    b.arr("mus_G_gap", mus.G_gap).arr("mus_gap_total", mus.gap_total)
    b.arr("mus_phasic_gain", mus.phasic_gain)
    b.arr("mus_row_mask_d", mus._row_mask_d, "u1").arr("mus_row_mask_v", mus._row_mask_v, "u1")
    b.arr("mus_row_n_d", mus._row_n_d).arr("mus_row_n_v", mus._row_n_v)
    b.arr("mus_row_pos", mus.row_pos).arr("mus_joint_gain", mus.joint_gain)
    b.arr("mus_joint_s", mus.joint_s)
    b.f("mus_s_eq", mus.s_eq)
    b.f("mus_decay_ca", mus._decay_ca).f("mus_decay_te", mus._decay_te)
    b.f("mus_C_nF", mus._C_nF)
    _export_scalars(b, p.muscle, MUSCLE_SCALARS, "mus_")
    b.i("mus_n_rows", len(mus._rows))
    b.i("any_phasic", 1 if mus._any_phasic else 0)

    # -- body ---------------------------------------------------------------------------
    b.arr("body_rho", body.rho).arr("body_K", body.K).arr("body_gamma", body.gamma)
    b.arr("body_K_mat", body._K_mat).arr("body_B_mat", body._B_mat)
    b.arr("body_mask_rho", body._mask_rho).arr("body_mask_sqrt", body._mask_sqrt)
    b.arr("body_rho_max_off", body._rho_max_off)
    b.arr("body_radius", body.radius).arr("body_joint_radius", body.joint_radius)
    # Per-node half-width, for self-contact. Exported rather than recomputed in the
    # runtime so the two sides cannot drift in the radius profile's exponent, and so it
    # keeps following radius_max if morphology ever becomes heritable.
    b.arr("body_node_radius", body.node_radius)
    b.f("body_l", body.l)
    b.i("body_substeps", p.body.substeps)
    b.f("body_length", p.body.length).f("body_radius_max", p.body.radius_max)
    # Every medium, so the viewer can switch without a round trip.
    for name, med in MEDIA.items():
        b.f("med_%s_ct" % name, med.c_tangential).f("med_%s_cn" % name, med.c_normal)
    b.s("media", "\n".join(MEDIA.keys()))
    b.s("medium_default", "agar")

    # -- senses: the precomputed maps ---------------------------------------------------
    b.csr("wb", sen.W_b).csr("wa", sen.W_a)
    b.csr("wbf", sen.W_b_food).csr("waf", sen.W_a_food)
    b.csr("whead", sen.W_head)
    b.arr("W_head_sign", sen.W_head_sign)
    b.arr("head_window", sen._head_window)
    b.arr("g_scale_prop", sen.g_scale_prop).arr("g_scale_head", sen.g_scale_head)
    b.i("head_delay_n", sen._head_delay_n)
    b.f("head_decay", sen._head_decay)
    b.f("prop_adapt_rate", sen._prop_adapt_rate)
    b.f("chem_decay", sen._chem_decay).f("odour_decay", sen._odour_decay)
    b.f("odour_rate", sen._odour_rate).f("therm_decay", sen._therm_decay)
    b.f("o2_rate", sen._o2_rate).f("rep_rate", sen._rep_rate)
    b.f("touch_decay", sen._touch_decay).f("touch_rate", sen._touch_rate)
    b.f("omega_decay", sen._omega_decay).f("omega_ref_n", sen._omega_ref_n)
    b.f("hab_use", sen._hab_use).f("hab_recover", sen._hab_recover)
    b.i("habituates", 1 if sen._habituates else 0)
    b.i("head_distributed", 1 if p.sensory.head_distributed else 0)
    b.i("gate_latched", 1 if p.sensory.gate_latched else 0)
    _export_scalars(b, p.sensory, SENSORY_SCALARS, "sen_")

    # -- neuron index sets the step needs ------------------------------------------------
    sets = {
        "ase_on": sen.ase_on, "ase_off": sen.ase_off, "awc": sen.awc, "awa": sen.awa,
        "ash": sen.ash, "adl": sen.adl, "ask": sen.ask, "afd": sen.afd, "urx": sen.urx,
        "touch_ant": sen.touch_anterior, "touch_post": sen.touch_posterior,
        "nose_touch": sen.nose_touch, "dopaminergic": sen.dopaminergic, "nsm": sen.nsm,
        "avb": sen.avb, "ava": sen.ava,
        "db": sen.db, "vb": sen.vb, "da": sen.da, "va": sen.va,
        "omega_v": sen._omega_v, "omega_d": sen._omega_d,
        "mc": ph.mc, "m3": ph.m3, "m4": ph.m4, "i2": ph.i2,
        # VC06 is absent from egl.vc on purpose -- it has no synapses and no gap junctions
        # in this reconstruction, so reading it would be reading the noise generator.
        "egl_hsn": egl.hsn, "egl_vc": egl.vc,
    }
    for k, v in sets.items():
        b.arr("idx_" + k, np.asarray(v, dtype=np.int32), "i4")
    for k in mod.NAMES:
        b.arr("idx_mod_" + k, np.asarray(mod.sources[k], dtype=np.int32), "i4")
        b.f("mod_rate_" + k, mod._rate[k])
    # The coefficient is factored out: `mod1_unit` is the target set's resting conductance
    # and `mod_serotonin_mod1` scales it, so an individual can carry its own coefficient
    # without a re-export. `mod1_peak` was the product, which baked the coefficient into
    # the payload and is why this path could never be exercised in the browser.
    b.arr("mod1_unit", mod._mod1_unit)
    _export_scalars(b, p.modulator, MODULATOR_SCALARS, "mod_")

    # -- pharynx --------------------------------------------------------------------------
    _export_scalars(b, p.pharynx, PHARYNX_SCALARS, "ph_")

    # -- egg-laying -----------------------------------------------------------------------
    ep = p.egglaying
    _export_scalars(b, ep, EGGLAYING_SCALARS, "egl_")
    # The recovery rate itself, not just the tau it comes from. The runtime used to derive
    # it -- `1.0 - Math.exp(-dt / EGL_RESOURCE_TAU)`, recomputed two thousand times a
    # second for a constant -- which was tolerable only while Python computed it the same
    # lossy way. It no longer does, so deriving it there would manufacture a 6.5e-12
    # divergence between the two implementations out of nothing: the largest cancellation
    # of the ten rates, because this tau is by far the longest. Exporting it puts both
    # sides back on one number, which is what this file is for.
    b.f("egl_resource_recover", egl._recover)
    # The window in steps, derived from the duration rather than written down as a step
    # count -- see EggLayingParams.rest_seconds. Exported derived so the runtime does not
    # have to know dt to reproduce it, and so a change of dt moves both sides together.
    b.i("egl_rest_samples", egl._rest_steps)
    # The vulval muscle's decay per step. The runtime used to integrate this filter by
    # forward Euler, `vm += (target - vm) * (dt / vm_tau)`, which is the model's only
    # non-exponential first-order state and diverges for vm_tau < dt/2 -- profitably, by
    # laying eggs. Exported so both implementations relax the same way. See #42.
    b.f("egl_vm_decay", egl._vm_decay)
    # The browser keeps eggs in a fixed ring rather than a growing list: a tab left
    # open overnight lays thousands, and the plate is a picture, not a record.
    b.i("max_eggs", 4096)

    # -- world ---------------------------------------------------------------------------
    wp = p.world
    _export_scalars(b, wp, WORLD_SCALARS, "world_")
    b.i("world_grid", wp.grid)
    b.f("world_extent", sim.world.extent)

    # -- genome ------------------------------------------------------------------------
    # Recorded in the header so the browser can address genes by name without keeping its
    # own copy of the list. Validated rather than filtered: a gene that names a scalar
    # this file does not export would otherwise vanish silently, the runtime would keep
    # its compiled-in literal, and a mutation on it would do nothing -- indistinguishable
    # from a gene under no selection. That is the quietest way this could ship broken.
    unknown = [g for g in GENES if g not in b.meta["scalars"]]
    if unknown:
        raise KeyError("genes name scalars that are not exported: %s" % ", ".join(unknown))
    b.meta["genes"] = list(GENES)

    size = b.write(path)
    _emit_ts(b.meta, "wasm/assembly/model_gen.ts")
    return path, size, b.meta


def _emit_ts(meta, path):
    """Emit the payload layout as AssemblyScript compile-time constants.

    The alternative is a runtime binding step -- JS reads the JSON header and tells the
    module where each array landed -- and that is an entire class of bug (a slot list in
    two places, silently out of order) in exchange for nothing. The .wasm and the .model
    are produced by the same command, so they can simply agree by construction. Scalars
    become literal constants too, which the optimiser likes.
    """
    def ident(k):
        return k.replace("-", "_")
    out = ["// GENERATED by tools/export_model.py -- do not edit.",
           "// Offsets into the .model payload, and every scalar the step functions read.",
           ""]
    for k, v in sorted(meta["arrays"].items()):
        n = 1
        for d in v["shape"]:
            n *= d
        out.append("export const OFF_%s: usize = %d;" % (ident(k), v["offset"]))
        out.append("export const LEN_%s: i32 = %d;" % (ident(k), n))
        if len(v["shape"]) == 2:
            out.append("export const ROWS_%s: i32 = %d;" % (ident(k), v["shape"][0]))
            out.append("export const COLS_%s: i32 = %d;" % (ident(k), v["shape"][1]))
    out.append("")
    for k, v in sorted(meta["scalars"].items()):
        out.append("export const %s: f64 = %r;" % (ident(k).upper(), float(v)))
    for k, v in sorted(meta["ints"].items()):
        out.append("export const %s: i32 = %d;" % (ident(k).upper(), int(v)))

    # Genome slot numbering. Emitted rather than hand-written on either side, because a
    # slot list kept in two places is exactly the bug this file's docstring is about.
    out.append("")
    out.append("// Genome slots. The list lives in tools/export_model.py; see GENES there.")
    for slot, name in enumerate(meta["genes"]):
        out.append("export const GENE_%s: i32 = %d;" % (ident(name).upper(), slot))
    out.append("export const N_GENES: i32 = %d;" % len(meta["genes"]))
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    path, size, meta = export(path)
    print("wrote %s  (%.2f MB)" % (path, size / 1024 ** 2))
    print("  %d arrays, %d scalars, %d ints"
          % (len(meta["arrays"]), len(meta["scalars"]), len(meta["ints"])))
    big = sorted(meta["arrays"].items(), key=lambda kv: -kv[1]["bytes"])[:6]
    for k, v in big:
        print("    %-18s %-12s %7.1f kB" % (k, "x".join(map(str, v["shape"])),
                                            v["bytes"] / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
