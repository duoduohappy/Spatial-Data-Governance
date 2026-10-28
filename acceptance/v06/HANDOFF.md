# v0.6 upgrade handoff

User authorized the upgrade and selected POI delivery acceptance. Branch codex-v06-collaborative-review; local UI http://127.0.0.1:8768/ via start-v06.cmd; isolated workspace work/v06-app-v2.

Implemented local proposer/reviewer roles, optional read-only tools, four-call/one-tool-round/one-revision limits and explicit human acknowledgement. No model approval authority. Job mode/strategy migration and idempotency are tested.

Freshness scopes use explicit positive markers and disjoint dictionary enums, stable instance IDs and scope fingerprints. Unknown/empty scopes cannot pass. Source reclassification cannot close an earlier failure. UI and HTML disclose source scopes.

Actual checks: 58 tests; six frozen packs; 30 core and 33 compare probes; 15 real Chromium checks; 13 HTTP checks. Actual two-call local workbench draft was reviewed by Codex as a synthetic development case, approved through IAB without parameter edits, and validated PASS with two scope rows. This is not independent business approval.

Developer ablation: single 38/40, self-review 38/40, dual-review 37/40; tokens 19102/75824/66506. Single remains default; dual review is experimental. Failures, environment interruption and exact experiment source snapshots are retained. Experiment code predates later scope/report refinements.

Real POI pilot NOT_STARTED; no actual batches, business reviewers or human-efficiency evidence. Templates are ready. No cloud model calls occurred in this upgrade. Remote PR/CI and candidate packaging remain the engineering handoff steps at this snapshot.
