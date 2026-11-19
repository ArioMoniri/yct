"""D-067 c / QA #2: the single P4 prediction loader."""
import json

import pytest

from yct.predict.p4_index import p4_index


class FakeStore:
    def __init__(self, rows, keys):
        self.text = "\n".join(json.dumps(r) for r in rows)
        self.keys = {k: 1 for k in keys}

    def s3_get_text(self, key):
        return self.text if key == "manifest.jsonl" else None

    def s3_list(self, prefix):
        return {k: v for k, v in self.keys.items() if k.startswith(prefix)}


CFG = {"superseded_run_ids": ["old_run"], "run_set_t3": ["v1", "v2"], "run_set_t1": ["v1"]}


def row(vid, track, run="new_run", rev="r" * 64, key=None, ok=True, d038=None):
    return {"job": f"{vid}.{track}", "video_id": vid, "track": track, "run_id": run, "gate_pass": ok,
            "pred_key": key or f"pred_clampv1/{track}/{vid}.npy", "pred_sha256": "a" * 64,
            "revisions_sha256": rev, "d038": d038}


def store(rows):
    return FakeStore(rows, [r["pred_key"] for r in rows])


def good_rows():
    return [row("v1", "t3", d038={"pass": True}), row("v2", "t3"), row("v1", "t1")]


def test_returns_one_ref_per_run_set_job():
    idx = p4_index(store(good_rows()), CFG)
    assert set(idx) == {("t3", "v1"), ("t3", "v2"), ("t1", "v1")}
    assert all(p.pred_key.startswith("pred_clampv1/") for p in idx.values())
    assert len({p.revisions_sha256 for p in idx.values()}) == 1


def test_superseded_rows_are_ignored():
    rows = good_rows() + [row("v2", "t3", run="old_run", rev="o" * 64, key="pred/t3/v2.npy")]
    idx = p4_index(store(rows), CFG)
    assert idx[("t3", "v2")].run_id == "new_run"


def test_failed_rows_are_ignored_and_missing_job_raises():
    rows = [r for r in good_rows() if r["video_id"] != "v2"] + [row("v2", "t3", ok=False)]
    with pytest.raises(RuntimeError, match="without a passing row"):
        p4_index(store(rows), CFG)


def test_mixed_revisions_raise():
    rows = good_rows()
    rows[1]["revisions_sha256"] = "x" * 64
    with pytest.raises(RuntimeError, match="revisions"):
        p4_index(store(rows), CFG)


def test_key_outside_clampv1_raises():
    rows = good_rows()
    rows[2]["pred_key"] = "pred/t1/v1.npy"
    with pytest.raises(RuntimeError, match="outside"):
        p4_index(store(rows), CFG)


def test_duplicate_passing_rows_raise():
    with pytest.raises(RuntimeError, match="two passing"):
        p4_index(store(good_rows() + [row("v2", "t3")]), CFG)


def test_key_absent_from_store_raises():
    rows = good_rows()
    s = store(rows)
    del s.keys[rows[1]["pred_key"]]
    with pytest.raises(RuntimeError, match="not in store"):
        p4_index(s, CFG)
