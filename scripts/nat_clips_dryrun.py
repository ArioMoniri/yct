"""NAT reference-clip build dry run (D-071 (c)/(d), D-084): pod-side, CPU-only, read-only.

The NAT clips are the 15 manifest rows' trimmed T1 clips (P1/P2/P2b/P3, identical to analysis T1), not
built by refclips_build.py. Before the manifest sha is frozen this checks, numbers only, that every input the
clip-manifest step needs is present and matches the committed manifest: the T1 mp4 (sha256 == t1_sha256), the
16 kHz wav (sha256 == wav_sha256), the T1 record json, and the P2b transcript file (sha only; never read).
It also records ffprobe stream facts. Writes one JSON record; changes nothing, uploads nothing.

Usage: nat_clips_dryrun.py --manifest data/refstim/nat_manifest.json --t1-dir /work/yct/nat_scratch/t1
       --asr-dir /work/yct/nat_asr/asr --out <record.json> [--no-probe]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe(p: Path) -> dict:
    entries = "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels"
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(p)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st = {s["codec_type"]: s for s in j.get("streams", [])}
    v, a = st.get("video", {}), st.get("audio", {})
    return {"duration_s": round(float(j["format"]["duration"]), 3), "v_codec": v.get("codec_name"),
            "width": v.get("width"), "height": v.get("height"), "r_frame_rate": v.get("r_frame_rate"),
            "a_codec": a.get("codec_name"), "sample_rate": a.get("sample_rate"),
            "channels": a.get("channels")}


def check(manifest: list[dict], t1_dir: Path, asr_dir: Path, do_probe: bool = True) -> dict:
    rows, problems = [], []
    for i, r in enumerate(manifest):
        t = r["t1_name"]
        mp4, wav, rec = t1_dir / f"{t}.mp4", t1_dir / "audio16k" / f"{t}.wav", t1_dir / f"{t}.json"
        tr = sorted(asr_dir.glob(f"{t}.*")) if asr_dir.is_dir() else []
        row = {"slot": f"nat_{i:02d}", "t1_name": t, "session": r["session"],
               "mp4": mp4.is_file(), "wav": wav.is_file(), "record": rec.is_file(), "transcripts": len(tr)}
        if row["mp4"]:
            row["mp4_sha_ok"] = sha256(mp4) == r["t1_sha256"]
            if do_probe:
                row["probe"] = probe(mp4)
        if row["wav"]:
            row["wav_sha_ok"] = sha256(wav) == r["wav_sha256"]
        row["transcript_sha256"] = [sha256(p) for p in tr]
        for k in ("mp4", "wav", "record", "mp4_sha_ok", "wav_sha_ok"):
            if row.get(k) is False or k not in row:
                problems.append(f"{t}: {k}")
        if not tr:
            problems.append(f"{t}: transcript")
        rows.append(row)
    return {"n": len(rows), "ok": not problems, "problems": problems, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--t1-dir", required=True)
    ap.add_argument("--asr-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args(argv)
    man = json.loads(Path(a.manifest).read_text())
    res = check(man, Path(a.t1_dir), Path(a.asr_dir), not a.no_probe)
    res["manifest_sha256"] = sha256(Path(a.manifest))
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({"n": res["n"], "ok": res["ok"], "problems": res["problems"]}))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
