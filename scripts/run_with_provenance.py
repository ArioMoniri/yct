#!/usr/bin/env python3
"""Run a command and record its provenance in outputs/runs/<run_id>/ (v2.md §3: no result without a run dir).

Writes: cmd (JSON argv), git_sha (HEAD), config_sha (sha256 of config.yaml), exit_code, stdout.log
(stdout+stderr, also echoed to the console), metrics.json (exit code, start/end, wall time, git dirty
state + sha256 of `git diff HEAD` (a dirty tree also gets git_diff.patch + untracked_sha256.txt),
requirements.lock sha256, platform, `pip freeze` sha256 (the list is
saved as pip_freeze.txt), and pytest pass/fail/skip counts when the output has a pytest summary) and
report.md. The child gets YCT_RUN_DIR=<run dir>; if it writes child_metrics.json there, that JSON is
merged into metrics.json under "result", and a report.md it writes is kept (else a minimal one is
generated). The command's exit code is propagated; an existing run dir is never overwritten (exit 2).

Usage: python scripts/run_with_provenance.py [--run-id ID] [--out-root outputs/runs] -- CMD ARGS...
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected|warnings?)\b")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def pytest_counts(log: str) -> dict[str, int] | None:
    lines = [ln for ln in log.splitlines() if re.search(r"\d+ (passed|failed|errors?)\b.* in [\d.]+s", ln)]
    if not lines:
        return None
    out: dict[str, int] = {}
    for n, kind in SUMMARY.findall(lines[-1]):
        kind = {"error": "errors", "warning": "warnings"}.get(kind, kind)
        out[kind] = int(n)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--out-root", default=str(ROOT / "outputs" / "runs"))
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("no command given (use -- CMD ...)")
    started = dt.datetime.now(dt.UTC)
    run_id = a.run_id or f"run_{started:%Y%m%dT%H%M%SZ}"
    d = Path(a.out_root) / run_id
    if d.exists():
        print(f"ERROR run dir {d} exists; refusing to overwrite", file=sys.stderr)
        return 2
    d.mkdir(parents=True)
    git_sha = _git("rev-parse", "HEAD").strip()
    # BUG-024: never capture data/ or CSVs (manifest/curation/sealed) in provenance diffs — blinding.
    excl = [":(exclude)data", ":(exclude)*.csv", ":(exclude)*.age"]
    diff = _git("diff", "HEAD", "--", ".", *excl)
    untracked = [u for u in _git("ls-files", "--others", "--exclude-standard").split()
                 if not u.startswith("data/") and not u.endswith((".csv", ".age"))]
    cfg = ROOT / "config.yaml"
    if diff.strip() or untracked:  # dirty tree: keep the exact uncommitted state next to the run
        (d / "git_diff.patch").write_text(diff)
        (d / "untracked_sha256.txt").write_text("".join(
            f"{hashlib.sha256((ROOT / u).read_bytes()).hexdigest()}  {u}\n" for u in untracked
            if (ROOT / u).is_file()))
    (d / "cmd").write_text(json.dumps(cmd) + "\n")
    (d / "git_sha").write_text(git_sha + "\n")
    cfg_sha = hashlib.sha256(cfg.read_bytes()).hexdigest() if cfg.exists() else ""
    (d / "config_sha").write_text(cfg_sha + "\n")

    t0 = time.time()
    with open(d / "stdout.log", "w") as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                bufsize=1, env={**os.environ, "YCT_RUN_DIR": str(d.resolve())})
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = proc.wait()
    wall = time.time() - t0
    (d / "exit_code").write_text(f"{rc}\n")
    lock = ROOT / "requirements.lock"
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout
    (d / "pip_freeze.txt").write_text(freeze)
    child = d / "child_metrics.json"
    metrics = {
        "run_id": run_id,
        "exit_code": rc,
        "started_utc": started.isoformat(),
        "wall_s": round(wall, 3),
        "git_sha": git_sha,
        "git_dirty": bool(diff.strip() or untracked),
        "git_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "untracked_files": untracked,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "requirements_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
        "pip_freeze_sha256": hashlib.sha256(freeze.encode()).hexdigest(),
        "pytest": pytest_counts((d / "stdout.log").read_text()),
    }
    if child.exists():
        metrics["result"] = json.loads(child.read_text())
    (d / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    if not (d / "report.md").exists():
        (d / "report.md").write_text(
            f"# Run {run_id}\n\n- cmd: `{' '.join(cmd)}`\n"
            f"- git_sha: `{git_sha}` (dirty: {metrics['git_dirty']})\n"
            f"- config_sha: `{cfg_sha}`\n- exit_code: {rc}\n- wall_s: {metrics['wall_s']}\n"
            f"- pytest: {metrics['pytest']}\n")
    print(f"provenance: {d} (exit {rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
