# D-087 v2: response to council cycle 1 (council_d087_*.md, REVISE ×5)

Owner rulings (2026-11-23): "Body + place only", "Pre-exclude place_14", "Screen scrambles too".

| Member | Item | Response | Where |
|---|---|---|---|
| Watchdog | B1 settle place_14 | Round-0 `pre_excluded`, cites STOP_NOTE, post_hoc; owner "Pre-exclude place_14". The draft §7 "place_14 is not in v2" now follows from the rule | config `pre_excluded`; `select(pre_excluded=)`; v2 §2.3; tests `test_pre_excluded_*` |
| Watchdog | B2 rebuild_identity | `rebuild_identity.build1` (GREY_CTRL/FLASH/MOT/MOT_STAT vs build 1) + `.loc` (patch sha vs screen record) | config; `refclips_build.restrict_*`, `patch_identity_mismatches`; v2 §6; tests |
| Watchdog | B3 pod driver + v2 builder path | `scripts/locscreen_v2.py` (real wiring + `run_screen` tested with fakes end to end); `refclips_build.py --images v2` | v2 §3, §6; `test_driver_*`, `test_v2_*` |
| Watchdog | B4 owner confirmation | Q1, B1, B5 answered by the owner 2026-11-23; to be recorded in DECISIONS D-087 | v2 header, §8 |
| Watchdog | B5 scramble screen | Adopted (owner): scramble + swap of every slot gate, face slots included | `rendered_loc_patches`, `make_gate`; config `scramble_*`; tests |
| Watchdog | T-DRV-V2; append-only continuation | `campaign_cap` + carried-spend check in `guard_launch`, also in NAT `check_projection`; continuation prefix byte-identity + committed-before-rescreen | `ref_campaign.py`, `gpu_p4b_nat0.py`; `locscreen_v2.py`; tests |
| Referee | B1 driver + v2 manifests | As Watchdog B3 | — |
| Referee | B2 v2 rebuild checks | As Watchdog B2 | — |
| Referee | B3 owner Q1 | Owner "Body + place only" | — |
| Referee | B4 §2.6/§3 rewrite | §3: continuation is the main path (every v4 log ends at pass 20); where it runs and its cost; v1 manifest sha untouched; TALKFACE rank 492 unless a face scramble hit; face continuation path | v2 §3, §4 |
| Referee | B5 T-DRV-V2 | Done | v2 §5 |
| Referee | B6 scramble gap; round 1 partly known | Scrambles screened (owner); §7 discloses round 1 partly known from build-2 QC | v2 §7 |
| Biostat | B1 owner confirms Q1 | Done | — |
| Biostat | B2 place_14 surface gap | Pre-excluded in round 0 (owner); x264 round-trip screen not adopted (the threshold/margin is disclosed, not lowered) | v2 §2.3, §7 |
| Biostat | B3 driver + integration test | `test_driver_runs_continuation_then_asks_for_a_commit_before_rescreening` (synthetic logs, continuation, commit gate, manifests, record); pod run records the toolchain through the builder | — |
| Biostat | B4 split C3 | As Watchdog B2 | — |
| Biostat | B5 cap/exhaustion STOPs final | `continuation.cap_or_exhaustion: stop_owner_final`; driver STOP_NOTE; tests | v2 §3 |
| Biostat | non-blocking: v1 → face rank 492; scramble forecast | `test_consumed_rank_and_talkface_start` (draft) + face max rank tests; scrambles are now gating (owner), not only descriptive; `face_absent` recorded | — |
| Neuro | 1 screen scrambles incl. face | Adopted (owner) | — |
| Neuro | 2 place_14 | Pre-excluded (owner) | — |
| Neuro | 3 C3 for v2 | As Watchdog B2 | — |
| Neuro | 4 driver | As Watchdog B3 | — |
| Neuro | 5 T-DRV-V2; pod time counts | Done; pod time disclosed (not a ledger GPU spend) | v2 §3, §5 |
| QA | driver end to end | As Watchdog B3 | — |
| QA | per-patch sha | `patch_sha256` in the screen record; builder check before any build | v2 §2.9, §6 |
| QA | scrambles | Adopted (owner) | — |
| QA | tell the owner Q1 | Done | — |
| QA | recommended: face-present record + pooled forecast | `face_absent` (descriptive) | v2 §2.5 |
| QA | recommended: x264 margin | Not adopted: the threshold stays at the frozen QC value; disclosed in §7 (lowering it now would be post-result) | v2 §7 |
| QA | note: TALKFACE reduces to 492 | Stated; true unless a face slot is replaced through a scramble/swap hit | v2 §4 |
