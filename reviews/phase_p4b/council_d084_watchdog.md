# Council D-084 (watchdog): NAT continuation down the same frozen snapshot

Reviewed d084_draft.md, 09c561e, 2f8102f (no sealed data/labels/transcripts/predictions read). `pytest tests/test_nat_d084.py tests/test_guards_frozen_config.py`: 34 passed.
Verdict: **REVISE** (one blocking item, a text fix only; the code is acceptable as drafted).
## Judgement
- **Outcome-blindness.** Only the stopping rule is post hoc. Rules, thresholds, models, pins and snapshot order stay
  frozen, and the owner turned down relaxation and other sources. Acceptable, given the §0/§3 disclosure.
- **max_sessions = 6 chosen after seeing 4/40: acceptable.** The cap decides only whether we STOP. It cannot change
  which clips are selected: the selection is always the first 15 passes by CPU rank over a fully evaluated prefix.
  At p = 0.10, P(< 11 more passes in 240) is negligible, so the cap is a cost ceiling, not a tuning knob. The
  disclosure is honest.
- **Invariance to session boundaries.** It holds by construction. Buffers are consecutive 40-blocks, every k >= 1
  is evaluated in full, and session 0 evaluated all 40. `nat_selection` fails closed on duplicates, aliens and
  gaps. The tests cover a re-split and reversed row order.
- **Launch rules.** They are unchanged and applied per k: frozen-key check (+ refclips_d084), limits, terminator
  window, pushed CI-green HEAD, L4 reconcile, CPU log sha, one instance, baseline, then the cap guard. Distinct
  ledger and run names nat{k}. Sequencing (0..k-1 logged, k not), overlap and short-buffer refusals are tested.
- **CPU stage.** `check_cpu_target` caps it at one buffer ahead, within max_sessions, while the selection is
  incomplete. Tests are adequate (incl. a real-log check that only buffer 1 is allowed now).
## Blocking
1. **§2.6 misstates the cost bound.** "Six sessions cost at most about $2.4 actual" is the expected cost, not a
   bound. The enforced worst case per session is max_hours x price = $3.48 (the terminator and usd-limit bound
   it), so 6 x $3.48 ≈ $20.9. Next to the ~$63 projection, that exceeds the $75 cap. `guard_launch` checks only
   spend + this launch, not the rest of the campaign. Fix: state the worst case, and require the D-071 (k)
   campaign projection (spend + remaining P4b plan) to be re-stated in each session's pre-launch record. If the
   projection exceeds $75, STOP to the owner rather than letting NAT sessions eat the main campaign's headroom.
## Non-blocking
- `_finish_k` "failed" path (post-GPU error, rows not logged): add a line saying session k is not re-run without
  a council note, because a re-run would re-evaluate a buffer whose GPU output already exists. §3: disclose
  that the NAT clips may come from several pods/sessions (same pins, same rules).
