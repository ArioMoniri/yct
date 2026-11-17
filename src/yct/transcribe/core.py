"""P2b transcripts in TRIBE's event format (v2.md §5 P2b; tribe_requirements §2.2, §2.4).

TRIBE (`ExtractWordsFromAudio`) caches WhisperX output as `<wav_stem>.tsv` with columns
`text, start, duration, sequence_id, sentence` (seconds from file start, one row per aligned word,
sequence_id = WhisperX segment index, sentence = that segment's text) and skips ASR when the file exists.
We write that file from our pinned WhisperX run, beside `<stem>.mp4`, before every TRIBE run:

  prepare_tribe_inputs(dir):  1. purge feature cache + stale .wav   2. write the pinned .tsv
                              3. assert the .tsv sha256 matches the transcript manifest
                              4. `asr_guard()` makes any whisperx/uvx subprocess raise
                              5. assert content-hash filenames (<sha256[:16]>.mp4)
"""

from __future__ import annotations

import contextlib
import csv
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from yct.config import load_config
from yct.media import sha256_file


class TsvFormatError(ValueError):
    pass


class UnpinnedASRError(RuntimeError):
    pass


# ---------------------------------------------------------------- words <-> tsv
def whisperx_segments_to_words(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """WhisperX aligned JSON segments -> TRIBE word rows (words without an aligned start are dropped)."""
    rows = []
    for i, seg in enumerate(segments):
        sentence = str(seg.get("text", "")).strip().replace('"', "")
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue
            rows.append(
                {
                    "text": str(w["word"]).strip().replace('"', ""),
                    "start": float(w["start"]),
                    "duration": float(w["end"]) - float(w["start"]),
                    "sequence_id": i,
                    "sentence": sentence,
                }
            )
    return rows


def write_tribe_tsv(words: Iterable[dict[str, Any]], path: str | Path, cfg: dict | None = None) -> Path:
    cols = (cfg or load_config())["transcribe"]["tsv_columns"]
    df = pd.DataFrame(list(words), columns=cols)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    return path


def validate_tsv(
    path: str | Path, media_duration_s: float | None = None, cfg: dict | None = None
) -> pd.DataFrame:
    """Raise TsvFormatError unless `path` is a TRIBE-format word tsv."""
    tc = (cfg or load_config())["transcribe"]
    try:
        df = pd.read_csv(path, sep="\t", keep_default_na=False, dtype={"text": str, "sentence": str})
    except Exception as exc:  # noqa: BLE001 - any parse failure is a format failure
        raise TsvFormatError(f"{path}: unreadable as tsv: {exc}") from exc
    if list(df.columns) != list(tc["tsv_columns"]):
        raise TsvFormatError(f"{path}: columns {list(df.columns)} != {tc['tsv_columns']}")
    if df.empty:
        return df
    for col in ("start", "duration"):
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise TsvFormatError(f"{path}: {col} not numeric")
        if not df[col].map(math.isfinite).all():
            raise TsvFormatError(f"{path}: non-finite {col}")
    if not pd.api.types.is_integer_dtype(df["sequence_id"]):
        raise TsvFormatError(f"{path}: sequence_id not integer")
    if (df["text"].str.strip() == "").any():
        raise TsvFormatError(f"{path}: empty word text")
    if (df["start"] < 0).any() or (df["duration"] < 0).any():
        raise TsvFormatError(f"{path}: negative start/duration")
    if (df["start"].diff().dropna() < 0).any():
        raise TsvFormatError(f"{path}: start times not monotonic")
    if (df["sequence_id"].diff().dropna() < 0).any():
        raise TsvFormatError(f"{path}: sequence_id not monotonic")
    if media_duration_s is not None:
        end = float((df["start"] + df["duration"]).max())
        if end > media_duration_s + tc["end_tolerance_s"]:
            raise TsvFormatError(f"{path}: last word ends at {end:.3f}s > media {media_duration_s:.3f}s")
    unmatched = sum(
        str(t).lower().strip(".,!?;:") not in str(s).lower()
        for t, s in zip(df["text"], df["sentence"], strict=True)
    )
    if unmatched / len(df) > tc["max_unmatched_ratio"]:
        raise TsvFormatError(f"{path}: {unmatched}/{len(df)} words not found in their sentence")
    return df


# ---------------------------------------------------------------- pinned WhisperX wrapper (runs on GPU)
def whisperx_command(wav: str | Path, out_dir: str | Path, cfg: dict | None = None) -> list[str]:
    w = (cfg or load_config())["transcribe"]["whisperx"]
    return [
        w["executable"],
        str(wav),
        "--model",
        w["model"],
        "--language",
        w["language"],
        "--device",
        w["device"],
        "--compute_type",
        w["compute_type"],
        "--batch_size",
        str(w["batch_size"]),
        "--align_model",
        w["align_model"],
        "--output_format",
        "json",
        "--output_dir",
        str(out_dir),
    ]


def _installed_whisperx_version() -> str | None:
    try:
        return importlib.metadata.version("whisperx")
    except importlib.metadata.PackageNotFoundError:
        return None


def transcribe_whisperx(
    wav: str | Path,
    cfg: dict | None = None,
    runner: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Run pinned WhisperX on `wav`; return {'words', 'segments', 'model', 'version', 'command'}.

    `runner` defaults to subprocess.run(check=True); tests inject a fake that writes the JSON.
    """
    cfg = cfg or load_config()
    w = cfg["transcribe"]["whisperx"]
    version = _installed_whisperx_version()
    if w.get("version") and version and version != w["version"]:
        raise UnpinnedASRError(f"whisperx {version} installed, config pins {w['version']}")
    run = runner or (lambda c: subprocess.run(c, check=True))
    with tempfile.TemporaryDirectory() as td:
        cmd = whisperx_command(wav, td, cfg)
        run(cmd)
        out = Path(td) / f"{Path(wav).stem}.json"
        segments = json.loads(out.read_text())["segments"]
    return {
        "words": whisperx_segments_to_words(segments),
        "segments": segments,
        "model": w["model"],
        "version": version,
        "command": cmd,
    }


# ---------------------------------------------------------------- transcript store + manifest
def read_manifest(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, newline="") as fh:
        return {r["video_id"]: r["tsv_sha256"] for r in csv.DictReader(fh)}


def store_transcript(
    video_id: str,
    words: Iterable[dict[str, Any]],
    store_dir: str | Path,
    manifest: str | Path,
    media_duration_s: float | None = None,
    cfg: dict | None = None,
) -> str:
    """Write <store_dir>/<video_id>.tsv, validate it, and record its sha256 in the manifest csv."""
    cfg = cfg or load_config()
    tsv = write_tribe_tsv(words, Path(store_dir) / f"{video_id}.tsv", cfg)
    validate_tsv(tsv, media_duration_s, cfg)
    digest = sha256_file(tsv)
    rows = read_manifest(manifest)
    rows[video_id] = digest
    cols = cfg["transcribe"]["manifest_columns"]
    with open(manifest, "w", newline="") as fh:
        wr = csv.writer(fh, lineterminator="\n")
        wr.writerow(cols)
        for vid in sorted(rows):
            wr.writerow([vid, rows[vid]])
    return digest


# ---------------------------------------------------------------- pre-run preparation
@contextlib.contextmanager
def asr_guard():
    """Any subprocess whose argv mentions whisperx or uvx raises UnpinnedASRError (v2.2 P2b step 4)."""
    banned = ("whisperx", "uvx")

    def check(args: Any) -> None:
        argv = [args] if isinstance(args, str | bytes | Path) else list(args)
        text = " ".join(str(a) for a in argv).lower()
        if any(b in text for b in banned):
            raise UnpinnedASRError(f"unpinned ASR call blocked: {text[:200]}")

    orig_popen_init = subprocess.Popen.__init__

    def guarded_init(self, args, *a, **k):
        check(args)
        return orig_popen_init(self, args, *a, **k)

    orig_system = os.system

    def guarded_system(cmd):
        check(cmd)
        return orig_system(cmd)

    subprocess.Popen.__init__ = guarded_init
    os.system = guarded_system
    try:
        yield
    finally:
        subprocess.Popen.__init__ = orig_popen_init
        os.system = orig_system


def prepare_tribe_inputs(
    tribe_dir: str | Path,
    store_dir: str | Path,
    manifest: str | Path,
    cache_dir: str | Path | None = None,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Run P2b steps 1-3 and 5 for every <stem>.mp4 in tribe_dir; returns an ordered step log.

    Raises if any transcript is missing, its sha256 differs from the manifest, or a filename is not
    its content hash. Wrap the subsequent TRIBE call in `asr_guard()` (step 4).
    """
    cfg = cfg or load_config()
    hash_len = cfg["normalize"]["hash_len"]
    tribe_dir, store_dir = Path(tribe_dir), Path(store_dir)
    log: list[dict[str, Any]] = []
    mp4s = sorted(tribe_dir.glob("*.mp4"))

    # 5. content-hash filenames
    for m in mp4s:
        if sha256_file(m)[:hash_len] != m.stem:
            raise ValueError(f"{m.name} is not named by its content hash")
    log.append({"step": "content_hash_names", "n": len(mp4s)})

    # 1. purge feature cache and stale .wav / .tsv (TRIBE reuses both by filename without checking)
    purged = []
    if cache_dir is not None and Path(cache_dir).exists():
        for p in Path(cache_dir).iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            purged.append(str(p))
    for pat in ("*.wav", "*.tsv"):
        for p in tribe_dir.glob(pat):
            p.unlink()
            purged.append(str(p))
    log.append({"step": "purge", "removed": purged})

    # 2. write pinned tsv, then 3. assert sha256 matches manifest
    want = read_manifest(manifest)
    written = []
    for m in mp4s:
        src = store_dir / f"{m.stem}.tsv"
        if not src.exists():
            raise FileNotFoundError(f"no pinned transcript for {m.stem}")
        dst = tribe_dir / f"{m.stem}.tsv"
        shutil.copyfile(src, dst)
        written.append(str(dst))
    log.append({"step": "write_tsv", "written": written})
    for m in mp4s:
        dst = tribe_dir / f"{m.stem}.tsv"
        if not dst.exists():
            raise FileNotFoundError(dst)
        got = sha256_file(dst)
        if want.get(m.stem) != got:
            raise ValueError(f"{dst.name}: sha256 {got[:12]} != manifest {str(want.get(m.stem))[:12]}")
    log.append({"step": "assert_sha256", "n": len(mp4s)})
    return {"steps": log}
