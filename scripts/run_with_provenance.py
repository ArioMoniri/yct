#!/usr/bin/env python3
"""Run a command and record its provenance in outputs/runs/<run_id>/ (v2.md §3: no result without a run dir).

Writes: cmd (JSON argv), git_sha (HEAD), config_sha (sha256 of config.yaml), exit_code, stdout.log
(stdout+stderr, also echoed to the console) and metrics.json (exit code, start/end, wall time, git dirty
state + sha256 of `git diff HEAD`, and pytest pass/fail/skip counts when the output has a pytest summary).
The command's exit code is propagated; an existing run dir is never overwritten (exit 2).

Usage: python scripts/run_with_provenance.py [--run-id ID] [--out-root outputs/runs] -- CMD ARGS...
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
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
    diff = _git("diff", "HEAD")
    untracked = _git("ls-files", "--others", "--exclude-standard").split()
    cfg = ROOT / "config.yaml"
    (d / "cmd").write_text(json.dumps(cmd) + "\n")
    (d / "git_sha").write_text(git_sha + "\n")
    cfg_sha = hashlib.sha256(cfg.read_bytes()).hexdigest() if cfg.exists() else ""
    (d / "config_sha").write_text(cfg_sha + "\n")

    t0 = time.time()
    with open(d / "stdout.log", "w") as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = proc.wait()
    wall = time.time() - t0
    (d / "exit_code").write_text(f"{rc}\n")
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
        "pytest": pytest_counts((d / "stdout.log").read_text()),
    }
    (d / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    print(f"provenance: {d} (exit {rc})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
