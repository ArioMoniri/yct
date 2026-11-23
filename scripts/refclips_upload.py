#!/usr/bin/env python3
"""D-091 reference-clip upload, POD side (council refcampaign U3): copy, never build.

    python scripts/refclips_upload.py --clip-manifest data/refstim/refclips_manifest.json \
        --nat-tsv data/refstim/nat_tsv_manifest.json --record data/refstim/refclips_upload_record.json

Reads the frozen clip manifest and the frozen NAT tsv sidecar (both sha-checked against config), copies
every file to controls.refclips_d091.upload.pod_dir/<CLIP_ID>.{mp4,wav,tsv}, re-hashes every copy, then
uploads to <refclips.s3_root>clips/ with .sha256 sidecars (refused if that prefix already holds objects that
are not byte-equal to the plan), downloads every object back and re-hashes it. Writes the shas-only record.
Exit 1 on any mismatch. AWS_DEFAULT_REGION=eu-central-1; yct bucket only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yct.config import load_config  # noqa: E402
from yct.tribe_run import ref_manifest as rm  # noqa: E402
from yct.tribe_run import refclips_upload as ru  # noqa: E402

VISUAL_DIR, SPEECH_DIR = "/work/yct/refclips_v2_build", "/work/yct/speech_build_v2"


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def aws(*args: str) -> str:
    env = {**os.environ, "AWS_DEFAULT_REGION": "eu-central-1"}
    return subprocess.run(["aws", *args], capture_output=True, text=True, check=True, env=env).stdout


def frozen_text(path: str, want: str | None, what: str) -> str:
    text = Path(path).read_text()
    if not want or hashlib.sha256(text.encode()).hexdigest() != want:
        raise SystemExit(f"{what} sha256 != the frozen config value")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip-manifest", required=True)
    ap.add_argument("--nat-tsv", required=True)
    ap.add_argument("--record", required=True)
    a = ap.parse_args(argv)
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1")
    cfg = load_config()
    art, d91 = cfg["controls"]["refclips_artifacts"], cfg["controls"]["refclips_d091"]
    man = json.loads(frozen_text(a.clip_manifest, art["manifest_sha256"], "clip manifest"))
    side = json.loads(frozen_text(a.nat_tsv, art["nat_tsv_manifest_sha256"], "NAT tsv sidecar"))
    adapted = rm.adapt(man, side)
    up = d91["upload"]
    pod_dir = Path(up["pod_dir"])
    s3_prefix = cfg["controls"]["refclips"]["s3_root"].rstrip("/") + "/" + up["s3_subdir"]
    if not s3_prefix.startswith("s3://yct-research-235229001983/"):
        raise SystemExit("s3 prefix outside the yct bucket")
    dirs = {"visual_dir": VISUAL_DIR, "speech_dir": SPEECH_DIR, "t1_dir": d91["nat_tsv"]["t1_dir"],
            "nat_tsv_dir": d91["nat_tsv"]["out_dir"], "pod_dir": str(pod_dir),
            "talkface_s3": cfg["controls"]["refclips_d085"]["talkface"]["mirror_s3"]}
    rows = ru.plan(adapted, dirs)
    pod_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:                                     # copy (never build), then re-hash
        dst = Path(r["dst"])
        if r["src_kind"] == "pod":
            shutil.copyfile(r["src"], dst)
        else:
            aws("s3", "cp", "--only-show-errors", r["src"], str(dst))
    pod_meas = {Path(r["dst"]).name: sha_file(Path(r["dst"])) for r in rows}
    pod_bad = ru.verify(rows, pod_meas, "pod")
    if pod_bad:
        print(json.dumps({"pod_mismatches": pod_bad}))
        Path(a.record).write_text(json.dumps(ru.record(rows, pod_bad, [], s3_prefix), indent=1,
                                             sort_keys=True) + "\n")
        return 1
    existing = [ln.split()[-1] for ln in aws("s3", "ls", s3_prefix).splitlines() if ln.strip()] \
        if subprocess.run(["aws", "s3", "ls", s3_prefix], capture_output=True).returncode == 0 else []
    plan_names = {Path(r["dst"]).name for r in rows} | {Path(r["dst"]).name + ".sha256" for r in rows}
    if set(existing) - plan_names:
        extra = sorted(set(existing) - plan_names)[:3]
        raise SystemExit(f"{s3_prefix} holds objects outside the plan: {extra}")
    for r in rows:
        dst = Path(r["dst"])
        aws("s3", "cp", "--only-show-errors", str(dst), s3_prefix + dst.name)
        side_f = dst.with_suffix(dst.suffix + ".sha256")
        side_f.write_text(f"{r['sha256']}  {dst.name}\n")
        aws("s3", "cp", "--only-show-errors", str(side_f), s3_prefix + side_f.name)
    with tempfile.TemporaryDirectory() as tmp:          # read every object back and re-hash it
        aws("s3", "cp", "--only-show-errors", "--recursive", "--exclude", "*.sha256", s3_prefix, tmp)
        s3_meas = {p.name: sha_file(p) for p in Path(tmp).iterdir() if p.is_file()}
    s3_bad = ru.verify(rows, s3_meas, "s3")
    rec = ru.record(rows, pod_bad, s3_bad, s3_prefix)
    Path(a.record).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: rec[k] for k in ("n_clips", "n_files", "ok", "pod_mismatches", "s3_mismatches")}))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
