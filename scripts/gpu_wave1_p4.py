#!/usr/bin/env python3
"""Wave-1 P4: resumable batch TRIBE driver, full model, T1 + T3, frozen run sets (D-063; ticket FIX-P4E).

Run under provenance (one Lambda session per invocation; re-run while it exits 75; exit 1 needs a human):
    python scripts/run_with_provenance.py --run-id p4_<UTC> -- python scripts/gpu_wave1_p4.py \
        [--max-hours 3.75] [--usd-limit 10] [--external-terminator-at <epoch|ISO>]
Dry run (no network, no GPU; in-memory Lambda, local-directory pod/box/S3):
    python scripts/gpu_wave1_p4.py --dry-run [--dry-run-root DIR] [--limit N]

Exit codes: 0 = every job of the frozen run sets is synced and passed; 75 = this session ended cleanly with
jobs left (re-run while it exits 75); 1 = any gate failure, error, D-038 STOP or instance alive after
teardown: exit 1 needs a human, never an automatic retry loop.
D-038 STOP latch (QA cycle-2 N1): a D-038 Gate 1/2 failure writes the immutable marker p4/stops/<run>.json
(and its manifest row); while any stop (marker or failing D-038 row) has no p4/stops_cleared/<run>.json,
every later invocation refuses before launching. Only `--clear-stop D-NNN` clears it, and only if
DECISIONS.md has an entry D-NNN that names every stopped run id (a human/orchestrator decision first).
S3 reads (QA cycle-2 N2): only a 404/NoSuchKey reads as "absent"; any other error raises S3ReadError and
the run fails closed (no manifest rewrite, no upload over an immutable object); a manifest that reads as
absent while rows/ exist is refused.

Jobs (plan_jobs): config p4.run_set_t1 x T1 (51) + p4.run_set_t3 x T3 (52), the 3 D-038 clips first. Per job
the box runs src/yct/tribe_run/run_clip.py --bug018-word-fix --qc-gate <track> (one setting for all of P4,
QA D11) on the pod's normalised clip + pinned transcript (sha256 checked against the transcript manifest);
the D-038 clips also run --fresh-drift --keep-fresh plus a cached rerun (Gate 1 bit-identical, Gate 2
reliability >= 0.99; a failure is a STOP) and their fresh predictions + features are saved (D-063).

Resumable, per-video sync (D-063 engineering blockers):
  * after EACH job: cache entry tar (no media) + FILES_SHA256SUMS -> S3 feature_cache/<key>.*, an entry index
    entries_clampv1/<job>.json (which run/instance produced it), predictions + segments -> pred_clampv1/<track>/<video>.*,
    the sanitised record -> records/, then one row appended to manifest.jsonl (+ immutable rows/<run>/<job>);
    media of the entry (clip copy, TRIBE's .wav) stay on the pod (/work/yct/p4/cache_media, by sha256);
  * S3 objects are immutable: an existing object whose .sha256 sidecar differs is never overwritten;
  * manifest.jsonl is appended, never rewritten (the remote must still equal what was read: check_append);
  * a job is skipped when its passing manifest row, predictions and cache tar are all in S3; a job whose
    cache entry is in S3 but not its predictions (crash) is RESTORED on the new box (cache_archive) and
    predicted from cache: never re-extracted mid-campaign (Biostat P4-entry Q7);
  * <= 4 h per Lambda session (config p4.session_max_hours, lambda_gpu hard cap): no job starts unless it
    fits before the instance deadline minus teardown time.
Gates (yct.tribe_run.qc.clip_gate, fail closed): exactly one Audio and one Video chunk, shape (T, 20484),
T, finite, n_words == .tsv rows, offline/no ASR, GPU model == p4.gpu_name, BUG-018 fix on, transcript and
clip sha256 == the pod's, the same revisions sha256 as every other P4 entry (cache key = video ||
transcript || revisions incl. backbone revisions + GPU model). Any failure -> exit 1.

OUTPUT FIREWALL (D-063 B2): this driver never loads a prediction array and computes no W-average,
ROI/network readout, OOD or cross-video statistic; records keep numbers and hashes only (no pred mean/SD,
no feature names: they hold transcript text). tests/test_gpu_wave1_p4.py asserts it imports no analysis code.

Cost guards (D-063 Q7, BUG-027): at EVERY session start reap + name-deadline reap + liveness-aware sweep
(keeps a concurrent run whose box touch is fresh), and refuse to launch while any yct-* instance lives. The
instance name carries its launch time and deadline; the box dead-man switch starts as the FIRST ssh command
(halts at grace/hard cap/deadline). A driver-INDEPENDENT terminator is required per launch at deadline +
15 min: either the pod-side systemd-run timer (infra/gpu_terminator.sh; Lambda key read pod-side from SSM
/yct/lambda_api_key, owner-created) or, if the pod cannot read that key, a one-shot scheduled session that
the orchestrator creates BEFORE launch and declares with --external-terminator-at (it must run
`python infra/lambda_gpu.py reap-deadline --margin-s 0`). Without either, the driver refuses to launch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from yct.tribe_run.qc import GPU_NAME, WORD_END_CLAMP, clip_gate, sanitize_metrics  # noqa: E402

# BUG-029 (FIX-P4G, D-067): predictions of the clamped stack go to their own prefix, so a job re-run after the
# superseded (pre-clamp) runs never collides with their pred/<track>/<video>.npy (S3 objects are never
# overwritten). Consumers read the row's pred_key, never a fixed path.
PRED_PREFIX = f"pred_clamp{WORD_END_CLAMP}"
ENTRY_PREFIX = f"entries_clamp{WORD_END_CLAMP}"   # same reason for entries/<job>.json
D038_PREFIX = f"d038_fresh_clamp{WORD_END_CLAMP}"  # ... and d038_fresh/<video>.fresh_*

EXIT_OK, EXIT_FAIL, EXIT_INCOMPLETE = 0, 1, 75
TEARDOWN_S = 600          # sync of the last job + terminate, reserved before the deadline
SETUP_EST_S = 1800        # remote_setup.sh (weights, venv) on a fresh box
EXTRACT_EST_S = 360       # measured ~305 s per 58 s clip (D-062) + load
PREDICT_EST_S = 120       # restore + predict from cache
TERMINATOR_MAX_LATE_S = 3600   # an external terminator later than deadline + margin + 1 h is refused
DEADMAN_GRACE_S = 1200
TOUCH_EVERY_S = 60
TOUCH = "~/yct_driver_touch"
POD_P4 = "/work/yct/p4"
REPO = "/work/yct/repo"
PY = "/work/yct/venv/bin/python"


class ManifestConflictError(RuntimeError):
    """The remote manifest changed underneath this session (no silent overwrite)."""


class OverwriteRefusedError(RuntimeError):
    """An immutable S3 object already exists with different content."""


class S3ReadError(RuntimeError):
    """An S3 read failed for any reason other than "object not found" (fail closed, QA c2 N2)."""


_NOT_FOUND = re.compile(r"\((?:404|NoSuchKey)\)")


@dataclass(frozen=True)
class Job:
    video_id: str
    track: str
    d038: bool = False

    @property
    def id(self) -> str:
        return f"{self.video_id}.{self.track}"


@dataclass
class SessionArgs:
    max_hours: float
    usd_limit: float
    external_terminator_at: float | None
    run_id: str
    limit: int | None = None
    clear_stop: str | None = None
    decisions_path: Path | None = None


def plan_jobs(cfg: dict) -> list[Job]:
    """Frozen run sets (config p4, D-063): D-038 clips first (T1), then T1, then T3, by video_id."""
    p = cfg["p4"]
    d038 = list(p["d038_clips"])
    jobs = [Job(v, "t1", True) for v in d038]
    jobs += [Job(v, "t1") for v in sorted(p["run_set_t1"]) if v not in d038]
    jobs += [Job(v, "t3") for v in sorted(p["run_set_t3"])]
    return jobs


# ---------------------------------------------------------------- manifest + immutable S3 objects
def append_manifest(old: str, rows: list[dict]) -> str:
    new = old + "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    assert new.startswith(old)
    return new


def check_append(read_before: str, remote_now: str) -> None:
    if remote_now != read_before:
        raise ManifestConflictError("manifest.jsonl changed since it was read; refusing to overwrite it")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Store:
    """Immutable-object + append-only-manifest layer over a backend's S3 primitives (keys relative to p4/)."""

    def __init__(self, backend):
        self.b = backend

    def put_file(self, pod_path: str, key: str, sha: str) -> bool:
        """Upload unless an identical object exists; an existing different object -> OverwriteRefusedError."""
        have = self.b.s3_get_text(key + ".sha256")
        if have is not None:
            if have.strip() != sha:
                raise OverwriteRefusedError(f"refusing to overwrite {key}: existing sha256 {have.strip()[:12]} != {sha[:12]}")
            return False
        self.b.s3_upload(pod_path, key)
        self.b.s3_put_text(key + ".sha256", sha + "\n")
        return True

    def put_text(self, key: str, text: str) -> bool:
        have = self.b.s3_get_text(key)
        if have is not None:
            if have != text:
                raise OverwriteRefusedError(f"refusing to overwrite {key} with different content")
            return False
        self.b.s3_put_text(key, text)
        return True

    def append_rows(self, rows: list[dict], run_id: str) -> None:
        old = self.b.s3_get_text("manifest.jsonl")
        if old is None and self.b.s3_list("rows/"):
            raise ManifestConflictError("manifest.jsonl reads as absent while rows/ exist; refusing to rewrite it")
        old = old or ""
        new = append_manifest(old, rows)
        check_append(old, self.b.s3_get_text("manifest.jsonl") or "")
        self.b.s3_put_text("manifest.jsonl", new)
        for r in rows:
            self.put_text(f"rows/{run_id}/{r['job']}.json", json.dumps(r, sort_keys=True, indent=1))


@dataclass
class State:
    rows: list[dict]
    entries: dict[str, dict]
    keys: set[str]

    def passed(self, job: Job) -> dict | None:
        ok = [r for r in self.rows if r.get("job") == job.id and r.get("gate_pass") is True]
        return ok[-1] if ok else None

    def revisions_sha256(self) -> str | None:
        shas = {r["revisions_sha256"] for r in self.rows if r.get("gate_pass") and r.get("revisions_sha256")}
        if len(shas) > 1:
            raise RuntimeError(f"P4 manifest mixes {len(shas)} revisions sets (one stack + GPU for all of P4)")
        return shas.pop() if shas else None


def load_state(backend, superseded: tuple[str, ...] | list[str] = ()) -> State:
    """Manifest rows + entries. Rows/entries of ``superseded`` runs (config p4.superseded_run_ids, BUG-029: made
    before the word-end clamp) are ignored for done/restore/revisions; their S3 objects stay (append-only).
    D-038 STOP markers are never ignored."""
    sup = set(superseded)
    text = backend.s3_get_text("manifest.jsonl")
    keys = set(backend.s3_list(""))
    if text is None and any(k.startswith("rows/") for k in keys):
        raise SystemExit("S3 manifest.jsonl is absent while rows/ exist: inconsistent store, refusing (repair "
                         "from rows/ by hand; never rewritten automatically)")
    rows = [json.loads(x) for x in (text or "").splitlines() if x.strip()]
    stop_rows = [r for r in rows if r.get("d038") is not None and r.get("gate_pass") is False]
    rows = [r for r in rows if r.get("run_id") not in sup] + [r for r in stop_rows if r.get("run_id") in sup]
    entries = {}
    for k in sorted(x for x in keys if x.startswith(("entries/", ENTRY_PREFIX + "/")) and x.endswith(".json")):
        e = json.loads(backend.s3_get_text(k))
        if e.get("run_id") in sup:
            continue
        entries[e["job"]] = e
    return State(rows, entries, keys)


def latched_stops(st: State) -> list[str]:
    """Run ids with a D-038 STOP (marker or failing D-038 manifest row) and no clearance (QA c2 N1)."""
    stops = {k[len("stops/"):-len(".json")] for k in st.keys if k.startswith("stops/") and k.endswith(".json")}
    stops |= {r["run_id"] for r in st.rows if r.get("d038") is not None and r.get("gate_pass") is False}
    cleared = {k[len("stops_cleared/"):-len(".json")] for k in st.keys
               if k.startswith("stops_cleared/") and k.endswith(".json")}
    return sorted(stops - cleared)


def decision_entry(decisions: str, dec_id: str) -> str | None:
    """Text of the DECISIONS.md bullet `- <dec_id> ...` up to the next decision bullet or section."""
    lines = decisions.splitlines()
    for i, ln in enumerate(lines):
        if re.match(rf"^\s*- {re.escape(dec_id)}\b", ln):
            out = [ln]
            for nxt in lines[i + 1:]:
                if re.match(r"^\s*- D-\d{3}", nxt) or nxt.startswith("## "):
                    break
                out.append(nxt)
            return "\n".join(out)
    return None


def is_done(job: Job, st: State) -> bool:
    r = st.passed(job)
    return bool(r and r.get("pred_key") in st.keys and f"feature_cache/{r['cache_key']}.tar" in st.keys)


def restorable(job: Job, st: State) -> dict | None:
    e = st.entries.get(job.id)
    if e and e.get("tar_key") in st.keys and e.get("sums_key") in st.keys and not is_done(job, st):
        return e
    return None


def _parse_when(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()


# ---------------------------------------------------------------- one job
def _d038_gate(rec: dict, rerun: dict | None) -> dict:
    d = rec.get("drift") or {}
    out = {"fresh_gate_pass": d.get("reliability_gate_pass") is True,
           "fresh_reliability_min": d.get("reliability_min"), "pred_reliability_fresh": d.get("pred_reliability"),
           "pred_max_abs_diff_fresh": d.get("pred_max_abs_diff"), "fresh_pred_sha256": d.get("fresh_pred_sha256"),
           "cached_rerun_bit_identical": bool(rerun and rerun.get("pred_sha256") == rec.get("pred_sha256")
                                              and rerun.get("cache_reused") is True)}
    out["pass"] = bool(out["fresh_gate_pass"] and out["cached_rerun_bit_identical"] and out["fresh_pred_sha256"])
    return out


def do_job(job: Job, ctx: dict) -> str:
    """Run, gate, sync one job. Returns "pass", "gate_fail" or "stop"; raises on infrastructure errors."""
    b, store, st, res, a = ctx["backend"], ctx["store"], ctx["state"], ctx["res"], ctx["args"]
    inp = ctx["inputs"][job.video_id][job.track]
    restore = restorable(job, st)
    b.stage(ctx["box"], job, inp, restore)
    if restore:
        res["restored"].append(job.id)
    rc, raw = b.run_job(ctx["box"], job, inp, "main")
    if raw is None:
        raise RuntimeError(f"run_clip rc={rc}, no metrics json")
    rec = sanitize_metrics(raw)
    del raw
    expected = {"transcript_sha256": inp["tsv_sha256"], "input_sha256": inp["sha256"]}
    if ctx["rev_sha"]:
        expected["revisions_sha256"] = ctx["rev_sha"]
    if restore:
        expected["cache_key"] = restore["cache_key"]
        expected["cache_reused"] = True
    gate = clip_gate(rec, job.track, expected)
    if rc != 0 and gate["pass"]:
        gate = {"pass": False, "failures": [f"run_clip exit code {rc}"]}
    d038 = None
    if job.d038 and gate["pass"]:
        rc2, raw2 = b.run_job(ctx["box"], job, inp, "rerun")
        rerun = sanitize_metrics(raw2) if raw2 else None
        del raw2
        d038 = _d038_gate(rec, rerun)
        if rc2 != 0 or rerun is None or not clip_gate(rerun, job.track, expected)["pass"]:
            d038["pass"] = False
    row = {"job": job.id, "video_id": job.video_id, "track": job.track, "run_id": a.run_id,
           "instance_id": ctx["iid"], "git_sha": ctx["git_sha"], "t": ctx["clock"](),
           "cache_key": rec.get("cache_key"), "cache_reused": rec.get("cache_reused"),
           "input_sha256": rec.get("input_sha256"), "transcript_sha256": rec.get("transcript_sha256"),
           "revisions_sha256": rec.get("revisions_sha256"), "gpu": (rec.get("revisions") or {}).get("gpu"),
           "pred_sha256": rec.get("pred_sha256"), "pred_shape": rec.get("pred_shape"),
           "gate_pass": gate["pass"] and (d038 is None or d038["pass"]), "gate_failures": gate["failures"],
           "restored_from_s3": bool(restore), "d038": d038}
    store.put_text(f"records/{job.track}/{job.video_id}.{a.run_id}.json",
                   json.dumps({"record": rec, "gate": gate, "d038": d038}, sort_keys=True, indent=1))
    if not gate["pass"]:
        store.append_rows([row], a.run_id)
        res["gate_failures"][job.id] = gate["failures"]
        return "gate_fail"
    if d038 is not None and not d038["pass"]:
        store.put_text(f"stops/{a.run_id}.json", json.dumps(
            {"job": job.id, "run_id": a.run_id, "d038": d038, "t": ctx["clock"](),
             "rule": "v2.md P4: a D-038 Gate 1/2 failure is a STOP; cleared only by --clear-stop D-NNN"},
            sort_keys=True, indent=1))
        store.append_rows([row], a.run_id)
        res["gate_failures"][job.id] = [f"D-038 gate: {d038}"]
        return "stop"
    files = b.collect(ctx["box"], job, rec)
    if files["pred"][1] != rec["pred_sha256"]:
        raise RuntimeError(f"pod copy of the predictions differs from the box sha256 for {job.id}")
    key = rec["cache_key"]
    tar_key, sums_key = f"feature_cache/{key}.tar", f"feature_cache/{key}.FILES_SHA256SUMS"
    store.put_file(files["entry_tar"][0], tar_key, files["entry_tar"][1])
    store.put_file(files["entry_sums"][0], sums_key, files["entry_sums"][1])
    if restore is None:
        store.put_text(f"{ENTRY_PREFIX}/{job.id}.json", json.dumps(
            {"job": job.id, "cache_key": key, "tar_key": tar_key, "sums_key": sums_key,
             "tar_sha256": files["entry_tar"][1], "sums_sha256": files["entry_sums"][1], "run_id": a.run_id,
             "instance_id": ctx["iid"], "revisions_sha256": rec.get("revisions_sha256"), "t": ctx["clock"]()},
            sort_keys=True, indent=1))
    b.after_entry_sync(job)          # dry-run fault injection point (crash between entry and predictions)
    pred_key = f"{PRED_PREFIX}/{job.track}/{job.video_id}.npy"
    store.put_file(files["pred"][0], pred_key, files["pred"][1])
    store.put_file(files["segments"][0], f"{PRED_PREFIX}/{job.track}/{job.video_id}.segments.csv", files["segments"][1])
    if d038 is not None:
        store.put_file(files["fresh_pred"][0], f"{D038_PREFIX}/{job.video_id}.fresh_pred.npy", files["fresh_pred"][1])
        store.put_file(files["fresh_feat"][0], f"{D038_PREFIX}/{job.video_id}.fresh_feat.tar", files["fresh_feat"][1])
        if files["fresh_pred"][1] != d038["fresh_pred_sha256"]:
            raise RuntimeError(f"fresh prediction sha256 mismatch for {job.id}")
    row.update({"pred_key": pred_key, "tar_sha256": files["entry_tar"][1], "sums_sha256": files["entry_sums"][1]})
    store.append_rows([row], a.run_id)
    if ctx["rev_sha"] is None:
        ctx["rev_sha"] = rec.get("revisions_sha256")
    return "pass"


# ---------------------------------------------------------------- one session
def run_session(a: SessionArgs, cfg: dict, lg, backend, clock, run_dir: Path) -> tuple[int, dict]:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    p = cfg["p4"]
    cap = min(float(p["session_max_hours"]), float(cfg["budget"]["max_hours_per_instance"]), 4.0)
    if a.max_hours > cap:
        raise SystemExit(f"--max-hours {a.max_hours} exceeds the {cap:g} h session cap (<= 4 h)")
    itype, margin = p["gpu_type"], float(p["terminator_margin_s"])
    if p["gpu_name"] != GPU_NAME:
        raise SystemExit(f"config p4.gpu_name {p['gpu_name']!r} != qc.GPU_NAME {GPU_NAME!r}")
    store = Store(backend)
    jobs = plan_jobs(cfg)
    st = load_state(backend, p.get("superseded_run_ids") or [])
    res: dict[str, Any] = {"run_id": a.run_id, "git_sha": backend.git_sha(), "instance_type": itype,
                           "jobs_run": [], "restored": [], "gate_failures": {}, "errors": {},
                           "decision": "D-063", "firewall": "per-clip checks only (D-063 B2)"}
    pending = [j for j in jobs if not is_done(j, st)]
    res["pending_at_start"] = len(pending)
    # BUG-027 / D-063 Q7: at EVERY session start, before anything else
    res["orphans_at_start"] = {"reap": lg.reap(), "reap_deadline": lg.reap_deadline(margin_s=0),
                               "sweep": lg.sweep()}
    if lg._live(lg.list_ours()):
        raise SystemExit("a yct-* instance is still alive after the orphan sweep (a concurrent live run "
                         "with a fresh touch, or booting); one instance at a time")
    # QA c2 N1: a D-038 STOP is latched (orphan cleanup above still runs: it only terminates)
    stops = latched_stops(st)
    if a.clear_stop and not stops:
        raise SystemExit(f"--clear-stop {a.clear_stop}: there is no latched D-038 STOP to clear")
    if stops and not a.clear_stop:
        raise SystemExit(f"D-038 STOP latched by run(s) {stops} (v2.md P4: a STOP). A human decision is "
                         "needed: add a DECISIONS.md entry naming these run ids, then pass --clear-stop D-NNN")
    if stops:
        dec_path = Path(a.decisions_path or ROOT / "DECISIONS.md")
        entry = decision_entry(dec_path.read_text(), a.clear_stop)
        if entry is None:
            raise SystemExit(f"--clear-stop {a.clear_stop}: no such entry in {dec_path.name}")
        missing = [r for r in stops if r not in entry]
        if missing:
            raise SystemExit(f"--clear-stop {a.clear_stop}: the entry does not name the stopped run(s) {missing}")
        for r in stops:
            store.put_text(f"stops_cleared/{r}.json", json.dumps(
                {"run_id": r, "decision": a.clear_stop, "cleared_by_run": a.run_id, "t": clock(),
                 "decision_entry_sha256": sha256_text(entry)}, sort_keys=True, indent=1))
        res["stop_cleared"] = {r: a.clear_stop for r in stops}
    if not pending:
        res["status"] = "complete"
        return _finish(res, run_dir, backend, store, jobs, p.get("superseded_run_ids") or [])
    if a.limit:
        pending = pending[:a.limit]
    price = lg.types()[itype]["usd_per_hour"]
    if price * a.max_hours > a.usd_limit:
        raise SystemExit(f"{price}*{a.max_hours} h exceeds the task limit ${a.usd_limit}")
    backend.preflight(res["git_sha"])    # pod repo at this commit (pod-side scripts, terminator) before inputs
    inputs = backend.inputs(sorted({j.video_id for j in pending}))
    missing = [j.id for j in pending if j.track not in inputs.get(j.video_id, {})]
    if missing:
        raise SystemExit(f"pod inputs missing for {missing[:5]} (+{max(0, len(missing) - 5)})")
    # D-063 Q7: a driver-independent terminator at deadline + 15 min, or no launch
    ext = a.external_terminator_at
    planned = clock() + a.max_hours * 3600
    pod_term = backend.terminator_available()
    if ext is not None and not planned + margin <= ext <= planned + margin + TERMINATOR_MAX_LATE_S:
        raise SystemExit(f"external terminator at {ext:.0f} must fire between deadline + {margin:.0f} s "
                         f"({planned + margin:.0f}) and + {TERMINATOR_MAX_LATE_S} s more")
    if ext is None and not pod_term:
        raise SystemExit("no driver-independent terminator: the pod cannot schedule gpu_terminator.sh "
                         "(systemd-run or SSM /yct/lambda_api_key unavailable) and no --external-terminator-at "
                         "was given (create a one-shot scheduled session at deadline + 15 min running "
                         "`python infra/lambda_gpu.py reap-deadline --margin-s 0` first)")
    spent0 = lg.spent_usd()
    rec = lg.launch(itype, "yct-p4", a.max_hours, "yct-pod", None, name_deadline=True)
    iid, deadline = rec["id"], float(rec["deadline"])
    res.update({"instance_id": iid, "instance_name": rec.get("name"), "deadline": deadline})
    box = None
    ctx = {"backend": backend, "store": store, "state": st, "res": res, "args": a, "inputs": inputs,
           "iid": iid, "git_sha": res["git_sha"], "clock": clock, "rev_sha": st.revisions_sha256()}
    try:
        if ext is not None:
            if ext < deadline + margin:
                raise RuntimeError(f"external terminator fires before deadline + {margin:.0f} s; terminating")
            res["terminator"] = {"kind": "external_scheduled_session", "fire_at": ext}
        if pod_term:
            try:
                backend.schedule_terminator(iid, deadline + margin, a.run_id)
                res["terminator"] = {**res.get("terminator", {}), "kind": res.get("terminator", {}).get(
                    "kind", "pod_systemd_timer"), "pod_timer_fire_at": deadline + margin}
            except Exception as exc:  # noqa: BLE001
                if ext is None:
                    raise RuntimeError(f"terminator scheduling failed ({type(exc).__name__}: {exc}); "
                                       "terminating") from exc
                res["terminator"]["pod_timer_error"] = f"{type(exc).__name__}: {exc}"[:300]
        box = backend.start_box(iid, deadline)
        backend.setup_box(box)
        ctx["box"] = box
        done_s: list[float] = []
        for job in pending:
            est = PREDICT_EST_S if restorable(job, st) else (sum(done_s) / len(done_s) if done_s else EXTRACT_EST_S)
            if job.d038:
                est = 2 * EXTRACT_EST_S + PREDICT_EST_S
            if clock() + est + TEARDOWN_S > deadline:
                res["stopped_for_time"] = {"at_job": job.id, "left_s": round(deadline - clock())}
                break
            t0 = clock()
            res["jobs_run"].append(job.id)
            try:
                outcome = do_job(job, ctx)
            except (OverwriteRefusedError, ManifestConflictError) as exc:
                res["errors"][job.id] = f"{type(exc).__name__}: {exc}"[:1000]
                continue
            if outcome == "pass" and not job.d038:
                done_s.append(clock() - t0)
            if outcome == "stop":
                res["stop"] = f"D-038 gate failed on {job.id} (STOP, v2.md P4)"
                break
    except Exception as exc:  # noqa: BLE001 - always record and fall through to terminate
        res["error"] = f"{type(exc).__name__}: {exc}"[-4000:]
    finally:
        try:
            backend.stop_box(box)
        except Exception as exc:  # noqa: BLE001
            res.setdefault("teardown_errors", []).append(f"stop_box: {exc}"[:300])
        try:
            lg.terminate(iid, "job_done")
        except Exception as exc:  # noqa: BLE001
            res.setdefault("teardown_errors", []).append(f"terminate: {exc}"[:300])
        lg.reap()
        res["alive_after"] = lg._live(lg.list_ours())
        res["usd_spent_this_run"] = round(lg.spent_usd() - spent0, 4)
        try:
            backend.mirror_ledger(a.run_id)
        except Exception as exc:  # noqa: BLE001
            res.setdefault("teardown_errors", []).append(f"ledger mirror: {exc}"[:300])
    return _finish(res, run_dir, backend, store, jobs, p.get("superseded_run_ids") or [])


def _finish(res: dict, run_dir: Path, backend, store: Store, jobs: list[Job], superseded: list[str] = ()) -> tuple[int, dict]:
    st = load_state(backend, superseded)
    res["remaining"] = [j.id for j in jobs if not is_done(j, st)]
    res["n_done"] = len(jobs) - len(res["remaining"])
    res["n_jobs"] = len(jobs)
    try:
        res["revisions_sha256"] = st.revisions_sha256()
    except RuntimeError as exc:
        res["error"] = str(exc)
    failed = bool(res.get("error") or res["gate_failures"] or res["errors"] or res.get("stop")
                  or res.get("alive_after"))
    rc = EXIT_FAIL if failed else (EXIT_INCOMPLETE if res["remaining"] else EXIT_OK)
    res.setdefault("status", "failed" if failed else ("incomplete" if res["remaining"] else "complete"))
    res["exit_code"] = rc
    text = json.dumps(res, indent=1, sort_keys=True, default=str)
    (run_dir / "child_metrics.json").write_text(text)
    try:
        store.put_text(f"runs/{res['run_id']}/child_metrics.json", text)
    except Exception as exc:  # noqa: BLE001
        res.setdefault("teardown_errors", []).append(f"run record: {exc}"[:300])
    return rc, res


# ---------------------------------------------------------------- dry-run fakes (also used by the tests)
class FakeClock:
    def __init__(self, t0: float):
        self.t = float(t0)

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s

    def time(self) -> float:          # the `time` module shim for the fake lambda_gpu
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


class _FakeLambdaAPI:
    def __init__(self, clock):
        self.clock, self.inst, self.n = clock, {}, 0

    def __call__(self, method, path, body=None):
        if method == "GET" and path == "/instances":
            return {"data": [dict(v) for v in self.inst.values()]}
        if method == "GET" and path.startswith("/instances/"):
            return {"data": dict(self.inst[path.rsplit("/", 1)[1]])}
        if method == "GET" and path == "/ssh-keys":
            return {"data": [{"name": "yct-pod"}]}
        if method == "POST" and path == "/instance-operations/launch":
            self.n += 1
            iid = f"fake{self.n:04d}"
            self.inst[iid] = {"id": iid, "name": body["name"], "status": "active", "ip": None,
                              "touch_age": None}
            return {"data": {"instance_ids": [iid]}}
        if method == "POST" and path == "/instance-operations/terminate":
            for iid in body["instance_ids"]:
                self.inst[iid]["status"] = "terminated"
                self.inst[iid]["terminated_at"] = self.clock()
            return {"data": {}}
        raise AssertionError(f"unexpected Lambda API call {method} {path}")


class FakeLG:
    """infra/lambda_gpu.py itself (a private copy), with the Lambda API, the clock, prices, the owner budget
    and the ledger replaced: the dry run exercises the real launch/reap/sweep/terminate code."""

    def __init__(self, clock, ledger: Path | None = None):
        spec = importlib.util.spec_from_file_location(f"_lg_fake_{id(self)}", ROOT / "infra" / "lambda_gpu.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.api = _FakeLambdaAPI(clock)
        mod._req = self.api
        mod.time = clock
        mod.LEDGER = ledger or Path(tempfile.mkdtemp(prefix="yct_fake_ledger_")) / "ledger.jsonl"
        mod.types = lambda: {"gpu_1x_a100_sxm4": {"usd_per_hour": 1.99, "regions": ["eu-central-1"]}}
        mod._ssm_budget = lambda: 200.0
        mod.fetch_touch_age = lambda inst: self.api.inst[inst["id"]].get("touch_age")
        self.mod, self.clock = mod, clock
        self.launched: list[str] = []
        orig = mod.launch

        def launch(*args, **kw):
            rec = orig(*args, **kw)
            self.launched.append(rec["id"])
            return rec

        mod.launch = launch

    def __getattr__(self, name):
        return getattr(self.mod, name)

    @property
    def status(self) -> dict:
        return {k: v["status"] for k, v in self.api.inst.items()}

    @property
    def deadline(self) -> dict:
        return {k: self.mod.name_times(v["name"])[1] for k, v in self.api.inst.items()}

    @property
    def terminated_at(self) -> dict:
        return {k: v.get("terminated_at") for k, v in self.api.inst.items()}

    def add_instance(self, base: str, age_s: float, touch_age: float | None, hours: float = 3.5) -> str:
        t0 = self.clock() - age_s
        self.api.n += 1
        iid = f"other{self.api.n:04d}"
        self.api.inst[iid] = {"id": iid, "name": f"{base}-t{int(t0)}-dl{int(t0 + hours * 3600)}",
                              "status": "active", "ip": None, "touch_age": touch_age}
        return iid


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class DryRunBackend:
    """Local directories for S3 (s3/), the pod (pod/) and each box (boxes/<iid>/). The box runs the real
    yct.tribe_run.feature_cache.run_cached with a synthetic extractor/predictor and the real cache_archive;
    the clock advances by the measured per-step times. Faults (self.faults): job id -> crash_after_entry |
    two_audio_chunks | rerun_differs; "schedule_terminator" -> fail."""

    T_SETUP, T_EXTRACT, T_PREDICT = 600.0, 330.0, 60.0

    def __init__(self, root: Path, cfg: dict, clock):
        self.root, self.cfg, self.clock = Path(root), cfg, clock
        self.s3, self.pod = self.root / "s3", self.root / "pod"
        self.rev_extra: dict = {}          # test hook: extra revisions (simulates a stack change, BUG-029)
        self.s3.mkdir(parents=True, exist_ok=True)
        self.pod.mkdir(parents=True, exist_ok=True)
        self.faults: dict[str, str] = {}
        self.terminator_ok = True
        self.terminators: list[tuple[str, float]] = []
        self._extr: Counter = Counter()
        self.box_pred_sha: dict[str, str] = {}

    # -- S3
    def s3_list(self, prefix: str) -> dict[str, int]:
        return {p.relative_to(self.s3).as_posix(): p.stat().st_size for p in sorted(self.s3.rglob("*"))
                if p.is_file() and p.relative_to(self.s3).as_posix().startswith(prefix)}

    def s3_get_text(self, key: str) -> str | None:
        p = self.s3 / key
        return p.read_text() if p.exists() else None

    def s3_put_text(self, key: str, text: str) -> None:
        p = self.s3 / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def s3_upload(self, pod_path: str, key: str) -> None:
        p = self.s3 / key
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pod_path, p)

    def s3_sha(self, key: str) -> str:
        return _sha_file(self.s3 / key)

    # -- pod
    def git_sha(self) -> str:
        return "dryrun"

    def preflight(self, git_sha: str) -> None:
        pass

    def inputs(self, video_ids: list[str]) -> dict:
        out: dict = {}
        for vid in video_ids:
            for track in ("t1", "t3"):
                if vid not in self.cfg["p4"][f"run_set_{track}"]:
                    continue
                stem = hashlib.sha256(f"{vid}.{track}".encode()).hexdigest()[:16]
                d = self.pod / "norm" / track
                d.mkdir(parents=True, exist_ok=True)
                clip = d / f"{stem}.mp4"
                if not clip.exists():
                    clip.write_bytes(f"synthetic {vid} {track} ".encode() * 40)
                    (d / f"{stem}.tsv").write_text("text\tstart\tduration\tsequence_id\tsentence\n"
                                                   + "".join(f"w{i}\t{i}.0\t0.3\t0\ts\n" for i in range(20)))
                dur = 42.8 if vid in self.cfg["p4"]["t1_excluded"] else 58.0
                out.setdefault(vid, {})[track] = {"stem": stem, "path": str(clip), "sha256": _sha_file(clip),
                                                  "tsv_sha256": _sha_file(clip.with_suffix(".tsv")),
                                                  "duration_s": dur}
        return out

    def terminator_available(self) -> bool:
        return self.terminator_ok

    def schedule_terminator(self, iid: str, fire_at: float, run_id: str) -> None:
        if self.faults.get("schedule_terminator") == "fail":
            raise RuntimeError("systemd-run failed")
        self.terminators.append((iid, fire_at))

    def mirror_ledger(self, run_id: str) -> None:
        pass

    # -- box
    def start_box(self, iid: str, deadline: float) -> dict:
        d = self.root / "boxes" / iid
        (d / "fc").mkdir(parents=True, exist_ok=True)
        return {"iid": iid, "dir": d, "staged": {}}

    def setup_box(self, box: dict) -> None:
        self.clock.advance(self.T_SETUP)

    def stop_box(self, box: dict | None) -> None:
        pass

    def stage(self, box: dict, job: Job, inp: dict, restore: dict | None) -> None:
        from yct.tribe_run import cache_archive as ca

        d = box["dir"] / "clips" / job.track
        d.mkdir(parents=True, exist_ok=True)
        clip = d / f"{inp['stem']}.mp4"
        shutil.copy2(inp["path"], clip)
        shutil.copy2(Path(inp["path"]).with_suffix(".tsv"), clip.with_suffix(".tsv"))
        box["staged"][job.id] = clip
        if restore:
            media = sorted((self.pod / "cache_media").glob("*"))
            ca.restore_entry(self.s3 / restore["tar_key"], (self.s3 / restore["sums_key"]).read_text(),
                             [*media, clip], box["dir"] / "fc")

    def extractions_per_job(self) -> dict[str, int]:
        return dict(self._extr)

    @property
    def n_extractions(self) -> int:
        return sum(self._extr.values())

    def run_job(self, box: dict, job: Job, inp: dict, mode: str) -> tuple[int, dict | None]:
        import numpy as np

        from yct.tribe_run.feature_cache import FeatureStore, run_cached

        clip = box["staged"][job.id]
        rng = np.random.default_rng(abs(hash((job.id, mode, self.clock()))) % 2**32)
        n_t = 43 if inp["duration_s"] < 50 else 58
        fault = self.faults.get(job.id)

        def extract(video: Path, feat: Path) -> None:
            self._extr[job.id] += 1
            self.clock.advance(self.T_EXTRACT)
            base = np.frombuffer(video.read_bytes()[:64].ljust(64, b"\0"), np.uint8).astype(np.float32)
            np.save(feat / "audio.npy", np.tile(base, (n_t, 1)) + 1e-4 * rng.standard_normal((n_t, 64)).astype(np.float32))
            video.with_suffix(".wav").write_bytes(b"RIFF synthetic " + video.read_bytes()[:32])

        def predict(video: Path, feat: Path):
            self.clock.advance(self.T_PREDICT)
            a = np.load(feat / "audio.npy").astype(np.float32)
            return np.repeat(a.mean(1, keepdims=True), 20484, axis=1).astype(np.float16), {}

        out = box["dir"] / "res" / (job.id + ("_rerun" if mode == "rerun" else ""))
        fresh = job.d038 and mode == "main"
        m = run_cached(clip, FeatureStore(box["dir"] / "fc"), extract, predict,
                       {"gpu": GPU_NAME, "bug018_word_fix": True, "bug018_word_end_clamp": WORD_END_CLAMP,
                        "backbones": {"dry": "run"}, **self.rev_extra}, out,
                       fresh_drift=fresh, offline=True, keep_fresh=f"{out}.fresh_feat" if fresh else None,
                       fresh_preds_out=f"{out}.fresh_pred.npy" if fresh else None)
        m.pop("aux")
        if mode == "rerun" and fault == "rerun_differs":
            m["pred_sha256"] = "f" * 64
        m.update({"duration_s": inp["duration_s"], "shape": m["pred_shape"], "finite": True, "TR_s": 1.0,
                  "T_within_1": abs(n_t - inp["duration_s"]) <= 1, "words_after_duration": 0,
                  "chunks": {"Audio": [[0.0, inp["duration_s"]]] * (2 if fault == "two_audio_chunks" else 1),
                             "Video": [[0.0, inp["duration_s"]]]},
                  "bug018_word_check": {"ok": True, "n_words": 20, "n_tsv_rows": 20, "bug018_fix": True},
                  "asr_called": False, "uvx_on_path": False, "pred_mean": 0.0, "pred_std": 1.0})
        if mode == "main":
            self.box_pred_sha[job.id] = m["pred_sha256"]
        return 0, m

    def collect(self, box: dict, job: Job, rec: dict) -> dict[str, tuple[str, str]]:
        from yct.tribe_run import cache_archive as ca

        d = self.pod / "p4" / "runs" / box["iid"] / job.id
        d.mkdir(parents=True, exist_ok=True)
        res = box["dir"] / "res"
        info = ca.archive_entry(box["dir"] / "fc", rec["cache_key"], d / "entry.tar")
        (d / "entry.FILES_SHA256SUMS").write_text(info["files_sha256sums"])
        ca.save_media(box["dir"] / "fc", rec["cache_key"], self.pod / "cache_media")
        shutil.copy2(res / f"{job.id}.npy", d / "pred.npy")
        (d / "segments.csv").write_text("tr_index,segment_start_s,segment_duration_s\n")
        files = {"entry_tar": d / "entry.tar", "entry_sums": d / "entry.FILES_SHA256SUMS",
                 "pred": d / "pred.npy", "segments": d / "segments.csv"}
        if job.d038:
            shutil.copy2(res / f"{job.id}.fresh_pred.npy", d / "fresh_pred.npy")
            shutil.make_archive(str(d / "fresh_feat"), "tar", res, f"{job.id}.fresh_feat")
            files.update({"fresh_pred": d / "fresh_pred.npy", "fresh_feat": d / "fresh_feat.tar"})
        return {k: (str(v), _sha_file(v)) for k, v in files.items()}

    def after_entry_sync(self, job: Job) -> None:
        if self.faults.get(job.id) == "crash_after_entry":
            raise RuntimeError(f"simulated driver crash after the entry sync of {job.id}")


# ---------------------------------------------------------------- real backend (EC2 pod + Lambda box)
class PodBackend:
    """Pod via SSM (infra/pod_exec.sh), box via ssh from the pod (scripts/gpu_p0_rerun.Box); small S3 text
    objects from this container (aws CLI), big files pod -> S3. Never prints secrets or transcript text."""

    def __init__(self, cfg: dict, run_id: str, run_dir: Path):
        sys.path.insert(0, str(ROOT / "scripts"))
        import gpu_p0_rerun as g

        self.g, self.cfg, self.run_id, self.run_dir = g, cfg, run_id, run_dir
        self.s3root = cfg["p4"]["s3_prefix"].rstrip("/")
        self.pod_dir = f"{POD_P4}/runs/{run_id}"
        self._stop = threading.Event()
        self._watcher = None
        self._pod_inputs: dict = {}
        g.SHIP = [*g.SHIP, "infra/gpu_deadman.sh"]

    # -- S3 (keys relative to the p4 prefix)
    def _aws(self, *args: str, inp: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
        env = {**os.environ, "AWS_DEFAULT_REGION": "eu-central-1"}
        return subprocess.run(["aws", *args], input=inp, capture_output=True, text=True, env=env, timeout=600,
                              check=check)

    def s3_list(self, prefix: str) -> dict[str, int]:
        bucket, _, root = self.s3root[5:].partition("/")
        r = self._aws("s3api", "list-objects-v2", "--bucket", bucket, "--prefix", f"{root}/{prefix}",
                      "--query", "Contents[].[Key,Size]", "--output", "json")
        rows = json.loads(r.stdout or "null") or []
        return {k[len(root) + 1:]: int(s) for k, s in rows}

    def s3_get_text(self, key: str) -> str | None:
        """Object text; None ONLY for 404/NoSuchKey. Anything else (403, throttling, network, 5xx, missing
        credentials, unknown) raises S3ReadError: the run fails closed (QA c2 N2)."""
        r = self._aws("s3", "cp", f"{self.s3root}/{key}", "-", check=False)
        if r.returncode == 0:
            return r.stdout
        if _NOT_FOUND.search(r.stderr or ""):
            return None
        raise S3ReadError(f"S3 read of {key} failed (rc {r.returncode}): {(r.stderr or '').strip()[-300:]}")

    def s3_put_text(self, key: str, text: str) -> None:
        self._aws("s3", "cp", "-", f"{self.s3root}/{key}", "--quiet", inp=text)

    def s3_upload(self, pod_path: str, key: str) -> None:
        self.g.pod(f"aws s3 cp --region eu-central-1 --quiet {pod_path} {self.s3root}/{key}", 1800)

    # -- pod
    def git_sha(self) -> str:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    def preflight(self, git_sha: str) -> None:
        self.g.pod(f"cd {REPO} && git fetch -q origin && git checkout -q {git_sha} && git rev-parse HEAD && "
                   f"mkdir -p {self.pod_dir} {POD_P4}/cache_media {POD_P4}/stage", 300)

    def inputs(self, video_ids: list[str]) -> dict:
        """Pod-only table: per video the T1/T3 clip path, its sha256 and the pinned transcript sha256."""
        self.g.pod(f"mkdir -p {self.pod_dir} && cd {REPO} && {PY} scripts/wave1_p2b_pod.py inputs "
                   f"{self.pod_dir}/inputs.csv", 300)
        script = f"""set -euo pipefail
cd {self.pod_dir}
{PY} - <<'PY'
import csv, hashlib, json
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()
want = set({json.dumps(video_ids)})
man = {{r[0]: r[1] for r in csv.reader(open('/work/yct/transcripts/manifest.csv')) if len(r) == 2}}
out = {{}}
for r in csv.DictReader(open('inputs.csv')):
    if r['video_id'] not in want:
        continue
    for track, stem, path in (('t1', r['content_id'], r['t1_path']), ('t3', r['t3_content_id'], r.get('t3_path', ''))):
        if stem and path:
            out.setdefault(r['video_id'], {{}})[track] = {{'stem': stem, 'path': path, 'sha256': sha(path),
                'tsv': '/work/yct/transcripts/' + stem + '.tsv', 'tsv_sha256': man.get(stem),
                'duration_s': float(r['duration_s'])}}
json.dump(out, open('p4_inputs.json', 'w'))
print(len(out))
PY
"""
        self._pod_bash(script, 1800)
        out = json.loads(self.g.pod_file(f"{self.pod_dir}/p4_inputs.json"))
        for vid, tracks in out.items():
            for t, v in tracks.items():
                if not v.get("tsv_sha256"):
                    raise SystemExit(f"no pinned transcript sha256 for {vid} {t}")
        self._pod_inputs = out
        return out

    def _pod_bash(self, script: str, timeout: int = 900) -> str:
        import base64

        b64 = base64.b64encode(script.encode()).decode()
        name = f"/tmp/yct_p4_{int(time.time() * 1000)}.sh"
        self.g.pod(f"echo {b64} | base64 -d > {name}", 120)
        return self.g.pod(f"bash {name}", timeout)

    def terminator_available(self) -> bool:
        out = self.g.pod("command -v systemd-run >/dev/null && aws ssm get-parameter --region eu-central-1 "
                         "--name /yct/lambda_api_key --with-decryption --query Parameter.Version --output text "
                         ">/dev/null 2>&1 && echo TERMINATOR_OK || echo TERMINATOR_NO", 120, check=False)
        return "TERMINATOR_OK" in out

    def schedule_terminator(self, iid: str, fire_at: float, run_id: str) -> None:
        from infra import lambda_gpu as lg

        out = self._pod_bash(lg.pod_terminator_script(iid, fire_at, time.time(), run_id, REPO), 300)
        if not out.strip().splitlines() or out.strip().splitlines()[-1].strip() == "0":
            raise RuntimeError("pod terminator timer not listed")

    def mirror_ledger(self, run_id: str) -> None:
        self.s3_put_text(f"ledger/{run_id}.jsonl", (ROOT / "infra" / "gpu_ledger.jsonl").read_text())

    # -- box
    def start_box(self, iid: str, deadline: float):
        from infra import lambda_gpu as lg

        g = self.g
        ip = None
        for _ in range(60):
            inst = lg._req("GET", f"/instances/{iid}")["data"]
            if inst.get("status") == "active" and inst.get("ip"):
                ip = inst["ip"]
                break
            time.sleep(20)
        if not ip:
            raise RuntimeError("instance never became active")
        box = g.Box(ip, self.pod_dir)
        for _ in range(30):
            if g.pod(f"{box.ssh} true && echo up", 120, check=False).strip().endswith("up"):
                break
            time.sleep(20)
        # dead-man FIRST (QA D3): before shipping code; hard cap + absolute launch deadline
        box.put_text((ROOT / "infra" / "gpu_deadman.sh").read_text(), "/home/ubuntu/gpu_deadman.sh")
        box.run(f"touch {TOUCH}; pgrep -f gpu_deadman.sh >/dev/null || (nohup bash ~/gpu_deadman.sh {TOUCH} "
                f"{DEADMAN_GRACE_S} {int(max(60, deadline - time.time()))} {int(deadline)} >/dev/null 2>&1 "
                "</dev/null &); sleep 1; pgrep -f gpu_deadman.sh >/dev/null && echo deadman_up")

        def _toucher() -> None:
            while not self._stop.wait(TOUCH_EVERY_S):
                try:
                    g.pod(f"{box.ssh} 'touch {TOUCH}'", 120, check=False)
                except Exception:  # noqa: BLE001 - a missed touch is covered by the grace period
                    pass

        threading.Thread(target=_toucher, daemon=True).start()
        g.ship_code(box, self.pod_dir)
        box.run(f"pgrep -f gpu_heartbeat.sh >/dev/null || (nohup bash {g.B}/infra/gpu_heartbeat.sh >/dev/null "
                "2>&1 </dev/null &); sleep 2; tail -1 ~/yct_heartbeat.log")
        self._watcher = subprocess.Popen([sys.executable, str(ROOT / "infra" / "lambda_gpu.py"), "watch"],
                                         env={**os.environ, "YCT_HB_VIA_POD": "1"},
                                         stdout=open(self.run_dir / "watch.log", "w"), stderr=subprocess.STDOUT)
        return box

    def setup_box(self, box) -> None:
        g = self.g
        g.pod("aws ssm get-parameter --region eu-central-1 --name /yct/hf_token --with-decryption "
              "--query Parameter.Value --output text | "
              f"{box.ssh} 'mkdir -p ~/.cache/huggingface && umask 077 && cat > ~/.cache/huggingface/token "
              "&& wc -c < ~/.cache/huggingface/token'", 300)
        box.start("setup", f"cp {g.B}/src/yct/tribe_run/remote_setup.sh {g.B}/; bash {g.B}/remote_setup.sh {g.B}\n"
                           f"nvidia-smi > {g.B}/nvidia_smi.txt\n")
        rc = box.wait("setup", 2700)
        if rc != 0:
            raise RuntimeError("setup failed:\n" + box.cat("~/steps/setup.log")[-3000:])
        gpu = box.run("nvidia-smi --query-gpu=name --format=csv,noheader | head -1").strip()
        if gpu != GPU_NAME:
            raise RuntimeError(f"GPU {gpu!r} != {GPU_NAME!r} (one GPU type for all of P4)")

    def stop_box(self, box) -> None:
        self._stop.set()
        if self._watcher is not None:
            time.sleep(5)
            self._watcher.terminate()

    def stage(self, box, job: Job, inp: dict, restore: dict | None) -> None:
        g, bdir = self.g, self.g.B
        d = f"{bdir}/clips/{job.track}"
        g.pod(f"[ \"$(sha256sum {inp['tsv']} | cut -d' ' -f1)\" = {inp['tsv_sha256']} ] && "
              f"cd $(dirname {inp['path']}) && tar cf - $(basename {inp['path']}) | {box.ssh} 'mkdir -p {d} && "
              f"tar xf - -C {d}' && cd /work/yct/transcripts && tar cf - {inp['stem']}.tsv | {box.ssh} "
              f"'tar xf - -C {d}'", 900)
        if inp["path"].rsplit("/", 1)[-1] != f"{inp['stem']}.mp4":
            box.run(f"cd {d} && mv $(basename {inp['path']}) {inp['stem']}.mp4")
        if restore:
            st = f"{POD_P4}/stage/{restore['cache_key']}"
            self._pod_bash(f"""set -euo pipefail
mkdir -p {st}/media
aws s3 cp --region eu-central-1 --quiet {self.s3root}/{restore['tar_key']} {st}/entry.tar
aws s3 cp --region eu-central-1 --quiet {self.s3root}/{restore['sums_key']} {st}/entry.sums
[ "$(sha256sum {st}/entry.tar | cut -d' ' -f1)" = {restore['tar_sha256']} ]
for h in $(grep -E '\\.(mp4|wav|mkv|mov)$' {st}/entry.sums | cut -d' ' -f1); do cp {POD_P4}/cache_media/$h.* {st}/media/ 2>/dev/null || true; done
tar cf - -C {st} . | {box.ssh} 'mkdir -p {bdir}/stage/{restore['cache_key']} && tar xf - -C {bdir}/stage/{restore['cache_key']}'
""", 1800)
            box.run(f"shopt -s nullglob; cd {bdir}; source venv/bin/activate; export PYTHONPATH={bdir}/src; "
                    f"S=stage/{restore['cache_key']}; "
                    f"python -m yct.tribe_run.cache_archive restore $S/entry.tar $S/entry.sums fc $S/media/* "
                    f"clips/{job.track}/{inp['stem']}.mp4", 1800)

    def run_job(self, box, job: Job, inp: dict, mode: str) -> tuple[int, dict | None]:
        g, bdir = self.g, self.g.B
        name = job.id + ("_rerun" if mode == "rerun" else "")
        extra = " --fresh-drift --keep-fresh" if (job.d038 and mode == "main") else ""
        step = name.replace(".", "_")
        box.start(step, f"""cd {bdir}; source venv/bin/activate; export PYTHONPATH={bdir}/src; mkdir -p res
python src/yct/tribe_run/run_clip.py --feature-cache fc --weights weights --out res/{name} \\
  --video clips/{job.track}/{inp['stem']}.mp4 --bug018-word-fix --qc-gate {job.track}{extra} > res/{name}.log 2>&1
""")
        rc = box.wait(step, 3 * 3600)
        txt = g.pod(f"{box.ssh} 'cat {bdir}/res/{name}.json 2>/dev/null || true' > {self.pod_dir}/{name}.raw.json; "
                    f"wc -c < {self.pod_dir}/{name}.raw.json", 300)
        if not txt.strip() or int(txt.strip().splitlines()[-1]) == 0:
            return rc, None
        raw = json.loads(g.pod_file(f"{self.pod_dir}/{name}.raw.json"))
        g.pod(f"rm -f {self.pod_dir}/{name}.raw.json", 60)   # raw json holds feature names (transcript text)
        return rc, raw

    def collect(self, box, job: Job, rec: dict) -> dict[str, tuple[str, str]]:
        bdir, key = self.g.B, rec["cache_key"]
        d = f"{self.pod_dir}/{job.id}"
        box.run(f"cd {bdir}; source venv/bin/activate; export PYTHONPATH={bdir}/src; "
                f"python -m yct.tribe_run.cache_archive archive fc {key} res/{job.id}.entry.tar > res/{job.id}.archive.json && "
                f"python -m yct.tribe_run.cache_archive save-media fc {key} res/{job.id}.media >/dev/null && "
                + (f"tar cf res/{job.id}.fresh_feat.tar -C res {job.id}.fresh_feat && " if job.d038 else "")
                + "true", 3600)
        names = {"entry_tar": f"{job.id}.entry.tar", "entry_sums": f"{job.id}.entry.tar.FILES_SHA256SUMS",
                 "pred": f"{job.id}.npy", "segments": f"{job.id}.segments.csv"}
        if job.d038:
            names.update({"fresh_pred": f"{job.id}.fresh_pred.npy", "fresh_feat": f"{job.id}.fresh_feat.tar"})
        files = " ".join(names.values())
        out = self._pod_bash(f"""set -euo pipefail
mkdir -p {d} {POD_P4}/cache_media
{box.ssh} 'cd {bdir}/res && tar cf - {files} {job.id}.media' | tar xf - -C {d}
cp -n {d}/{job.id}.media/* {POD_P4}/cache_media/ 2>/dev/null || true
cd {d} && sha256sum {files}
""", 3600)
        sums = {ln.split()[1]: ln.split()[0] for ln in out.splitlines() if len(ln.split()) == 2}
        return {k: (f"{d}/{v}", sums[v]) for k, v in names.items()}

    def after_entry_sync(self, job: Job) -> None:
        pass


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    from yct.config import load_config

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-hours", type=float, default=3.75)
    ap.add_argument("--usd-limit", type=float, default=10.0)
    ap.add_argument("--external-terminator-at", help="epoch or ISO time of a one-shot scheduled session that "
                    "runs `lambda_gpu.py reap-deadline --margin-s 0` (D-063 Q7), if the pod cannot")
    ap.add_argument("--limit", type=int, help="at most this many jobs in this session")
    ap.add_argument("--clear-stop", metavar="D-NNN", help="clear a latched D-038 STOP; the DECISIONS.md entry "
                    "D-NNN must exist and name every stopped run id")
    ap.add_argument("--dry-run", action="store_true", help="no network/GPU: fake Lambda, local pod/box/S3")
    ap.add_argument("--dry-run-root", help="directory for the dry-run pod/box/S3 (default: a temp dir)")
    a = ap.parse_args(argv)
    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p4_{int(time.time())}")
    cfg = load_config()
    args = SessionArgs(a.max_hours, a.usd_limit, _parse_when(a.external_terminator_at), run_dir.name, a.limit,
                       a.clear_stop)
    if a.dry_run:
        root = Path(a.dry_run_root or tempfile.mkdtemp(prefix="yct_p4_dry_"))
        clock = FakeClock(time.time())
        rc, res = run_session(args, cfg, FakeLG(clock, root / "ledger.jsonl"), DryRunBackend(root, cfg, clock),
                              clock, run_dir)
    else:
        if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
            raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
        from infra import lambda_gpu as lg

        os.environ["YCT_HB_VIA_POD"] = "1"   # box ssh (heartbeat, sweep touch age) goes through the pod
        rc, res = run_session(args, cfg, lg, PodBackend(cfg, run_dir.name, run_dir), time.time, run_dir)
    print(json.dumps({k: res.get(k) for k in ("status", "exit_code", "n_done", "n_jobs", "jobs_run", "error",
                                               "stop", "gate_failures", "errors")}, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
