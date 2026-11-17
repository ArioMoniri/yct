#!/usr/bin/env python3
"""Wave-1 P2b (transcripts) + speech-rate confound refresh, POD side (run with /work/yct/venv python).

Stages (label-blind: reads only data/manifest.csv `in_primary` via the P2 runlog, never titles/URLs/outcomes):
  inputs  OUT.csv           video_id -> T1/T3 content ids, wav path, T1 duration (pod-only file)
  ingest  INPUTS JSON_DIR   WhisperX <content_id>.json -> TRIBE .tsv in /work/yct/transcripts (named by the T1
                            AND T3 content hash, the stems TRIBE sees) + manifest.csv (sha256), validated
                            against the media duration; label-free per-video summary (no text) to
                            /work/yct/summaries/wave1_transcripts_summary.csv; 5 WER hypothesis texts to
                            /work/yct/transcripts/wer_pending/ (hand-made references pending, owner/human)
  confounds INPUTS          apply_transcript() to every /work/yct/confounds/{t1,t3} parquet + summary json
                            (originals kept once as *.pre_p2b.*), then wave1_summ.py regenerates the CSVs
  wer                       WER for every wer_pending/<vid>.ref.txt that exists (none until hand-checked)

Transcripts hold speech text (may name companies): they live on the pod and in the private S3 bucket only.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

REPO = Path("/work/yct/repo")
sys.path.insert(0, str(REPO / "src"))
from yct.config import load_config  # noqa: E402
from yct.confounds import apply_transcript  # noqa: E402
from yct.transcribe import (  # noqa: E402
    TsvFormatError,
    read_manifest,
    store_transcript,
    validate_tsv,
    whisperx_segments_to_words,
)

N, C = Path("/work/yct/norm"), Path("/work/yct/confounds")
T = Path("/work/yct/transcripts")
MAN = T / "manifest.csv"
SUMM = Path("/work/yct/summaries")
WER_N = 5


def _ids() -> list[str]:
    with open(REPO / "data/manifest.csv") as f:
        return sorted(r["video_id"] for r in csv.DictReader(f) if r["in_primary"].strip().lower() == "true")


def inputs(out: str) -> None:
    rows = []
    for vid in _ids():
        done = N / "runlog" / f"{vid}.done"
        if not done.exists():
            continue
        h = done.read_text().strip()
        r = json.loads((N / "records" / f"{h}.json").read_text())
        rows.append({"video_id": vid, "content_id": h, "t3_content_id": Path(r["t3"]["t3_path"]).stem if r.get("t3") else "",
                     "wav_path": r["wav_path"], "t1_path": r["path"], "duration_s": r["out_duration_s"]})
    pd.DataFrame(rows).to_csv(out, index=False)
    print(json.dumps({"n": len(rows)}))


def _w_default(cfg: dict) -> tuple[float, float]:
    w, tr = cfg["window"], cfg["tribe"]["tr_s"]
    return w["default_start_tr"] * tr, (w["default_start_tr"] + w["default_len_tr"]) * tr


def ingest(inp: str, json_dir: str) -> None:
    cfg = load_config()
    w0, w1 = _w_default(cfg)
    min_w = cfg["m0"]["min_words_in_w"]
    T.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in pd.read_csv(inp, dtype=str, keep_default_na=False).to_dict("records"):
        vid, h, dur = r["video_id"], r["content_id"], float(r["duration_s"])
        jf = Path(json_dir) / f"{h}.json"
        row = {"video_id": vid, "content_id": h, "duration_s": dur}
        if not jf.exists():
            rows.append({**row, "tsv_valid": False, "flags": "no_whisperx_json"})
            continue
        segs = json.loads(jf.read_text())["segments"]
        words = whisperx_segments_to_words(segs)
        n_raw = sum(len(s.get("words", [])) for s in segs)
        flags = []
        try:
            digest = store_transcript(h, words, T, MAN, media_duration_s=dur, cfg=cfg)
            valid, err = True, ""
        except TsvFormatError as exc:
            valid, err, digest = False, re.sub(r"^\S+: ", "", str(exc))[:160], ""
            flags.append("tsv_invalid")
        if r["t3_content_id"] and valid:  # TRIBE on T3 sees the T3 stem; audio is identical (photometric copy)
            store_transcript(r["t3_content_id"], words, T, MAN, media_duration_s=dur, cfg=cfg)
        df = pd.DataFrame(words, columns=cfg["transcribe"]["tsv_columns"])
        mid = df["start"] + df["duration"] / 2 if len(df) else pd.Series(dtype=float)
        n_w = int(((mid >= w0) & (mid < w1)).sum())
        unmatched = (sum(str(t).lower().strip(".,!?;:") not in str(s).lower()
                         for t, s in zip(df["text"], df["sentence"], strict=True)) / len(df)) if len(df) else 0.0
        if not len(df):
            flags.append("empty_transcript")
        if n_w < min_w:
            flags.append(f"lt{min_w}_words_in_W_default")
        if n_raw - len(df):
            flags.append("unaligned_words_dropped")
        rows.append({**row, "n_segments": len(segs), "n_words": len(df), "n_words_unaligned_dropped": n_raw - len(df),
                     "asr_word_speech_s": round(float(df["duration"].sum()), 3) if len(df) else 0.0,
                     "first_word_start_s": round(float(df["start"].min()), 3) if len(df) else None,
                     "last_word_end_s": round(float((df["start"] + df["duration"]).max()), 3) if len(df) else None,
                     "words_per_min": round(len(df) / dur * 60, 2), "W_default_s": f"[{w0:g},{w1:g})",
                     "n_words_in_W_default": n_w, "unmatched_ratio": round(unmatched, 4), "tsv_valid": valid,
                     "tsv_error": err, "tsv_sha256": digest, "flags": ";".join(flags)})
    SUMM.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out.to_csv(SUMM / "wave1_transcripts_summary.csv", index=False)
    # WER hypotheses: first WER_N video_ids (sorted, label-blind) with a non-empty valid transcript.
    wd = T / "wer_pending"
    wd.mkdir(exist_ok=True)
    pick = [r for r in rows if r.get("tsv_valid") and r.get("n_words", 0) > 0][:WER_N]
    for r in pick:
        tsv = validate_tsv(T / f"{r['content_id']}.tsv", r["duration_s"], cfg)
        (wd / f"{r['video_id']}.hyp.txt").write_text(" ".join(tsv["text"].astype(str)) + "\n")
    (wd / "README.txt").write_text(
        "P2b WER check (ROADMAP P2 DoD): hypothesis = pinned WhisperX words (whisperx 3.8.6, large-v3).\n"
        "PENDING HUMAN STEP: for each <video_id>.hyp.txt write <video_id>.ref.txt = a hand-checked verbatim\n"
        "transcript of the 58 s T1 audio (/work/yct/norm/audio16k/<content_id>.wav), then run\n"
        "  /work/yct/venv/bin/python /work/yct/repo/scripts/wave1_p2b_pod.py wer\n"
        f"Videos (first {WER_N} sorted video_ids with a non-empty transcript): "
        + ", ".join(r["video_id"] for r in pick) + "\n")
    print(json.dumps({"n": len(rows), "n_valid": int(out["tsv_valid"].sum()), "wer_pending": [r["video_id"] for r in pick],
                      "n_manifest": len(read_manifest(MAN)),
                      "flag_counts": out["flags"].str.split(";").explode().value_counts().to_dict()}))


def confounds(inp: str) -> None:
    cfg = load_config()
    n = 0
    for r in pd.read_csv(inp, dtype=str, keep_default_na=False).to_dict("records"):
        vid, h = r["video_id"], r["content_id"]
        tsv = T / f"{h}.tsv"
        if not tsv.exists():
            print(f"{vid}: no tsv, confounds left without speech rate")
            continue
        for kind, stem in (("t1", h), ("t3", r["t3_content_id"])):
            pq, sj = C / kind / f"{stem}.parquet", C / "summary" / f"{vid}.{kind}.json"
            if not (stem and pq.exists() and sj.exists()):
                continue
            bpq, bsj = pq.with_suffix(".pre_p2b.parquet"), sj.with_suffix(".pre_p2b.json")
            if not bpq.exists():
                shutil.copy2(pq, bpq)
                shutil.copy2(sj, bsj)
            df, s = apply_transcript(pd.read_parquet(bpq), json.loads(bsj.read_text()), tsv, cfg)
            s["transcript_sha256"] = read_manifest(MAN).get(h)
            df.to_parquet(pq, index=False)
            sj.write_text(json.dumps(s, indent=2, default=float))
            n += 1
    print(json.dumps({"updated": n}))


def _tok(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower()).split()


def wer_score(ref: str, hyp: str) -> float:
    r, h = _tok(ref), _tok(hyp)
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / max(1, len(r))


def wer() -> None:
    wd = T / "wer_pending"
    out = {}
    for ref in sorted(wd.glob("*.ref.txt")):
        vid = ref.name[: -len(".ref.txt")]
        out[vid] = round(wer_score(ref.read_text(), (wd / f"{vid}.hyp.txt").read_text()), 4)
    print(json.dumps({"wer": out, "n_hand_checked": len(out),
                      "mean": round(sum(out.values()) / len(out), 4) if out else None}))


if __name__ == "__main__":
    st = sys.argv[1]
    {"inputs": lambda: inputs(sys.argv[2]), "ingest": lambda: ingest(sys.argv[2], sys.argv[3]),
     "confounds": lambda: confounds(sys.argv[2]), "wer": wer}[st]()
