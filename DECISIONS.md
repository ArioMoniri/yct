# DECISIONS

Append-only log. Format: date | phase | id | summary | evidence.

## 2026-11-17 | Prompt v1 → v2 | council: Watchdog FIX, Strict Referee FIX, Biostat FIX, Neuro FIX → decision: adopt v2
- D-001 Council slimmed to 5 independent voting reviewers (Watchdog, Referee, Biostat, Neuro, QA); exec roles don't vote. Resolves Referee "delete council" vs Watchdog "make it independent".
- D-002 Sole primary = H4 ΔAUC(M2−M0) via conditional permutation (Biostat). Referee's M0b comparator adopted as H4b in Holm family + gating for any "brain-specific" wording.
- D-003 Primary features = spatially standardised Yeo-7 means (Biostat B1: per-vertex temporal z makes means 0).
- D-004 No extra HRF shift; TRIBE outputs already +5 s (Neuro). Window W default TRs [5,45), finalised label-free in P4.
- D-005 No letterbox padding; native aspect + crop-coverage covariate (Neuro: V-JEPA2 centre-crops square).
- D-006 Inject pinned WhisperX .tsv; never let TRIBE call unpinned uvx (Neuro).
- D-007 Stop thresholds: <20 conf-A/group → descriptive pilot (Biostat) rather than Referee's 30; 20–29 flagged underpowered.
- D-008 Holdout only if N≥200 (Biostat); else temporal replication set.
- D-009 Positive/negative controls gate P4b with STOP (Referee + Neuro).
- D-010 Labels sealed with age to human key; human-only UNBLIND_TOKEN (Watchdog).
- D-011 DATA_DECISION.md human signature required before any media download (Watchdog legal).
- D-012 Phase 9b rater study deferred; Neurosynth reverse inference removed; Destrieux label-only (Referee).
- Budget: BUDGET_USD=50 default pending human (Watchdog proposed 150).

## 2026-11-17 | Prompt v2 → v2.1 | round-2: Watchdog FIX, Strict Referee FIX → decision: adopt v2.1
- D-013 H4 residualises M1 once (label-free, full set) on Q(M0) = M0 + squares + products; same R for observed and null (Referee sim: raw-vs-residual mismatch skews p; nonlinear M0 leaks at 0.40).
- D-014 Confirmatory set = one video per company, seeded label-free choice; pair swaps invalid (accepted always later). Pairs exploratory.
- D-015 M1 = 6 non-limbic Yeo means + spatial SD (rank-6 issue). M0b PCA per block 3/2/2.
- D-016 H4 MDE stated as d≈1.06 beyond M0 at 30/group (optimistic sim). No brain-specific claim licensed.
- D-017 Positive controls fully specified (HAC within-video, selectivity, between-video at analysis aggregation).
- D-018 T1 = first 60 s clip (no chunking); exclude <47 s from T1; W frozen in P4 before M0/M0b averaging; impulse latency may shift W.
- D-019 Era strata from YC calendar with mechanical merge rule; M0 AUC≥.85 never demotes H4.
- D-020 Curator = separate subagent; plaintext labels never on disk; Curator never sees §1.
- D-021 Human-only actions enforced by SSH-signed commits checked in CI (to build in P0; Watchdog treats agent-performed ones as CRITICAL until then). Gate quorum = ⌈2/3⌉ of assigned reviewers; P6 unanimous 5/5.
- D-022 P5b pipeline validation moved before prereg lock; DATA_DECISION adds EU→US transfer, Llama licence, HCP-MMP terms; short side ≥292 px; tsv injection order + uvx block.
