# ENHANCEMENTS

Append-only log. Format: date | phase | id | summary | evidence.
- ENH-001 | P3 | add words/s and speech fraction to M0 explicitly (TRIBE text features are summed per bin, so speech rate scales text input). Expected effect: fewer spurious H4 effects driven by speech rate. Measure: VIF/partial-R² of M1 on rate.
- ENH-002 | P4b | dry-run positive controls on reference clips before prereg lock (paper expects weakened low-level visual predictions → V1–V3 motion control may fail).
- ENH-003 | exploratory | facebook/tribev2-subcortical exists on HF (since 2026-05-13) → could address N3 subcortical gap (NAcc/amygdala proxies). Proposal for council at G-D032; would be EXPLORATORY only. tribe_requirements.md §3 "not released" is outdated.
- ENH-004 | P4 | Peak VRAM 13.4 GB on A100-40GB → A10 (24 GB, $1.29/h) qualifies per v2 §3; propose A10_ALLOWED=1 at P0 gate (cost saving ~35%).
- ENH-005 | P2 | (Neuro G-D032 A1) add swscale flags accurate_rnd+full_chroma_int to colour conversion (−2 code-value bias → +0.35 on BT.601 sources). Before P2 normalisation.
- ENH-006 | P2 | (Neuro A2) detect HDR (PQ/HLG transfer) sources; force SDR download format or tone-map + flag as covariate. Before P2 normalisation.
- ENH-007 | P9 | (Neuro) reliability mask = anatomical dropout proxy (OFC/TP); legend must say so; caveat omission of ventral anterior temporal (TF/TE2a/PeEc/EC) and vmPFC (10r/10v/25/s32) or extend mask pre-lock.
