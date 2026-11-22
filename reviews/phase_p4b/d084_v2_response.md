# D-084 v2: response to the council (council_d084_*.md)

Verdicts on d084_draft.md: referee, biostat, neuro and QA APPROVE; watchdog REVISE (one blocking item).

| Member | Item | Resolution |
|---|---|---|
| Watchdog (blocking) | §2.6 states the expected cost (~$2.4) as if it were a bound; the enforced worst case is $3.48/session, ~$20.9 for six, which beside the ~$61 main plan exceeds the $75 cap; `guard_launch` checks only spend + this launch | §2.6 now states both figures. New `check_projection` (scripts/gpu_p4b_nat0.py) runs in every k ≥ 1 pre-flight: projection = campaign spend + `controls.refclips_d084.main_campaign_plan_usd` (61.0, d071_v3 §k) + price × max_hours; over $75 → refused, STOP to the owner, before any launch. It is recorded as `pre_launch.projection`. It also refuses once any non-NAT `yct-p4b-ref` launch exists (plan stale). Tests: `test_projection_recorded_in_pre_launch`, `test_projection_over_cap_is_a_stop_before_launch`, `test_projection_refused_once_main_campaign_started`, `test_projection_not_applied_to_session0`. |
| Watchdog (non-blocking) | `failed` status: no re-run without a council note; disclose multi-session/pod provenance | §2.5 and §3 bullets added. |
| Biostat (non-blocking) | `test_session_k_refused_on_overlap` never reached the overlap check | `check_session_k` now checks overlap before the selection's gap check; the test uses a session-0-stage row and asserts "already evaluated" and the id. |
| Biostat (non-blocking) | No direct test of `_finish_k`'s STOP path | `test_finish_k_stops_at_max_sessions`, `test_finish_k_stops_when_snapshot_exhausted` (exit 1, rows logged first). |
| Biostat (non-blocking) | Exhaustion at a buffer boundary refuses with "buffer empty" rather than logging a stop | Stated in §2.5 as the STOP for that case; `test_snapshot_exhausted_at_buffer_boundary_refuses_without_launch`. |
| Biostat (non-blocking) | Report the binomial 95% CI and the cumulative ratio; put the $20.9 next to the $2.4 | §3 bullet (4/40 = 10%, exact CI 2.8–23.7%); §2.6. |
| Referee, neuro, QA | — | No items. |

No frozen key, threshold, order or selection rule changed. `max_sessions` stays 6. Full suite green; ruff,
`make guards` and check_blinding clean.
