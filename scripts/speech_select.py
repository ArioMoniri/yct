#!/usr/bin/env python3
"""D-085 part 2 step 2: speech selection on the pod (CPU). Texts private, numbers public, no listening.

  python scripts/speech_select.py OUT_PUBLIC_JSON PRIVATE_S3_URI

Refuses unless the corpus sha and the speech key are frozen (speech_corpus.require_frozen). Fetches the
private raw page, verifies it and every item sha (resolve_texts), builds EspeakSynth (verifies the espeak-ng
pin first, fail closed), runs the frozen select, uploads the full log (with texts) to the private bucket,
and writes the public record: kept/rejected ids (source sha256s), spans, pass rates with Wilson 95% intervals
(descriptive only). Queue exhaustion is a STOP to the owner (exit 1, nothing public written).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from yct.tribe_run import speech_corpus as S  # noqa: E402,N812


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def public(sel: dict, verified: dict, corpus_sha: str, commit: str) -> dict:
    rates = {}
    for f, r in sel["pass_rates"].items():
        lo, hi = wilson(r["kept"], r["tried"])
        rate = round(r["kept"] / r["tried"], 4) if r["tried"] else None
        rates[f] = {**r, "rate": rate, "wilson95": [lo, hi]}
    return {"decision": "D-085 part 2 step 2", "corpus_sha256": corpus_sha, "engine_verified": verified,
            "code_commit": commit, "texts_public": False, "queue_used": sel["queue_used"],
            "queue_used_by_family": sel.get("queue_used_by_family"),
            "rate_wpm_by_family": sel.get("rate_wpm_by_family"),
            "pass_rates": rates, "items": S.public_record(sel["items"]),
            "rejects": S.public_record(sel["rejects"])}


def stop_record(partial: dict, verified: dict, corpus_sha: str, commit: str) -> dict:
    """Public STOP record on queue exhaustion: numbers and ids only (the frozen rule: STOP to the owner)."""
    rec = public(partial, verified, corpus_sha, commit)
    rec.update(stop="queue_exhausted", final_stop=True,        # D-089 v2: final in every family
               stopped_at={"family": partial["family"], "slot": partial["slot"],
                           "queue_position": partial["queue_used"]},
               kept_counts={f: len(v) for f, v in partial["items"].items()})
    return rec


def _s3(args: list[str]) -> None:
    subprocess.run(["aws", "s3", *args, "--only-show-errors"], check=True,
                   env={**os.environ, "AWS_DEFAULT_REGION": "eu-central-1"})


def require_d089(cfg: dict) -> None:
    """D-089: when the refclips_d089 block exists, selection runs only after it is frozen."""
    if cfg["controls"].get("refclips_d089") and not any(
            f.get("key") == "controls.refclips_d089" for f in cfg.get("frozen", [])):
        raise SystemExit("controls.refclips_d089 is not frozen: no D-089 selection before the freeze (STOP)")


def run(cfg: dict, raw: bytes, synth) -> dict:
    S.require_frozen(cfg)
    require_d089(cfg)
    spec = S.effective_spec(cfg)
    doc = json.loads((ROOT / spec["corpus_file"]).read_text())
    queue = S.resolve_texts(doc, raw)
    return S.select(queue, synth, spec)


def main() -> int:
    from yct.config import load_config
    from yct.tribe_run.espeak_engine import EspeakSynth

    out, private_uri = Path(sys.argv[1]), sys.argv[2]
    cfg = load_config()
    S.require_frozen(cfg)
    require_d089(cfg)
    spec = S.effective_spec(cfg)
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "raw.html"
        _s3(["cp", spec["private_raw_s3"], str(dst)])
        raw = dst.read_bytes()
    synth = EspeakSynth(spec)                       # pin verified here, before any synthesis
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    corpus_sha = hashlib.sha256((ROOT / spec["corpus_file"]).read_bytes()).hexdigest()
    try:
        sel = run(cfg, raw, synth)
    except S.CorpusStopError as e:
        if e.partial is None:
            print(json.dumps({"stop": str(e)}))
            return 1
        rec = stop_record(e.partial, synth.verified, corpus_sha, commit)
        stop_out = out.with_name(out.stem + "_STOP.json")
        stop_out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps({"stop": str(e), "stopped_at": rec["stopped_at"], "kept": rec["kept_counts"],
                          "pass_rates": rec["pass_rates"], "queue_used": rec["queue_used"]}))
        return 1
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "selection_private.json"
        p.write_text(json.dumps({**sel, "code_commit": commit}, indent=1, sort_keys=True))
        _s3(["cp", str(p), private_uri])
    rec = public(sel, synth.verified, corpus_sha, commit)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"pass_rates": rec["pass_rates"], "queue_used": rec["queue_used"],
                      "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
