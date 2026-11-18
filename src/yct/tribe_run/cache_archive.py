"""Off-box archive and restore of content-addressed feature-cache entries (FIX-P4E; QA P4-entry D8/D9).

The S3 derived/ prefix holds no media (D-060), so an archived entry is
  * ``<key>.tar``: every file of ``<root>/<key>/`` except media (clip copy, TRIBE's sidecar .wav), with
    member names ``<key>/...``;
  * ``FILES_SHA256SUMS`` text (``<sha256>  <key>/<rel>`` per line, sorted, media included), whose sha256
    the P4 manifest records;
and the media files are kept pod-side (``save_media``; content-addressed by sha256).

``restore_entry`` rebuilds the entry on a new box: safe extraction into a temp dir, re-insert each media
file by its sha256, check every file against the sums (no missing, extra or changed file), move into place
atomically and run ``FeatureStore.verify``. Anything else raises ``ArchiveError`` and leaves nothing behind.
An identical entry already present is a no-op; a differing one is never overwritten.

CLI (box/pod):  python -m yct.tribe_run.cache_archive archive ROOT KEY OUT.tar   -> JSON (stdout)
                python -m yct.tribe_run.cache_archive save-media ROOT KEY MEDIA_DIR
                python -m yct.tribe_run.cache_archive restore TAR SUMS ROOT MEDIA...  -> key (stdout)
"""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from yct.tribe_run.feature_cache import FeatureStore, sha256_file

MEDIA_SUFFIXES = (".mp4", ".wav", ".mkv", ".mov")


class ArchiveError(RuntimeError):
    """An archive or its restore is inconsistent (missing media, sha256 mismatch, unsafe member)."""


def _files(entry: Path) -> list[Path]:
    return sorted(p for p in entry.rglob("*") if p.is_file())


def parse_sums(text: str) -> dict[str, str]:
    """``<sha256>  <path>`` lines -> {path: sha256}."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        if len(digest) != 64 or not path:
            raise ArchiveError(f"bad sums line {line[:80]!r}")
        out[path] = digest
    return out


def archive_entry(root: str | Path, key: str, out_tar: str | Path) -> dict[str, Any]:
    """Tar one verified entry without media; returns sums text, tar sha256 and the excluded media list."""
    root = Path(root)
    FeatureStore(root).verify(key, "before archive")  # incomplete / corrupt entries are never archived
    entry = root / key
    files = _files(entry)
    rels = [f"{key}/{p.relative_to(entry).as_posix()}" for p in files]
    digests = {r: sha256_file(p) for r, p in zip(rels, files, strict=True)}
    sums = "".join(f"{digests[r]}  {r}\n" for r in sorted(rels))
    out_tar = Path(out_tar)
    out_tar.parent.mkdir(parents=True, exist_ok=True)
    media = sorted(r for r in rels if r.endswith(MEDIA_SUFFIXES))
    with tarfile.open(out_tar, "w", format=tarfile.PAX_FORMAT) as tf:
        for r, p in sorted(zip(rels, files, strict=True)):
            if r in media:
                continue
            ti = tf.gettarinfo(str(p), arcname=r)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.mtime = 0
            with open(p, "rb") as f:
                tf.addfile(ti, f)
    return {"cache_key": key, "tar_sha256": sha256_file(out_tar), "tar_bytes": out_tar.stat().st_size,
            "files_sha256sums": sums, "n_files": len(rels),
            "media_excluded": [{"path": r, "sha256": digests[r]} for r in media],
            "media_files": {digests[r]: PurePosixPath(r).name for r in media}}


def save_media(root: str | Path, key: str, media_dir: str | Path) -> list[Path]:
    """Copy the entry's media files to media_dir, named <sha256><suffix> (pod-side store, not S3)."""
    media_dir = Path(media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for p in _files(Path(root) / key):
        if p.name.endswith(MEDIA_SUFFIXES):
            dst = media_dir / f"{sha256_file(p)}{p.suffix}"
            if not dst.exists():
                shutil.copy2(p, dst)
            out.append(dst)
    return out


def _safe_members(tf: tarfile.TarFile, key: str) -> list[tarfile.TarInfo]:
    members = tf.getmembers()
    for m in members:
        pp = PurePosixPath(m.name)
        if (pp.is_absolute() or ".." in pp.parts or not (m.isfile() or m.isdir())
                or not pp.parts or pp.parts[0] != key):
            raise ArchiveError(f"unsafe tar member {m.name!r}")
    return members


def restore_entry(tar: str | Path, sums_text: str, media: list[str | Path], root: str | Path) -> str:
    """Restore one archived entry under root; returns its cache key (see module docstring)."""
    sums = parse_sums(sums_text)
    keys = {PurePosixPath(p).parts[0] for p in sums}
    if len(keys) != 1:
        raise ArchiveError(f"sums must describe exactly one entry, got {len(keys)}")
    key = keys.pop()
    root = Path(root)
    store = FeatureStore(root)
    if (root / key).exists():
        store.verify(key, "before restore")  # corrupt entry -> FeatureCacheError; never overwritten
        have = {f"{key}/{p.relative_to(root / key).as_posix()}": sha256_file(p) for p in _files(root / key)}
        if have != sums:
            raise ArchiveError(f"entry {key} already exists with different files")
        return key
    root.mkdir(parents=True, exist_ok=True)
    by_sha = {sha256_file(m): Path(m) for m in media}
    with tempfile.TemporaryDirectory(prefix=".restore_", dir=root) as td:
        with tarfile.open(tar) as tf:
            members = _safe_members(tf, key)
            tf.extractall(td, members=members, filter="data")
        tmp_entry = Path(td) / key
        for rel, digest in sums.items():
            dst = Path(td) / rel
            if dst.exists():
                continue
            if not rel.endswith(MEDIA_SUFFIXES):
                raise ArchiveError(f"{rel} missing from the tar")
            src = by_sha.get(digest)
            if src is None:
                raise ArchiveError(f"media file {rel} (sha256 {digest[:12]}) not supplied")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        have = {f"{key}/{p.relative_to(tmp_entry).as_posix()}": sha256_file(p) for p in _files(tmp_entry)}
        bad = sorted(set(have) ^ set(sums)) + sorted(r for r in set(have) & set(sums) if have[r] != sums[r])
        if bad:
            raise ArchiveError(f"restored files differ from the sha256 sums: {bad[:5]}")
        tmp_entry.replace(root / key)
    try:
        store.verify(key, "after restore")
    except Exception:
        shutil.rmtree(root / key, ignore_errors=True)
        raise
    return key


def main(argv: list[str]) -> int:
    cmd, *rest = argv
    if cmd == "archive":
        root, key, out = rest
        info = archive_entry(root, key, out)
        Path(f"{out}.FILES_SHA256SUMS").write_text(info["files_sha256sums"])
        print(json.dumps({k: v for k, v in info.items() if k != "files_sha256sums"}))
    elif cmd == "save-media":
        root, key, media_dir = rest
        print(json.dumps([p.name for p in save_media(root, key, media_dir)]))
    elif cmd == "restore":
        tar, sums, root, *media = rest
        print(restore_entry(tar, Path(sums).read_text(), media, root))
    else:
        raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
