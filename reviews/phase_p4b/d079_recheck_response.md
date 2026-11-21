# D-079 re-check: response matrix (workflow wf_4ef7126f-cea)

| Member | Verdict | Item | Resolution | Where |
|---|---|---|---|---|
| Biostat | REVISE | B1: state in advance how every non-defect STOP is resolved | Identity mismatch becomes a D1 `identity_changed` reject and the run resumes at the next rank. A revision moving within a batch is retried once, then a STOP to the council. Any other audit STOP is a code defect: BUG entry, then v3 from rank 1. | d079_v3 §A, §B; `controls.refclips_d079.stop_resolution`, `identity_rule`, `extra_reject_reasons`; `ra.identity_ok`, `ra.identity_reject_row`, `rs.page_meta_c4`, `rs.RevidMovedError`; runner |
| Biostat | REVISE | B2: `duplicate` exempt only if the other reason is not C1 | Done; both listed cases are now STOPs | d079_v3 §C; `ra.audit_v2`; tests `test_v1_duplicate_vs_v2_c1_reject_is_a_stop`, `test_unlisted_v1_c1_reject_vs_v2_duplicate_is_a_stop` |
| QA | REVISE | B1: `preload_v2` strict on `log_version` | No default; tested with a real v1-shaped row (no key); the 3 committed v1 logs are confirmed to carry no key | d079_v3 §E; `ra.preload_v2`; `test_preload_refuses_v1_shaped_row_without_log_version`, `test_real_v1_logs_have_no_log_version_key` |
| QA | non-blocking | STOP messages include the title | Done | d079_v3 §F; `test_stop_messages_name_the_title` |
| QA | open question (b) | STOP rather than reject | Superseded by Biostat B1: a reject, stated in advance. The frozen reason list is amended, not edited. | d079_v3 §A |
| Watchdog | APPROVE | N1: state in advance how a drift-audit STOP or identity STOP is resolved | Same as Biostat B1 | d079_v3 §B |
| Watchdog | APPROVE | N2: strict `log_version` | Same as QA B1 | d079_v3 §E |
| Watchdog | APPROVE | N3: C4 extmetadata revision | `prop=info` on the C4 query; lastrevid must equal `read_revid`, otherwise the §B revision-move rule applies | d079_v3 §D; `test_page_meta_c4_compares_extmetadata_revision_with_read_revid`, `test_page_meta_c4_requests_info_on_the_extmetadata_query` |
| Watchdog | APPROVE | N4: frozen-config test rows in the freeze commit | Kept for the freeze commit, after the second re-check | d079_v3 §G |
| Referee | APPROVE | owner resolution stated by rule, not per image | Covered by the §B rules; no STOP is resolved one title at a time | d079_v3 §B |
| Neuro | APPROVE | any resolution applies from rank 1 (a v3), not to one title | `other_audit_stop` means v3 from rank 1; an identity reject is a fixed rule applied at every rank | d079_v3 §B |
| All | open question (a) | revid-drift files stay non-exempt | Kept | d079_v3 §G |

Not done, as instructed: no freeze rows, no DECISIONS D-079 and no v2 run. The next step is the second
re-check by the two REVISE members, Biostat and QA.
