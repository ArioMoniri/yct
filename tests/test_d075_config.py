"""D-075: frozen automatic image + NAT filter rules (config + schema + freeze + DECISIONS entry)."""

import copy
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from yct.config import load_config
from yct.config_schema import validate_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
A = CFG["controls"]["refclips_auto"]
ART = CFG["controls"]["refclips_auto_artifacts"]


def _bad(mut):
    c = copy.deepcopy(CFG)
    mut(c["controls"])
    with pytest.raises(ValidationError):
        validate_config(c)


def test_d075_key_values_are_the_entry():
    assert A["decision"] == "D-075"
    fd = A["face_detector"]
    assert (fd["score_threshold"], fd["nms_threshold"], fd["top_k"]) == (0.9, 0.3, 5000)
    assert fd["input_long_side"] == 640
    assert fd["exclusion_score_threshold"] == 0.5
    assert fd["revision"] == "f12e12798e8314f7c074a6656816c048dcc95b7a"
    assert A["eye_detector"]["min_count"] == 2 and A["eye_detector"]["min_neighbors"] == 5
    assert A["person_detector"]["score_threshold"] == 0.5 and A["person_detector"]["person_class"] == 1
    assert A["person_detector"]["url"].endswith("fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth")
    assert A["ocr"] == {"impl": "tesseract", "psm": 11, "oem": 1, "min_conf": 60, "max_text_area_frac": 0.01,
                        "image_long_side": 1600}
    assert A["clip"]["revision"] == "1a25a446712ba5ee05982a381eed697ef9b435cf"
    assert A["clip"]["decision"] == "argmax"
    hp = A["headpose"]
    assert hp["solver"] == "SQPNP" and (hp["max_abs_yaw_deg"], hp["max_abs_pitch_deg"]) == (20, 20)
    assert hp["model_points_mm"] == [[-31.5, 0.0, 0.0], [31.5, 0.0, 0.0], [0.0, 35.0, -30.0],
                                     [-25.0, 70.0, -5.0], [25.0, 70.0, -5.0]]
    assert A["face_rules"] == {"min_face_height_frac_crop": 0.40, "min_interocular_frac_box": 0.25}
    assert A["body_rules"] == {"min_person_area_frac": 0.15}
    assert A["common"]["min_short_side_px"] == 316 and A["common"]["dhash_max_hamming"] == 4
    assert A["common"]["metadata_columns"] == ["company_key", "company_id"]
    assert "wave2_pool" not in str(A)
    n = A["nat"]
    assert n["stage"] == "session_0" and n["counts_toward_cap"] is True and n["cpu_buffer"] == 40
    assert n["lang_id"]["samples_s"] == [0, 30] and n["lang_id"]["min_prob_en"] == 0.9
    assert n["diarization"]["pyannote_audio"] == "4.1.0"
    assert (n["diarization"]["min_main_speaker_frac"], n["diarization"]["max_other_speaker_s"]) == (0.95, 3.0)
    validate_config(CFG)


def test_env_pins_match_the_lock_file():
    lock = (ROOT / A["env"]["lock"]).read_text()
    for pkg, ver in A["env"]["packages"].items():
        assert f"{pkg}=={ver}" in lock, pkg


@pytest.mark.parametrize("mut", [
    lambda c: c["refclips_auto"].update(extra=1),
    lambda c: c["refclips_auto"]["face_detector"].update(score_threshold=0.8),
    lambda c: c["refclips_auto"]["headpose"].update(solver="ITERATIVE"),
    lambda c: c["refclips_auto"]["headpose"].update(model_points_mm=[[0.0, 0.0, 0.0]]),
    lambda c: c["refclips_auto"]["ocr"].update(max_text_area_frac=0.05),
    lambda c: c["refclips_auto"]["clip"].update(decision="threshold"),
    lambda c: c["refclips_auto"]["nat"].update(stage="session_1"),
    lambda c: c["refclips_auto"]["rule_reasons"].update(C0="invented_reason"),
    lambda c: c["refclips_auto"].update(image_artifacts=["nope_sha256"]),
    lambda c: c["refclips_auto_artifacts"].update(yunet_sha256="xyz"),
])
def test_d075_schema_rejects(mut):
    _bad(mut)


def test_reject_reasons_unchanged():
    assert CFG["controls"]["refclips"]["reject_reasons"] == [
        "licence", "personality_rights", "not_photo", "multi_subject", "face_not_frontal", "face_detected",
        "no_face_detected", "text_or_logo", "person_present", "too_small", "duplicate", "not_english",
        "too_short", "not_single_speaker", "low_face_present", "yc_link"]


def test_d075_entry_in_decisions():
    text = (ROOT / "DECISIONS.md").read_text()
    entries = re.findall(r"^- D-075\b.*$", text, flags=re.M)
    assert len(entries) == 1 and "owner" in entries[0]
    assert not re.findall(r"^- D-073\b", text, flags=re.M)      # D-073 still reserved (ablation)


def test_artifacts_frozen_only_once_set():
    rows = {r["key"]: r["frozen_at"] for r in yaml.safe_load((ROOT / "config.yaml").read_text())["frozen"]}
    for k, v in ART.items():
        key = f"controls.refclips_auto_artifacts.{k}"
        if v is None:
            assert key not in rows, key
        if key in rows:
            assert v is not None and re.fullmatch(r"[0-9a-f]{40}", rows[key])
    if "controls.refclips_auto" in rows:
        assert re.fullmatch(r"[0-9a-f]{40}", rows["controls.refclips_auto"])
