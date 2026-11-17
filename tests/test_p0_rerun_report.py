"""scripts/p0_rerun_report.py: GPU re-run summary (exact cached rerun, D-038 reliability, clip shapes)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("rep", ROOT / "scripts" / "p0_rerun_report.py")
rep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rep)


def _run(sha, reused, drift=None, **kw):
    r = {"pred_sha256": sha, "cache_reused": reused, "feature_sha256": {"f": "1"}, "shape": [10, 20484],
         "duration_s": 10.0, "T_within_1": True, **kw}
    if drift is not None:
        r["fresh_extraction_drift"] = {"pred_max_abs_diff": 1e-3, "feature_reliability": {
            "n_arrays": 3, "reliability_min": drift, "reliability_gate_pass": drift >= 0.99,
            "per_extractor": {"video": {"reliability": drift, "max_abs_diff": 0.1, "n_arrays": 1}}}}
    return r


def test_summary_detects_exact_rerun_and_gate(tmp_path):
    cm = {"run_id": "r", "instance_id": "i", "instance_type": "a100", "usd_spent_this_run": 1.0,
          "alive_after": [], "instance_heartbeats": 5, "steps": {"smoke": 0},
          "runs": {"smoke_a": _run("x", False), "smoke_b": _run("x", True), "smoke_c": _run("x", True, 0.995),
                   "rel_long70": _run("y", False, 0.98), "rel_long70_rerun": _run("y", True)}}
    (tmp_path / "child_metrics.json").write_text(json.dumps(cm))
    s = rep.summarise(tmp_path)
    assert s["cached_rerun"]["bit_identical_a_b"] is True and s["cached_rerun"]["bit_identical_a_c"] is True
    assert s["fresh_drift"]["smoke_c"]["reliability_gate_pass"] is True
    assert s["fresh_drift"]["rel_long70"]["reliability_gate_pass"] is False
    assert s["rel_reruns"]["long70"] == {"bit_identical": True, "rerun_cache_reused": True}
    md = rep.report(s)
    assert "bit-identical A==B: **True**" in md and "rel_long70" in md


def test_summary_flags_non_identical_rerun(tmp_path):
    cm = {"runs": {"smoke_a": _run("x", False), "smoke_b": _run("z", True)}, "steps": {}}
    (tmp_path / "child_metrics.json").write_text(json.dumps(cm))
    assert rep.summarise(tmp_path)["cached_rerun"]["bit_identical_a_b"] is False
