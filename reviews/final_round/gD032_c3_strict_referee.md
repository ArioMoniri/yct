# G-D032 cycle 3 — Strict Referee (fresh, adversarial)

**Scope.** Reviewed at 31235e6 (CI run 55 green); data/sealed/ not opened. Re-ran the Q-rule, firewall, T3 and manifest tests: 62 passed.

## Verdict: GO

The T3 rules, localisation firewall and D-037 Q rule are sound and tested. The remaining items are bookkeeping or D-047 spill-over. They must close before the P3 M0 freeze. None warrants escalation.

## Prior required changes (cycle 2)

1. **v2.md/config `m0:` match the governing rule — FIXED** (superseded by D-037).
   - Q rule text: v2.md:64–70; config.yaml:189–203.
   - "No PCA" is stated at v2.md:64 and :81.
2. **"Beyond M0" wording — FIXED.** v2.md:16–17.
3. **Q implemented; FPR rerun on the new Q — DEFERRED-OK.**
   - `m0.q_m0` and `h4_null_sim` are implemented (D-041).
   - The final-N FPR rerun is a P5b item (v2.md:430).
4. **Remedy "never reduce Q" — FIXED.** v2.md:430; ROADMAP.md:168.
5. **BUG-003 as a hard P4 prerequisite — FIXED.**
   - Text: v2.md:390; ROADMAP.md:121.
   - Code: offline.py:30,82; run_clip.py:52,84.
   - Run: p0rel_20261117T163701Z "Offline / pins".
6. **ENHANCEMENTS.md deferral line — NOT FIXED.** ENHANCEMENTS.md:6 still says "Proposal for council at G-D032".

## New defects

**N1. The Q dimension table is stale.**
- v2.md:70 and `q_dimension_table(n_era_levels=3)` (m0.py:410–420) assume 9 continuous features + `voiced_any` + 3 eras.
- Two things have changed since:
  - era now has 2 levels (E12/E3; config.yaml:32–38);
  - v2.md:104 declares `platform_nonYT`, `upload_lag_days` and `lag_unknown` "forced linear M0 covariates".
- None of the three is in config `m0.features`/`binary` (config.yaml:175–186).
- Recomputed at N = 53: 1+9+1+1+3+3 = 18 > ⌊53/3⌋ = 17. A merge is forced where the table says none.
- For the YouTube-only analysis (N = 46, limit 15), 2 merges are needed.
- As written, the prereg would print a wrong Q.

**N2. The label-proxy logic is inconsistent.**
- v2.md:101 bars route r from M0 because it "would put a label proxy into AUC(M0)".
- Yet `upload_lag_days` is forced into M0 (v2.md:104), although it is plausibly outcome-caused (post-decision uploads).
- v2.md:17 still says "measured stimulus features". Platform and lag are metadata.

**N3. The T3 H1 survival rule is ambiguous.**
- v2.md:132 says "p < .05 … judged per network". It does not say whether that p is raw or maxT-adjusted.
- T1 H1 is maxT-adjusted (v2.md:82).

**Searched, found nothing further:** caption (v2.md:141), lint list, T3 reuse (v2.md:130), medial-wall counts (v2.md:40).

## Required changes

1. Append "ENH-003 DEFERRED (G-D032, D-034)" to ENHANCEMENTS.md.
2. Put the D-047 covariates in `m0:`, or drop them by a DECISIONS entry (see 4).
3. Make `q_dimension_table` read era levels and binaries from config. Reprint v2.md:70 for N = 46/50/53.
4. Resolve N2 by a DECISIONS entry. Either:
   - (a) keep lag out of M0 and add a pre-decision-upload-only sensitivity; or
   - (b) keep it, and reword v2.md:17/:101 as "stimulus features and upload metadata (possibly outcome-caused)".
5. In v2.md:132, use the maxT-adjusted T3 p (same B, same seeds).
