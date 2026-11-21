"""T-NAT0 CPU stage (D-075 §3): metadata rules, buffer fill, resume, fail-closed STOPs, streamed download."""
import io
import json
import urllib.error

import pytest

from yct.config import load_config
from yct.curate import natstim as ns
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

CFG = load_config()


def meta(t, templates=("Template:Cc-zero",), dur=120.0, desc="", cats=""):
    return {"templates": list(templates), "license_short": "", "duration": dur, "description": desc,
            "categories": cats, "url": f"https://upload.wikimedia.org/x/{t}.webm", "read_revid": 7,
            "artist": "A", "credit": ""}


def test_metadata_rules_in_order():
    d = ns.metadata_decide
    assert d("t", meta("t", ["Template:Personality rights", "Template:Cc-zero"]), CFG, set(), 1)["reason"] \
        == "personality_rights"
    assert d("t", meta("t", ["Template:Cc-by-sa-4.0"]), CFG, set(), 1)["reason"] == "licence"
    assert d("t", meta("t", dur=57.9), CFG, set(), 1)["reason"] == "too_short"
    assert d("t", meta("t", desc="Y Combinator Demo"), CFG, set(), 1)["reason"] == "yc_link"
    assert d("t", meta("t", desc="talk at YC W21"), CFG, set(), 1)["reason"] == "yc_link"
    ok = d("t", meta("t", dur=58.0), CFG, set(), 1)
    assert ok["decision"] == "continue" and ok["values"]["licence"] == "CC0"


def test_missing_duration_is_a_stop():
    with pytest.raises(ra.StopError):
        ns.metadata_decide("t", meta("t", dur=None), CFG, set(), 1)


def test_reasons_are_frozen_reasons():
    for r in ns.CPU_RULES.values():
        for x in (r if isinstance(r, list) else [r]):
            assert x in CFG["controls"]["refclips"]["reject_reasons"]


def order(n):
    return sorted([{"title": f"File:v{i}.webm", "pageid": i, "revid": 1} for i in range(n)],
                  key=lambda e: rs.title_key(e["title"]))


def runner(tmp_path, n=60, short=(), bad=(), calls=None, known=frozenset()):
    calls = [] if calls is None else calls

    def pm(titles):
        calls.append(len(titles))
        return {t: meta(t, ["Template:Cc-by-sa-4.0"] if t in bad else ["Template:Cc-zero"]) for t in titles}

    def fn(e, m):
        return {"trimmed_duration_s": 40.0 if e["title"] in short else 58.0, "source_sha1": "s1",
                "source_sha256": "s2", "sha256": "t" + e["title"], "video_id": "id" + e["title"]}

    log = tmp_path / "nat_auto_log.jsonl"
    o = order(n)
    out = ns.run_cpu(o, CFG, log, pm, fn, set(), 1, set(known))
    return o, log, out


def test_fills_buffer_in_order_and_stops(tmp_path):
    o, log, out = runner(tmp_path, short={order(60)[1]["title"]}, bad={order(60)[0]["title"]})
    rows = ns.load_log(log)
    assert [r["title"] for r in rows] == [e["title"] for e in o[:len(rows)]]
    assert len(out) == CFG["controls"]["refclips_auto"]["nat"]["cpu_buffer"] == 40
    assert rows[0]["reason"] == "licence" and rows[1]["reason"] == "too_short" and rows[1]["rule"] == "P2"
    assert len(rows) == 42 and rows[-1]["decision"] == "pass"
    assert all(r["stage"] == "cpu" for r in rows)
    assert ns.buffer_ids(rows, CFG) == [r["t1_name"] for r in rows if r["decision"] == "pass"]


def test_resume_never_reevaluates(tmp_path):
    o, log, _ = runner(tmp_path, n=60)
    n0 = len(ns.load_log(log))
    calls = []
    runner(tmp_path, n=60, calls=calls)
    assert len(ns.load_log(log)) == n0 and calls == []


def test_resume_refuses_non_prefix(tmp_path):
    log = tmp_path / "nat_auto_log.jsonl"
    log.write_text(json.dumps({"stage": "cpu", "title": "File:zzz", "decision": "reject"}) + "\n")
    with pytest.raises(ra.StopError, match="prefix"):
        ns.run_cpu(order(5), CFG, log, lambda t: {}, lambda e, m: {}, set(), 1, set())


def test_known_url_hash_is_a_stop(tmp_path):
    o = order(3)
    u = f"https://upload.wikimedia.org/x/{o[0]['title']}.webm"
    with pytest.raises(ra.StopError, match="manifest"):
        runner(tmp_path, n=3, known={rs.url_hash(u)})


def test_normalise_error_propagates_as_stop(tmp_path):
    def fn(e, m):
        raise ra.StopError("decode failed")

    with pytest.raises(ra.StopError, match="decode"):
        ns.run_cpu(order(3), CFG, tmp_path / "l.jsonl", lambda ts: {t: meta(t) for t in ts}, fn,
                   set(), 1, set())
    assert not (tmp_path / "l.jsonl").exists()


def test_exhausted_snapshot_returns_short_buffer(tmp_path):
    _, log, out = runner(tmp_path, n=10)
    assert len(out) == 10


def test_snapshot_check_uses_frozen_sha(tmp_path):
    o = ns.check_snapshot(CFG, rs.REFSTIM / "snapshots" / "nat_nat_snapshot.json")
    assert len(o) == 1000 and o == sorted(o, key=lambda e: rs.title_key(e["title"]))
    bad = tmp_path / "s.json"
    bad.write_text("{}")
    with pytest.raises(ra.StopError):
        ns.check_snapshot(CFG, bad)


class _Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def time(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_stream_get_ua_retry_after_and_part_cleanup(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req.get_header("User-agent"))
        if len(seen) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "x", {"Retry-After": "7"}, None)
        return io.BytesIO(b"abc" * 1000)

    dest = tmp_path / "f.webm"
    ns.stream_get("https://upload.wikimedia.org/a.webm", dest, opener=opener, clock=_Clock())
    assert dest.read_bytes() == b"abc" * 1000 and not (tmp_path / "f.webm.part").exists()
    assert set(seen) == {CFG["controls"]["curation_http"]["user_agent"]}


def test_stream_get_404_raises(tmp_path):
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "x", {}, None)

    with pytest.raises(rs.CurationError):
        ns.stream_get("https://upload.wikimedia.org/b.webm", tmp_path / "g", opener=opener, clock=_Clock())
