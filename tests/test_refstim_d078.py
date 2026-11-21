"""D-078: second Commons category for body; union over the frozen D-074 body snapshot; fail-closed audit."""

import json
from pathlib import Path

import pytest

from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "refstim" / "snapshots"
CFG = load_config()
D = CFG["controls"]["refclips_d078"]


def ent(i, title=None):
    return {"title": title or f"File:m{i}.jpg", "pageid": i, "revid": 9000 + i, "mime": "image/jpeg",
            "mediatype": "BITMAP", "sha1": f"{i:040x}", "width": 800, "height": 600}


def base_snapshot(n=5):
    h = rs.header_for_d074(CFG, "body", "2026-11-19")
    return {"header": {**h, "complete": True, "n_members": n},
            "entries": [{**ent(i, f"File:b{i}.jpg"), "source": "Rear views of people"} for i in range(n)]}


def fake(entries, complete=True):
    def f(category, namespace, limit):
        assert category == "Rear views of men" and namespace == 6
        return {"complete": complete, "entries": entries}
    return f


def test_config_key():
    assert D["decision"] == "D-078" and D["amends"] == "D-074" and D["categories"] == ["body"]
    src = D["image_sources"]["body"]
    assert src[0] == CFG["controls"]["refclips_d074"]["image_sources"]["body"][0]
    assert src[1] == {"category": "Rear views of men", "depth": 0}


def test_union_base_verbatim_first_and_dedup(tmp_path):
    base = base_snapshot()
    (tmp_path / "base.json").write_text(json.dumps(base))
    hdr = rs.header_for_d078(CFG, "body", "2026-11-21", "a" * 64)
    added = [ent(100), ent(101), ent(0, "File:b0.jpg")]                # b0 also in base: kept once (base)
    s = rs.build_d078_snapshot(hdr, base, fake(added))
    assert s["entries"][:5] == base["entries"]
    assert [e["title"] for e in s["entries"][5:]] == ["File:m100.jpg", "File:m101.jpg"]
    assert all(e["source"] == "Rear views of men" for e in s["entries"][5:])
    assert s["header"]["n_members"] == 7 and s["header"]["complete"] is True
    assert s["header"]["base_snapshot_sha256"] == "a" * 64
    assert s["header"]["base_snapshot"] == rs.snapshot_name_d074("body", CFG)


def test_incomplete_or_over_limit_added_source_refused():
    hdr = rs.header_for_d078(CFG, "body", "2026-11-21", "a" * 64)
    with pytest.raises(rs.CurationError):
        rs.build_d078_snapshot(hdr, base_snapshot(), fake([ent(1)], complete=False))
    hdr2 = {**hdr, "limit": 1}
    with pytest.raises(rs.CurationError):
        rs.build_d078_snapshot(hdr2, base_snapshot(), fake([ent(1), ent(2)]))


def test_base_sources_must_match_header():
    hdr = rs.header_for_d078(CFG, "body", "2026-11-21", "a" * 64)
    b = base_snapshot()
    b["header"]["sources"] = [{"category": "Other", "depth": 0}]
    with pytest.raises(rs.CurationError):
        rs.build_d078_snapshot(hdr, b, fake([]))


def test_routing_body_only():
    assert rs.snapshot_name_eff("body", CFG) == "image_body_d078_snapshot.json"
    assert rs.snapshot_name_eff("face", CFG) == rs.snapshot_name_d074("face", CFG)
    assert rs.snapshot_name_eff("place", CFG) == rs.snapshot_name_d074("place", CFG)
    assert rs.image_log_rel("body", CFG) == "data/refstim/image_body_d078_auto_log.jsonl"
    assert rs.image_log_rel("face", CFG) == "data/refstim/image_face_auto_log.jsonl"
    assert rs.image_log_rel("place", CFG) == "data/refstim/image_place_auto_log.jsonl"


def test_committed_d078_snapshot_matches_config_and_header():
    p = SNAP / "image_body_d078_snapshot.json"
    want = CFG["controls"]["refclips_d078_artifacts"]["body_snapshot_sha256"]
    if not p.exists():
        assert want is None
        return
    assert rs.file_sha(p) == want
    s = json.loads(p.read_text())
    rs.check_header_d078(s, CFG, SNAP)
    base = json.loads((SNAP / rs.snapshot_name_d074("body", CFG)).read_text())
    assert s["entries"][:len(base["entries"])] == base["entries"]


def test_run_refuses_unless_d078_frozen():
    cfg = json.loads(json.dumps(CFG))
    cfg["frozen"] = [r for r in cfg.get("frozen") or [] if r["key"] != "controls.refclips_d078"]
    with pytest.raises(ra.StopError, match="refclips_d078"):
        ra.check_frozen_d078(cfg)
    cfg = json.loads(json.dumps(CFG))
    cfg["controls"]["refclips_d078_artifacts"]["body_snapshot_sha256"] = None
    cfg["frozen"] = (cfg.get("frozen") or []) + [
        {"key": "controls.refclips_d078", "frozen_at": "x"},
        {"key": "controls.refclips_d078_artifacts.body_snapshot_sha256", "frozen_at": "x"}]
    with pytest.raises(ra.StopError):
        ra.check_frozen_d078(cfg)


@pytest.mark.parametrize("new,old,ok", [
    (("pass", None), ("pass", None), True),
    (("reject", "licence"), ("reject", "licence"), True),
    (("reject", "duplicate"), ("pass", None), True),
    (("pass", None), ("reject", "duplicate"), True),
    (("pass", None), ("reject", "too_small"), False),
    (("reject", "licence"), ("reject", "too_small"), False),
])
def test_determinism_audit(new, old, ok):
    prior = {"File:x.jpg": {"title": "File:x.jpg", "decision": old[0], "reason": old[1]}}
    row = {"title": "File:x.jpg", "decision": new[0], "reason": new[1]}
    if ok:
        ra.audit_prior(row, prior)
    else:
        with pytest.raises(ra.StopError, match="determinism"):
            ra.audit_prior(row, prior)
    ra.audit_prior({"title": "File:new.jpg", "decision": "pass", "reason": None}, prior)   # not in prior


def test_d074_body_files_byte_identical_to_committed():
    want = {"data/refstim/snapshots/image_body_d074_snapshot.json":
            "7a88c1a20f69d4061edf527779f4e8d0ac70e5d3079844aff21bd619afbc7bbc",
            "data/refstim/image_body_auto_log.jsonl":
            "b87d8a19ee271585106a02bf2ae6001e11ab6e9c38fd12b82233ca5a57049954"}   # 9f38eb1
    for rel, sha in want.items():
        assert rs.file_sha(ROOT / rel) == sha, rel


def _load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_snapshot_script_writes_only_d078_and_returns_file_sha(tmp_path):
    import shutil
    for c in CFG["controls"]["refclips"]["loc_categories"]:
        shutil.copy(SNAP / rs.snapshot_name_d074(c, CFG), tmp_path)
    before = {p.name: rs.file_sha(p) for p in tmp_path.iterdir()}
    out = _load("refstim_snapshot_d078").run(tmp_path, CFG, fake([ent(1), ent(2)]), "2026-11-21")
    p = tmp_path / "image_body_d078_snapshot.json"
    assert out == {"body": rs.file_sha(p)}
    assert {q.name: rs.file_sha(q) for q in tmp_path.iterdir() if q.name in before} == before
    assert {q.name for q in tmp_path.iterdir()} - set(before) == {p.name}


def test_runner_routes_through_d078_helpers():
    src = (ROOT / "scripts" / "refstim_auto_run.py").read_text()
    for s in ("rs.image_log_rel(cat, cfg)", "rs.snapshot_name_eff(cat, cfg)", "ra.check_frozen_d078(cfg)",
              "ra.audit_prior(row, prior, exempt)", "rs.check_header_d078(snap, cfg, snapdir)"):
        assert s in src, s
    assert src.index("ra.audit_prior(row, prior, exempt)") < src.index("ra.append_jsonl(log_path, row)")
