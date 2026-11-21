"""D-079 council re-check (wf_4ef7126f-cea): pre-stated STOP resolutions (biostat B1), the duplicate
exemption restricted to non-C1 counterparts (biostat B2), strict log_version in preload (QA B1, watchdog N2),
C4 extmetadata revision equal to the read revision (watchdog N3), titles in STOP messages (QA)."""
import json
from pathlib import Path

import pytest

from tests.test_refstim_bug036 import TITLES, fake_commons
from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

CFG = load_config()
D9 = CFG["controls"]["refclips_d079"]
EX, C1 = tuple(D9["audit"]["exempt_reasons"]), tuple(D9["audit"]["c1_reasons"])


def r(title, decision="reject", reason=None):
    return {"title": title, "sha256_title": title, "decision": decision, "reason": reason}


def audit(row, prior_rows, flips=frozenset()):
    ra.audit_v2(row, [("L", {p["title"]: p for p in prior_rows})], {"L": set(flips)}, EX, C1)


# ------------------------------------------------------------------ B1: pre-stated STOP resolutions
def test_config_states_every_stop_resolution():
    assert D9["identity_rule"] == "reject_identity_changed"
    assert D9["extra_reject_reasons"] == ["identity_changed"]
    assert D9["stop_resolution"] == {"identity_mismatch": "reject_identity_changed_resume_next_rank",
                                     "lastrevid_moved": "retry_batch_once_then_stop_to_council",
                                     "other_audit_stop": "code_defect_bug_entry_v3_from_rank_1"}
    assert "identity_changed" not in CFG["controls"]["refclips"]["reject_reasons"]   # frozen D-071 list


def test_identity_mismatch_is_a_reject_not_a_stop():
    assert ra.identity_ok("ab", "ab") is True
    assert ra.identity_ok("ab", "ab", "ab") is True
    assert ra.identity_ok("ab", "cd") is False
    assert ra.identity_ok("ab", "ab", "cd") is False


@pytest.mark.parametrize("snap,com", [(None, "ab"), ("ab", None), ("", "ab")])
def test_identity_with_missing_sha1_is_still_a_stop(snap, com):
    with pytest.raises(ra.StopError, match="identity"):
        ra.identity_ok(snap, com, title="File:x.jpg")


def test_identity_reject_row():
    c = ra.Candidate("File:x.jpg", "k", {}, {}, None, None, True, lambda: None)
    row = ra.identity_reject_row("face", c)
    assert row == {"title": "File:x.jpg", "sha256_title": "k", "category": "face", "decision": "reject",
                   "rule": "D1", "reason": "identity_changed", "values": {}}


def test_byte_identity_mismatch_in_load_becomes_a_reject_row():
    def load():
        raise ra.RejectError("D1", "identity_changed")
    c = ra.Candidate("File:x.jpg", "k", {"mediatype": CFG["controls"]["refclips_d074"]["bitmap_mediatype"],
                                         "mime": "image/jpeg", "width": 4000, "height": 4000, "sha1": "s"},
                     {"description": "", "categories": ""}, "CC0", "Template:Cc-zero", True, load)
    row = ra.evaluate_image("face", c, None, CFG, ra.State(), set(), 1)
    assert (row["decision"], row["rule"], row["reason"]) == ("reject", "D1", "identity_changed")


def test_check_log_accepts_identity_changed_only_as_an_extra_reason():
    snap = {"entries": [{"title": "File:a.jpg"}, {"title": "File:b.jpg"}]}
    order = rs.ordered(snap)
    log = [{"title": order[0]["title"], "sha256_title": rs.title_key(order[0]["title"]),
            "decision": "reject", "reason": "identity_changed"},
           {"title": order[1]["title"], "sha256_title": rs.title_key(order[1]["title"]),
            "decision": "pass", "reason": ""}]
    with pytest.raises(rs.CurationError, match="reject_reasons"):
        rs.check_log(log, snap, CFG, 1)
    assert len(rs.check_log(log, snap, CFG, 1, extra_reasons=D9["extra_reject_reasons"])) == 1


def test_audit_identity_changed_row_is_exempt_whatever_v1_said():
    for v1 in [r("a", "pass"), r("a", "reject", "licence"), r("a", "reject", "multi_subject")]:
        audit(r("a", "reject", "identity_changed"), [v1])


def test_other_audit_stop_names_the_defect_resolution():
    with pytest.raises(ra.StopError, match="code defect.*v3 from rank 1"):
        audit(r("a", "pass"), [r("a", "reject", "multi_subject")])


def test_lastrevid_moving_is_retried_once_then_stops():
    t = TITLES[8]
    n = {"calls": 0}
    moving = fake_commons(cap=2, revids={(t, 0): 100, (t, 2): 101})
    steady = fake_commons(cap=2)

    def flaky(params, pause=0.0):                 # first attempt moves, the retry is steady
        if params.get("tlcontinue") is None and "templates" in params.get("prop", ""):
            n["calls"] += 1
        return (moving if n["calls"] == 1 else steady)(params, pause)

    meta = rs.page_meta_c4([t], get=flaky)
    assert meta[t]["read_revid"] == 100 and n["calls"] == 2

    with pytest.raises(rs.CurationError, match=rf"lastrevid.*{t}.*STOP to the council"):
        rs.page_meta_c4([t], get=moving)          # moves on both attempts


def test_revid_moved_is_a_curation_error_with_the_title():
    t = TITLES[8]
    with pytest.raises(rs.RevidMovedError) as e:
        rs.page_meta([t], get=fake_commons(cap=2, revids={(t, 0): 100, (t, 2): 101}))
    assert e.value.title == t and isinstance(e.value, rs.CurationError)


# ------------------------------------------------------------------ B2: duplicate exemption vs C1
def test_v1_duplicate_vs_v2_c1_reject_is_a_stop():
    for c1 in C1:
        with pytest.raises(ra.StopError, match="determinism audit"):
            audit(r("a", "reject", c1), [r("a", "reject", "duplicate")])


def test_unlisted_v1_c1_reject_vs_v2_duplicate_is_a_stop():
    for c1 in C1:
        with pytest.raises(ra.StopError, match="determinism audit"):
            audit(r("a", "reject", "duplicate"), [r("a", "reject", c1)])


def test_listed_flip_v1_licence_vs_v2_duplicate_is_allowed():
    audit(r("a", "reject", "duplicate"), [r("a", "reject", "licence")], {"a"})


def test_duplicate_vs_non_c1_still_exempt():
    audit(r("a", "reject", "duplicate"), [r("a", "pass")])
    audit(r("a", "pass"), [r("a", "reject", "duplicate")])
    audit(r("a", "reject", "duplicate"), [r("a", "reject", "face_not_frontal")])


# ------------------------------------------------------------------ QA B1 / watchdog N2: strict preload
def test_preload_refuses_v1_shaped_row_without_log_version(tmp_path):
    (tmp_path / "data" / "refstim").mkdir(parents=True)
    v1_row = {"title": "a", "sha256_title": "k", "category": "face", "decision": "pass", "rule": None,
              "reason": None, "values": {"dhash": "1"}, "sha1": "s"}       # real v1 rows carry no log_version
    (tmp_path / rs.image_log_v2("face", CFG)).write_text(json.dumps(v1_row) + "\n")
    with pytest.raises(ra.StopError, match="log_version"):
        ra.preload_v2(ra.State(), "face", CFG, tmp_path)


def test_real_v1_logs_have_no_log_version_key():
    root = Path(__file__).resolve().parents[1]
    for paths in D9["superseded_logs"].values():
        for p in paths:
            rows = [json.loads(x) for x in (root / p).read_text().splitlines() if x.strip()]
            assert rows and all("log_version" not in x for x in rows)


# ------------------------------------------------------------------ watchdog N3: C4 revision check
def test_page_meta_c4_compares_extmetadata_revision_with_read_revid():
    t = TITLES[0]
    seen = {"n": 0}
    base, later = fake_commons(cap=1000), fake_commons(cap=1000, revids={(t, 0): 101})

    def get(params, pause=0.0):                   # templates query at rev 100, the C4 query always at 101
        if "templates" in params.get("prop", ""):
            seen["n"] += 1
            return base(params, pause)
        return later(params, pause)

    with pytest.raises(rs.CurationError, match=rf"C4.*{t}.*STOP to the council"):
        rs.page_meta_c4([t], get=get)
    assert seen["n"] == 2                          # retried once


def test_page_meta_c4_requests_info_on_the_extmetadata_query():
    calls = []
    good = fake_commons(cap=1000)

    def get(params, pause=0.0):
        calls.append(params)
        return good(params, pause)

    meta = rs.page_meta_c4(TITLES[:2], get=get)
    ext = [c for c in calls if "templates" not in c["prop"]]
    assert ext and all("info" in c["prop"].split("|") for c in ext)
    assert meta[TITLES[0]]["description"] and meta[TITLES[0]]["categories"] == "c1 c2"


def test_runner_uses_the_library_page_meta_c4():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "refstim_auto_run.py").read_text()
    assert "rs.page_meta_c4(" in src and "ra.identity_ok(" in src and "ra.check_identity(" not in src


# ------------------------------------------------------------------ QA: STOP messages carry the title
def test_stop_messages_name_the_title():
    with pytest.raises(ra.StopError, match="File:x.jpg"):
        ra.identity_ok(None, "ab", title="File:x.jpg")
    with pytest.raises(ra.StopError, match="File:x.jpg"):
        ra.revid_fields({"revid": 1, "title": "File:x.jpg"}, {"read_revid": None})
    src = (Path(__file__).resolve().parents[1] / "scripts" / "refstim_auto_run.py").read_text()
    assert "no download url for {key}\"" not in src and "decode failed for BITMAP file {key}\"" not in src
