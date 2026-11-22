"""D-085 draft: the amended p4b_ref/v1 stimulus QC (yct.tribe_run.refclips_qc85), pure parts only.

Owner decision 2026-11-22 ("Fix the rule"): LOC/LOC_SCR "no face" gated by the frozen T-LIC YuNet
(score >= 0.5) on the decoded post-SHINE patch; Haar face_area_crop_frac reported, not gated; face_hit_frac
read at family level; twin pixel identity outside event windows. Council-only completions of design_v2 §1.5:
luminance/contrast constancy, MOT static level, FLASH luminance_change at events only, "no other regressor
moves" (audio/video identity with the matched control)."""
from __future__ import annotations

import copy

import numpy as np
import pytest

from yct.config import load_config
from yct.tribe_run import refclips58 as R  # noqa: N812
from yct.tribe_run import refclips_qc85 as Q  # noqa: N812

CFG = load_config()
QC = CFG["controls"]["refclips_d085"]["qc"]
CLIPS = {c.name: c for c in R.plan(CFG)}


def test_refuses_unless_d085_is_frozen():
    unfrozen = copy.deepcopy(CFG)   # the repo config is frozen since D-085 part 1: test the unfrozen state
    unfrozen["frozen"] = [f for f in unfrozen["frozen"] if not f["key"].startswith("controls.refclips_d085")]
    with pytest.raises(SystemExit, match="not frozen"):
        Q.require_frozen(unfrozen)
    cfg = copy.deepcopy(unfrozen)
    cfg["frozen"] = list(cfg["frozen"]) + [{"key": "controls.refclips_d085", "frozen_at": "x"}]
    Q.require_frozen(cfg)


def test_face_hit_is_pooled_over_the_family():
    rows = [{"family": "LOC", "face_event_hits": [True]} for _ in range(19)] + \
           [{"family": "LOC", "face_event_hits": [False]}]
    r = Q.face_hit_family(rows, QC["face_hit_min"])
    assert r["n_events"] == 20 and r["frac"] == pytest.approx(0.95) and r["pass"]
    rows[0]["face_event_hits"] = [False]
    assert Q.face_hit_family(rows, QC["face_hit_min"])["pass"]          # 18/20 = 0.90: the bound passes
    rows[1]["face_event_hits"] = [False]
    assert not Q.face_hit_family(rows, QC["face_hit_min"])["pass"]      # 17/20 = 0.85


def test_yunet_gated_trs_skip_face_events_in_loc_and_cover_all_of_loc_scr():
    loc, scr = CLIPS["loc_00"], CLIPS["loc_scr_00"]
    face = [int(e["onset"]) for e in loc.events if e["category"] == "face"]
    g = Q.yunet_trs(loc, 58)
    assert set(face).isdisjoint(g) and len(g) == 58 - len(face)
    assert Q.yunet_trs(scr, 58) == list(range(58))


class FakeYunet:
    def __init__(self, hit_at=()):
        self.calls, self.hit_at = [], set(hit_at)

    def __call__(self, bgr640, thr):
        assert bgr640.shape == (640, 640, 3) and thr == QC["yunet_score_threshold"]
        n = len(self.calls)
        self.calls.append(n)
        return [{"score": 0.7, "box": [0, 0, 10, 10]}] if n in self.hit_at else []


def _patches(n_tr, per_tr):
    return [(t / per_tr, np.full((316, 316), 128, np.uint8)) for t in range(n_tr * per_tr)]


def test_yunet_gate_passes_clean_and_fails_on_any_detection():
    clip = CLIPS["loc_scr_00"]
    pt = _patches(58, 2)
    ok = Q.yunet_gate(clip, pt, 1.0, FakeYunet(), QC["yunet_score_threshold"])
    assert ok["pass"] and ok["n_frames"] == 116 and ok["hits"] == []
    bad = Q.yunet_gate(clip, pt, 1.0, FakeYunet(hit_at=[7]), QC["yunet_score_threshold"])
    assert not bad["pass"] and bad["hits"][0]["tr"] == 3


def test_twin_identity_ignores_event_windows_and_flags_any_other_difference():
    loc = CLIPS["loc_00"]
    n = int(R.DUR * R.FPS)
    a = [np.zeros((4, 4), np.uint8) for _ in range(n)]
    b = [x.copy() for x in a]
    o = loc.onsets[0]
    b[int((o + 1) * R.FPS)][0, 0] = 9                   # inside [o-4, o+8): allowed
    assert Q.twin_identity(a, b, loc, CFG)["pass"]
    b[int((o + 9) * R.FPS)][0, 0] = 9                   # outside every window: fail
    r = Q.twin_identity(a, b, loc, CFG)
    assert not r["pass"] and r["n_diff_frames"] == 1


def test_constancy_within_one_percent_of_the_clip_mean():
    x = np.full(58, 0.5)
    assert Q.constancy(x, QC["constancy_tol"])["pass"]
    x[10] = 0.5 * 1.02
    assert not Q.constancy(x, QC["constancy_tol"])["pass"]
    x = np.full(58, 0.5)
    x[0] = np.nan
    assert Q.constancy(x, QC["constancy_tol"])["pass"]


def test_mot_event_ratio_static_level_and_static_twin_has_no_event():
    ev = [9, 29, 49]
    mot, stat = np.full(58, 1e-4), np.full(58, 1e-4)
    mot[ev] = 0.05
    r = Q.mot_checks(mot, stat, ev, QC["mot_ratio"])
    assert r["pass"] and r["ratio"] >= 10
    m2 = mot.copy()
    m2[20] = 0.02                                        # motion outside the events
    assert not Q.mot_checks(m2, stat, ev, QC["mot_ratio"])["pass"]
    s2 = stat.copy()
    s2[29] = 0.01                                        # the static twin moves
    assert not Q.mot_checks(mot, s2, ev, QC["mot_ratio"])["pass"]


def test_flash_luminance_change_only_at_onsets_and_offsets():
    lum = np.full(58, 0.5)
    for o in (9, 29, 49):
        lum[o] = 1.0
    r = Q.flash_check(lum, [9, 29, 49], QC["flash_quiet_frac"])
    assert r["pass"]
    lum[40] = 0.52
    assert not Q.flash_check(lum, [9, 29, 49], QC["flash_quiet_frac"])["pass"]


def test_no_other_regressor_audio_identity_for_visual_and_video_identity_for_audio():
    ctrl = {"sha256": {"wav": "a" * 64, "mp4": "m" * 64}}
    assert Q.audio_identity({"sha256": {"wav": "a" * 64}}, ctrl)["pass"]
    assert not Q.audio_identity({"sha256": {"wav": "b" * 64}}, ctrl)["pass"]
    vf = {"luminance_crop": np.ones(58), "face_area_crop_frac": np.zeros(58)}
    assert Q.video_identity(vf, copy.deepcopy(vf))["pass"]
    vf2 = copy.deepcopy(vf)
    vf2["luminance_crop"][3] = 1.001
    assert not Q.video_identity(vf, vf2)["pass"]


def test_haar_is_descriptive_only_in_loc_rows():
    fa = np.zeros(58)
    fa[[3, 4]] = 0.03
    d = Q.haar_descriptive(CLIPS["loc_scr_00"], fa)
    assert d["n_hit_trs"] == 2 and d["gating"] is False


def test_t_lic_yunet_refuses_an_onnx_that_is_not_the_frozen_file(tmp_path):
    p = tmp_path / "face_detection_yunet_2023mar.onnx"
    p.write_bytes(b"not the model")
    with pytest.raises(SystemExit, match="sha256"):
        Q.t_lic_yunet(CFG, p)


def test_rendered_intact_event_frame_equals_the_locimg_patch():
    """SHINE ratification (council): the intact patch shown at a LOC event is exactly the normalised
    locimg patch, so any ghosting on the contact sheet is not introduced by loc_frames."""
    rng = np.random.default_rng(0)
    imgs = {c: [np.clip(rng.normal(128, 32, (316, 316)), 0, 255).astype(np.uint8) for _ in range(20)]
            for c in ("face", "body", "place")}
    clip = CLIPS["loc_03"]
    frames = R.loc_frames(clip, imgs)
    for e in clip.events:
        n = int(round((e["onset"] + 0.5) * R.FPS))
        want = R._u8(R._frame(R._norm(imgs[e["category"]][e["image"]].astype(np.float64))))
        assert np.array_equal(frames[n], want)
