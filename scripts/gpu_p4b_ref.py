#!/usr/bin/env python3
"""P4b reference-clip campaign driver (D-071; tickets T-REFRUN, T-ABL). Runs the frozen, pre-built 58 s
reference clips (refclips_manifest.json, sha256 == config controls.refclips_artifacts.manifest_sha256)
through the SAME session code as P4 (scripts/gpu_wave1_p4.run_session with a Campaign), under the sibling S3
root controls.refclips.s3_root. The P4 store (p4/) is only READ, to seed the revisions sha256 (one stack and
one GPU type for P4 and P4b); its manifest is never written.

    python scripts/run_with_provenance.py --run-id p4bref_<UTC> -- python scripts/gpu_p4b_ref.py \
        --clip-manifest PATH --external-terminator-at <ISO> [--max-hours 1.75] [--limit 3] [--ack-cap-80]
    python scripts/gpu_p4b_ref.py --dry-run [--limit N]          # no network, no GPU

Per session, before any launch (exit 1 = a human decides; 75 = re-run; 0 = every job synced and passed):
  * the clip manifest sha256 equals the frozen config value and its family counts equal controls.refclips;
  * the pod clips' sha256 (mp4 + tsv) equal the manifest (clips are never built or rebuilt on the box);
  * the external terminator fire time is new (re-armed on every retry; a time a launched session already used
    is refused) and fits the driver's deadline window;
  * the campaign baseline (entries/campaign_baseline.json) exists (written once, before session 1) and the
    $-cap guard (src/yct/tribe_run/ref_campaign.py, frozen controls.refclips.campaign_cap_usd) passes.
Job order = controls.refclips.job_order: the D-038 clips (GREY_CTRL_00, SPK_00, MOT_00), the families, the
audio-only and text-only conditions on the SPK clips (predicted from the full model's cache entry; the first 3
per condition get a Gate-1 cached rerun), then BURST and TALKFACE. Predictions: full/, audioonly/, textonly/.
The cfg is always load_config() (frozen keys; no overrides in this script).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from yct.config import load_config  # noqa: E402
from yct.predict.p4_index import p4_index  # noqa: E402
from yct.tribe_run import ref_campaign as rcmp  # noqa: E402


def _driver():
    if "gpu_wave1_p4" in sys.modules:
        return sys.modules["gpu_wave1_p4"]
    spec = importlib.util.spec_from_file_location("gpu_wave1_p4", ROOT / "scripts" / "gpu_wave1_p4.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_wave1_p4"] = mod
    spec.loader.exec_module(mod)
    return mod


p4 = _driver()

TRACK, QC_TRACK = "ref", "t1"            # 58 s single-chunk clips: the T1 per-clip gate rules
CONDITIONS = ("audioonly", "textonly")   # T-ABL (D-071 Q1; v2.md v2.8)
ABL_FAMILY, GATE1_N = "SPK", 3
D038_CLIPS = ("GREY_CTRL_00", "SPK_00", "MOT_00")   # D-071: session 1 = --limit 3 = these
POD_CLIPS = "/work/yct/p4b_ref/{version}/clips"


def clip_id(family: str, i: int) -> str:
    return f"{family}_{i:02d}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------- frozen inputs
def load_clip_manifest(text: str, cfg: dict) -> dict:
    want = cfg["controls"]["refclips_artifacts"]["manifest_sha256"]
    if not want:
        raise SystemExit("controls.refclips_artifacts.manifest_sha256 is not set "
                         "(T-STIM freezes it before upload)")
    if sha256_text(text) != want:
        raise SystemExit(f"clip manifest sha256 {sha256_text(text)[:12]} != frozen {want[:12]} (D-071 d)")
    m = json.loads(text)
    fams = cfg["controls"]["refclips"]["families"]
    got = Counter(c["family"] for c in m["clips"])
    if dict(got) != dict(fams):
        raise SystemExit(f"clip manifest family counts {dict(got)} != "
                         f"controls.refclips.families {dict(fams)}")
    ids = [c["clip_id"] for c in m["clips"]]
    if len(set(ids)) != len(ids) or any(c["clip_id"] != clip_id(c["family"], c["index"]) for c in m["clips"]):
        raise SystemExit("clip manifest ids must be unique and equal <FAMILY>_<index:02d>")
    return m


def plan_ref_jobs(cfg: dict, manifest: dict) -> list:
    clips = {c["clip_id"]: c for c in manifest["clips"]}
    jobs, seen = [], set()

    def add(j):
        if j.id not in seen:
            jobs.append(j)
            seen.add(j.id)

    for group in cfg["controls"]["refclips"]["job_order"]:
        for item in group:
            if item == "d038":
                for cid in D038_CLIPS:
                    add(p4.Job(cid, TRACK, True, qc_track=QC_TRACK))
            elif item in CONDITIONS:
                for n, cid in enumerate(sorted(c for c in clips if clips[c]["family"] == ABL_FAMILY)):
                    add(p4.Job(cid, TRACK, condition=item, qc_track=QC_TRACK, gate1_rerun=n < GATE1_N))
            else:
                for cid in sorted(c for c in clips if clips[c]["family"] == item):
                    add(p4.Job(cid, TRACK, qc_track=QC_TRACK))
    missing = set(clips) - {j.video_id for j in jobs if j.condition == "full"}
    if missing or not set(D038_CLIPS) <= set(clips):
        raise SystemExit(f"job_order does not cover every manifest clip: {sorted(missing)[:5]}")
    return jobs


def seed_revisions(p4_store, cfg: dict) -> str:
    """The P4 revisions sha256 (one stack + GPU for P4 and P4b), read through the single P4 loader."""
    idx = p4_index(p4_store, cfg["p4"])
    (rev,) = {r.revisions_sha256 for r in idx.values()}
    return rev


def check_inputs(inputs: dict, manifest: dict) -> None:
    bad = []
    for c in manifest["clips"]:
        inp = (inputs.get(c["clip_id"]) or {}).get(TRACK)
        if not inp or inp["sha256"] != c["mp4_sha256"] or inp["tsv_sha256"] != c["tsv_sha256"]:
            bad.append(c["clip_id"])
    if bad:
        raise SystemExit("pod clips differ from the frozen clip manifest (never rebuilt on the box): "
                         f"{bad[:5]}")


def check_terminator_rearmed(backend, ext: float | None) -> None:
    if ext is None:
        return
    for k in backend.s3_list("runs/"):
        if not k.endswith("/child_metrics.json"):
            continue
        r = json.loads(backend.s3_get_text(k) or "{}")
        used = (r.get("terminator") or {}).get("fire_at")
        if used is not None and abs(float(used) - ext) < 1:
            raise SystemExit(f"external terminator time {ext:.0f} was already used by {r.get('run_id')}: "
                             "arm a new one-shot terminator for this retry")


# ---------------------------------------------------------------- campaign cap (D-071 k)
def _ledger(lg) -> tuple[list[str], list[dict]]:
    path = Path(lg.LEDGER)
    lines = [x for x in (path.read_text().splitlines() if path.exists() else []) if x.strip()]
    return lines, [json.loads(x) for x in lines]


def ensure_baseline(backend, lg, cfg: dict, clock) -> dict:
    text = backend.s3_get_text(rcmp.BASELINE_KEY)
    if text is not None:
        return json.loads(text)
    lines, _ = _ledger(lg)
    base = rcmp.make_baseline(lines, lg.spent_usd(), clock())
    rcmp.check_baseline(lines, base, cfg["controls"]["refclips"]["ledger_name_prefix"])
    rcmp.write_baseline(backend, base)
    return base


def make_pre_launch(backend, lg, cfg: dict, clock, ack: bool):
    def pre_launch(price: float, max_hours: float) -> dict:
        base = json.loads(backend.s3_get_text(rcmp.BASELINE_KEY))
        lines, records = _ledger(lg)
        return rcmp.guard_launch(cfg, records, lines, base, price=price, max_hours=max_hours, now=clock(),
                                 ack=ack)
    return pre_launch


# ---------------------------------------------------------------- one session
def build_campaign(cfg: dict, manifest: dict, rev: str, backend, lg, clock, ack: bool):
    clips = {c["clip_id"]: c for c in manifest["clips"]}
    jobs = plan_ref_jobs(cfg, manifest)
    return p4.Campaign(
        name=cfg["controls"]["refclips"]["ledger_name_prefix"],
        pred_prefix_="full", entry_prefix_="entries_ref", d038_prefix_="d038_fresh",
        plan=lambda _cfg: jobs,
        expected=lambda job, inp: {"input_sha256": clips[job.video_id]["mp4_sha256"],
                                   "transcript_sha256": clips[job.video_id]["tsv_sha256"]},
        seed_rev_sha=rev, pre_launch=make_pre_launch(backend, lg, cfg, clock, ack))


def run_ref_session(a, cfg: dict, lg, backend, p4_store, clock, run_dir: Path, manifest_text: str,
                    ack: bool = False) -> tuple[int, dict]:
    manifest = load_clip_manifest(manifest_text, cfg)
    check_terminator_rearmed(backend, a.external_terminator_at)
    rev = seed_revisions(p4_store, cfg)
    check_inputs(backend.inputs([c["clip_id"] for c in manifest["clips"]]), manifest)
    ensure_baseline(backend, lg, cfg, clock)
    camp = build_campaign(cfg, manifest, rev, backend, lg, clock, ack)
    rc, res = p4.run_session(a, cfg, lg, backend, clock, run_dir, camp)
    res["clip_manifest_sha256"] = sha256_text(manifest_text)
    return rc, res


# ---------------------------------------------------------------- backends
def write_synthetic_clips(pod: Path, cfg: dict) -> str:
    """Dry run: deterministic stand-in clips + the manifest text describing them (never used for real)."""
    d = pod / "refclips"
    d.mkdir(parents=True, exist_ok=True)
    clips = []
    for fam, n in cfg["controls"]["refclips"]["families"].items():
        for i in range(int(n)):
            cid = clip_id(fam, i)
            mp4, tsv = d / f"{cid}.mp4", d / f"{cid}.tsv"
            if not mp4.exists():
                mp4.write_bytes(f"synthetic ref {cid} ".encode() * 40)
                tsv.write_text("text\tstart\tduration\tsequence_id\tsentence\n"
                               + "".join(f"w{k}\t{k}.0\t0.3\t0\ts\n" for k in range(20)))
            clips.append({"clip_id": cid, "family": fam, "index": i, "mp4_sha256": p4._sha_file(mp4),
                          "tsv_sha256": p4._sha_file(tsv), "duration_s": 58.0})
    return json.dumps({"version": cfg["controls"]["refclips"]["version"], "clips": clips},
                      sort_keys=True, indent=1)


class RefDryRunBackend(p4.DryRunBackend):
    def inputs(self, video_ids: list[str]) -> dict:
        d = self.pod / "refclips"
        out = {}
        for cid in video_ids:
            mp4 = d / f"{cid}.mp4"
            if not mp4.exists():
                continue
            out[cid] = {TRACK: {"stem": cid, "path": str(mp4), "sha256": p4._sha_file(mp4),
                                "tsv": str(mp4.with_suffix(".tsv")),
                                "tsv_sha256": p4._sha_file(mp4.with_suffix(".tsv")), "duration_s": 58.0}}
        return out


class RefPodBackend(p4.PodBackend):
    """Clips are uploaded once to the pod (T-STIM) and only hashed here; never built on the pod or box."""

    def inputs(self, video_ids: list[str]) -> dict:
        d = POD_CLIPS.format(version=self.cfg["controls"]["refclips"]["version"])
        out = self.g.pod(f"cd {d} && for c in {' '.join(video_ids)}; do [ -f $c.mp4 ] && [ -f $c.tsv ] && "
                         "echo $c $(sha256sum $c.mp4 | cut -d' ' -f1) $(sha256sum $c.tsv | cut -d' ' -f1); "
                         "done; true", 900)
        res = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] in video_ids:
                cid, s1, s2 = parts
                res[cid] = {TRACK: {"stem": cid, "path": f"{d}/{cid}.mp4", "sha256": s1,
                                    "tsv": f"{d}/{cid}.tsv", "tsv_sha256": s2, "duration_s": 58.0}}
        return res


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clip-manifest",
                    help="local refclips_manifest.json (sha256 must equal the frozen value)")
    ap.add_argument("--max-hours", type=float, default=1.75)
    ap.add_argument("--usd-limit", type=float, default=8.0)
    ap.add_argument("--external-terminator-at", help="epoch or ISO time of a NEW one-shot terminator session")
    ap.add_argument("--limit", type=int, help="at most this many jobs (session 1: 3, watched)")
    ap.add_argument("--ack-cap-80", action="store_true", help="acknowledge campaign spend >= the warn level")
    ap.add_argument("--dry-run", action="store_true", help="no network/GPU: fake Lambda, local pod/box/S3")
    ap.add_argument("--dry-run-root", help="directory for the dry-run pod/box/S3 (default: a temp dir)")
    a = ap.parse_args(argv)
    cfg = load_config()
    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p4bref_{int(time.time())}")
    args = p4.SessionArgs(a.max_hours, a.usd_limit, p4._parse_when(a.external_terminator_at), run_dir.name,
                          a.limit)
    if a.dry_run:
        raise SystemExit("--dry-run needs a test cfg with a manifest sha (see tests/test_gpu_p4b_ref.py); "
                         "this CLI only runs the frozen config")
    if not a.clip_manifest:
        raise SystemExit("--clip-manifest is required")
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    from infra import lambda_gpu as lg

    os.environ["YCT_HB_VIA_POD"] = "1"
    backend = RefPodBackend(cfg, run_dir.name, run_dir, s3root=cfg["controls"]["refclips"]["s3_root"])
    p4_store = p4.PodBackend(cfg, run_dir.name + "_p4read", Path(tempfile.mkdtemp()))
    rc, res = run_ref_session(args, cfg, lg, backend, p4_store, time.time, run_dir,
                              Path(a.clip_manifest).read_text(), ack=a.ack_cap_80)
    keys = ("status", "exit_code", "n_done", "n_jobs", "jobs_run", "error", "stop", "gate_failures", "errors",
            "pre_launch")
    print(json.dumps({k: res.get(k) for k in keys}, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
