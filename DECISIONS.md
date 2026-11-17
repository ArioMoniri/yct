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

## 2026-11-17 | Prompt v2.1 → v2.2 | round-3: Biostat FIX, Neuro FIX → adopt v2.2; prompt-review FIX cycle 3 of 3 reached → escalate residual to human
- D-023 H4 residualisation = unpenalised OLS on Q(M0) = [1, M0, M0², pairwise products among K_Q prereg-named features], rank(Q) ≤ ⌊N/3⌋, era linear only, no ridge/PCA; M0 feature list and p frozen in prereg, binary/categorical not squared (Biostat D1, D5; supersedes D-013's ridge).
- D-024 P5b: H4 FPR on synthetic nonlinear-M0 outcomes (500 reps, B = 500, accept 3.1–7.1%; reduce K_Q pre-P6 if failing); H1–H3/H4b keep 1,000 shuffles at 3.7–6.4%; planted-effect PASS = power at d = 0.5/0.8/1.06 within ±10 pts of h4sim (Biostat D2, D3).
- D-025 ROADMAP aligned to v2.md: short side ≥292 px, test_controls mirrors final P4b, P5b listed before P6 in both files (Biostat D4).
- D-026 T1 clip = first 58.0 s (ffprobe ≤ 58.5 s) with a one-Audio/one-Video-chunk test; W = [max(5, 4+L+1), +40) TRs; T1 exclusion = trimmed duration < W_end + 2 s; ≥2 s latency-shift clause removed (Neuro M1, M2; supersedes D-018's 60 s / 47 s).
- D-027 Limbic is the omitted reference (exact linear combination), not dropped for SNR; H1 still tests all 7 (compositional); H2 parcels = HCP-MMP STSv, STSdp, PGi, 45, 44, TE1a, TP excluded (Neuro M3, Biostat minor).
- D-028 P4b controls: (a) partial Pearson r with crop-restricted, L-shifted, impulse-convolved regressors, Fisher-z t across videos, low-SD exclusion with reference-clip fallback (HAC dropped); STG → AUD = A4 ∪ A5; (c) uses mean speech envelope; new (d) face/place localiser replication (Neuro M4, M5).

## 2026-11-17 | Owner actions (chat, interim until signed-commit CI exists)
- H-001 Owner set GPU budget cap to USD 200 → infra/BUDGET_USD (lambda_gpu.py now reads the file, not env).
- H-002 Owner signed DATA_DECISION.md by chat message; media download in P1 is now permitted.
- H-003 Owner fixed IAM/SSM + NAT path; pod i-02dc0aef7260534ee Online in SSM. Note: release its Elastic IP when the pod is deleted.
- D-029 (deviation, interim) Phase 1 started before owner age key exists: Curator subagent writes plaintext labels to git-ignored data/sealed/labels_pending.csv; orchestrator/analysts never read data/sealed/; encrypt to docs/owner_age.pub and shred plaintext as soon as the owner commits the key. Watchdog to audit at P1 gate.
- D-030 Owner actions move from SSH-signed commits to AWS SSM Parameter Store /yct/owner/* (owner-only write; pod role + tribe-pod-manager explicitly DENIED write and DENIED reading age_key/hf_token as applicable). Verification = parameter exists + GetParameterHistory LastModifiedUser == /yct/owner/owner_arn, checked at runtime on the pod (CI cannot reach AWS). Reason: owner wants zero local tooling; setup via AWS CloudShell (scripts/owner_cloudshell.sh). owner_mac.sh removed. Supersedes the signing mechanism of D-021.
- D-031 owner_cloudshell.sh replaced by scripts/owner_setup.sh (same logic; runs on the owner's Mac with existing AWS login or in CloudShell; no clone/jq). (Also: commit 8005ceb briefly edited D-030 in place, violating append-only; reverted here — logged in BUGS.md.)
- D-032 Owner request: add T3 photometric-normalised sensitivity track (gray-world WB, global luminance/contrast match) and descriptive atlas localisation outputs (peak-parcel tables Schaefer/Yeo/HCP-MMP/Destrieux + 4-view maps). Primary analysis unchanged (normalising the stimulus alters TRIBE input). Pre-lock change, to be reviewed at P0 gate. TRIBE docs/issues audit commissioned → docs/tribe_known_issues.md.
- D-033 D-032 additions are PROVISIONAL until council gate G-D032 (Watchdog, Referee, Biostat, Neuro, QA; fresh contexts) votes GO on code + tests + docs/tribe_known_issues.md. Until then T3 and localisation outputs must not be used in any gate packet.

## 2026-11-17 | Gate G-D032 (T3 photometric, atlas localisation, TRIBE known issues) | votes: Watchdog VETO (fixable), Referee FIX, Biostat FIX, Neuro FIX, QA FIX (merge-blocking) → decision: FIX, cycle 1/3
- Ticket FIX-D032-1 (engineering): CI green (ruff pin, lint tribe_run/transcribe, install all extras, atlas cache in CI, no silent skips, make guards BASE), requirements.lock, weak tests (T1-unchanged, photometric BT.709, smoothing), BUG-006 feature-cache determinism, BUG-007, BUG-008, GPU heartbeat ledger.
- Ticket FIX-D032-2 (science): medial wall = Schaefer ∪ HCP '???' ∪ Destrieux medial; crop-aware face regressor + T3 stats; T3 rules (reuse T1 M0/Q/W/blocks/seeds; outside Holm, no α; survives = same sign & p<.05 else fragile; max_gain cap; report gain/clipping by group); localisation firewall (fixed caption + test, claim-language lint, company-cluster bootstrap BCa + stability + selection footnote + BH-FDR q column, hatch unreliable, "best-overlap" wording); M0 NaN rule (drop text_frac from M0; W-averaging step; label-free imputation; finite + rank asserts); speech rate & speech fraction forced into Q(M0); label-free no-audio/<20-words exclusion; tribe_requirements §3 subcortical correction.
- PI resolution of Referee (defer) vs Neuro (exploratory OK) on ENH-003: DEFER. Re-proposable after P4 as its own exploratory gate with ≤6 pre-fixed bilateral structures, pinned checkpoint, never in M-models.
- ENH-002 accepted: dry-run P4b controls on reference clips before prereg lock; any control change only via DECISIONS entry before lock.
