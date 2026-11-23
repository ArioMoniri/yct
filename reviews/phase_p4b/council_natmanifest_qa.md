# Council QA: NAT manifest pre-freeze (D-075 §3, D-084) — APPROVE

- Rule output: independent recompute from committed `nat_auto_log.jsonl` gives 120 GPU rows = CPU ranks 0–119 (no gap/dup); selected ranks 12…115 = all 15 passes, in CPU-rank order; manifest equals `ns.nat_manifest(log, cfg)`. File sha256 = 2fbe3421…825e (matches record and test).
- Log append-only: each of the last 4 log commits (9aa1090→03de683→b1356ce→0bac6cb→cfc2d48) is a byte prefix extension of the previous.
- Tests: `pytest tests/test_nat_manifest_ready.py tests/test_nat_d084.py` 42 passed; `make guards` rc 0 (no test weakening, guard config unchanged).
- Pass-rate table sums (48+41+16+15=120); Wilson 95% CI for 15/120 rechecked = 7.7–19.6%.
- Disclosure (§3): post-hoc D-084 rule, owner decision after 4/40, max_sessions chosen post hoc, multi-session/multi-pod origin, BUG-047 aborted launch — adequate.
- BUG-047 (f92490a tests first, d00871d fix): `gpu_price` raises NoCapacityError before any launch/log write; nat0 and talk return 75/no_capacity; p0_rerun/p2b return 75. Correct; tests cover nat0 and talk.
- Freeze plan: Commit A sets the sha, Commit B adds `frozen:` row + guard expectation; `test_manifest_sha_is_the_reviewed_one` accepts null or the sha, so A passes CI. No blocker.
- Non-blocking: the v1 report must also state the CPU rank range of the selected clips (12–115 of 0–119), required by D-084 "Disclosed in v1" and absent from nat_manifest_ready.md; `ns.load_log` needs a Path (str crashes) — cosmetic.
- Not read: data/sealed, labels, transcript text, predictions.
