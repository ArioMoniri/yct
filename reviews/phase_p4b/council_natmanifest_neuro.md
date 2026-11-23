# Council (neuro): NAT manifest pre-freeze (nat_manifest_ready.md, 0feabcb) — APPROVE

- Rule output: confirmed. `data/refstim/nat_manifest.json` sha 2fbe3421…825e equals the reviewed one and HEAD is unchanged since cfc2d48. The 7 tests in tests/test_nat_manifest_ready.py pass, along with nat0/talk/dry-run, 62/62. The manifest equals `nat_manifest(log, cfg)`, is in CPU-rank order, is session-split 4/4/7 and is shuffle-invariant. I also recomputed it: the 15 selected CPU ranks are 12–115 of 120. Every GPU pass is selected, so the "first 15" cut-off decided nothing here.
- Thresholds: every row meets the frozen D-075/D-082 thresholds. p(en) is 0.911–1.0, main speaker 0.955–1.0, and face_present_crop_w is 0.50–1.0. Licences are CC-BY-3.0/4.0 or PD.
- Disclosure: adequate against D-084. It covers the post-hoc continuation and the owner's choice after session 0, per-session N1/N2/N3 counts, 15/120 with a Wilson CI, three sessions on two pods, and the BUG-047 non-launch.
- BUG-047 fix (f92490a tests first, d00871d fix): correct. `gpu_price` raises NoCapacityError as the first preflight step, before any baseline, log row or launch. It maps to exit 75 `no_capacity` in nat0 and talk, the same as the existing launch-time capacity path. p0_rerun and p2b return 75 before spending anything. No frozen key or selection logic changed.
- Freeze plan: Commit A sets the sha, then Commit B adds the frozen row and the guard expectation. This matches the D-084 note "freeze after re-sign-off". Nothing blocks it.

Non-blocking:
1. Add the CPU rank range (12–115 of 120 CPU passes) to §2. D-084 lists it as a v1 disclosure item.
2. In v1, report face_present_crop_w per clip. Four clips sit at 0.50–0.56, near the N3 floor, so the face signal over W is weaker for them. This is descriptive only; the frozen threshold is unchanged.
3. Native short sides of 300–1080 px are all ≥ `stimulus.min_short_side_px` 292. Resolution stays descriptive (D-086).
4. Some rows record the licence as the pattern "PD-*". Confirm that `licence_template` carries the concrete template for attribution.
