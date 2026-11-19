"""D-074 (T-LIC images): Commons category snapshots, complete enumeration, file names, record kept."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
import yaml

from yct.config import load_config
from yct.curate import refstim as rs

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "refstim" / "snapshots"
CFG = load_config()


def ent(i, mediatype="BITMAP", title=None):
    return {"title": title or f"File:c{i}.jpg", "pageid": i, "revid": 9000 + i, "mime": "image/jpeg",
            "mediatype": mediatype, "sha1": f"{i:040x}", "width": 800, "height": 600}


def fake(members):
    def f(category, namespace, limit):
        assert namespace == 6
        return members[category]
    return f


def full_members(n=30):
    return {
        "Portrait photographs": {"complete": True, "entries": [ent(i) for i in range(n)]},
        "Rear views of people": {"complete": True, "entries": [ent(100 + i) for i in range(n)]},
        "Empty rooms": {"complete": True, "entries": [ent(200 + i) for i in range(n)]},
        "Empty streets": {"complete": True, "entries": [ent(300 + i) for i in range(n)] + [ent(200)]},
    }


def test_header_and_entries_carry_title_pageid_revid():
    s = rs.build_category_snapshot(rs.header_for_d074(CFG, "face", "2026-11-19"), fake(full_members()))
    rs.check_header_d074(s, CFG)
    assert s["header"]["sources"] == [{"category": "Portrait photographs", "depth": 0}]
    assert s["header"]["complete"] is True and s["header"]["n_members"] == 30
    for e in s["entries"]:
        assert {"title", "pageid", "revid", "mediatype", "sha1", "width", "height", "mime"} <= set(e)
    s["header"]["limit"] = 10
    with pytest.raises(rs.CurationError):
        rs.check_header_d074(s, CFG)


def test_place_union_dedup_and_sha_title_order():
    s = rs.build_category_snapshot(rs.header_for_d074(CFG, "place", "2026-11-19"), fake(full_members()))
    titles = [e["title"] for e in s["entries"]]
    assert len(titles) == len(set(titles)) == 60                 # File:c200.jpg in both: once
    o = rs.ordered(s)
    assert [rs.title_key(e["title"]) for e in o] == sorted(rs.title_key(t) for t in titles)


@pytest.mark.parametrize("bad", ["incomplete", "over_limit", "missing_field"])
def test_snapshot_refused(bad):
    m = full_members()
    if bad == "incomplete":
        m["Portrait photographs"]["complete"] = False
    elif bad == "over_limit":
        m["Portrait photographs"]["entries"] = [ent(i) for i in range(6001)]
    else:
        del m["Portrait photographs"]["entries"][3]["revid"]
    with pytest.raises(rs.CurationError):
        rs.build_category_snapshot(rs.header_for_d074(CFG, "face", "2026-11-19"), fake(m))


def test_non_bitmap_stays_in_snapshot_and_is_not_photo():
    m = full_members()
    m["Portrait photographs"]["entries"][5] = ent(5, mediatype="DRAWING")
    s = rs.build_category_snapshot(rs.header_for_d074(CFG, "face", "2026-11-19"), fake(m))
    e = next(x for x in s["entries"] if x["pageid"] == 5)
    assert rs.pre_reason_d074(e, CFG) == "not_photo"
    assert rs.pre_reason_d074(ent(1), CFG) is None
    log = [{"title": x["title"], "sha256_title": rs.title_key(x["title"]),
            "decision": "reject" if rs.pre_reason_d074(x, CFG) else "pass",
            "reason": rs.pre_reason_d074(x, CFG) or ""} for x in rs.ordered(s)][:21]
    passes = [r for r in log if r["decision"] == "pass"][:20]
    log = log[: log.index(passes[-1]) + 1]
    assert len(rs.check_log(log, s, CFG, 20)) == 20


def test_fewer_than_20_passes_after_exhaustion_refuses():
    m = full_members(n=19)
    s = rs.build_category_snapshot(rs.header_for_d074(CFG, "face", "2026-11-19"), fake(m))
    log = [{"title": x["title"], "sha256_title": rs.title_key(x["title"]), "decision": "pass", "reason": ""}
           for x in rs.ordered(s)]
    with pytest.raises(rs.CurationError, match="build does not start"):
        rs.check_log(log, s, CFG, 20)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _api(monkeypatch, bodies):
    calls = []

    def urlopen(req, timeout=60):
        calls.append(req.full_url)
        return _Resp(json.dumps(bodies[len(calls) - 1]).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return calls


def _page(i, ii=True):
    p = {"pageid": i, "title": f"File:p{i}.jpg", "lastrevid": 500 + i}
    if ii:
        p["imageinfo"] = [{"mime": "image/jpeg", "mediatype": "BITMAP", "sha1": "a" * 40,
                           "width": 9, "height": 9}]
    return p


def test_fetch_follows_gcmcontinue_and_iicontinue_to_batchcomplete(monkeypatch):
    bodies = [
        {"continue": {"gcmcontinue": "g1", "continue": "gcmcontinue||"}, "query": {"pages": [_page(1)]}},
        {"continue": {"iicontinue": "i1", "continue": "||"}, "query": {"pages": [_page(2, ii=False)]}},
        {"batchcomplete": True, "query": {"pages": [_page(2)]}},
    ]
    calls = _api(monkeypatch, bodies)
    r = rs.fetch_category("Portrait photographs", 6, 6000)
    assert r["complete"] is True and [e["pageid"] for e in r["entries"]] == [1, 2]
    assert all(e["mediatype"] == "BITMAP" and e["revid"] for e in r["entries"])
    assert "gcmcontinue=g1" in calls[1] and "iicontinue=i1" in calls[2]


def test_fetch_iicontinue_not_followed_leaves_entry_incomplete_and_refused(monkeypatch):
    bodies = [{"batchcomplete": True, "query": {"pages": [_page(1), _page(2, ii=False)]}}]
    _api(monkeypatch, bodies)
    r = rs.fetch_category("Portrait photographs", 6, 6000)
    with pytest.raises(rs.CurationError, match="lacks"):
        rs.build_category_snapshot(rs.header_for_d074(CFG, "face", "2026-11-19"),
                                   lambda c, n, lim: r)


def test_fetch_over_limit_and_api_error_refused(monkeypatch):
    _api(monkeypatch, [{"batchcomplete": True, "query": {"pages": [_page(i) for i in range(5)]}}])
    with pytest.raises(rs.CurationError):
        rs.fetch_category("Empty rooms", 6, 4)
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=60: _Resp(json.dumps({"error": {"code": "x"}}).encode()))
    with pytest.raises(rs.CurationError):
        rs.fetch_category("Empty rooms", 6, 6000)


def _load_script():
    spec = importlib.util.spec_from_file_location("snap_d074", ROOT / "scripts" / "refstim_snapshot_d074.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_writes_new_names_only_and_concat_sha(tmp_path):
    old = {}
    for name in ["image_face_snapshot.json", "image_body_snapshot.json", "image_place_snapshot.json",
                 "nat_nat_snapshot.json"]:
        (tmp_path / name).write_bytes((SNAP / name).read_bytes())
        old[name] = (SNAP / name).read_bytes()
    sha = _load_script().run(tmp_path, CFG, fake(full_members()), "2026-11-19")
    for name, b in old.items():
        assert (tmp_path / name).read_bytes() == b                # D-071 record + NAT byte-identical
    names = [rs.snapshot_name_d074(c, CFG) for c in ("face", "body", "place")]
    assert names == ["image_face_d074_snapshot.json", "image_body_d074_snapshot.json",
                     "image_place_d074_snapshot.json"]
    assert sha == hashlib.sha256(b"".join((tmp_path / n).read_bytes() for n in names)).hexdigest()


def test_committed_d071_image_snapshots_still_match_d071_header():
    for cat in ("face", "body", "place"):
        s = json.loads((SNAP / f"image_{cat}_snapshot.json").read_text())
        rs.check_header(s, CFG)
        assert s["entries"] == []


def test_repo_d074_snapshots_once_present():
    """Q7 (iii): once the D-074 snapshots exist, the artifact sha equals their concatenated sha, each header
    matches config, and its frozen row (when present) predates any reject log."""
    names = [rs.snapshot_name_d074(c, CFG) for c in CFG["controls"]["refclips"]["loc_categories"]]
    if not all((SNAP / n).exists() for n in names):
        assert CFG["controls"]["refclips_artifacts"]["image_snapshot_sha256"] is None
        return
    for n in names:
        rs.check_header_d074(json.loads((SNAP / n).read_text()), CFG)
    want = rs.image_snapshot_sha_d074(SNAP, CFG)
    assert CFG["controls"]["refclips_artifacts"]["image_snapshot_sha256"] == want
    rows = {r["key"] for r in yaml.safe_load((ROOT / "config.yaml").read_text())["frozen"]}
    logs = sorted((ROOT / "data" / "refstim").glob("*_reject_log*.json"))
    if logs:
        assert "controls.refclips_artifacts.image_snapshot_sha256" in rows
        for n in names:
            for lg in logs:
                assert rs.snapshot_precedes(ROOT, f"data/refstim/snapshots/{n}", str(lg.relative_to(ROOT)))
