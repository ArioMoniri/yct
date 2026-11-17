# P0 cycle 2 — Neuroscientist (fresh context)

I reviewed at HEAD 2a4ef09; the code is that of cef030e. I did not read `data/sealed/`.

**Verdict: GO.** The GPU reruns support D-038 (synthetic clips only):
- **Cached determinism is exact:** p0rerun_20261117T155528Z, A==B==C. p0rel_20261117T163701Z reruns too.
- **Fresh reliability is above the gate:** minimum 0.9997 at 10 s, 0.9995 at 70 s, 0.9913 at 110 s.
- **Offline and pinned in both runs:** V-JEPA2 875c192, w2v-BERT da985ba, Llama 13afe51.
- **One GPU type:** A100-SXM4-40GB.

The items below are documentation or prerequisites for P4/P4b. Not P1/P2 blocking.

## Phase-0 cycle-1 required changes
| Item | Status | Evidence |
|---|---|---|
| P1 measured kernel, no shift | FIXED (spec); derivation DEFERRED-OK (before P4b lock) | config.yaml:280-284 |
| P2 readout lags 0–3 TR | FIXED | config.yaml:286; v2.md:416 |
| P3 min_tail_s 5 | FIXED | config.yaml:25 |
| P4 HCP ROI lists; latency on HCP ROIs | FIXED; recompute DEFERRED-OK | config.yaml:260-267 |
| P5 standardised maps, talking face, MT+ fallback | FIXED (spec) | config.yaml:267, 287-292 |
| P6 A10 conditions | FIXED | v2.md:291-292 |
| Reword "leakage"; add centroid/FWHM | **NOT FIXED** | tribe_requirements.md:163 still says "L = 0 TR … pre-onset leakage via the temporal transformer" |

## New defects
**L1 (major, latency).**
- The documents disagree: §10 (:163) says "L = 0", while v2.md:26 and :51 say "L ≤ 0".
- I recomputed from the smoke ctrlsub CSVs:

  | Course | Half-max span | Positive-mass centroid |
  |---|---|---|
  | Visual | −3…+4 TR | +2.4 TR |
  | Auditory | — | +1.3 TR |

- The peak is at 0, but the response mass lies after onset, so "≤ 0" understates the lag.
- With a centroid L of 2, W would be [7, 47).

**L2 (major for P4). The source of the drift is mis-stated.**
- tribe_requirements.md:114-119 attributes the drift to fp16 backbones.
- In p0rel, the V-JEPA2 and w2v-BERT fresh extractions are bit-identical (max|diff| 0.0). Only the Llama text features drift: max|diff| up to 1.06, minimum reliability 0.9913.
- Drift therefore grows with transcript length and hits the language/H2 features most.

**L3 (major). BUG-018, and a gate that passes broken output.**
- long110 returns (229, 20484), with 552 words, 276 of them after the clip ends. Its gate still reports "pass True", because the gate ignores `T_within_1`.
- T1 (58 s) and T3 are safe: long70 is a single chunk with T = 70.
- T2 is unusable above about 70 s.

**L4 (minor). The evidence is synthetic and partly mislabelled.**
- The clips are testsrc2 + espeak (make_long_clip.py:1-3). v2.md:397 requires ≥ 3 real-like clips, assessed on M1 features and parcel values.
- p0rel report.md:6-8 prints "A==B: False (sha256 None)" for steps that never ran.
- The §10 "Not measured > 60 s" row is stale.

## Required changes
1. **L1:**
   - §10 reads: "peak lag 0 TR; half-max −3…+4; centroid ≈ +2 (visual) / +1 (auditory) TR; pre-onset rise = bidirectional context + 5 s offset, not leakage".
   - Align v2.md:26 and :51 with it.
   - DECISIONS: W = [7, 47) as a pre-specified T1 sensitivity, outside Holm.
2. **L2:**
   - Correct §6: the text extractor is the only nondeterministic one.
   - Gate 2 reports the language-network M1 reliability separately.
3. **L3:** `reliability_gate_pass` also requires `T_within_1` and `words_after_duration == 0`. Add a test on the long110 metrics.
4. **L4, before P4:**
   - Run Gate 2 on ≥ 3 real wave-1 clips chosen label-blind by seeded sha (one > 60 s), M1 + parcel level.
   - Print "n/a" for steps that did not run.
   - Update the stale §10 row.
