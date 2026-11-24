"""BUG-050b fix (council wf_f85f8bc4-847: watchdog + QA APPROVE, referee/biostat/neuro REVISE, converged
conditions). A restored cache entry (by content key or by job id, incl. a non-full condition restoring its
base entry) is judged by its FILES_SHA256SUMS, anchored to the recorded entry sums_sha256:
(a) staging fails closed when the downloaded sums object's sha256 != the recorded sums_sha256;
(b) after the run the re-archived sums sha256 must equal the recorded sums_sha256, else STOP, nothing uploaded;
(c) both restore kinds; (d) restored jobs never re-upload the tar/sums, and their row carries the stored shas
(rearchive_tar_sha256 descriptive only); (f) no umask change / mode normalisation. Dry run only."""
from __future__ import annotations

import json
import os

from test_bug050_cache_collision import _rows, _run, env, p4  # noqa: F401  (env is a fixture)


def _umask0_run(env, run_id, **kw):
    old = os.umask(0)                                    # box writes cache files 0o666/0o777 (BUG-050b)
    try:
        return _run(env, run_id, **kw)
    finally:
        os.umask(old)


def _err(res):
    return str(res.get("error")) + str(res.get("errors"))


def _cache_sha_objects(env):
    b = env["backend"]
    return {k: b.s3_get_text(k) for k in b.s3_list("feature_cache/") if k.endswith(".sha256")}


def test_sums_mismatch_at_staging_is_a_stop(env):
    _run(env, "s1", limit=3)
    g0 = {r["job"]: r for r in _rows(env)}["GREY_CTRL_00.ref"]
    sums_key = f"feature_cache/{g0['cache_key']}.FILES_SHA256SUMS"
    b = env["backend"]
    b.s3_put_text(sums_key, b.s3_get_text(sums_key) + "0" * 64 + "  extra\n")   # tampered anchor object
    rc, res = _run(env, "s2")
    assert rc == p4.EXIT_FAIL
    assert "RestoreIntegrityError" in _err(res) and "GREY_CTRL_01.ref" in _err(res)
    assert b.extractions_per_job().get("GREY_CTRL_01.ref", 0) == 0
    assert not any(r["job"] == "GREY_CTRL_01.ref" for r in _rows(env))


def test_post_run_sums_mismatch_is_a_stop_and_uploads_nothing(env):
    _run(env, "s1", limit=3)
    before = _cache_sha_objects(env)
    b = env["backend"]
    b.faults["GREY_CTRL_01.ref"] = "sums_differ"
    rc, res = _run(env, "s2")
    assert rc == p4.EXIT_FAIL
    assert "RestoreIntegrityError" in _err(res) and "GREY_CTRL_01.ref" in _err(res)
    assert _cache_sha_objects(env) == before                                     # no tar/sums upload
    assert not any(r["job"] == "GREY_CTRL_01.ref" for r in _rows(env))
    assert "entries_ref/GREY_CTRL_01.ref.json" not in b.s3_list("entries_ref/")


def test_crash_recovery_restore_of_a_group_writable_entry_neither_reuploads_nor_refuses(env):
    b = env["backend"]
    _run(env, "s1", limit=3)
    b.faults["LOC_00.ref"] = "crash_after_entry"
    rc1, res1 = _umask0_run(env, "s2", limit=1)            # LOC_00: entry synced 0o666/0o777, then crash
    assert rc1 == p4.EXIT_FAIL and "LOC_00.ref" in str(res1.get("error"))
    b.faults.clear()
    before = _cache_sha_objects(env)
    stored = json.loads(b.s3_get_text("entries_ref/LOC_00.ref.json"))
    rc2, res2 = _run(env, "s3", limit=1)
    assert rc2 in (0, p4.EXIT_INCOMPLETE), {k: res2.get(k) for k in ("error", "errors", "gate_failures")}
    assert "LOC_00.ref" in res2["restored"]
    assert _cache_sha_objects(env) == before                                     # no re-upload
    row = {r["job"]: r for r in _rows(env) if r.get("gate_pass")}["LOC_00.ref"]
    assert row["tar_sha256"] == stored["tar_sha256"] and row["sums_sha256"] == stored["sums_sha256"]
    assert row["rearchive_tar_sha256"] != stored["tar_sha256"]                   # descriptive only
    assert b.extractions_per_job().get("LOC_00.ref", 0) == 1


def test_non_full_condition_restoring_a_group_writable_base_entry(env):
    rc1, res1 = _umask0_run(env, "s1", limit=3)            # SPK_00 full entry written group-writable
    assert rc1 == p4.EXIT_INCOMPLETE, res1
    rc2, res2 = _run(env, "s2")                              # SPK_00.audioonly / .textonly on a new box
    assert rc2 == 0, {k: res2.get(k) for k in ("error", "errors", "gate_failures")}
    rows = {r["job"]: r for r in _rows(env) if r.get("gate_pass")}
    base = rows["SPK_00.ref"]
    for cond in ("audioonly", "textonly"):
        r = rows[f"SPK_00.ref.{cond}"]
        assert r["restored_from_s3"] is True and r["cache_key"] == base["cache_key"]
        assert r["tar_sha256"] == base["tar_sha256"] and r["sums_sha256"] == base["sums_sha256"]
