/* Weight drift: which of the 3,935 heritable synapses moved from wild-type, and how far.
 *
 * THE QUESTION THIS EXISTS TO ANSWER is on the record in wasm/arena.mjs: the one full
 * weight-mutation run (seed 21) LOST the gene-level proprio-gain climb that five
 * genes-only seeds all showed, and the honest reading was "either wiring variance
 * drowns the gene signal or selection moved into the weights where these reports
 * cannot see it". The gene reports are blind to the wiring tier; this module is the
 * instrument that can see it.
 *
 * Shared by the node drivers and the browser viewer -- ONE implementation, like
 * arena-policy.js, because a drift number that means different things in the report
 * and on the screen is worse than no number. The caller provides the model header and
 * a way to read payload arrays; everything else is uniform:
 *
 *   wild-type   the payload's own syn_val / gap_val / mus_raw_val tables -- the very
 *               arrays a fresh animal aliases until its first mutation clones them.
 *               No reference animal needs to exist to know what wild-type is.
 *   drift       per locus, |log2(current / wild)|: symmetric in direction, additive
 *               over generations of lognormal mutation, and 0 exactly when untouched.
 *   moved       loci with |log2 ratio| > 0.01 -- far below one mutation step
 *               (sigma 0.15 in log space) and far above float noise.
 *
 * TRACK B, as everything about heritable wiring is: drift is a statement about what
 * selection did to this reconstruction's graph, never about C. elegans.
 */

export const FAMS = 3;                 // WFAM_SYN, WFAM_GAP, WFAM_MUS -- runtime order

/* Build the naming/lookup kit from the model header. `readArray(name, Type)` returns a
 * COPY of a payload array -- a copy, because the browser's payload lives in wasm linear
 * memory and views into it detach when the heap grows. Node reads the model file. */
export function makeWiring(head, readArray) {
  const names = (head.strings.neuron_names || '').split('\n');
  const w = {
    nNeurons: head.ints.n_neurons,
    names,
    ptr: [readArray('syn_ptr', Int32Array),
          readArray('gap_ptr', Int32Array),
          readArray('mus_raw_ptr', Int32Array)],
    idx: [readArray('syn_idx', Int32Array),
          readArray('gap_idx', Int32Array),
          readArray('mus_raw_idx', Int32Array)],
    base: [readArray('syn_val', Float64Array),
           readArray('gap_val', Float64Array),
           readArray('mus_raw_val', Float64Array)],
  };
  w.counts = w.base.map((b) => b.length);

  // CSR row of entry k: the largest r with ptr[r] <= k. Rows are postsynaptic neurons
  // for chemical and gap, muscles for the raw rows.
  const rowOf = (fam, k) => {
    const p = w.ptr[fam];
    let lo = 0, hi = p.length - 1;
    while (lo + 1 < hi) {
      const mid = (lo + hi) >> 1;
      if (p[mid] <= k) lo = mid; else hi = mid;
    }
    return lo;
  };

  /* The neuron indices a locus touches -- where its drift is charged in the per-neuron
   * aggregate. A chemical synapse touches pre and post; a gap junction its two ends; a
   * muscle row only its presynaptic neuron (the muscle is not on the neuron panel). */
  w.endpoints = (fam, k) => {
    const pre = w.idx[fam][k];
    if (fam === 2) return [pre];
    return [pre, rowOf(fam, k)];
  };

  w.nameOf = (fam, k) => {
    const pre = names[w.idx[fam][k]];
    if (fam === 2) return `${pre}→muscle row ${rowOf(fam, k) + 1}`;
    const post = names[rowOf(fam, k)];
    return fam === 1 ? `${pre}⇄${post}` : `${pre}→${post}`;
  };

  return w;
}

/* The drift of one animal against wild-type. Null for an animal that has never had a
 * weight mutation -- its arrays still alias the payload, and saying "0 everywhere"
 * costs 3,935 reads to say what hasOwnWeights says for free. */
export function driftOf(E, id, w, topN = 5) {
  if (!E.hasOwnWeights(id)) return null;
  const per = new Float64Array(w.nNeurons);
  let moved = 0, sum = 0, max = 0, total = 0;
  const top = [];
  for (let fam = 0; fam < FAMS; fam++) {
    const base = w.base[fam], n = w.counts[fam];
    total += n;
    for (let k = 0; k < n; k++) {
      const cur = E.getWeight(id, fam, k), b = base[k];
      // A weight mutated to zero is a deletion: real, and off the log scale. Charge it
      // as 6 doublings -- larger than any plausible surviving ratio, finite in sums.
      let l;
      if (b > 0 && cur > 0) l = Math.log2(cur / b);
      else if (cur === b) l = 0;
      else l = cur === 0 ? -6 : 6;
      const a = Math.abs(l);
      if (a <= 0.01) continue;
      moved++; sum += a; if (a > max) max = a;
      for (const e of w.endpoints(fam, k)) per[e] += a;
      if (top.length < topN || a > Math.abs(top[top.length - 1].log2)) {
        top.push({ fam, k, log2: l, name: w.nameOf(fam, k) });
        top.sort((x, y) => Math.abs(y.log2) - Math.abs(x.log2));
        if (top.length > topN) top.pop();
      }
    }
  }
  return { moved, total, meanLog2: moved ? sum / moved : 0, maxLog2: max,
           top, perNeuron: per };
}

/* The most-drifted loci touching one neuron -- the hover story. A scan, not an index:
 * 3,935 comparisons per tooltip is nothing, and an index would be one more thing that
 * can go stale. */
export function neuronTopSynapses(E, id, w, neuron, topN = 3) {
  if (!E.hasOwnWeights(id)) return [];
  const out = [];
  for (let fam = 0; fam < FAMS; fam++) {
    const base = w.base[fam], n = w.counts[fam];
    for (let k = 0; k < n; k++) {
      if (!w.endpoints(fam, k).includes(neuron)) continue;
      const cur = E.getWeight(id, fam, k), b = base[k];
      if (!(b > 0)) continue;
      const l = cur > 0 ? Math.log2(cur / b) : -6;
      if (Math.abs(l) <= 0.01) continue;
      out.push({ fam, k, log2: l, name: w.nameOf(fam, k) });
    }
  }
  out.sort((x, y) => Math.abs(y.log2) - Math.abs(x.log2));
  return out.slice(0, topN);
}

/* One report line for a population -- the node drivers' summary. */
export function driftLine(E, ids, w) {
  const ds = ids.map((id) => driftOf(E, id, w)).filter(Boolean);
  if (!ds.length) return 'wiring: wild-type everywhere';
  const moved = ds.reduce((a, d) => a + d.moved, 0) / ds.length;
  const mean = ds.reduce((a, d) => a + d.meanLog2, 0) / ds.length;
  const champ = ds.flatMap((d) => d.top)
    .sort((x, y) => Math.abs(y.log2) - Math.abs(x.log2))[0];
  return `wiring: ${ds.length} carriers, ${moved.toFixed(1)}/${ds[0].total} loci moved, `
    + `mean |log2| ${mean.toFixed(3)}`
    + (champ ? `, top ${champ.name} ×${Math.pow(2, champ.log2).toFixed(2)}` : '');
}
