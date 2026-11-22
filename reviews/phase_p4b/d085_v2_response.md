# D-085 v2: response to the council (council_d085_*.md)

| Member | Item | Response | Where |
|---|---|---|---|
| All | (a) Harvard list not public domain | Recorded as copyright not cleared, non-commercial research (owner); LICENSES.md section; `speech.licence_status` | d085_v2 §3; docs/stimuli/LICENSES.md |
| Biostat, Neuro, Watchdog | (a) texts out of the public corpus file | Hash-only corpus file; texts private; `resolve_texts` fail-closed; owner chose a one-time history rewrite | speech_corpus.py; config `private_raw_s3` |
| Referee | (a) drop list/item keys | Not adopted: list/item are needed to resolve texts from the private page; they reveal no text | d085_v2 §3 |
| Watchdog, Biostat, QA | (b)(ii) 3-word SPK at 175 wpm | Adopted (owner); `spk_words_rule` removed; disclosed | config `speech.spk_words`; tests |
| Referee | (b)(iv) per-length rates | Not adopted (owner chose 3-word only) | — |
| Neuro | (b) duration-driven k | Not adopted (owner chose 3-word only; QA: it would choose word count from measured duration) | — |
| Biostat | per-family pass-rate logging | `select()` returns `pass_rates` | speech_corpus.py |
| All | (c) constructive SPK/BURST gate | `speech_gate` on the rendered 48 kHz audio: outside-window identity + exact reconstruction at the logged onsets | refclips_qc85.py |
| Neuro | (c) event-window RMS within 1% gate | Subsumed: exact reconstruction implies the matched RMS; ratio reported | refclips_qc85.py |
| Neuro | (c) BURST envelope from pre-mix utterance | Pre-specified in `speech.envelope` | config |
| All | (c) speech_envelope descriptive; T-ENV frozen before speech builds | `envelope.gating: false`; `speech_build_preconditions` | config; speech_corpus.py |
| All | (d) decoded diffs descriptive | `twin_decoded`, `decoded_vs_rendered` (gating false); `row_pass` | refclips_qc85.py |
| Referee, Neuro, QA / Watchdog, Biostat | (e) weights | `wav2lip.pth` (3–2) | config `talkface.weights_file` |
| Neuro | (e) --fps 30; 96 px disclosure | `talkface.fps: 30`; disclosed | config; d085_v2 §4 |
| All | (e) private mirror, shas only | `talkface.mirror_s3` private; README sha field | config |
| Owner / Watchdog / QA | TALKFACE never published | `publish: false` (schema), `synthetic_label: true` | config; schema |
| All | face rule fallback, 5 skips STOP, no ND | `talkface_face`; `face_rule` block | refclips_qc85.py; config |
| Neuro | disclose LOC identity match | `disclose_loc_identity_match: true` | config |
| Watchdog | C1 YuNet never ran | `assert_no_yunet_outputs`, tested on the repo | refclips_qc85.py |
| Watchdog | C2 owner family-pooled ruling | `qc.face_hit_scope_ruled_by: owner_2026-11-22` | config |
| Watchdog | C3 rebuild sha before YuNet | `rebuild_mismatches` in `build_all`, STOP before `run_qc` | scripts/refclips_build.py |
| Biostat, Referee | R1b reader set | test pins the `face_area_crop_frac` reader set | tests/test_d085_council.py |
| Watchdog | cost: TALKFACE worst case | `talkface.session_worst_usd` in `check_projection`; `-talk` not counted as main | scripts/gpu_p4b_nat0.py |
| Referee, Biostat | two-part freeze | `freeze_plan`; QC require_frozen keyed to `.qc` | config; refclips_qc85.py |
| Neuro | **Neuro B1**: YuNet gates only intact body/place event TRs | **Not applied**: narrows the owner-approved gate (every non-face LOC TR + every LOC_SCR TR). Needs an owner ruling before the part-1 freeze | d085_v2 §8 |
| QA | Q1 keep texts public by default | Superseded by the owner's decision (hashes + rewrite) | — |
