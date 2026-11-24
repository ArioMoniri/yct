"""BUG-050b offline repro: does restoring a stored feature-cache tar and re-archiving it change its bytes?

Reads only tar member metadata and file bytes for hashing (no feature/prediction values are parsed).
Usage: python -I scripts/bug050b_repro.py STORED.tar WORKDIR
Prints, for each tarfile extraction filter, the sha256 of the re-archived tar and the set of file modes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

MEDIA = (".mp4", ".wav", ".mkv", ".mov")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def retar(root: Path, key: str, out: Path) -> str:
    """Same member loop as cache_archive.archive_entry (minus verify and media)."""
    entry = root / key
    files = sorted(p for p in entry.rglob("*") if p.is_file())
    rels = [f"{key}/{p.relative_to(entry).as_posix()}" for p in files]
    with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tf:
        for r, p in sorted(zip(rels, files, strict=True)):
            if r.endswith(MEDIA):
                continue
            ti = tf.gettarinfo(str(p), arcname=r)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.mtime = 0
            with open(p, "rb") as f:
                tf.addfile(ti, f)
    return sha(out)


def main(src: str, work: str) -> dict:
    src_p = Path(src)
    with tarfile.open(src_p) as tf:
        stored_modes = sorted({oct(m.mode) for m in tf.getmembers() if m.isfile()})
        key = tf.getmembers()[0].name.split("/")[0]
    out = {"stored_sha256": sha(src_p), "stored_modes": stored_modes, "umask": oct(os.umask(0o022))}
    os.umask(int(out["umask"], 8))
    for flt in ("data", "tar", "fully_trusted"):
        with tempfile.TemporaryDirectory(dir=work) as td:
            with tarfile.open(src_p) as tf:
                tf.extractall(td, filter=flt)
            modes = sorted({oct(os.stat(p).st_mode & 0o7777) for p in Path(td).rglob("*") if p.is_file()})
            out[flt] = {"retar_sha256": retar(Path(td), key, Path(td) / "re.tar"), "file_modes": modes}
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1))
