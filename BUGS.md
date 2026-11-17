# BUGS

Append-only log. Format: date | phase | id | summary | evidence.
- BUG-001 | P0 | orchestrator edited an existing DECISIONS.md line (commit 8005ceb) | reverted next commit | evidence: git show 8005ceb -- DECISIONS.md. Root cause: sed on log file; guard: check_append_only.py in CI (P0).
