# Council D-084, referee: APPROVE (no blocking items)
Reviewed `reviews/phase_p4b/d084_draft.md`, 09c561e (tests) and 2f8102f (code/config). Read only the session-0 run
dir `outputs/runs/p4bnat0_1795336302/` (STOP_NOTE, child_metrics). `tests/test_nat_d084.py` + frozen-config guards: 34 passed.

1. **Outcome-blindness / pre-specification.** The rule is post hoc, which is disclosed in §0, §3, the config (`post_hoc: true`) and the
   schema (`Literal[True]`). The only thing seen was a filter yield (4/40), not any study outcome. The rule changes how far down a frozen
   ordered list the evaluation goes. It does not change which candidates qualify or how they are ranked. **`max_sessions` 6 chosen
   after 4/40 is acceptable:** it is a stop ceiling, not a selection criterion. Because the set is "first 15 passes by CPU rank", any
   ceiling that is reached gives the same 15 clips as an unbounded continuation. A value set from the yield can only affect whether
   the run STOPs to the owner, not what is selected. At p≈0.10, 240 candidates make 11 more passes very likely (expected ≈24).
2. **Invariance to session boundaries.** Holds. Buffers are consecutive blocks of CPU passes, every continuation buffer is
   evaluated in full, and session 0 evaluated all 40 (its early stop never fired; STOP_NOTE confirms 40 rows). `nat_selection`
   requires the evaluated set to be a gapless prefix of CPU ranks, rejects duplicates and ids that are not CPU passes, and sorts by rank.
   The result equals sequential one-by-one evaluation stopped at the 15th pass. `test_selection_invariant_to_session_boundaries` covers this.
3. **Launch rules.** These are unchanged and enforced for k ≥ 1: `check_frozen(cfg, k)` adds the `refclips_d084` freeze, and limits,
   the terminator window, pushed + CI-green, L4 reconcile, the CPU-stage check and one-instance all run through the same `preflight`.
   `check_session_k` enforces the order 0..k−1, k ≤ max, an incomplete selection, a complete buffer and no overlap, each with a test.
4. **Cost cap.** `ref_campaign` checks actual ledger spend + planned (1.99 $/h × 1.75 h = $3.48) ≤ $75 before every session, so the cap
   is enforced per launch and is not a forecast. The worst case is about $2.4 actual for six sessions.
5. **CPU look-ahead.** `check_cpu_target` keeps the CPU stage at most one buffer ahead and within max_sessions, and refuses once the
   selection is complete. No GPU-side outcome can choose which CPU rows are filled.

Non-blocking (fix when convenient):
- N1. In `_finish_k`, the call `ns.nat_selection(log, cfg)` comes after the rows are appended and is not wrapped. A StopError there
  exits by traceback, without `res` status. Catch it as `status=failed`, exit 1, so the exit-code semantics stay explicit.
- N2. In the §3 disclosure list, state explicitly that `max_sessions` 6 was set after seeing 4/40. It is in §2.6, but list it in the
  v1 report. Also re-state the updated campaign projection after each session.
- N3. If a session ends with exit 75 (box step failure), its buffer is re-run without logged rows. Disclose any such rerun in the
  per-session counts.
- N4. The freeze commit must also add the expected `controls.refclips_d084` row to `tests/test_guards_frozen_config.py`, as §4 says.
