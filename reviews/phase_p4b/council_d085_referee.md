# Council, D-085 draft (p4b_ref/v1): Referee

**Verdict: REVISE (minor).** §1–§6 implement my R1a/R1b and the BUG-044/SHINE items faithfully. The pre-step (11507d4) commits the build-1 hashes before any D-085 text, the rule change is disclosed as post-outcome, (h) is not consumed, and YuNet is behind `require_frozen`. Nothing below is tuned to an outcome, and no TRIBE output exists. **Split the freeze:** freeze `refclips_d085.qc` (§1–§3) now, so the visual rebuild (§9 steps 2–3) can go ahead. Freeze the speech/TALKFACE keys in a second D-085 commit, once (a), (b), (c) and (e) are settled.

## Open choices: recommendations
- **(a) Harvard licence.** "Public domain" is not established, and the draft wording must change. The source is IEEE Std 297-1969 (doi:10.1109/IEEESTD.1969.7405210). US works from 1964–77 that were published with notice were renewed *automatically* (Copyright Renewal Act 1992), so the renewal check is moot: assume the compilation is © IEEE. A web check (2026-11-22) found no licence statement for the text. The Open Speech Repository covers recordings only. Our use rests on two grounds: (i) individual sentences are words/short phrases, not copyrightable (37 CFR 202.1(a)); (ii) non-commercial research use of a standard test corpus, ≤ 93 sentences synthesised, reordered by sha256. Document both, with the citation and URL/fetch sha, in LICENSES.md under "copyright status: not verified public domain". Do not commit the raw HTML. Before the freeze, make sure the corpus JSON does not need all 720 sentences in list/item order. Keep the texts plus sha, but drop the redundant `list`/`item` keys if their only purpose is to reproduce the IEEE arrangement (the corpus sha is not frozen yet, so this is free). The owner must accept this corrected basis; it replaces the premise the owner approved.
- **(b) §7 speech rate. Pick (iv), a single a-priori rule.** Use per-length SPK rate = 60·n/1.25 wpm: 96 wpm for 2 words, 144 wpm for 3 words. This centres the nominal span at the SPK range midpoint and keeps the design_v2 2/3 balance. BURST and TALKFACE stay at 175 wpm (2 sentences ≈ 16 words ≈ 5.5 s, inside 4–6 s). Against the options in the draft:
  - Option (i) knowingly courts a STOP.
  - Option (ii) breaks the frozen design balance.
  - Option (iii), 120 wpm, puts *both* lengths on the range edges (1.0 s and 1.5 s).

  This changes the owner-approved 175 wpm, so it is an owner question. If the owner declines, fall back to (i), with exhaustion as a STOP. Also disclose that SPK leads are clipped sentence prefixes, some of which end in a function word ("Cut the", "Shape the"). That is acceptable for an AUD localiser and needs no rule.
- **(c) T-ENV / envelope check.** A gate on "mean `speech_envelope` rises at events" repeats the Haar defect: speech replaces the bed at matched RMS, so the stimulus can pass or fail by construction. Fix the check a priori in the second freeze:
  - **Gate:** the SPK/BURST wav is sample-identical to the GREY_CTRL bed outside every utterance window, and every window contains the selected utterance span (constructive, like twin identity).
  - **Report only:** `speech_envelope`, the event-boxcar correlation and the event/non-event ratio. These are disclosed and never gate.
  - **Order:** T-ENV (ENH-002) is implemented, tested and frozen before any speech build. That keeps the hard dependency in §9 step 4.
- **(d) Twin identity.** Adopt the draft: the gate is rendered uint8 equality outside [o−4, o+8). Report decoded max|Δ| outside the windows, and decoded-vs-rendered at event mid-frames (§3), as descriptive statistics with no tolerance. Decoder determinism is already gated by step 2 (sha equality to build1).
- **(e) Wav2Lip licence and face rule.**
  - **Licence: acceptable** for this non-commercial study. The repo licence binds use. Publishing 3 descriptive TALKFACE clips in a research report is within "research/academic". Do **not** redistribute the weights: keep the S3 mirror private, record only the sha in the repo, and cite LRS2 (© BBC, research-only) in LICENSES.md.
  - **Weights:** pick `wav2lip.pth`. The README gives it the more accurate lip-sync, and sync is the construct; visual quality matters little after greyscale.
  - **Face rule:** the 21st face pass is acceptable, with two a-priori additions. (1) The licence must permit adaptation: CC0, CC-BY or CC-BY-SA; no ND, and no image tagged with personality-rights restrictions. (2) If s3fd misses the face on any frame, take the next pass, at most 5 in total, logged; then STOP. Disclose that the clip is a synthetic animation of a real person.

## Blocking items
1. Correct the §7 licence text and add the LICENSES.md entry, per (a).
2. Choose the SPK rate rule, (iv) or (i), before `speech_corpus_sha256` is frozen.
3. Write the envelope gate and report rules from (c) into `refclips_d085` before T-ENV or any speech build.
4. Fix the Wav2Lip weights choice and the face-rule additions from (e) before T-TALK setup.
5. The freeze commit re-asserts the R1b grep: no frozen computation reads refclip `face_area_crop_frac`.
