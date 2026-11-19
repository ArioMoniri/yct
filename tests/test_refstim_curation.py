"""T-LIC / T-NAT (D-071 b/c, T4 a-g): label-free reference-stimulus curation rules."""

import io
import json
import subprocess

import pytest

from yct.config import load_config
from yct.curate import refstim as rs

CFG = load_config()


def snap(n=30, kind="image", cat="face"):
    h = rs.header_for(kind, CFG, cat, "2026-11-19")
    entries = [
        {"title": f"File:x{i}.jpg", "pageid": i, "revid": 1000 + i, "query": h["queries"][0]}
        for i in range(n)
    ]
    return {"header": h, "entries": entries}


def log_for(s, n_pass, reject_every=3, reason="multi_subject"):
    rows, p = [], 0
    for i, e in enumerate(rs.ordered(s)):
        dec = "reject" if i % reject_every == 1 else "pass"
        rows.append(
            {
                "title": e["title"],
                "sha256_title": rs.title_key(e["title"]),
                "decision": dec,
                "reason": reason if dec == "reject" else "",
            }
        )
        p += dec == "pass"
        if p == n_pass:
            break
    return rows


def mrow(i, lic="CC-BY-4.0", tpl="Template:Cc-by-4.0"):
    return {
        "file": f"face_{i:02d}.jpg",
        "url": f"https://commons.wikimedia.org/wiki/File:x{i}.jpg",
        "pageid": i,
        "revid": 1000 + i,
        "licence": lic,
        "licence_template": tpl,
        "attribution": f"Author {i}",
        "sha256": f"{i:064x}",
    }


# (b) header equals config
def test_header_matches_config_and_tamper_fails():
    s = snap()
    rs.check_header(s, CFG)
    assert s["header"]["queries"] == CFG["controls"]["refclips"]["image_queries"]["face"]
    assert s["header"]["limit"] == 2000 and s["header"]["srnamespace"] == 6
    s["header"]["limit"] = 500
    with pytest.raises(rs.CurationError):
        rs.check_header(s, CFG)


def test_nat_header_and_place_union():
    n = rs.header_for("nat", CFG, None, "2026-11-19")
    assert (
        n["queries"] == ["lecture OR interview OR talk"] and n["filetype"] == "video" and n["limit"] == 1000
    )
    h = rs.header_for("image", CFG, "place", "2026-11-19")
    calls = []

    def fetch(q, lim):
        calls.append((q, lim))
        return [
            {"title": "File:a.jpg", "pageid": 1, "revid": 2},
            {"title": f"File:{len(calls)}.jpg", "pageid": 9, "revid": 9},
        ]

    s = rs.build_snapshot(h, fetch)
    assert [c[0] for c in calls] == [f"{q} filetype:bitmap" for q in h["queries"]] and len(calls) == 2
    assert [e["title"] for e in s["entries"]] == ["File:a.jpg", "File:1.jpg", "File:2.jpg"]


# (c) ordered, contiguous, stops at the n-th pass
def test_log_order_contiguity_and_stop():
    s = snap()
    log = log_for(s, 20)
    assert len(rs.check_log(log, s, CFG, 20)) == 20
    swapped = log[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(rs.CurationError, match="order"):
        rs.check_log(swapped, s, CFG, 20)
    with pytest.raises(rs.CurationError, match="order"):
        rs.check_log(log[:3] + log[4:], s, CFG, 20)  # gap
    extra = log + [{"title": "x", "sha256_title": "x", "decision": "reject", "reason": "licence"}]
    with pytest.raises(rs.CurationError):
        rs.check_log(extra, s, CFG, 20)


# (d) reason codes from the fixed list
def test_reason_codes_fixed():
    s = snap()
    with pytest.raises(rs.CurationError, match="reject_reasons"):
        rs.check_log(log_for(s, 20, reason="ugly"), s, CFG, 20)
    for r in CFG["controls"]["refclips"]["reject_reasons"]:
        rs.check_log(log_for(s, 20, reason=r), s, CFG, 20)


# (e) licences + personality rights
def test_licence_mapping():
    assert rs.licence_of(["Template:Cc-zero"], None) == ("CC0", "Template:Cc-zero")
    assert rs.licence_of(["Template:PD-self"], None)[0] == "PD-*"
    assert rs.licence_of(["Template:Cc-by-4.0"], None)[0] == "CC-BY-4.0"
    for bad in (
        ["Template:Cc-by-sa-4.0"],
        ["Template:GFDL"],
        ["Template:Cc-by-nc-2.0"],
        ["Template:Cc-by-nd-3.0"],
    ):
        assert rs.licence_of(bad, None) == (None, None)
    assert rs.licence_of(["Template:Cc-by-4.0", rs.PERSONALITY], None) == (None, rs.PERSONALITY)
    allowed = CFG["controls"]["refclips"]["image_licences"]
    assert rs.admissible("PD-*", allowed) and not rs.admissible(None, allowed)


def test_manifest_licence_and_personality_rights_refused():
    m = [mrow(i) for i in range(20)]
    rs.check_manifest(m, CFG, 20)
    bad = [dict(r) for r in m]
    bad[3]["licence"] = "CC-BY-SA-4.0"
    with pytest.raises(rs.CurationError, match="licence"):
        rs.check_manifest(bad, CFG, 20)
    pr = [dict(r) for r in m]
    pr[2]["licence_template"] = rs.PERSONALITY
    with pytest.raises(rs.CurationError, match="personality"):
        rs.check_manifest(pr, CFG, 20)


# (f) exactly 20 (NAT 15) or the build refuses
def test_exact_counts():
    s = snap(n=25)
    with pytest.raises(rs.CurationError, match="does not start"):
        rs.check_log(log_for(s, 20, reject_every=2), s, CFG, 20)  # snapshot exhausted before 20 passes
    with pytest.raises(rs.CurationError, match="exactly"):
        rs.check_manifest([mrow(i) for i in range(19)], CFG, 20)
    rs.check_manifest([mrow(i) for i in range(15)], CFG, CFG["controls"]["refclips"]["nat_n"])


# (g) LICENSES.md fields
def test_licenses_md_fields():
    m = [mrow(i) for i in range(3)]
    text = rs.licenses_md({"face": m})
    rs.check_licenses_md(text, m)
    m2 = [dict(r) for r in m]
    m2[1]["attribution"] = "Someone Else"
    with pytest.raises(rs.CurationError, match="attribution"):
        rs.check_licenses_md(text, m2)


# (a) snapshot committed in a strict ancestor of the log/manifest commit
def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def test_snapshot_precedes(tmp_path):
    r = tmp_path
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "snap.json").write_text("{}\n")
    _git(r, "add", "snap.json")
    _git(r, "commit", "-qm", "snap")
    (r / "log.json").write_text("[]\n")
    _git(r, "add", "log.json")
    _git(r, "commit", "-qm", "log")
    assert rs.snapshot_precedes(r, "snap.json", "log.json")
    # same commit -> not a strict ancestor
    (r / "snap2.json").write_text("{}\n")
    (r / "log2.json").write_text("[]\n")
    _git(r, "add", "snap2.json", "log2.json")
    _git(r, "commit", "-qm", "both")
    assert not rs.snapshot_precedes(r, "snap2.json", "log2.json")
    # snapshot changed after the log -> its current blob was not committed before the log
    (r / "snap.json").write_text('{"x": 1}\n')
    _git(r, "commit", "-qam", "edit")
    assert not rs.snapshot_precedes(r, "snap.json", "log.json")


# NAT disjointness: hashes only
def test_nat_disjoint_hashes_only(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("video_id,url,other\nv1,https://youtu.be/abc,SECRET\n")
    known = rs.known_url_hashes([p])
    assert known == {rs.url_hash("https://youtu.be/abc")}
    assert all(len(h) == 64 for h in known) and "SECRET" not in str(known)
    assert rs.nat_disjoint(["https://commons.wikimedia.org/wiki/File:a.webm"], known)
    assert not rs.nat_disjoint(["https://youtu.be/abc "], known)


def test_attribution_plain_text_never_empty():
    assert rs.attribution('<a href="x">Jane Doe</a>', "Own work") == "Jane Doe (Own work)"
    assert rs.attribution("", "") == "unknown author (see file page)"
    assert rs.attribution("A &amp; B", "A &amp; B") == "A & B"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_error_is_never_read_as_zero_results(monkeypatch):
    bodies = [{"error": {"code": "ratelimited"}}, {"error": {"code": "maxlag"}}, {"batchcomplete": True}]
    calls = []

    def urlopen(req, timeout=60):
        calls.append(1)
        return _Resp(json.dumps(bodies[min(len(calls), 3) - 1]).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert rs.fetch_commons("q", 10) == [] and len(calls) == 3  # errors retried; only a real empty is empty
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=60: _Resp(json.dumps({"error": {"code": "x"}}).encode())
    )
    with pytest.raises(rs.CurationError):
        rs.fetch_commons("q", 10)
