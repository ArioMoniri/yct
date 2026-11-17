# G-D032 cycle 2 — Strict Referee (fresh)

**Scope.** Reviewed at b83e6c2. I did not read data/sealed/ or any other cycle-2 or phase_0 review.

**Vote: FIX.** Eight of my nine cycle-1 items are resolved. D-036 is sound, but the protocol text still contradicts it. BUG-003 is still not a P4 gate.

## Cycle-1 items

| Item | Status | Evidence |
|---|---|---|
| T3 survival / reuse of T1 M0, Q, K_Q, W; outside Holm; no rescue | OK | v2.md:108–113 |
| max_gain, flags kept, by-group report | OK | config.yaml:73–74; test_photometric_t3.py:64,79,95 |
| Lossy encode, luma Y′ | OK | v2.md:102,106 |
| Caption + lint | OK | config.yaml:183–200; test_localize_firewall.py:37,52,67 |
| Peak table (standardised T1, cluster BCa, stability, BH-FDR q, unreliable) | OK | v2.md:116–118; tests :76–216 |
| Reconcile | OK by supersession | v2.md:122 |
| ENH-003 deferred | DECISIONS OK; ENHANCEMENTS.md:6 stale | — |
| words/s and speech fraction in K_Q; no-audio/<20-word exclusion; medial-wall union | OK | v2.md:34,56,59; m0.py:109,209; test_medial_wall_union.py |
| **Pinned revisions as P4 prerequisite** | **OPEN** | D3 |

## Defects

**D1. v2.md and the code contradict D-036.**
- v2.md:69 still says "Q(M0) = [1, M0, M0², products among K_Q] … No ridge and **no PCA**".
- v2.md:56, config.yaml:172 and m0.py:192–222 still use the 1/VIF K_Q.
- The governing rule is not in the protocol.

**D2. The claim wording is now false.** v2.md:12–13 still says "beyond the linear + quadratic span" / "up to quadratic terms".
- At N = 40, ⌊N/3⌋ = 13. Then 1 + 2 + j + (2 + j) + 1 ≤ 13 gives **j = 3**.
- So Q spans 3 of the ≈8 remaining M0 dimensions, their 3 squares and one product.
- The squares of PCs are not the squares of the named features.
- Linear M0 is still protected, because it enters both H4 models.
- The nonlinear "beyond" set is a small, data-derived subspace that cannot be interpreted feature-wise.
- The PCA is label-free and deterministic, so the rule is sound for leakage control, but it licenses a weaker claim.
- Also unspecified:
  - where `voiced_any` and the era dummies go;
  - whether speech_rate² and speech_fraction² are included;
  - the ddof.

**D3. BUG-003 is open.**
- remote_setup.sh:36–37 pins only tribev2. The backbones come from HF `main` (smoke_report "Resolved revisions").
- run_clip.py:46–58 `_revisions()` omits the backbone revisions, so a drifted backbone passes the cache guard (feature_cache.py:118).
- I grepped src/, tests/ and infra/ for `HF_HUB_OFFLINE` and found nothing.
- ROADMAP.md:113–137 lists no prerequisite.

**D4. The P5b remedy goes the wrong way** (v2.md:394, "reduce K_Q").
- FPR inflation under y* = g(M0) means R leaks M0 nonlinearity outside Q. Shrinking Q worsens the leak.
- Under D-036, Q cannot grow either.

**Guard votes (BUG-009, BUG-010).** Searched config.yaml `guards:` and BUGS.md:12,15; found no scientific objection. I defer to QA and the Watchdog.

## Required changes

1. **Make v2.md:56/69 and config `m0:` match D-036 exactly:**
   - the Q columns;
   - era and `voiced_any` linear, outside the PCA, counted in rank;
   - the forced features squared or not;
   - PCA on the z-scored full analysis set after exclusions, label-free, with ddof stated;
   - the tie rule;
   - delete "no PCA";
   - add a v2.4.1 note.
2. **Replace v2.md:12–13 with:** "'Beyond M0' means beyond the span of the prereg-frozen Q(M0): M0 linearly in the classifier; for residualisation, speech rate, speech fraction, the first j label-free PCs of the remaining M0, their squares and K_Q pairwise products. Not beyond all quadratic functions of the measured features."
   - The prereg prints j, K_Q and the loadings.
   - P10 repeats the sentence beside every H4 result.
3. **Implement FIX-D032-3 before P5b** (not just P6). Rerun h4sim and the H4 FPR on the D-036 Q.
4. **Change v2.md:394 to:** "FPR > 7.1% → H4 is reported as non-interpretable as 'beyond M0' (descriptive), unless a pre-P6 DECISIONS entry drops M0 features to free rank. Never reduce K_Q."
5. **Make closing BUG-003 a ROADMAP P4 prerequisite:**
   - `snapshot_download` of the three backbones at the tribe_requirements §10 revisions;
   - run_clip sets `HF_HUB_OFFLINE=1`;
   - the backbone revisions are in `_revisions()`;
   - a no-network / revision-mismatch test.
6. **Append** an "ENH-003 DEFERRED (G-D032)" line to ENHANCEMENTS.md.
