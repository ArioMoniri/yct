"""NAT word tsvs for the reference campaign (D-091; council refcampaign U2, route (c) sidecar).

The 15 NAT clips are the trimmed T1 clips of the frozen NAT manifest. Their pinned WhisperX json (made from
the T1-trimmed 16 kHz wav, NAT sessions 0-2) is converted with the SAME frozen P2b core that wave 1 used
(whisperx_segments_to_words -> store_transcript -> validate_tsv against the clip's own media duration), into
a NAT-only store (controls.refclips_d091.nat_tsv.out_dir), never the wave-1 /work/yct/transcripts store or
its manifest. The D-067 / BUG-029 word-end clamp is applied on the box, as for T1, not here.

Provenance chain asserted per clip (fail closed): <t1>.json sha == the frozen clip manifest sha256.transcript;
audio16k/<t1>.wav sha == sha256.wav (the exact file the ASR box was given); <t1>.mp4 sha == sha256.mp4.
Only shas and counts leave the pod; tsv text is never read here beyond the frozen validator.
Any tsv_invalid or zero-word clip is a STOP to the owner (no substitution: the NAT selection is closed).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from yct.transcribe import TsvFormatError, store_transcript, whisperx_segments_to_words

WAVE1_TRANSCRIPTS = Path("/work/yct/transcripts")


class NatTsvError(SystemExit):
    """A provenance or store violation (exit 1, a human decides)."""


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def nat_rows(manifest: dict) -> list[dict]:
    """The NAT rows of the parsed frozen clip manifest, in index order."""
    rows = sorted((c for c in manifest["clips"] if c["family"] == "NAT"), key=lambda c: c["i"])
    for c in rows:
        for k in ("t1_name", "sha256"):
            if k not in c:
                raise NatTsvError(f"{c.get('name')}: NAT row lacks {k}")
        for k in ("mp4", "wav", "transcript"):
            if k not in c["sha256"]:
                raise NatTsvError(f"{c['name']}: NAT row lacks sha256.{k}")
    return rows


def build(rows: list[dict], json_dir: Path, t1_dir: Path, out_dir: Path, probe, cfg: dict,
          wave1_dir: Path = WAVE1_TRANSCRIPTS) -> dict:
    """Write <out_dir>/<CLIP_ID>.tsv for every NAT row and return the sidecar (shas + counts only)."""
    out_dir = Path(out_dir)
    if _inside(out_dir, wave1_dir):
        raise NatTsvError(f"{out_dir} is inside the wave-1 transcripts store {wave1_dir}")
    w1_man = Path(wave1_dir) / "manifest.csv"
    w1_before = sha256_file(w1_man) if w1_man.exists() else None
    out_dir.mkdir(parents=True, exist_ok=True)
    man = out_dir / "manifest.csv"
    res_rows, stop = [], []
    for c in rows:
        cid, t1 = f"NAT_{c['i']:02d}", c["t1_name"]
        jf, wav, mp4 = Path(json_dir) / f"{t1}.json", Path(t1_dir) / "audio16k" / f"{t1}.wav", \
            Path(t1_dir) / f"{t1}.mp4"
        for p, key in ((jf, "transcript"), (wav, "wav"), (mp4, "mp4")):
            if not p.is_file():
                raise NatTsvError(f"{cid}: {key} file missing")
            if sha256_file(p) != c["sha256"][key]:
                raise NatTsvError(f"{cid}: {key} sha256 != the frozen clip manifest (provenance)")
        dur = float(probe(mp4))
        segs = json.loads(jf.read_text())["segments"]
        words = whisperx_segments_to_words(segs)
        try:
            digest, valid = store_transcript(cid, words, out_dir, man, media_duration_s=dur, cfg=cfg), True
        except TsvFormatError:
            digest, valid = None, False
        row = {"clip_id": cid, "t1_name": t1, "transcript_json_sha256": c["sha256"]["transcript"],
               "wav_sha256": c["sha256"]["wav"], "mp4_sha256": c["sha256"]["mp4"],
               "duration_s": round(dur, 3),
               "n_raw_words": sum(len(s.get("words", [])) for s in segs), "n_words": len(words),
               "tsv_valid": valid, "tsv_sha256": digest}
        if not valid or len(words) < 1:
            stop.append(cid)
        res_rows.append(row)
    w1_after = sha256_file(w1_man) if w1_man.exists() else None
    if w1_after != w1_before:
        raise NatTsvError("the wave-1 transcripts manifest changed during the NAT tsv build")
    return {"decision": "D-091", "functions": ["whisperx_segments_to_words", "store_transcript",
                                               "validate_tsv"],
            "media_duration": "ffprobe_mp4", "n": len(res_rows), "rows": res_rows, "stop": stop,
            "wave1_manifest_sha256": w1_before}


def sidecar_text(sidecar: dict) -> str:
    return json.dumps(sidecar, indent=1, sort_keys=True) + "\n"
