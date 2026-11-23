# D-089 v2: response to the council (cycle 1, wf_f75444e5-978)

| Member | Item | Response |
|---|---|---|
| all 5 | Re-confirm the SPK rate with the owner on accurate numbers (140 wpm gives median 0.985 s, not the 1.0–1.1 s offered) | Done. The owner chose "120 wpm by rule" (2026-11-23). d089_v2 §0, §1. |
| watchdog B1, biostat, referee, neuro, qa | Choose the rate by a stated rule computed only from the v1 STOP spans; test that recomputes it | Done. `spk_rate_rule` is in config with the source sha. `spk_rate_by_rule` gives 120. Tests: `test_rule_recomputed_from_the_stop_record_gives_120` and the boundary test (115 vs 120). |
| biostat | Schema pins the exact rule rate (80–174 accepted any value) | Done. The schema requires SPK = 120. `test_schema_pins_spk_at_the_rule_rate` checks it. |
| watchdog B2, referee, biostat, neuro | Explicit owner ruling that exhaustion in BURST/TALKFACE is also final; downstream meaning stated before the re-run | Done. The owner chose "Final stop, report it". Config has `final_stop_families` and `on_final_stop` (control failed; dependent analyses dropped and named; no amendment). d089_v2 §3. |
| referee, biostat, neuro | Per-family exhaustion record: tried, kept, Wilson, stop position | Done. `stop_record` adds `final_stop`, `stopped_at.queue_position` and `queue_used_by_family`. Wilson is computed per family (`test_stop_record_is_numbers_only_with_wilson_and_stop_position`). |
| watchdog B3a, referee, neuro, qa | EspeakSynth refuses `rate_wpm=None` under a per-family spec | Done. `test_espeak_refuses_missing_rate_when_spec_is_per_family`. |
| watchdog B3a, referee, neuro, qa | Build takes rates from the frozen selection record and asserts they equal effective_spec | Done. `speech_corpus.build_rates`, with tests. |
| watchdog B3b, biostat | Build test that fails if SPK is sent at 175 | Done. `build_raw_speech` plus `test_build_raw_speech_sends_the_spk_rate_never_175`. |
| watchdog B3c, biostat, neuro, qa | Clip manifest records the rate per clip; selection record stores rate per item | Done. `clip_speech_meta`; `select` writes `rate_wpm` for each item. |
| watchdog B3d, referee, biostat, neuro, qa | QC re-measures every built SPK span at −40 dBFS; in [1.0, 1.5] s and equal to the selection span (±1 sample); else STOP | Done. `refclips_qc85.spk_span_qc` is gating. `build_qc` in config sets the tolerance at 1 sample. |
| watchdog, neuro | Test that v1 keep ids never enter without re-measurement; queue_used per family | Done. `check_no_carry_over` plus `test_no_v1_keep_enters_without_remeasurement`; `queue_used_by_family`. |
| watchdog, neuro, qa | Freeze row pins rate_wpm_by_family, on_exhausted, restart_queue_at; expected row in test_guards_frozen_config | Planned for the freeze (d089_v2 §6). The whole `controls.refclips_d089` block is frozen, covering every subkey. The expected row is added in the freeze commit, not now (no freeze before re-sign-off). |
| neuro (required), referee Q1 | Descriptive envelope modulation peak per family plus a limitations sentence on the rate mismatch | Done. `yct.confounds.modspec.peak_modulation_hz` (gating false). Disclosure is in d089_v2 §7. T-ENV is unchanged. |
| qa | Disclose that the rate was tuned on the same 410 items (span only); sensitivity range | Done. d089_v2 §1 table (e = 1, 0.8, 0.6) and §7. |
| qa | Replace "at least ~15%" with the joint SPK+BURST queue budget | Done. d089_v2 §1, "Joint queue budget". |
| referee, biostat (non-blocking) | Restart at 0 with no carry-over is correct | Kept as drafted. |
