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
