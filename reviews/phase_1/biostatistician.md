# Biostatistician review: Phase 1 gate (wave 1 curation)

Repo fd08ad9 (packet cites 536e816; diff = packet + gpu_ledger only). Manifest sha256 = 719080c8…1ea, matches D-045. I did not read data/sealed/*. I used only the manifest and the reported totals.

**Vote: FIX.** Wave 1 can go ahead as exploratory. Before the prereg lock, D-044's confirmatory design needs the sizing and alpha changes below.

## Derived numbers (manifest only)

- in_primary = 58 (30 accepted / 28 rejected reported). It holds 56 distinct companies; only `firejet` repeats (yct_0641–0643). **Effective N = 56.** Worst case per group, without labels: min group ≥ 26 (both dropped rows are rejected, consistent with D-045), so 30/26.
- T1 duration rule: W_end = 45 s + min_tail 5 s, so a video needs ≥ 50 s. yct_0483 (43 s) is excluded, giving **T1 N = 55** and a worst-case group of 25. The no-audio and <20-word exclusions are still unknown.
- Era: E3 46, E2 7, E1 3 (after dedup). Platform: YouTube 49, LinkedIn 6, web 1.
- Q(M0) (`m0.q_dimension_table`): ⌊56/3⌋ = 18 (also 18 at N 55). Required block = 16 (3 era levels): **0 merges**, 2 optional squares. If E1 is merged into E2: 15 required, 3 optional. The N < 39 hard-fail is far away.
- Single-network Welch MDE (`pw.py` method): 30/26 gives d = 0.76 (AUC 0.71). Bonferroni over 7 (maxT bound) gives d = 0.98. Holm worst case (α/4) gives d = 0.92.
- **H4** (committed `analysis/power/h4sim.py`, B = 99, 80 datasets per row, N via an env override): eff 1.06 gives power **0.50 at N 56**, 0.46 at N 60, 0.72 at N 80 and 0.79 at N 100. eff 1.5 at N 56 gives 0.68. Null size at N 60 = 0.06. So the H4 MDE at this N is above 1.5.
- Wave-2 n/group for 80% power: d = 0.74 needs **30** (two-sided α .05) and 43 under Holm worst case (α/4). H4 at eff 1.06 needs **about 50/group** (N ≈ 100).

## Defects

1. **[MAJOR] The H4 MDE claim does not reproduce.** v2.md §0 l.20 and D-016 say d ≈ 1.06 gives about 80% power at 30/group. The committed script gives 0.46 at N 60, and 80 datasets put the SE near 0.056. The 0.79 in reviews/prompt_v2/strict_referee.md came from an uncommitted scratch variant.
   - Required: rerun h4sim with ≥ 500 datasets and a pinned seed, commit the N parameter, and correct §0 (H4 ≈ 80% only at about 50/group) through a DECISIONS entry.
   - The P5b planted-effect PASS band (±10 pts of h4sim) must use the corrected values.
2. **[MAJOR] D-044 multiplicity.** "Wave 2+ … analysed once each as confirmatory" allows several confirmatory looks at α .05 each, which inflates FWER across waves. Required:
   - one confirmatory analysis at a pre-registered N_target or a fixed calendar stop, triggered without labels (Curator totals only);
   - later waves treated as replication outside α, or a declared α-spending plan (e.g. O'Brien–Fleming over k looks).
3. **[MAJOR] The wave-2 confirmatory floor of ≥20/group is too low.**
   - At 20/group the single-test MDE is d = 0.91 and H4 power is below 0.4.
   - Required: confirmatory status needs ≥ 30/group (the H1–H3 MDE 0.74), and H4 is labelled "underpowered" unless ≥ 50/group, with the MDE printed.
   - Wave-2 companies must be disjoint from wave-1 company_ids, because multi-cycle companies like FireJet violate independence. `collected_after_lock` and a `wave` column must also exist in the manifest before the lock.
4. **[MAJOR] Era × route blocks are at risk.**
   - E1 + E2 holds only 10 rows. Seven of them are contiguous IDs (yct_0626–0633) from one curation round, which suggests a single route and possibly a single label.
   - E1 (3) merges into E2 under the <6 rule. If either route cell of E1∪E2 is still <6, it merges into E3 and era stratification within that route is gone.
   - If E1∪E2 turns out label-pure, effective accepted N drops to 20 in the worst case, right at the "inconclusive" threshold.
   - Required:
     - the Curator reports block totals (no labels) at this gate;
     - the prereg fixes E1→E2 merging for the Q era dummies (D-019 mechanical rule; E1 dummy on 3 rows is near-aliased);
     - at unblinding, the label × era table is reported.
5. **[MINOR] Platform is an unmodelled confound.** Platform (7 non-YouTube rows, contiguous yct_0635–0646) is not in M0 or the blocks, and encoding and aspect ratio differ by platform. Required: a YouTube-only sensitivity outside Holm, and a label × platform table at unblinding.
6. **[MINOR] Reconciliation gaps.**
   - D-045 says FireJet has "4 rejected cycles", but the manifest has 3 FireJet in_primary rows. Either one is conf-B, or a cycle sits under another company_id; if so, effective N = 55 and rejected = 25.
   - curation_report.md is stale (39 conf-A, 627 rows, "Platform: youtube 627"); it must be regenerated for the 661-row manifest.
7. **[MINOR] The κ ≥ 0.9 re-derivation is uninformative at 15%.** 15% is 9 rows, so a single disagreement gives κ ≈ 0.78 and fails, and the CI spans roughly 0.5–1. Required: blindly re-derive all 58 conf-A rows with a sealed re-derivation agent run owner-side. The owner script outputs only κ, n_disagree and a 95% CI; one disagreement then gives κ ≈ 0.97.

## Required changes (exact)

- **v2.md §0:** replace the H4 line with the reproduced power table (N 56/80/100) and state that wave 1 is exploratory, with the H4 MDE > 1.5.
- **DECISIONS** (new D-entry amending D-044):
  - a single confirmatory look at N_target ≥ 30/group (H4 underpowered flag < 50/group);
  - a label-blind stop trigger;
  - waves 3+ as replication outside α;
  - disjoint company_ids across waves;
  - E1→E2 era merge for Q.
- **Manifest:** add `wave` and `collected_after_lock`.
- **Curator:** regenerate curation_report.md, report label-free block totals, and reconcile the FireJet count.
- **ROADMAP P1 DoD:** κ is computed on all conf-A rows, run by the owner on the sealed data.
