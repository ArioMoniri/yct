# D-084 draft: NAT continuation sessions down the same frozen snapshot (post hoc)

Status: DRAFT for the council. Not in DECISIONS, not frozen. The CPU stage for buffer 1 runs under the
frozen D-075 CPU rules, which this draft does not change. GPU session 1 is refused by the driver until
`controls.refclips_d084` is frozen.

## 0. Trigger and owner decision

- NAT session 0 (D-075 §3, run `p4bnat0_1795336302`, 2026-11-22 08:31Z) stopped under the frozen rule: 4 of
  40 passes, below `nat_n` 15. The 36 rejects were N1 18, N2 12 and N3 6. All 40 rows are logged.
- On the STOP the owner chose (AskUserQuestion, 2026-11-22) "Continue same list": the same frozen rules
  (CPU filters, N1/N2/N3 thresholds, snapshot order), continuing down the frozen 1000-entry NAT snapshot
  from where the CPU stage stopped, with further short GPU sessions until there are 15 passes.
- **Post-hoc disclosure:** this rule was chosen after the session-0 outcome was seen. The v1 report states
  this and gives the per-session counts. Session 0's rule (D-075 §3) is unchanged and its 40 rows stand.

## 1. What does not change

- The NAT snapshot (`nat_snapshot_sha256`, frozen) and its order, ascending sha256(title).
- Every CPU rule (C1 licence, T58 too_short, C4 yc_link, P2 too_short after trim) and every GPU rule:
  - N1: faster-whisper p(en) ≥ 0.9 on [0, 30 s).
  - N2: pyannote 3.1, main speaker ≥ 95%, others ≤ 3 s, no-speech rejected.
  - N3: face_present_crop over W ≥ 0.5, computed only for N1/N2 passes.
  - Thresholds, models, pins (D-082) and reject reasons are unchanged.
- `nat_n` 15, `cpu_buffer` 40, the $75 campaign cap, and the D-071 (k) launch rules for every session:
  - `--max-hours ≤ 1.75` and `--usd-limit 8`;
  - an external terminator re-armed per session at deadline + 900 s … + 3600 s, never reusing a fire time;
  - the dead-man switch and exit-code semantics;
  - launch only from a pushed, CI-green commit;
  - L4 ledger reconciliation before each launch;
  - one instance at a time.

## 2. Continuation rule (fixed now, outcome-blind from here on)

1. **Buffers.** Buffer k is CPU passes [40k, 40k+40) in NAT-log order. The log is a prefix of the snapshot
   order (`check_prefix`), so buffer 0 is the session-0 buffer.
   - The CPU stage fills buffers in order. It is never more than one buffer ahead of the evaluated sessions
     (`cpu_ahead_max` 1, `natstim.check_cpu_target`).
   - The CPU stage stops once the selection is complete.
2. **Session k ≥ 1.** The driver is `scripts/gpu_p4b_nat0.py --session k`. It refuses unless:
   - `controls.refclips_d084` is frozen;
   - sessions 0..k−1 are logged and k is not;
   - k ≤ `max_sessions`;
   - the selection is still incomplete;
   - buffer k is complete: exactly 40 passes, or a short last buffer with the logged `snapshot_exhausted`
     record;
   - none of buffer k's ids has been evaluated before.
3. **Full evaluation.** Each continuation session evaluates every id in its buffer, with no early stop at
   15. All rows are logged as `stage: session, session: k`.
4. **Selection.** The NAT set is the first `nat_n` passes by CPU rank, taken over all evaluated rows
   (session 0 and k ≥ 1).
   - Because buffers are consecutive blocks and are evaluated in full, the selected set does not depend on
     where session boundaries fall (tested).
   - Session 0 stopped at nat_n only in the fail case; here it evaluated all 40. Its 4 passes keep their
     CPU ranks (12, 28, 31 and 34, 0-based, among the 40 CPU passes) and therefore their place in the
     selection.
   - Fail-closed: an id evaluated twice, an evaluated id that is not a CPU pass, or a gap in the evaluated
     prefix is a STOP.
5. **After each session.** Passes are counted cumulatively, by CPU rank:
   - ≥ 15: selected. The NAT manifest is the first 15, and the NAT manifest sha is then set and frozen
     (two commits).
   - < 15 and k < `max_sessions` and snapshot not exhausted: fill buffer k+1 on CPU, then session k+1.
   - < 15 and (k = `max_sessions` or snapshot exhausted): STOP to the owner. There is no relaxation and no
     other source.
6. **Hard limits.**
   - `max_sessions` = 6 continuation sessions, up to 240 more GPU-evaluated candidates.
   - The snapshot holds 1000 entries; 68 have been evaluated on CPU.
   - All sessions count toward the $75 cap. Each is about 12 min on one A100, about $0.4 actual and $3.48
     planned in the cap guard.
   - Six sessions cost at most about $2.4 actual, beside a projected ~$63 for the full P4b campaign.
   - The value 6 was chosen after seeing 4/40 (a 10% GPU pass rate): 240 candidates at that rate give an
     expected 24 passes. That is disclosed, and it is a ceiling, not a target.

## 3. Disclosure in the v1 report

- That the rule is post hoc (§0).
- Per-session evaluated / pass counts and N1/N2/N3 reject counts.
- The CPU rank range the 15 selected clips span.
- The early CPU rehearsal (3 clips, outcome-exposed, CPU int8), as already disclosed under D-082.
- The NAT control's reliance on a low-yield public-domain lecture/talk pool: English single-speaker
  face-present clips are a minority of it.

## 4. Code (TDD; tests/test_nat_d084.py)

- `natstim`:
  - `cpu_passes`;
  - `buffer_ids(log, cfg, k)` and `buffer_complete(log, cfg, k)`; k = 0 is the default, so session 0 is
    unchanged;
  - `session_rows(k, …)`, which evaluates the full buffer and requires k ≥ 1;
  - `gpu_rows`, `sessions_logged`, `nat_selection` (cumulative, fail-closed) and `check_cpu_target`;
  - `run_cpu(..., n_buffers)`;
  - `nat_manifest`, which now uses `nat_selection` and records each row's session.
- `scripts/gpu_p4b_nat0.py`:
  - `--session k`;
  - `check_frozen(cfg, k)`, which adds `controls.refclips_d084` for k ≥ 1;
  - `check_session_k`;
  - `_finish_k`, with statuses selected (0), next_buffer (0) and stop (1);
  - ledger name `yct-p4b-ref-nat{k}`, run directory `p4bnat{k}_<t>`.
- `scripts/natstim_cpu_run.py run SCRATCH --buffers K`.
- `config.yaml controls.refclips_d084`, schema `RefClipsD084`. It is frozen in a later commit after council
  sign-off, with its expected row in `tests/test_guards_frozen_config.py`.
- A pod CPU rehearsal is not repeated. The box path (ship list, steps, offline pyannote) is unchanged from
  the one rehearsed and launched at e1a0f66. Only the driver's buffer index and post-session bookkeeping
  differ, and the dry tests cover them.
