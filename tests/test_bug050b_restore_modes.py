"""BUG-050b: restoring an archived feature-cache entry and archiving it again changes the tar bytes when the
original files had group/other write bits (the GPU box wrote 0o777 / 0o664), because restore_entry extracts
with tarfile filter="data", which clears those bits (0o777 -> 0o755, 0o664 -> 0o644) and archive_entry
records the file mode in the tar header. File contents, and therefore the FILES_SHA256SUMS text, are
unchanged. Seen on the pod (session 3, p4bref_20261124T090803Z): 14/14 members identical by sha256, only
modes differ; stored tar 858643…, re-archived 8705275e…, sums byte-identical (fa0e6ebb…).

This module pins the cause (characterisation; passes today). The driver-level reproduction lives in
tests/test_bug050_cache_collision.py once the fix lands (see reviews/phase_p4b/bug050b_diagnosis.md).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from yct.tribe_run import cache_archive as ca
from yct.tribe_run.feature_cache import SIDECAR, FeatureStore, sha256_file


def _entry(root: Path, key: str, mode_feat: int, mode_meta: int) -> None:
    e = root / key
    (e / "feat").mkdir(parents=True)
    (e / "input").mkdir()
    (e / "input" / "clip.mp4").write_bytes(b"synthetic clip bytes")
    (e / "input" / "clip.tsv").write_text("text\tstart\tduration\tsequence_id\tsentence\n")
    f = e / "feat" / "a.npy"
    f.write_bytes(b"\x93NUMPY synthetic, not parsed")
    meta = {"input_sha256": sha256_file(e / "input" / "clip.mp4"), "input_name": "clip.mp4",
            "transcript_sha256": None, "cache_key": key, "revisions": {}, "revisions_sha256": "0" * 64,
            "tensors": {"a.npy": {"sha256": sha256_file(f), "bytes": f.stat().st_size}},
            "input_files": {p.name: sha256_file(p) for p in sorted((e / "input").iterdir())}}
    (e / SIDECAR).write_text(json.dumps(meta))
    os.chmod(f, mode_feat)
    os.chmod(e / SIDECAR, mode_meta)


def _roundtrip(tmp: Path, mode_feat: int, mode_meta: int):
    key = "k" * 64
    a, b = tmp / "a", tmp / "b"
    _entry(a, key, mode_feat, mode_meta)
    FeatureStore(a).verify(key)
    first = ca.archive_entry(a, key, tmp / "first.tar")
    media = [a / key / "input" / "clip.mp4"]
    ca.restore_entry(tmp / "first.tar", first["files_sha256sums"], media, b)
    second = ca.archive_entry(b, key, tmp / "second.tar")
    return first, second


def test_restore_then_rearchive_changes_tar_bytes_for_group_writable_files(tmp_path):
    first, second = _roundtrip(tmp_path, 0o777, 0o664)
    assert first["tar_sha256"] != second["tar_sha256"]                 # the BUG-050b symptom
    assert first["files_sha256sums"] == second["files_sha256sums"]     # contents unchanged


def test_restore_then_rearchive_is_byte_identical_for_0644_files(tmp_path):
    """Control: why the dry-run tests never saw it (files written under umask 022 are 0o644)."""
    first, second = _roundtrip(tmp_path, 0o644, 0o644)
    assert first["tar_sha256"] == second["tar_sha256"]
