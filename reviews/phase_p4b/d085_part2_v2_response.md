# D-085 part 2: response matrix (council cycle 1 → v2)

| Member | Item | Response | Where |
|---|---|---|---|
| all | T-ENV filter: disclose, no amendment; frozen before ratification; order 8; −6 dB at 10 Hz; silent → zeros | Text written for the DECISIONS entry | d085_part2_v2 §1, §6 |
| watchdog B1, QA B1, biostat B1, referee B3 | Synthesis verifies the engine shas, fails closed, test; data-tree script committed; engine_pin frozen inside `speech` | `EspeakSynth` + `verify_engine`; `scripts/espeak_pin.py`; `engine_pin` required in the schema; re-checked on the pod | espeak_engine.py, espeak_pin.py, config_schema.py; tests 1–7 |
| neuro 2 | Name the resample step | Selection resamples 22050 → 48 kHz with the build's `resample_bandlimited`, `selection_sr` key | §2, config |
| watchdog, referee B1, biostat 3 | Option (b): pin the upstream SD-loader commit; re-hash README/licence; s3fd unchanged; else fallback (a) on the fixture, before any real face | (b) does not exist (master = bac9a81, no SD loader in 113 commits); README, licence, s3fd unchanged; (a) applied | §3, loader_check.json |
| QA B2, neuro 3 | (a) as strict state_dict into the pinned class; jit only if strict fails | Strict load ok (352/352, max diff 0.0); `jit_fallback: false` | wav2lip_loader.py, loader_check.json; tests 8–10 |
| watchdog B3, biostat B3 | Loader test on the synthetic fixture before the part-2 freeze | Done on the pod, recorded, committed | outputs/runs/d085p2_loader_check/ |
| all | GAN never used | `gan_allowed: false`; loader refuses GAN files | tests 9 |
| watchdog B2, referee B2, QA B3, neuro 4, biostat 4 | Name `talkface.face_continuation`, separate budget from D-087, terms as ruled, byte-identical rows | Key added; runner `--purpose talkface` gated on the part-2 freeze; face only; target ≤ 21 + 5; `assert_byte_prefix` after each category | config, refstim_auto_run.py; tests 11–14 |
| referee B3, QA 5, neuro 5, biostat 5, watchdog 5 | Amended freeze order; weights sha frozen in the part-2 commit | Order written | §5 |
| biostat | pass_rates descriptive with Wilson 95% interval; never feed back; exhaustion = STOP | Pre-specified | §5 step 2 |
| watchdog B2, QA B4, biostat B2 | DECISIONS entry carries the disclosures | Drafted, not appended (re-sign-off first, D-084 note) | §6 |
| process | Freeze only after every REVISE member re-signs (D-084 note) | Nothing frozen; no DECISIONS entry | — |
