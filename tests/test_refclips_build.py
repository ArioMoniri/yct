"""scripts/refclips_build.py: the pod-side builder of the non-NAT p4b_ref/v1 clips (D-071 (a)-(d)).
Guards only (no pod, no ffmpeg): frozen image manifest, family selection, speech-corpus refusal, QC STOP,
no upload before the clip-manifest freeze."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from yct.config import load_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refclips_build", ROOT / "scripts" / "refclips_build.py")
B = importlib.util.module_from_spec(spec)
sys.modules["refclips_build"] = B
spec.loader.exec_module(B)
CFG = load_config()


def test_image_manifest_guard_accepts_the_committed_frozen_manifests():
    mans = B.check_image_manifests(CFG, ROOT)
    assert [len(mans[c]) for c in ("face", "body", "place")] == [20, 20, 20]


def test_image_manifest_guard_refuses_unfrozen_or_mismatched(tmp_path):
    cfg = copy.deepcopy(CFG)
    key = "controls.refclips_artifacts.image_manifest_sha256"
    cfg["frozen"] = [f for f in cfg["frozen"] if f["key"] != key]
    with pytest.raises(SystemExit, match="not frozen"):
        B.check_image_manifests(cfg, ROOT)
    cfg = copy.deepcopy(CFG)
    cfg["controls"]["refclips_artifacts"]["image_manifest_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="sha"):
        B.check_image_manifests(cfg, ROOT)


def test_family_selection_refuses_nat_and_unfrozen_speech():
    assert set(B.select_families(CFG, None)) == {"GREY_CTRL", "FLASH", "LOC", "LOC_SCR", "MOT", "MOT_STAT"}
    with pytest.raises(SystemExit, match="NAT"):
        B.select_families(CFG, ["NAT"])
    for f in ("SPK", "BURST", "TALKFACE"):
        with pytest.raises(SystemExit, match="speech corpus"):
            B.select_families(CFG, [f])
    with pytest.raises(SystemExit, match="unknown"):
        B.select_families(CFG, ["OBJ"])


def test_mot_twins_are_built_together():
    with pytest.raises(SystemExit, match="twin"):
        B.select_families(CFG, ["MOT"])
    with pytest.raises(SystemExit, match="twin"):
        B.select_families(CFG, ["LOC_SCR"])
    assert set(B.select_families(CFG, ["MOT", "MOT_STAT"])) == {"MOT", "MOT_STAT"}


def test_qc_failure_is_a_stop_with_no_manifest(tmp_path, monkeypatch):
    clips = [c for c in B.R.plan(CFG) if c.family == "GREY_CTRL"]
    monkeypatch.setattr(B.R, "build_clip", lambda c, d, cfg, images=None, speech=None: {
        "name": c.name, "family": c.family, "sha256": {"mp4": "a" * 64}})
    monkeypatch.setattr(B.R, "stimulus_qc", lambda c, p, cfg, twin=None: {"name": c.name, "pass": False})
    rc = B.build_all(clips, tmp_path, CFG, images=None)
    assert rc == 1
    assert json.loads((tmp_path / "qc.json").read_text())[0]["pass"] is False
    assert (tmp_path / "STOP_NOTE.md").exists()
    assert not (tmp_path / "refclips_partial_manifest.json").exists()


def test_qc_pass_writes_partial_manifest_and_never_uploads(tmp_path, monkeypatch):
    clips = [c for c in B.R.plan(CFG) if c.family in ("GREY_CTRL", "FLASH")]
    monkeypatch.setattr(B.R, "build_clip", lambda c, d, cfg, images=None, speech=None: {
        "name": c.name, "family": c.family, "sha256": {"mp4": hashlib.sha256(c.name.encode()).hexdigest()}})
    monkeypatch.setattr(B.R, "stimulus_qc", lambda c, p, cfg, twin=None: {"name": c.name, "pass": True})
    monkeypatch.setattr(B, "toolchain", lambda: {"ffmpeg": "test"})
    called = []
    monkeypatch.setattr(B.subprocess, "run", lambda *a, **k: called.append(a))
    rc = B.build_all(clips, tmp_path, CFG, images=None)
    assert rc == 0
    m = json.loads((tmp_path / "refclips_partial_manifest.json").read_text())
    assert m["partial"] is True and "NAT" in m["families_missing"]
    assert sorted(r["name"] for r in m["clips"]) == sorted(c.name for c in clips)
    assert not any("s3" in " ".join(map(str, a[0])) for a in called)


def test_sources_resolve_from_local_scratch_by_sha256_and_upload_to_manifest_key(tmp_path, monkeypatch):
    """BUG-044: the T-LIC finalise wrote s3_key but never uploaded; the builder takes the source from the
    pod scratch by content sha256 only, uploads it to the frozen manifest s3_key, and decodes it."""
    import cv2
    import numpy as np

    scratch = tmp_path / "scratch" / "face"
    scratch.mkdir(parents=True)
    img = np.random.default_rng(1).integers(0, 256, (40, 50, 3)).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    f = scratch / "0123456789abcdef.org&utm_x"
    f.write_bytes(buf.tobytes())
    (scratch / "other.jpg").write_bytes(b"not it")
    row = {"title": "File:A.png", "s3_key": "sources/images/face/face_00.png",
           "sha256": hashlib.sha256(buf.tobytes()).hexdigest()}
    calls = []
    monkeypatch.setattr(B.subprocess, "run", lambda cmd, **k: calls.append(cmd))
    load = B.fetch_sources({"face": [row]}, CFG, tmp_path / "cache", local=[tmp_path / "scratch"])
    rgb = load(row)
    assert rgb.shape == (40, 50, 3) and np.array_equal(rgb, img[..., ::-1])
    up = [c for c in calls if c[:3] == ["aws", "s3", "cp"] and not c[-2].startswith("s3://")]
    assert len(up) == 1 and up[0][-1] == CFG["controls"]["refclips"]["s3_root"] + row["s3_key"]


def test_sources_refuse_when_no_local_or_s3_copy_matches(tmp_path, monkeypatch):
    row = {"title": "File:B.png", "s3_key": "sources/images/face/face_01.png", "sha256": "f" * 64}

    def fail(cmd, **k):
        raise B.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(B.subprocess, "run", fail)
    load = B.fetch_sources({"face": [row]}, CFG, tmp_path / "cache", local=[tmp_path])
    with pytest.raises(SystemExit, match="no source"):
        load(row)
