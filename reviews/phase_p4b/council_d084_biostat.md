# Council D-084: biostat review

Verdict: **APPROVE**. Nothing blocking. Reviewed d084_draft.md, 2f8102f and 09c561e (tests/test_nat_d084.py: 24 passed locally).

## Outcome-blindness and pre-specification
- The post hoc part is a stopping and continuation rule, not a selection rule. Which clips are selected depends only on the frozen snapshot order (ascending sha256(title), which is in effect a random permutation) and on the frozen per-item N1/N2/N3 decisions. Continuing is therefore equivalent to drawing a larger random sample from the same pool under the same filter. It adds no researcher degree of freedom over *which* clips enter the NAT set.
- max_sessions 6, chosen after seeing 4/40: acceptable. It changes only whether the procedure ends in "selected" or in STOP to the owner. It never changes the membership of a completed selection, and the STOP has no relaxation and no other source. The 4/40 rate has a wide 95% CI (Clopper-Pearson ~2.8-23.7%). At p = 0.05, 240 more candidates give ~12 passes against the 11 needed, so a STOP remains a live outcome. That is fine: the stop is fail-safe. §2.6 already discloses the 4/40 rationale.
- This is a curation positive-control pool, not a study outcome, so a post hoc rule here does not touch any inferential endpoint.

## Invariance to session boundaries
- Holds by construction. Buffers are consecutive blocks of the CPU-pass order, they are evaluated in full (no early stop), and `nat_selection` takes the first nat_n passes by CPU rank. It fails closed on duplicates, on non-CPU-pass ids and on gaps in the prefix. The test covers different splits and a reversed row order.
- Session 0's 4 passes (ranks 12/28/31/34) keep their place. Session 0 evaluated all 40, so the prefix condition holds (the real-log test confirms 4 selected).

## Disclosure, launch rules, cost cap
- §3 is adequate. Add to v1, non-blocking: the binomial CI on the per-session pass rate, and the final cumulative evaluated/pass ratio.
- The launch rules are unchanged and enforced through the same preflight for k >= 1. The refclips_d084 freeze is required, and runs are one at a time.
- Cost: the cap guard plans $3.48 per session, about $20.9 for 6, against ~$2.4 actual. If the planned sums ever bind before actual spend does, the guard refuses (fail-safe). Non-blocking: state the planned total next to the actual one in the draft.

## Tests (non-blocking nits)
- `test_session_k_refused_on_overlap` accepts either error message. Its session-9 row makes the "not logged" branch fire first, so the overlap branch itself is not exercised. Use a session-1 row placed before buffer 1 instead.
- `_finish_k`'s `stop` path (k = max_sessions, or snapshot exhausted with < nat_n passes, giving exit 1) has no direct test. Add one.
- Edge case: the snapshot runs out exactly at a buffer boundary. The driver then refuses "buffer empty" (exit 1) instead of logging a `stop` status. That is safe but undocumented. Add one line to §2.5.
