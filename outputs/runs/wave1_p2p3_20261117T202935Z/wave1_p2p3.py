"""Wave-1 P2 normalisation + P3 confounds driver (pod side). Calls the project CLIs per video.

Layout: /work/yct/norm/{t1,q480,t3,audio16k,records,runlog}, /work/yct/confounds/{t1,t3}/<hash>.parquet.
Resumable: a video with runlog/<id>.done is skipped. No titles / outcomes are read or written.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAW, N, C = Path("/work/yct/raw"), Path("/work/yct/norm"), Path("/work/yct/confounds")
REPO = Path("/work/yct/repo")
PY = sys.executable
for d in ("t1", "records", "runlog"):
    (N / d).mkdir(parents=True, exist_ok=True)
for d in ("t1", "t3", "summary"):
    (C / d).mkdir(parents=True, exist_ok=True)

ids = []
with open(REPO / "data/manifest.csv") as f:
    for r in csv.DictReader(f):
        if r["in_primary"].strip().lower() == "true":
            ids.append(r["video_id"])
stage = sys.argv[1] if len(sys.argv) > 1 else "all"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def normalise(vid):
    src = RAW / f"{vid}.mp4"
    done = N / "runlog" / f"{vid}.done"
    if done.exists():
        return
    if not src.exists():
        (N / "runlog" / f"{vid}.missing").write_text("no raw file\n")
        log(vid, "MISSING")
        return
    t = time.time()
    p = subprocess.run([PY, "-m", "yct.normalize", "--in", str(src), "--out", str(N)],
                       cwd=REPO, capture_output=True, text=True)
    (N / "runlog" / f"{vid}.err").write_text(p.stderr[-20000:])
    if p.returncode != 0:
        (N / "runlog" / f"{vid}.failed").write_text(p.stderr[-4000:])
        log(vid, "FAILED", p.stderr.strip().splitlines()[-1:] if p.stderr else "")
        return
    rec = json.loads(p.stdout)
    h = rec["video_id"]
    mp4 = Path(rec["path"])
    dest = N / "t1" / mp4.name
    shutil.move(str(mp4), dest)            # T1 mp4 -> t1/ (the CLI writes it to the out root)
    rec["path"] = str(dest)
    rec["manifest_video_id"] = vid
    (N / f"{h}.json").unlink(missing_ok=True)
    (N / "records" / f"{h}.json").write_text(json.dumps(rec, indent=2, default=float))
    (N / "runlog" / f"{vid}.failed").unlink(missing_ok=True)
    done.write_text(h + "\n")
    log(vid, "ok", h, f"{time.time() - t:.0f}s", ",".join(rec["flags"]))


def confounds(vid):
    done = N / "runlog" / f"{vid}.done"
    if not done.exists():
        return
    h = done.read_text().strip()
    rec = json.loads((N / "records" / f"{h}.json").read_text())
    jobs = [("t1", rec["path"])]
    if rec.get("t3"):
        jobs.append(("t3", rec["t3"]["t3_path"]))
    for kind, mp4 in jobs:
        out = C / kind / f"{Path(mp4).stem}.parquet"
        summ = C / "summary" / f"{vid}.{kind}.json"
        if out.exists() and summ.exists():
            continue
        t = time.time()
        p = subprocess.run([PY, "-m", "yct.confounds", "--mp4", mp4, "--wav", rec["wav_path"],
                            "--out", str(out)], cwd=REPO, capture_output=True, text=True)
        if p.returncode != 0:
            (C / "summary" / f"{vid}.{kind}.failed").write_text(p.stderr[-4000:])
            log(vid, kind, "CONFOUNDS FAILED", p.stderr.strip().splitlines()[-1:] if p.stderr else "")
            continue
        s = json.loads(p.stdout)
        s.update(manifest_video_id=vid, content_id=h, copy=kind)
        summ.write_text(json.dumps(s, indent=2, default=float))
        log(vid, kind, "confounds ok", f"{time.time() - t:.0f}s")


log("in_primary ids:", len(ids), "stage:", stage)
if stage in ("all", "norm"):
    for v in ids:
        normalise(v)
if stage in ("all", "conf"):
    for v in ids:
        confounds(v)
log("DONE")
