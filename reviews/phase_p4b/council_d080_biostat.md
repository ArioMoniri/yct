# Council D-080: biostat review (draft d080_draft.md; commits 8148366, 4118fa2)

Verdict: REVISE (1 blocking item; the rest of the draft I can approve once it is fixed)

## Is C1 <-> C1 equivalence outcome-blind and safe?
- Yes. `audit_pair` returns `c1_equivalent` only when both sides are `reject` with reasons in the frozen `c1_reasons`. A C1 reject is excluded before C3/C5/F*/B*/P* in both logs, so the selected set and the C3 pass state are the same either way. The selection rule, order, thresholds and the first-20 rule are untouched.
- Precedence is right: flip list first (a listed title still at C1 is a STOP), then equal, then duplicate_exempt (B2), then c1_equivalent. Admissibility changes still STOP. The tests cover both directions and the flag-off case.
- The choice was made from the STOP row only (one title, two reasons). No pass/reject counts or detector output were used. Option (b) and option (a) would give the same selection, so the choice cannot bias it.
- Non-blocking: for the v2 run-1 log (same fixed client), a C1 reason change can only come from Commons drift, so equivalence there is harmless. The `audit_c1_equivalent` field records it anyway.

## Is the dry audit adequate?
- For C0-C4 and D1 it is. It runs the frozen `evaluate_image` with a download sentinel, not a re-implementation. The counts add up (948, 18, 568, 15). The flip counts match the committed list (260/108/3). would_stop = 0, and the BUG-037 title is among the 2 face c1_equivalent pairs. I recomputed the file's sha: 35bb0b95...6fe7 matches config.
- The disclosed limits are correct: no C3, no post-download rules, no Commons drift after the dry run. The frozen `lastrevid_moved` and `identity_mismatch` rules cover the drift. For post-download nondeterminism, the 6 v2 run-1 rows that reached the download all matched v1. That is weak but the only evidence there is. Disclose it as such.

## Blocking
1. The launch rule is not enforced fail-closed. `check_frozen_d080` checks only that the sha key is frozen and non-null. The runner never reads `dry_audit_file`, so a wrong file, an edited file or a non-empty `would_stop` would still launch. Fix: before rank 1, the runner (a) recomputes sha256(dry_audit_file) and requires it to equal the frozen `dry_audit_sha256`; (b) requires `would_stop == []` for every category with superseded logs and checks that each superseded log is present in `logs`; (c) has the dry-audit JSON record the code commit it ran at, and refuses to launch if `src/yct/curate/refstim*.py` or the dry-audit script changed between that commit and the run commit (otherwise re-run the dry audit before the freeze). Add one test for each refusal.

## Could anything still STOP or bias selection?
- STOP is still possible from post-download nondeterminism (235 face, 105+2 body pairs reach the download) and from Commons drift after the dry run. Both fall under frozen rules. Neither can bias selection, because v4 is allowed only for a code defect, from rank 1, and is never driven by outcomes. Launch soon after the dry run to keep drift small.

## Re-sign-off (cycle 2: d080_v2.md, c5ccdfb, e7f87c8)
Verdict: APPROVE. Blocking item 1 is fixed.
- (a) `ra.check_dry_audit` runs in `run` before rank 1 and re-hashes the file against `dry_audit_sha256`. I recomputed sha256(d080_dry_audit.json) = ca87244c...2b40. It matches config.
- (b) It STOPs on a missing category, on a superseded log that was not audited, and when `would_stop != []`. The file covers all 4 superseded logs, and would_stop = [] for face and body. The counts match §C and the cycle-1 run.
- (c) `code_commit` = c5ccdfb. The script refuses to run with uncommitted changes in the code paths, and the runner diffs `refstim*.py` plus the script against the run commit. `git diff c5ccdfb HEAD` shows no change in those paths. The audit imports only refstim, refstim_auto and yct.config, so the pathspec covers the code. There is one test for each refusal; I ran `tests/test_refstim_d080_council.py` and all 20 pass.
- `audit_revid_drift` only turns a would-be STOP into a logged and disclosed row when the revid differs from both the superseded revid and the dry-audit revid. It never selects, so it cannot bias selection.
- Non-blocking: config.yaml and the superseded logs are outside the code-path diff. Config is covered by the frozen-config checks, but no hash pins the logs. Freeze the sha (it is set, not yet frozen), and launch soon after the freeze.
