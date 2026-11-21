# D-079 final sign-off: response (wf_7797c743-b64)

Watchdog, Biostat and Neuro: APPROVE. Referee and QA: REVISE. Changes are in d079_v3.md §H.

| Member | Item | Resolution | Where |
|---|---|---|---|
| Referee | B1: byte-stage mismatch is a download defect, not identity_changed | Delete, re-download once, STOP naming the title if still different; identity_changed only at the metadata stage | `ra.fetch_verified`; runner `load()`; tests `test_bad_bytes_*`, `test_stale_cached_file_is_redownloaded`, `test_byte_stage_is_never_an_identity_reject_in_runner` |
| Referee | B2: §A disclosure not implemented | `finalise` writes `image_identity_changed_v2.json` (list or "none"); a row without stage/data sha1 STOPs | `ra.identity_disclosure`; tests `test_identity_disclosure_*`, `test_finalise_writes_identity_disclosure` |
| QA | B1: identity_changed rows lack stage and bytes sha1 | Rows log `identity_stage` ("metadata") and `data_sha1` (null: no download at that stage); the byte stage no longer produces rows | `ra.identity_reject_row`; tests `test_identity_reject_row_logs_stage_and_data_sha1`, `test_identity_reject_row` (stricter) |

Nothing is frozen and DECISIONS D-079 is not written; the freeze commit follows the sign-off of these two items.
