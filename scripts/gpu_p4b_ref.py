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
from yct.tribe_run import launch_checks as lc  # noqa: E402
from yct.tribe_run import ref_campaign as rcmp  # noqa: E402
from yct.tribe_run import ref_manifest as rm  # noqa: E402


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
def load_clip_manifest(text: str, cfg: dict, nat_tsv_text: str | None = None) -> dict:
    """The frozen manifest (sha on the raw text BEFORE parsing), read through the pure read-only adapter
    (council refcampaign U1); the NAT tsv shas come from the D-091 sidecar, itself sha-checked against
    controls.refclips_artifacts.nat_tsv_manifest_sha256 (U2)."""
    art = cfg["controls"]["refclips_artifacts"]
    want = art["manifest_sha256"]
    if not want:
        raise SystemExit("controls.refclips_artifacts.manifest_sha256 is not set "
                         "(T-STIM freezes it before upload)")
    if sha256_text(text) != want:
        raise SystemExit(f"clip manifest sha256 {sha256_text(text)[:12]} != frozen {want[:12]} (D-071 d)")
    side = None
    if nat_tsv_text is not None:
        sw = art.get("nat_tsv_manifest_sha256")
        if not sw or sha256_text(nat_tsv_text) != sw:
            raise SystemExit("NAT tsv sidecar sha256 != controls.refclips_artifacts.nat_tsv_manifest_sha256 "
                             "(D-091)")
        side = json.loads(nat_tsv_text)
    m = rm.adapt(json.loads(text), side)
    fams = cfg["controls"]["refclips"]["families"]
    got = Counter(c["family"] for c in m["clips"])
    if dict(got) != dict(fams):
        raise SystemExit(f"clip manifest family counts {dict(got)} != "
                         f"controls.refclips.families {dict(fams)}")
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
        elif not isinstance(inp.get("duration_s"), int | float):
            bad.append(f"{c['clip_id']} (no measured duration)")
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


def n_done_full(backend) -> int:
    """Completed full-model jobs in this campaign's manifest (gate passed, no condition): the U4 count."""
    rows = [json.loads(x) for x in (backend.s3_get_text("manifest.jsonl") or "").splitlines() if x.strip()]
    return len({r["job"] for r in rows if r.get("gate_pass") and r.get("condition", "full") == "full"})


def projection_or_refuse(cfg: dict, records: list[dict], price: float, max_hours: float, now: float,
                         backend) -> dict | None:
    """Council refcampaign U4 (D-091), fail closed: the main-campaign projection is part of every pre-launch
    record. controls.refclips_d091 unfrozen -> refusal (exit 1), never a skipped projection. A cfg without
    the block at all (schema-required in config.yaml, so only a pre-D-091 test fixture) keeps the D-071
    rule."""
    if "refclips_d091" not in cfg["controls"]:
        return None
    if not rcmp._frozen(cfg, "controls.refclips_d091"):
        raise rcmp.CampaignCapError("controls.refclips_d091 is not frozen: the D-091 projection cannot be "
                                    "computed, launch refused (fail closed)")
    return rcmp.main_projection(cfg, records, price=price, max_hours=max_hours, now=now,
                                n_done_full=n_done_full(backend))


def make_pre_launch(backend, lg, cfg: dict, clock, ack: bool):
    def pre_launch(price: float, max_hours: float) -> dict:
        base = json.loads(backend.s3_get_text(rcmp.BASELINE_KEY))
        lines, records = _ledger(lg)
        guard = rcmp.guard_launch(cfg, records, lines, base, price=price, max_hours=max_hours, now=clock(),
                                  ack=ack)
        guard["projection"] = projection_or_refuse(cfg, records, price, max_hours, clock(), backend)
        guard["baseline_sha256"] = sha256_text(json.dumps(base, sort_keys=True))
        return guard
    return pre_launch


def check_launch_gate(gate: dict, lg) -> dict:
    """Council refcampaign U5: launch only from the pushed CI-green HEAD, with a committed L4 ledger
    reconciliation record matching the ledger now, and no live yct-* instance (shared launch_checks)."""
    lc.check_commit(gate["head"], gate.get("ci_green_sha"), gate["pushed"])
    lc.check_reconcile(gate.get("recon"), lg)
    if lg._live(lg.list_ours()):
        raise lc.Refused("a yct-* instance is alive: one instance at a time")
    return {"head": gate["head"], "ci_green_sha": gate["ci_green_sha"],
            "reconcile_ledger_sha256": gate["recon"]["ledger_sha256"]}


def gpu_price_or_none(lg, itype: str) -> float | None:
    """Check-only price (BUG-047: a missing type is no capacity, never a KeyError); the launch itself uses
    p4.run_session's own capacity path (exit 75)."""
    avail = lg.types()
    return avail[itype]["usd_per_hour"] if itype in avail else None


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


def _p4_manifest_sha(p4_store) -> str | None:
    t = p4_store.s3_get_text("manifest.jsonl")
    return None if t is None else sha256_text(t)


def run_ref_session(a, cfg: dict, lg, backend, p4_store, clock, run_dir: Path, manifest_text: str,
                    ack: bool = False, nat_tsv_text: str | None = None, gate: dict | None = None,
                    check_only: bool = False) -> tuple[int, dict]:
    """gate: {head, ci_green_sha, pushed, recon}; main() always passes it (council refcampaign U5).
    check_only: every pre-launch check against the real pod/S3/ledger, then return without launching."""
    manifest = load_clip_manifest(manifest_text, cfg, nat_tsv_text)
    gate_rec = check_launch_gate(gate, lg) if gate is not None else None
    check_terminator_rearmed(backend, a.external_terminator_at)
    rev = seed_revisions(p4_store, cfg)
    check_inputs(backend.inputs([c["clip_id"] for c in manifest["clips"]]), manifest)
    p4_before = _p4_manifest_sha(p4_store)
    if check_only:
        text = backend.s3_get_text(rcmp.BASELINE_KEY)
        lines, records = _ledger(lg)
        base = json.loads(text) if text is not None else None
        if base is not None:
            rcmp.check_baseline(lines, base, cfg["controls"]["refclips"]["ledger_name_prefix"])
        price = gpu_price_or_none(lg, cfg["p4"]["gpu_type"])
        proj = None if price is None else projection_or_refuse(cfg, records, price, a.max_hours, clock(),
                                                                backend)
        return 0, {"status": "check_only", "n_clips": len(manifest["clips"]), "launch_gate": gate_rec,
                   "baseline": None if base is None else {**base, "sha256_of_record":
                                                          sha256_text(json.dumps(base, sort_keys=True))},
                   "price_usd_per_hour": price, "projection": proj, "p4_manifest_sha256": p4_before,
                   "revisions_sha256": rev, "plan_first3": [j.id for j in plan_ref_jobs(cfg, manifest)[:3]],
                   "clip_manifest_sha256": sha256_text(manifest_text)}
    ensure_baseline(backend, lg, cfg, clock)
    camp = build_campaign(cfg, manifest, rev, backend, lg, clock, ack)
    rc, res = p4.run_session(a, cfg, lg, backend, clock, run_dir, camp)
    res["clip_manifest_sha256"] = sha256_text(manifest_text)
    res["launch_gate"] = gate_rec
    p4_after = _p4_manifest_sha(p4_store)            # D-071 (e): the P4 store is read only
    res["p4_manifest_sha256"] = {"before": p4_before, "after": p4_after}
    if p4_after != p4_before:
        res["stop"] = "the P4 manifest.jsonl changed during a reference session (D-071 e)"
        rc = p4.EXIT_FAIL
    return rc, res


# ---------------------------------------------------------------- backends
SYNTH_DURATION_S = 58.0   # dry run ONLY: synthetic bytes cannot be probed; the pod backend measures ffprobe


def write_synthetic_clips(pod: Path, cfg: dict) -> str:
    """Dry run: deterministic stand-in clips + the manifest text describing them, in the FROZEN manifest
    schema (family, i, name, sha256{mp4,tsv}) read through the same adapter (never used for real)."""
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
            clips.append({"family": fam, "i": i, "name": cid.lower(),
                          "sha256": {"mp4": p4._sha_file(mp4), "tsv": p4._sha_file(tsv)}})
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
                                "tsv_sha256": p4._sha_file(mp4.with_suffix(".tsv")),
                                "duration_s": SYNTH_DURATION_S}}
        return out


def pod_clips_dir(cfg: dict) -> str:
    d = POD_CLIPS.format(version=cfg["controls"]["refclips"]["version"])
    up = cfg["controls"].get("refclips_d091", {}).get("upload", {}).get("pod_dir")
    if up is not None and up.rstrip("/") != d:
        raise SystemExit(f"pod clip dir {d} != refclips_d091.upload.pod_dir {up}")
    return d


def inputs_cmd(d: str, video_ids: list[str]) -> str:
    """One pod command: per clip, the mp4 and tsv sha256 and the ffprobe-measured duration (U1b)."""
    return (f"cd {d} && for c in {' '.join(video_ids)}; do [ -f $c.mp4 ] && [ -f $c.tsv ] && "
            "echo $c $(sha256sum $c.mp4 | cut -d' ' -f1) $(sha256sum $c.tsv | cut -d' ' -f1) "
            "$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $c.mp4); done; true")


def parse_inputs(out: str, video_ids: list[str], d: str) -> dict:
    res = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] not in video_ids:
            continue
        cid, s1, s2, dur = parts
        try:
            dur_s = float(dur)
        except ValueError:
            continue           # no measured duration -> check_inputs refuses the clip
        res[cid] = {TRACK: {"stem": cid, "path": f"{d}/{cid}.mp4", "sha256": s1, "tsv": f"{d}/{cid}.tsv",
                            "tsv_sha256": s2, "duration_s": dur_s}}
    return res


class RefPodBackend(p4.PodBackend):
    """Clips are uploaded once to the pod (D-091 U3) and only hashed + probed here; never built."""

    def inputs(self, video_ids: list[str]) -> dict:
        d = pod_clips_dir(self.cfg)
        return parse_inputs(self.g.pod(inputs_cmd(d, video_ids), 1800), video_ids, d)


# ---------------------------------------------------------------- CLI
RECONCILE_PATH = "data/refstim/ledger_reconcile_ref.json"     # committed L4 record (D-091 U5)
NAT_TSV_PATH = "data/refstim/nat_tsv_manifest.json"


def _git(*args: str) -> str:
    import subprocess

    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clip-manifest",
                    help="local refclips_manifest.json (sha256 must equal the frozen value)")
    ap.add_argument("--nat-tsv", default=str(ROOT / NAT_TSV_PATH),
                    help="the D-091 NAT tsv sidecar (sha256 must equal the frozen value)")
    ap.add_argument("--max-hours", type=float, default=1.75)
    ap.add_argument("--usd-limit", type=float, default=8.0)
    ap.add_argument("--external-terminator-at", help="epoch or ISO time of a NEW one-shot terminator session")
    ap.add_argument("--ci-green-sha", help="the commit whose CI run is green; must equal HEAD (U5)")
    ap.add_argument("--limit", type=int, help="at most this many jobs (session 1: 3, watched)")
    ap.add_argument("--ack-cap-80", action="store_true", help="acknowledge campaign spend >= the warn level")
    ap.add_argument("--reconcile-only", action="store_true",
                    help=f"write the L4 ledger reconciliation record to {RECONCILE_PATH}, then exit")
    ap.add_argument("--check-only", action="store_true",
                    help="every pre-launch check against the real pod/S3/ledger; no launch")
    ap.add_argument("--dry-run", action="store_true", help="no network/GPU: fake Lambda, local pod/box/S3")
    ap.add_argument("--dry-run-root", help="directory for the dry-run pod/box/S3 (default: a temp dir)")
    a = ap.parse_args(argv)
    cfg = load_config()
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    if a.dry_run:
        raise SystemExit("--dry-run needs a test cfg with a manifest sha (see tests/test_gpu_p4b_ref.py); "
                         "this CLI only runs the frozen config")
    from infra import lambda_gpu as lg

    if a.reconcile_only:
        rec = lc.reconcile(lg, cfg, time.time)
        (ROOT / RECONCILE_PATH).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))
        return 0
    if not a.clip_manifest:
        raise SystemExit("--clip-manifest is required")
    if not a.check_only and (not a.external_terminator_at or not a.ci_green_sha):
        raise SystemExit("--external-terminator-at and --ci-green-sha are required for a launch")
    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p4bref_{int(time.time())}")
    args = p4.SessionArgs(a.max_hours, a.usd_limit, p4._parse_when(a.external_terminator_at), run_dir.name,
                          a.limit)
    head = _git("rev-parse", "HEAD")
    rp = ROOT / RECONCILE_PATH
    gate = {"head": head, "ci_green_sha": a.ci_green_sha or (head if a.check_only else None),
            "pushed": bool(_git("branch", "-r", "--contains", head)),
            "recon": json.loads(rp.read_text()) if rp.exists() else None}
    os.environ["YCT_HB_VIA_POD"] = "1"
    backend = RefPodBackend(cfg, run_dir.name, run_dir, s3root=cfg["controls"]["refclips"]["s3_root"])
    p4_store = p4.PodBackend(cfg, run_dir.name + "_p4read", Path(tempfile.mkdtemp()))
    rc, res = run_ref_session(args, cfg, lg, backend, p4_store, time.time, run_dir,
                              Path(a.clip_manifest).read_text(), ack=a.ack_cap_80,
                              nat_tsv_text=Path(a.nat_tsv).read_text(), gate=gate, check_only=a.check_only)
    if a.check_only:
        print(json.dumps(res, default=str, indent=1, sort_keys=True))
        return rc
    keys = ("status", "exit_code", "n_done", "n_jobs", "jobs_run", "error", "stop", "gate_failures", "errors",
            "pre_launch", "p4_manifest_sha256")
    print(json.dumps({k: res.get(k) for k in keys}, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
