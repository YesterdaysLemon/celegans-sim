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


class Blob:
    """Collects named arrays and scalars, then writes header + payload."""

    def __init__(self):
        self.meta = {"arrays": {}, "scalars": {}, "ints": {}, "strings": {}}
        self.chunks = []
        self.offset = 0

    def arr(self, name, a, dtype="f8"):
        a = np.ascontiguousarray(np.asarray(a, dtype=np.dtype(dtype)))
        self.meta["arrays"][name] = {"dtype": dtype, "shape": list(a.shape),
                                     "offset": self.offset, "bytes": a.nbytes}
        self.chunks.append(a.tobytes())
        self.offset += a.nbytes
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
    b.arr("G_syn", nrv.G_syn).arr("GE_syn", nrv.GE_syn).arr("G_gap", nrv.G_gap)
    b.arr("gap_total", nrv.gap_total)
    b.arr("g_leak", nrv.g_leak).arr("E_leak", nrv.E_leak)
    b.arr("g_ca", nrv.g_ca).arr("g_adapt", nrv.g_adapt)
    b.arr("V_th", nrv.V_th).arr("ca_vhalf", nrv.ca_vhalf).arr("k_vhalf", nrv.k_vhalf)
    b.arr("adapt_decay", nrv._adapt_decay)
    b.arr("d_rest", nrv.d_rest).arr("depress_use", nrv._use)
    b.arr("V_init", nrv.V).arr("s_init", nrv.s).arr("a_init", nrv.a)
    b.f("n0", float(np.asarray(nrv.n0).ravel()[0]))
    np_ = p.neural
    for k in ("beta", "ca_slope", "k_slope", "E_K", "E_Ca", "E_inh", "a_rise", "a_decay",
              "noise_tau", "noise_sigma", "depression_tau", "C_m"):
        b.f("neural_" + k, getattr(np_, k))
    b.f("v_clamp_lo", np_.v_clamp[0]).f("v_clamp_hi", np_.v_clamp[1])
    b.i("gap_iters", np_.gap_iters)
    b.i("any_depress", 1 if nrv._any_depress else 0)

    # -- muscle -------------------------------------------------------------------------
    b.arr("mus_G", mus.G).arr("mus_E_pre", mus.E_pre)
    b.arr("mus_G_gap", mus.G_gap).arr("mus_gap_total", mus.gap_total)
    b.arr("mus_phasic_gain", mus.phasic_gain)
    b.arr("mus_row_mask_d", mus._row_mask_d, "u1").arr("mus_row_mask_v", mus._row_mask_v, "u1")
    b.arr("mus_row_n_d", mus._row_n_d).arr("mus_row_n_v", mus._row_n_v)
    b.arr("mus_row_pos", mus.row_pos).arr("mus_joint_gain", mus.joint_gain)
    b.arr("mus_joint_s", mus.joint_s)
    b.f("mus_s_eq", mus.s_eq)
    b.f("mus_decay_ca", mus._decay_ca).f("mus_decay_te", mus._decay_te)
    b.f("mus_C_nF", mus._C_nF)
    mp = p.muscle
    for k in ("g_leak", "E_leak", "beta", "v_half", "rest_tension"):
        b.f("mus_" + k, getattr(mp, k))
    b.i("mus_n_rows", len(mus._rows))
    b.i("any_phasic", 1 if mus._any_phasic else 0)

    # -- body ---------------------------------------------------------------------------
    b.arr("body_rho", body.rho).arr("body_K", body.K).arr("body_gamma", body.gamma)
    b.arr("body_K_mat", body._K_mat).arr("body_B_mat", body._B_mat)
    b.arr("body_mask_rho", body._mask_rho).arr("body_mask_sqrt", body._mask_sqrt)
    b.arr("body_rho_max_off", body._rho_max_off)
    b.arr("body_radius", body.radius).arr("body_joint_radius", body.joint_radius)
    b.f("body_l", body.l)
    b.f("body_length", p.body.length).f("body_radius_max", p.body.radius_max)
    # Every medium, so the viewer can switch without a round trip.
    for name, med in MEDIA.items():
        b.f("med_%s_ct" % name, med.c_tangential).f("med_%s_cn" % name, med.c_normal)
    b.s("media", "\n".join(MEDIA.keys()))
    b.s("medium_default", "agar")

    # -- senses: the precomputed maps ---------------------------------------------------
    b.arr("W_b", sen.W_b).arr("W_a", sen.W_a)
    b.arr("W_b_food", sen.W_b_food).arr("W_a_food", sen.W_a_food)
    b.arr("W_head", sen.W_head).arr("W_head_sign", sen.W_head_sign)
    b.arr("head_window", sen._head_window)
    b.arr("g_scale_prop", sen.g_scale_prop).arr("g_scale_head", sen.g_scale_head)
    b.i("head_delay_n", sen._head_delay_n)
    b.f("head_decay", sen._head_decay)
    b.f("prop_adapt_rate", sen._prop_adapt_rate)
    b.f("chem_decay", sen._chem_decay).f("odour_decay", sen._odour_decay)
    b.f("odour_rate", sen._odour_rate).f("therm_decay", sen._therm_decay)
    b.f("o2_rate", sen._o2_rate)
    b.f("touch_decay", sen._touch_decay).f("touch_rate", sen._touch_rate)
    b.f("omega_decay", sen._omega_decay).f("omega_ref_n", sen._omega_ref_n)
    b.f("hab_use", sen._hab_use).f("hab_recover", sen._hab_recover)
    b.i("habituates", 1 if sen._habituates else 0)
    b.i("head_distributed", 1 if p.sensory.head_distributed else 0)
    b.i("gate_latched", 1 if p.sensory.gate_latched else 0)
    sp = p.sensory
    for k in ("chemo_gain", "thermo_gain", "cultivation_temp", "oxygen_gain",
              "oxygen_preferred", "oxygen_d_gain", "repellent_gain", "food_gain",
              "proprio_gain", "head_proprio_gain", "tonic_forward", "tonic_backward",
              "cord_drive", "gate_slope", "gate_bias", "gate_hysteresis",
              "turn_bias_limit", "touch_gain", "omega_current", "omega_ventral_fraction",
              "omega_reflex_suppression", "nose_touch_gain"):
        if hasattr(sp, k):
            b.f("sen_" + k, getattr(sp, k))

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
    }
    for k, v in sets.items():
        b.arr("idx_" + k, np.asarray(v, dtype=np.int32), "i4")
    for k in mod.NAMES:
        b.arr("idx_mod_" + k, np.asarray(mod.sources[k], dtype=np.int32), "i4")
        b.f("mod_rate_" + k, mod._rate[k])
    b.arr("mod1_peak", mod._mod1_peak)
    b.i("any_mod1", 1 if mod._any_mod1 else 0)
    mo = p.modulator
    for k in ("dopamine_slowing", "serotonin_slowing", "dopamine_wavelength",
              "serotonin_turning", "octopamine_speeding", "pdf_roaming",
              "serotonin_mod1"):
        b.f("mod_" + k, getattr(mo, k))

    # -- pharynx --------------------------------------------------------------------------
    pp = p.pharynx
    for k in ("myogenic_rate", "mc_rate_gain", "i2_rate_gain", "serotonin_to_mc",
              "octopamine_to_mc", "max_rate", "pump_duration", "m3_duration_gain",
              "volume_per_pump", "m4_transport", "m4_gain", "lumen_capacity"):
        b.f("ph_" + k, getattr(pp, k))

    # -- world ---------------------------------------------------------------------------
    wp = p.world
    for k in ("radius", "diffusion", "decay", "ingestion_rate", "field_dt",
              "temp_cold", "temp_warm", "o2_ambient", "o2_depth", "o2_length_scale"):
        if hasattr(wp, k):
            b.f("world_" + k, getattr(wp, k))
    b.i("world_grid", wp.grid)
    b.f("world_extent", sim.world.extent)

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
