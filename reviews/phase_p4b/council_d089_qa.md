# Council D-089 — QA member review (draft d089_draft.md, commits bb059b0, 5cf52d0)

Verdict: **REVISE** (mechanics sound; rate choice and build condition need tightening before the freeze).
Checks: `pytest tests/test_d089.py tests/test_speech_corpus.py` 24 passed; `make guards` exit 0 (no weakening).
Inputs read: STOP record ids/spans/counts only (it holds no texts); 410 SPK spans, median 0.788 s, max 1.261 s.

**Rate.** 140 wpm gives a linear median of 0.985 s, below the "median ~1.0–1.1 s" the owner was shown. The draft's
own caveat (sub-linear slowdown) is the main risk. With f = 1 + a(175/w − 1), SPK pass rates are:
- 140 wpm: a=0.5 27%, a=0.7 33%, a=1.0 45%
- 120 wpm: 41%, 59%, 73%
- 115 wpm: 47%, 65%, 75% (over 1.5 s at a=1: 19 of 410 at 120, 35 at 115)

At 140, SPK probably still fills: at 27% that is about 222 queue items. But BURST is left with about 188 items it was
never measured on, the keeps pile up at the 1.0 s floor, and any BURST exhaustion is the final STOP. Recommend a
rate picked by a stated rule: **the integer wpm that maximises the worst-case in-range fraction of the v1 spans for
a in [0.7, 1.0]**. That gives about 120 wpm (linear median about 1.15 s). The owner re-confirms the rate either way.
Better still: before the freeze, measure `a` on the pod at 175 and the candidate wpm with a public, non-corpus
calibration list. That touches no corpus texts.

**Second exhaustion = final STOP.** Acceptable as the owner's ruling. Be aware that it now also covers BURST and
TALKFACE, which are untested. The owner should say explicitly that a BURST or TALKFACE exhaustion is also final.

**Restart at 0, no carry-over.** Correct. All 31 v1 keeps (1.0–1.26 s at 175 wpm) would be about 1.25–1.58 s at
140 wpm, and mixing rates breaks within-family uniformity. Disclose that the rate was tuned on the same 410 items
that get re-selected (span only, so no outcome leakage).

**Build condition is not enough as written.** `EspeakSynth.__call__(text, rate_wpm=None)` silently falls back to
175. Required:
- the build path passes an explicit rate, or a no-default wrapper raises;
- the selection record stores `rate_wpm` per item;
- the clip manifest stores `rate_wpm` per clip;
- the frozen QC asserts both equal `effective_spec`, and re-measures each built clip's span against the selected
  span and `ranges_s` (fail-closed);
- the freeze adds the expected `controls.refclips_d089` row to `tests/test_guards_frozen_config.py`.

Minor: the "at least about 15%" figure assumes SPK gets the whole queue. State the joint SPK+BURST budget instead.
