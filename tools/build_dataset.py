"""Build a single validated C. elegans connectome dataset from the raw sources.

Inputs (data/raw/):
  CElegansNeuronTables.xls  -- OpenWorm c302 distribution of the White et al. (1986) /
                               Chen et al. (2006) connectome, with neurotransmitter
                               annotations, the neuron->body-wall-muscle (NMJ) table and
                               a sensory-neuron functional annotation table.
  NeuronType.xls            -- WormAtlas neuron table: soma position along the body
                               (0 = tip of nose, 1 = tip of tail), soma region, process span.
  herm_full_edgelist.csv    -- Cook et al. (2019) hermaphrodite edge list, used only to
                               cross-validate the muscle roster.

Output:
  data/celegans.json  -- everything the simulator needs, with provenance and checksums.

Everything here is deliberately assertion-heavy: a silent data error in the connectome
would produce a worm that looks plausible and is wrong, which is the worst outcome.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import sys

import xlrd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "celegans.json")

# Motor-neuron classes whose members are numbered and appear zero-padded in one source
# and unpadded in the other (e.g. "DA1" vs "DA01").
PADDED_CLASSES = ("AS", "DA", "DB", "DD", "VA", "VB", "VC", "VD")
_PAD_RE = re.compile(r"^(%s)(\d{1,2})$" % "|".join(PADDED_CLASSES))

# The 20 pharyngeal neurons. They form a nearly autonomous nervous system connected to
# the somatic one only through the RIP interneurons, and have no soma position in the
# WormAtlas somatic table.
PHARYNGEAL = {
    "I1L", "I1R", "I2L", "I2R", "I3", "I4", "I5", "I6",
    "M1", "M2L", "M2R", "M3L", "M3R", "M4", "M5",
    "MCL", "MCR", "MI", "NSML", "NSMR",
}

# McIntire, Jorgensen, Kaplan & Horvitz (1993) Nature 364:337-341 -- the 26 GABAergic
# neurons of C. elegans. Used to validate the neurotransmitter labels in the edge table.
GABAERGIC_CANONICAL = (
    {"DD%02d" % i for i in range(1, 7)}
    | {"VD%02d" % i for i in range(1, 14)}
    | {"AVL", "DVB", "RIS", "RMED", "RMEV", "RMEL", "RMER"}
)

# Neurons known to make no synapses at all in the White/Chen reconstruction. They are part
# of the canonical 302 but absent from every edge table.
NON_SYNAPTIC = {"CANL", "CANR"}

# GABAergic but *excitatory*. AVL and DVB release GABA onto enteric muscle through EXP-1,
# a GABA-gated cation channel rather than a chloride channel (Beg & Jorgensen 2003,
# Nat. Neurosci. 6:1145), so their synapses depolarise their targets. Every standard model
# -- Wicks 1996, Kunert et al. 2014, c302 -- marks these two inhibitory purely because they
# stain for GABA. We keep them GABAergic and make their synapses excitatory, which is what
# the receptor pharmacology actually says.
EXCITATORY_GABA = {"AVL", "DVB"}

# The WormAtlas somatic table omits the 20 pharyngeal neurons, the two canal-associated
# CAN neurons and VC06. Their soma positions below are approximate, read off WormAtlas
# anatomy (pharynx = anterior ~12% of the body; CAN soma sits on the excretory canal just
# behind the midbody; VC06 lies posterior to the vulva). They are flagged pos_approx in
# the output and are used only for layout and proprioceptive addressing.
EXTRA_SOMA = {
    # anterior pharynx: procorpus / metacorpus
    "I1L": 0.045, "I1R": 0.045, "I2L": 0.035, "I2R": 0.035, "I3": 0.055,
    "M1": 0.050, "M2L": 0.075, "M2R": 0.075, "MI": 0.070,
    "MCL": 0.065, "MCR": 0.065, "NSML": 0.055, "NSMR": 0.055,
    # isthmus / terminal bulb
    "I4": 0.085, "I5": 0.100, "I6": 0.110,
    "M3L": 0.080, "M3R": 0.080, "M4": 0.095, "M5": 0.105,
    # somatic stragglers
    "CANL": 0.470, "CANR": 0.470,
    "VC06": 0.620,
}
EXTRA_REGION = {"CANL": "M", "CANR": "M", "VC06": "M"}

MUSCLE_RE = re.compile(r"^M([DV])([LR])(\d{2})$")

# Achacoso & Yamamoto ganglion designations used by the WormAtlas table.
GANGLIA = {
    "A": "anterior ganglion",
    "B": "dorsal ganglion",
    "C": "lateral ganglion",
    "D": "ventral ganglion",
    "E": "retrovesicular ganglion",
    "F": "posterolateral ganglion",
    "G": "ventral cord",
    "H": "pre-anal ganglion",
    "J": "dorsorectal ganglion",
    "K": "lumbar ganglion",
}
GANGLION_EXTRA = dict(
    [(n, "pharyngeal nervous system") for n in PHARYNGEAL]
    + [("CANL", "lateral (canal-associated)"), ("CANR", "lateral (canal-associated)"),
       ("VC06", "ventral cord")]
)

_QUADRANTS = ("DL", "DR", "VL", "VR")
_OPPOSITE = {"L": "R", "R": "L"}

# The only two classes whose members carry a bare dorsal/ventral suffix without also
# carrying a left/right one. Spelling them out is safer than a string rule, which would
# also swallow the singleton RID (RI + D looks identical to RME + D).
IRREGULAR_CLASS = {
    "RMED": "RME", "RMEV": "RME",
    "SABD": "SAB", "SABVL": "SAB", "SABVR": "SAB",
}


def neuron_class(name: str, roster) -> str:
    """Strip the positional suffix to get the anatomical class (AVAL -> AVA).

    A suffix is only stripped when the sibling it implies actually exists, so genuine
    singletons whose names happen to end in L/R/D/V are left alone (AVL stays AVL, AQR
    stays AQR) instead of being folded into a phantom class.
    """
    if name in IRREGULAR_CLASS:
        return IRREGULAR_CLASS[name]
    m = re.fullmatch(r"([A-Z]+)(\d{2})", name)
    if m:
        return m.group(1)                                   # DA01 -> DA, VC06 -> VC
    stem = name[:-2]
    if len(stem) >= 2 and name[-2:] in _QUADRANTS and all(
            stem + q in roster for q in _QUADRANTS):
        return stem                                         # CEPDL -> CEP, SMDVR -> SMD
    stem, suffix = name[:-1], name[-1]
    if len(stem) >= 2 and suffix in _OPPOSITE and stem + _OPPOSITE[suffix] in roster:
        return stem                                         # AVAL -> AVA, I1L -> I1
    return name


def canonical(name: str) -> str:
    """Normalise a neuron name to the zero-padded canonical form."""
    name = str(name).strip()
    m = _PAD_RE.match(name)
    if m:
        return "%s%02d" % (m.group(1), int(m.group(2)))
    return name


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sheet(book_path: str, name: str):
    return xlrd.open_workbook(book_path).sheet_by_name(name)


def rows(sh, ncols: int):
    for r in range(1, sh.nrows):
        vals = [sh.cell_value(r, c) for c in range(ncols)]
        if all((isinstance(v, str) and not v.strip()) or v == "" for v in vals):
            continue
        yield vals


def build() -> dict:
    tables = os.path.join(RAW, "CElegansNeuronTables.xls")
    types_path = os.path.join(RAW, "NeuronType.xls")
    cook_path = os.path.join(RAW, "herm_full_edgelist.csv")
    for p in (tables, types_path, cook_path):
        if not os.path.exists(p):
            sys.exit("missing raw input: %s (run tools/fetch_raw.sh)" % p)

    # ---------------------------------------------------------------- neuron roster
    ntype = sheet(types_path, "NeuronType.csv")
    soma = {}
    for v in rows(ntype, 15):
        name = canonical(v[0])
        if not name:
            continue
        soma[name] = {
            "soma_pos": float(v[1]),
            "region": str(v[2]).strip(),      # H(ead) / M(idbody) / T(ail)
            "span": str(v[3]).strip(),        # S(hort) / L(ong) process span
            "ganglion": GANGLIA.get(str(v[14]).strip(), "unassigned"),
        }

    conn = sheet(tables, "Connectome")
    edges = []
    for v in rows(conn, 5):
        src, dst = canonical(v[0]), canonical(v[1])
        kind = str(v[2]).strip()
        weight = float(v[3])
        nt = str(v[4]).strip()
        assert kind in ("Send", "GapJunction"), kind
        assert weight > 0, (src, dst, weight)
        edges.append((src, dst, kind, weight, nt))

    nmj_sheet = sheet(tables, "NeuronsToMuscle")
    nmj_rows = []
    for v in rows(nmj_sheet, 4):
        nmj_rows.append((canonical(v[0]), str(v[1]).strip(), float(v[2]), str(v[3]).strip()))

    sens = sheet(tables, "Sensory")
    sensory_ann = {}
    for v in rows(sens, 7):
        name = canonical(v[0])
        func = str(v[6]).strip().lower()
        pos = v[2]
        prev = sensory_ann.get(name)
        modality = func or (prev or {}).get("modality", "")
        sensory_ann[name] = {
            "modality": modality,
            "receptor_pos": float(pos) if isinstance(pos, float) else None,
        }

    names = set(soma) | {e[0] for e in edges} | {e[1] for e in edges} | NON_SYNAPTIC
    names |= {n for n, _, _, _ in nmj_rows}
    # Muscle names must never leak into the neuron roster.
    names = {n for n in names if not MUSCLE_RE.match(n) and n not in ("MANAL", "MVULVA")}

    missing_pos = sorted(n for n in names if n not in soma)
    assert set(missing_pos) == set(EXTRA_SOMA), (
        "soma-position coverage changed -- unaccounted: %s ; stale: %s"
        % (sorted(set(missing_pos) - set(EXTRA_SOMA)), sorted(set(EXTRA_SOMA) - set(missing_pos)))
    )
    approx = set(EXTRA_SOMA)
    for n, p in EXTRA_SOMA.items():
        soma[n] = {"soma_pos": p, "region": EXTRA_REGION.get(n, "H"), "span": "S",
                   "ganglion": GANGLION_EXTRA[n]}

    assert len(names) == 302, "expected the canonical 302 neurons, got %d" % len(names)

    # ------------------------------------------------------------------- classification
    nmj_neurons = {n for n, _, _, _ in nmj_rows}
    sensory_neurons = {n for n in sensory_ann if n in names}

    def classify(n: str) -> str:
        if n in PHARYNGEAL:
            return "pharyngeal"
        is_s = n in sensory_neurons
        is_m = n in nmj_neurons
        if is_s and is_m:
            return "sensory-motor"
        if is_s:
            return "sensory"
        if is_m:
            return "motor"
        return "inter"

    # Presynaptic neurotransmitter per neuron: a neuron releases one transmitter, so we
    # take the majority label across all of its outgoing chemical synapses (including NMJs).
    tx_votes = collections.defaultdict(collections.Counter)
    for src, _dst, kind, w, nt in edges:
        if kind == "Send" and nt:
            for token in re.split(r"[,_]", nt):
                token = token.strip()
                if token:
                    tx_votes[src][token] += w
    for src, _m, w, nt in nmj_rows:
        for token in re.split(r"[,_]", nt):
            token = token.strip()
            if token and token != "FRMFemide":  # source typo for FMRFamide
                tx_votes[src][token] += w

    # Only acetylcholine, glutamate and GABA are fast ionotropic transmitters in C. elegans;
    # monoamines and peptides are co-released neuromodulators and are reported separately
    # rather than being promoted to "the" transmitter when the table has no fast label.
    FAST = ("GABA", "Acetylcholine", "Glutamate")
    transmitter, modulators = {}, {}
    for n in sorted(names):
        votes = tx_votes.get(n, collections.Counter())
        fast = [(w, t) for t, w in votes.items() if t in FAST]
        transmitter[n] = max(fast)[1] if fast else "unassigned"
        modulators[n] = sorted(t for t in votes if t not in FAST)

    # Synaptic sign comes from the canonical GABAergic roster, not from the edge-table
    # labels: the c302 table's neurotransmitter column carries a handful of spurious GABA
    # annotations (it mixes in neuropeptide and receptor evidence). McIntire et al. (1993)
    # is the authoritative immunostaining result, so it wins. The table label is still kept
    # per neuron for display, and the disagreement is reported rather than hidden.
    assert GABAERGIC_CANONICAL <= names, (
        "canonical GABAergic neurons missing from the roster: %s"
        % sorted(GABAERGIC_CANONICAL - names)
    )
    gaba = set(GABAERGIC_CANONICAL)
    inhibitory_set = gaba - EXCITATORY_GABA
    labelled = {n for n in names if transmitter[n] == "GABA"}
    tx_disagreement = {
        "labelled_gaba_but_not_canonical": sorted(labelled - gaba),
        "canonical_but_not_labelled_gaba": sorted(gaba - labelled),
    }
    for n in gaba:
        transmitter[n] = "GABA"
    # Re-vote the spurious GABA labels without GABA in the running, so the displayed
    # transmitter never contradicts the polarity we actually simulate.
    for n in labelled - gaba:
        votes = collections.Counter({t: w for t, w in tx_votes[n].items() if t != "GABA"})
        fast = [(w, t) for t, w in votes.items() if t in FAST]
        transmitter[n] = max(fast)[1] if fast else "unassigned"

    # -------------------------------------------------------------------- neuron order
    # Sort by soma position so that index order is anatomical (nose -> tail); pharyngeal
    # and non-synaptic neurons keep their anatomical position where known.
    order = sorted(names, key=lambda n: (soma[n]["soma_pos"], n))
    index = {n: i for i, n in enumerate(order)}

    neurons = []
    for n in order:
        s = soma[n]
        ann = sensory_ann.get(n, {})
        neurons.append({
            "name": n,
            "cls": neuron_class(n, names),
            "soma_pos": round(float(s["soma_pos"]), 4),
            "pos_approx": n in approx,
            "region": s["region"],
            "span": s["span"],
            "ganglion": s["ganglion"],
            "kind": classify(n),
            "transmitter": transmitter[n],
            "modulators": modulators[n],
            "inhibitory": n in inhibitory_set,
            "gabaergic": n in gaba,
            "modality": ann.get("modality", ""),
            "side": "L" if n.endswith("L") else ("R" if n.endswith("R") else "-"),
        })

    # ------------------------------------------------------------------------ synapses
    # Gap junctions. The table lists each junction once per direction; we symmetrise by
    # taking the maximum reported count (they occasionally disagree by one).
    gap = collections.defaultdict(float)
    chem = collections.defaultdict(float)
    for src, dst, kind, w, _nt in edges:
        if src not in index or dst not in index:
            continue
        i, j = index[src], index[dst]
        if kind == "GapJunction":
            if i == j:
                continue
            a, b = (i, j) if i < j else (j, i)
            gap[(a, b)] = max(gap[(a, b)], w)
        else:
            if i == j:
                continue
            chem[(i, j)] += w

    # A gap junction is electrically symmetric, so the table should report each one from
    # both sides. Verify that before relying on the symmetrisation above.
    directed_gap = {
        (index[s], index[d]) for s, d, k, _w, _n in edges
        if k == "GapJunction" and s in index and d in index and s != d
    }
    one_sided = sorted(
        (order[a], order[b]) for (a, b) in gap
        if not ((a, b) in directed_gap and (b, a) in directed_gap)
    )
    # A handful of junctions (all involving the pharyngeal nervous system, which the c302
    # table merges in from a separate reconstruction) are listed from one side only. They
    # are still physically bidirectional, so symmetrising is correct -- but if this ever
    # starts happening in the somatic connectome the table has changed and we want to know.
    somatic_one_sided = [
        (a, b) for a, b in one_sided if a not in PHARYNGEAL and b not in PHARYNGEAL
    ]
    assert not somatic_one_sided, (
        "somatic gap junctions reported in only one direction: %s" % somatic_one_sided
    )

    # ---------------------------------------------------------------------- muscles
    muscles = []
    for quad in ("MDL", "MDR", "MVL", "MVR"):
        n_in_quad = 23 if quad == "MVL" else 24
        for k in range(1, n_in_quad + 1):
            muscles.append("%s%02d" % (quad, k))
    mus_index = {m: i for i, m in enumerate(muscles)}
    assert len(muscles) == 95, len(muscles)

    seen_muscles = {m for _n, m, _w, _t in nmj_rows if MUSCLE_RE.match(m)}
    assert seen_muscles == set(muscles), (
        "muscle roster mismatch: %s" % sorted(seen_muscles ^ set(muscles))
    )

    # Cross-validate the roster against the independent Cook et al. (2019) edge list.
    cook_muscles = set()
    with open(cook_path) as fh:
        next(fh)
        for line in fh:
            parts = [p.strip() for p in line.split(",")]
            for node in parts[:2]:
                m = re.fullmatch(r"([dv])BWM([LR])(\d{1,2})", node)
                if m:
                    cook_muscles.add("M%s%s%02d" % (
                        m.group(1).upper(), m.group(2), int(m.group(3))))
    assert cook_muscles == set(muscles), (
        "Cook 2019 muscle roster disagrees: %s" % sorted(cook_muscles ^ set(muscles))
    )

    nmj = collections.defaultdict(float)
    for n, m, w, _nt in nmj_rows:
        if not MUSCLE_RE.match(m):
            continue  # MANAL / MVULVA are not body-wall muscles
        nmj[(index[n], mus_index[m])] += w

    # Every body-wall muscle must be innervated, or the body would have dead segments.
    innervated = {j for _i, j in nmj}
    assert innervated == set(range(95)), (
        "un-innervated muscles: %s" % sorted(set(range(95)) - innervated)
    )

    muscle_meta = []
    for m in muscles:
        mm = MUSCLE_RE.match(m)
        k = int(mm.group(3))
        n_in_quad = 23 if m.startswith("MVL") else 24
        muscle_meta.append({
            "name": m,
            "side": mm.group(1),          # D or V
            "lr": mm.group(2),            # L or R
            "index": k,                   # 1..24, anterior -> posterior
            # Normalised position of the muscle midpoint along the body. Body-wall muscles
            # span roughly from 6% to 96% of body length (Boyle & Cohen 2008).
            "body_pos": round(0.06 + 0.90 * (k - 0.5) / n_in_quad, 4),
        })

    dataset = {
        "meta": {
            "description": "C. elegans hermaphrodite connectome, muscle map and anatomy, "
                           "assembled for the openworm-sim neuromechanical simulator.",
            "sources": {
                "CElegansNeuronTables.xls": {
                    "sha256": sha256(tables),
                    "origin": "openworm/c302 @ master :: c302/data/CElegansNeuronTables.xls",
                    "provenance": "White et al. 1986; Chen, Hall & Chklovskii 2006",
                },
                "NeuronType.xls": {
                    "sha256": sha256(types_path),
                    "origin": "wormatlas.org/images/NeuronType.xls",
                    "provenance": "WormAtlas neuron table (soma positions)",
                },
                "herm_full_edgelist.csv": {
                    "sha256": sha256(cook_path),
                    "origin": "openworm/c302 @ master :: c302/data/herm_full_edgelist.csv",
                    "provenance": "Cook et al. 2019 (used only to cross-check the muscle roster)",
                },
            },
            "conventions": {
                "soma_pos": "0 = tip of nose, 1 = tip of tail",
                "synapse_weight": "number of reconstructed synaptic contacts",
                "gap_weight": "number of reconstructed gap-junction contacts (symmetric)",
                "polarity": "inhibitory iff the presynaptic neuron is GABAergic "
                            "(McIntire et al. 1993), except AVL and DVB whose GABA acts on "
                            "the EXP-1 cation channel and is excitatory; all other fast "
                            "transmitters excitatory",
            },
            "transmitter_label_disagreement": tx_disagreement,
            "one_sided_gap_junctions": ["%s-%s" % ab for ab in one_sided],
        },
        "neurons": neurons,
        "muscles": muscle_meta,
        "gap_junctions": [[a, b, w] for (a, b), w in sorted(gap.items())],
        "chemical_synapses": [
            [i, j, w, -1 if neurons[i]["inhibitory"] else 1]
            for (i, j), w in sorted(chem.items())
        ],
        "neuromuscular_junctions": [
            [i, j, w, -1 if neurons[i]["inhibitory"] else 1]
            for (i, j), w in sorted(nmj.items())
        ],
    }
    return dataset


def report(d: dict) -> None:
    n = d["neurons"]
    kinds = collections.Counter(x["kind"] for x in n)
    tx = collections.Counter(x["transmitter"] for x in n)
    print("neurons                %d" % len(n))
    for k, v in sorted(kinds.items()):
        print("    %-14s     %d" % (k, v))
    print("transmitters           %s" % dict(tx.most_common()))
    print("inhibitory (GABA)      %d" % sum(1 for x in n if x["inhibitory"]))
    print("gap junctions          %d edges, %d contacts"
          % (len(d["gap_junctions"]), sum(e[2] for e in d["gap_junctions"])))
    print("chemical synapses      %d edges, %d contacts"
          % (len(d["chemical_synapses"]), sum(e[2] for e in d["chemical_synapses"])))
    inh = sum(1 for e in d["chemical_synapses"] if e[3] < 0)
    print("    inhibitory edges   %d (%.1f%%)" % (inh, 100.0 * inh / len(d["chemical_synapses"])))
    print("body-wall muscles      %d" % len(d["muscles"]))
    nmj_inh = sum(1 for e in d["neuromuscular_junctions"] if e[3] < 0)
    print("NMJs                   %d edges, %d contacts (%d inhibitory edges)"
          % (len(d["neuromuscular_junctions"]),
             sum(e[2] for e in d["neuromuscular_junctions"]), nmj_inh))
    print("ganglia                %s"
          % dict(collections.Counter(x["ganglion"] for x in n).most_common()))
    dis = d["meta"]["transmitter_label_disagreement"]["labelled_gaba_but_not_canonical"]
    print("table GABA labels overridden: %s" % dis)


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    report(data)
    print("\nwrote %s (%.1f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))
