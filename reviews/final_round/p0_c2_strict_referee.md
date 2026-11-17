# Phase 0 cycle 2 — Strict Referee (fresh, adversarial)

**Scope.** Commit 31235e6, CI run 55. I read runs p0rerun_20261117T155528Z and p0rel_20261117T163701Z (report.md, summary.json). I did not open data/sealed/.

## Verdict: GO. P0 closes; P4 is BLOCKED until B1–B5 are done.

The P0 claims hold: shape, TR, offline pinned backbones, a bit-identical cached rerun, and fresh-extraction reliability ≥ 0.991. The remaining items are P4 prerequisites.

## Prior required changes

1. **BUG-003 — FIXED.**
   - Code: offline.py:30,59–83; run_clip.py:52,84,172; tests/test_tribe_offline.py.
   - Run: the p0rel report shows refs/main equal to the pinned revision for all 3 backbones, with offline=True.
2. **Determinism spec — FIXED (spec).**
   - Spec: v2.md:395–398; one GPU type (v2.md:291); M0b reads the same cache.
   - Gate 1 passed in p0rerun_155528Z (report.md:9).
   - Gate 2 evidence does not meet the spec; see N1.
3. **Prereg statement — FIXED** (v2.md:398). **Second-extraction sensitivity — DEFERRED-OK.** It is replaced by Gate 2, but only once Gate 2 is applied to M1 (N1).
4. **P4b redesign — FIXED (spec); execution DEFERRED-OK.**
   - Spec: v2.md:400–417; config.yaml:258–286; test_controls_config.py.
   - The ENH-002 dry run has not been done yet.
5. **5 s exclusion margin — FIXED.** v2.md:51; ROADMAP.md:129. It excludes 1 of the 53 analysis rows (duration < 50 s).
6. **Timing sentence — FIXED.** v2.md:26; see the N3 caveat.
7. **Off-pod archive of P0 artifacts, with the location in §10 — NOT FIXED.**
   - tribe_requirements §10 gives no location.
   - The p0rel report puts the artifacts only on the pod (`/work/yct/…`).
   - D-038 requires them off the pod.

## New defects

**N1. Gate 2 was not tested as specified.**
- v2.md:397 requires ≥ 3 *real-like*, seeded clips and reliability ≥ 0.99 for *every M1 feature and the parcel values*.
- What p0rel actually did:
  - it used 3 synthetic clips;
  - it gated on backbone arrays and the whole-map r, with no M1 or parcel reliability;
  - one of the clips, long110, is the BUG-018 broken case: (229, 20484), "T ok False".
- Separately, the drift comes from the Llama text features (max |diff| 1.06), not from V-JEPA2.

**N2. An absent step is reported as a failure.**
- The p0rel report says "bit-identical A==B: **False** … (sha256 None)", but that step never ran there (cache_reused=None).
- The cause is scripts/p0_rerun_report.py:34, which maps a missing sha to False.
- A reader would take this as a Gate 1 STOP.

**N3. The latency wording understates the leakage.**
- In cycle 1, the response to a 15 s flash rose at 11–12 s, i.e. 3–4 TR early.
- v2.md:26 and D-039 say "±2 TR".

**N4. The talking-face / acoustic latency is still unmeasured.** P4b(a)/(b) rely on it.

## Required changes (P4 blockers)

- **B1.** Store the feature cache and the P0 artifacts off the pod, content-addressed, with a sha256 manifest. Record the location and the manifest hash in §10.
- **B2.** Rerun Gate 2 on ≥ 3 real wave-1 T1 clips chosen by seeded sha. Report reliability for M1 and the parcels. Drop clips that fail the T check.
- **B3.** Make the report print "NOT RUN" for a missing step, and add a test for it.
- **B4.** Change v2.md:26 to "response can begin up to 4 TR before the event; ±4 TR", and record it in a new DECISIONS entry.
- **B5.** Run the ENH-002 dry run (latency CI) before the P4b lock. Fix BUG-018, or restrict P4 to T1/T3.
