"""Every ffmpeg invocation in the repo passes -nostdin (FIX-D032-1; ffmpeg otherwise eats stdin
of the enclosing shell/SSM session and can hang or corrupt batch loops)."""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = ("data/sealed/",)


def _tracked(*globs: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", *globs], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / p for p in out if not p.startswith(SKIP_DIRS) and (ROOT / p).is_file()]


def _py_ffmpeg_lists(path: Path) -> list[tuple[int, list]]:
    """List literals whose first element is the string 'ffmpeg' (argv construction)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.List) and node.elts:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and first.value == "ffmpeg":
                vals = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                found.append((node.lineno, vals))
    return found


def test_python_ffmpeg_calls_use_nostdin():
    bad = []
    n = 0
    for p in _tracked("*.py"):
        for line, vals in _py_ffmpeg_lists(p):
            n += 1
            if "-nostdin" not in vals:
                bad.append(f"{p.relative_to(ROOT)}:{line}")
    assert n >= 8, f"scanner found only {n} ffmpeg argv lists; is it broken?"
    assert not bad, f"ffmpeg without -nostdin: {bad}"


SH_FF = re.compile(r"(^|[\s;|&(`$\"'=])ffmpeg(\s|$)")


def test_shell_ffmpeg_calls_use_nostdin():
    bad = []
    for p in _tracked("*.sh", "Makefile", "*.yml", "*.yaml"):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if SH_FF.search(code) and "apt-get" not in code and "-nostdin" not in code:
                bad.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not bad, f"ffmpeg without -nostdin: {bad}"
