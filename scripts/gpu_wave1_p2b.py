#!/usr/bin/env python3
"""Wave-1 P2b + P4 prerequisites in ONE Lambda session (pattern: scripts/gpu_p0_rerun.py).

Run under provenance:  python scripts/run_with_provenance.py --run-id wave1p2b_<UTC> -- \
                           python scripts/gpu_wave1_p2b.py [--max-hours 3.5] [--usd-limit 25]
One gpu_1x_a100_sxm4 (the P4 GPU type), driven from the EC2 pod (infra/pod_exec.sh -> ssh, /root/.ssh/yct_lambda);
HF token piped pod-side SSM -> box file (never on a command line); instance heartbeat + `lambda_gpu.py watch`
reaper; the instance is ALWAYS terminated (finally).

Box steps
  setup     TRIBE env (remote_setup.sh) + synthetic clips: long160, long110 (make_long_clip), ENH-002 reference
            clips (make_reference_clips)
  wxsetup   separate venv with the pinned WhisperX (config transcribe.whisperx.version, D-061)
  asr       ONE pinned WhisperX batch over the 57 wave-1 audio16k wavs -> raw JSON -> pod
            (pod: scripts/wave1_p2b_pod.py ingest -> TRIBE .tsv, manifest, label-free summary, WER hypotheses)
  bug018    run_clip --bug018-word-fix on long160 (>= 160 s) and long110: post-run word/T check must pass
  real      D-038 gate on the first 3 T1-eligible wave-1 clips by sorted video_id (label-blind): extract +
            fresh re-extraction (--fresh-drift --keep-fresh; reliability >= 0.99 per feature) + cached rerun
            (bit-identical predictions)
  enh002    ENH-002 dry run: ref_control, ref_flash (5 flashes), ref_speech (5 bursts), ref_face (talking face)
Afterwards (pod / local): feature cache -> S3 wave1/derived/feature_cache/ (per-entry tar without media + sha256
manifest), transcripts -> S3 wave1/derived/transcripts/, speech-rate confound refresh, ENH-002 latency CI.

Nothing with speech text (transcripts, events.csv / feature names of real clips) is written to $YCT_RUN_DIR:
real-clip results are reduced to numbers and hashes here.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import gpu_p0_rerun  # noqa: E402
from gpu_p0_rerun import B, Box, log, pod, pod_file, ship_code  # noqa: E402

gpu_p0_rerun.SHIP.append("infra/gpu_deadman.sh")  # BUG-027 box-side dead-man switch
DEADMAN_GRACE_S = 1200   # box halts 20 min after the last driver touch (driver/container died)
TOUCH_EVERY_S = 60
TOUCH = "~/yct_driver_touch"

ITYPE = "gpu_1x_a100_sxm4"
S3 = "s3://yct-research-235229001983/wave1/derived"
PY = "/work/yct/venv/bin/python"
REPO = "/work/yct/repo"
P2B = "/work/yct/p2b"
N_REAL = 3
MEDIA = (".mp4", ".wav", ".mkv", ".mov")

RUN = f"""cd {B}; source venv/bin/activate; export PYTHONPATH={B}/src
RC={B}/src/yct/tribe_run/run_clip.py; R={B}/res; FC={B}/fc; mkdir -p $R
run() {{ name=$1; shift; python $RC --feature-cache $FC --weights {B}/weights --out $R/$name "$@" > $R/$name.log 2>&1; }}
rc=0
"""


def real_clips(n: int = N_REAL) -> list[dict]:
    """First n T1-eligible wave-1 videos by sorted video_id (label-blind; P2 QC table only)."""
    rows = [r for r in csv.DictReader(open(ROOT / "data/wave1_normalize_qc.csv"))
            if r["status"] == "pass" and r["t1_excluded"] == "False"]
    return [{"video_id": r["video_id"], "content_id": r["content_id"]}
            for r in sorted(rows, key=lambda r: r["video_id"])[:n]]


def short_extractor(name: str) -> str:
    m = re.search(r"extractors\.(\w+)\.(\w+)", name)
    return f"{m.group(1)}.{m.group(2)}" if m else re.sub(r"[^\w.=-]", "_", name)[:60]


def sanitize_run(j: dict, real: bool) -> dict:
    """Numbers / hashes only (feature file names of real clips contain transcript text)."""
    keep = ("duration_s", "shape", "finite", "TR_s", "expected_T", "T_within_1", "n_words", "n_segments",
            "word_start_min_s", "word_start_max_s", "words_after_duration", "wall_load_s", "wall_extract_s",
            "wall_events_predict_s", "peak_vram_smi_mib", "torch_max_allocated_mib", "gpu", "torch", "cuda",
            "pred_mean", "pred_std", "uvx_on_path", "asr_called", "input_sha256", "transcript_sha256",
            "cache_key", "cache_reused", "pred_sha256", "pred_shape", "offline", "bug018_word_check")
    out = {k: j.get(k) for k in keep if k in j}
    out["chunks"] = {k: len(v) for k, v in (j.get("chunks") or {}).items()}
    out["event_types"] = j.get("event_types")
    out["n_feature_files"] = len(j.get("feature_sha256") or {})
    d = j.get("fresh_extraction_drift")
    if d:
        fr = d.get("feature_reliability", {})
        per = {}
        for k, v in (fr.get("per_extractor") or {}).items():
            s = short_extractor(k)
            per[s if s not in per else f"{s}#{len(per)}"] = v
        out["drift"] = {"pred_reliability": d.get("pred_reliability"), "pred_max_abs_diff": d.get("pred_max_abs_diff"),
                        "pred_pearson_r": d.get("pred_pearson_r"), "pred_bit_identical": d.get("pred_bit_identical"),
                        "n_arrays": fr.get("n_arrays"), "n_unreadable": len(fr.get("unreadable") or []),
                        "reliability_min": fr.get("reliability_min"), "reliability_gate": fr.get("reliability_gate"),
                        "reliability_gate_pass": fr.get("reliability_gate_pass"), "per_extractor": per,
                        "n_arrays_not_bit_identical": sum(1 for v in (fr.get("arrays") or {}).values()
                                                          if not v.get("bit_identical", False))}
    if not real:
        out["revisions"] = j.get("revisions")
    return out


def pod_bash(script: str, timeout: int = 900) -> str:
    """Run a bash script on the pod (SSM's shell is sh; this needs pipefail / bash syntax)."""
    import base64

    b64 = base64.b64encode(script.encode()).decode()
    name = f"/tmp/yct_pod_{int(time.time() * 1000)}.sh"
    pod(f"echo {b64} | base64 -d > {name}", 120)
    return pod(f"bash {name}", timeout)


def persist_cache(box: Box, pod_dir: str, labels: dict[str, str]) -> dict:
    """Box fc/ -> pod run dir + /work/yct/cache; per-entry tar (media excluded) + sha256 manifest -> S3."""
    pod(f"mkdir -p {pod_dir} /work/yct/cache && {box.ssh} 'tar cf - -C {B} fc' | tar xf - -C {pod_dir} && "
        f"cp -rn {pod_dir}/fc/. /work/yct/cache/ && du -sh {pod_dir}/fc", 3600)
    script = f"""
set -euo pipefail
cd {pod_dir}; mkdir -p fc_tar; : > fc_tar/FILES_SHA256SUMS
for e in fc/*/; do k=$(basename $e)
  (cd fc && find $k -type f -exec sha256sum {{}} + | sort -k2) >> fc_tar/FILES_SHA256SUMS
  (cd fc && find $k -type f {' '.join(f"! -name '*{x}'" for x in MEDIA)} -print0 | sort -z | tar cf ../fc_tar/$k.tar --null -T -)
done
cd fc_tar; sha256sum *.tar > TAR_SHA256SUMS
aws s3 cp --recursive --region eu-central-1 --quiet . {S3}/feature_cache/
python3 - <<'PY'
import json, os, subprocess
tars = dict(l.split()[::-1] for l in open('TAR_SHA256SUMS'))
files = [l.split(None, 1) for l in open('FILES_SHA256SUMS')]
media = {{'.mp4', '.wav', '.mkv', '.mov'}}
out = {{}}
for t, sha in sorted(tars.items()):
    k = t[:-4]
    mine = [(h, p.strip()) for h, p in files if p.startswith(k + '/')]
    out[k] = {{'tar': t, 'tar_sha256': sha, 'tar_bytes': os.path.getsize(t), 'n_files': len(mine),
              'media_excluded': [{{'sha256': h, 'ext': os.path.splitext(p)[1]}} for h, p in mine
                                 if os.path.splitext(p)[1] in media]}}
fs = subprocess.run(['sha256sum', 'FILES_SHA256SUMS'], capture_output=True, text=True).stdout.split()[0]
print(json.dumps({{'entries': out, 'files_manifest_sha256': fs}}))
PY
"""
    box_out = pod_bash(script, 3600)
    man = json.loads(box_out.strip().splitlines()[-1])
    for k, v in man["entries"].items():
        v["clip"] = labels.get(k, "unknown")
    return man


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=3.5)
    ap.add_argument("--usd-limit", type=float, default=25.0)
    ap.add_argument("--steps", default="asr,bug018,real,enh002")
    a = ap.parse_args()
    from infra import lambda_gpu as lg

    run_dir = Path(os.environ.get("YCT_RUN_DIR") or ROOT / "outputs" / "runs" / f"wave1p2b_{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    pod_dir = f"/work/yct/runs/{run_id}"
    steps = a.steps.split(",")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    price = lg.types()[ITYPE]["usd_per_hour"]
    if price * a.max_hours > a.usd_limit:
        raise SystemExit(f"{price}*{a.max_hours} h exceeds the task limit ${a.usd_limit}")
    # BUG-027: any live yct-* instance now is an orphan of a dead driver (one instance at a time) -> terminate.
    reaped, swept = lg.reap(), lg.sweep()
    if reaped or swept:
        log(f"orphans terminated at start: reap={reaped} sweep={swept}")
    if lg._live(lg.list_ours()):
        raise SystemExit("a yct-* instance is still alive after the orphan sweep; one instance at a time")
    # Pod repo at this commit (pod-side scripts + code), inputs table.
    pod(f"cd {REPO} && git fetch -q origin && git checkout -q {sha} && git rev-parse HEAD && mkdir -p {P2B} {pod_dir}", 300)
    pod(f"cd {REPO} && {PY} scripts/wave1_p2b_pod.py inputs {P2B}/inputs.csv", 300)
    reals = real_clips()
    result: dict = {"run_id": run_id, "git_sha": sha, "instance_type": ITYPE, "usd_per_hour": price, "steps": {},
                    "real_clips": reals, "real_clip_rule": "first 3 T1-eligible video_ids, sorted (label-blind)"}
    spent0 = lg.spent_usd()
    t_launch = time.time()
    iid = result["instance_id"] = lg.launch(ITYPE, "yct-wave1p2b", a.max_hours, "yct-pod", None)["id"]
    log(f"instance {iid} launched")
    watcher = None
    labels: dict[str, str] = {}
    stop_touch = threading.Event()
    result["orphans_swept_at_start"] = {"reap": reaped, "sweep": swept}
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
        box.run(f"pgrep -f gpu_heartbeat.sh >/dev/null || (nohup bash {B}/infra/gpu_heartbeat.sh >/dev/null 2>&1 "
                "</dev/null &); sleep 2; tail -1 ~/yct_heartbeat.log")
        # BUG-027 dead-man switch: the box halts itself when this driver stops touching it (or at the hard cap)
        box.run(f"touch {TOUCH}; pgrep -f gpu_deadman.sh >/dev/null || (nohup bash {B}/infra/gpu_deadman.sh "
                f"{TOUCH} {DEADMAN_GRACE_S} {int(a.max_hours * 3600)} >/dev/null 2>&1 </dev/null &); sleep 1; "
                "pgrep -f gpu_deadman.sh >/dev/null && echo deadman_up")

        def _toucher() -> None:
            while not stop_touch.wait(TOUCH_EVERY_S):
                try:
                    pod(f"{box.ssh} 'touch {TOUCH}'", 120, check=False)
                except Exception:  # noqa: BLE001 - a missed touch is covered by the grace period
                    pass

        threading.Thread(target=_toucher, daemon=True).start()
        watcher = subprocess.Popen([sys.executable, str(ROOT / "infra" / "lambda_gpu.py"), "watch"],
                                   env={**os.environ, "YCT_HB_VIA_POD": "1"},
                                   stdout=open(run_dir / "watch.log", "w"), stderr=subprocess.STDOUT)
        pod("aws ssm get-parameter --region eu-central-1 --name /yct/hf_token --with-decryption "
            "--query Parameter.Value --output text | "
            f"{box.ssh} 'mkdir -p ~/.cache/huggingface && umask 077 && cat > ~/.cache/huggingface/token "
            "&& wc -c < ~/.cache/huggingface/token'", 300)
        # audio for ASR (pod -> box), while the box sets up
        if "asr" in steps:
            pod(f"cd /work/yct/norm/audio16k && tar cf - *.wav | {box.ssh} 'mkdir -p {B}/audio && tar xf - -C {B}/audio "
                f"&& ls {B}/audio | wc -l'", 1800)
        box.start("setup", f"cp {B}/src/yct/tribe_run/remote_setup.sh {B}/; bash {B}/remote_setup.sh {B}\n"
                           f"cd {B}; source venv/bin/activate\n"
                           f"python src/yct/tribe_run/make_long_clip.py {B}/clips/long160/long160.mp4 160\n"
                           f"python src/yct/tribe_run/make_long_clip.py {B}/clips/long110/long110.mp4 110\n"
                           f"python src/yct/tribe_run/make_reference_clips.py {B}/clips/ref\n"
                           f"nvidia-smi > {B}/nvidia_smi.txt\n")
        rc = result["steps"]["setup"] = box.wait("setup", 2400)
        if rc != 0:
            raise RuntimeError("setup failed:\n" + box.cat("~/steps/setup.log")[-3000:])
        log("setup OK")
        import yaml

        wxv = yaml.safe_load((ROOT / "config.yaml").read_text())["transcribe"]["whisperx"]["version"]
        if "asr" in steps:
            box.start("wxsetup", f"""cd {B}; UV=$HOME/.uvbin/uv
[ -d wxvenv ] || $UV venv -q -p 3.11 wxvenv
source wxvenv/bin/activate
$UV pip install -q "whisperx=={wxv}" "pyyaml==6.0.3" "pydantic==2.14.3"
python -c 'import importlib.metadata as m; v=m.version("whisperx"); assert v == "{wxv}", v; print("whisperx", v)'
python -c "import nltk; nltk.download('punkt_tab', quiet=True)"
$UV pip freeze > {B}/wx_pip_freeze.txt
""")
            rc = result["steps"]["wxsetup"] = box.wait("wxsetup", 1800)
            if rc == 0:
                box.start("asr", f"""cd {B}; source wxvenv/bin/activate; export PYTHONPATH={B}/src
SP=$(python -c 'import site; print(site.getsitepackages()[0])')
export LD_LIBRARY_PATH=$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:${{LD_LIBRARY_PATH:-}}
mkdir -p asr/json
# output -> file only (WhisperX may print recognised text; the step log is tailed into the run log)
python -m yct.transcribe --out-dir asr/json --record asr/whisperx_run.json audio/*.wav > asr/asr.log 2>&1
""")
                rc = result["steps"]["asr"] = box.wait("asr", 3600)
            else:
                result.setdefault("errors", {})["wxsetup"] = box.cat("~/steps/wxsetup.log")[-3000:]
            if result["steps"].get("asr") is not None:
                result["whisperx_run"] = json.loads(
                    box.run(f"cat {B}/asr/whisperx_run.json 2>/dev/null || echo '{{}}'").strip() or "{}")
                (run_dir / "whisperx_run.json").write_text(json.dumps(result["whisperx_run"], indent=1))
                (run_dir / "wx_pip_freeze.txt").write_text(box.run(f"cat {B}/wx_pip_freeze.txt || true"))
                if rc != 0:
                    result.setdefault("errors", {})["asr"] = box.run(
                        f"grep -iE 'error|traceback|exception|cuda|cudnn' {B}/asr/asr.log | tail -n 15 || true")[-3000:]
        # BUG-018 runs on the GPU while the pod ingests transcripts
        if "bug018" in steps:
            box.start("bug018", RUN + "run long160 --video clips/long160/long160.mp4 --bug018-word-fix || rc=1\n"
                                      "run long110f --video clips/long110/long110.mp4 --bug018-word-fix || rc=1\n"
                                      "exit $rc\n")
        if result["steps"].get("asr") == 0 or "asr" not in steps:
            if "asr" in steps:
                pod(f"mkdir -p {P2B}/asr && {box.ssh} 'tar cf - -C {B}/asr .' | tar xf - -C {P2B}/asr && "
                    f"ls {P2B}/asr/json | wc -l", 900)
                ing = pod(f"cd {REPO} && {PY} scripts/wave1_p2b_pod.py ingest {P2B}/inputs.csv {P2B}/asr/json", 1800)
                result["ingest"] = json.loads(ing.strip().splitlines()[-1])
                log(f"ingest {result['ingest']}")
            # real clips + their pinned transcripts -> box; sha256 must match the transcript manifest
            names = " ".join(f"{r['content_id']}.mp4" for r in reals)
            tsvs = " ".join(f"{r['content_id']}.tsv" for r in reals)
            pod(f"cd /work/yct/norm/t1 && tar cf - {names} | {box.ssh} 'mkdir -p {B}/clips/real && tar xf - -C {B}/clips/real' && "
                f"cd /work/yct/transcripts && tar cf - {tsvs} | {box.ssh} 'tar xf - -C {B}/clips/real'", 900)
            man = dict(r.split(",") for r in pod("tail -n +2 /work/yct/transcripts/manifest.csv", 120).split()
                       if r.count(",") == 1)
            got = dict(ln.split()[::-1] for ln in pod(f"{box.ssh} 'cd {B}/clips/real && sha256sum *.tsv'", 120).splitlines()
                       if len(ln.split()) == 2)  # pod output ends with blank lines (run 1: ValueError here)
            for r in reals:
                if man.get(r["content_id"]) != got.get(f"{r['content_id']}.tsv"):
                    raise RuntimeError(f"transcript sha256 mismatch for {r['video_id']}")
            result["real_tsv_sha256_verified"] = True
        if "bug018" in steps:
            rc = result["steps"]["bug018"] = box.wait("bug018", 4800)
            log(f"step bug018 rc={rc}")
        if "real" in steps and result.get("real_tsv_sha256_verified"):
            body = "".join(f"run real_{r['content_id']} --video clips/real/{r['content_id']}.mp4 --fresh-drift "
                           f"--keep-fresh || rc=1\nrun real_{r['content_id']}_rerun --video clips/real/"
                           f"{r['content_id']}.mp4 || rc=1\n" for r in reals)
            box.start("real", RUN + body + "exit $rc\n")
            rc = result["steps"]["real"] = box.wait("real", 5400)
            log(f"step real rc={rc}")
        left_h = a.max_hours - (time.time() - t_launch) / 3600
        if "enh002" in steps and left_h > 1.2:
            box.start("enh002", RUN + "".join(
                f"run {c} --video clips/ref/{c}/{c}.mp4 {'--bug018-word-fix' if c != 'ref_face' else ''} || rc=1\n"
                for c in ("ref_control", "ref_flash", "ref_speech", "ref_face")) + "exit $rc\n")
            rc = result["steps"]["enh002"] = box.wait("enh002", 5400)
            log(f"step enh002 rc={rc}")
        elif "enh002" in steps:
            result["steps"]["enh002"] = f"skipped: {left_h:.2f} h left of the session cap"
        # numbers for the run dir (box-side): rerun identity + sanitised per-run metrics
        box.run(f"shopt -s nullglob; cd {B}; sha256sum res/*.npy > res/SHA256SUMS; "
                f"find fc -type f -exec sha256sum {{}} + | sort -k2 > res/FC_SHA256SUMS; du -sh fc res")
        pod(f"{box.ssh} 'tar cf - -C {B} res pip_freeze.txt nvidia_smi.txt clips/long160 clips/long110 clips/ref' "
            f"| tar xf - -C {pod_dir} && du -sh {pod_dir}", 1800)
        labels = {}
        runs = {}
        for r in reals:
            for suf in ("", "_rerun"):
                n = f"real_{r['content_id']}{suf}"
                txt = pod_file(f"{pod_dir}/res/{n}.json", missing_ok=True)
                if txt.strip().startswith("{"):
                    j = json.loads(txt)
                    runs[f"{r['video_id']}{suf}"] = sanitize_run(j, real=True)
                    labels[j["cache_key"]] = r["video_id"]
        for n in ("long160", "long110f", "ref_control", "ref_flash", "ref_speech", "ref_face"):
            txt = pod_file(f"{pod_dir}/res/{n}.json", missing_ok=True)
            if txt.strip().startswith("{"):
                j = json.loads(txt)
                runs[n] = sanitize_run(j, real=False)
                labels[j["cache_key"]] = n
                ev = pod_file(f"{pod_dir}/res/{n}.events.csv", missing_ok=True)
                if ev.strip():
                    (run_dir / f"{n}.events.csv").write_text(ev)
        result["runs"] = runs
        if box.run(f"ls {B}/fc | wc -l").strip() != "0":
            result["feature_cache"] = persist_cache(box, pod_dir, labels)
            (run_dir / "feature_cache_manifest.json").write_text(json.dumps(result["feature_cache"], indent=1))
        for f in ("pip_freeze.txt", "nvidia_smi.txt"):
            (run_dir / f).write_text(pod_file(f"{pod_dir}/{f}", missing_ok=True))
    except Exception as exc:  # noqa: BLE001 - always record and fall through to terminate
        result["error"] = f"{type(exc).__name__}: {exc}"[-4000:]
        log(f"ERROR {result['error'][:500]}")
    finally:
        stop_touch.set()
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
        result["instance_heartbeats"] = sum(1 for r in lg._ledger() if r["event"] == "heartbeat" and r["id"] == iid)
        log(f"terminated; alive={live}; spent this run ${result['usd_spent_this_run']}")
    post(result, run_dir, pod_dir)
    (run_dir / "child_metrics.json").write_text(json.dumps(result, indent=1, default=str))
    bad = [k for k, v in result["steps"].items() if isinstance(v, int) and v != 0]
    return 1 if result.get("error") or bad or result.get("post_errors") else 0


def post(result: dict, run_dir: Path, pod_dir: str) -> None:
    """CPU-side after the instance is gone: gates, transcripts/confounds refresh + S3, ENH-002 latency."""
    errs = result.setdefault("post_errors", {})
    runs = result.get("runs", {})
    gates = result.setdefault("gates", {})
    for n in ("long160", "long110f"):
        if n in runs:
            r = runs[n]
            wc = r.get("bug018_word_check") or {}
            gates[f"bug018_{n}"] = {"pass": bool(wc.get("ok") and r.get("T_within_1")), "duration_s": r.get("duration_s"),
                                    "T": (r.get("shape") or [None])[0], "n_words": wc.get("n_words"),
                                    "n_tsv_rows": wc.get("n_tsv_rows"), "word_start_max_s": wc.get("word_start_max_s"),
                                    "duplicates": wc.get("n_duplicate_text_start"),
                                    "words_after_duration": wc.get("words_after_duration"), "chunks": r.get("chunks")}
    for rc in result.get("real_clips", []):
        a, b = runs.get(rc["video_id"]), runs.get(f"{rc['video_id']}_rerun")
        if a and b:
            d = a.get("drift") or {}
            gates[f"d038_{rc['video_id']}"] = {
                "cached_rerun_bit_identical": a["pred_sha256"] == b["pred_sha256"] and b.get("cache_reused") is True,
                "fresh_reliability_min": d.get("reliability_min"), "fresh_gate_pass": d.get("reliability_gate_pass"),
                "pred_reliability_fresh": d.get("pred_reliability"), "pred_max_abs_diff_fresh": d.get("pred_max_abs_diff"),
                "n_arrays": d.get("n_arrays"), "n_arrays_not_bit_identical": d.get("n_arrays_not_bit_identical")}
    if "ingest" in result:
        try:
            out = pod(f"cd {REPO} && {PY} scripts/wave1_p2b_pod.py confounds {P2B}/inputs.csv && "
                      f"{PY} /work/yct/scripts/wave1_summ.py /work/yct/summaries", 3600)
            result["confounds_refresh"] = out.strip().splitlines()[-1][:400]
            pod(f"aws s3 cp --region eu-central-1 --quiet --recursive /work/yct/transcripts {S3}/transcripts/ "
                f"--exclude 'wer_pending/*' && aws s3 cp --region eu-central-1 --quiet --recursive {P2B}/asr "
                f"{S3}/transcripts/whisperx_raw/ && "
                f"for k in t1 t3 summary; do aws s3 cp --region eu-central-1 --quiet --recursive /work/yct/confounds/$k "
                f"{S3}/confounds/$k/; done && aws s3 cp --region eu-central-1 --quiet --recursive /work/yct/summaries "
                f"{S3}/summaries/", 3600)
            for f in ("wave1_transcripts_summary.csv", "wave1_confounds_summary.csv"):
                (ROOT / "data" / f).write_text(pod_file(f"/work/yct/summaries/{f}"))
            result["wer"] = {"status": "pending hand-check (owner/human)",
                             "hypotheses_at": "/work/yct/transcripts/wer_pending/ (pod only)",
                             "videos": result["ingest"].get("wer_pending")}
        except Exception as exc:  # noqa: BLE001
            errs["transcripts_confounds"] = f"{type(exc).__name__}: {exc}"[-2000:]
    if "ref_flash" in runs and "ref_control" in runs:
        try:
            loc = run_dir / "enh002_preds"
            loc.mkdir(exist_ok=True)
            files = [f"res/{c}.{x}" for c in ("ref_control", "ref_flash", "ref_speech", "ref_face")
                     for x in ("npy", "segments.csv")] + ["clips/ref/enh002.json"]
            pod("; ".join(f"aws s3 cp --region eu-central-1 --quiet {pod_dir}/{f} {S3}/enh002/{result['run_id']}/"
                          f"{Path(f).name} || true" for f in files), 1800)
            subprocess.run(["aws", "s3", "cp", "--recursive", "--quiet", "--region", "eu-central-1",
                            f"{S3}/enh002/{result['run_id']}/", str(loc)], check=True)
            sys.path.insert(0, str(ROOT / "src"))
            from yct.tribe_run.enh002 import main as enh

            res = enh(str(loc), str(run_dir))
            result["enh002_latency"] = {m: {c: v["latency"] for c, v in d.items()} for m, d in res["maps"].items()}
            for p in loc.glob("*.npy"):
                p.unlink()  # large; archived in S3 enh002/<run_id>/
        except Exception as exc:  # noqa: BLE001
            errs["enh002"] = f"{type(exc).__name__}: {exc}"[-2000:]
    if not errs:
        result.pop("post_errors")


if __name__ == "__main__":
    sys.exit(main())
