"""P3 tests: per-TR features aligned to the 1.0 s grid and within range (synthetic clips)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests import _synth as syn
from yct.config import load_config, with_overrides
from yct.confounds import FEATURES, extract_confounds, pitch_track, tr_grid
from yct.confounds.__main__ import main as cli_main
from yct.transcribe import write_tribe_tsv


@pytest.fixture(scope="module")
def stim(tmp_path_factory):
    """Video: black 0-2 s | testsrc2 2-4 s | smptebars 4-6 s (cuts at 2 and 4).
    Audio: silence 0-3 s | 220 Hz tone 3-5 s | silence 5-6 s."""
    d = tmp_path_factory.mktemp("conf")
    mp4, wav = d / "stim.mp4", d / "stim.wav"
    syn.ff(
        "-f",
        "lavfi",
        "-i",
        "color=black:s=640x360:r=30:d=2",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=640x360:r=30:d=2",
        "-f",
        "lavfi",
        "-i",
        "smptebars=s=640x360:r=30:d=2",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=mono:d=3",
        "-f",
        "lavfi",
        "-i",
        "sine=f=220:r=48000:d=2",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=mono:d=1",
        "-filter_complex",
        "[0][1][2]concat=n=3:v=1:a=0[v];[3][4][5]concat=n=3:v=0:a=1[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        *syn.enc(mp4),
    )
    syn.ff("-i", str(mp4), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav))
    words = [
        {"text": w, "start": 3.1 + 0.3 * i, "duration": 0.2, "sequence_id": 0, "sentence": "one two three"}
        for i, w in enumerate(["one", "two", "three"])
    ]
    tsv = write_tribe_tsv(words, d / "stim.tsv")
    df, summary = extract_confounds(mp4, wav, tsv, video_id="vid0")
    return {"dir": d, "mp4": mp4, "wav": wav, "tsv": tsv, "df": df, "summary": summary}


def test_tr_grid():
    g = tr_grid(6.0, 1.0)
    assert list(g["tr"]) == list(range(6)) and np.allclose(g["tr_start_s"], np.arange(6))
    g2 = tr_grid(5.5, 1.0)
    assert len(g2) == 6 and g2["tr_coverage"].iloc[-1] == pytest.approx(0.5)


def test_tidy_columns_and_grid_alignment(stim):
    df = stim["df"]
    assert list(df.columns[:5]) == ["video_id", "tr", "tr_start_s", "tr_end_s", "tr_coverage"]
    assert set(FEATURES) <= set(df.columns)
    assert len(df) == 6 and (df["video_id"] == "vid0").all()
    assert np.allclose(df["tr_start_s"], df["tr"] * 1.0)
    assert np.allclose(df["tr_end_s"] - df["tr_start_s"], 1.0)


def test_audio_features_aligned(stim):
    df = stim["df"].set_index("tr")
    sp = df["speech_frac"]
    assert sp[[0, 1, 2, 5]].max() < 0.05
    assert sp[[3, 4]].min() > 0.9
    assert (df.loc[[3, 4], "rms_db"] > df.loc[[0, 1, 2, 5], "rms_db"].max() + 30).all()
    assert df.loc[3, "speech_rate_wps"] == pytest.approx(3.0) and df.loc[4, "speech_rate_wps"] == 0
    assert df.loc[[3, 4], "pitch_mean_hz"].to_numpy() == pytest.approx([220, 220], rel=0.03)
    assert df.loc[[0, 1, 2, 5], "pitch_mean_hz"].isna().all()


def test_video_features_aligned(stim):
    df = stim["df"].set_index("tr")
    assert df.loc[[0, 1], "luminance"].max() < 0.1
    assert df.loc[[2, 3, 4, 5], "luminance"].min() > 0.2
    assert df.loc[[0, 1], "contrast"].max() < 0.02
    assert df.loc[[2, 3, 4, 5], "contrast"].min() > 0.1
    cuts = df["scene_cuts"]
    assert cuts.sum() == 2 and cuts[2] == 1 and cuts[4] == 1
    assert df.loc[[0, 1], "motion_energy"].max(skipna=True) < 0.01
    assert df.loc[3, "motion_energy"] > df.loc[1, "motion_energy"]


def test_value_ranges(stim):
    df = stim["df"]
    for col in (
        "speech_frac",
        "luminance",
        "contrast",
        "motion_energy",
        "motion_energy_crop",
        "face_present_frac",
        "face_area_frac",
    ):
        v = df[col].dropna()
        assert ((v >= 0) & (v <= 1)).all(), col
    assert (df["rms_db"] <= 0).all() and (df["rms_db"] >= -120).all()
    assert (df["scene_cuts"] >= 0).all() and (df["face_count_mean"].dropna() >= 0).all()
    assert (df["speech_rate_wps"] >= 0).all()
    p = df["pitch_mean_hz"].dropna()
    assert ((p >= 60) & (p <= 400)).all()
    assert df["text_frac"].isna().all()  # stub


def test_summary(stim):
    s = stim["summary"]
    assert s["n_tr"] == 6 and s["n_scene_cuts"] == 2
    assert s["speech_s"] == pytest.approx(2.0, abs=0.15)
    assert s["words_per_min"] == pytest.approx(30.0, abs=1)
    assert s["pitch_mean_hz"] == pytest.approx(220, rel=0.03)
    assert s["text_detection"] == "not_implemented"


def test_pitch_track_sine():
    sr = 16000
    t = np.arange(sr) / sr
    for f in (110.0, 180.0, 300.0):
        _, f0 = pitch_track(0.5 * np.sin(2 * np.pi * f * t), sr, load_config()["confounds"]["pitch"])
        assert np.nanmedian(f0) == pytest.approx(f, rel=0.02)
    _, f0 = pitch_track(np.random.default_rng(0).normal(0, 0.1, sr), sr, load_config()["confounds"]["pitch"])
    assert np.isnan(f0).mean() > 0.8


def test_no_tsv_gives_nan_rate(stim):
    df, s = extract_confounds(stim["mp4"], stim["wav"], None)
    assert df["speech_rate_wps"].isna().all() and s["words_per_min"] is None


def test_text_detection_flag_not_implemented(stim):
    cfg = with_overrides(load_config(), {"confounds": {"text_detection": True}})
    with pytest.raises(NotImplementedError):
        extract_confounds(stim["mp4"], stim["wav"], cfg=cfg)


def test_cli_writes_parquet(stim, capsys):
    out = stim["dir"] / "confounds.parquet"
    assert (
        cli_main(
            [
                "--mp4",
                str(stim["mp4"]),
                "--wav",
                str(stim["wav"]),
                "--tsv",
                str(stim["tsv"]),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    back = pd.read_parquet(out)
    assert len(back) == 6 and "motion_energy" in back.columns
    assert '"n_tr": 6' in capsys.readouterr().out


def test_summary_speech_rate_and_fraction_per_video(stim):
    s = stim["summary"]
    assert s["has_audio_track"] is True
    assert s["n_words"] == 3
    assert s["speech_rate_wps"] == pytest.approx(3 / 6.0, rel=0.02)
    assert 0 < s["speech_frac"] < 1
    df = stim["df"]
    for col in ("face_present_crop", "face_area_crop_frac", "luminance_crop", "contrast_crop"):
        v = df[col].dropna()
        assert len(v) and ((v >= 0) & (v <= 1)).all(), col


def test_apply_transcript_matches_full_extraction(stim):
    """P2b after P3: filling the transcript columns later gives exactly the with-tsv extraction."""
    from yct.confounds import apply_transcript

    df0, s0 = extract_confounds(stim["mp4"], stim["wav"], None, video_id="vid0")
    df1, s1 = apply_transcript(df0, s0, stim["tsv"])
    ref_df, ref_s = stim["df"], stim["summary"]
    assert np.allclose(df1["speech_rate_wps"], ref_df["speech_rate_wps"])
    for k in ("n_words", "speech_rate_wps", "words_per_min", "speech_rate_wps_mean"):
        assert s1[k] == pytest.approx(ref_s[k]), k
    others = [c for c in ref_df.columns if c != "speech_rate_wps"]
    pd.testing.assert_frame_equal(df1[others], df0[others])
    assert df0["speech_rate_wps"].isna().all()  # input frame untouched


def test_apply_transcript_empty_tsv_gives_zero_rate(stim, tmp_path):
    from yct.confounds import apply_transcript

    df0, s0 = extract_confounds(stim["mp4"], stim["wav"], None, video_id="vid0")
    empty = write_tribe_tsv([], tmp_path / "empty.tsv")
    df1, s1 = apply_transcript(df0, s0, empty)
    assert (df1["speech_rate_wps"] == 0).all() and s1["n_words"] == 0 and s1["words_per_min"] == 0.0
