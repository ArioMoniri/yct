# NAT manifest: pre-freeze record for the council (D-075 §3, D-084)

Status: the NAT selection is complete (15 of 15). `data/refstim/nat_manifest.json` (cfc2d48) has sha256
`2fbe3421696d37a027d13dcf7d8b9116fa607b07a6e7ad3919fe5b6848da825e`. Nothing is frozen yet; the two-commit
freeze below waits for the council.

## 1. Validation against the frozen rules (tests/test_nat_manifest_ready.py, 7 tests, all pass)
- The committed manifest equals `natstim.nat_manifest(log, cfg)` recomputed from the committed append-only
  log `data/refstim/nat_auto_log.jsonl`, row for row.
- It is the first 15 GPU passes by CPU rank across sessions 0–2 (D-084): ids in CPU-rank order, equal to the
  rank-sorted pass list truncated at `nat_n` 15. Here every pass is selected (15 passes in 120 evaluated).
- Selection invariance: shuffling the GPU rows (5 seeds) gives the same selection; a duplicate evaluation or
  a gap in the evaluated CPU prefix is a STOP (both tested).
- Every row has non-empty title, pageid, read_revid, url, source sha1/sha256, t1_name, t1_sha256, wav_sha256,
  attribution, licence and template, session and the N1/N2/N3 values. Each licence is in
  `controls.refclips.image_licences`. Each row meets the frozen thresholds: p(en) ≥ 0.9, main speaker ≥ 95%,
  other speakers ≤ 3 s, face_present_crop over W ≥ 0.5.
- No outcome word (the `check_blinding` OUTCOME_WORDS pattern) in any row's title, url or attribution.

## 2. Pass rates (for the v1 report)
| Session | Evaluated | N1 reject | N2 reject | N3 reject | Pass |
|---|---|---|---|---|---|
| 0 | 40 | 18 | 12 | 6 | 4 |
| 1 | 40 | 15 | 15 | 6 | 4 |
| 2 | 40 | 15 | 14 | 4 | 7 |
| Total | 120 | 48 | 41 | 16 | 15 |

- GPU-stage pass rate: 15/120 = 12.5%, Wilson 95% CI 7.7–19.6%.
- CPU stage: 234 candidates checked, 120 passed (rejects: licence 69, YC link 27, too short 15, personality
  rights 3).
- Spend for sessions 0–2: about $0.39 + $0.35 + $0.49 = $1.22 (counted in the $75 v2 cap).

## 3. Disclosure (post hoc, D-084)
- Session 0 passed 4 of 40, under the frozen D-075 rule of 15 in one 40-buffer, which was a STOP to the owner.
  The owner chose "continue same list" after seeing that result. D-084 fixed the continuation rule in advance
  of sessions 1–2 (same filters and order; full-buffer evaluation; first 15 by CPU rank; max_sessions 6, chosen
  after seeing the 10% rate). Two sessions were needed. The report states this, the pass rate and its CI, and
  that the NAT set comes from three sessions and two pod CPU runs.
- The first launch attempt of session 2 found the A100 type briefly missing from the Lambda list and exited 1
  on a KeyError before launching anything (BUG-047, now exit 75). No spend, no rows.

## 4. Prepared freeze (not committed; the council checks first)
- Commit A: `config.yaml` `controls.refclips_artifacts.nat_manifest_sha256:
  2fbe3421696d37a027d13dcf7d8b9116fa607b07a6e7ad3919fe5b6848da825e` (replacing `null`).
- Commit B: `frozen:` row `{key: controls.refclips_artifacts.nat_manifest_sha256, frozen_at: <commit A>}`
  and, in `tests/test_guards_frozen_config.py`, the expected row
  `("controls.refclips_artifacts.nat_manifest_sha256", "2fbe3421…825e")` next to `image_manifest_sha256`.

## 5. NAT clip build: dry run (read-only, pod CPU, numbers only)
The NAT reference clips are the 15 rows' trimmed T1 clips, built by P1/P2/P2b/P3 exactly as the analysis T1
(D-071 (c)); `refclips58`/`refclips_build.py` refuse NAT by design. What the D-071 (d) clip-manifest step
needs, per slot `nat_00`…`nat_14` in manifest order:
- the T1 mp4 (sha256 = `t1_sha256`) and the 16 kHz wav (sha256 = `wav_sha256`), on the pod in
  `/work/yct/nat_scratch/t1/` and on S3 under `s3_root/nat_t1/`;
- the T1 record json;
- the P2b transcript (`/work/yct/nat_asr/asr/<t1>.json`, synced to `s3_root/nat_asr/`), whose sha the GPU box
  gates as `transcript_sha256`;
- no events tsv (NAT has no events; the readout uses the frozen window W).

`scripts/nat_clips_dryrun.py` (tests/test_nat_clips_dryrun.py) ran on the pod against the committed manifest
(sha matched): 15 of 15 rows have the mp4 with matching sha, the wav with matching sha, the record and exactly
one transcript; no problems. All 15 mp4s are 58.000 s, 30/1 fps, h264 + aac 48 kHz; short sides range 300–1080
px (native T1 sizes; V-JEPA2 resizes). Record: `outputs/runs/nat_clips_dryrun/record.json` (shas and stream
facts only; no transcript text read).

Remaining for the build after the freeze: add the 15 NAT entries (mp4, wav, transcript shas) to the full
`refclips_manifest.json` together with the visual and speech families, then set and freeze
`controls.refclips_artifacts.manifest_sha256` (D-071 (d)), then upload the manifest objects.

## 6. Council non-blocking items (5/5 APPROVE, council_natmanifest_*.md)
- **CPU rank range:** the 15 selected ids sit at CPU-pass ranks 12, 28, 31, 34, 46, 51, 56, 73, 82, 83, 90,
  102, 110, 114, 115 (of ranks 0–119): range 12–115.
- **face_present_crop_w per clip (v1 report):** reported per clip. Sorted: 0.500, 0.500, 0.537, 0.550, 0.562,
  0.650, 0.688, 0.725, 0.738, 0.750, 0.812, 0.875, 0.938, 0.988, 1.000. Four clips sit at 0.50–0.56, just at
  the frozen N3 floor of 0.5.
- **PD-* rows: the recorded licence_template is NOT concrete.** All 8 PD-* rows record
  `Template:PD-Layout`, the generic layout helper that every PD template transcludes. `refstim.licence_of`
  takes the first `PD-` template in page order, and PD-Layout sorts first. Admissibility is unaffected: each
  row's full logged template list carries a concrete PD template, so the selection is unchanged. The concrete
  template per row (from the committed log's `templates`, excluding PD-Layout and `/`-subpages):

  | Slot | t1_name | Concrete template |
  |---|---|---|
  | nat_02 | 564c3eba65354c05 | Template:PD-USGov-VOA |
  | nat_04 | 567874498d6d1fb5 | Template:PD-USGov-VOA |
  | nat_06 | e892cafec1353bfb | Template:PD-US-Longines |
  | nat_07 | 7aefedfb534a235d | Template:PD-USGov-NASA |
  | nat_08 | 088a2be4f7fa89c6 | Template:PD-USGov-VOA |
  | nat_10 | 7601fee519651165 | Template:PD-USGov-NASA |
  | nat_11 | 65956af7c4b852e6 | Template:PD-USGov-HHS-CDC |
  | nat_12 | ce9f9db3d604cf4f | Template:PD-USGov-VOA |

  The NAT manifest is frozen as-is (editing it would be a post-selection change). The full clip manifest and
  LICENSES.md carry the concrete template, derived by this fixed rule from the committed log. Logged as
  BUG-048. The frozen `licence_of` is unchanged. The same label defect is in the frozen image manifests (v1 and
  v2: 4 of 5 body, 1 of 8 face, 5 of 5 place PD rows record PD-Layout); admissibility is unaffected there too,
  and the clip manifest / LICENSES.md take the concrete template by the same rule.
