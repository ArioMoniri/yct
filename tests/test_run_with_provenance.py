"""scripts/run_with_provenance.py: every claimed run has outputs/runs/<run_id>/ (v2.md §3 Provenance)."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts" / "run_with_provenance.py"


def _run(tmp_path, *cmd, run_id="r1"):
    return subprocess.run([sys.executable, str(S), "--out-root", str(tmp_path), "--run-id", run_id, "--",
                           *cmd], cwd=ROOT, capture_output=True, text=True)


def test_writes_all_provenance_files_and_propagates_exit_code(tmp_path):
    code = ("import sys; print('hello'); print('err', file=sys.stderr); "
            "print('7 passed, 2 skipped in 1.0s'); sys.exit(3)")
    res = _run(tmp_path, sys.executable, "-c", code)
    assert res.returncode == 3
    d = tmp_path / "r1"
    for f in ("cmd", "git_sha", "config_sha", "exit_code", "stdout.log", "metrics.json"):
        assert (d / f).is_file(), f
    assert (d / "exit_code").read_text().strip() == "3"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout
    assert (d / "git_sha").read_text().strip() == head.strip()
    cfg_sha = hashlib.sha256((ROOT / "config.yaml").read_bytes()).hexdigest()
    assert (d / "config_sha").read_text().strip() == cfg_sha
    assert json.loads((d / "cmd").read_text())[-1] == code
    log = (d / "stdout.log").read_text()
    assert "hello" in log and "err" in log
    m = json.loads((d / "metrics.json").read_text())
    assert m["exit_code"] == 3 and m["pytest"] == {"passed": 7, "skipped": 2}
    assert isinstance(m["git_dirty"], bool) and m["wall_s"] >= 0
    assert "hello" in res.stdout  # still echoed to the console


def test_refuses_to_overwrite_existing_run(tmp_path):
    assert _run(tmp_path, sys.executable, "-c", "pass").returncode == 0
    res = _run(tmp_path, sys.executable, "-c", "pass")
    assert res.returncode == 2 and "exists" in res.stdout + res.stderr


def test_makefile_test_target_uses_provenance():
    mk = (ROOT / "Makefile").read_text()
    body = mk.split("\ntest:", 1)[1].split("\n\n", 1)[0]
    assert "run_with_provenance.py" in body and "pytest" in body
