"""BUG-018 / BUG-002: absolute-time Word events for chunked TRIBE clips (CPU only, TRIBE mocked).

The upstream loop (tribev2 af58661 eventstransforms.py ExtractWordsFromAudio._run) is re-implemented
here as ``_upstream_run`` (same arithmetic: full transcript per Audio chunk, start += chunk.start +
chunk.offset) to reproduce the GPU finding of run p0rerun_20261117T155528Z on a synthetic events frame:
a 110 s clip chunked [0, 60] + [60, 50] gets every word twice and the second copy shifted by +120 s.
The patched transform must give one word per .tsv row at its true time. GPU verification: pending.
"""
from __future__ import annotations

import copy
import importlib.util
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from yct.tribe_run import word_events as we

ROOT = Path(__file__).resolve().parents[1]


def _upstream_run(self, events):
    """Faithful re-implementation of the af58661 loop (bug included); the .tsv is read next to the wav."""
    if "Word" in events.type.unique():
        return events
    audio = events.loc[events.type == "Audio"]
    trs = {fp: pd.read_csv(Path(fp).with_suffix(".tsv"), sep="\t") for fp in audio.filepath.unique()}
    out = []
    for ev in audio.itertuples():
        t = copy.deepcopy(trs[ev.filepath])
        for k, v in ev._asdict().items():
            if k not in ("frequency", "filepath", "type", "start", "duration", "offset"):
                t.loc[:, k] = v
        t["type"] = "Word"
        t["language"] = self.language
        t["start"] += ev.start + ev.offset
        out.append(t)
    return pd.concat([events, pd.concat(out)], ignore_index=True) if out else events


def fake_et():
    cls = type("ExtractWordsFromAudio", (),
               {"language": "english", "overwrite": False, "_run": _upstream_run})
    return types.SimpleNamespace(ExtractWordsFromAudio=cls)


def tsv(tmp_path, dur=110.0, n=276, name="clip"):
    starts = np.round(np.linspace(0.5, dur - 1.5, n), 3)
    df = pd.DataFrame({"text": [f"w{i}" for i in range(n)], "start": starts, "duration": 0.3,
                       "sequence_id": np.arange(n) // 12, "sentence": "s"})
    wav = tmp_path / f"{name}.wav"
    wav.write_bytes(b"")
    df.to_csv(wav.with_suffix(".tsv"), sep="\t", index=False)
    return wav, df


def chunked_events(wav, chunks, video_dur=None):
    rows = []
    for s, d in chunks:
        rows.append({"type": "Audio", "start": s, "duration": d, "offset": s, "filepath": str(wav),
                     "frequency": 16000, "timeline": "t0", "subject": "avg"})
        rows.append({"type": "Video", "start": s, "duration": d, "offset": s,
                     "filepath": str(wav)[:-4] + ".mp4",
                     "frequency": 2, "timeline": "t0", "subject": "avg"})
    return pd.DataFrame(rows)


def test_upstream_loop_reproduces_plus_120s_shift_and_duplication(tmp_path):
    wav, tr = tsv(tmp_path)
    et = fake_et()
    out = et.ExtractWordsFromAudio()._run(chunked_events(wav, [(0.0, 60.0), (60.0, 50.0)]))
    w = out[out.type == "Word"]
    assert len(w) == 2 * len(tr) == 552                         # every word once per chunk
    assert w.start.max() == pytest.approx(tr.start.max() + 120.0)   # +120 s shift on chunk 2
    assert (w.start > 110.0).sum() > 0
    chk = we.check_word_events(out, len(tr), 110.0)
    assert chk["ok"] is False and chk["n_duplicate_text_start"] == 0 and chk["words_after_duration"] > 0


def test_patched_transform_absolute_non_duplicated_words(tmp_path):
    wav, tr = tsv(tmp_path)
    et = fake_et()
    we.install(et)
    assert we.is_installed(et)
    out = et.ExtractWordsFromAudio()._run(chunked_events(wav, [(0.0, 60.0), (60.0, 50.0)]))
    w = out[out.type == "Word"].sort_values("start")
    assert len(w) == len(tr)
    np.testing.assert_allclose(w.start.to_numpy(), tr.start.to_numpy())
    assert list(w.text) == list(tr.text)
    assert w.start.max() <= 110.0
    assert set(w.language) == {"english"} and set(w.timeline) == {"t0"}
    chk = we.check_word_events(out, len(tr), 110.0)
    assert chk["ok"] is True and chk["n_words"] == 276 and chk["words_after_duration"] == 0


def test_patched_equals_upstream_for_single_unchunked_audio(tmp_path):
    """T1 (58 s, one chunk, offset 0): the fix changes nothing."""
    wav, tr = tsv(tmp_path, dur=58.0, n=140)
    ev = chunked_events(wav, [(0.0, 58.0)])
    up = fake_et().ExtractWordsFromAudio()._run(ev.copy())
    et = fake_et()
    we.install(et)
    fx = et.ExtractWordsFromAudio()._run(ev.copy())
    cols = ["type", "start", "duration", "text", "sequence_id", "timeline", "language"]
    pd.testing.assert_frame_equal(up[cols].reset_index(drop=True), fx[cols].reset_index(drop=True))


def test_three_chunks_and_nonzero_timeline_start(tmp_path):
    """160 s clip (max analysis-set duration) placed at timeline start 5 s: chunks [5,60],[65,60],[125,40]
    with offsets 0/60/120 -> absolute start = 5 + t_file, each word once."""
    wav, tr = tsv(tmp_path, dur=160.0, n=400)
    rows = []
    for off, d in ((0.0, 60.0), (60.0, 60.0), (120.0, 40.0)):
        rows.append({"type": "Audio", "start": 5.0 + off, "duration": d, "offset": off, "filepath": str(wav),
                     "frequency": 16000, "timeline": "t0"})
    et = fake_et()
    we.install(et)
    out = et.ExtractWordsFromAudio()._run(pd.DataFrame(rows))
    w = out[out.type == "Word"].sort_values("start")
    assert len(w) == 400
    np.testing.assert_allclose(w.start.to_numpy(), 5.0 + tr.start.to_numpy())


def test_words_present_are_left_alone_and_missing_tsv_raises(tmp_path):
    et = fake_et()
    we.install(et)
    ev = pd.DataFrame([{"type": "Word", "start": 1.0, "duration": 0.2, "text": "x"}])
    assert et.ExtractWordsFromAudio()._run(ev) is ev
    ev2 = chunked_events(tmp_path / "nope.wav", [(0.0, 70.0)])
    with pytest.raises(RuntimeError, match="transcript .* missing"):
        et.ExtractWordsFromAudio()._run(ev2)


def test_install_idempotent(tmp_path):
    et = fake_et()
    we.install(et)
    we.install(et)
    assert et.ExtractWordsFromAudio._run is we.patched_run


def test_guard_refuses_long_clip_without_fix():
    we.guard_duration(58.0, False)
    we.guard_duration(60.0, False)
    with pytest.raises(SystemExit, match="BUG-018"):
        we.guard_duration(60.5, False)
    with pytest.raises(SystemExit, match="BUG-018"):
        we.guard_duration(110.0, False)
    we.guard_duration(110.0, True)


def _run_clip():
    spec = importlib.util.spec_from_file_location("run_clip",
                                                  ROOT / "src" / "yct" / "tribe_run" / "run_clip.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_run_clip_preflight_guard_and_patch(tmp_path):
    rc = _run_clip()
    with pytest.raises(SystemExit, match="BUG-018"):
        rc.preflight(tmp_path / "x.mp4", bug018_fix=False, probe=lambda _: 110.0)
    assert rc.preflight(tmp_path / "x.mp4", bug018_fix=False, probe=lambda _: 58.0) == 58.0
    assert rc.preflight(tmp_path / "x.mp4", bug018_fix=True, probe=lambda _: 110.0) == 110.0
    et = fake_et()
    rc.apply_word_fix(et, True)
    assert we.is_installed(et)
    et2 = fake_et()
    rc.apply_word_fix(et2, False)
    assert not we.is_installed(et2)
    ap = rc.build_parser()
    base = ["--video", "v", "--feature-cache", "c", "--out", "o", "--weights", "w"]
    assert ap.parse_args(base).bug018_word_fix is False
    assert ap.parse_args(["--video", "v", "--feature-cache", "c", "--out", "o", "--weights", "w",
                          "--bug018-word-fix"]).bug018_word_fix is True
