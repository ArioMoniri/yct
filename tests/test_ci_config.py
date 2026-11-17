"""CI must run every test with every extra, the same pinned ruff, cached atlases and no silent skips
(QA/Watchdog G-D032; BUG-007, BUG-008)."""
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
LOCK = ROOT / "requirements.lock"


def _steps() -> list[dict]:
    return yaml.safe_load(CI.read_text())["jobs"]["test"]["steps"]


def _run_text() -> str:
    return "\n".join(s.get("run", "") for s in _steps())


def _lock_pins() -> dict[str, list[str]]:
    pins: dict[str, list[str]] = {}
    for m in re.finditer(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", LOCK.read_text(), re.M):
        pins.setdefault(m.group(1).lower(), []).append(m.group(2))
    return pins


def test_ruff_pinned_identically_in_pyproject_and_lock():
    dev = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]["dev"]
    ruff = [d for d in dev if d.startswith("ruff")]
    assert len(ruff) == 1 and re.fullmatch(r"ruff==\d+\.\d+\.\d+", ruff[0]), ruff
    assert _lock_pins()["ruff"] == [ruff[0].split("==")[1]]
    assert "ruff==" not in _run_text()  # CI gets ruff only from the lock, so versions cannot diverge


def test_lock_covers_all_extras_fully_pinned():
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    pins = _lock_pins()
    names = [re.split(r"[<>=!~\[ ]", d)[0].lower() for d in proj["dependencies"]]
    for extra in ("dev", "pre", "neuro"):
        names += [re.split(r"[<>=!~\[ ]", d)[0].lower() for d in proj["optional-dependencies"][extra]]
    missing = [n for n in names if n not in pins]
    assert not missing, missing
    reqs = [ln for ln in LOCK.read_text().splitlines() if re.match(r"^[A-Za-z0-9]", ln)]
    assert reqs and all("==" in ln for ln in reqs)
    assert "--hash=sha256:" in LOCK.read_text()


def test_ci_installs_from_lock_with_hashes():
    run = _run_text()
    assert "pip install --require-hashes -r requirements.lock" in run
    assert "pip install --no-deps -e ." in run


def test_ci_caches_and_fetches_atlases_and_never_sets_offline():
    steps = _steps()
    cache = [s for s in steps if str(s.get("uses", "")).startswith("actions/cache@")]
    assert cache and cache[0]["with"]["path"] == "~/.cache/yct/atlases"
    assert "fetch_atlases.py --key" in _run_text() and "steps.atlas.outputs.key" in cache[0]["with"]["key"]
    assert "python scripts/fetch_atlases.py\n" in _run_text() + "\n"
    assert "YCT_OFFLINE" not in CI.read_text()


def test_ci_runs_lint_tests_and_guards():
    run = _run_text()
    assert "ruff check ." in run and "make test" in run and "make guards" in run
    names = [s.get("name", "") for s in _steps()]
    assert names.index("Lint") < next(i for i, n in enumerate(names) if n.startswith("Tests"))
