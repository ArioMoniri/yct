# Council D-084 — QA review (draft d084_draft.md; commits 09c561e tests-first, 2f8102f impl)

Verdict: **APPROVE** (no blocking items).

## Checks run
- `pytest -q tests/test_nat_d084.py tests/test_gpu_p4b_nat0.py tests/test_nat0_council_d082.py`: 66 passed.
- `make guards`: exit 0 (no test weakening; guard config unchanged/QA-approved).
- TDD order holds: tests commit 09c561e precedes impl 2f8102f. No sealed data, labels or predictions read.

## Judgement
- Outcome-blindness: the continuation changes no CPU/N1/N2/N3 rule, threshold, model or snapshot order.
  Selection = first nat_n passes by CPU rank over all evaluated rows; which clips are chosen is fixed by
  the frozen order and rules, not by the 4/40 outcome. Session 0's 40 rows stand unchanged.
- max_sessions 6 chosen after seeing 4/40: acceptable. It only bounds when we STOP to the owner, never
  which clips are selected; it is disclosed (draft §2.6, config `post_hoc: true`) and is a ceiling, not a
  target. Must be frozen (with its test_guards_frozen_config row) before session 1, as the driver enforces.
- Session-boundary invariance: buffers are consecutive 40-blocks evaluated in full (no early stop), so the
  evaluated set is always a CPU-pass prefix and the selection cannot depend on boundaries; tested
  (test_selection_invariant_to_session_boundaries). Fail-closed on duplicates, non-CPU-pass ids and gaps.
- Sequencing: check_session_k refuses re-run, skipped session, k > max_sessions, complete selection,
  short buffer without snapshot_exhausted, overlap; check_cpu_target keeps CPU <= 1 buffer ahead. All tested.
- Launch rules: preflight path unchanged for k >= 1 (limits 1.75 h / $8, per-session re-armed terminator
  with no reused fire time, pushed CI-green commit, L4 reconcile, one instance, baseline + cap guard).
- Cost: <= 6 x ~$3.48 planned (~$0.4 actual) within the $75 cap, guarded per session.
- Disclosure (§3) is adequate: post hoc, per-session counts and reject reasons, CPU rank span, rehearsal.

## Non-blocking notes
- A crash mid-append in `_finish_k` leaves a partial session k; later sessions then fail closed (gap),
  which is safe but needs a human repair path — worth one sentence in the runbook.
- v1 report should state the planned-vs-actual cap accounting for the continuation sessions.
