# D-085 part 2 step 2: STOP to the owner (speech corpus queue exhausted)

- Run on the pod (CPU) at 825c975 (code; corpus and speech keys frozen at 84d741d), `scripts/speech_select.py`,
  EspeakSynth with the engine pin verified (binary, library, data tree all equal), texts private, no listening.
- Frozen rule `speech.on_exhausted: stop_owner`: the 410-item queue ran out while filling SPK.
- SPK (3-word leads at 175 wpm, −40 dBFS span on the 48 kHz path, range [1.0, 1.5] s): 31 of 60 kept from all
  410 tried (7.56%, Wilson 95% 5.4–10.5%). Every one of the 379 rejects was **too short** (< 1.0 s); none was
  too long. Median span 0.79 s. BURST and TALKFACE were never reached (0 tried).
- This is the feasibility risk disclosed in D-086/D-085 (neuro re-sign-off): trimming to the −40 dBFS span
  makes most 3-word items at 175 wpm shorter than the 1.0 s floor.
- Public record: `speech_selection_v1_STOP.json` (ids, spans, counts; no texts), sha256 25168eca…95d7. The
  private log with texts was not written (the STOP path returns before it). Nothing is frozen from step 2;
  step 3 (TALKFACE face continuation) was not run.
- No rule changed. Any way forward (rate, word count, range, corpus) is an owner decision and a new D- entry,
  disclosed as made after seeing this result.
- Earlier attempts: attempt 0 crashed on a missing scipy in the wrong venv (venv_refstim) after the pin check
  and before any selection record; attempt 1 (fa1111c) hit the same STOP but wrote no counts, which led to
  the STOP-record code at 825c975 (reporting only, rule unchanged).
