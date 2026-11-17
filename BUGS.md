# BUGS

Append-only log. Format: date | phase | id | summary | evidence.
- BUG-001 | P0 | orchestrator edited an existing DECISIONS.md line (commit 8005ceb) | reverted next commit | evidence: git show 8005ceb -- DECISIONS.md. Root cause: sed on log file; guard: check_append_only.py in CI (P0).
- BUG-002 | P2b/P4 (T2 only) | CRITICAL upstream: TRIBE chunk-2 word times shifted +120 s and duplicated for clips >60 s (tribev2 PR #29/#81 unmerged, eventstransforms.py l.205) | T1 (58 s) unaffected | fix: build absolute-time Word events ourselves or vendor #81 patch + regression test before any T2 run. Source: docs/tribe_known_issues.md
- BUG-003 | P0 | MAJOR upstream: from_pretrained ignores revision, backbones unpinned | fix: snapshot_download at pinned revisions + HF_HUB_OFFLINE=1 + no-network test
- BUG-004 | P5/P9 | MAJOR upstream: HCP helper keeps medial-wall '???' as a region; top-k helper crashes hemi="both" (PR #30) | fix: own labelling (src/yct/interpret/localize.py), drop '???'
- BUG-005 | P1 | Watchdog G-D032: data/curation/search_log.csv contains per-query outcome-labelled counts outside data/sealed/ (blinding) | untracked from git now; Curator to move outcome-labelled columns to data/sealed/ and commit a sanitized log. Already present in git history (commits before 9921d72) — counts per query only, no per-video labels.
- BUG-006 | P0/P4 | Determinism FAIL: two fresh-cache TRIBE runs differ max 3.57e-3 (r=0.999994), run smoke_20261117T142354Z; prediction from cached features is bit-identical (0.0) → nondeterminism is in GPU backbone feature extraction (fp16). Fix (design, not tolerance change): extract features exactly once per input sha256, store + hash them, all predictions/ablations/reruns read the cache; determinism test = cached-feature rerun ≤1e-4 (exact) plus a reported (not gated) fresh-extraction drift. Requires QA vote at P0 gate.
- BUG-007 | P0 | CI red: ruff fails in src/yct/tribe_run/*.py (E702) so Tests/Guards never ran in CI on 529652d/e9b891c (Watchdog G-D032).
- BUG-008 | P0 | tests/_atlas.py:17 adds pytest.skip without ticket → check_test_weakening rc=1; offline CI would silently skip atlas tests (Watchdog G-D032).
