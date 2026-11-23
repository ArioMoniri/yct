# Reference campaign session 1: pre-launch record for the council (D-071 (k), p4b_ref/v2 under D-087, D-091)

Status: **U1–U5 closed (D-091), awaiting the council re-sign-off.** Not launched; no spend. The council
re-checks this record and the closing commits before the watched `--limit 3` launch.

History: the first version of this record (bab3bb8) found the driver could not read the frozen manifest
(KeyError) and the NAT clips had no word `.tsv`. Council wf_06444af7-0cf: REVISE ×5. D-091 closes U1–U5.

## 1. Frozen inputs
| Key | Value | Set / frozen |
|---|---|---|
| `controls.refclips_artifacts.manifest_sha256` | d1141cf1…37ea (`data/refstim/refclips_manifest.json`, 120 clips) | 6440ebf / 0edb3d8 |
| `nat_manifest_sha256` | 2fbe3421…825e (15 NAT) | a502253 / 3587da2 |
| `nat_tsv_manifest_sha256` (D-091) | 43db439a…5dde (`data/refstim/nat_tsv_manifest.json`) | 556f637 / 24440be |
| `image_manifest_sha256` | 322f8a42…f425 (v1 record; v2 images via D-087 screen record) | 376966a |
| Family counts | LOC 20, LOC_SCR 20, SPK 20, MOT 16, MOT_STAT 16, NAT 15, BURST 5, FLASH 5, GREY_CTRL 2, TALKFACE 1 | `controls.refclips.families` |

The frozen clip manifest is unchanged (bytes and frozen row). NAT word tsvs come only from the sidecar under
its own frozen key (route (c)).

## 2. Launch preconditions
| # | Precondition | Where enforced | State |
|---|---|---|---|
| P1 | Clip manifest sha == frozen value (raw text, before parsing); read through the pure adapter; family counts == config | `load_clip_manifest` + `ref_manifest.adapt` | **closed (U1)**; tested on the real file + mutated copies |
| P1b | NAT tsv sidecar sha == frozen key; every NAT row valid, ≥ 1 word; json/wav/mp4 provenance == manifest | `load_clip_manifest`, `ref_manifest.nat_tsv_index` | **closed (U2)** |
| P2 | Pod clips (mp4 + tsv) sha == manifest, never built; duration measured by ffprobe on the pod | `check_inputs` / `RefPodBackend.inputs` (`inputs_cmd`) | **closed (U1b)**; pod files placed by U3 |
| P2b | All 120 clips at `/work/yct/p4b_ref/v1/clips/<CLIP_ID>.*` and `<s3_root>clips/`, every copy re-hashed | `scripts/refclips_upload.py`, record `data/refstim/refclips_upload_record.json` | **U3** (see §4) |
| P3 | P4 revisions sha seeded from the single P4 loader (same stack + GPU) | `seed_revisions` (p4_index) | wired |
| P4 | Campaign baseline exists, written before the first yct-p4b-ref launch | `ensure_baseline` / `check_baseline` | **met**: `entries/campaign_baseline.json` written 2026-11-22 08:31Z (n_lines 2807, sha 4261f62b…), before the first launch (ledger line 2807, nat0) |
| P5 | $ cap: v2 own cap $75 (D-087, $0.39 carried) via guard_launch | `rcmp.guard_launch` | wired |
| P6 | Main-campaign projection: spend + price × max_hours + max(0, $61 − done full jobs × $0.45) ≤ $75, in the pre-launch record | `rcmp.main_projection` | **closed (U4)**; active once `controls.refclips_d091` is frozen (see §5) |
| P7 | External terminator: NEW one-shot fire time in [deadline+900 s, +3600 s], re-armed on every retry | `check_terminator_rearmed` + p4 window | wired |
| P8 | `--max-hours` ≤ 1.75; `--usd-limit` 8 | p4.run_session | wired |
| P9 | Launch only from the pushed CI-green HEAD (`--ci-green-sha` == HEAD, on the remote) | `launch_checks.check_commit` (shared with nat0/talk) | **closed (U5)** |
| P10 | L4 ledger reconciliation record committed and fresh; no open launch / live instance | `launch_checks.reconcile` / `check_reconcile`; `--reconcile-only` → `data/refstim/ledger_reconcile_ref.json` | **closed (U5)**; record written just before launch |
| P11 | Type missing from `lg.types()` → exit 75 (BUG-033/047) | gpu_wave1_p4 | wired |
| P12 | Session 1 `--limit 3` = D-038 clips GREY_CTRL_00, SPK_00, MOT_00 | `plan_ref_jobs` | **tested on the real frozen manifest + sidecar** |
| P13 | T-ABL audio-only / text-only on the 20 SPK clips (from the full cache; first 3 get a Gate-1 rerun) | `plan_ref_jobs` | wired; not in session 1 |
| P14 | Gate-1/2 T1 per-clip gate (qc_track t1) | p4.run_session | wired; a header-only 0-word tsv (GREY_CTRL_00) passes clip_gate like a silent clip (tested) |
| P15 | ENH-002 K-run committed | 0b75d65; `src/yct/controls/kernels.py` unchanged since | met |
| P16 | After every session the P4 `manifest.jsonl` sha is unchanged (D-071 (e)); else exit 1 | `run_ref_session` (`p4_manifest_sha256` before/after) | **closed** (tested) |

Stated in advance: a crash or D-038 Gate-2 failure on GREY_CTRL_00 / SPK_00 / MOT_00 is exit 1, a latched
STOP and a BUG; no clip swap (tested: GREY_CTRL_00 rerun_differs → exit 1, the next run refused "STOP").
`reliability()` returns None for differing constant arrays, which are excluded from the D-038 minimum, never
passed (tested); the count excluded per clip is in the run's drift record (`per_extractor`, `arrays`).

## 3. Dry runs (no launch)
- `tests/test_gpu_p4b_ref.py` (17) and `tests/test_ref_session1.py` (36) pass: adapter on the real frozen
  manifest, mutated copies refused, sidecar sha + provenance, plan = [GREY_CTRL_00, SPK_00, MOT_00], ffprobe
  duration parse, upload plan (360 files; NAT from T1 + sidecar tsv, TALKFACE from the private mirror),
  projection, shared launch gate, `--check-only`, D-038 STOP, P4-unchanged STOP, zero-word tsv, reliability.
- `--check-only` against the real pod/S3/ledger at 7ab9da6 (no launch; `outputs/runs/ref_checkonly_d091/`):
  rc 0. The adapter + sidecar loaded the frozen manifest; `check_inputs` matched all 120 pod clips (mp4 +
  tsv sha, ffprobe duration present); the L4 record matched the ledger (2817 lines, no open/live); the
  baseline checks (n_lines 2807, sha 4261f62b…); P4 revisions seeded (74e75882…); P4 manifest sha
  03322d84… recorded; plan first 3 = GREY_CTRL_00, SPK_00, MOT_00; price $1.99/h; projection $66.33 ≤ $75.
  The check-only run used HEAD as the CI sha; the real launch passes `--ci-green-sha` after CI is green.

## 4. U2/U3 runs on the pod (numbers only)
- **U2 (3e3c697):** `scripts/nat_tsv_build.py`: 15/15 valid, `stop: []`, two builds bit-identical; n_words
  139, 132, 193, 215, 142, 141, 130, 147, 115, 144, 111, 148, 100, 124, 99. The wave-1
  `/work/yct/transcripts/manifest.csv` sha (aa93a8c8…) is unchanged before and after. Tsvs at
  `/work/yct/p4b_ref/v1/nat_tsv` (pod) and, after U3, `<s3_root>clips/NAT_ii.tsv` (private bucket) only.
- **U3 (24440be):** `scripts/refclips_upload.py`: 120 clips / 360 files copied (never built) to
  `/work/yct/p4b_ref/v1/clips/<CLIP_ID>.{mp4,wav,tsv}` and `<s3_root>clips/` (empty before; .sha256
  sidecars), every pod copy re-hashed and every S3 object read back and re-hashed: 0 mismatches, `ok: true`.
  Record (shas only): `data/refstim/refclips_upload_record.json` (sha c26fcf3c…).

## 5. For the council
- `controls.refclips_d091` (projection rule, NAT tsv route, upload paths) is **not frozen**: the council
  re-signs, then it is frozen in two commits before launch (the U4 projection is only active once frozen;
  the D-084 note asks every member who raised items to re-sign before a freeze).
- Disclosed: p4b_ref/v2 (D-087) uses the frozen `p4b_ref/v1` S3 root, pod path and manifest version string;
  no prediction object exists under `<s3_root>` (only curation/, entries/campaign_baseline.json, models/,
  nat_asr/, nat_t1/, runs/, sources/ and now clips/).
- U6 (deferred, approved): the (b)–(d) readout script is committed and reviewed before anything but the QC
  gate reads `full/`. The session-1 human check covers gates, shapes, finiteness, shas and cost only.

## 6. Launch command (after the council re-sign-off and the D-091 freeze)
```bash
AWS_DEFAULT_REGION=eu-central-1 python scripts/gpu_p4b_ref.py --reconcile-only     # commit the record
AWS_DEFAULT_REGION=eu-central-1 python scripts/gpu_p4b_ref.py --check-only \
  --clip-manifest data/refstim/refclips_manifest.json                              # no launch
AWS_DEFAULT_REGION=eu-central-1 python scripts/run_with_provenance.py --run-id p4bref_<UTC> -- \
  python scripts/gpu_p4b_ref.py --clip-manifest data/refstim/refclips_manifest.json \
  --ci-green-sha <HEAD> --external-terminator-at <ISO, deadline+900..3600 s> --max-hours 1.75 \
  --usd-limit 8 --limit 3
```
Watched, with a send_later reap terminator for `yct-p4b-ref` instances only (D-059), deleted after we confirm
nothing is live.

## 7. Cost
- Session 1 (3 jobs on one A100 at $1.99/h): about $0.5–1 expected; worst case 1.75 h = $3.48.
- Campaign spend so far: about $1.85 (NAT sessions 0–2 and the TALKFACE sessions).
- Projection (U4 rule): $1.85 + $3.48 + $61 = $66.3 ≤ $75.
