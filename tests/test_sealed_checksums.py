"""Every data/sealed/*.sha256 verifies with `cd data/sealed && sha256sum -c` (BUG-016, FIX-P1).

Only ciphertext hashes are checked; nothing is decrypted."""
import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SEALED = Path(__file__).resolve().parents[1] / "data" / "sealed"
SUMS = sorted(SEALED.glob("*.sha256"))
LINE = re.compile(r"^([0-9a-f]{64})  ([^/\s]+)$")


def test_every_archive_has_a_checksum():
    assert SUMS, "no sealed checksum files"
    for age in SEALED.glob("*.age"):
        assert (SEALED / f"{age.name}.sha256").is_file(), age.name


@pytest.mark.parametrize("path", SUMS, ids=[p.name for p in SUMS])
def test_checksum_line_is_relative_and_matches(path):
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    m = LINE.match(lines[0])
    assert m, f"{path.name}: expected '<sha256>  <bare file name>' (relative to data/sealed)"
    digest, name = m.groups()
    assert name == path.name[: -len(".sha256")]
    assert hashlib.sha256((SEALED / name).read_bytes()).hexdigest() == digest


def test_sha256sum_c_in_sealed_dir():
    assert shutil.which("sha256sum"), "coreutils sha256sum required (CI: ubuntu)"
    res = subprocess.run(["sha256sum", "-c", *[p.name for p in SUMS]], cwd=SEALED, capture_output=True,
                         text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "could not be read" not in res.stderr
