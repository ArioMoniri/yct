"""BUG-050: two reference clips with byte-identical inputs (mp4 + tsv) share one content-addressed
feature-cache key. When the second clip runs on a NEW box (a later session), the driver's restore lookup is
keyed by job id only, so it re-extracts on the GPU (nondeterministic, BUG-006), gets a different entry tar for
the same key, and the immutable store refuses the upload (OverwriteRefusedError).

The frozen v1 manifest has three such groups: GREY_CTRL_00 == GREY_CTRL_01, FLASH_00 == FLASH_01 == FLASH_04,
FLASH_02 == FLASH_03. These tests reproduce the failure (red until the fix) and pin the intended behaviour
(feature_cache.py docstring: features are extracted EXACTLY ONCE per cache key): the second clip must restore
the existing entry by its content key and must not re-extract. Dry run only; no prediction content read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pre_d087 import pre_d087
from _pre_d091 import pre_d091
from test_gpu_p4b_ref import P4_SMALL, p4, ref

from yct.config import load_config, with_overrides

FAMS = {"LOC": 1, "LOC_SCR": 1, "MOT": 1, "MOT_STAT": 1, "SPK": 1, "BURST": 1, "FLASH": 1, "TALKFACE": 1,
        "GREY_CTRL": 2, "NAT": 1}


def _cfg(manifest_sha=None):
    over = {**P4_SMALL, "controls": {"refclips": {"families": FAMS},
                                     "refclips_artifacts": {"manifest_sha256": manifest_sha}}}
    return pre_d091(pre_d087(with_overrides(load_config(), over)))


@pytest.fixture
def env(tmp_path):
    cfg0 = _cfg()
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    p4_store = p4.DryRunBackend(tmp_path / "p4dry", cfg0, clock)
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="p4_seed")
    rc, res = p4.run_session(a, cfg0, lg, p4_store, clock, tmp_path / "runs" / "p4_seed")
    assert rc == 0, res
    backend = ref.RefDryRunBackend(tmp_path / "refdry", cfg0, clock)
    d = backend.pod / "refclips"
    d.mkdir(parents=True, exist_ok=True)
    # GREY_CTRL_01 is byte-identical to GREY_CTRL_00 (as in the frozen v1 manifest)
    body = b"synthetic ref GREY_CTRL shared " * 40
    tsv = "text\tstart\tduration\tsequence_id\tsentence\n"
    for cid in ("GREY_CTRL_00", "GREY_CTRL_01"):
        (d / f"{cid}.mp4").write_bytes(body)
        (d / f"{cid}.tsv").write_text(tsv)
    text = ref.write_synthetic_clips(backend.pod, cfg0)
    return {"cfg": _cfg(ref.sha256_text(text)), "clock": clock, "lg": lg, "p4": p4_store,
            "backend": backend, "text": text, "tmp": tmp_path}


def _run(env, run_id, **kw):
    a = {"max_hours": 3.5, "usd_limit": 25.0, "external_terminator_at": None, "run_id": run_id, "limit": None}
    a.update(kw)
    env["clock"].advance(60)
    return ref.run_ref_session(p4.SessionArgs(**a), env["cfg"], env["lg"], env["backend"], env["p4"],
                               env["clock"], env["tmp"] / "runs" / run_id, env["text"])


def _rows(env):
    return [json.loads(x) for x in (env["backend"].s3_get_text("manifest.jsonl") or "").splitlines()]


def test_fixture_has_two_identical_grey_clips(env):
    clips = {c["name"]: c["sha256"] for c in json.loads(env["text"])["clips"]}
    assert clips["grey_ctrl_00"] == clips["grey_ctrl_01"]


def test_identical_clip_on_a_new_box_restores_by_content_key_and_does_not_reextract(env):
    rc1, res1 = _run(env, "ref_s1", limit=3)                     # D-038 clips: GREY_CTRL_00, SPK_00, MOT_00
    assert rc1 == p4.EXIT_INCOMPLETE, res1
    assert "GREY_CTRL_00.ref" in res1["jobs_run"]
    rc2, res2 = _run(env, "ref_s2")                              # new instance, empty local cache
    assert not res2.get("errors"), res2.get("errors")           # BUG-050: OverwriteRefusedError today
    assert rc2 == 0, {k: res2.get(k) for k in ("error", "errors", "gate_failures")}
    rows = {r["job"]: r for r in _rows(env)}
    g0, g1 = rows["GREY_CTRL_00.ref"], rows["GREY_CTRL_01.ref"]
    assert g1["gate_pass"] is True
    assert g1["cache_key"] == g0["cache_key"] and g1["tar_sha256"] == g0["tar_sha256"]
    assert g1["cache_reused"] is True
    assert env["backend"].extractions_per_job().get("GREY_CTRL_01.ref", 0) == 0, \
        "features are extracted exactly once per cache key (feature_cache.py)"


def test_identical_clip_in_the_same_session_reuses_the_local_entry(env):
    """Control: on one box the local FeatureStore already dedups by content key (no error even today)."""
    rc, res = _run(env, "ref_one")
    assert rc == 0, {k: res.get(k) for k in ("error", "errors", "gate_failures")}
    rows = {r["job"]: r for r in _rows(env)}
    assert rows["GREY_CTRL_01.ref"]["cache_key"] == rows["GREY_CTRL_00.ref"]["cache_key"]
    assert rows["GREY_CTRL_01.ref"]["tar_sha256"] == rows["GREY_CTRL_00.ref"]["tar_sha256"]


def test_the_frozen_manifest_duplicate_groups_are_known():
    """Pins the scope of BUG-050 in the real frozen v1 manifest (shas only)."""
    m = json.loads((Path(__file__).resolve().parents[1] / "data/refstim/refclips_manifest.json").read_text())
    groups: dict[tuple, list[str]] = {}
    for c in m["clips"]:
        groups.setdefault((c["sha256"]["mp4"], c["sha256"].get("tsv")), []).append(c["name"])
    dups = sorted(sorted(v) for v in groups.values() if len(v) > 1)
    assert dups == [["flash_00", "flash_01", "flash_04"], ["flash_02", "flash_03"],
                    ["grey_ctrl_00", "grey_ctrl_01"]]


# ------------------------------------------------------------ BUG-050 fix (council APPROVE 5/5 conditions)
FAMS_FLASH = {**FAMS, "FLASH": 3, "GREY_CTRL": 1}


@pytest.fixture
def flash_env(tmp_path):
    """FLASH_00 == FLASH_01 == FLASH_02 (as the frozen FLASH_00/01/04 group), each on a NEW box."""
    def cfg_for(sha):
        over = {**P4_SMALL, "controls": {"refclips": {"families": FAMS_FLASH},
                                         "refclips_artifacts": {"manifest_sha256": sha}}}
        return pre_d091(pre_d087(with_overrides(load_config(), over)))

    cfg0 = cfg_for(None)
    clock = p4.FakeClock(1_800_000_000.0)
    lg = p4.FakeLG(clock, tmp_path / "ledger.jsonl")
    p4_store = p4.DryRunBackend(tmp_path / "p4dry", cfg0, clock)
    a = p4.SessionArgs(max_hours=3.5, usd_limit=25.0, external_terminator_at=None, run_id="p4_seed")
    assert p4.run_session(a, cfg0, lg, p4_store, clock, tmp_path / "runs" / "p4_seed")[0] == 0
    backend = ref.RefDryRunBackend(tmp_path / "refdry", cfg0, clock)
    d = backend.pod / "refclips"
    d.mkdir(parents=True, exist_ok=True)
    body = b"synthetic ref FLASH shared " * 40
    tsv = "text\tstart\tduration\tsequence_id\tsentence\n"
    for cid in ("FLASH_00", "FLASH_01", "FLASH_02"):
        (d / f"{cid}.mp4").write_bytes(body)
        (d / f"{cid}.tsv").write_text(tsv)
    text = ref.write_synthetic_clips(backend.pod, cfg0)
    return {"cfg": cfg_for(ref.sha256_text(text)), "clock": clock, "lg": lg, "p4": p4_store,
            "backend": backend, "text": text, "tmp": tmp_path}


def test_three_clip_flash_group_restores_by_content_key_each_on_a_new_box(flash_env):
    env = flash_env
    jobs = [j.id for j in ref.plan_ref_jobs(env["cfg"], ref.load_clip_manifest(env["text"], env["cfg"]))]
    i0 = jobs.index("FLASH_00.ref")
    _run(env, "s1", limit=3)
    _run(env, "s2", limit=i0 + 1 - 3)                                 # ... up to FLASH_00 inclusive
    _run(env, "s3", limit=1)                                          # FLASH_01 alone on a new box
    rc, res = _run(env, "s4")                                         # FLASH_02 and the rest on a new box
    assert rc == 0, {k: res.get(k) for k in ("error", "errors", "gate_failures")}
    rows = {r["job"]: r for r in _rows(env) if r.get("gate_pass")}
    f0 = rows["FLASH_00.ref"]
    ex = env["backend"].extractions_per_job()
    for j in ("FLASH_01.ref", "FLASH_02.ref"):
        assert rows[j]["cache_key"] == f0["cache_key"] and rows[j]["tar_sha256"] == f0["tar_sha256"]
        assert rows[j]["cache_reused"] is True and rows[j]["restored_from_job"] == "FLASH_00.ref"
        assert ex.get(j, 0) == 0
        ent = json.loads(env["backend"].s3_get_text(f"entries_ref/{j}.json"))
        assert ent["restored_from_job"] == "FLASH_00.ref" and ent["cache_reused"] is True
        assert ent["tar_sha256"] == f0["tar_sha256"]


def _add_row(env, row):
    old = env["backend"].s3_get_text("manifest.jsonl") or ""
    env["backend"].s3_put_text("manifest.jsonl", old + json.dumps(row, sort_keys=True) + "\n")


def test_conflicting_tar_sha_for_one_content_key_is_a_stop(env):
    _run(env, "s1", limit=3)
    g0 = {r["job"]: r for r in _rows(env)}["GREY_CTRL_00.ref"]
    _add_row(env, {**g0, "job": "GHOST.ref", "video_id": "GHOST", "tar_sha256": "e" * 64, "run_id": "ghost"})
    rc, res = _run(env, "s2")
    assert rc == p4.EXIT_FAIL
    assert "CacheKeyConflictError" in str(res.get("error")) and "GREY_CTRL_01.ref" in str(res.get("error"))
    assert env["backend"].extractions_per_job().get("GREY_CTRL_01.ref", 0) == 0
    assert not any(r["job"] == "GREY_CTRL_01.ref" and r.get("gate_pass") for r in _rows(env))


def test_content_key_with_only_non_passing_rows_is_a_stop(env):
    from yct.tribe_run.feature_cache import content_key
    _run(env, "s1", limit=3)
    clips = {c["clip_id"]: c for c in ref.load_clip_manifest(env["text"], env["cfg"])["clips"]}
    rev = {r["job"]: r for r in _rows(env)}["GREY_CTRL_00.ref"]["revisions_sha256"]
    other = clips["LOC_00"]                 # a not-yet-run clip: give its key a failing row only
    key = content_key(other["mp4_sha256"], other["tsv_sha256"], rev)
    _add_row(env, {"job": "GHOST.ref", "video_id": "GHOST", "cache_key": key, "gate_pass": False,
                   "run_id": "ghost", "track": "t1"})
    rc, res = _run(env, "s2")
    assert rc == p4.EXIT_FAIL
    assert "no passing row" in str(res.get("error")) and "LOC_00.ref" in str(res.get("error"))


def test_p4_campaign_is_unaffected(env):
    """The P4 analysis-set store is only read; its manifest is byte-identical across ref sessions, and the P4
    campaign keeps job-id restore (no content-key lookup: D-063 job selection unchanged)."""
    assert p4.P4_CAMPAIGN.restore_by_content_key is False
    before = env["p4"].s3_get_text("manifest.jsonl")
    _run(env, "s1", limit=3)
    rc, res = _run(env, "s2")
    assert rc == 0, res.get("errors")
    assert env["p4"].s3_get_text("manifest.jsonl") == before
    assert res["p4_manifest_sha256"]["before"] == res["p4_manifest_sha256"]["after"]
    st = p4.load_state(env["p4"])
    job = p4.plan_jobs(env["cfg"])[0]
    assert p4.restorable(job, st, {"sha256": "x", "tsv_sha256": "y"}, p4.P4_CAMPAIGN) is None
