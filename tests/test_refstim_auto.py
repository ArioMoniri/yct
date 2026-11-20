"""D-075: frozen automatic image + NAT filters (src/yct/curate/refstim_auto.py). Fakes only: no candidate
image, no model weights, no network."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from yct.config import load_config
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
A = CFG["controls"]["refclips_auto"]
MODEL = np.asarray(A["headpose"]["model_points_mm"], float)


class Fake:
    """Configurable fake detectors."""

    def __init__(self, **kw):
        self.faces = kw.get("faces", [{"box": [200, 100, 240, 300], "score": 0.97, "lm": None}])
        self.excl_faces = kw.get("excl_faces", [])
        self.person_list = kw.get("persons", [])
        self.photo = kw.get("photo", [0.9, 0.02, 0.02, 0.02, 0.02, 0.02])
        self.adult = kw.get("adult", [0.1, 0.9])
        self.ocr = kw.get("ocr", [])
        self.haar_full = kw.get("haar_full", np.array([[300, 200, 200, 200]]))
        self.haar_proc = kw.get("haar_proc", np.array([[60, 60, 128, 128]]))
        self.eyes = kw.get("eyes", np.array([[40, 60, 30, 30], [150, 60, 30, 30]]))
        self.yaw = kw.get("yaw", 0.0)
        self.pitch = kw.get("pitch", 0.0)
        self.calls = []

    def yunet(self, bgr640, thr):
        self.calls.append("yunet")
        if thr == A["face_detector"]["exclusion_score_threshold"]:
            return self.excl_faces
        out = []
        for f in self.faces:
            g = dict(f)
            if g["lm"] is None:
                lm = ra.project(MODEL, self.yaw, self.pitch, (bgr640.shape[1], bgr640.shape[0]), dist_mm=400)
                g["lm"] = lm.flatten().tolist()
            out.append(g)
        return out

    def persons(self, rgb):
        self.calls.append("persons")
        return self.person_list

    def clip_probs(self, rgb, prompts):
        self.calls.append("clip")
        return self.photo if len(prompts) == 6 else self.adult

    def ocr_boxes(self, rgb):
        return self.ocr

    def haar_faces(self, grey):
        return self.haar_proc if grey.shape == (256, 256) else self.haar_full

    def haar_eyes(self, grey):
        return self.eyes


def cand(**kw):
    e = {"mediatype": "BITMAP", "mime": "image/jpeg", "width": 1280, "height": 960,
         "sha1": kw.get("sha1", "a" * 40)}
    e.update(kw.get("entry", {}))
    img = kw.get("img", np.full((960, 1280, 3), 128, np.uint8))
    return ra.Candidate(kw.get("title", "File:x.jpg"), "k" * 64, e, kw.get("meta", {}), kw.get("lic", "CC0"),
                        kw.get("tpl", "Template:Cc-zero"), kw.get("adm", True), lambda: img)


def ev(cat, c, det, st=None, keys=None):
    return ra.evaluate_image(cat, c, det, CFG, st or ra.State(), keys or set(), 1)


def textured(seed=0):
    return np.random.default_rng(seed).integers(0, 255, (960, 1280, 3), dtype=np.uint8)


# ---------------------------------------------------------------- rule order and reasons
def test_every_rule_maps_to_exactly_one_reason_table_entry_in_reject_reasons():
    reasons = set(CFG["controls"]["refclips"]["reject_reasons"])
    rules = {r for rs_ in ra.IMAGE_RULES.values() for r in rs_} | set(ra.NAT_RULES)
    assert set(A["rule_reasons"]) == rules
    for rule, rr in A["rule_reasons"].items():
        for r in rr if isinstance(rr, list) else [rr]:
            assert r in reasons, rule


def test_face_pass_with_frontal_fake():
    r = ev("face", cand(img=textured()), Fake())
    assert r["decision"] == "pass", r
    assert abs(r["values"]["yaw"]) < 1 and abs(r["values"]["pitch"]) < 1


@pytest.mark.parametrize("kw,c_kw,rule,reason", [
    ({}, {"entry": {"mediatype": "DRAWING"}}, "C0", "not_photo"),
    ({}, {"tpl": "Template:Personality rights", "adm": False}, "C1", "personality_rights"),
    ({}, {"adm": False}, "C1", "licence"),
    ({}, {"entry": {"width": 315}}, "C2", "too_small"),
    ({}, {"meta": {"description": "Pitch at YC W21 demo"}}, "C4", "text_or_logo"),
    ({"photo": [0.1, 0.8, 0.02, 0.04, 0.02, 0.02]}, {}, "C5", "not_photo"),
    ({"faces": []}, {}, "F1", "no_face_detected"),
    ({"faces": [{"box": [0, 0, 50, 50], "score": .95, "lm": None}] * 2}, {}, "F1", "multi_subject"),
    ({"persons": [{"box": [0, 0, 10, 10], "score": .9}] * 2}, {}, "F2", "multi_subject"),
    ({"haar_proc": np.zeros((0, 4))}, {}, "F6", "no_face_detected"),
    ({"haar_proc": np.array([[90, 90, 100, 100]])}, {}, "F3", "too_small"),
    ({"yaw": 25.0}, {}, "F4", "face_not_frontal"),
    ({"pitch": -24.0}, {}, "F4", "face_not_frontal"),
    ({"eyes": np.array([[40, 60, 30, 30]])}, {}, "F5b", "face_not_frontal"),
    ({"adult": [0.7, 0.3]}, {}, "F7", "personality_rights"),
    ({"ocr": [{"box": [0, 0, 200, 100], "conf": 90.0, "text": "SALE"}]}, {}, "F8", "text_or_logo"),
])
def test_face_first_failing_rule_is_logged(kw, c_kw, rule, reason):
    r = ev("face", cand(img=textured(), **c_kw), Fake(**kw))
    assert (r["decision"], r["rule"], r["reason"]) == ("reject", rule, reason), r


def test_f3_haar_crop_centre_outside_yunet_box_is_multi_subject():
    f = Fake(faces=[{"box": [10, 10, 60, 60], "score": .95, "lm": None}])
    r = ev("face", cand(img=textured()), f)
    assert (r["rule"], r["reason"]) in {("F3", "multi_subject")}, r


def test_ocr_ignores_low_conf_and_empty_text():
    f = Fake(ocr=[{"box": [0, 0, 400, 400], "conf": 59.0, "text": "X"},
                  {"box": [0, 0, 400, 400], "conf": 95.0, "text": "  "}])
    assert ev("face", cand(img=textured()), f)["decision"] == "pass"


def test_body_rules():
    one = [{"box": [100, 100, 600, 700], "score": .95}]
    no_haar = np.zeros((0, 4))
    assert ev("body", cand(img=textured()), Fake(persons=one, haar_proc=no_haar))["decision"] == "pass"
    cases = [(dict(persons=[]), "B1", "not_photo"), (dict(persons=one * 2), "B1", "multi_subject"),
             (dict(persons=[{"box": [0, 0, 100, 100], "score": .9}]), "B2", "too_small"),
             (dict(persons=one, excl_faces=[{"box": [0, 0, 9, 9], "score": .6, "lm": [0] * 10}]), "B3",
              "face_detected"),
             (dict(persons=one), "B3", "face_detected"),        # Haar positive on the processed crop
             (dict(persons=one, haar_proc=np.zeros((0, 4)), adult=[.6, .4]), "B4", "personality_rights")]
    for kw, rule, reason in cases:
        r = ev("body", cand(img=textured()), Fake(**kw))
        assert (r["rule"], r["reason"]) == (rule, reason), (kw, r)


def test_person_below_threshold_ignored_and_place_rules():
    weak = [{"box": [0, 0, 500, 500], "score": 0.49}]
    no_haar = np.zeros((0, 4))
    assert ev("place", cand(img=textured()), Fake(persons=weak, haar_proc=no_haar))["decision"] == "pass"
    r = ev("place", cand(img=textured()), Fake(persons=[{"box": [0, 0, 5, 5], "score": 0.5}]))
    assert (r["rule"], r["reason"]) == ("P1", "person_present")
    r = ev("place", cand(img=textured()), Fake())
    assert (r["rule"], r["reason"]) == ("P2", "face_detected")


def test_duplicates_sha1_and_dhash_across_categories():
    st = ra.State()
    img = textured(1)
    assert ev("face", cand(img=img, sha1="b" * 40), Fake(), st)["decision"] == "pass"
    r = ev("face", cand(img=img, sha1="b" * 40), Fake(), st)
    assert (r["rule"], r["reason"]) == ("C3", "duplicate")
    r = ev("place", cand(img=img.copy(), sha1="c" * 40), Fake(), st)      # same pixels, other sha1
    assert (r["rule"], r["reason"]) == ("C3", "duplicate")


# ---------------------------------------------------------------- fail-closed
def test_decode_error_and_nan_are_stops_not_rejects():
    def bad():
        raise ra.StopError("decode failed")
    c = cand()
    c.load_rgb = bad
    with pytest.raises(ra.StopError):
        ev("face", c, Fake())
    with pytest.raises(ra.StopError):
        ev("face", cand(img=textured()), Fake(photo=[float("nan")] * 6))


def test_first_detector_call_refused_unless_frozen_and_artifacts_set():
    with pytest.raises(ra.StopError):
        ra.check_frozen({**CFG, "frozen": []})
    rows = [{"key": "controls.refclips_auto"}] + [{"key": f"controls.refclips_auto_artifacts.{k}"}
                                                  for k in A["image_artifacts"]]
    cfg = {**CFG, "frozen": rows,
           "controls": {**CFG["controls"],
                        "refclips_auto_artifacts": dict.fromkeys(CFG["controls"]["refclips_auto_artifacts"])}}
    with pytest.raises(ra.StopError, match="not set"):
        ra.check_frozen(cfg)


def test_artifact_and_env_mismatch_refuse(tmp_path):
    f = tmp_path / "m.bin"
    f.write_bytes(b"abc")
    with pytest.raises(ra.StopError):
        ra.check_artifact(f, "0" * 64)
    good = dict(A["env"]["packages"])
    ra.check_env(CFG, good)
    with pytest.raises(ra.StopError):
        ra.check_env(CFG, {**good, "torch": "2.9.0+cpu"})


# ---------------------------------------------------------------- head pose (SQPNP, non-circular checks)
def test_sqpnp_on_frozen_points_does_not_raise_and_frontal_is_zero():
    y, p, r = ra.head_pose(ra.project(MODEL, 0, 0, (640, 480)), (640, 480), MODEL)
    assert max(abs(y), abs(p), abs(r)) < 0.5


@pytest.mark.parametrize("yaw,pitch,ok", [(19, 0, True), (-19, 0, True), (21, 0, False), (-21, 0, False),
                                          (0, 19, True), (0, -19, True), (0, 21, False), (0, -21, False)])
def test_pose_boundary_decisions(yaw, pitch, ok):
    y, p, _ = ra.head_pose(ra.project(MODEL, yaw, pitch, (640, 480)), (640, 480), MODEL)
    assert (abs(y) <= 20 and abs(p) <= 20) == ok


def test_pose_decision_stable_when_true_face_differs_from_model_by_3mm():
    """Landmarks are generated from a perturbed face (every point moved 3 mm in a random direction) and
    estimated with the frozen model: the decision at +-5 deg and +-35 deg never flips. Disclosed (D-075):
    at 5 mm the error reaches ~18 deg, so decisions near +-20 deg are approximate."""
    rng = np.random.default_rng(20261120)
    for _ in range(300):
        d = rng.normal(size=MODEL.shape)
        d = d / np.linalg.norm(d, axis=1, keepdims=True) * 3.0
        for yaw, pitch in [(5, 0), (-5, 0), (0, 5), (0, -5), (35, 0), (-35, 0), (0, 35), (0, -35)]:
            y, p, _ = ra.head_pose(ra.project(MODEL + d, yaw, pitch, (640, 480)), (640, 480), MODEL)
            assert (abs(y) <= 20 and abs(p) <= 20) == (abs(yaw) <= 20 and abs(pitch) <= 20)


# ---------------------------------------------------------------- C4 metadata
def test_c4_regex_terms_and_hashed_multiword_keys(tmp_path):
    m = tmp_path / "manifest.csv"
    m.write_text("video_id,company_key,company_id\nyct_0001,acme robotics,acme\n")
    keys, longest = ra.manifest_key_hashes(m)
    assert all(len(k) == 64 for k in keys) and longest == 2
    terms, rx = A["common"]["metadata_terms"], A["common"]["metadata_regex"]
    assert ra.metadata_hit("YC W21 batch photo", terms, rx, set(), 1)
    assert ra.metadata_hit("YCS22 kit", terms, rx, set(), 1)
    assert ra.metadata_hit("bicycles22", terms, rx, set(), 1) is False
    assert ra.metadata_hit("at Y Combinator", terms, rx, set(), 1)
    assert ra.metadata_hit("Portrait by Acme Robotics staff", terms, rx, keys, longest)
    assert not ra.metadata_hit("Portrait of a woman", terms, rx, keys, longest)


def test_module_never_opens_wave2_pool():
    src = (ROOT / "src" / "yct" / "curate" / "refstim_auto.py").read_text()
    run = (ROOT / "scripts" / "refstim_auto_run.py").read_text()
    for s in (src, run):
        code = "\n".join(n.value for n in ast.walk(ast.parse(s))
                         if isinstance(n, ast.Constant) and isinstance(n.value, str))
        assert "wave2_pool/" not in code.replace("never opens data/wave2_pool/", "")


# ---------------------------------------------------------------- crop identical to refstim_inspect
def test_crop_info_matches_existing_crop_box_and_processed(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ri", ROOT / "scripts" / "refstim_inspect.py")
    ri = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ri)
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 255, (2000, 2400, 3), dtype=np.uint8)
    f = Fake(haar_full=np.array([[500, 300, 220, 220]]))
    monkeypatch.setattr(ri, "faces", lambda g, cfg: np.array([[500, 300, 220, 220]]))
    g = ri.grey709(rgb)
    scale = 1600 / max(g.shape)
    import cv2
    gs = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    for cat in ("face", "place"):
        want = tuple(int(round(v / scale)) for v in ri.crop_box(gs, cat, CFG))
        got = ra.crop_info(rgb, cat, f)
        assert got["box"] == want
        assert np.array_equal(got["proc"], ri.processed(rgb, want))


# ---------------------------------------------------------------- NAT rules
def test_nat_n1_n2_boundaries():
    seg = [(0.0, 50.0, "A")]
    assert ra.nat_decide({"en": 0.9}, seg, CFG)["decision"] == "pass"
    assert ra.nat_decide({"en": 0.8999}, seg, CFG)["reason"] == "not_english"
    assert ra.nat_decide({"en": 0.99}, [], CFG)["reason"] == "not_single_speaker"
    assert ra.nat_decide({"en": 0.99}, [(0, 40, "A"), (40, 42.0, "B")], CFG)["decision"] == "pass"   # 95.2%
    assert ra.nat_decide({"en": 0.99}, [(0, 40, "A"), (40, 43.0, "B")], CFG)["reason"] == "not_single_speaker"
    assert ra.nat_decide({"en": 0.99}, [(0, 80, "A"), (80, 83.0, "B")], CFG)["decision"] == "pass"   # 3.0 s
    assert ra.nat_decide({"en": 0.99}, [(0, 80, "A"), (80, 83.1, "B")], CFG)["reason"] == "not_single_speaker"
    assert ra.nat_decide({"en": 0.99}, [(0, 10, "A"), (10, 11, "B"), (11, 12, "C")], CFG)["reason"] == \
        "not_single_speaker"
    with pytest.raises(ra.StopError):
        ra.nat_decide({"en": float("nan")}, seg, CFG)


def test_nat_select_first_15_in_order_and_stop_below_15():
    ids = [f"n{i:02d}" for i in range(40)]
    ok = lambda i: {"decision": "pass" if int(i[1:]) % 2 == 0 else "reject"}   # noqa: E731
    sel, log = ra.nat_select(ids, ok, CFG)
    assert sel == [f"n{i:02d}" for i in range(0, 30, 2)] and len(log) == 29
    with pytest.raises(ra.StopError):
        ra.nat_select(ids, lambda i: {"decision": "pass" if int(i[1:]) < 14 else "reject"}, CFG)
    with pytest.raises(ra.StopError):
        ra.nat_select(ids + ["extra"], ok, CFG)


# ---------------------------------------------------------------- determinism + append-only log
def test_two_processes_give_identical_rows(tmp_path):
    code = ("import json,numpy as np,sys;sys.path.insert(0,'tests');import test_refstim_auto as t;"
            "print(json.dumps(t.ev('face', t.cand(img=t.textured(5)), t.Fake()), sort_keys=True))")
    outs = [subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}).stdout
            for _ in range(2)]
    assert outs[0] and outs[0] == outs[1]


def test_logs_are_append_only_guarded_and_jsonl(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("cao", ROOT / "scripts" / "check_append_only.py")
    cao = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(cao)
    for cat in CFG["controls"]["refclips"]["loc_categories"]:
        assert A["logs"]["image"].replace("<cat>", cat) in cao.APPEND_ONLY
    assert A["logs"]["nat"] in cao.APPEND_ONLY
    p = tmp_path / "l.jsonl"
    ra.append_jsonl(p, {"a": 1})
    ra.append_jsonl(p, {"b": 2})
    assert [json.loads(x) for x in p.read_text().splitlines()] == [{"a": 1}, {"b": 2}]
