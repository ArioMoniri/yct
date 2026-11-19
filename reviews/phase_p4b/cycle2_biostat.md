# P4b design v2: Biostatistician review (council cycle 2)

Reviewed:
- reviews/phase_p4b/cycle1_biostat.md (my cycle-1 items B1–B5, N1–N12);
- reviews/phase_p4b/design_v2.md, including the closing "Owner decisions (2026-11-19)" section;
- reviews/phase_p4b/d071_draft.md;
- config.yaml `controls:`, `seeds:` and `frozen:`;
- src/yct/tribe_run/enh002.py.

The owner decisions are binding inputs here:
- a $75 campaign cap;
- Wikimedia Commons CC0 / PD / CC-BY localiser images;
- MT+ demotion on failure.

Scope respected:
- no AWS;
- no sealed data, labels, data/wave2_pool/ or prediction arrays;
- no commit.

`pytest tests/test_controls_config.py tests/test_enh002_latency.py tests/test_guards_frozen_config.py`: 24 passed.

## Simulation method
All simulations use synthetic data only, and no project data was used.

The model is a full 58-TR control-subtracted course per clip:
- events at [9, 29, 49] + s;
- Gaussian response, peak lag +1, SD 1.5 TR;
- clip courses read at lags −4…+8;
- every rule implemented as written in D-071 (f).

Two noise regimes are simulated, because TRIBE is deterministic and the matched control is identical to the clip outside events:
- **A ("AR")**: AR(1) ρ = 0.7, unit SD at every TR, with a fixed event amplitude d. This is pessimistic, and it is the cycle-1 model.
- **B ("jitter")**: each exemplar's amplitude is drawn as N(d, 1). Outside responses there is only small AR noise (SD 0.1). This is the deterministic-input view: the variance comes from exemplars, not from TRs.

A variant, **Bs**, has the 3 events of a clip share one exemplar, so the variance sits at the clip level.

Effect sizes are in units of the per-event SD at the peak. Each cell has 600–4,000 reps.

The scripts are in the session scratchpad (`sim_k.py`, `sim_k2.py`, `sim_conj.py`, `sim_conj2.py`, `sim_d.py`, `sim_k5.py`). They are not committed.

## Verdicts

1. **Commit D-071 as written: NO-GO.**
   - The draft contradicts itself on MT+: (j) says "Q6 = hard STOP" while (g) demotes MT+.
   - Three rules (K3, K3′, K6) refer to a "peak" that, under its own kernel definition, is identically 1.
   - The hard-STOP AUD kernels are run at a power that makes a false STOP the most likely outcome.
   - **GO to commit once items B6–B11 below are folded into the D-071 text and config.** These are text and threshold edits plus +22 clips (≈ +$9.5, total ≈ $52, under the $75 cap). If they are adopted as written here, no further full council cycle is needed. Any other resolution returns to the council.
2. **Build the tickets and launch the reference-clip GPU job: GO-with-conditions.**
   - Building the tickets: GO once the amended D-071 is committed.
   - Launch: GO when all of the following hold:
     - every G ticket is closed on a pushed, CI-green commit;
     - T-KERNEL implements the amended rules, with the operating-characteristic tests in N13, under BOTH noise regimes;
     - the ENH-002 known-data check has run and been disclosed;
     - T-D071 freezes the corrected config (N20), including a bootstrap seed;
     - the cost re-estimate with the added clips is recorded at or below $75, together with the cap-scope statement (N18).
   - I do not need another review of the diff, provided those tests exist and pass.

## Cycle-1 items

**B1: clips and exemplars per gating kernel. PARTIAL.**
- Closed:
  - FFC has 20 LOC clips, MT_plus 10 MOT clips and AUD 10 SPK clips (≥ 8 each);
  - every gating event has a distinct exemplar (30 utterances; one face per LOC clip);
  - the unit of replication is the clip. This correctly answers my pseudo-replication point.
- New problem: moving K1 to clip means at α = .001 leaves n_t = 5 for AUD and MOT, with t(4) > 7.17. That is less power than v1's event-level test. K1 pass rates, simulated:

  | kernel (clips, events per clip) | d = 1 | d = 1.5 | d = 2 | null |
  |---|---|---|---|---|
  | FFC (20, 1), t + all > 0 (as written) | 0.11–0.15 | 0.45–0.48 | 0.77–0.81 | 0.000 |
  | FFC (20, 1), t only | 0.21–0.24 | 0.63–0.68 | 0.92–0.94 | 0.002 |
  | AUD/MOT (10, 3 distinct) | 0.12–0.14 | 0.36–0.38 | 0.63–0.66 | ≤ 0.003 |
  | MOT (10, 3 sharing one exemplar, Bs) | 0.03 | 0.09 | 0.20 | 0.000 |
  | AUD/MOT (16, 3) | 0.51–0.58 | 0.93–0.96 | ≈ 1 | 0.000 |
  | AUD/MOT (20, 3) | 0.79–0.83 | ≈ 1 | 1 | ≤ 0.001 |
  | AUD/MOT (10, 3), α = .01 | 0.54–0.60 | 0.90–0.93 | ≈ 1 | 0.009–0.013 |

- For FFC, "every test-half clip mean > 0" costs about 0.18 in power, because each clip mean is a single event: Φ(1)^10 ≈ 0.18 at d = 1.
- See B6 for the fix.

**B2: K4 non-diagnostic. CLOSED.**
- K4a (median LOCO held-out r ≥ 0.5) and K4b (split-half r ≥ 0.7) are adopted verbatim, and T-KERNEL lists a null test.
- Re-simulated under the AR null: K4a passes 0.001–0.016 and K4b 0.02–0.03.
- At d = 1.5 they pass 0.78–1.0 (K4a) and 0.87–1.0 (K4b).
- FFC's K4a is the weakest case (0.21 at d = 1 under AR), because each held-out FFC clip is a single event.
- Caveat for T-KERNEL (N13): under a zero-mean jitter null (regime B, d = 0), K4a and K4b pass 0.33–0.52. They test whether the shape is consistent, not the sign of the mean, so in that regime K1 is the only guard. The conjunction null stays ≤ 0.002.

**B3: K3 SNR. CLOSED.**
- My formula is adopted as written: the across-clip variance at lags −4…−2, divided by n.
- Null pass rate: 0.007–0.022. At d = 1: 0.90–0.98.
- One gap is left: "peak" is undefined. It is carried into B7.

**B4: exact specification. PARTIAL.**
- Adopted:
  - even/odd halves;
  - p* = signed argmax of the selection-half mean;
  - K1 on the test half only, with a clip sign check;
  - K2 on both p* and the full-data argmax;
  - K5 sign agreement;
  - all of these frozen in config before any output exists.
- Still missing:
  - the quantity behind "peak" in K3, K3′ and K6 (B7);
  - behaviour when max(mean course) ≤ 0, which makes the signed normalisation divide by a non-positive number (B7);
  - the K2 50%-crossing definition (B7);
  - the K3′ span set (B8);
  - the bootstrap method and seed for (d) (N17);
  - the halves are perfectly aliased with the onset shift (B10);
  - the config values are stale (N20).

**B5: stimulus-set decisions. CLOSED, with one residual item.**
- (i) Body category: added, with a 20-exemplar floor.
- (ii) Localiser images: settled by the owner decision (Wikimedia CC0 / PD / CC-BY).
- (iii) NAT: 15 clips, and P10 is fixed (numpy linear percentile, ddof 1). The fallback n = 15 matches `min_videos`.
- (iv) Audio-only and text-only reference predictions ride in the same campaign, from the D-038 cache.
- Residual: the Commons candidate pool for the images is undefined (B11). D-071 (b) also curates an "object" category that no family uses.

**Cycle-1 N items.**
- N1, N2, N3, N5, N6, N7, N10 and N11: CLOSED as adopted.
- N4: CLOSED by the alternative route. Impulse-length 1.0–1.5 s utterances replace bursts for the kernel, and BURST validates kernel ⊗ envelope.
- N8: CLOSED. Route blocks are dropped, so no per-block statistics.
- Q4: on route blocks I defer to the council majority. The conjunction "unrestricted AND era_block" is a conservative gate, and I accept it.
- N9: PARTIAL. `seeds.controls_perm` is added, but there is no bootstrap seed for (d) (N17).
- N12: OPEN. T-CTRL's planted-effect test should use a realistic, small within-video face SD (talking heads). This is unchanged and non-blocking.

## New blocking items

**B6. K1 power on hard-STOP kernels. Blocks the D-071 commit (it changes clip counts and thresholds).**
- AUD is hard STOP twice: the full model and audio-only, both on the same 10 SPK clips.
- With the design as written, a single gating kernel passes all of its K rules with probability:

  | kernel | regime | d = 1 | d = 1.5 | d = 2 |
  |---|---|---|---|---|
  | AUD | AR | 0.04 | 0.21 | 0.47 |
  | AUD | jitter | 0.14 | 0.39 | 0.66 |
  | FFC | AR | 0.02 | 0.27 | 0.66 |
  | FFC | jitter | 0.14 | 0.46 | 0.77 |

- At d ≤ 1.5, a P4b STOP that comes from power, not from the pipeline, is the expected outcome, and it would use up the one permitted redesign.
- The motion spec also contradicts itself: "directions 0/45/…/315° (10 distinct)" lists 8 values, and the pattern is static for the whole clip. So it is unclear whether a clip's 3 events share one exemplar. If they do, the clip is one exemplar (row Bs above): K1 ≈ 0.09 at d = 1.5, and demotion of MT+ becomes near-certain for a power reason.
- Required (my preferred package, Option B′):
  1. **K1 at the clip level uses α = .01 for every kernel.** The unit is now the clip, and the p-value measures consistency across exemplars (as D-071 itself discloses). The conjunction null stays ≤ 0.007 in both regimes.
  2. **The FFC sign check becomes "≥ 80% of test-half clip means > 0"** (8 of 10). It stays "all > 0" for 3-event clip means, where it costs nothing.
  3. **SPK is raised to 20 clips** (60 distinct utterances; n_t = 10).
  4. **MOT is raised to ≥ 16 clips, each with its own static twin.** Every event uses a distinct pattern × direction (state the direction set exactly; 8 directions × 2 pattern types × distinct seeds is fine).
- All-rule pass rate per kernel with B6 + B8 + B10, simulated:

  | kernel | regime | d = 1 | d = 1.5 | d = 2 |
  |---|---|---|---|---|
  | FFC (20, α = .01) | AR | 0.13 | 0.70 | 0.96 |
  | FFC (20, α = .01) | jitter | 0.61 | 0.94 | 0.995 |
  | AUD (10, α = .01) | AR | 0.38 | 0.87 | 0.98 |
  | AUD (10, α = .01) | jitter | 0.60 | 0.92 | 0.99 |
  | AUD (20, α = .001) | AR | 0.72 | 0.98 | 0.99 |
  | AUD (20, α = .001) | jitter | 0.82 | ≈ 1 | 1 |

  - AUD at 20 clips with α = .01 is at least as high as the α = .001 row.
  - Null: ≤ 0.007 in every configuration.
- Cost:
  - +10 SPK, +6 MOT and +6 MOT-STAT = 22 clips at ≈ $0.43 per clip. That rate is v2's own $42 / 98 and includes session overhead.
  - So ≈ +$9.5, for a campaign of ≈ $52, under the $75 cap.
- Option A (keep α = .001) instead needs SPK 20, MOT 20 + 20 and LOC 30 + 30 ≈ $63. FFC would then be 0.80 (AR) / 0.94 (jitter) at d = 1.5. That leaves only about $12 of headroom.

**B7. "Peak" is undefined in K3, K3′ and K6. Blocks the D-071 commit.**
- k = mean / max(mean), so the kernel's peak is identically 1.
- Taken literally:
  - K3 tests 1 / SE;
  - K3′ tests |baseline| ≤ 0.10 in kernel units;
  - K6 compares a unitless 1 with a standardised FLASH amplitude, which is meaningless.
- Required (one definition, used everywhere): peak := m_full(p*), the un-normalised, control-subtracted, standardised full-data mean course at p*.
  - K6: m_MOT,full(p*_MOT) > mean over lags 0–3 of m_FLASH(lag), both in MT_plus on the standardised map. Report a clip-bootstrap CI of the difference (N16).
  - Normalisation: if m_full(p*) ≤ 0, the result is FAIL, not a division.
  - K2 crossing: the smallest lag ℓ in [−4, argmax] with m_full(ℓ) ≥ 0.5·m_full(argmax), on the integer lag grid without interpolation, from the full data. The tail rule "mean over lags 0–3 ≥ 0.5·peak" uses the same peak.

**B8. K3′ (a 10% baseline bound with no allowance for imprecision) is a false-STOP generator under AR noise. Blocks the D-071 commit.**
- K3′ pass rate at true return-to-baseline:
  - AR regime: 0.39–0.57 at d = 1, 0.57–0.77 at d = 1.5, 0.72–0.87 at d = 2;
  - jitter regime: ≈ 1.
- The spans hold only 8 TRs per clip, so the baseline mean has SE ≈ 0.2–0.27 against a bound of 0.1·d.
- Required:
  - K3′ FAILs only for a demonstrable sustained offset: |span mean| > 0.10·peak AND a two-sided one-sample t over per-clip span means gives p < .01.
  - Simulated: ≥ 0.985 at d ≥ 1 in both regimes. It still catches a real offset, because a real offset is consistent across clips.
  - Define the spans exactly: [o_i + 12, o_{i+1} − 5] for events i = 1, 2 of each clip (8 TRs per clip). There is no span before the first event and none after the last.

**B9. D-071 contradicts itself, and contradicts the owner decision. Blocks the D-071 commit.**
- (j) says "Q6 = hard STOP", but (g) says MT_plus is demoted on failure.
- (g) says "the motion (a)/(c) controls do not gate", but (c) has no motion pair. It should say "(a)-motion, and MT_plus in K6".
- (k) still carries the $42 estimate. It should be re-estimated after B6.
- Design §3.2 and §3.4 still say "no demotion path". The owner section overrides them, but D-071 is the frozen text and must be self-consistent: replace (j) Q6 with "pre-registered MT_plus demotion per (g); FFC and AUD hard STOP".

**B10. The onset shift is aliased with the halves. Blocks T-REF58 (it changes clip inputs).**
- s = 0 for even clip indices and −1 for odd ones, and the halves are even/odd. So every selection clip has s = 0 and every test clip has s = −1.
- Any effect tied to absolute time (encoder warm-up, chunking, position) then becomes a selection-vs-test difference that K1, K4b and K5 absorb.
- In simulation, an artefact present only on s = −1 clips moved K1 from 0.33 to 0.69 (AUD, d = 1.5), purely through the aliasing.
- Required:
  - s = 0 if (index // 2) mod 2 = 0, else −1, so that each half holds both shifts;
  - balance the LOC Latin-square rows across halves (with 20 clips the rows split 4/3/3 against 3/4/3; use a block order that is balanced per half);
  - a T-REF58 test asserting both balances.

**B11. The image and NAT candidate pools are undefined. Blocks the D-071 commit (the selection rule is part of what is frozen).**
- "The first 20 by sha256 of the file title that pass" is mechanical only if the candidate list is fixed first. Otherwise the curator's search defines the population, which is a forking path even without labels.
- Required in D-071 (b) and (c):
  - the exact Commons categories or search strings;
  - the API query and retrieval date;
  - the sha256 of the full candidate list, frozen before filtering;
  - every candidate examined up to the k-th accept, with its pass or fail reason, recorded in the manifest.
- Also fix two inconsistencies:
  - drop the "object" category or give it a stated use;
  - align the design §1.2 text ("sorted file name") with the owner rule (sha256 of the file title).
- If B6 Option A is chosen, the per-category count rises to 30.

## New non-blocking items

**N13. T-KERNEL operating-characteristic tests.**
- State both null models: AR noise with no response, and zero-mean exemplar jitter.
- "Per-rule null pass < 0.05" holds for K1, K3, K4a and K4b only under the AR null. K2 has a null pass of 0.08–0.13 and K3′ of 0.07–0.33, which is expected because they are timing and shape rules.
- Test the conjunction null at < 0.01 under both nulls.
- Report the per-kernel all-rule pass table above, for the frozen clip counts, in the ticket PR.

**N14. Report end-to-end gate power.**
- Three hard-STOP kernels (FFC, AUD-full, AUD-audio-only; the two AUD kernels are highly correlated), plus (a) ×3, (b) ×2, (c) ×2 and (d).
- T-CTRL already reports the end-to-end pass probability. Extend it to include the K stage.

**N15. K5.**
- Pass rate in simulation: 0.66–0.89 at d = 1 and 0.83–0.96 at d = 1.5 (the correlation between raw and standardised noise ranges from 0.7 to 0.95). Most of the loss comes from p* disagreement, not from sign.
- The simulation does not model systematic differences between raw and standardised maps, such as removal of the global signal under speech or flash.
- Acceptable as written. Optionally, restrict the sign check to lags where |m_std| ≥ 0.25·peak.

**N16. K6 has no uncertainty allowance.**
- At a true MOT-minus-FLASH difference of 0, it is a coin flip.
- Acceptable only because MT_plus is demotable. Report the difference with a clip-bootstrap CI, and name the failing rule if MT+ is demoted.

**N17. Specify the (d) rule.**
- The bootstrap is a percentile bootstrap over clips, B = 10,000, with a new key `seeds.controls_boot` in `seeds:` and in `frozen:`.
- The CI applies to BOTH contrasts of each ROI in each hemisphere.
- State explicitly that PH's (d) contrasts gate even though the PH kernel is descriptive.
- The per-hemisphere vertex counts that design §4(d) says are "listed in D-071" are not in the draft. Add them; they are label-free atlas counts.
- Simulated (20 clips; δ in per-clip SD units; correlation between left and right noise 0.5–0.9):

  | δ | FFC passes | PH passes | gate (both) passes |
  |---|---|---|---|
  | 0 (null) | ≤ 0.012 | ≤ 0.008 | 0.000 |
  | 0.8 | 0.39–0.53 | 0.50–0.57 | 0.19–0.32 |
  | 1.0 | 0.67–0.70 | 0.77–0.78 | 0.54 |
  | 1.5 | 0.96–0.97 | 0.99 | 0.95 |

  This is adequate if δ ≥ 1.5; disclose the curve.

**N18. Cap scope and redesign.**
- State whether the $75 cap covers v1 only or v1 plus the one permitted `p4b_ref/v2`. At ≈ $52 for v1, a v2 cannot fit under a shared cap.
- A v2 redesign may change stimuli only. The K rules and thresholds stay those of D-071, so that a second attempt does not become a second forking path.

**N19. MT+ demotion.**
- Statistically acceptable, because it is pre-registered before any output exists.
- Without B6's MOT increase, demotion has probability ≈ 0.6–0.9 at d ≤ 1.5. The motion control would then be lost to low power, and that cause should be named in the report if it happens.

**N20. Stale config must be corrected in the T-D071 commit, before freezing.**
- `controls.kernel.min_reference_clips: 5` and `controls.dry_run.reference_clips_min: 5` are stale.
- The comment on `controls.pass.min_videos` says "≥ 5 reference naturalistic clips", where the value is now 15 NAT clips.
- The comment on `low_sd_percentile` says "reference clips", where it is now NAT, linear, ddof 1.
- `controls.pass` has no keys for the (c) conjunction (unrestricted AND era_block) or for the (d) CI rule.
- The K-code must read every threshold from config only, as T-D071 already says.

**N21. The P10 cutoff is noisy at n = 15.**
- P10 of 15 NAT values interpolates between the 2nd and 3rd order statistics. Disclose this.
- The (a) fallback at n = 15 needs t(14) > 3.79, which is fine.

## Summary of status
| item | status |
|---|---|
| B1 | PARTIAL → B6 |
| B2 | CLOSED |
| B3 | CLOSED (peak definition → B7) |
| B4 | PARTIAL → B7, B8, B10, N17, N20 |
| B5 | CLOSED (candidate pool → B11) |
| New blocking | B6–B11 (D-071 text/config/clip counts; B10 before T-REF58) |
| New non-blocking | N13–N21 |
