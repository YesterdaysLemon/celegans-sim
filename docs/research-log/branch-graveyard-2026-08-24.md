# The branch graveyard, 2026-08-24

Forty-three stale branches deleted in one hygiene sweep, at the owner's direction.
Every open PR had already been dispositioned (the fresh-slate audit closed each with
reasons; #174 closed today as superseded by #175). Squash merges mean git ancestry
cannot certify what landed, so the tip of every deleted branch is recorded here --
a dangling commit stays fetchable by SHA, and any branch that ever carried a PR is
additionally pinned by that PR's refs forever.

| branch | tip |
|---|---|
| ci-gate-at-jobs | 8a12bf5 |
| ci-manual-only | 4aae3ee |
| claude/agitated-boyd-99faaf | 4252463 |
| claude/ci-trigger-policy | 815a53d |
| claude/depleted-lawns-src | cb19b6c |
| claude/egglaying-euler | 5495c07 |
| claude/energy-fitness | 9c71e39 |
| claude/evolution-loop | 72c12dd |
| claude/expm1-rates | 3e21877 |
| claude/exporter-validation | 6e5b798 |
| claude/focus-clamp | 23c2ca6 |
| claude/genetic-evolution-audit-hgqtp5 | 68973b6 |
| claude/heading-convention | f62bdba |
| claude/heuristic-swanson-eef0d9 | cd6f416 |
| claude/medium-state | ae09fea |
| claude/multi-animal-conformance | 10d7b9e |
| claude/nginx-mime | 7e70769 |
| claude/per-worm-ablation | 8f4407c |
| claude/repo-architecture-investigation-w43stj | cf5fdb9 |
| claude/repo-overview-options-hdcg0y | 8a015f5 |
| claude/runtime-fair-feeding | ab7980c |
| claude/scratch-hoist | 6944dba |
| claude/server-transport | a406c6d |
| claude/sim-rate | 66e96d9 |
| claude/skater-hunt | 910061d |
| codex/issues-38-39-python-runtime | 41f80ab |
| codex/issues-40-41-genome-cache | cc2ed2d |
| codex/issues-49-57-audit-safety | 247ca7d |
| codex/issues-50-54-55-repro-tests | 48e92ee |
| codex/managed-production-deploy | 709dd91 |
| codex/portfolio-backlink | 8d3413d |
| command-layer-diagnosis | 2567083 |
| converge-the-integrator | e429efa |
| differential-repellent | 6baf458 |
| evolved-not-celegans | e4e1ce7 |
| head-circuit | 695f7be |
| record-evolution-decisions | dcab3e2 |
| runtime-invariants | f771473 |
| self-avoidance | 7eab781 |
| self-contact-audit | 3ff2f95 |
| turn-frontier-caveats | 40fefc8 |
| turn-moment-ceiling | 54279a6 |
| viewer-quality | b648b19 |

## Deleting them

This session's git proxy scopes pushes to its own branch, so the deletions themselves
need the owner's credentials. One paste:

```
git push origin --delete ci-gate-at-jobs ci-manual-only claude/agitated-boyd-99faaf claude/ci-trigger-policy claude/depleted-lawns-src claude/egglaying-euler claude/energy-fitness claude/evolution-loop claude/expm1-rates claude/exporter-validation claude/focus-clamp claude/genetic-evolution-audit-hgqtp5 claude/heading-convention claude/heuristic-swanson-eef0d9 claude/medium-state claude/multi-animal-conformance claude/nginx-mime claude/per-worm-ablation claude/repo-architecture-investigation-w43stj claude/repo-overview-options-hdcg0y claude/runtime-fair-feeding claude/scratch-hoist claude/server-transport claude/sim-rate claude/skater-hunt codex/issues-38-39-python-runtime codex/issues-40-41-genome-cache codex/issues-49-57-audit-safety codex/issues-50-54-55-repro-tests codex/managed-production-deploy codex/portfolio-backlink command-layer-diagnosis converge-the-integrator differential-repellent evolved-not-celegans head-circuit record-evolution-decisions runtime-invariants self-avoidance self-contact-audit turn-frontier-caveats turn-moment-ceiling viewer-quality
```
