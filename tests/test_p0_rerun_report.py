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


# ---- BUG-026 (Referee P0 c2 N2/B3, Watchdog P0 c2 defect 1, Biostat N4): absent steps and provenance
def _write(tmp_path, cm, **files):
    (tmp_path / "child_metrics.json").write_text(json.dumps(cm))
    for k, v in files.items():
        (tmp_path / k).write_text(v if isinstance(v, str) else json.dumps(v))
    return tmp_path


def test_absent_cached_rerun_prints_not_run_not_false(tmp_path):
    cm = {"runs": {"rel_smoke": _run("y", False, 0.999), "rel_smoke_rerun": _run("y", True)}, "steps": {}}
    s = rep.summarise(_write(tmp_path, cm))
    cr = s["cached_rerun"]
    assert cr["bit_identical_a_b"] is None and cr["bit_identical_a_c"] is None
    assert cr["feature_sha256_equal"] is None
    md = rep.report(s)
    assert "bit-identical A==B: **not run**" in md and "A==C: **not run**" in md
    assert "**False**" not in md.split("## Fresh")[0]
    assert "sha256 None" not in md


def test_partially_run_cached_rerun_not_run_for_missing_side(tmp_path):
    cm = {"runs": {"smoke_a": _run("x", False), "smoke_b": _run("x", True)}, "steps": {}}
    s = rep.summarise(_write(tmp_path, cm))
    assert s["cached_rerun"]["bit_identical_a_b"] is True and s["cached_rerun"]["bit_identical_a_c"] is None
    assert "A==C: **not run**" in rep.report(s)


def test_nonzero_exit_and_collect_only_sha_mismatch_disclosed(tmp_path):
    cm = {"runs": {"smoke_a": _run("x", False), "smoke_b": _run("x", True)}, "steps": {"smoke": 0}}
    d = _write(tmp_path, cm, exit_code="1\n", git_sha="aaaa111\n", collect_git_sha="bbbb222\n",
               collect_cmd='["python", "scripts/gpu_p0_rerun.py", "--collect-only"]',
               **{"metrics.json": {"exit_code": 1, "git_sha": "aaaa111", "git_dirty": True}})
    s = rep.summarise(d)
    p = s["provenance"]
    assert p["exit_code"] == 1 and p["exit_code_nonzero"] is True
    assert p["collect_only"] is True and p["collect_sha_mismatch"] is True and p["git_dirty"] is True
    md = rep.report(s)
    assert "exit code **1** (NON-ZERO" in md
    assert "collect-only" in md and "aaaa111" in md and "bbbb222" in md and "SHA MISMATCH" in md
    assert "git_dirty: **True**" in md


def test_clean_provenance_reported_plainly(tmp_path):
    cm = {"runs": {"smoke_a": _run("x", False), "smoke_b": _run("x", True)}, "steps": {"smoke": 0}}
    d = _write(tmp_path, cm, exit_code="0\n", git_sha="aaaa111\n",
               **{"metrics.json": {"exit_code": 0, "git_sha": "aaaa111", "git_dirty": False}})
    p = rep.summarise(d)["provenance"]
    assert p["exit_code_nonzero"] is False and p["collect_only"] is False
    assert p["collect_sha_mismatch"] is False
    md = rep.report(rep.summarise(d))
    assert "exit code **0**" in md and "NON-ZERO" not in md and "MISMATCH" not in md


def test_missing_exit_code_is_not_reported_as_zero(tmp_path):
    cm = {"runs": {"smoke_a": _run("x", False)}, "steps": {}}
    s = rep.summarise(_write(tmp_path, cm))
    assert s["provenance"]["exit_code"] is None
    assert "exit code **not recorded**" in rep.report(s)


def test_recompute_cmd_disclosed(tmp_path):
    cm = {"runs": {"rel_smoke": _run("y", False)}, "steps": {}}
    d = _write(tmp_path, cm, exit_code="0", recompute_cmd='["python3", "x.py"]  # working-tree code')
    s = rep.summarise(d)
    assert s["provenance"]["recompute_cmd"].startswith('["python3"')
    assert "recomputed post hoc" in rep.report(s)


def test_append_corrections_keeps_original_and_is_idempotent(tmp_path):
    cm = {"runs": {"rel_smoke": _run("y", False, 0.999), "rel_smoke_rerun": _run("y", True)}, "steps": {}}
    d = _write(tmp_path, cm, exit_code="1", git_sha="aaaa111", collect_git_sha="bbbb222")
    orig = "# old report\n- predictions bit-identical A==B: **False** (sha256 None)\n"
    (d / "report.md").write_text(orig)
    (d / "summary.json").write_text('{"old": true}')
    rep.append_corrections(d, "BUG-026")
    new = (d / "report.md").read_text()
    assert new.startswith(orig)                                  # nothing deleted or edited
    tail = new[len(orig):]
    assert "## Corrections (BUG-026)" in tail and "**not run**" in tail and "NON-ZERO" in tail
    assert (d / "summary.json").read_text() == '{"old": true}'    # original summary untouched
    assert json.loads((d / "summary_bug026.json").read_text())["cached_rerun"]["bit_identical_a_b"] is None
    rep.append_corrections(d, "BUG-026")
    assert (d / "report.md").read_text() == new                  # idempotent
