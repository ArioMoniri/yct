# G-D032 — Strict Scientific Referee (red team)

Reviewed at 529652d; data/sealed/ and the other reviews were not read.

**Vote: FIX.** The code matches its docstrings; the protocol leaves the interpretive choices open.

## (1) T3 photometric track

The concept is sound: V-JEPA2 sees global brightness, colour and contrast, and audio and text are untouched, so T1 vs T3 isolates photometric signal that enters through vision. Defects:

- **D1. "Survives" is undefined** (v2.md:97). There is no criterion, family or rule for T1 null + T3 positive, which is a forking path.
- **D2. M0, W and Q(M0) on T3 are unspecified** (v2.md:96). M0 contains luminance and contrast (ROADMAP.md:99). If they are recomputed on T3 they become near-constant, Q changes rank, and H4-T3 becomes a different estimand.
- **D3. Gain is unbounded, and clipping has no consequence.**
  - photometric.py:94 applies `a = target/rms` uncapped. Dim webcam clips get a ≈ 3–5, and the 8-bit lutrgb (l.121–126) amplifies blocking and posterises.
  - The `clipping` flag (l.119, core.py:529) has no defined effect.
  - Gain and clipping plausibly track era and device, and therefore group. This is a group-correlated artefact.
- **D4. Minor.** T3 is a second lossy encode (photometric.py:144). "Luminance" here is gamma-encoded luma Y′.

## (2) Localisation

The "descriptive only" firewall lives only in docstrings. It is not enforceable.

- **D5. No caption travels with the outputs.**
  - `peak_table` (localize.py:45–86) returns a bare DataFrame, and the plot has only an optional title.
  - "Nearest HCP-MMP area name" in a ranked list invites reverse inference (44/45 → "language", OFC → "value").
  - I searched tests/*.py and src/ for a banned-wording guard and found only the whisperx guard (transcribe/core.py:212).
- **D6. The difference-map top-20 is a de facto uncorrected parcel test.**
  - Percentile CIs are computed on parcels selected from the same data (localize.py:62–68), so they carry winner's-curse bias.
  - The bootstrap unit is unspecified (§1 uses company-cluster).
  - It duplicates the BH-FDR exploratory parcels at v2.md:106, without their multiplicity control.
- **D7. The map and the masks are unspecified.**
  - v2.md:100 does not say raw vs spatially standardised, or which window.
  - `peak_table` takes no `unreliable` mask, so masked parcels can top the table while they are greyed in the plot.
  - Three documents disagree on three choices: hatched (spec) vs greyed (code, l.122); "nearest" vs best-overlap HCP; and per-hemisphere top-k with peak-vertex Destrieux (tribe_known_issues.md) vs overall top-k with modal Destrieux (code).

## (3) ENH-003 subcortical

Do not adopt it now.

- N ≈ 60 gives no power for the noisiest targets.
- The stated motivation, "NAcc/amygdala proxies" (ENHANCEMENTS.md:6), is the valuation framing §1 forbids (v2.2 N-M3).
- It adds a pin (BUG-003), an inference pass and an unverified output space.
- Reconsider at the P0 gate only under these conditions:
  - EXPLORATORY;
  - at most 6 pre-registered anatomical ROIs;
  - estimates and CIs only, with no p-values;
  - never in an M-model;
  - no functional labels.

## (4) Known issues that change the primary analysis now (pre-lock)

- **#8 / ENH-001.** Summed text features scale with speech rate. Add words/s and speech fraction over W to the frozen M0, and force both into Q(M0) through a named prereg rule.
- **#7.** Exclude, label-free: no audio track, or fewer than 20 words in W. (silent tracks get noise z-scored to unit variance).
- **#10.** The medial wall is Schaefer label 0 only (atlas.py:201–202). Checked on the cached annots: 121 LH and 110 RH HCP `???` vertices lie outside it, and 123 and 109 lie the other way. This mask defines the M1 spatial standardisation (v2.md:33). Decide union vs Schaefer-only in DECISIONS and apply it everywhere. Implication 6 of tribe_known_issues.md is not yet implemented.
- **#3 / BUG-003.** Make pinned revisions + `HF_HUB_OFFLINE` + a no-network test a hard prerequisite for P4.

## Required changes (all before GO)

1. **v2.md:97 must say:** "T3 survival is:
   - (H4) ΔAUC_T3 > 0, one-sided permutation p < .05, with the same R construction;
   - (H1) the same network significant by maxT, with the same sign.

   T3 is outside the Holm family. A T3-only effect is exploratory and cannot rescue a null T1. W, the exclusions, K_Q, the C grid and **M0 come from T1 unchanged**; only M1 is recomputed from T3."
2. **Gain cap and clipping.**
   - Add `max_gain` (e.g. 3.0) to the config. When it binds, re-solve b and record `gain_capped`, with tests.
   - Never exclude flagged clips.
   - Pre-specify one descriptive report of a, clip fraction and colour cast by group.
3. **v2.md:96, add:** "T1–T3 differences include one extra lossy encode; 'luminance' means gamma-encoded luma Y′."
4. **The localisation writer must always emit** this caption, plus a test that asserts it and a report lint for "language area", "reward", "valuation", "theory of mind", "engagement" and "brain activity":

   > "Descriptive only. TRIBE v2-predicted (average-subject) relative responses, spatially standardised, averaged over W. Atlas names are anatomical labels, not functions; no reverse inference. Only H1 networks and the H2 composite carry inferential claims. CIs are not adjusted for parcel selection."
5. **Peak-table spec:**
   - spatially standardised map, averaged over W, T1 only, after unblinding only;
   - company-cluster bootstrap;
   - the difference table shows the v2.md:106 BH-FDR q;
   - `peak_table(unreliable=…)` flags or excludes masked parcels.
6. **Reconcile** hatched/greyed, nearest/best-overlap and per-hemisphere/overall across v2.md, localize.py and tribe_known_issues.md.
7. **Record ENH-003 as deferred**, with the conditions above.
8. **Log a D-0xx decision** adopting #8, #7 and #10 (M0 list, exclusions, mask) before the Phase 6 lock.
