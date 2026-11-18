"""D-063 (Gate P4-entry) label-blind rulings fixed in config BEFORE any real-data P4 output (FIX-P4E):
L = 0, W = [5, 45), the frozen T1/T3 run sets, the `low_fps_source` flag, the WER action threshold and the
MT ∪ MST ∪ FST motion-control ROI. Reads only label-free columns (video_id, in_primary, qc_pass of the
manifest; the P2 QC table) — never labels, titles or URLs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from yct.config import load_config

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
P4 = CFG["p4"]


def _analysis_set() -> list[str]:
    m = pd.read_csv(ROOT / "data/manifest.csv", usecols=["video_id", "in_primary", "qc_pass"], dtype=str,
                    keep_default_na=False)
    return sorted(m[(m.in_primary == "True") & (m.qc_pass == "True")].video_id)


def _qc() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data/wave1_normalize_qc.csv",
                       usecols=["video_id", "status", "src_fps", "trimmed_duration_s"]).set_index("video_id")


def test_latency_and_window_fixed_d063_b1():
    w = CFG["window"]
    assert w["latency_l_tr"] == 0
    assert (w["start_tr"], w["end_tr"]) == (5, 45)
    assert w["start_tr"] == max(5, 4 + w["latency_l_tr"] + 1)            # v2.md W formula
    assert w["end_tr"] - w["start_tr"] == w["default_len_tr"] == 40
    assert w["min_tail_s"] == 5


def test_run_sets_are_analysis_set_minus_0644_and_t1_minus_0483():
    a = _analysis_set()
    assert len(a) == 53 and "yct_0644" in a
    assert P4["analysis_excluded"] == {"yct_0644": "source_unavailable"}
    assert P4["run_set_t3"] == sorted(set(a) - {"yct_0644"}) and len(P4["run_set_t3"]) == 52
    assert P4["run_set_t1"] == sorted(set(P4["run_set_t3"]) - {"yct_0483"}) and len(P4["run_set_t1"]) == 51
    assert set(P4["t1_excluded"]) == {"yct_0483"}
    assert "yct_0641" not in P4["run_set_t3"]                         # D-063 Q3: not in the analysis set


def test_t1_exclusion_follows_the_label_free_tail_rule():
    q, w, tr = _qc(), CFG["window"], CFG["tribe"]["tr_s"]
    need = w["end_tr"] * tr + w["min_tail_s"]
    short = sorted(v for v in P4["run_set_t3"] if q.loc[v, "trimmed_duration_s"] < need)
    assert short == sorted(P4["t1_excluded"]) == ["yct_0483"]
    assert all(q.loc[v, "status"] == "pass" for v in P4["run_set_t3"])


def test_low_fps_source_flag_d063_q3():
    q, f = _qc(), P4["flags"]["low_fps_source"]
    lo = sorted(v for v in P4["run_set_t3"] if q.loc[v, "src_fps"] < CFG["stimulus"]["min_source_fps"])
    assert f["videos"] == lo == ["yct_0626"]
    assert f["sensitivity"] == "S-LOWFPS" and CFG["stimulus"]["min_source_fps"] == 16


def test_wer_action_threshold_d063_q5():
    wer = CFG["transcribe"]["wer"]
    assert wer["action_threshold"] == 0.25 and wer["n_hand_checked"] == 5
    assert wer["rule"] == "any_video"     # strictest reading: any of the 5 above 0.25 -> re-transcribe


def test_motion_control_is_mt_mst_fst_and_v1v3_descriptive_d063_q4():
    c = CFG["controls"]
    assert c["rois"]["MT_plus"]["areas"] == ["MT", "MST", "FST"] and c["rois"]["MT_plus"]["n_vertices"] == 139
    assert c["regressors"]["motion"]["roi"] == "MT_plus" and c["regressors"]["motion"]["gating"] is True
    assert not [n for n, r in c["regressors"].items() if r["gating"] and r["roi"] == "V1_V3"]
    assert {(d["regressor"], d["roi"]) for d in c["descriptive"]} == {("motion", "V1_V3"),
                                                                      ("luminance_change", "V1_V3")}


def test_p4_compute_settings():
    assert P4["gpu_type"] == "gpu_1x_a100_sxm4" and P4["gpu_name"] == "NVIDIA A100-SXM4-40GB"
    assert P4["s3_prefix"] == "s3://yct-research-235229001983/wave1/derived/p4"
    assert P4["session_max_hours"] <= CFG["budget"]["max_hours_per_instance"] <= 4
    assert P4["terminator_margin_s"] == 900
    assert P4["d038_clips"] == ["yct_0016", "yct_0034", "yct_0036"]
    assert set(P4["d038_clips"]) <= set(P4["run_set_t1"])
    from yct.tribe_run.qc import GPU_NAME
    assert GPU_NAME == P4["gpu_name"]
