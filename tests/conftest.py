"""Shared fixtures for the P0 integrity-guard tests: throwaway git repos in tmp_path."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Agent",
    "GIT_AUTHOR_EMAIL": "agent@example.invalid",
    "GIT_COMMITTER_NAME": "Agent",
    "GIT_COMMITTER_EMAIL": "agent@example.invalid",
}


class Repo:
    """Minimal git driver for building fixture histories."""

    def __init__(self, path: Path):
        self.path = path
        self.env = {**os.environ, **_GIT_ENV}

    def git(self, *args: str, check: bool = True) -> str:
        res = subprocess.run(["git", *args], cwd=self.path, env=self.env, capture_output=True, text=True)
        if check and res.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr}")
        return res.stdout.strip()

    def write(self, rel: str, content: str) -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def append(self, rel: str, content: str) -> None:
        with open(self.path / rel, "a") as fh:
            fh.write(content)

    def rm(self, rel: str) -> None:
        self.git("rm", "-q", rel)

    def commit(self, msg: str, files: dict[str, str] | None = None) -> str:
        for rel, content in (files or {}).items():
            self.write(rel, content)
        self.git("add", "-A")
        args = ["commit", "-q", "--allow-empty", "-m", msg]
        self.git(*args)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def tag(self, name: str, ref: str = "HEAD") -> None:
        self.git("tag", name, ref)

    def run_script(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.path, env=self.env, capture_output=True, text=True,
        )


@pytest.fixture
def repo(tmp_path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    r = Repo(path)
    r.git("init", "-q", "-b", "main")
    r.commit("root", {"README.md": "fixture\n"})
    return r
