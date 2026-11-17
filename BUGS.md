# BUGS

Append-only log. Format: date | phase | id | summary | evidence.
- BUG-001 | P0 | orchestrator edited an existing DECISIONS.md line (commit 8005ceb) | reverted next commit | evidence: git show 8005ceb -- DECISIONS.md. Root cause: sed on log file; guard: check_append_only.py in CI (P0).
- BUG-002 | P2b/P4 (T2 only) | CRITICAL upstream: TRIBE chunk-2 word times shifted +120 s and duplicated for clips >60 s (tribev2 PR #29/#81 unmerged, eventstransforms.py l.205) | T1 (58 s) unaffected | fix: build absolute-time Word events ourselves or vendor #81 patch + regression test before any T2 run. Source: docs/tribe_known_issues.md
- BUG-003 | P0 | MAJOR upstream: from_pretrained ignores revision, backbones unpinned | fix: snapshot_download at pinned revisions + HF_HUB_OFFLINE=1 + no-network test
- BUG-004 | P5/P9 | MAJOR upstream: HCP helper keeps medial-wall '???' as a region; top-k helper crashes hemi="both" (PR #30) | fix: own labelling (src/yct/interpret/localize.py), drop '???'
