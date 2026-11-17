# Phase 1 (wave 1) — Strict Scientific Referee (fresh)
fd08ad9; manifest sha256 = D-045 (verified). Sealed data not opened. **Vote: FIX.** P2 download may start after D1–D4 are done. P1 stays open until D5–D7 are done.

## Defects
**D1. Blinding/DPIA breach.** D-045 and the packet name a company together with its outcome ("FireJet = 4 rejected cycles"). That unblinds yct_0641–0643 and breaks DATA_DECISION §3. `company_id` is also the plain company name. Required:
- add a superseding D-entry in pseudonymous wording;
- hash `company_id` with a salt;
- log the breach in BUGS;
- add a sensitivity analysis without those rows.

**D2. Count mismatch.** The manifest has 3 FireJet rows, not 4. There are 56 unique companies, so one-per-company gives 30/26, not 30/25. The Curator must reconcile against the sealed files and report totals only.

**D3. Platform and upload timing are plausibly outcome-correlated.** Primary rows are YouTube 51, LinkedIn 6, web 1. All 7 non-YouTube rows were posted 87–1,535 days after the decision, and 21 of 43 dated rows overall were uploaded after the decision. LinkedIn also re-encodes video (lower bitrate, square or vertical frames), which shifts the photometric, motion and cut features and the crop. Required before lock:
- (a) add forced M0 covariates `platform_nonYT` and `upload_lag_days`, both label-free (UNKNOWN imputed and flagged);
- (b) add a YouTube-only sensitivity analysis;
- (c) in P2, re-encode all sources to a common CFR, resolution and audio rate, and log source bitrate, resolution, fps and codec as confounds;
- (d) the Curator writes a sealed platform × label table; only a "cell < 3" flag is released.

**D4. The "keyword_search" route is not outcome-neutral.** 151 of 814 queries contain outcome terms ("rejected", "didn't get in", "got in"), so the D-035 same-route sensitivity is still contaminated. Required:
- seal the class of each row's first-hit query: OUTCOME-TERM / NEUTRAL / DIRECTORY / PLAYLIST / COMMUNITY;
- run the sensitivity on NEUTRAL rows only;
- add the D-040 opaque block-code column to the manifest (it is missing).

**D5. `is_original_application_video` carries no information.** It is "true" for all 661 rows and was never verified by watching. 16 primary rows run over 75 s and 7 over 90 s, and post-decision uploads may be re-cuts. Required in P2:
- check each row against a written rubric: submitted cut / re-edit / compilation;
- exclude anything that is not the submitted cut;
- add a duration > 75 s sensitivity analysis.

**D6. The era split is degenerate for blocking.** E1 = 3, E2 = 7, E3 = 48. Merge E1 and E2 into "pre-S2020" using a label-free rule fixed now, and report effective N per block.

**D7. ROADMAP P1 tasks and tests are absent.** Missing:
- verify_labels.py and the A-rule recompute;
- the evidence-snapshot and quote tests;
- the manifest-schema test;
- the pilot-hash exclusion;
- the perceptual-hash and audio-fingerprint duplicate checks (cross-platform);
- the within-company pair file.

P1 cannot close without them.

**Exclusions (sane).** The totals reconcile, nothing overlaps the manifest, and there are no duplicate URLs. 59 are unavailable or private, so links are rotting: download promptly.

## Adequacy and MDE
n = 30/26 after the seeded one-per-company pick.
- Single test, two-sided α = .05, 80% power: d ≈ 0.76 (AUC ≈ 0.70).
- With Holm over 7 networks: d ≈ 0.95.
- Null-AUC SE is about 0.078, so the 95% CI is about ±0.15.
- H4 needs d ≳ 1.06 beyond M0.

This is adequate only as an exploratory, estimation-first wave. The prereg must print these MDEs and state that wave-1 nulls cannot rule out realistic effects (AUC 0.52–0.60).

## Blind κ ≥ 0.9 procedure
1. Commit `kappa_sample.py`. It selects 15% of rows by sha256(video_id + committed salt), stratified by confidence tier, with at least 15 conf-A rows; it uses label-free inputs only.
2. Run a disposable re-derivation agent on the pod under its own IAM role. It sees only URLs and evidence snapshots, never the original labels, and is never reused. Its output and transcript are age-encrypted to the owner.
3. The owner runs the committed, synthetically tested `kappa_check.py`. It prints only n, κ (outcome), κ (A vs not-A) and the IDs that disagree.
4. Report the conf-A κ separately. The owner adjudicates any disagreement, logged and sealed.
5. The owner's 10-row spot-check is still pending and is separate from this.
