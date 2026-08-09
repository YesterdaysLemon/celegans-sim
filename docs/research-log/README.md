# Research log — the project's long-term memory

This directory is where scientific history lives. It is separate from
[`NEXT.md`](../../NEXT.md) on purpose, because the two answer different questions and
compete for the same scarce resource:

| | Question | Property it must have |
|---|---|---|
| [`NEXT.md`](../../NEXT.md) | What should we do next? | **Sparse.** Loadable into working memory in one sitting. |
| this directory | What was already tried, and what happened? | **Complete.** Nothing is removed to make a point. |

Before this split, one file did both, and the one that must stay short lost. It reached
181 kB and 2,934 lines, grew about 63% in its last seven days, and had to grow its own
"Start here" section because it could no longer be read front to back — which is the tell.

---

## How to read what is in here

**Everything here is a record of what was believed and measured at the time it was
written.** Statements in an archived document are not claims about the model as it stands
today. Some of them were retracted the same day. Some were retracted a week later. Some are
still true. The archive does not tell you which — [`README.md`](../../README.md) and
[`NEXT.md`](../../NEXT.md) do.

Read the archive to answer *"has this been tried?"* and *"why was it abandoned?"*, and read
the README to answer *"what does the model do now?"*.

### What must never happen to these files

- **Do not rewrite a historical conclusion to match a current belief.** A retraction stays a
  retraction. A failed experiment stays failed. A superseded interpretation stays where it
  was written, next to what superseded it.
- **Do not delete a negative result.** Three of this project's most expensive lessons are
  recorded as failures, and the record is why nobody re-runs them. The
  *three mechanisms tested, three failures* table in the 2026-08-04 snapshot exists
  precisely so that the cascade's phase, a shorter head lag, and muscle force-velocity are
  not re-attempted as gait-modulation fixes.
- **Do not tidy.** If a document contradicts itself because the author changed their mind
  halfway down, that contradiction is data about how the conclusion was reached.

Improving *placement and discoverability* is always allowed. Improving *content* is not.

---

## Contents

| File | Covers | Snapshot of |
|---|---|---|
| [`next-history-through-2026-08-04.md`](next-history-through-2026-08-04.md) | Roughly the project's first three weeks: the gait-modulation investigation and its two retractions, the head-cascade measurements, force-velocity, internal damping, the omega-turn ceiling, the evolution project's decided shape, the exporter rework, the egg-measure negative result, and the accumulated *things that will bite whoever picks this up* | `NEXT.md` as of commit `987129c` (2026-08-04), preserved byte-for-byte |

**Provenance of the snapshot.** It was moved with `git mv`, so `git log --follow` on it
reaches the whole history of `NEXT.md`. Its SHA-256 is
`78077ac31a7160b68cc103da0bd9f5c56b90aad9701b8e2c1713ac5bb8aa845e`, which is the SHA-256 of
`NEXT.md` at its last commit before the move. Nothing was edited in transit — not a
heading, not a retraction, not a stale line.

> Note on the stale lines it contains, since they are load-bearing evidence rather than
> defects to fix: the snapshot's *Third tier* still asks for a viewer scrubber that has
> since been built (`web/viewer/history.js`), and its *Second tier* still describes gait
> modulation in terms that its own later sections revise. Both are correct as history. They
> are examples of why an append-only roadmap stops being a roadmap.

---

## Prose references to "NEXT.md" written before 2026-08-08

About twenty source files cite `NEXT.md` as the source of a measurement, an argument or a
caution — `worm/params.py`, `wasm/evolve.mjs`, `tools/head_medium.py`,
`web/viewer/history.js` and others. Those references were written when `NEXT.md` *was* the
research log, and they point at material that now lives in this directory.

They have deliberately not been rewritten. Editing twenty files' prose to change a filename
would churn more than it clarifies, and several of those comments sit inside checked text
that other tooling reads. **Read a pre-2026-08-08 reference to "NEXT.md" as a reference to
this directory.** New references should cite the archived file, or the README, directly.

---

## Adding to the log

The smallest structure that works is the one to keep. Today that is: one snapshot file per
archival event, named for what it covers and the date it covers it through.

If and when the volume justifies it, plausible subdivisions are `measurements/`,
`experiments/` and `retractions/`. **Do not build that hierarchy before there is something
to put in it** — an empty taxonomy is a context cost with no payoff.

When `NEXT.md` next accumulates material that is history rather than intent, archive that
material here and shorten `NEXT.md` again. That is the intended lifecycle, not an
exceptional event.
