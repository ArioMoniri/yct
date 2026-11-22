"""D-087 v2 re-check (wf_6140ad4f-5e3): the outcome-blind real-path smoke of scripts/locscreen_v2.py, the
--local default including SCRATCH, the no-upload source loader and the toolchain record. Tests first."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import locimg
from yct.tribe_run import refclips58 as R  # noqa: N812

ROOT = Path(__file__).resolve().parents[1]
CATS = ["face", "body", "place"]


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_local_default_includes_the_scratch():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    assert drv.local_dirs(None, Path("/s")) == [Path("/work/yct/refstim_auto_scratch"), Path("/s")]
    assert drv.local_dirs([Path("/a")], Path("/s")) == [Path("/a"), Path("/s")]
    assert drv.local_dirs([Path("/s")], Path("/s")) == [Path("/s")]


def test_fetch_sources_no_upload_never_uploads(tmp_path, monkeypatch):
    bld = _mod("refclips_build", "scripts/refclips_build.py")
    import cv2
    src = tmp_path / "local" / "a.png"
    src.parent.mkdir()
    cv2.imwrite(str(src), np.full((8, 8, 3), 100, np.uint8))
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    calls = []

    class Done:
        returncode = 1

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        if k.get("check"):
            raise bld.subprocess.CalledProcessError(1, cmd)
        return Done()
    monkeypatch.setattr(bld.subprocess, "run", fake_run)
    load = bld.fetch_sources({}, load_config(), tmp_path / "cache", local=[src.parent], upload=False)
    img = load({"s3_key": "sources/images/place/v2/x.png", "sha256": sha, "title": "t"})
    assert img.shape == (8, 8, 3)
    uploads = [c for c in calls if len(c) >= 2 and str(c[-1]).startswith("s3://")]
    assert uploads == []


def test_screen_record_inputs_carry_the_toolchain(tmp_path):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    t = _mod("t87", "tests/test_d087_v2.py")
    t._write_logs(tmp_path, {"face": 22, "body": 22, "place": 22})
    cfg = t._cfg_frozen()
    cfg["controls"]["refclips_d087"]["pre_excluded"] = []
    for c in CATS:
        cfg["controls"]["refclips_d087"]["manifests"][c] = f"data/refstim/m_{c}.json"
    patch_from, yunet = t._driver_fakes()
    ver = {"cv2": "4.x", "onnxruntime": "1.x", "ffmpeg": "ffmpeg version 6"}
    rc = drv.run_screen(cfg, tmp_path, patch_from, t.ident, yunet, lambda c, n: None, lambda p: True,
                        to_bgr=t.to_bgr, render=None, versions=ver)
    assert rc == 0
    rec = json.loads((tmp_path / cfg["controls"]["refclips_d087"]["screen_record"]).read_text())
    assert rec["inputs"]["toolchain"] == ver
    assert set(CATS) <= set(rec["inputs"])


def test_versions_records_cv2_onnxruntime_ffmpeg():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    v = drv.versions(ffmpeg=lambda: "ffmpeg version X")
    assert set(v) == {"cv2", "onnxruntime", "ffmpeg"} and v["ffmpeg"] == "ffmpeg version X"


# ---- smoke (b): the real patch / joint SHINE / rendered path on the known v1 selection ----
def _src(seed, h=400, w=500):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3)).astype(np.uint8)


def _v1_world():
    cfg = load_config()
    n = int(cfg["controls"]["refclips"]["loc_per_category"])
    mans, rows = {}, {}
    for c in CATS:
        mans[c], rows[c] = [], []
        for k in range(n):
            t = f"{c}_{k}"
            box = [10, 20, 316]
            mans[c].append({"title": t, "category": c, "crop_box": box, "sha256": f"{c}{k}",
                            "s3_key": f"v1/{t}"})
            rows[c].append({"title": t, "decision": "reject", "rule": "C1"})
            rows[c].append({"title": t + "p", "decision": "pass", "crop_box": box,
                            "source_sha256": f"{c}{k}"})
    return cfg, mans, rows


def _loaders():
    def load_v1(row):
        c, k = row["title"].split("_")
        return _src(CATS.index(c) * 100 + int(k))

    def load_cand(cand):
        c = cand["category"]
        k = int(cand["row"]["source_sha256"][len(c):])
        return _src(CATS.index(c) * 100 + k)
    return load_v1, load_cand


def test_smoke_render_equals_the_builder_path():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg, mans, rows = _v1_world()
    load_v1, load_cand = _loaders()
    res = drv.smoke_render(cfg, mans, rows, load_v1, load_cand, max_clips=1)
    assert res["equal_to_loc_images"] is True and res["equal_to_loc_frames"] is True
    n_loc = sum(c.family == "LOC" for c in R.plan(cfg))
    assert res["n_entries"] == 3 * n_loc * len(next(c for c in R.plan(cfg) if c.family == "LOC").events)
    assert res["n_entries"] == 180 and res["dtype"] == "uint8" and res["shape"] == [R.PATCH, R.PATCH]


def test_smoke_render_fails_closed_on_a_different_patch():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg, mans, rows = _v1_world()
    load_v1, load_cand = _loaders()

    def bad(cand):
        x = load_cand(cand)
        if cand["category"] == "body" and cand["row"]["source_sha256"] == "body3":
            x = x.copy()
            x[30, 30] ^= 1
        return x
    with pytest.raises(SystemExit, match="loc_images"):
        drv.smoke_render(cfg, mans, rows, load_v1, bad, max_clips=1)


def test_smoke_render_maps_v1_titles_to_v4_passes_by_source_sha():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg, mans, rows = _v1_world()
    rows["place"] = [r for r in rows["place"] if r.get("source_sha256") != "place7"]
    with pytest.raises(SystemExit, match="not a v4 pass"):
        drv.smoke_render(cfg, mans, rows, *_loaders(), max_clips=1)


# ---- smoke (c): YuNet only on non-candidate reject rows and a uniform grey patch ----
def _reject_rows():
    return {"face": [{"title": "f1", "decision": "reject", "rule": "F1", "reason": "no_face_detected",
                      "values": {"yunet_n": 0}, "sha1": "a"},
                     {"title": "f2", "decision": "reject", "rule": "F1", "reason": "multi_subject",
                      "values": {"yunet_n": 3}, "sha1": "b"},
                     {"title": "fp", "decision": "pass", "values": {"yunet_n": 1}}],
            "body": [{"title": "bp", "decision": "pass"}],
            "place": [{"title": "p1", "decision": "reject", "rule": "P2", "reason": "face_detected",
                       "values": {"yunet_n_excl": 1}, "sha1": "c"}]}


def test_smoke_yunet_reproduces_logged_counts_on_rejects_only():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg = load_config()
    seen = []
    counts = {"f1": 0, "f2": 3, "p1": 1}

    def load_reject(cat, row):
        assert row["decision"] == "reject"
        seen.append(row["title"])
        return np.full((50, 60, 3), counts[row["title"]], np.uint8)

    def yunet(bgr, thr):
        v = int(bgr[0, 0, 0])
        return [{"score": 0.9}] * v if bgr.shape[0] != bgr.shape[1] else []
    res = drv.smoke_yunet(cfg, _reject_rows(), load_reject, yunet, n_face=2)
    assert sorted(seen) == ["f1", "f2", "p1"]
    assert res["grey_patch_detections"] == 0 and all(r["match"] for r in res["rows"])


def test_smoke_yunet_mismatch_fails_closed():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg = load_config()

    def yunet(bgr, thr):
        return []
    with pytest.raises(SystemExit, match="reproduce"):
        drv.smoke_yunet(cfg, _reject_rows(), lambda c, r: np.zeros((50, 60, 3), np.uint8), yunet, n_face=2)


def test_smoke_yunet_uses_the_tlic_thresholds():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg = copy.deepcopy(load_config())
    fd = cfg["controls"]["refclips_auto"]["face_detector"]
    thr = []

    def yunet(bgr, t):
        thr.append(t)
        return [{"score": 0.9}] * int(bgr[0, 0, 0]) if bgr.shape[0] != bgr.shape[1] else []
    counts = {"f1": 0, "f2": 3, "p1": 1}
    drv.smoke_yunet(cfg, _reject_rows(), lambda c, r: np.full((50, 60, 3), counts[r["title"]], np.uint8),
                    yunet, n_face=2)
    assert thr[:3] == [fd["score_threshold"], fd["score_threshold"], fd["exclusion_score_threshold"]]


def test_smoke_never_needs_d087_frozen():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg = load_config()
    assert not any(f["key"].startswith("controls.refclips_d087") for f in cfg["frozen"])
    assert callable(drv.smoke_render) and callable(drv.smoke_yunet) and callable(drv.smoke_sources)


def test_smoke_sources_checks_every_logged_pass():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    rows = {c: [{"title": f"{c}{k}", "decision": "pass", "url": "u.jpg", "source_sha256": f"s{k}",
                 "crop_box": [0, 0, 8]} for k in range(3)] + [{"title": "r", "decision": "reject"}]
            for c in CATS}
    got = []
    res = drv.smoke_sources(rows, lambda row: got.append(row["title"]) or np.zeros((2, 2, 3), np.uint8))
    assert res == {c: {"passes": 3, "loaded": 3} for c in CATS} and len(got) == 9


def test_locimg_patch_is_used_by_smoke_render(monkeypatch):
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    cfg, mans, rows = _v1_world()
    called = []
    real = locimg.patch
    monkeypatch.setattr(locimg, "patch", lambda *a, **k: called.append(1) or real(*a, **k))
    drv.smoke_render(cfg, mans, rows, *_loaders(), max_clips=1)
    assert len(called) >= 60


def test_v2_row_file_name_drops_the_url_query_string():
    drv = _mod("locscreen_v2", "scripts/locscreen_v2.py")
    url = ("https://upload.wikimedia.org/wikipedia/commons/9/99/A_%28B%29.tif?utm_source=commons.wikimedia.org"
           "&utm_campaign=imageinfo&utm_content=original")
    r = drv.v2_row("face", 3, {"title": "t", "rank": 7, "row": {"url": url}})
    assert r["file"] == "face_v2_03_r0007.tif"
    assert r["s3_key"] == "sources/images/face/v2/face_v2_03_r0007.tif"
    assert r["download_url"] == url


def test_screen_loader_never_uploads_slot0_orphan_keys():
    src = (ROOT / "scripts" / "locscreen_v2.py").read_text()
    calls = [ln for ln in src.splitlines() if "bld.fetch_sources(" in ln]
    assert len(calls) == 3 and all("upload=False" in ln for ln in calls)
