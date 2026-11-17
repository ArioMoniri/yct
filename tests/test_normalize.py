"""P2 normalisation tests (ROADMAP P2: test_normalize, test_no_padding) on synthetic ffmpeg clips."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests import _synth as syn
from yct.media import decode_audio, ffprobe, sha256_file, stream
from yct.normalize import crop_coverage, normalize_video, target_dims
from yct.normalize.__main__ import main as cli_main


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    return tmp_path_factory.mktemp("norm")


@pytest.fixture(scope="module")
def cfg():
    return syn.fast_cfg()


@pytest.fixture(scope="module")
def padded(work, cfg):
    src = syn.padded_clip(work / "padded.mp4")
    return normalize_video(src, work / "out_padded", cfg)


@pytest.fixture(scope="module")
def portrait(work, cfg):
    src = syn.clip(work / "portrait.mp4", size="288x512", dur=3.0)
    return normalize_video(src, work / "out_portrait", cfg)


def _probe(path):
    p = ffprobe(path)
    return p, stream(p, "video"), stream(p, "audio")


# ---------------------------------------------------------------- pure functions
def test_target_dims_never_upscale_beyond_need():
    assert target_dims(1920, 1080, 292) == (1920, 1080, False)
    assert target_dims(641, 361, 292) == (640, 360, False)       # even, no upscale
    assert target_dims(288, 512, 292) == (292, 520, True)        # minimal upscale, native aspect
    assert target_dims(320, 240, 292) == (390, 292, True)
    w, h, _ = target_dims(250, 251, 292)
    assert min(w, h) >= 292 and w % 2 == 0 and h % 2 == 0


def test_crop_coverage_geometry():
    c = crop_coverage(1920, 1080, 292, 256)
    assert c["crop_frac_width_outside"] == pytest.approx(1 - 256 / (292 * 16 / 9))
    assert c["crop_frac_height_outside"] == pytest.approx(1 - 256 / 292)
    sq = crop_coverage(500, 500, 292, 256)
    assert sq["crop_frac_width_outside"] == pytest.approx(sq["crop_frac_height_outside"])
    for v in c.values():
        assert 0.0 <= v < 1.0


# ---------------------------------------------------------------- full pipeline
def test_trims_leading_trailing_black_and_silence(padded):
    t = padded["trims"]
    assert t["trim_start_s"] == pytest.approx(2.0, abs=0.1)
    assert t["trim_end_s"] == pytest.approx(6.0, abs=0.1)
    assert padded["out_duration_s"] == pytest.approx(4.0, abs=0.15)
    assert t["trimmed_lead_s"] > 0 and t["trimmed_tail_s"] > 0


def test_normalize_ffprobe_assertions(padded):
    mp4 = Path(padded["path"])
    p, v, a = _probe(mp4)
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert v["r_frame_rate"] == "30/1" and v["avg_frame_rate"] == "30/1"
    assert a["codec_name"] == "aac" and int(a["sample_rate"]) == 48000
    assert float(p["format"]["duration"]) <= 58.5
    # content-hash name
    assert mp4.name == sha256_file(mp4)[:16] + ".mp4" and padded["video_id"] == mp4.stem
    # sidecar wav: 16 kHz mono, NOT next to the mp4 (TRIBE reuses <stem>.wav silently)
    wav = Path(padded["wav_path"])
    _, _, wa = _probe(wav)
    assert int(wa["sample_rate"]) == 16000 and int(wa["channels"]) == 1
    assert not (mp4.parent / f"{mp4.stem}.wav").exists()
    # record written, original res/fps/bitrate kept
    rec = json.loads((mp4.parent / f"{mp4.stem}.json").read_text())
    assert rec["source"]["width"] == 640 and rec["source"]["fps_avg"] == 30
    assert rec["source"]["bitrate_bps"] > 0


def test_speech_gated_loudness_and_true_peak(padded):
    assert padded["loudness_out_speech_lufs"] == pytest.approx(-23.0, abs=1.0)
    assert padded["true_peak_out_dbtp"] <= -1.0 + 0.5
    assert "loudness_off_target" not in padded["flags"]


def test_no_padding(padded, portrait):
    for rec, (w, h) in ((padded, (640, 360)), (portrait, (292, 520))):
        mp4 = rec["path"]
        _, v, _ = _probe(mp4)
        assert (int(v["width"]), int(v["height"])) == (w, h)
        assert int(v["width"]) / int(v["height"]) == pytest.approx(rec["source"]["width"] / rec["source"]["height"],
                                                                   rel=0.01)
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp4, "-vf", "cropdetect=limit=24:round=2:reset=0",
                              "-f", "null", "-"], capture_output=True, text=True).stderr
        assert re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", err)[-1] == (str(w), str(h), "0", "0")


def test_portrait_stratum_and_crop_covariate(portrait):
    assert portrait["stratum_9x16"] is True and portrait["aspect_label"] == "portrait"
    assert portrait["upscaled"] is True and "upscaled_to_min_short_side" in portrait["flags"]
    assert portrait["crop_frac_width_outside"] == pytest.approx(1 - 256 / 292, abs=1e-3)
    assert portrait["crop_frac_height_outside"] == pytest.approx(1 - 256 / 520, abs=1e-3)


def test_vfr_source_becomes_cfr30(work, cfg):
    rec = normalize_video(syn.vfr_clip(work / "vfr.mp4"), work / "out_vfr", cfg)
    assert rec["source"]["vfr"] is True and "source_vfr" in rec["flags"]
    _, v, _ = _probe(rec["path"])
    assert v["r_frame_rate"] == "30/1" and v["avg_frame_rate"] == "30/1"
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", rec["path"]], capture_output=True, text=True)
    assert int(n.stdout.strip()) == pytest.approx(rec["out_duration_s"] * 30, abs=2)


def test_mono_phase_flags_inverted_channel(work, cfg):
    bad = normalize_video(syn.inverted_stereo_clip(work / "inv.mp4"), work / "out_inv", cfg)
    assert bad["mono_phase_flag"] is True and bad["mono_phase_drop_db"] > 3.0 and "mono_phase" in bad["flags"]
    ok = normalize_video(syn.clip(work / "stereo_ok.mp4", dur=3.0), work / "out_ok", cfg)
    assert ok["mono_phase_flag"] is False and ok["mono_phase_drop_db"] == pytest.approx(0.0, abs=0.5)


def test_av_sync_offset_reported_and_flagged(work, cfg, padded):
    rec = normalize_video(syn.av_offset_clip(work / "av.mp4", offset_s=0.2), work / "out_av", cfg)
    assert rec["av_offset_ms"] > 40 and "av_sync_offset" in rec["flags"]
    assert abs(padded["av_offset_ms"]) <= 40 and "av_sync_offset" not in padded["flags"]


def test_t1_is_first_58s(work, cfg):
    src = syn.clip(work / "long.mp4", size="320x240", dur=61.0)
    rec = normalize_video(src, work / "out_long", cfg)
    assert 57.9 <= rec["out_duration_s"] <= 58.5
    assert rec["trimmed_duration_s"] == pytest.approx(61.0, abs=0.2)


def test_quality_floor_round_trip(work, cfg):
    rec = normalize_video(syn.clip(work / "hd.mp4", size="960x540", dur=2.0), work / "out_hd", cfg)
    assert rec["q480_low_dims"] == [854, 480]
    q = Path(rec["q480_path"])
    _, v, a = _probe(q)
    assert (int(v["width"]), int(v["height"])) == (960, 540) and a is not None
    assert q.stem == rec["q480_sha256"][:16] and q.parent.name == "q480"


def test_deterministic_names_and_t1_unchanged_by_photometric(work, cfg, padded):
    src = work / "padded.mp4"
    again = normalize_video(src, work / "out_again", cfg)
    no_t3 = normalize_video(src, work / "out_no_t3", syn.fast_cfg(normalize={"photometric": {"enabled": False}}))
    assert again["video_id"] == padded["video_id"] == no_t3["video_id"]
    assert "t3" not in no_t3


def test_sidecar_wav_matches_mp4_audio(padded):
    x = decode_audio(padded["wav_path"], 16000, 1)[:, 0]
    assert len(x) / 16000 == pytest.approx(padded["out_duration_s"], abs=0.1)
    assert np.sqrt(np.mean(x**2)) > 0


def test_cli_prints_json(work, capsys):
    src = syn.clip(work / "cli.mp4", dur=2.0)
    cfg_path = work / "fast.yaml"
    import yaml

    cfg_path.write_text(yaml.safe_dump(syn.fast_cfg(normalize={"photometric": {"enabled": False}})))
    assert cli_main(["--in", str(src), "--out", str(work / "out_cli"), "--config", str(cfg_path)]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert Path(rec["path"]).exists() and rec["video_id"] == Path(rec["path"]).stem
