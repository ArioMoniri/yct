# D-089 draft: SPK speech rate 140 wpm (amends the frozen D-085 part-2 speech key)

Status: DRAFT for the council. Nothing is frozen and nothing is synthesised. No DECISIONS entry yet.

## 0. Trigger and owner decision

The D-085 part-2 step-2 selection (pod CPU, run at 825c975; espeak-ng pin verified; texts private, no
listening) STOPped on queue exhaustion. Record: `outputs/runs/d085p2_selection/STOP_NOTE.md` and
`speech_selection_v1_STOP.json` (sha256 25168eca…95d7).

- SPK kept 31 of 60 after all 410 queue items. Pass rate 7.6%, Wilson 95% 5.4–10.5%.
- Every one of the 379 SPK rejects was shorter than 1.0 s. None was longer than 1.5 s. Median span 0.79 s.
- BURST and TALKFACE were never reached.

Owner decision (in-session AskUserQuestion, 2026-11-23): **"Slower rate for SPK"**. The 3-word SPK phrases
are spoken at 140 wpm, BURST and TALKFACE stay at 175 wpm, and the selection re-runs. The change is
disclosed as post hoc.

## 1. What changes

A new block, `controls.refclips_d089`, layers onto the frozen key and is frozen in its own two-commit
freeze. The frozen key `controls.refclips_d085.speech` is **not edited**: `speech.rate_wpm` stays 175.

- `rate_wpm_by_family: {SPK: 140, BURST: 175, TALKFACE: 175}`. `speech_corpus.effective_spec(cfg)`
  layers it onto the frozen key. `select()` calls the pin-verified synth with `rate_wpm=` for each family,
  and `EspeakSynth` passes it to espeak-ng as `-s`.
- `restart_queue_at: 0`. Selection re-runs from queue position 0, in the same frozen ascending-sha256 order.
- `carry_over_v1_keeps: false`. The 31 v1 SPK keeps are not carried over: every item is re-measured at the
  new rate.
- `on_exhausted: final_stop_owner`. If the queue runs out again, that is a final STOP to the owner, with no
  third amendment.
- `scripts/speech_select.py` refuses to run until `controls.refclips_d089` is frozen.
- The schema refuses any BURST or TALKFACE rate other than 175, or an SPK rate that is not slower than 175.

**Unchanged:**
- the corpus file and its frozen sha (252c83ac…);
- the queue order and the exclusion lexicon;
- `spk_words: 3`, `burst_sentences: 2` and `fill_order` (SPK, BURST, TALKFACE);
- the −40 dBFS span gate on the 48 kHz band-limited selection path;
- `ranges_s`: SPK [1.0, 1.5] s, BURST [4.0, 6.0] s, TALKFACE [1.0, 6.0] s;
- `counts` (60 / 15 / 3);
- the espeak-ng engine pin and its fail-closed re-hash;
- voice en-us, pitch 50, amplitude 100;
- `texts_public: false`; nobody listens.

**Build path:** the SPK clips must be synthesised at the same 140 wpm. The build's RawSpeech binding has
not been written yet. It must take the rate from `effective_spec`, never from `speech.rate_wpm`. This is a
council condition for the build ticket.

## 2. A-priori estimate (numbers only, from the v1 STOP record)

The 140 wpm rate was **chosen after seeing the v1 SPK span distribution**. The estimate below scales the
410 recorded v1 spans (all 175 wpm, 3-word leads) linearly by 175/140 = 1.25, and is checked in
`tests/test_d089.py::test_expected_pass_rate_from_the_v1_stop_record`. Linear scaling is an approximation:
espeak's inter-word pauses and phoneme durations do not scale exactly with `-s`.

| | v1 at 175 wpm (observed) | estimate at 140 wpm |
|---|---|---|
| items | 410 | 410 |
| inside [1.0, 1.5] s | 31 | 184 (44.9%) |
| shorter than 1.0 s | 379 | 224 |
| longer than 1.5 s | 0 | 2 (0.5%) |
| median span | 0.79 s | 0.985 s |
| range | — | 0.63–1.58 s |

**Expected effect:**
- **SPK:** needs 60 keeps. At about 45% it should fill after about 134 queue items. That leaves about 276
  items for BURST (15 slots, 2 sentences per attempt) and TALKFACE (3 slots, 1 sentence per attempt).
- **Above 1.5 s:** small risk (2 of 410 estimated).
- **Main risk:** the median sits right at the 1.0 s floor, so a slightly sub-linear real slowdown would pull
  the pass rate down. A 60-keep SPK fill needs a pass rate of at least about 15% on the queue SPK sees.
- **BURST and TALKFACE:** unmeasured at 175 wpm, since v1 never reached them. Their exhaustion risk is
  unknown, and a queue exhaustion there is also the final STOP.

## 3. Order (after council sign-off)

1. DECISIONS D-089 (append-only), then the two-commit freeze of `controls.refclips_d089` with its expected
   row in `tests/test_guards_frozen_config.py`.
2. On the pod (CPU), re-run `scripts/speech_select.py` from queue position 0. It uses the pin-verified
   `EspeakSynth`; texts stay private and nobody listens. Commit the public ids, shas, spans and pass rates.
   Freeze the selection-record sha in the next commit. Queue exhaustion is a final STOP.
3. Then continue the D-085 part-2 order (TALKFACE face continuation, build plus frozen QC, clip manifest
   sha), as frozen.

## 4. Disclosure (for the v1 report)

- D-089 is a post-hoc amendment of the frozen D-085 part-2 speech key. It was made after the step-2
  selection STOP (v1: SPK 31 of 60, median span 0.79 s at 175 wpm).
- The SPK rate (140 wpm) was chosen after seeing that span distribution. The a-priori linear estimate was
  184 of 410 in range.
- SPK and BURST/TALKFACE now differ in speech rate (140 vs 175 wpm). The SPK speech-envelope and kernel
  readouts are therefore not rate-matched to BURST. That is a limitation of the speech-family contrasts, and
  the speech envelope stays descriptive only.
- The v1 selection record is kept in full as evidence, and none of its keeps are reused.
- Nothing else in D-085 part 2 changed.

## 5. Questions for the council

- Q1: does the rate difference between SPK and BURST/TALKFACE need any additional disclosure or a
  descriptive check in the SPK/BURST kernel analysis?
- Q2: should the a-priori estimate's floor risk be handled now? Options are a pre-stated rule if SPK
  exhausts, or accepting the final STOP. The owner's ruling says a second exhaustion is final.
