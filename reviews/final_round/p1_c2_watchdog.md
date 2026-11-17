# Watchdog: Phase 1 cycle 2
Fresh watchdog subagent, session_011NAQ1mksc4Ea1mJcrGfTSd, final-round instance.
- **Audited:** HEAD 31235e6 (cef030e plus the packet).
- **Read:** packet.md and reviews/phase_1/*.md only.
- **Not read:** data/sealed/ and scratchpad contents. I wrote no per-row values.

## VERDICT: INCIDENT + VETO
The INCIDENT is a blinding breach, rated MAJOR: it exposes a label proxy, not the labels. The VETO can be lifted quickly.

## INCIDENT
Both `outputs/runs/p0rerun_20261117T154358Z/git_diff.patch` and `outputs/runs/p0rerun_20261117T155528Z/git_diff.patch` are tracked at HEAD and were added in d1c9d84, the "seal labels" commit.
- **Contents:** each holds the pre-seal manifest diff, 628 `+` rows with header `…,label_confidence,evidence_url,discovery_method,notes`. The exclusions diff also carries `discovery_method`.
- **Join to the current manifest by URL** (counts only): 38 of the 53 wave-1 analysis rows (`in_primary & qc_pass`) match. All 38 have a route, taking 2 distinct values.
- **Why this matters:** route is outcome-correlated by design (D-035), and D-040 makes it sealed-only. The rows with the minority route therefore have inferable labels from the current tree, not only from history (BUG-012 assumed history only).
- **Not caught** because `check_blinding` scans URLs and outcome words, not column names. Root cause: `scripts/run_with_provenance.py:69`. Exposed: any agent that read `outputs/runs/` after d1c9d84.

## Prior required changes
1. **Shred the scratchpad and attest.** The substance is FIXED: the listing shows no label-bearing names. The attestation is NOT FIXED: the orchestrator did the shredding (BUG-015), and there is no owner attestation in DECISIONS.
2. **yct_0644 URL.** FIXED: `data/manifest.csv:645` reads `sealed:yct_0644`, and an outcome-word scan of the URL column finds 0 hits.
3. **Per-company outcome wording.** FIXED with a superseding note at BUGS.md:22.
4. **URL scan in check_blinding.** FIXED (`tests/test_guards_blinding.py:82`; guards report "OK blinding: 281 files"). It misses this INCIDENT.
5. **p1b .sha256 path.** FIXED: `tests/test_sealed_checksums.py` passes.
6. **Search log tracked or documented.** NOT FIXED: it is still in `.gitignore:13`, with no sanitised log and no decision. ROADMAP.md:53 still names the old path.

## BUG-017, BUG-021 and BUG-023
- **BUG-017 is adequate.**
  - `git fsck` is clean apart from 1 dangling commit.
  - I followed the `--no-hardlinks` clone rule and removed my clone with `rm -rf`.
  - `scratchpad/repair_16837/yct.git`, a full history mirror, still exists and should be removed.
- **BUG-021 is adequate for wave 1 only**, on condition that the orchestrator makes no wave-1 analysis choice.
  - The cause is still there: `scripts/owner_label_qc.sh:416-418` prints labels in the same stream as the summary.
  - The "report back only" warning comes after the labels.
- **BUG-023 is adequate:** exact fingerprints, and gitleaks finds no leaks in 78 commits. Residuals: `.gitleaksignore` is not frozen, and the AKIA-shaped probe at de7cf74:54 is not an AWS "EXAMPLE" key, so I cannot prove it is fake.

## New defects
1. The INCIDENT above.
2. **`scripts/verify_labels.py` is missing**, although §2b.4 check 2 requires it. BUG-022's needs-recheck rule is unimplemented: `git grep needs.recheck` finds only BUGS.md.
3. **Unverified flag.** All 53 rows have `is_original_application_video=true`, and none has been verified by watching. DEFERRED-OK: watch during P2, before P4.
4. **Pending owner actions, not blocking P2:** the spot-check count, and the pod's IAM read access to `/yct/owner/blocks`.

## Required changes to lift the VETO
1. `git rm` both patches and record their sha256.
2. Fix `run_with_provenance.py` so its diff excludes `data/` and `*.csv`.
3. Make `check_blinding.py` FAIL when a sealed column name (`label_confidence`, `discovery_method`, `evidence_*`, `outcome`) appears in a CSV or diff header of any tracked file, with a test.
4. Add a BUGS entry giving the exposure scope.

Separately, the owner decides on a history rewrite together with BUG-012.

Once items 1–4 are done and CI is green, P2 downloads may start: DATA_DECISION is SIGNED in SSM (v1).

Not blocking: owner shred attestation; search-log decision; `verify_labels.py` before P5; opt-in or file-only spot-check output.
