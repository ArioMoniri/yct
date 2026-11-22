"""D-085 draft, council-only items in scripts/refclips_build.py: BUG-044 S3 read-back of every source
image (exists + sha256 == manifest), libx264 version recorded in the toolchain, and the D-085 QC path
refused until controls.refclips_d085 is frozen."""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from yct.config import load_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refclips_build_d085", ROOT / "scripts" / "refclips_build.py")
B = importlib.util.module_from_spec(spec)
sys.modules["refclips_build_d085"] = B
spec.loader.exec_module(B)
CFG = load_config()


def _mans():
    a, b = b"img-a", b"img-b"
    return ({"face": [{"file": "a.jpg", "s3_key": "refstim/a.jpg", "sha256": hashlib.sha256(a).hexdigest()}],
             "body": [{"file": "b.jpg", "s3_key": "refstim/b.jpg", "sha256": hashlib.sha256(b).hexdigest()}]},
            {"refstim/a.jpg": a, "refstim/b.jpg": b})


def test_s3_readback_passes_when_every_key_exists_with_the_manifest_sha():
    mans, store = _mans()
    rec = B.verify_s3_sources(mans, store.get)
    assert rec == {"refstim/a.jpg": mans["face"][0]["sha256"], "refstim/b.jpg": mans["body"][0]["sha256"]}


def test_s3_readback_refuses_a_missing_or_altered_object():
    mans, store = _mans()
    with pytest.raises(SystemExit, match="missing"):
        B.verify_s3_sources(mans, {"refstim/a.jpg": store["refstim/a.jpg"]}.get)
    store["refstim/b.jpg"] = b"tampered"
    with pytest.raises(SystemExit, match="sha256"):
        B.verify_s3_sources(mans, store.get)


def test_toolchain_records_the_libx264_package_version(monkeypatch):
    def fake_run(cmd, **kw):
        out = {"ffmpeg": "ffmpeg version 6.1.1-3ubuntu5\nlibavcodec 60.31.102\n",
               "dpkg-query": "libx264-164:amd64 2:0.164.3108+git31e19f9-1\n"}[cmd[0]]
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    monkeypatch.setattr(B.subprocess, "run", fake_run)
    tc = B.toolchain()
    assert tc["ffmpeg"].startswith("ffmpeg version 6.1.1") and "0.164.3108" in tc["libx264"]


def test_d085_qc_path_is_refused_until_frozen(tmp_path):
    with pytest.raises(SystemExit, match="not frozen"):
        B.build_all([], tmp_path, CFG, qc="d085")
