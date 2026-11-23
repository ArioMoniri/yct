# Reference campaign session 1: pre-launch record for the council (D-071 (k), p4b_ref/v2 under D-087)

Status: **NOT ready to launch.** The full 120-clip manifest is frozen, but the driver cannot read it yet
(§3, U1) and the NAT transcripts are not in TRIBE `.tsv` form (U2). Nothing launched; no spend.

## 1. Frozen inputs (all set and frozen)
| Key | Value | Set / frozen |
|---|---|---|
| `controls.refclips_artifacts.manifest_sha256` | d1141cf1…37ea (`data/refstim/refclips_manifest.json`, 120 clips) | 6440ebf / 0edb3d8 |
| `nat_manifest_sha256` | 2fbe3421…825e (15 NAT) | a502253 / 3587da2 |
| `image_manifest_sha256` | 322f8a42…f425 (v1 record; v2 images via D-087 screen record) | 376966a |
| Family counts | LOC 20, LOC_SCR 20, SPK 20, MOT 16, MOT_STAT 16, NAT 15, BURST 5, FLASH 5, GREY_CTRL 2, TALKFACE 1 | `controls.refclips.families` |

The manifest is assembled by `scripts/clip_manifest_assemble.py` (`--check` re-derives it bit for bit from the
committed parts). Each part's frozen QC passed: the visual build (D-087), the speech build (D-089), the TALKFACE
session p4btalk_1795471461 (QC pass, 9 gates; shas re-verified against the private mirror), and the NAT dry run
(15/15 inputs present and sha-matching).

## 2. Launch preconditions (D-071 (k) and later amendments)
| # | Precondition | Where enforced | State |
|---|---|---|---|
| P1 | Clip manifest sha == frozen value; family counts == config | `gpu_p4b_ref.load_clip_manifest` | **blocked by U1** |
| P2 | Pod clips (mp4 + tsv) sha == manifest, never built on the box | `check_inputs` / `RefPodBackend.inputs` | **blocked by U1, U3** |
| P3 | P4 revisions sha seeded from the single P4 loader (same stack + GPU) | `seed_revisions` (p4_index) | wired |
| P4 | Campaign baseline `entries/campaign_baseline.json` written once before session 1 | `ensure_baseline` | wired (not yet written) |
| P5 | $ cap: v2 own cap $75 (D-087, $0.39 carried), guard_launch with the planned worst case | `rcmp.guard_launch` → `cost_cap_usd` (T-DRV-V2) | wired |
| P6 | Campaign projection (spend so far + this session's worst case + remaining plan ≤ $75) | `check_projection` exists only in the NAT/TALKFACE drivers | **U4** |
| P7 | External terminator: a NEW one-shot fire time in [deadline+900 s, +3600 s], re-armed on every retry | `check_terminator_rearmed` + p4 window check | wired |
| P8 | `--max-hours` ≤ `p4.launcher_max_hours` 1.75; `--usd-limit` 8 | p4.run_session | wired |
| P9 | Launch only from a pushed CI-green commit | orchestrator check (as in NAT/TALKFACE) | **U5** (not in this driver) |
| P10 | L4 ledger reconciliation record fresh, no open launch / live instance | NAT/TALKFACE `reconcile`; p4 one-instance check | **U5** |
| P11 | Type missing from `lg.types()` → exit 75 | gpu_wave1_p4 (BUG-033) | wired |
| P12 | Job order = `controls.refclips.job_order` unchanged; session 1 `--limit 3` = D-038 clips GREY_CTRL_00, SPK_00, MOT_00 | `plan_ref_jobs` | wired (tested on synthetic) |
| P13 | T-ABL: audio-only and text-only conditions on the 20 SPK clips, predicted from the full cache; first 3 per condition get a Gate-1 cached rerun | `plan_ref_jobs` / box `--condition` | wired (tested); not in session 1 |
| P14 | Gate-1/2 T1 per-clip gate rules (qc_track t1) | p4.run_session | wired |

Analysis-side (consumed after predictions; not launch gates, all frozen):
- **Kernels K1–K6:** `src/yct/controls/kernels.py`, rules in `controls.kernel.*`, frozen FIX-NORM-0.
- **Controls (a)–(d):**
  - (a) partial r with `partial_out` [face, motion, luminance_change, speech_envelope] plus nuisance
    [intercept, legendre_1] (D-086; intercept-only reported descriptively): `controls/partial.py`;
  - (b)/(c) kernel derivation and the FFC/PH/AUD/V1_V3 ROI lists;
  - (d) localiser readout = mean of output lags `readout_lag_tr` [0, 3].
  - The (b)–(d) readout script that reads `full/` predictions is **not yet written (U6)**; this is not needed
    for session 1.

## 3. Driver dry run against the frozen manifest (no launch, no network)
- `tests/test_gpu_p4b_ref.py` (17 tests: synthetic manifest, fake Lambda) passes: plan, D-038 first, ablations,
  baseline, cap refusal, warn ack, terminator re-arm, capacity miss, limit 3.
- Against the **real** frozen manifest: `gpu_p4b_ref.load_clip_manifest(refclips_manifest.json, cfg)` fails with
  `KeyError: 'clip_id'`. The sha check passes first; the schema does not.

## 4. Unwired items (each needs code + tests, and U1/U2 a council ruling, before launch)
- **U1, manifest schema.** The driver expects `clip_id` = `<FAMILY>_<index:02d>` (e.g. `GREY_CTRL_00`),
  `index`, `mp4_sha256`, `tsv_sha256`, `duration_s`. The frozen manifest has `name` (`grey_ctrl_00`), `i`,
  `sha256{mp4,wav,tsv}` (NAT: `sha256{mp4,wav,transcript}`). Proposed: a read-only adapter in the driver that
  maps fields (`clip_id = FAMILY_ii`), tested against the frozen file. The frozen manifest is unchanged.
- **U2, NAT transcripts.** TRIBE takes a word `.tsv`. The 15 NAT clips have only the WhisperX `.json` (P2b),
  whose sha is in the manifest as `transcript`. The wave-1 path converts json → tsv with
  `scripts/wave1_p2b_pod.py ingest` (frozen `transcribe.tsv_columns`). Council choice:
  - (a) Run the frozen ingest on the 15 NAT jsons. Record the tsv shas, then amend the manifest to v1.1 with
    `tsv` for NAT, and re-freeze `manifest_sha256`. This is outcome-blind: no reference prediction exists.
  - (b) Keep the manifest; derive the tsv on the pod with the frozen ingest; gate a derived sha record.
  - Recommendation (a): the box gate stays "manifest sha only", as D-071 (d) says.
- **U3, upload.** The clips are not yet at `/work/yct/p4b_ref/v1/clips/` (pod) nor uploaded under
  `controls.refclips.s3_root`. D-071 (d) uploads after the freeze. Needed: a T-STIM upload step that copies
  each clip from its source (visual, speech and NAT pod dirs; TALKFACE private mirror, never public) to the pod
  clip dir and S3, named `<clip_id>.mp4/.tsv`, then re-verifies every sha against the manifest.
- **U4, projection.** Add the D-084/T-DRV-V2 `check_projection` to `gpu_p4b_ref` (spend so far $1.85 +
  session worst case + remaining reference plan ≤ $75) and store it in the pre-launch record.
- **U5, CI-green + L4.** Add the `--ci-green-sha` / pushed-HEAD check and the L4 reconcile record, as in the
  NAT and TALKFACE drivers.
- **U6, readout script.** The (b)–(d) readout script is analysis-side, after session 1.

## 5. Launch command (after U1–U5 are done and the council signs off)
```bash
AWS_DEFAULT_REGION=eu-central-1 python scripts/run_with_provenance.py --run-id p4bref_<UTC> -- \
  python scripts/gpu_p4b_ref.py --clip-manifest data/refstim/refclips_manifest.json \
  --external-terminator-at <ISO, deadline+900..3600 s> --max-hours 1.75 --usd-limit 8 --limit 3
```
Watched, with a send_later reap terminator for `yct-p4b-ref` instances only (D-059), deleted after we confirm
nothing is live.

## 6. Cost
- **Session 1** (3 jobs: GREY_CTRL_00, SPK_00, MOT_00 on one A100 at $1.99/h): expected about $0.5–1, plus
  setup. The worst case is the 1.75 h launcher limit = $3.48.
- **Campaign spend so far:** $1.85 (NAT sessions 0–2, TALKFACE sessions).
- **Projection:** $1.85 + $3.48 + the remaining reference plan ($61, `main_campaign_plan_usd`) = $66.3, under
  the $75 v2 cap.
