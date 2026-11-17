"""P2b tests: test_tsv_format, test_cache_purged, pinned-WhisperX wrapper (mocked), ASR guard."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from yct.config import load_config
from yct.media import sha256_file
from yct.transcribe import (
    TsvFormatError,
    UnpinnedASRError,
    asr_guard,
    prepare_tribe_inputs,
    read_manifest,
    store_transcript,
    transcribe_whisperx,
    validate_tsv,
    whisperx_command,
    whisperx_segments_to_words,
    write_tribe_tsv,
)

SEGMENTS = [
    {"text": " Hi, we are Acme.", "words": [
        {"word": "Hi,", "start": 0.50, "end": 0.80},
        {"word": "we", "start": 0.90, "end": 1.00},
        {"word": "are", "start": 1.05, "end": 1.20},
        {"word": "Acme.", "start": 1.25, "end": 1.70},
    ]},
    {"text": " We build 3D tools.", "words": [
        {"word": "We", "start": 2.00, "end": 2.10},
        {"word": "build", "start": 2.15, "end": 2.40},
        {"word": "3D"},                                   # unaligned -> dropped (TRIBE l.147-148)
        {"word": "tools.", "start": 2.80, "end": 3.20},
    ]},
]


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def words():
    return whisperx_segments_to_words(SEGMENTS)


def test_segments_to_words(words):
    assert len(words) == 7
    assert words[0] == {"text": "Hi,", "start": 0.5, "duration": pytest.approx(0.3), "sequence_id": 0,
                        "sentence": "Hi, we are Acme."}
    assert {w["sequence_id"] for w in words} == {0, 1}


def test_tsv_format(tmp_path, words, cfg):
    p = write_tribe_tsv(words, tmp_path / "abc.tsv", cfg)
    header = p.read_text().splitlines()[0]
    assert header == "text\tstart\tduration\tsequence_id\tsentence"
    df = validate_tsv(p, media_duration_s=4.0, cfg=cfg)
    assert len(df) == 7 and df["start"].is_monotonic_increasing
    assert (df["start"] >= 0).all() and (df["duration"] >= 0).all()
    # TRIBE reads it back with pandas the same way
    back = pd.read_csv(p, sep="\t")
    assert list(back.columns) == cfg["transcribe"]["tsv_columns"]


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda df: df.drop(columns=["sentence"]), "columns"),
        (lambda df: df[["start", "text", "duration", "sequence_id", "sentence"]], "columns"),
        (lambda df: df.assign(start=df["start"][::-1].values), "monotonic"),
        (lambda df: df.assign(duration=-df["duration"]), "negative"),
        (lambda df: df.assign(start=df["start"] + 10), "media"),
        (lambda df: df.assign(sentence="unrelated words only"), "sentence"),
    ],
)
def test_tsv_format_rejects_bad_files(tmp_path, words, cfg, mutate, msg):
    df = mutate(pd.DataFrame(words))
    p = tmp_path / "bad.tsv"
    df.to_csv(p, sep="\t", index=False)
    with pytest.raises(TsvFormatError, match=msg):
        validate_tsv(p, media_duration_s=4.0, cfg=cfg)


def test_whisperx_wrapper_pinned_and_mocked(tmp_path, cfg):
    wav = tmp_path / "abcd.wav"
    wav.write_bytes(b"")
    seen = {}

    def fake_runner(cmd):
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("--output_dir") + 1]) / "abcd.json"
        out.write_text(json.dumps({"segments": SEGMENTS}))

    res = transcribe_whisperx(wav, cfg, runner=fake_runner)
    cmd = seen["cmd"]
    assert cmd[cmd.index("--model") + 1] == "large-v3" == cfg["transcribe"]["whisperx"]["model"]
    assert cmd[cmd.index("--language") + 1] == "en"
    assert cmd[cmd.index("--align_model") + 1] == "WAV2VEC2_ASR_LARGE_LV60K_960H"
    assert cmd == whisperx_command(wav, cmd[cmd.index("--output_dir") + 1], cfg)
    assert len(res["words"]) == 7 and res["model"] == "large-v3"


def _tribe_dir(tmp_path, cfg, words):
    tribe = tmp_path / "tribe"
    tribe.mkdir()
    data = b"fake mp4 bytes"
    import hashlib

    stem = hashlib.sha256(data).hexdigest()[:16]
    (tribe / f"{stem}.mp4").write_bytes(data)
    store, manifest = tmp_path / "store", tmp_path / "transcripts_manifest.csv"
    store_transcript(stem, words, store, manifest, media_duration_s=4.0, cfg=cfg)
    return tribe, store, manifest, stem


def test_cache_purged(tmp_path, cfg, words):
    tribe, store, manifest, stem = _tribe_dir(tmp_path, cfg, words)
    stale_wav = tribe / f"{stem}.wav"
    stale_wav.write_bytes(b"stale 44.1k extraction")
    stale_tsv = tribe / f"{stem}.tsv"
    stale_tsv.write_text("text\tstart\tduration\tsequence_id\tsentence\nold\t0\t1\t0\told\n")
    cache = tmp_path / "cache"
    (cache / "audio").mkdir(parents=True)
    (cache / "audio" / "feat.npy").write_bytes(b"x")
    (cache / "top.pkl").write_bytes(b"x")

    log = prepare_tribe_inputs(tribe, store, manifest, cache_dir=cache, cfg=cfg)

    assert list(cache.iterdir()) == []
    assert not stale_wav.exists()
    assert sha256_file(tribe / f"{stem}.tsv") == read_manifest(manifest)[stem]
    steps = [s["step"] for s in log["steps"]]
    assert steps.index("purge") < steps.index("write_tsv") < steps.index("assert_sha256")
    assert str(stale_wav) in log["steps"][steps.index("purge")]["removed"]


def test_prepare_fails_on_manifest_mismatch(tmp_path, cfg, words):
    tribe, store, manifest, stem = _tribe_dir(tmp_path, cfg, words)
    (store / f"{stem}.tsv").write_text((store / f"{stem}.tsv").read_text().replace("Acme", "Acne"))
    with pytest.raises(ValueError, match="manifest"):
        prepare_tribe_inputs(tribe, store, manifest, cfg=cfg)


def test_prepare_fails_on_missing_transcript(tmp_path, cfg, words):
    tribe, store, manifest, stem = _tribe_dir(tmp_path, cfg, words)
    (store / f"{stem}.tsv").unlink()
    with pytest.raises(FileNotFoundError):
        prepare_tribe_inputs(tribe, store, manifest, cfg=cfg)


def test_prepare_requires_content_hash_names(tmp_path, cfg, words):
    tribe, store, manifest, stem = _tribe_dir(tmp_path, cfg, words)
    (tribe / "video.mp4").write_bytes(b"other")
    with pytest.raises(ValueError, match="content hash"):
        prepare_tribe_inputs(tribe, store, manifest, cfg=cfg)


def test_asr_guard_blocks_whisperx_and_uvx():
    with asr_guard():
        with pytest.raises(UnpinnedASRError):
            subprocess.run(["uvx", "whisperx", "a.wav"])
        with pytest.raises(UnpinnedASRError):
            subprocess.Popen("whisperx a.wav", shell=True)
        with pytest.raises(UnpinnedASRError):
            os.system("uvx whisperx a.wav")
        assert subprocess.run(["true"]).returncode == 0
    assert subprocess.run(["echo", "uvx"], capture_output=True).returncode == 0  # restored
