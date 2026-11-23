#!/usr/bin/env python3
"""FIX-C3-ENG item F: P0 GPU re-run (feature-cache determinism, D-038 reliability, long clips, offline).

Run under provenance:  python scripts/run_with_provenance.py --run-id p0rerun_<UTC> -- \
                           python scripts/gpu_p0_rerun.py [--max-hours 2] [--usd-limit 15]
Drives ONE Lambda instance (infra/lambda_gpu.py launch, A100 SXM4 as in the P0 smoke) from the pod
(infra/pod_exec.sh -> ssh with /root/.ssh/yct_lambda; Lambda key "yct-pod"). The HF token is piped
pod-side from SSM straight into the box's token file (never on a command line). The instance-side
heartbeat (infra/gpu_heartbeat.sh) is polled into the ledger by `lambda_gpu.py watch` (idle/heartbeat
reaper) for the whole session. The instance is ALWAYS terminated (finally).

Box runs (src/yct/tribe_run/run_clip.py, HF_HUB_OFFLINE=1 + no network, pinned backbones):
  smoke 10 s : run A (extract + predict), run B (cache reuse -> predictions must be bit-identical),
               run C (--fresh-drift: throw-away re-extraction -> per-feature reliability, D-038 gate 0.99)
  long70 / long110 : testsrc2 + espeak speech throughout + our .tsv -> shape/T, chunks, words, VRAM;
               long70 also --fresh-drift (second real-like clip for the reliability gate)
Persists res/, fc/ (feature cache) and clips/ on the pod (/work/yct/runs/<run_id>/, cache entries also
under /work/yct/cache/) and writes into $YCT_RUN_DIR: child_metrics.json, report.md, cache_manifest.json,
artifacts_sha256.txt, per-run JSONs.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
POD_EXEC = str(ROOT / "infra" / "pod_exec.sh")
ITYPE = "gpu_1x_a100_sxm4"  # same class as the P0 smoke (ENH-004 not decided: no A10)
KEY = "/root/.ssh/yct_lambda"
SSHO = (f"-i {KEY} -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "
        "-o UserKnownHostsFile=/root/.ssh/known_hosts_yct -o ServerAliveInterval=30")
SHIP = ["src/yct/__init__.py", "src/yct/config.py", "src/yct/media.py", "src/yct/config_schema.py", "config.yaml", "src/yct/tribe_run",
        "src/yct/transcribe", "infra/gpu_heartbeat.sh"]
B = "/home/ubuntu/yct"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def pod(cmd: str, timeout: int = 900, check: bool = True) -> str:
    res = subprocess.run([POD_EXEC, cmd, str(timeout)], capture_output=True, text=True, timeout=timeout + 300)
    if check and res.returncode != 0:
        raise RuntimeError(f"pod command failed ({res.returncode}): {cmd[:200]}\n{res.stdout[-2000:]}"
                           f"\n{res.stderr[-2000:]}")
    return res.stdout


def pod_file(path: str, missing_ok: bool = False) -> str:
    """Text of a pod file, fetched in base64 chunks (SSM StandardOutputContent is truncated at 24,000 chars)."""
    n = pod(f"if [ -f {path} ]; then base64 -w0 {path} | wc -c; else echo -1; fi", 300).strip()
    if int(n) < 0:
        if missing_ok:
            return ""
        raise FileNotFoundError(path)
    parts, step = [], 20000
    for i in range(0, int(n), step):
        parts.append(pod(f"base64 -w0 {path} | cut -c{i + 1}-{i + step}", 300).strip())
    return base64.b64decode("".join(parts)).decode()


class Box:
    def __init__(self, ip: str, pod_dir: str):
        self.ip, self.pod_dir = ip, pod_dir
        self.ssh = f"ssh {SSHO} ubuntu@{ip}"

    def put_text(self, text: str, remote: str) -> None:
        b64 = base64.b64encode(text.encode()).decode()
        pod(f"echo {b64} | base64 -d | {self.ssh} 'cat > {remote}'", 300)

    def run(self, script: str, timeout: int = 900) -> str:
        """Run a bash script on the box in the foreground (stdin = /dev/null)."""
        name = f"/tmp/yct_step_{int(time.time() * 1000)}.sh"
        self.put_text("set -euo pipefail\n" + script, name)
        return pod(f"{self.ssh} 'bash {name} </dev/null'", timeout)

    def start(self, name: str, script: str) -> None:
        """Run a bash script detached on the box; rc lands in ~/steps/<name>.rc."""
        self.put_text("set -euo pipefail\n" + script, f"/tmp/{name}.sh")
        pod(f"{self.ssh} 'mkdir -p ~/steps && rm -f ~/steps/{name}.rc && "
            f"(nohup bash -c \"bash /tmp/{name}.sh > ~/steps/{name}.log 2>&1; echo \\$? > ~/steps/{name}.rc\" "
            f"</dev/null >/dev/null 2>&1 &)'", 120)

    def wait(self, name: str, timeout_s: int) -> int:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            out = pod(f"{self.ssh} 'cat ~/steps/{name}.rc 2>/dev/null || true; tail -n 2 ~/steps/{name}.log "
                      "2>/dev/null || true'", 120, check=False)
            first = out.strip().splitlines()[0] if out.strip() else ""
            if first.isdigit():
                return int(first)
            log(f"  {name}: running ({int(time.time() - t0)} s) {out.strip()[-160:]!r}")
            time.sleep(45)
        raise TimeoutError(f"step {name} exceeded {timeout_s} s")

    def cat(self, path: str) -> str:
        return pod(f"{self.ssh} 'cat {path}'", 300)


def ship_code(box: Box, pod_dir: str) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel in SHIP:
            tf.add(ROOT / rel, arcname=rel,
                   filter=lambda ti: None if "__pycache__" in ti.name else ti)
    b64 = base64.b64encode(buf.getvalue()).decode()
    pod(f"mkdir -p {pod_dir} && rm -f {pod_dir}/code.b64", 120)
    for i in range(0, len(b64), 20000):
        pod(f"echo -n {b64[i:i + 20000]} >> {pod_dir}/code.b64", 120)
    pod(f"base64 -d {pod_dir}/code.b64 > {pod_dir}/code.tgz && "
        f"cat {pod_dir}/code.tgz | {box.ssh} 'mkdir -p {B} && tar xzf - -C {B}' && sha256sum {pod_dir}/code.tgz",
        300)


RUN = f"""cd {B}; source venv/bin/activate; export PYTHONPATH={B}/src
RC={B}/src/yct/tribe_run/run_clip.py; R={B}/res; FC={B}/fc; mkdir -p $R
run() {{ name=$1; shift; python $RC --feature-cache $FC --weights {B}/weights --out $R/$name "$@" > $R/$name.log 2>&1; }}
"""


def collect(pod_dir: str, run_dir: Path, result: dict) -> None:
    """Copy the small artifacts (per-run JSON, events, sha256 lists, cache manifest) from the pod run dir."""
    for f in ("res/SHA256SUMS", "res/FC_SHA256SUMS", "pip_freeze.txt"):
        (run_dir / Path(f).name).write_text(pod_file(f"{pod_dir}/{f}"))
    names = ["smoke_a", "smoke_b", "smoke_c", "long70", "long110"]
    names += [f"rel_{c}{x}" for c in ("smoke", "long70", "long110") for x in ("", "_rerun")]
    for n in names:
        out = pod_file(f"{pod_dir}/res/{n}.json", missing_ok=True)
        if out.strip().startswith("{"):
            (run_dir / f"{n}.json").write_text(out)
            result.setdefault("runs", {})[n] = json.loads(out)
        ev = pod_file(f"{pod_dir}/res/{n}.events.csv", missing_ok=True)
        if ev.strip():
            (run_dir / f"{n}.events.csv").write_text(ev)
    pod(f"cd {pod_dir} && python3 -c \"import json,pathlib;"
        "pathlib.Path('cache_manifest.json').write_text(json.dumps({str(p.parent.name): json.loads(p.read_text()) "
        "for p in sorted(pathlib.Path('fc').glob('*/features.meta.json'))}))\"", 300)
    man = pod_file(f"{pod_dir}/cache_manifest.json")
    (run_dir / "cache_manifest.json").write_text(json.dumps(json.loads(man), indent=1, sort_keys=True))
    smoke_old = pod("cd /work/yct/runs/smoke_20261117T142354Z && sha256sum *.npy clips/*/*", 300)
    result["p0_smoke_artifacts_sha256"] = smoke_old.strip().splitlines()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=2.0)
    ap.add_argument("--usd-limit", type=float, default=15.0)
    ap.add_argument("--attach", help="reuse this live yct-* instance (after a --keep-on-fail run)")
    ap.add_argument("--skip-setup", action="store_true")
    ap.add_argument("--keep-on-fail", action="store_true",
                    help="on a failed step leave the instance up for debugging (watch/idle-kill keep running)")
    ap.add_argument("--spent-before", type=float, default=None, help="ledger spend before the first attempt")
    ap.add_argument("--collect-only", action="store_true",
                    help="only (re)collect artifacts of an existing pod run dir /work/yct/runs/<run_id> into "
                         "$YCT_RUN_DIR (same run_id); merges into its child_metrics.json")
    ap.add_argument("--steps", default="smoke,long70,long110",
                    help="comma list from: smoke, long70, long110 (P0 re-run) and rel_smoke, rel_long70, "
                         "rel_long110 (D-038 reliability: extract + fresh re-extraction kept for audit)")
    a = ap.parse_args()
    from infra import lambda_gpu as lg

    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"p0rerun_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    pod_dir = f"/work/yct/runs/{run_id}"
    if a.collect_only:
        cm = run_dir / "child_metrics.json"
        result = json.loads(cm.read_text()) if cm.exists() else {"run_id": run_id, "steps": {}}
        result.pop("error", None)
        result["collected_post_hoc"] = True
        collect(pod_dir, run_dir, result)
        cm.write_text(json.dumps(result, indent=1, default=str))
        return 0
    avail = lg.types()
    if ITYPE not in avail:                                   # BUG-047: capacity miss, retry later (exit 75)
        print(f"no_capacity: {ITYPE} not in available types", file=sys.stderr)
        return 75
    price = avail[ITYPE]["usd_per_hour"]
    if price * a.max_hours > a.usd_limit:
        raise SystemExit(f"{price}*{a.max_hours} h exceeds the task limit ${a.usd_limit}")
    live = lg._live(lg.list_ours())
    if a.attach:
        if [i["id"] for i in live] != [a.attach]:
            raise SystemExit(f"--attach {a.attach}: live yct instances are {live}")
    elif live:
        raise SystemExit("a yct-* instance is already alive; one instance at a time")
    spent0 = a.spent_before if a.spent_before is not None else lg.spent_usd()
    result: dict = {"run_id": run_id, "instance_type": ITYPE, "usd_per_hour": price, "steps": {},
                    "attached": bool(a.attach)}
    if a.attach:
        iid = result["instance_id"] = a.attach
    else:
        iid = result["instance_id"] = lg.launch(ITYPE, "yct-p0rerun", a.max_hours, "yct-pod", None)["id"]
    log(f"instance {iid} ({'attached' if a.attach else 'launched'})")
    watcher = None
    keep = False
    try:
        ip = None
        for _ in range(60):
            inst = lg._req("GET", f"/instances/{iid}")["data"]
            if inst.get("status") == "active" and inst.get("ip"):
                ip = inst["ip"]
                break
            time.sleep(20)
        if not ip:
            raise RuntimeError("instance never became active")
        box = Box(ip, pod_dir)
        for _ in range(30):
            if pod(f"{box.ssh} true && echo up", 120, check=False).strip().endswith("up"):
                break
            time.sleep(20)
        log(f"box {ip} reachable")
        ship_code(box, pod_dir)
        box.run(f"pgrep -f gpu_heartbeat.sh >/dev/null || (nohup bash {B}/infra/gpu_heartbeat.sh >/dev/null 2>&1 </dev/null &); sleep 2; tail -1 ~/yct_heartbeat.log")
        watcher = subprocess.Popen([sys.executable, str(ROOT / "infra" / "lambda_gpu.py"), "watch"],
                                   env={**os.environ, "YCT_HB_VIA_POD": "1"},
                                   stdout=open(run_dir / "watch.log", "w"), stderr=subprocess.STDOUT)
        # HF token: SSM -> pod pipe -> box file. Only the byte count is printed.
        pod("aws ssm get-parameter --region eu-central-1 --name /yct/hf_token --with-decryption "
            "--query Parameter.Value --output text | "
            f"{box.ssh} 'mkdir -p ~/.cache/huggingface && umask 077 && cat > ~/.cache/huggingface/token "
            "&& wc -c < ~/.cache/huggingface/token'", 300)
        if not a.skip_setup:
          box.start("setup", f"cp {B}/src/yct/tribe_run/remote_setup.sh {B}/; bash {B}/remote_setup.sh {B}\n"
                           f"cd {B}; bash src/yct/tribe_run/make_test_clips.sh {B}/clips\n"
                           f"source venv/bin/activate\n"
                           f"python src/yct/tribe_run/make_long_clip.py {B}/clips/long70/long70.mp4 70\n"
                           f"python src/yct/tribe_run/make_long_clip.py {B}/clips/long110/long110.mp4 110\n"
                           f"nvidia-smi > {B}/nvidia_smi.txt\n")
          rc = box.wait("setup", 2400)
          result["steps"]["setup"] = rc
          if rc != 0:
              raise RuntimeError("setup failed:\n" + box.cat("~/steps/setup.log")[-3000:])
          log("setup OK")
        all_steps = {
            "smoke": RUN + "run smoke_a --video clips/smoke/smoke.mp4\nrun smoke_b --video clips/smoke/smoke.mp4\n"
                           "run smoke_c --video clips/smoke/smoke.mp4 --fresh-drift\n",
            "long70": RUN + "run long70 --video clips/long70/long70.mp4 --fresh-drift\n",
            "long110": RUN + "run long110 --video clips/long110/long110.mp4\n",
            **{f"rel_{c}": RUN + f"run rel_{c} --video clips/{c}/{c}.mp4 --fresh-drift --keep-fresh\n"
                                 f"run rel_{c}_rerun --video clips/{c}/{c}.mp4\n"
               for c in ("smoke", "long70", "long110")},
        }
        steps = {k: all_steps[k] for k in a.steps.split(",")}
        for name, script in steps.items():
            box.start(name, script)
            rc = box.wait(name, 3000)
            result["steps"][name] = rc
            log(f"step {name} rc={rc}")
            if rc != 0:
                result.setdefault("errors", {})[name] = box.run(
                    f"tail -n 60 {B}/res/*.log 2>/dev/null || true; tail -n 30 ~/steps/{name}.log")[-6000:]
                if name in ("smoke", "rel_smoke"):
                    keep = a.keep_on_fail
                    break
        # Persist off the ephemeral box: pod run dir + content-addressed cache root.
        box.run(f"shopt -s nullglob; cd {B}; mkdir -p res fc; sha256sum res/*.npy clips/*/*.mp4 clips/*/*.tsv > res/SHA256SUMS; "
                f"find fc -type f -exec sha256sum {{}} + | sort -k2 > res/FC_SHA256SUMS; du -sh fc res")
        pod(f"mkdir -p {pod_dir} /work/yct/cache && {box.ssh} 'tar cf - -C {B} res fc clips pip_freeze.txt "
            f"nvidia_smi.txt' | tar xf - -C {pod_dir} && cp -rn {pod_dir}/fc/. /work/yct/cache/ && "
            f"du -sh {pod_dir} /work/yct/cache", 1800)
        collect(pod_dir, run_dir, result)
    except Exception as exc:  # noqa: BLE001 - always record and fall through to terminate
        result["error"] = f"{type(exc).__name__}: {exc}"[-4000:]
        log(f"ERROR {result['error'][:500]}")
    finally:
        if keep:
            log(f"--keep-on-fail: instance {iid} left up for debugging (watcher pid "
                f"{watcher.pid if watcher else None} keeps polling; idle-kill after 15 min, deadline applies)")
        else:
            try:
                lg.terminate(iid, "job_done")
            except Exception as exc:  # noqa: BLE001
                log(f"terminate failed: {exc}; reaping")
            if watcher is not None:
                time.sleep(5)
                watcher.terminate()
        lg.reap()
        live = lg._live(lg.list_ours())
        result["alive_after"] = live
        result["usd_spent_this_run"] = round(lg.spent_usd() - spent0, 4)
        result["instance_heartbeats"] = sum(1 for r in lg._ledger()
                                            if r["event"] == "heartbeat" and r["id"] == iid)
        log(f"terminated; alive={live}; spent this run ${result['usd_spent_this_run']}")
    result["kept_alive_for_debug"] = keep
    (run_dir / "child_metrics.json").write_text(json.dumps(result, indent=1, default=str))
    return 1 if result.get("error") or any(result["steps"].get(k) for k in result["steps"]) else 0


if __name__ == "__main__":
    sys.exit(main())
