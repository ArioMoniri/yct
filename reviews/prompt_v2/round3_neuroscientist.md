# Round 3 — Neuroscientist review of docs/prompts/v2.md (v2.1)

V = v2.md, R = tribe_requirements.md.

**Vote: FIX** (0 CRITICAL, 5 MAJOR).

## (1) TRIBE claims vs R

Supported: V21↔R87; V42↔R51,R89; V46↔R88; V50↔R62-64; V220-222↔R24-26,R52; V235↔R30; V293↔R83; V306-308↔R64,R71-72; V310↔R63,R73; V314-320↔R50,R53,R75-76; V330↔R101-107; V331↔R112-119; V348↔R93-96; V351-353↔R133-136; V375↔R86.

Unsupported: **V36** "Limbic … has the lowest SNR" — R says nothing about TRIBE's limbic accuracy (R94: parcel scores exist only as paper figures). Fix in M3 below.

## Defects

**M1 — V42: the 60 s trim sits exactly on the chunking boundary.** R51 says events "longer than 60 s" are split into 30–60 s chunks. A cut at "first 60 s" can decode to 60.03 s after frame/sample rounding and get split into two 30 s chunks, each z-scored separately (R63).
Replace V42 with: "T1 feeds TRIBE a clip trimmed to its **first 58.0 s** (ffprobe duration ≤ 58.5 s asserted). A test asserts that the events dataframe holds exactly one Audio and one Video chunk per clip (tribe_requirements §2.2, §3)."

**M2 — V43-47: W start and the exclusion threshold do not follow the measured latency.** R88 leaves the output latency L open (0 s by the issue #78 scan, 5 s by the localiser). Each 2 Hz video feature uses the preceding 4 s (R64). So output TR t has a full, real 4 s video context only when t ≥ 4 + L. With L = 5, TRs 5–8 are still warm-up. V44's "<47 s" exclusion is also hard-coded to W_end = 45.
Replace V43-44 with: "Default W = [max(5, 4 + L + 1), that + 40) TRs, where L is the P0 impulse latency rounded up to whole TRs (L = 0 gives [5, 45)). Videos whose trimmed duration is < W_end + 2 s are excluded from T1 (logged) and kept in T2."
Delete V46's "≥ 2 s" clause.

**M3 — V36 vs V60 vs V61: the limbic/rank logic is inconsistent.**
(a) V60's H1 runs maxT over **7** networks, but M1 (V36) has 6. Under spatial standardisation the 7 means are linearly dependent: m_L = −Σ n_k m_k / n_L. So dropping limbic loses **no** information for the linear models (H3/H4/H4b), and "lowest SNR" is not the reason for dropping it. For H1, though, the limbic test is redundant but legitimate.
(b) H2 (V61) includes TP, which is Yeo-limbic and is exactly the region V36 calls a dropout zone.
(c) H2 is a separate parcel composite, independent of M1; no hypothesis concerns vmPFC/OFC valuation, so nothing is lost.
Replace V36 with: "Use the 6 non-limbic Yeo networks as M1 features. Limbic is the omitted reference: its mean is the exact linear combination −Σ(n_k/n_L)m_k, so no information is lost. Limbic (OFC/temporal pole) is also susceptible to signal dropout in the fMRI TRIBE was trained on, so it is not interpreted. No valuation/reward claim is made."
In V60 add: "(7 tests on the spatially standardised map; the results are compositional, i.e. relative to the cortical mean)."
In V61 replace the parcel list with: "HCP-MMP STSv, STSdp, PGi, 45, 44, TE1a (left + right except 44/45 left only), on the spatially standardised map; TP (TGd) excluded as dropout-prone."

**M4 — V336: P4b(a) is statistically incoherent and can STOP the project spuriously.**
- HAC SEs are computed, but the test uses Fisher-z of r across videos, so HAC is never used.
- "Partial r" names no covariates.
- Talking-head face fraction is near-constant, so FFC can "fail" from a degenerate regressor, not a bad model.
- Face fraction and motion are measured on the full frame, but the model sees only the central 256×256 crop (R64, R72).
- Lag: R88 compensation is nominal and unverified.
Replace V336-337 with:
"Per video, Pearson r between the ROI time course over W and the regressor. Regressors are computed **inside the central 256×256 crop** at 2 Hz, mean-pooled to 1 Hz, shifted by the P0 latency L and convolved with the P0-measured impulse response (no canonical HRF). Partial r controls for the other two regressors. Inference is across videos: one-sample t on Fisher-z, PASS = mean z > 0.2 and p < .001. Videos where the regressor SD over W falls below the 10th percentile of the reference clips are excluded from that control (logged). If fewer than 15 videos remain, that control is evaluated on the ≥5 reference naturalistic clips instead."

**M5 — V340-343: ROI names are undefined, and the strongest supported control is missing.** "STG" is not an HCP-MMP label. R95 gives FFC and A5. V1, V2 and V3 exist in HCP-MMP. The paper's face→FFC localiser (R142, R147) is the one control TRIBE is *documented* to pass, but P4b does not use it. Speech *fraction* is ~1 in nearly every pitch, so r > 0.3 is fragile.
Replace "STG" everywhere with: "AUD = HCP-MMP A4 ∪ A5 (bilateral)". In V343 change "the STG feature with speech fraction" to "the AUD feature with mean speech envelope". Add after V344:
"(d) **Localiser replication**: 1 s face/place/body image flashes, response at t = 5 s minus the other categories (paper §5.9). PASS = FFC face > place and PH place > face, sign-consistent in both hemispheres."

## Minor
V50: M0b should use TRIBE's layer set [0.5,0.75,1.0] (R62-64). V330: add R106 caveat (zeroing ≠ retrained unimodal).

## (5) Claims language
Searched V for engag/persua/trust/"brain activ"/prefer/valuation/reward. All uses are in the prohibitions at V20. The functional label "language/social composite" (V61) is an atlas convenience, and the prereg should say so. No other overclaim found.
