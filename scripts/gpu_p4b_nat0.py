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
  * the buffer: the NAT log's CPU-stage passes (1..cpu_buffer), no session-0 row logged yet;
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
import importlib.util
import json
import os
import subprocess
import sys
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


def check_frozen(cfg: dict) -> None:
    rows = {r["key"] for r in cfg.get("frozen") or []}
    need = ["controls.refclips_auto", "controls.refclips_d082", "controls.refclips_artifacts.nat_snapshot_sha256"] + \
        [f"controls.refclips_auto_artifacts.{k}" for k in PYANNOTE_KEYS]
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


def check_buffer(cfg: dict, log: list[dict]) -> list[str]:
    if any(r.get("stage") == ns.STAGE_S0 for r in log):
        raise Refused("session-0 rows are already logged (a logged candidate is never re-evaluated)")
    buf = ns.buffer_ids(log, cfg)
    if not buf:
        raise Refused("the NAT buffer is empty: run the CPU stage first")
    return buf


def preflight(a, cfg: dict, lg, store, clock, head: str, pushed: bool, log: list[dict]) -> dict:
    """All pre-launch checks, in order; the baseline is written last-but-one (only once every other check
    passed), then the cap guard. Returns the plan."""
    price = lg.types()[cfg["p4"]["gpu_type"]]["usd_per_hour"]
    check_frozen(cfg)
    check_limits(cfg, a.max_hours, a.usd_limit, price)
    check_terminator(cfg, store, a.external_terminator_at, clock(), a.max_hours)
    check_commit(head, a.ci_green_sha, pushed)
    buf = check_buffer(cfg, log)
    if lg._live(lg.list_ours()):
        raise Refused("a yct-* instance is alive: one instance at a time")
    ref.ensure_baseline(store, lg, cfg, clock)
    guard = ref.make_pre_launch(store, lg, cfg, clock, a.ack_cap_80)(price, a.max_hours)
    return {"buffer": buf, "price": price, "pre_launch": guard}


def run_session0(a, cfg: dict, lg, store, box, clock, log_path: Path, head: str,
                 pushed: bool) -> tuple[int, dict]:
    log = ns.load_log(log_path)
    res: dict = {"session": SESSION, "git_sha": head, "steps": {}}
    try:
        plan = preflight(a, cfg, lg, store, clock, head, pushed, log)
    except SystemExit as exc:
        res.update(status="refused", error=str(exc))
        return 1, res
    res.update(pre_launch=plan["pre_launch"], n_buffer=len(plan["buffer"]))
    name = cfg["controls"]["refclips"]["ledger_name_prefix"] + "-" + SESSION
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
    finally:
        try:
            lg.terminate(iid, "job_done")
        finally:
            lg.reap()
        res["alive_after"] = lg._live(lg.list_ours())
    store.s3_put_text(f"runs/{a.run_id}/child_metrics.json", json.dumps(res, default=str))
    if gpu is None:
        return 75, res
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


# ---------------------------------------------------------------- real pod/box backend (not used in tests)
class PodBox:
    """The P2b box pattern (scripts/gpu_wave1_p2b.py): pod-driven ssh, dead-man switch, heartbeat, pinned
    WhisperX env from the committed freeze file, pyannote OFFLINE from the S3 mirror. Never sees a token."""

    FREEZE = "outputs/runs/wave1p2b_20261117T234829Z/wx_pip_freeze.txt"

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
        g.SHIP.append("infra/gpu_deadman.sh")
        g.ship_code(self.box, self.pod_dir)
        hard = int(min(self.max_hours * 3600, deadline - time.time()))
        self.box.run(f"touch ~/yct_driver_touch; nohup bash {g.B}/infra/gpu_deadman.sh ~/yct_driver_touch "
                     f"1200 {hard} >/dev/null 2>&1 </dev/null & sleep 1; "
                     "pgrep -f gpu_deadman.sh >/dev/null && echo dm")

    def step(self, name: str, buffer: list[str]):
        g, b = self.g, self.g.B
        n = self.cfg["controls"]["refclips_auto"]
        root = self.cfg["controls"]["refclips"]["s3_root"].rstrip("/")
        if name == "setup_wx":
            self.box.start("wxsetup", f"cd {b}; UV=$HOME/.uvbin/uv; "
                                      "[ -d wxvenv ] || $UV venv -q -p 3.11 wxvenv\n"
                                      f"$UV pip install -q --python wxvenv/bin/python -r {b}/{self.FREEZE}\n")
            if self.box.wait("wxsetup", 2400) != 0:
                raise RuntimeError("wxsetup failed")
        elif name == "push_buffer":
            names = " ".join(f"{i}.wav" for i in buffer)
            g.pod(f"mkdir -p /work/yct/nat_box && aws s3 sync --only-show-errors --region eu-central-1 "
                  f"{root}/{n['nat']['weights_mirror'].strip('/')}/pyannote/ /work/yct/nat_box/mirror/ && "
                  f"cd /work/yct/nat_scratch/t1/audio16k && tar cf - {names} | {self.box.ssh} "
                  f"'mkdir -p {b}/nat/wavs && tar xf - -C {b}/nat/wavs' && cd /work/yct/nat_box && "
                  f"tar cf - mirror | {self.box.ssh} 'tar xf - -C {b}/nat'", 3600)
        elif name == "nat0":
            shas = json.dumps({k.removeprefix("pyannote_").removesuffix("_sha256"):
                               self.cfg["controls"]["refclips_auto_artifacts"][k] for k in PYANNOTE_KEYS})
            self.box.start("nat0", f"cd {b}; export PYTHONPATH={b}/src\n"
                                   "wxvenv/bin/python -m yct.curate.nat0_box --wavs nat/wavs "
                                   "--mirror nat/mirror "
                                   f"--shas '{shas}' --out nat/nat0.json > nat/nat0.log 2>&1\n")
            if self.box.wait("nat0", 3600) != 0:
                raise RuntimeError("nat0 failed:\n" + self.box.cat(f"{b}/nat/nat0.log")[-2000:])
            return json.loads(self.box.run(f"cat {b}/nat/nat0.json"))
        elif name == "asr":
            self.box.start("asr", f"cd {b}; source wxvenv/bin/activate; export PYTHONPATH={b}/src\n"
                                  "mkdir -p nat/asr\n"
                                  "python -m yct.transcribe --out-dir nat/asr --record nat/asr_run.json "
                                  "nat/wavs/*.wav > nat/asr.log 2>&1\n")
            if self.box.wait("asr", 3600) != 0:
                raise RuntimeError("asr failed")
            g.pod(f"mkdir -p /work/yct/nat_asr && {self.box.ssh} 'tar cf - -C {b}/nat asr asr_run.json' | "
                  f"tar xf - -C /work/yct/nat_asr && aws s3 sync --only-show-errors --region eu-central-1 "
                  f"/work/yct/nat_asr {root}/nat_asr/", 1800)

    def n3(self, t1_name: str) -> float:
        out = self.g.pod(f"cd /work/yct/repo && /work/yct/venv/bin/python -c \"import json,sys; "
                         f"sys.path.insert(0,'src'); from yct.config import load_config; "
                         f"from yct.confounds.core import tr_grid, video_features; "
                         f"from yct.normalize.core import probe_source; c=load_config(); "
                         f"p='/work/yct/nat_scratch/t1/{t1_name}.mp4'; "
                         f"g=tr_grid(probe_source(p)['duration_s'], c['tribe']['tr_s']); "
                         "print(json.dumps(list(map(float, "
                         "video_features(p, g, c)['face_present_crop']))))\"",
                         1800)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-hours", type=float, default=1.75)
    ap.add_argument("--usd-limit", type=float, default=USD_LIMIT_MAX)
    ap.add_argument("--external-terminator-at", required=True)
    ap.add_argument("--ci-green-sha", required=True, help="the commit whose CI run is green (checked by the "
                                                          "orchestrator); must equal HEAD")
    ap.add_argument("--ack-cap-80", action="store_true")
    a = ap.parse_args(argv)
    if os.environ.get("AWS_DEFAULT_REGION", "eu-central-1") != "eu-central-1":
        raise SystemExit("AWS_DEFAULT_REGION must be eu-central-1 (yct resources only)")
    cfg = load_config()
    from infra import lambda_gpu as lg

    p4 = ref.p4
    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p4bnat0_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    a.external_terminator_at = p4._parse_when(a.external_terminator_at)
    a.run_id = run_dir.name
    head = _git("rev-parse", "HEAD")
    pushed = bool(_git("branch", "-r", "--contains", head))
    os.environ["YCT_HB_VIA_POD"] = "1"
    rc, res = run_session0(a, cfg, lg, S3Store(cfg), PodBox(cfg, a.run_id, a.max_hours), time.time,
                           ROOT / cfg["controls"]["refclips_auto"]["logs"]["nat"], head, pushed)
    (run_dir / "child_metrics.json").write_text(json.dumps(res, indent=1, default=str))
    keys = ("status", "error", "n_pass", "n_buffer", "pre_launch")
    print(json.dumps({k: res.get(k) for k in keys}, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main())
