"""BUG-018 / BUG-002: absolute-time Word events for chunked TRIBE clips (vendored fix, CPU-testable).

Upstream bug (tribev2 af58661, ``tribev2/eventstransforms.py`` ``ExtractWordsFromAudio._run``; PR #29 / #81
unmerged; docs/tribe_known_issues.md finding #1): after ``ChunkEvents`` splits a long Audio event into
chunks (chunk k: ``start = s0 + offset_k``, ``offset = offset_k`` into the file), the transform gives EVERY
chunk the FULL file transcript and shifts it by ``audio_event.start + audio_event.offset``. Transcript
times are file-relative, so chunk 2 of a 110 s clip ([60, 50], offset 60) gets every word at +120 s, and
every word appears once per chunk (GPU run p0rerun_20261117T155528Z: 552 words for 276 .tsv rows, word
starts up to 228.57 s, prediction shape (229, 20484)).

Fix (same contract as the upstream transform, only the timing/assignment differs):
  * each transcript row is assigned to exactly ONE chunk of its file: the chunk whose file-time span
    ``[offset, offset + duration)`` contains the word start (words before the first chunk go to the first,
    words at/after the end of the last chunk go to the last), so no word is duplicated;
  * its absolute start is ``audio_event.start - audio_event.offset + t_file`` (= ``s0 + t_file``).
With a single, unchunked Audio event (offset 0) the result equals upstream's, so T1 (58 s) is unchanged.

BUG-029 (P4 session 4, FIX-P4G): a word whose END runs past the end of its file's audio (the 58.0 s T1 trim
cuts the last word: end 58.010-58.030 s in 6/6 failing clips, 0/5 passing) is silently dropped downstream
(n_words = .tsv rows - 1). Each word's end is therefore clamped to ``END_GUARD_S`` before the file's audio end
(start unchanged); :data:`WORD_END_CLAMP` is part of the cache key (run_clip revisions).

:func:`install` monkeypatches ``ExtractWordsFromAudio._run`` (ASR is never run: a missing .tsv raises).
:func:`check_word_events` is the post-run regression check (n_words == .tsv rows, no word after the clip,
no duplicate (text, start)); :func:`guard_duration` is run_clip's hard guard: clips longer than
``MAX_UNPATCHED_S`` are refused unless the fix is enabled. GPU verification is PENDING (BUGS.md BUG-018
status line): the fix is CPU-tested against a faithful re-implementation of the upstream loop only.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import pandas as pd

END_GUARD_S = 1e-3             # BUG-029: clamped word end = audio end - 1 ms
WORD_END_CLAMP = "v1"          # BUG-029 fix version; recorded in run_clip revisions (cache key)
MAX_UNPATCHED_S = 60.0          # ChunkEvents max chunk length; longer clips may be chunked (BUG-018)
_SKIP_COLS = ("frequency", "filepath", "type", "start", "duration", "offset")   # as upstream
PATCH_MARK = "_yct_bug018_absolute_words"


def _offset(ev: Any) -> float:
    o = getattr(ev, "offset", 0.0)
    try:
        o = float(o)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(o) else o


def absolute_word_events(audio_events: pd.DataFrame, transcripts: dict[str, pd.DataFrame],
                         language: str, end_cap: float | None = None) -> list[pd.DataFrame]:
    """Word event frames (one per Audio event/chunk) with absolute, non-duplicated word times. Word ends are
    clamped to min(file audio end, ``end_cap``) - END_GUARD_S (BUG-029; end_cap = absolute end of the Video
    events, which can be a frame shorter than the audio, Neuro FIX-P4G finding 3)."""
    out: list[pd.DataFrame] = []
    spans: dict[str, tuple[float, float]] = {}
    for ev in audio_events.itertuples():
        o, d = _offset(ev), float(ev.duration)
        lo, hi = spans.get(ev.filepath, (math.inf, -math.inf))
        spans[ev.filepath] = (min(lo, o), max(hi, o + d))
    for ev in audio_events.itertuples():
        tr = transcripts[ev.filepath]
        if len(tr) == 0:
            continue
        o, d = _offset(ev), float(ev.duration)
        first, last = spans[ev.filepath]
        t = tr["start"].astype(float)
        lo_ok = (t >= o) | (o <= first)
        hi_ok = (t < o + d) | (o + d >= last)
        w = copy.deepcopy(tr.loc[lo_ok & hi_ok]).reset_index(drop=True)
        if len(w) == 0:
            continue
        for k, v in ev._asdict().items():
            if k in _SKIP_COLS:
                continue
            w.loc[:, k] = v
        w["type"] = "Word"
        w["language"] = language
        w["start"] = float(ev.start) - o + w["start"].astype(float)
        if "duration" in w:
            end_abs = float(ev.start) - o + last
            if end_cap is not None and end_cap < end_abs:
                end_abs = end_cap
            end_abs -= END_GUARD_S
            w["duration"] = clamp_durations(w["start"], w["duration"], end_abs)
        out.append(w)
    return out


def clamp_durations(start: pd.Series, duration: pd.Series, end: float) -> pd.Series:
    """BUG-029: durations cut so that start + duration <= end (never negative; start is never moved)."""
    st, du = start.astype(float), duration.astype(float)
    return du.where((st + du <= end) | du.isna(), (end - st).clip(lower=0.0))   # NaN stays NaN (QA P2 #3)


def n_words_past_end(tsv: pd.DataFrame, duration_s: float) -> int:
    """.tsv rows whose end (start + duration) is after the clip end: the words BUG-029 clamps."""
    if len(tsv) == 0 or "duration" not in tsv:
        return 0
    return int((tsv["start"].astype(float) + tsv["duration"].astype(float) > duration_s).sum())


def _read_tsv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, sep="\t")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def patched_run(self, events: pd.DataFrame) -> pd.DataFrame:
    """Drop-in for ``ExtractWordsFromAudio._run`` (af58661) with absolute chunk timing; no ASR."""
    if "Word" in events.type.unique():
        return events
    audio = events.loc[events.type == "Audio"]
    transcripts: dict[str, pd.DataFrame] = {}
    for fp in audio.filepath.unique():
        tsv = Path(fp).with_suffix(".tsv")
        if not tsv.exists():
            raise RuntimeError(f"BUG-018 word fix: transcript {tsv} missing (ASR is never run)")
        transcripts[fp] = _read_tsv(tsv)
    video = events.loc[events.type == "Video"]
    end_cap = float((video.start.astype(float) + video.duration.astype(float)).max()) if len(video) else None
    words = absolute_word_events(audio, transcripts, getattr(self, "language", "english"), end_cap)
    if words:
        events = pd.concat([events, pd.concat(words)], ignore_index=True)
    return events


def install(et_module: Any) -> None:
    """Monkeypatch ``et_module.ExtractWordsFromAudio._run`` (et_module = tribev2.eventstransforms)."""
    cls = et_module.ExtractWordsFromAudio
    if not getattr(cls, PATCH_MARK, False):
        cls._run = patched_run
        setattr(cls, PATCH_MARK, True)


def is_installed(et_module: Any) -> bool:
    return bool(getattr(et_module.ExtractWordsFromAudio, PATCH_MARK, False))


def check_word_events(df: pd.DataFrame, n_tsv_rows: int, duration_s: float, tol_s: float = 0.5) -> dict:
    """Regression check on the final TRIBE events: one Word per .tsv row, none after the clip, no duplicate
    (text, start). ``ok`` is the conjunction."""
    w = df[df.type == "Word"]
    n = int(len(w))
    dup = int(w.duplicated(subset=["text", "start"]).sum()) if n else 0
    after = int((w.start.astype(float) > duration_s + tol_s).sum()) if n else 0
    res = {"n_words": n, "n_tsv_rows": int(n_tsv_rows), "n_duplicate_text_start": dup,
           "words_after_duration": after, "word_start_max_s": float(w.start.max()) if n else None}
    res["ok"] = n == n_tsv_rows and dup == 0 and after == 0
    return res


def guard_duration(duration_s: float, fix_enabled: bool, max_s: float = MAX_UNPATCHED_S) -> None:
    """run_clip hard guard: a clip longer than ``max_s`` needs the BUG-018 fix (else it may be chunked and
    get shifted, duplicated words)."""
    if duration_s > max_s and not fix_enabled:
        raise SystemExit(f"BUG-018 guard: clip is {duration_s:.2f} s > {max_s:.0f} s; TRIBE chunking shifts "
                         "and duplicates words. Re-run with --bug018-word-fix (GPU verification pending).")
