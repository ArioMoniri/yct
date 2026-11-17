# Phase 0 gate packet (artifact list only)
Commit: b140dd6. CI run 21 success (link above in reviews/gate_D032/cycle2_packet.md).
- Smoke test: outputs/runs/smoke_20261117T142354Z/ (smoke_report.md, metrics.json, latency CSVs); docs/tribe_requirements.md §10 "Measured in P0".
- Determinism: BUG-006 (fresh-extraction drift 3.57e-3; cached-feature rerun 0.0) + design fix src/yct/tribe_run/feature_cache.py and tests (CPU, mocked; GPU re-run not yet done).
- Guards/CI: scripts/check_*.py, .github/workflows/ci.yml, Makefile, requirements.lock, config.yaml guards:.
- Infra: infra/lambda_gpu.py (+ heartbeat/reap), infra/gpu_ledger.jsonl (spent $0.77), src/yct/owner_actions.py (SSM owner actions, D-030), DATA_DECISION.md.
- Known issues: docs/tribe_known_issues.md; ENH-004 (A10 allowed? peak VRAM 13.4 GB).
ROADMAP P0 DoD: CI green; smoke run dir with VRAM/runtime/TR/latency; tribe_requirements UNVERIFIED resolved or ticketed.
