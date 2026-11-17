#!/usr/bin/env python3
"""Summarise a scripts/gpu_p0_rerun.py run dir: writes <run_dir>/summary.json and <run_dir>/report.md.

Usage: python scripts/p0_rerun_report.py outputs/runs/<run_id>
       python scripts/p0_rerun_report.py outputs/runs/<run_id> --append-corrections BUG-026

BUG-026 (Referee P0 c2 N2/B3, Watchdog P0 c2 defect 1, Biostat P0 c2 N4): a comparison whose inputs were
never produced is reported as "not run" (None), never as False; the run's exit code (non-zero flagged),
git_dirty, a --collect-only recovery at a different SHA and a post-hoc recompute are disclosed in a
Provenance section. --append-corrections appends a "Corrections (<ticket>)" section to an existing
report.md (original text kept byte-for-byte; idempotent) and writes summary_<ticket>.json beside the
original summary.json, which is left untouched.
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


def _same(*vals):
    """True/False if every value was produced (truthy) and they are / are not all equal; None = not run."""
    if len(vals) < 2 or not all(vals):
        return None
    return all(v == vals[0] for v in vals[1:])


def _text(run_dir: Path, name: str) -> str | None:
    f = run_dir / name
    return f.read_text().strip() if f.exists() else None


def provenance(run_dir: Path) -> dict:
    """Exit code, SHAs, dirty flag, collect-only / recompute disclosures from the run dir files."""
    m = json.loads((run_dir / "metrics.json").read_text()) if (run_dir / "metrics.json").exists() else {}
    ec = _text(run_dir, "exit_code")
    ec = int(ec) if ec not in (None, "") else m.get("exit_code")
    sha = _text(run_dir, "git_sha") or m.get("git_sha")
    csha, ccmd = _text(run_dir, "collect_git_sha"), _text(run_dir, "collect_cmd")
    collect = csha is not None or ccmd is not None
    return {"exit_code": ec, "exit_code_nonzero": None if ec is None else ec != 0,
            "git_sha": sha, "git_dirty": m.get("git_dirty"),
            "collect_only": collect, "collect_git_sha": csha, "collect_cmd": ccmd,
            "collect_sha_mismatch": bool(collect and csha and sha and csha != sha),
            "recompute_cmd": _text(run_dir, "recompute_cmd")}


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
        "bit_identical_a_b": _same(a.get("pred_sha256"), b.get("pred_sha256")),
        "bit_identical_a_c": _same(a.get("pred_sha256"), c.get("pred_sha256")),
        "feature_sha256_equal": _same(*[r.get("feature_sha256") for r in (a, b, c) if r]),
    }
    s["provenance"] = provenance(run_dir)
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
    for f in sorted(run_dir.glob("*.reliability.json")):  # recomputed from kept fresh features (CPU)
        fr = json.loads(f.read_text())
        n = f.name[: -len(".reliability.json")]
        s["fresh_drift"].setdefault(n, {}).update({
            "recomputed_from_kept_fresh_features": True, "n_arrays": fr.get("n_arrays"),
            "unreadable": len(fr.get("unreadable", [])), "reliability_min": fr.get("reliability_min"),
            "reliability_gate_pass": fr.get("reliability_gate_pass"),
            "per_extractor": {k: {"reliability": v.get("reliability"), "max_abs_diff": v.get("max_abs_diff"),
                                  "n_arrays": v.get("n_arrays"), "bit_identical": v.get("bit_identical")}
                              for k, v in (fr.get("per_extractor") or {}).items()}})
    s["rel_reruns"] = {c: {"bit_identical": _same(_get(runs, f"rel_{c}", "pred_sha256"),
                                                  _get(runs, f"rel_{c}_rerun", "pred_sha256")),
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


def _v(x) -> str:
    """Report value: None (comparison inputs never produced) -> 'not run' (BUG-026)."""
    return "not run" if x is None else str(x)


def provenance_lines(p: dict) -> list[str]:
    ec = p.get("exit_code")
    ec_s = ("**not recorded**" if ec is None else
            f"**{ec}** (NON-ZERO: the run did not finish cleanly; see stdout.log)" if ec != 0 else f"**{ec}**")
    out = ["## Provenance (BUG-026)", "", f"- run exit code {ec_s}; git_sha {p.get('git_sha')}, "
           f"git_dirty: **{p.get('git_dirty')}**."]
    if p.get("collect_only"):
        out.append(f"- summary/report produced by a separate `--collect-only` recovery at git sha "
                   f"{p.get('collect_git_sha')} (cmd {p.get('collect_cmd')})"
                   + (f"; **SHA MISMATCH** with the run sha {p.get('git_sha')}." if p.get("collect_sha_mismatch")
                      else "."))
    if p.get("recompute_cmd"):
        out.append(f"- reliability recomputed post hoc: {p['recompute_cmd']}")
    return out + [""]


def report(s: dict) -> str:
    cr = s["cached_rerun"]
    nr = all(cr[k] is None for k in ("a_cache_reused", "b_cache_reused", "c_cache_reused"))
    det = (["- smoke A/B/C cached-rerun step: **not run** in this run (no smoke_a/b/c entries)."] if nr else
           [f"- smoke A extracted (cache_reused={_v(cr['a_cache_reused'])}); B and C re-predicted from the "
            f"cache (cache_reused={_v(cr['b_cache_reused'])}, {_v(cr['c_cache_reused'])})."])
    sha = cr["pred_sha256_a"]
    det.append(f"- predictions bit-identical A==B: **{_v(cr['bit_identical_a_b'])}**, A==C: "
               f"**{_v(cr['bit_identical_a_c'])}**" + (f" (sha256 {str(sha)[:16]})" if sha else "")
               + f"; feature sha256 equal: {_v(cr['feature_sha256_equal'])}.")
    lines = [f"# P0 GPU re-run `{s['run_id']}` (FIX-C3-ENG item F)", "",
             f"Instance `{s['instance_id']}` ({s['instance_type']}), spent ${s['usd_spent_this_run']}, "
             f"alive after: {s['alive_after']}, instance heartbeats in ledger: {s['instance_heartbeats']}.",
             f"Steps (rc): {s['steps']}." + (f" Error: `{s['error']}`" if s.get("error") else ""), "",
             *provenance_lines(s.get("provenance") or {}),
             "## Cached-feature determinism (D-038 gate: exact)", "", *det, "",
             f"- reliability runs, cached rerun bit-identical: {s.get('rel_reruns') or 'not run'}", "",
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


def append_corrections(run_dir: Path, ticket: str) -> bool:
    """Append a 'Corrections (<ticket>)' section (regenerated with the fixed labels) to report.md without
    touching the original text; write summary_<ticket>.json. Idempotent. Returns True if appended."""
    run_dir = Path(run_dir)
    rp = run_dir / "report.md"
    old = rp.read_text() if rp.exists() else ""
    head = f"## Corrections ({ticket})"
    if head in old:
        return False
    s = summarise(run_dir)
    (run_dir / f"summary_{ticket.lower().replace('-', '')}.json").write_text(json.dumps(s, indent=1, default=str))
    cr, p = s["cached_rerun"], s["provenance"]
    notes = []
    if all(cr[k] is None for k in ("bit_identical_a_b", "bit_identical_a_c")):
        notes.append("the smoke A/B/C cached-rerun step did **not run** in this run; the original "
                     "'bit-identical A==B: False ... (sha256 None)' line above is a mislabel, not a Gate-1 failure")
    if p.get("exit_code_nonzero"):
        notes.append(f"the run exited with code **{p['exit_code']}** (NON-ZERO); the original 'Steps (rc)' line "
                     "lists only the per-step return codes and did not disclose it")
    if p.get("collect_sha_mismatch"):
        notes.append(f"summary/report were produced by a `--collect-only` recovery at {p['collect_git_sha']}, "
                     f"not at the run sha {p['git_sha']} (SHA MISMATCH)")
    if p.get("git_dirty"):
        notes.append("the run started from a dirty working tree (git_dirty True)")
    if p.get("recompute_cmd"):
        notes.append("the fresh-drift reliability was recomputed post hoc (recompute_cmd)")
    body = [head, "", f"Appended by `scripts/p0_rerun_report.py --append-corrections {ticket}`; the text "
            "above is the original report, unchanged. Corrected summary: "
            f"`summary_{ticket.lower().replace('-', '')}.json` (the original summary.json is kept).", ""]
    body += [f"- {n}." for n in notes] + [""] if notes else ["- no mislabel found.", ""]
    body += ["### Regenerated report (fixed labels)", "", *("> " + ln if ln else ">" for ln in
                                                        report(s).rstrip("\n").split("\n")), ""]
    rp.write_text(old + ("" if old.endswith("\n") or not old else "\n") + "\n" + "\n".join(body))
    return True


if __name__ == "__main__":
    d = Path(sys.argv[1])
    if len(sys.argv) > 3 and sys.argv[2] == "--append-corrections":
        print("appended" if append_corrections(d, sys.argv[3]) else "already present")
        sys.exit(0)
    s = summarise(d)
    (d / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    (d / "report.md").write_text(report(s))
    print(json.dumps({k: s[k] for k in ("cached_rerun", "fresh_drift")}, indent=1, default=str))
