# Strict Scientific Referee Review: TRIBE v2 x YC Application Videos, Protocol v1

Reviewed file: `docs/prompts/v1_original.md`. This review covers the protocol, not code.

**Verdict: FIX.** The project is worth doing only as a small, honestly framed methods probe. As written, the protocol over-promises ("brain", the H2 direction), cannot support its many analyses at a realistic N, and has no strong stimulus baseline. That last gap means H4, the "KEY" hypothesis, cannot be interpreted.

Checked against the TRIBE v2 README (github.com/facebookresearch/tribev2): tri-modal input; output on fsaverage5 (~20k vertices, shape T × vertices); predictions are for an "average" subject and are shifted 5 s earlier for hemodynamic lag; supplied text is converted to speech and transcribed for word timings; CC-BY-NC-4.0. Paper: arXiv:2605.04326 (abstract: >1,000 h fMRI, 720 subjects).

**UNVERIFIED by me:** the exact encoders (V-JEPA 2 / Wav2Vec-BERT / LLaMA-3.2 are commonly reported, but neither the README nor the abstract names them), the TR/output rate, and the noise-ceiling maps. Step 0 of Prompt B must confirm all of these from the paper and code.

---

## Required changes

### 1. [CRITICAL] Reframe H4: TRIBE is a deterministic function of the stimulus

TRIBE output = g(frozen encoders(video, audio, text)). It contains no information that is not already in the stimulus. So ΔAUC(M2−M0) with M0 = about 20 handcrafted confounds tests whether those handcrafted confounds are complete, not whether "brain" adds anything. A positive H4 under the current M0 is uninterpretable.

Replacement text (P8):
> **Models.** M0a = handcrafted confounds (P3). M0b = *encoder baseline*: the same frozen encoders TRIBE uses (version-pinned per Step 0), with time-averaged layer embeddings per modality, reduced by PCA *inside folds* to the same dimensionality k as M1. M1 = TRIBE network features (k dims). M2 = M0a + M1. M3 = M0a + M0b. **Primary H4 contrast: M1 vs M0b at equal k** (does the brain-fitted readout act as a better low-dimensional projection than generic PCA of the same embeddings?). Secondary: M2 vs M3. Control M1-perm: TRIBE outputs with the vertex-to-parcel assignment spin-permuted (fixed seed). It must not outperform M1-true for any "network-specific" claim. Interpretation if M1 > M0b: the TRIBE readout is a useful *inductive bias / dimensionality reduction* of stimulus features. Never "the brain adds information."

### 2. [CRITICAL] Sample size and the number of analyses are disproportionate

At 30 per group:
- The MDE is d≈0.73, which the protocol itself states (B4). That corresponds to AUC≈0.70.
- The 95% CI half-width of AUC near 0.5 is about ±0.15.
- The CI on ΔAUC between two correlated models is wider still.

Realistic effects of a 1-minute video on a selection decision that rests mainly on team, traction and the written application are plausibly AUC 0.52–0.60. My expectation, not a citation: in the range of d≈0.1–0.3. Detecting that would take hundreds per group.

The protocol nevertheless stacks H1–H4 across several atlases, two tracks, raw and z-scored features, cluster and spin tests, about 10 sensitivity analyses, two classifiers, a holdout, TOST and mixed models.

Replacement text (Section 1):
> **Single primary confirmatory test.** H-primary: nested-CV AUC of M1 (Yeo-7 networks × {mean, SD} on track T1, per-video z-scored, edges dropped) > 0.5, one-sided permutation p<.05 (5,000 perms, labels permuted within year strata, grouped by company). **One key secondary:** ΔAUC(M1−M0b), reported as an estimate with 95% CI. No significance claim unless the CI excludes 0. Everything else is EXPLORATORY, reported as effect sizes with CIs, no p-values in the abstract. The power statement is mandatory and goes in the prereg: "With N=__/group, AUC ≥ __ is detectable at 80% power; smaller effects are not ruled out."

### 3. [CRITICAL] Pilot circularity for H2

H2 (a directional STS/TP/IFG/TPJ effect) comes from a 1 vs 1 pilot that used |BOLD|, no normalisation and arbitrary thresholds. That is a hunch, not a hypothesis. If the two pilot videos are re-included, the test is partly circular.

Replacement text:
> The two pilot videos (and any other video viewed by the team at vertex level before lock) are **excluded from all confirmatory analyses** and listed by sha256 in DECISIONS.md. H2 is retained as a single directional contrast: mean of the Yeo "Default"+language ROI composite (defined from atlas labels, not from the pilot maps), one-sided. The report states: "H2 was derived from N=1 vs 1 exploratory inspection."

### 4. [CRITICAL] Outcome validity and the population of inference

YC acceptance is driven mostly by non-video factors. Selection is severe. Rejected founders who post are rare and self-selected, probably enriched for later success ("rejected, then made it"). Accepted founders post more, and post polished videos. Era drift confounds format with year (production quality, 9:16 framing, YC prompt wording). YC's video requirements by year are UNVERIFIED.

Replacement text (new Section 1b, Estimand and population):
> The estimand is the association between TRIBE-predicted response features and *publicly reported* YC outcome among *founder-posted public application videos*. No inference is licensed about YC's decision process, about the causal effect of video content, or about unposted applications. Required analyses: (a) outcome × year and outcome × later_accepted tables before unblinding of features; (b) primary model stratified/permuted within era bins (pre-2016, 2016–2019, 2020+; finalise at P1 from counts); (c) sensitivity excluding later_accepted rejected videos. Primary claims must survive (b).

### 5. [CRITICAL] Add positive controls before any group test (pipeline validity)

Without a positive control, a null result is uninterpretable and a positive one is unanchored.

Replacement text (new P4b, gate before P5):
> **Positive controls, within the curated videos, labels hidden.** (i) Face frames vs no-face frames (face detector): predicted fusiform/FFA-proxy > V1 control, paired across videos. (ii) Speech vs silence segments: STG/auditory > control. (iii) Scene cuts: early-visual transient at the expected lag given README's 5 s shift. Each must reach d>0.8 across videos. If (i)–(ii) fail: STOP (the pipeline or the OOD inputs are broken). **OOD check:** compare predicted-response variance/spatial correlation for YC videos vs ≥10 reference clips from TRIBE-like stimuli (movie/podcast). Report the result; do not tune on it.

### 6. [MAJOR] Negative controls and falsification tests

Replacement text (P8 addition):
> (a) Shuffled-label AUC distribution (already present). (b) **Nuisance-label control:** run the identical pipeline to predict a meaningless binary label (upload-date parity) and a nuisance label (aspect ratio 16:9 vs other); report both AUCs next to the outcome AUC. (c) **Falsification:** if M0b alone achieves AUC ≥ M1, report that "TRIBE adds nothing over its own encoders"; this is a pre-declared, publishable outcome. (d) Encoder-embedding-residualised TRIBE features (regress M0b PCs out of M1 inside folds) must retain signal for any claim of TRIBE-specific structure.

### 7. [MAJOR] Pre-specified futility and stop rules

Replacement text (Section 7):
> STOP/DOWNGRADE to descriptive report if: (1) after P1, conf-A < 30/group (not 15); with 15–29/group proceed only as a descriptive pilot with no hypothesis tests; (2) positive controls fail; (3) M0a alone AUC ≥ 0.80 (outcome is trivially recoverable from format/era; any TRIBE result is confounded); (4) outcome × era association has Cramér's V > 0.5 and stratification leaves <10/group in any stratum. Record which rule fired.

### 8. [MAJOR] Blinding is violated by P3

P3 asks for a "confound-only group-difference table" before the P6 prereg lock and unblinding. That table requires labels and invites forking. Replacement text:
> P3 produces confound distributions **without outcome**. The outcome × confound table is generated only after P6 lock, by a script committed before lock.

### 9. [MAJOR] Internal inconsistencies to resolve

Resolve each in the prereg:
- **Primary feature space.** P5 says Schaefer-400 is primary. B3 says Yeo-7 + ≤5 ROIs. H1 tests parcels with FDR. Fix: Yeo-7 is primary; Schaefer is exploratory.
- **Stop threshold.** The DoD says "Stop if <15 conf-A". P1 says ≥30. See item 7.
- **Holdout (B9).** At N≈60 a 20% holdout is 12 videos (AUC CI ±0.3). Use nested CV only.
- **Mixed model (B2).** A company random effect is unidentifiable with mostly 1 video per company. Use grouped CV plus a one-video-per-company sensitivity.
- **Reverse inference.** "Optional NiMARE/Neurosynth" contradicts "no reverse inference". Delete it.
- **Gate voting.** Unanimous GO at P6 conflicts with the majority rule elsewhere. Pick one.
- **Normalisation.** Per-video z-scoring removes the mean amplitude, the pilot's main finding ("12% higher |BOLD|"); state that this claim is untested. A global-signal covariate on z-scored data is near-redundant; pick one normalisation.
- **Effective length.** T1 drops videos <30 s, but edge removal (6 s plus 3 TRs) leaves as little as ~20 s. Set the minimum after edges, e.g. ≥40 s usable.
- **Transcripts.** WhisperX transcripts in "TRIBE format" may duplicate or conflict with TRIBE's own TTS-transcription text path. Step 0 must decide which path is used, and use it for all videos.

### 10. [MAJOR] Required language and construct-claim restrictions

Replacement text (P9/P10):
> All results refer to "TRIBE v2-predicted average-subject cortical responses (fsaverage5)". Forbidden in title/abstract/conclusions: "brain response", "neural engagement", "the brain prefers", "engagement", "attention", "persuasion", or any claim about viewers or YC partners. Network names are anatomical/atlas labels only. Any statement linking a network to a cognitive function must cite literature and be labelled interpretation. A required limitations paragraph covers: deterministic function of stimulus; average subject; OOD stimuli; no subcortex; no measured fMRI; case-control public-video sample.

### 11. [MAJOR] Label quality

Confidence-A "rejected" (self-report plus directory absence) cannot exclude reapplication under another company name.

Replacement text:
> Two independent coders label all rows blind to video content; κ ≥ 0.7 required (B12). Label-flip simulation at 5/10/20% reports the attenuation of AUC. Report the A-only primary and A+B sensitivity.

### 12. [MINOR] Specify the reduction

Features = mean and SD per network over the usable window; k = 14 for M1/M0b. Time-to-peak, thirds and "AUC above baseline" are exploratory.

### 13. [MINOR] Determinism tolerance

≤1e-4 max abs difference may be unattainable on GPU. Require feature correlation >0.999 across reruns; pin device and dtype.

### 14. [MINOR] 9:16 videos and burned captions

Covariates or exclusions decided at P1 from counts; no separate inferential stratum at this N.

### 15. [MINOR] Report CIs everywhere

Hedges g with bootstrap CIs for every exploratory effect; no "trend" language.

---

## DELETE as overkill or unsupported at this N

1. The 12-role agent council with votes and FIX cycles. Replace with one Skeptic/Statistician checklist per gate and human sign-off at the P6 lock.
2. Phase 9b, the Prolific behavioural validation (100–200 raters, IRB). This is a separate study and should not be bolted on.
3. Vertex TFCE, T2 temporal clusters, Destrieux, lateralisation (N5), LLM content segments (N6): forking paths with no power.
4. The B9 locked 20% holdout, the B2 company random-effects model, and B1 within-company paired tests. Report pairs descriptively, because the few pairs are confounded by reapplication time.
5. Linear SVM as a second classifier. Keep L2 logistic only.
6. NiMARE/Neurosynth decoding.
7. Quality-matched downscaled copies as "primary" (E1), and the stereo-phase-cancellation check. Keep these as QC flags only.
8. Leave-one-year-out as a separate sensitivity analysis. Replace it with era-stratified permutation (item 4).
9. Two estimands with TOST (B5/B4). At N≈60, equivalence bounds will be uninformatively wide. Report CIs and the MDE instead.
