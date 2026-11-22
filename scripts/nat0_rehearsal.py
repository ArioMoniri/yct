#!/usr/bin/env python3
"""T-NAT0 pod CPU rehearsal of the real session-0 box path, $0 and no GPU (council D-082 W3 / referee /
biostat B3 / neuro B3 / QA §3). Run ON THE POD from a checkout at the D-082 freeze commit, with the yct pod
venv (numpy, yaml) as the interpreter:

    /work/yct/venv/bin/python scripts/nat0_rehearsal.py OUT.json [--n-wavs 3]

Steps, in order; every step's result goes to OUT.json (numbers, shas, names only; no transcript text):
  a  buffer files: for every CPU-pass t1_name in the committed NAT log, T1_DIR/<t1>.mp4 and
     WAV_DIR/<t1>.wav exist, the wav sha256 equals the logged wav_sha256, and nat0_box.read_wav accepts it
  b  the exact ship tarball (gpu_p4b_nat0.ship_tarball(ship_list())) untarred into a fresh dir; a fresh uv
     (installed exactly as the box's setup_wx does, into that dir); a fresh venv from the committed freeze;
     nltk punkt_tab
  c  the exact push_buffer mirror sync into the fresh dir, then nat0_box.check_mirror on the four frozen
     shas (box_shas, the JSON the nat0 step passes)
  d  `python -m yct.curate.nat0_box --device cpu` in the fresh venv on N buffer wavs, with that --shas
     JSON; the output is read back and must hold finite lang_probs and segments for each wav
  e  offline: in the fresh venv, after faster_whisper is imported, nat0_box.enforce_offline() makes
     huggingface_hub refuse a download
  f  yct.transcribe from the untarred tree on 1 wav (CPU: the untarred config's whisperx device/compute
     type set to cpu/int8 for the rehearsal only; the box runs cuda/float16)
  g  N3 via the exact gpu_p4b_nat0.n3_cmd on 1 buffer mp4 -> a finite float
  h  ns.session0_rows on the step-d JSON + the step-g N3, dry: nothing is written to any log
Exit 0 iff every step passed."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from yct.config import load_config  # noqa: E402
from yct.curate import nat0_box as nb  # noqa: E402
from yct.curate import natstim as ns  # noqa: E402


def sh(cmd: str, timeout: int = 7200, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", "set -euo pipefail\n" + cmd], capture_output=True, text=True,
                          timeout=timeout, env=env)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    import gpu_p4b_nat0 as drv

    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n-wavs", type=int, default=3)
    ap.add_argument("--work", default="/work/yct/nat0_rehearsal")
    a = ap.parse_args(argv)
    cfg = load_config()
    res: dict = {"git_head": sh(f"git -C {ROOT} rev-parse HEAD").stdout.strip(), "steps": {}}
    ok = True

    def done(name: str, passed: bool, **info) -> None:
        nonlocal ok
        ok = ok and passed
        res["steps"][name] = {"ok": passed, **info}
        Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))

    log = ns.load_log(ROOT / cfg["controls"]["refclips_auto"]["logs"]["nat"])
    rows = [r for r in ns.cpu_rows(log) if r["decision"] == "pass"]
    buf = ns.buffer_ids(log, cfg)
    # a: buffer files
    bad = []
    for r in rows:
        t1 = r["t1_name"]
        mp4, wav = Path(drv.T1_DIR) / f"{t1}.mp4", Path(drv.WAV_DIR) / f"{t1}.wav"
        if not mp4.is_file() or not wav.is_file():
            bad.append([t1, "missing"])
        elif sha256(wav) != r.get("wav_sha256"):
            bad.append([t1, "wav_sha256"])
        else:
            try:
                nb.read_wav(wav)
            except SystemExit as e:
                bad.append([t1, f"read_wav: {e}"])
    done("a_buffer_files", not bad and len(rows) == len(buf), n_buffer=len(buf),
         complete=ns.buffer_complete(log, cfg), bad=bad)
    # b: ship tarball + fresh uv + fresh venv from the freeze
    Path(a.work).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="r_", dir=a.work))
    box = work / "yct"
    box.mkdir()
    data = drv.ship_tarball(drv.ship_list())
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(box, filter="data")
    uvdir = work / ".uvbin"
    r = sh(f"curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR={uvdir} UV_NO_MODIFY_PATH=1 sh "
           f">/dev/null && cd {box} && {uvdir}/uv venv -q -p 3.11 wxvenv && "
           f"{uvdir}/uv pip install -q --python wxvenv/bin/python -r {box}/{drv.FREEZE} && "
           "wxvenv/bin/python -c \"import nltk; nltk.download('punkt_tab', quiet=True)\"")
    done("b_ship_uv_venv", r.returncode == 0, tarball_sha256=hashlib.sha256(data).hexdigest(),
         n_files=len(tarfile.open(fileobj=io.BytesIO(data)).getnames()), work=str(work), err=r.stderr[-1500:])
    if r.returncode != 0:
        return 1
    py = str(box / "wxvenv" / "bin" / "python")
    env = {**os.environ, "PYTHONPATH": str(box / "src")}
    # c: exact mirror sync + check_mirror on the frozen shas
    mirror = box / "nat" / "mirror"
    r = sh(f"mkdir -p {mirror} && {drv.mirror_sync_cmd(cfg, str(mirror) + '/')}")
    shas = drv.box_shas(cfg)
    try:
        nb.check_mirror(mirror, json.loads(shas))
        cm = None
    except (SystemExit, KeyError) as e:
        cm = str(e)
    done("c_mirror", r.returncode == 0 and cm is None, shas=json.loads(shas), err=(cm or r.stderr[-500:]))
    # d: nat0_box --device cpu on N wavs, read back
    wavs = box / "nat" / "wavs"
    wavs.mkdir(parents=True)
    pick = buf[:a.n_wavs]
    for t1 in pick:
        (wavs / f"{t1}.wav").symlink_to(Path(drv.WAV_DIR) / f"{t1}.wav")
    out = box / "nat" / "nat0.json"
    r = subprocess.run([py, "-m", "yct.curate.nat0_box", "--wavs", str(wavs), "--mirror", str(mirror),
                        "--shas", shas, "--out", str(out), "--device", "cpu"], capture_output=True, text=True,
                       cwd=box, env=env, timeout=7200)
    gpu, good = None, False
    if r.returncode == 0:
        gpu = json.loads(out.read_text())
        good = set(gpu["results"]) == set(pick) and all(
            all(math.isfinite(v) for v in g["lang_probs"].values()) and
            all(math.isfinite(s) and math.isfinite(e) for s, e, _ in g["segments"])
            for g in gpu["results"].values())
    got = (gpu or {"results": {}})["results"]
    done("d_nat0_box_cpu", r.returncode == 0 and good, rc=r.returncode, n=len(pick), stdout=r.stdout[-300:],
         err=r.stderr[-1500:] if r.returncode else "",
         p_en={k: round(v["lang_probs"].get("en", 0.0), 4) for k, v in got.items()},
         n_turns={k: len(v["segments"]) for k, v in got.items()},
         whisper_model=(gpu or {}).get("whisper_model"), out_bytes=out.stat().st_size if out.exists() else 0)
    # e: offline enforced after faster_whisper imported huggingface_hub
    probe = ("import faster_whisper, huggingface_hub as h\n"
             "from yct.curate import nat0_box as nb\nnb.enforce_offline()\n"
             "try:\n    h.hf_hub_download('gpt2', 'config.json', revision='main')\n    print('DOWNLOADED')\n"
             "except Exception as e:\n    print('REFUSED', type(e).__name__)\n")
    r = subprocess.run([py, "-c", probe], capture_output=True, text=True, cwd=box, env=env, timeout=600)
    done("e_offline", r.stdout.strip().startswith("REFUSED"), out=r.stdout.strip()[-200:],
         err=r.stderr[-500:] if r.returncode else "")
    # f: yct.transcribe on 1 wav from the untarred tree (cpu/int8 for the rehearsal only)
    import yaml

    c = yaml.safe_load((box / "config.yaml").read_text())
    c["transcribe"]["whisperx"].update(device="cpu", compute_type="int8")
    (box / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    asr = box / "nat" / "asr"
    r = subprocess.run([py, "-m", "yct.transcribe", "--out-dir", str(asr), "--record",
                        str(box / "nat" / "asr_run.json"), str(wavs / f"{pick[0]}.wav")],
                       capture_output=True, text=True, cwd=box, env=env, timeout=7200)
    produced = sorted(p.name for p in asr.glob("*")) if asr.exists() else []
    done("f_transcribe_cpu", r.returncode == 0 and bool(produced), rc=r.returncode, files=produced,
         err=r.stderr[-1500:] if r.returncode else "")
    # g: N3 via the exact n3_cmd
    r = sh(drv.n3_cmd(pick[0]), timeout=3600)
    n3 = None
    try:
        n3 = ns.n3_value(json.loads(r.stdout.strip().splitlines()[-1]), cfg)
    except Exception as e:  # noqa: BLE001 - recorded
        res["n3_error"] = f"{type(e).__name__}: {e}"[-500:]
    done("g_n3", n3 is not None and math.isfinite(n3), value=n3, err=r.stderr[-500:] if r.returncode else "")
    # h: session0_rows dry (nothing written)
    before = sha256(ROOT / cfg["controls"]["refclips_auto"]["logs"]["nat"])
    srows, stop = [], None
    if gpu:
        try:
            srows = ns.session0_rows(pick, gpu["results"], lambda i: n3, cfg)
        except ns.Session0Stop as s:          # expected with N < nat_n wavs
            srows, stop = s.rows, str(s)
    after = sha256(ROOT / cfg["controls"]["refclips_auto"]["logs"]["nat"])
    done("h_session0_rows_dry", bool(srows) and before == after, n_rows=len(srows),
         decisions=[[x["t1_name"], x["decision"], x.get("rule")] for x in srows], stop=stop,
         log_unchanged=before == after)
    res["ok"] = ok
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({k: v["ok"] for k, v in res["steps"].items()}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
