#!/usr/bin/env python3
"""T-NAT0 session 0 (D-075 §3): N1 (faster-whisper language ID) + N2 (pyannote 3.1) + P2b (pinned WhisperX)
over the 40-candidate NAT buffer on ONE gpu_1x_a100_sxm4, then N3 (P3 face_present_crop over W, pod CPU)
and the selection of the first nat_n (15) passes. NO TRIBE job runs in session 0.

    python scripts/run_with_provenance.py --run-id p4bnat0_<UTC> -- python scripts/gpu_p4b_nat0.py \
        --external-terminator-at <ISO> --ci-green-sha <sha> [--max-hours 1.75] [--usd-limit 8] [--ack-cap-80]

Every check below runs BEFORE the launch and refuses with exit 1 (a human decides):
  * frozen: controls.refclips_auto, the NAT snapshot sha and the three pyannote mirror shas (set + frozen
    rows);
  * --max-hours <= p4.launcher_max_hours (1.75); --usd-limit <= 8 (D-071 k); price * max_hours <= usd-limit;
  * a driver-independent external terminator between planned deadline + p4.terminator_margin_s and + 1 h more,
    never a fire time an earlier session already used (re-armed on every retry);
  * the code is the pushed, CI-green commit: HEAD == --ci-green-sha and HEAD is on the remote branch;
  * the L4 ledger reconciliation record (data/refstim/ledger_reconcile_nat0.json, written by
    --reconcile-only and committed) matches the ledger now: no open launch, no live yct-* instance;
  * the pod NAT CPU stage has ended and the committed NAT log is the pod's log byte for byte;
  * the buffer is complete: exactly cpu_buffer (40) CPU passes, or a short buffer with the logged
    snapshot_exhausted record (council D-082); no session-0 row logged yet;
  * the campaign baseline (entries/campaign_baseline.json) is written ONCE, before the first yct-p4b-ref
    launch (refused if any yct-p4b-ref instance predates it), and the $75 cap guard
    (ref_campaign.guard_launch) passes.
Exit codes (as P4): 0 = selection done (nat_n passes logged); 75 = re-run (no capacity, or the box failed
before any result: nothing logged); 1 = a human decides (preflight refusal, < nat_n passes = STOP to the
owner, or any post-session error). The instance is always terminated (finally) and the box carries the
dead-man switch.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from yct.config import load_config  # noqa: E402
from yct.curate import natstim as ns  # noqa: E402
from yct.curate import refstim_auto as ra  # noqa: E402


def _ref():
    if "gpu_p4b_ref" in sys.modules:
        return sys.modules["gpu_p4b_ref"]
    spec = importlib.util.spec_from_file_location("gpu_p4b_ref", ROOT / "scripts" / "gpu_p4b_ref.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gpu_p4b_ref"] = mod
    spec.loader.exec_module(mod)
    return mod


ref = _ref()
USD_LIMIT_MAX = 8.0                       # D-071 (k): --usd-limit 8 per session
TERMINATOR_MAX_LATE_S = 3600
SESSION = "nat0"
PYANNOTE_KEYS = ("pyannote_diarization_sha256", "pyannote_segmentation_sha256", "pyannote_embedding_sha256",
                 "pyannote_plda_sha256")                       # plda: D-082 draft (BUG-040)
STEPS = ("setup_wx", "push_buffer", "nat0", "asr")     # the only box steps: no TRIBE job


class Refused(SystemExit):
    """Exit 1 before any launch: a human decides."""


def check_frozen(cfg: dict, k: int = 0) -> None:
    rows = {r["key"] for r in cfg.get("frozen") or []}
    need = ["controls.refclips_auto", "controls.refclips_d082",
            "controls.refclips_artifacts.nat_snapshot_sha256"] + \
        [f"controls.refclips_auto_artifacts.{k}" for k in PYANNOTE_KEYS] + \
        (["controls.refclips_d084"] if k >= 1 else [])          # D-084: continuation sessions
    missing = [k for k in need if k not in rows]
    unset = [k for k in PYANNOTE_KEYS if not cfg["controls"]["refclips_auto_artifacts"].get(k)]
    if missing or unset:
        raise Refused(f"session 0 refused: not frozen {missing}; pyannote shas not set {unset}")


def check_limits(cfg: dict, max_hours: float, usd_limit: float, price: float) -> None:
    lim = float(cfg["p4"]["launcher_max_hours"])
    if max_hours > lim:
        raise Refused(f"--max-hours {max_hours} > p4.launcher_max_hours {lim}")
    if usd_limit > USD_LIMIT_MAX:
        raise Refused(f"--usd-limit {usd_limit} > {USD_LIMIT_MAX} (D-071 k)")
    if price * max_hours > usd_limit:
        raise Refused(f"{price} $/h * {max_hours} h exceeds --usd-limit {usd_limit}")


def check_terminator(cfg: dict, store, ext: float | None, now: float, max_hours: float) -> None:
    if ext is None:
        raise Refused("no --external-terminator-at: arm a one-shot terminator session at deadline + 15 min "
                      "running `python infra/lambda_gpu.py reap-deadline --margin-s 0` first")
    planned, margin = now + max_hours * 3600, float(cfg["p4"]["terminator_margin_s"])
    if not planned + margin <= ext <= planned + margin + TERMINATOR_MAX_LATE_S:
        raise Refused(f"external terminator at {ext:.0f} must fire between planned deadline + {margin:.0f} s "
                      f"({planned + margin:.0f}) and + {TERMINATOR_MAX_LATE_S} s more")
    try:
        ref.check_terminator_rearmed(store, ext)
    except SystemExit as exc:
        raise Refused(str(exc)) from None


def check_commit(head: str, ci_green_sha: str | None, pushed: bool) -> None:
    if not ci_green_sha or head != ci_green_sha:
        raise Refused(f"HEAD {head[:12]} is not the CI-green commit {str(ci_green_sha)[:12]} (D-071 k)")
    if not pushed:
        raise Refused(f"HEAD {head[:12]} is not on the remote branch (launch only from a pushed commit)")


def check_session_k(cfg: dict, log: list[dict], k: int) -> list[str]:
    """D-084 continuation session k >= 1: sessions 0..k-1 logged and k not; k <= max_sessions; the selection
    still incomplete; buffer k complete and none of its ids evaluated before."""
    d = cfg["controls"]["refclips_d084"]
    done = ns.sessions_logged(log)
    if k in done:
        raise Refused(f"session {k} rows are already logged (a logged candidate is never re-evaluated)")
    if done != list(range(k)):
        missing = [j for j in range(k) if j not in done]
        raise Refused(f"session {missing[0] if missing else k - 1} not logged before session {k} "
                      f"(logged: {done})")
    if k > d["max_sessions"]:
        raise Refused(f"session {k} > max_sessions {d['max_sessions']}: STOP to the owner")
    need = cfg["controls"]["refclips"]["nat_n"]
    buf = ns.buffer_ids(log, cfg, k)
    # council D-084 (biostat): the overlap check runs before the selection, whose gap check would otherwise
    # always pre-empt it for a buffer-k id evaluated out of order
    seen = {r["t1_name"] for r in ns.gpu_rows(log)}
    again = [i for i in buf if i in seen]
    if again:
        raise Refused(f"NAT buffer {k} ids already evaluated: {again[:5]}")
    try:
        sel = ns.nat_selection(log, cfg)
    except ra.StopError as exc:
        raise Refused(str(exc)) from None
    if len(sel) >= need:
        raise Refused(f"the NAT selection is complete ({need} passes): no session {k}")
    if not buf:
        raise Refused(f"NAT buffer {k} is empty: run the CPU stage (--buffers {k + 1}) first")
    per = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]
    if not ns.buffer_complete(log, cfg, k):
        raise Refused(f"NAT buffer {k} holds {len(buf)} of {per} CPU passes and the log has no matching "
                      "snapshot_exhausted record: finish the CPU stage first")
    return buf


def check_projection(cfg: dict, lg, *, price: float, max_hours: float, now: float, k: int) -> dict | None:
    """Council D-084 (watchdog): before each continuation session k >= 1, restate the D-071 (k) campaign
    projection = campaign spend so far + the main reference campaign's plan (not yet started) + the D-085
    TALKFACE session's worst case + this session's worst case (price x max_hours). Over the cap -> STOP to
    the owner; NAT sessions never eat the main campaign's headroom. Valid only while no non-NAT, non-TALKFACE
    yct-p4b-ref launch exists (else re-plan)."""
    if k < 1:
        return None
    rc, d = cfg["controls"]["refclips"], cfg["controls"]["refclips_d084"]
    prefix, cap = rc["ledger_name_prefix"], float(rc["campaign_cap_usd"])
    _lines, records = ref._ledger(lg)
    names = [str(r.get("name", "")) for r in records if r.get("event") == "launch"]
    tk = cfg["controls"].get("refclips_d085", {}).get("talkface", {})
    talk_prefix = tk.get("session_prefix", prefix + "-talk")
    main = [n for n in names if n.startswith(prefix) and not n.startswith(prefix + "-nat")
            and not n.startswith(talk_prefix)]
    if main:
        raise Refused(f"the main campaign has started ({main[0]}): the D-084 projection plan is stale, "
                      "STOP to the owner")
    spend = ref.rcmp.campaign_spend(records, prefix, now)
    plan = float(d["main_campaign_plan_usd"])
    talk = float(tk.get("session_worst_usd", 0.0))      # council D-085 (watchdog): TALKFACE's own session
    this = price * max_hours
    proj = spend + plan + talk + this
    out = {"campaign_spend_usd": round(spend, 4), "main_campaign_plan_usd": plan, "talkface_plan_usd": talk,
           "this_session_planned_usd": this, "projection_usd": round(proj, 4), "cap_usd": cap}
    if proj > cap + 1e-9:
        raise Refused(f"D-071 (k) projection {proj:.2f} = spend {spend:.2f} + main plan {plan:.2f} + "
                      f"TALKFACE session {talk:.2f} + session {k} worst case {this:.2f} > ${cap:g}: "
                      "STOP to the owner")
    return out


def check_buffer(cfg: dict, log: list[dict], k: int = 0) -> list[str]:
    if k >= 1:
        return check_session_k(cfg, log, k)
    if any(r.get("stage") == ns.STAGE_S0 for r in log):
        raise Refused("session-0 rows are already logged (a logged candidate is never re-evaluated)")
    buf = ns.buffer_ids(log, cfg)
    if not buf:
        raise Refused("the NAT buffer is empty: run the CPU stage first")
    need = cfg["controls"]["refclips_auto"]["nat"]["cpu_buffer"]
    if not ns.buffer_complete(log, cfg):        # council D-082 W2/B1: never fix a partial buffer
        raise Refused(f"the NAT buffer holds {len(buf)} of {need} CPU passes and the log has no matching "
                      "snapshot_exhausted record: finish the CPU stage first")
    return buf


def check_cpu_stage(state: dict | None, log_path: Path) -> None:
    """The pod CPU stage must have ended, and the committed log must be the pod's log byte for byte."""
    if state is None:
        raise Refused("no CPU-stage state (pod natstim_cpu_run liveness + log sha): refused")
    if state.get("alive"):
        raise Refused("the pod NAT CPU stage is still running (natcpu.rc absent or natstim_cpu_run alive)")
    local = hashlib.sha256(Path(log_path).read_bytes()).hexdigest() if Path(log_path).exists() else None
    if state.get("pod_log_sha256") != local:
        raise Refused(f"the pod NAT log sha {str(state.get('pod_log_sha256'))[:12]} != the committed log "
                      f"{str(local)[:12]}: commit the pod log first")


# ---------------------------------------------------------------- L4 ledger reconciliation (D-071 k)
def _ledger_lines(lg) -> list[str]:
    path = Path(lg.LEDGER)
    return [x for x in (path.read_text().splitlines() if path.exists() else []) if x.strip()]


def _lines_sha(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def reconcile(lg, cfg: dict, clock) -> dict:
    """L4: every ledger launch has a terminate record, no yct-* instance is alive on the Lambda API, and the
    spend figures (global, budget cap, campaign by prefix) are recorded against the ledger's line count and
    sha. Refuses (exit 1) on an open launch or a live instance. The committed record must match the ledger
    at launch time (check_reconcile). The D-071 (k) $ tolerance needs an external invoice, which no API in
    this project exposes: disclosed in t_nat0_ready.md."""
    lines = _ledger_lines(lg)
    recs = [json.loads(x) for x in lines]
    ended = {r["id"] for r in recs if r.get("event") == "terminate"}
    open_ = [r["id"] for r in recs if r.get("event") == "launch" and r["id"] not in ended]
    live = [i.get("id") for i in lg._live(lg.list_ours())]
    if open_ or live:
        raise Refused(f"ledger not reconciled: open launches {open_}, live yct-* instances {live}")
    prefix = cfg["controls"]["refclips"]["ledger_name_prefix"]
    return {"ledger_n_lines": len(lines), "ledger_sha256": _lines_sha(lines), "open_launches": open_,
            "live": live, "spent_usd": round(lg.spent_usd(), 4), "budget_cap_usd": lg.budget_cap(),
            "campaign_spend_usd": round(ref.rcmp.campaign_spend(recs, prefix, clock()), 4), "t": clock()}


def check_reconcile(rec: dict | None, lg) -> None:
    if rec is None:
        raise Refused("no L4 ledger reconciliation record: run --reconcile-only and commit it")
    lines = _ledger_lines(lg)
    if rec.get("ledger_n_lines") != len(lines) or rec.get("ledger_sha256") != _lines_sha(lines):
        raise Refused(f"the ledger reconciliation record is stale ({rec.get('ledger_n_lines')} lines vs "
                      f"{len(lines)} now): re-run --reconcile-only")
    if rec.get("open_launches") or rec.get("live"):
        raise Refused("the ledger reconciliation record shows open launches or live instances")


def preflight(a, cfg: dict, lg, store, clock, head: str, pushed: bool, log: list[dict],
              recon: dict | None = None, cpu_state: dict | None = None, log_path: Path | None = None) -> dict:
    """All pre-launch checks, in order; the baseline is written last-but-one (only once every other check
    passed), then the cap guard. Returns the plan."""
    price = lg.types()[cfg["p4"]["gpu_type"]]["usd_per_hour"]
    k = int(getattr(a, "session", 0) or 0)
    check_frozen(cfg, k)
    check_limits(cfg, a.max_hours, a.usd_limit, price)
    check_terminator(cfg, store, a.external_terminator_at, clock(), a.max_hours)
    check_commit(head, a.ci_green_sha, pushed)
    check_reconcile(recon, lg)
    check_cpu_stage(cpu_state, log_path)
    buf = check_buffer(cfg, log, k)
    if lg._live(lg.list_ours()):
        raise Refused("a yct-* instance is alive: one instance at a time")
    proj = check_projection(cfg, lg, price=price, max_hours=a.max_hours, now=clock(), k=k)
    ref.ensure_baseline(store, lg, cfg, clock)
    guard = ref.make_pre_launch(store, lg, cfg, clock, a.ack_cap_80)(price, a.max_hours)
    if proj is not None:
        guard = {**guard, "projection": proj}
    return {"buffer": buf, "price": price, "pre_launch": guard}


def run_session0(a, cfg: dict, lg, store, box, clock, log_path: Path, head: str,
                 pushed: bool, recon: dict | None = None, cpu_state: dict | None = None) -> tuple[int, dict]:
    log = ns.load_log(log_path)
    k = int(getattr(a, "session", 0) or 0)
    session = f"nat{k}"
    res: dict = {"session": session, "k": k, "git_sha": head, "steps": {}}
    try:
        plan = preflight(a, cfg, lg, store, clock, head, pushed, log, recon, cpu_state, log_path)
    except SystemExit as exc:
        res.update(status="refused", error=str(exc))
        return 1, res
    res.update(pre_launch=plan["pre_launch"], n_buffer=len(plan["buffer"]))
    name = cfg["controls"]["refclips"]["ledger_name_prefix"] + "-" + session
    try:
        rec = lg.launch(cfg["p4"]["gpu_type"], name, a.max_hours, "yct-pod", None, name_deadline=True)
    except SystemExit as exc:
        if "has no capacity" not in str(exc):
            raise
        res.update(status="no_capacity", error=str(exc))
        return 75, res
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        res.update(status="no_capacity", error=f"HTTP 400: {exc.read().decode(errors='replace')[:300]}")
        return 75, res
    iid = res["instance_id"] = rec["id"]
    res["terminator"] = {"kind": "external_scheduled_session", "fire_at": a.external_terminator_at}
    gpu = None
    try:
        box.start(iid, float(rec["deadline"]))
        for step in STEPS:
            out = box.step(step, plan["buffer"])
            res["steps"][step] = "ok"
            if step == "nat0":
                gpu = out
    except Exception as exc:  # noqa: BLE001 - nothing logged yet: a re-run (75) with a new terminator
        res.update(status="box_failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        gpu = None      # council D-082 (biostat B2): the selection is logged only when EVERY step is ok
    finally:
        try:
            lg.terminate(iid, "job_done")
        finally:
            lg.reap()
        res["alive_after"] = lg._live(lg.list_ours())
    store.s3_put_text(f"runs/{a.run_id}/child_metrics.json", json.dumps(res, default=str))
    if gpu is None or any(res["steps"].get(st) != "ok" for st in STEPS):
        return 75, res
    if k >= 1:
        return _finish_k(k, plan["buffer"], gpu, box, cfg, log_path, res)
    try:
        rows = ns.session0_rows(plan["buffer"], gpu["results"], box.n3, cfg)
    except ns.Session0Stop as stop:
        for r in stop.rows:
            ra.append_jsonl(log_path, r)
        res.update(status="stop", error=str(stop), n_pass=sum(r["decision"] == "pass" for r in stop.rows))
        return 1, res
    except Exception as exc:  # noqa: BLE001 - fail-closed post-session error: a human decides
        res.update(status="failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        return 1, res
    for r in rows:
        ra.append_jsonl(log_path, r)
    res.update(status="done", n_pass=sum(r["decision"] == "pass" for r in rows), n_rows=len(rows))
    return 0, res


def _finish_k(k: int, buffer: list[str], gpu: dict, box, cfg: dict, log_path: Path, res: dict):
    """D-084: log every row of session k, then the cumulative selection decides: selected (exit 0), next
    buffer (exit 0, status next_buffer), or STOP to the owner (exit 1: max_sessions reached or the snapshot
    exhausted with < nat_n passes)."""
    try:
        rows = ns.session_rows(k, buffer, gpu["results"], box.n3, cfg)
    except Exception as exc:  # noqa: BLE001 - fail-closed post-session error: a human decides
        res.update(status="failed", error=f"{type(exc).__name__}: {exc}"[-2000:])
        return 1, res
    for r in rows:
        ra.append_jsonl(log_path, r)
    log = ns.load_log(log_path)
    sel = ns.nat_selection(log, cfg)
    need = cfg["controls"]["refclips"]["nat_n"]
    res.update(n_rows=len(rows), n_pass=sum(r["decision"] == "pass" for r in rows),
               n_pass_total=ns.gpu_passes(log), n_selected=len(sel))
    if len(sel) >= need:
        res.update(status="selected")
        return 0, res
    if k >= cfg["controls"]["refclips_d084"]["max_sessions"] or ns.snapshot_exhausted(log):
        res.update(status="stop", error=f"{len(sel)} NAT passes < nat_n {need} after session {k} "
                                        "(max_sessions reached or snapshot exhausted): STOP to the owner")
        return 1, res
    res.update(status="next_buffer")
    return 0, res


# ---------------------------------------------------------------- real pod/box backend
FREEZE = "outputs/runs/wave1p2b_20261117T234829Z/wx_pip_freeze.txt"
# council D-082 B1: the box steps run yct.curate.nat0_box and yct.transcribe from the shipped tree and
# install the pinned env from the freeze file, so all of them ship (tests/test_nat0_council_d082.py checks
# the import closure against the tarball)
EXTRA_SHIP = ["infra/gpu_deadman.sh", "src/yct/curate/__init__.py", "src/yct/curate/nat0_box.py", FREEZE]
# P2b precedent (scripts/gpu_wave1_p2b.py): the pinned WhisperX env's cudnn/cublas for ctranslate2 on cuda
CUDA_LIBS = ("SP=$(python -c 'import site; print(site.getsitepackages()[0])')\n"
             "export LD_LIBRARY_PATH=$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:${LD_LIBRARY_PATH:-}\n")


T1_DIR = "/work/yct/nat_scratch/t1"     # natcpu.sh runs scripts/natstim_cpu_run.py run /work/yct/nat_scratch
WAV_DIR = f"{T1_DIR}/audio16k"


def box_shas(cfg: dict) -> str:
    """The --shas JSON the nat0 box step passes to yct.curate.nat0_box (also used by the pod rehearsal)."""
    return json.dumps({k.removeprefix("pyannote_").removesuffix("_sha256"):
                       cfg["controls"]["refclips_auto_artifacts"][k] for k in PYANNOTE_KEYS})


def mirror_src(cfg: dict) -> str:
    root = cfg["controls"]["refclips"]["s3_root"].rstrip("/")
    return f"{root}/{cfg['controls']['refclips_auto']['nat']['weights_mirror'].strip('/')}/pyannote/"


def mirror_sync_cmd(cfg: dict, dest: str) -> str:
    """The exact push_buffer mirror sync (also used by the pod rehearsal)."""
    return f"aws s3 sync --only-show-errors --region eu-central-1 {mirror_src(cfg)} {dest}"


def n3_cmd(t1_name: str, repo: str = "/work/yct/repo") -> str:
    """N3 (P3 face_present_crop over the T1 clip) on the pod CPU, printing the per-TR list."""
    return (f"cd {repo} && /work/yct/venv/bin/python -c \"import json,sys; "
            "sys.path.insert(0,'src'); from yct.config import load_config; "
            "from yct.confounds.core import tr_grid, video_features; "
            "from yct.normalize.core import probe_source; c=load_config(); "
            f"p='{T1_DIR}/{t1_name}.mp4'; "
            "g=tr_grid(probe_source(p)['duration_s'], c['tribe']['tr_s']); "
            "print(json.dumps(list(map(float, video_features(p, g, c)['face_present_crop']))))\"")


def ship_list() -> list[str]:
    """gpu_p0_rerun.SHIP (copied, never mutated) + the session-0 extras, de-duplicated in order."""
    import gpu_p0_rerun as g

    out: list[str] = []
    for p in [*g.SHIP, *EXTRA_SHIP]:
        if p not in out:
            out.append(p)
    return out


def ship_tarball(paths: list[str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in paths:
            tf.add(ROOT / rel, arcname=rel, filter=lambda ti: None if "__pycache__" in ti.name else ti)
    return buf.getvalue()


class PodBox:
    """The P2b box pattern (scripts/gpu_wave1_p2b.py): pod-driven ssh, dead-man switch, heartbeat, pinned
    WhisperX env from the committed freeze file, pyannote OFFLINE from the S3 mirror. Never sees a token."""

    FREEZE = FREEZE

    def __init__(self, cfg: dict, run_id: str, max_hours: float):
        import gpu_p0_rerun as g

        self.g, self.cfg, self.run_id, self.max_hours = g, cfg, run_id, max_hours
        self.pod_dir = f"/work/yct/runs/{run_id}"
        self.box = None

    def start(self, iid: str, deadline: float) -> None:
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
        self.box = g.Box(ip, self.pod_dir)
        g.pod(f"mkdir -p {self.pod_dir}", 120)
        for _ in range(30):
            if g.pod(f"{self.box.ssh} true && echo up", 120, check=False).strip().endswith("up"):
                break
            time.sleep(20)
        self.ship()
        hard = int(min(self.max_hours * 3600, deadline - time.time()))
        self.box.run(f"touch ~/yct_driver_touch; nohup bash {g.B}/infra/gpu_deadman.sh ~/yct_driver_touch "
                     f"1200 {hard} >/dev/null 2>&1 </dev/null & sleep 1; "
                     "pgrep -f gpu_deadman.sh >/dev/null && echo dm")

    def ship(self) -> str:
        """gpu_p0_rerun.ship_code with the session-0 ship list (ship_list); returns the tarball sha256."""
        g, data = self.g, ship_tarball(ship_list())
        b64 = base64.b64encode(data).decode()
        g.pod(f"mkdir -p {self.pod_dir} && rm -f {self.pod_dir}/code.b64", 120)
        for i in range(0, len(b64), 20000):
            g.pod(f"echo -n {b64[i:i + 20000]} >> {self.pod_dir}/code.b64", 120)
        g.pod(f"base64 -d {self.pod_dir}/code.b64 > {self.pod_dir}/code.tgz && cat {self.pod_dir}/code.tgz | "
              f"{self.box.ssh} 'mkdir -p {g.B} && tar xzf - -C {g.B}'", 300)
        return hashlib.sha256(data).hexdigest()

    def step(self, name: str, buffer: list[str]):
        g, b = self.g, self.g.B
        root = self.cfg["controls"]["refclips"]["s3_root"].rstrip("/")
        if name == "setup_wx":
            # a fresh box has no uv (only tribe_run's setup script installs it) and maybe no ffmpeg (WhisperX
            # load_audio); P2b's env also needs nltk punkt_tab (council D-082 referee 2/3, QA B2)
            self.box.start("wxsetup", f"cd {b}\n"
                           "for i in $(seq 1 60); do sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 "
                           "|| break; sleep 5; done\n"
                           "APT='sudo DEBIAN_FRONTEND=noninteractive apt-get -qq'\n"
                           "command -v ffmpeg >/dev/null || "
                           "{ $APT update && $APT install -y ffmpeg >/dev/null; }\n"
                           "if [ ! -x \"$HOME/.uvbin/uv\" ]; then curl -LsSf https://astral.sh/uv/install.sh "
                           "| env UV_INSTALL_DIR=\"$HOME/.uvbin\" UV_NO_MODIFY_PATH=1 sh >/dev/null; fi\n"
                           "UV=$HOME/.uvbin/uv\n"
                           "[ -d wxvenv ] || $UV venv -q -p 3.11 wxvenv\n"
                           f"$UV pip install -q --python wxvenv/bin/python -r {b}/{self.FREEZE}\n"
                           "wxvenv/bin/python -c \"import nltk; nltk.download('punkt_tab', quiet=True)\"\n")
            if self.box.wait("wxsetup", 2400) != 0:
                raise RuntimeError("wxsetup failed:\n" + self.box.cat("~/steps/wxsetup.log")[-2000:])
        elif name == "push_buffer":
            names = " ".join(f"{i}.wav" for i in buffer)
            sync = mirror_sync_cmd(self.cfg, "/work/yct/nat_box/mirror/")
            g.pod(f"mkdir -p /work/yct/nat_box && {sync} && "
                  f"cd {WAV_DIR} && tar cf - {names} | {self.box.ssh} "
                  f"'mkdir -p {b}/nat/wavs && tar xf - -C {b}/nat/wavs' && cd /work/yct/nat_box && "
                  f"tar cf - mirror | {self.box.ssh} 'tar xf - -C {b}/nat'", 3600)
        elif name == "nat0":
            shas = box_shas(self.cfg)
            self.box.start("nat0", f"cd {b}; source wxvenv/bin/activate; export PYTHONPATH={b}/src\n"
                                   + CUDA_LIBS +
                                   "python -m yct.curate.nat0_box --wavs nat/wavs --mirror nat/mirror "
                                   f"--shas '{shas}' --out nat/nat0.json > nat/nat0.log 2>&1\n")
            if self.box.wait("nat0", 3600) != 0:
                raise RuntimeError("nat0 failed:\n" + self.box.cat(f"{b}/nat/nat0.log")[-2000:])
            # QA B3: SSM stdout is truncated at 24,000 chars, so the result is copied box -> pod over ssh
            # and read back with the chunked pod_file, never from a `cat` through pod()
            local = f"{self.pod_dir}/nat0.json"
            g.pod(f"{self.box.ssh} 'cat {b}/nat/nat0.json' > {local}", 300)
            return json.loads(g.pod_file(local))
        elif name == "asr":
            self.box.start("asr", f"cd {b}; source wxvenv/bin/activate; export PYTHONPATH={b}/src\n"
                                  + CUDA_LIBS +
                                  "mkdir -p nat/asr\n"
                                  "python -m yct.transcribe --out-dir nat/asr --record nat/asr_run.json "
                                  "nat/wavs/*.wav > nat/asr.log 2>&1\n")
            if self.box.wait("asr", 3600) != 0:
                raise RuntimeError("asr failed")
            g.pod(f"mkdir -p /work/yct/nat_asr && {self.box.ssh} 'tar cf - -C {b}/nat asr asr_run.json' | "
                  f"tar xf - -C /work/yct/nat_asr && aws s3 sync --only-show-errors --region eu-central-1 "
                  f"/work/yct/nat_asr {root}/nat_asr/", 1800)

    def n3(self, t1_name: str) -> float:
        out = self.g.pod(n3_cmd(t1_name), 1800)
        return ns.n3_value(json.loads(out.strip().splitlines()[-1]), self.cfg)


class S3Store:
    """controls.refclips.s3_root as the campaign store (baseline, run metrics), via the aws CLI."""

    def __init__(self, cfg: dict):
        self.root = cfg["controls"]["refclips"]["s3_root"].rstrip("/")

    def s3_get_text(self, key: str):
        r = subprocess.run(["aws", "s3", "cp", "--region", "eu-central-1", f"{self.root}/{key}", "-"],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def s3_put_text(self, key: str, text: str) -> None:
        subprocess.run(["aws", "s3", "cp", "--region", "eu-central-1", "-", f"{self.root}/{key}"],
                       input=text, text=True, check=True)

    def s3_list(self, prefix: str) -> dict:
        r = subprocess.run(["aws", "s3", "ls", "--region", "eu-central-1", "--recursive",
                            f"{self.root}/{prefix}"],
                           capture_output=True, text=True)
        base = self.root.split("/", 3)[3] + "/" if self.root.count("/") >= 3 else ""
        return {ln.split()[-1].removeprefix(base): 1 for ln in r.stdout.splitlines() if ln.strip()}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


RECONCILE_PATH = "data/refstim/ledger_reconcile_nat0.json"     # committed L4 record (D-071 k)
POD_NAT_LOG = "/work/yct/repo/data/refstim/nat_auto_log.jsonl"


def pod_cpu_state() -> dict:
    """Liveness of the pod NAT CPU stage and the sha of the pod's NAT log (read-only)."""
    import gpu_p0_rerun as g

    out = g.pod("if pgrep -f 'natstim_cpu_run.py run' >/dev/null || { [ -f /work/yct/natcpu.sh ] && "
                "[ ! -f /work/yct/natcpu.rc ]; }; then echo alive; else echo done; fi; "
                f"sha256sum {POD_NAT_LOG} | cut -d' ' -f1", 120).split()
    return {"alive": out[0] == "alive", "pod_log_sha256": out[1] if len(out) > 1 else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-hours", type=float, default=1.75)
    ap.add_argument("--usd-limit", type=float, default=USD_LIMIT_MAX)
    ap.add_argument("--external-terminator-at")
    ap.add_argument("--ci-green-sha", help="the commit whose CI run is green (checked by the orchestrator); "
                                           "must equal HEAD")
    ap.add_argument("--ack-cap-80", action="store_true")
    ap.add_argument("--session", type=int, default=0,
                    help="0 = session 0 (D-075); k >= 1 = D-084 continuation session on NAT buffer k")
    ap.add_argument("--reconcile-only", action="store_true",
                    help=f"write the L4 ledger reconciliation record to {RECONCILE_PATH}, then exit")
    a = ap.parse_args(argv)
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    cfg = load_config()
    from infra import lambda_gpu as lg

    if a.reconcile_only:
        rec = reconcile(lg, cfg, time.time)
        (ROOT / RECONCILE_PATH).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        print(json.dumps(rec))
        return 0
    if not a.external_terminator_at or not a.ci_green_sha:
        raise SystemExit("--external-terminator-at and --ci-green-sha are required for a launch")
    p4 = ref.p4
    run_dir = Path(os.environ.get("YCT_RUN_DIR")
                   or ROOT / "outputs" / "runs" / f"p4bnat{a.session}_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    a.external_terminator_at = p4._parse_when(a.external_terminator_at)
    a.run_id = run_dir.name
    head = _git("rev-parse", "HEAD")
    pushed = bool(_git("branch", "-r", "--contains", head))
    os.environ["YCT_HB_VIA_POD"] = "1"
    rp = ROOT / RECONCILE_PATH
    recon = json.loads(rp.read_text()) if rp.exists() else None
    rc, res = run_session0(a, cfg, lg, S3Store(cfg), PodBox(cfg, a.run_id, a.max_hours), time.time,
                           ROOT / cfg["controls"]["refclips_auto"]["logs"]["nat"], head, pushed,
                           recon=recon, cpu_state=pod_cpu_state())
    (run_dir / "child_metrics.json").write_text(json.dumps(res, indent=1, default=str))
    keys = ("status", "error", "n_pass", "n_buffer", "pre_launch")
    print(json.dumps({k: res.get(k) for k in keys}, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
