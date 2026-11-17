#!/usr/bin/env python3
"""Summarise a scripts/gpu_p0_rerun.py run dir: writes <run_dir>/summary.json and <run_dir>/report.md.

Usage: python scripts/p0_rerun_report.py outputs/runs/<run_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _get(d: dict, *ks, default=None):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def summarise(run_dir: Path) -> dict:
    cm = json.loads((run_dir / "child_metrics.json").read_text())
    runs = cm.get("runs", {})
    s: dict = {"run_id": cm.get("run_id"), "instance_id": cm.get("instance_id"),
               "instance_type": cm.get("instance_type"), "usd_spent_this_run": cm.get("usd_spent_this_run"),
               "alive_after": cm.get("alive_after"), "instance_heartbeats": cm.get("instance_heartbeats"),
               "steps": cm.get("steps"), "error": cm.get("error")}
    a, b, c = runs.get("smoke_a", {}), runs.get("smoke_b", {}), runs.get("smoke_c", {})
    s["cached_rerun"] = {
        "a_cache_reused": a.get("cache_reused"), "b_cache_reused": b.get("cache_reused"),
        "c_cache_reused": c.get("cache_reused"),
        "pred_sha256_a": a.get("pred_sha256"), "pred_sha256_b": b.get("pred_sha256"),
        "pred_sha256_c": c.get("pred_sha256"),
        "bit_identical_a_b": bool(a.get("pred_sha256")) and a.get("pred_sha256") == b.get("pred_sha256"),
        "bit_identical_a_c": bool(a.get("pred_sha256")) and a.get("pred_sha256") == c.get("pred_sha256"),
        "feature_sha256_equal": a.get("feature_sha256") == b.get("feature_sha256") == c.get("feature_sha256"),
    }
    s["fresh_drift"] = {}
    for n in [k for k, r in runs.items() if r.get("fresh_extraction_drift")]:
        d = _get(runs, n, "fresh_extraction_drift") or {}
        fr = d.get("feature_reliability") or {}
        s["fresh_drift"][n] = {
            "pred_max_abs_diff": d.get("pred_max_abs_diff"), "pred_pearson_r": d.get("pred_pearson_r"),
            "pred_reliability": d.get("pred_reliability"), "n_arrays": fr.get("n_arrays"),
            "reliability_min": fr.get("reliability_min"), "reliability_gate_pass": fr.get("reliability_gate_pass"),
            "per_extractor": {k: {"reliability": v.get("reliability"), "max_abs_diff": v.get("max_abs_diff"),
                                  "n_arrays": v.get("n_arrays")} for k, v in (fr.get("per_extractor") or {}).items()},
        }
    s["rel_reruns"] = {c: {"bit_identical": bool(_get(runs, f"rel_{c}", "pred_sha256"))
                           and _get(runs, f"rel_{c}", "pred_sha256") == _get(runs, f"rel_{c}_rerun", "pred_sha256"),
                           "rerun_cache_reused": _get(runs, f"rel_{c}_rerun", "cache_reused")}
                       for c in ("smoke", "long70", "long110") if f"rel_{c}" in runs}
    s["clips"] = {}
    for n, r in runs.items():
        s["clips"][n] = {k: r.get(k) for k in (
            "duration_s", "shape", "expected_T", "T_within_1", "finite", "n_segments", "first_segment_start_s",
            "last_segment_start_s", "chunks", "n_words", "word_start_min_s", "word_start_max_s",
            "words_after_duration", "peak_vram_smi_mib", "torch_max_allocated_mib", "torch_max_reserved_mib",
            "wall_extract_s", "wall_events_predict_s", "gpu", "offline", "offline_env", "backbone_revisions",
            "cache_key", "input_sha256", "transcript_sha256")}
    return s


def report(s: dict) -> str:
    cr = s["cached_rerun"]
    lines = [f"# P0 GPU re-run `{s['run_id']}` (FIX-C3-ENG item F)", "",
             f"Instance `{s['instance_id']}` ({s['instance_type']}), spent ${s['usd_spent_this_run']}, "
             f"alive after: {s['alive_after']}, instance heartbeats in ledger: {s['instance_heartbeats']}.",
             f"Steps (rc): {s['steps']}." + (f" Error: `{s['error']}`" if s.get("error") else ""), "",
             "## Cached-feature determinism (D-038 gate: exact)", "",
             f"- smoke A extracted (cache_reused={cr['a_cache_reused']}); B and C re-predicted from the cache "
             f"(cache_reused={cr['b_cache_reused']}, {cr['c_cache_reused']}).",
             f"- predictions bit-identical A==B: **{cr['bit_identical_a_b']}**, A==C: **{cr['bit_identical_a_c']}** "
             f"(sha256 {str(cr['pred_sha256_a'])[:16]}); feature sha256 equal: {cr['feature_sha256_equal']}.", "",
             f"- reliability runs, cached rerun bit-identical: {s.get('rel_reruns')}", "",
             "## Fresh re-extraction reliability (D-038 gate: >= 0.99 per feature)", ""]
    for n, d in s["fresh_drift"].items():
        lines.append(f"- {n}: reliability_min **{d['reliability_min']}** over {d['n_arrays']} arrays, gate pass "
                     f"**{d['reliability_gate_pass']}**; predictions max|diff| {d['pred_max_abs_diff']}, "
                     f"r {d['pred_pearson_r']}, reliability {d['pred_reliability']}.")
        for k, v in d["per_extractor"].items():
            lines.append(f"  - `{k}`: reliability {v['reliability']}, max|diff| {v['max_abs_diff']} "
                         f"({v['n_arrays']} arrays)")
    lines += ["", "## Clips (shape, T, chunk/context boundaries, VRAM)", "",
              "| run | dur s | shape | T ok | segments first..last | Audio/Video chunks [start, dur] | words "
              "(min..max start, >dur) | peak VRAM MiB (smi / torch alloc) | extract s |", "|---|---|---|---|---|---|---|---|---|"]
    for n, c in s["clips"].items():
        lines.append(f"| {n} | {c['duration_s']} | {c['shape']} | {c['T_within_1']} | {c['n_segments']}: "
                     f"{c['first_segment_start_s']}..{c['last_segment_start_s']} | {c['chunks']} | {c['n_words']} "
                     f"({c['word_start_min_s']}..{c['word_start_max_s']}, {c['words_after_duration']}) | "
                     f"{c['peak_vram_smi_mib']} / {c['torch_max_allocated_mib']} | {c['wall_extract_s']} |")
    first = next(iter(s["clips"].values()), {})
    lines += ["", "## Offline / pins", "", f"- offline={first.get('offline')}, env {first.get('offline_env')}",
              f"- backbone revisions (refs/main == pinned, checked before running): {first.get('backbone_revisions')}",
              "", "Artifacts: pod `/work/yct/runs/<run_id>/` (res/, fc/, clips/) and feature cache entries under "
              "`/work/yct/cache/`; sha256 in SHA256SUMS, FC_SHA256SUMS and cache_manifest.json here."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    d = Path(sys.argv[1])
    s = summarise(d)
    (d / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    (d / "report.md").write_text(report(s))
    print(json.dumps({k: s[k] for k in ("cached_rerun", "fresh_drift")}, indent=1, default=str))
