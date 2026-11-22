# Council D-084: neuro member

Verdict: **APPROVE** (no blocking items).

Read: d084_draft.md, `git show 09c561e 2f8102f`. tests/test_nat_d084.py: 24 passed. I did not read sealed data,
labels, transcripts, outputs/ predictions or the contents of the NAT log.

## Judgement
- **Outcome-blindness.** The outcome seen was a QC pass rate (4/40), not any encoding or brain-model result. The
  frozen rules (C1/T58/C4/P2, N1/N2/N3, thresholds, pins) and the snapshot order are unchanged. The continuation
  only takes more draws from the same pre-registered stream, so no clip-level criterion was tuned on the outcome.
- **max_sessions 6, chosen after seeing 4/40.** Acceptable. Membership is "first nat_n passes by CPU rank", and
  every buffer is evaluated in full, so any max_sessions large enough to reach 15 gives the identical set.
  The value only decides whether the run ends selected or STOPs, and it caps spend. It cannot steer which clips
  are selected. It is disclosed as a ceiling, not a target. That is enough.
- **Stimulus exchangeability.** The order is ascending sha256(title), which is pseudo-random with respect to
  content. Later buffers are therefore exchangeable with buffer 0: going deeper adds no drift in speaker, topic
  or recording era. This is the property that matters for the NAT control.
- **Invariance to session boundaries.** It holds by construction: the evaluated set is a contiguous prefix, each
  buffer is evaluated in full, and selection is by rank. Tests cover it (split [40,60)+[60,120) vs 40-blocks, and
  reversed row order). The fail-closed checks for duplicates, gaps and non-CPU ids are correct. Session 0's
  4 passes keep their ranks.
- **Launch rules and cost.** D-071 (k) is unchanged for every session. The k-sequence, buffer-complete, overlap
  and d084-frozen refusals all sit before launch. The per-launch cap guard runs against the ledger. About $0.4
  actual per session against $75 is immaterial.
- **Disclosure (§3).** Adequate: post hoc status, per-session N1/N2/N3 counts, CPU rank span, and the yield
  caveat for the pool.

## Non-blocking
- `test_session_k_refused_on_overlap` matches on "already evaluated" OR "not logged". Its session-9 row trips
  the sequence check first, so the overlap branch is never exercised. Add a case with sessions 0..k-1 logged
  and one buffer-k id already present.
- The v1 report should state that only N3 (face) is evaluated on N1/N2 passes, so the per-session N3 counts
  are conditional counts. This matters when the yield is read as a property of the pool.
- In the v1 report, give the planned cap-guard total for 6 sessions (6 x $3.48) next to the actual cost.
