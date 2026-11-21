"""D-079 (draft, council re-check pending): v2 image logs after BUG-036.

v1 logs superseded (never read for selection, C3 state or finalise); v2 routing face -> body -> place;
determinism audit v2 vs every v1 log of the category with a committed C1 flip list; revid-drift rule;
file-identity rule (snapshot sha1 == Commons sha1 == sha1 of the downloaded bytes); fail-closed freeze check.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests._refstim_rules import rule_for
from yct.config import load_config
from yct.curate import refstim as rs
from yct.curate import refstim_auto as ra

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config()
D = CFG["controls"]["refclips_d079"]
V1 = {"face": ["data/refstim/image_face_auto_log.jsonl"],
      "body": ["data/refstim/image_body_auto_log.jsonl", "data/refstim/image_body_d078_auto_log.jsonl"],
      "place": []}


# ------------------------------------------------------------------ config and routing
def test_config_key():
    assert D["decision"] == "D-079" and D["amends"] == ["D-074", "D-075", "D-078"]
    assert D["log_version"] == "v2"
    assert D["category_order"] == ["face", "body", "place"] == CFG["controls"]["refclips"]["loc_categories"]
    assert D["superseded_logs"] == V1
    assert D["audit"] == {"exempt_reasons": ["duplicate"], "c1_reasons": ["licence", "personality_rights"],
                          "flip_file": "data/refstim/bug036_c1_flips.json"}
    assert D["revid_rule"] == "evaluate_current_log_both"
    assert D["identity_rule"] == "reject_identity_changed"    # D-079 re-check B1 (was "stop" in v2 draft)
    assert D["finality"] == "v2_is_selection"


def test_v2_log_paths():
    assert {c: rs.image_log_v2(c, CFG) for c in D["category_order"]} == {
        c: f"data/refstim/image_{c}_auto_log_v2.jsonl" for c in ("face", "body", "place")}


def test_v1_logs_exist_and_are_never_v2_paths():
    for cat, paths in V1.items():
        for p in paths:
            assert (ROOT / p).exists()
            assert p != rs.image_log_v2(cat, CFG)


@pytest.mark.parametrize("mut", ["version", "superseded", "order", "missing"])
def test_routing_refuses(mut):
    cfg = copy.deepcopy(CFG)
    d = cfg["controls"]["refclips_d079"]
    if mut == "version":
        d["log_version"] = "v1"
    elif mut == "superseded":
        d["logs"]["face"] = V1["face"][0]
    elif mut == "order":
        d["category_order"] = ["body", "face", "place"]
    else:
        del cfg["controls"]["refclips_d079"]
    with pytest.raises((rs.CurationError, KeyError)):
        rs.check_d079_routing(cfg)
        rs.image_log_v2("face", cfg)


def test_runner_never_routes_to_v1_logs():
    src = (ROOT / "scripts" / "refstim_auto_run.py").read_text()
    assert "image_log_rel(" not in src and 'a["logs"]["image"]' not in src
    assert src.count("rs.image_log_v2(") >= 2          # run() and finalise()
    assert "ra.check_frozen_d079(cfg)" in src and "ra.audit_v2(" in src and "ra.identity_ok(" in src


# ------------------------------------------------------------------ freeze (fail-closed)
def frozen(cfg, keys):
    c = copy.deepcopy(cfg)
    c["frozen"] = [r for r in c.get("frozen") or [] if not r["key"].startswith("controls.refclips_d079")]
    c["frozen"] += [{"key": k, "frozen_at": "0" * 40} for k in keys]
    c["controls"]["refclips_d079_artifacts"]["flip_sha256"] = "a" * 64
    return c


def test_unfrozen_d079_is_a_stop():
    with pytest.raises(ra.StopError, match="not frozen"):
        ra.check_frozen_d079(frozen(CFG, []))
    with pytest.raises(ra.StopError, match="not frozen"):
        ra.check_frozen_d079(frozen(CFG, ["controls.refclips_d079"]))
    keys = ["controls.refclips_d079", "controls.refclips_d079_artifacts.flip_sha256"]
    ra.check_frozen_d079(frozen(CFG, keys))


def test_unset_flip_sha_is_a_stop():
    c = frozen(CFG, ["controls.refclips_d079", "controls.refclips_d079_artifacts.flip_sha256"])
    c["controls"]["refclips_d079_artifacts"]["flip_sha256"] = None
    with pytest.raises(ra.StopError, match="flip_sha256"):
        ra.check_frozen_d079(c)


# ------------------------------------------------------------------ C1 flip list
def flip_doc():
    return {"decision": "D-079",
            "logs": {"image_face_auto_log.jsonl": {"inadm_to_adm": ["k1"], "adm_to_inadm": []},
                     "image_body_auto_log.jsonl": {"inadm_to_adm": ["k2"], "adm_to_inadm": []},
                                          "image_body_d078_auto_log.jsonl": {"inadm_to_adm": [],
                                                                            "adm_to_inadm": []}}}


def test_flip_file_sha_and_content_checked(tmp_path):
    p = tmp_path / "flips.json"
    p.write_text(json.dumps(flip_doc()))
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    f = rs.load_flips(p, sha, V1)
    assert f == {"image_face_auto_log.jsonl": {"k1"}, "image_body_auto_log.jsonl": {"k2"},
                 "image_body_d078_auto_log.jsonl": set()}
    with pytest.raises(rs.CurationError, match="sha256"):
        rs.load_flips(p, "b" * 64, V1)
    bad = flip_doc()
    bad["logs"]["image_face_auto_log.jsonl"]["adm_to_inadm"] = ["k9"]   # recheck: v1 never over-admitted
    p.write_text(json.dumps(bad))
    with pytest.raises(rs.CurationError, match="adm_to_inadm"):
        rs.load_flips(p, hashlib.sha256(p.read_bytes()).hexdigest(), V1)
    del bad["logs"]["image_body_d078_auto_log.jsonl"]
    bad["logs"]["image_face_auto_log.jsonl"]["adm_to_inadm"] = []
    p.write_text(json.dumps(bad))
    with pytest.raises(rs.CurationError, match="logs"):
        rs.load_flips(p, hashlib.sha256(p.read_bytes()).hexdigest(), V1)


# ------------------------------------------------------------------ determinism audit v2 vs v1
def r(title, decision="reject", reason=None, key=None):
    return {"title": title, "sha256_title": key or title, "decision": decision, "reason": reason,
            "rule": rule_for(decision, reason)}   # BUG-038: real rows carry their rule


EX, C1 = ("duplicate",), ("licence", "personality_rights")


def audit(row, prior_rows, flips=frozenset()):
    priors = [("L", {p["title"]: p for p in prior_rows})]
    ra.audit_v2(row, priors, {"L": set(flips)}, EX, C1)


def test_audit_equal_rows_pass_and_absent_title_passes():
    audit(r("a", "reject", "multi_subject"), [r("a", "reject", "multi_subject")])
    audit(r("a", "pass"), [r("a", "pass")])
    audit(r("new", "pass"), [r("a", "pass")])


def test_audit_duplicate_is_exempt():
    audit(r("a", "reject", "duplicate"), [r("a", "pass")])
    audit(r("a", "pass"), [r("a", "reject", "duplicate")])


def test_audit_listed_flip_allows_any_non_c1_outcome():
    audit(r("a", "pass"), [r("a", "reject", "licence")], {"a"})
    audit(r("a", "reject", "face_not_frontal"), [r("a", "reject", "licence")], {"a"})


def test_audit_unlisted_c1_flip_is_a_stop():
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(r("a", "pass"), [r("a", "reject", "licence")])


def test_audit_listed_flip_still_c1_in_v2_is_a_stop():
    with pytest.raises(ra.StopError, match="flip list"):
        audit(r("a", "reject", "licence"), [r("a", "reject", "licence")], {"a"})


def test_audit_listed_flip_not_c1_in_v1_is_a_stop():
    with pytest.raises(ra.StopError, match="flip list"):
        audit(r("a", "pass"), [r("a", "reject", "multi_subject")], {"a"})


@pytest.mark.parametrize("v1,v2", [(("pass", None), ("reject", "licence")),
                                   (("reject", "multi_subject"), ("reject", "personality_rights")),
                                   (("pass", None), ("reject", "face_not_frontal")),
                                   (("reject", "licence"), ("reject", "personality_rights"))])
def test_audit_any_other_mismatch_is_a_stop(v1, v2):
    with pytest.raises(ra.StopError, match="determinism audit"):
        audit(r("a", *v2), [r("a", *v1)])


def test_audit_checks_every_v1_log_of_the_category():
    priors = [("A", {"a": r("a", "reject", "licence")}), ("B", {"a": r("a", "reject", "multi_subject")})]
    ra.audit_v2(r("a", "reject", "multi_subject"), priors, {"A": {"a"}, "B": set()}, EX, C1)
    with pytest.raises(ra.StopError):
        ra.audit_v2(r("a", "pass"), priors, {"A": {"a"}, "B": set()}, EX, C1)


def test_audit_flip_list_is_keyed_by_sha256_title():
    priors = [("L", {"File:x.jpg": r("File:x.jpg", "reject", "licence", key="k")})]
    ra.audit_v2(r("File:x.jpg", "pass", key="k"), priors, {"L": {"k"}}, EX, C1)


# ------------------------------------------------------------------ C3 state from v2 logs only
def test_preload_state_reads_only_v2_logs(tmp_path):
    rows = [{"title": "a", "decision": "pass", "sha1": "s1", "values": {"dhash": "ff"}, "log_version": "v2"},
            {"title": "b", "decision": "reject", "sha1": "s2", "values": {}, "log_version": "v2"}]
    (tmp_path / "data" / "refstim").mkdir(parents=True)
    (tmp_path / rs.image_log_v2("face", CFG)).write_text("\n".join(map(json.dumps, rows)) + "\n")
    for p in V1["face"]:
        (tmp_path / p).write_text(json.dumps({"title": "v1", "decision": "pass", "sha1": "v1",
                                              "values": {"dhash": "1"}}) + "\n")
    st = ra.State()
    done = ra.preload_v2(st, "face", CFG, tmp_path)
    assert [x["title"] for x in done] == ["a", "b"]
    assert st.pass_sha1 == {"s1"} and st.pass_dhash == [0xFF]


def test_preload_refuses_a_category_out_of_order(tmp_path):
    (tmp_path / "data" / "refstim").mkdir(parents=True)
    st = ra.State()
    with pytest.raises(ra.StopError, match="order"):
        ra.preload_v2(st, "body", CFG, tmp_path, ran=[])          # face must run first
    ra.preload_v2(st, "body", CFG, tmp_path, ran=["face"])


def test_preload_refuses_v1_row_in_v2_log(tmp_path):
    (tmp_path / "data" / "refstim").mkdir(parents=True)
    (tmp_path / rs.image_log_v2("face", CFG)).write_text(json.dumps(
        {"title": "a", "decision": "pass", "sha1": "s", "values": {"dhash": "1"},
         "log_version": "v1"}) + "\n")
    with pytest.raises(ra.StopError, match="log_version"):
        ra.preload_v2(ra.State(), "face", CFG, tmp_path)


# ------------------------------------------------------------------ identity and revid rules
def test_identity_rule():
    ra.check_identity("ab", "ab")
    ra.check_identity("ab", "ab", "ab")
    for snap, com, data in [("ab", "cd", None), ("ab", "ab", "cd"), (None, "ab", None), ("ab", None, None)]:
        with pytest.raises(ra.StopError, match="identity"):
            ra.check_identity(snap, com, data)


def test_revid_fields_log_both_and_flag_drift():
    assert ra.revid_fields({"revid": 5}, {"read_revid": 5}) == {"snapshot_revid": 5, "read_revid": 5,
                                                                "revid": 5, "revid_drift": False}
    assert ra.revid_fields({"revid": 5}, {"read_revid": 7})["revid_drift"] is True
    with pytest.raises(ra.StopError, match="read_revid"):
        ra.revid_fields({"revid": 5}, {"read_revid": None})


def test_templates_digest_is_stable():
    t = ["Template:Information", "Template:Cc-by-4.0"]
    assert ra.templates_digest(t) == hashlib.sha256(json.dumps(t).encode()).hexdigest()


# ------------------------------------------------------------------ the committed flip file
def committed_flips():
    sha = CFG["controls"]["refclips_d079_artifacts"]["flip_sha256"]
    return rs.load_flips(ROOT / D["audit"]["flip_file"], sha, D["superseded_logs"])


def test_committed_flip_file_matches_config_and_recheck_counts():
    want = {"image_face_auto_log.jsonl": 260, "image_body_auto_log.jsonl": 108,
            "image_body_d078_auto_log.jsonl": 3}
    assert {k: len(v) for k, v in committed_flips().items()} == want


def test_every_listed_flip_is_a_v1_c1_reject():
    f = committed_flips()
    for paths in V1.values():
        for p in paths:
            rows = {x["sha256_title"]: x for x in map(json.loads, (ROOT / p).read_text().splitlines())}
            listed = f[Path(p).name]
            assert listed <= set(rows)
            assert all(rows[k]["reason"] in D["audit"]["c1_reasons"] for k in listed)


# ------------------------------------------------------------------ re-check flip list builder
def test_recheck_diff_rows_lists_flips_by_sha256_title():
    import importlib.util

    spec = importlib.util.spec_from_file_location("recheck", ROOT / "scripts" / "refstim_bug036_recheck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = [{"title": "a", "sha256_title": "ka", "rule": "C1", "decision": "reject", "reason": "licence",
             "licence": None, "revid": 1},
            {"title": "b", "sha256_title": "kb", "rule": None, "decision": "pass", "licence": "CC0",
             "licence_template": "Template:Cc-zero", "revid": 2},
            {"title": "c", "sha256_title": "kc", "rule": "C0", "decision": "reject", "licence": None,
             "revid": 3}]
    meta = {"a": {"templates": ["Template:Cc-by-4.0"], "license_short": "", "read_revid": 1},
            "b": {"templates": ["Template:Cc-zero"], "license_short": "", "read_revid": 5}}
    n, lists = mod.diff_rows(rows, meta)
    assert n["rows"] == 2 and n["inadm_to_adm"] == 1 and n["adm_to_inadm"] == 0 and n["revid_changed"] == 1
    assert lists == {"inadm_to_adm": ["ka"], "adm_to_inadm": [], "revid_changed": ["kb"]}
