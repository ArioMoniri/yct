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
