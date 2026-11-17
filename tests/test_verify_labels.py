"""scripts/verify_labels.py (v2.md §5 P1, §2b.4 check 2; BUG-022; D-053) on SYNTHETIC sealed tables only:
A-rule recomputation with the batch from the manifest, directory URL present, quote present else
NEEDS_RECHECK; stdout carries counts only (BUG-021)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACC, REJ = "acc" + "epted", "rej" + "ected"
DIR = "https://www.ycombinator.com/companies/"


@pytest.fixture(scope="module")
def vl():
    spec = importlib.util.spec_from_file_location("verify_labels", ROOT / "scripts" / "verify_labels.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _man(tmp_path, batches):
    p = tmp_path / "manifest.csv"
    p.write_text("video_id,claimed_batch,in_primary\n"
                 + "".join(f"{v},{b},True\n" for v, b in batches.items()))
    return p


def _sealed(tmp_path, rows, name="labels.csv"):
    d = tmp_path / "sealed"
    d.mkdir(exist_ok=True)
    cols = sorted({k for r in rows for k in r})
    (d / name).write_text(",".join(cols) + "\n" + "".join(",".join(r.get(c, "") for c in cols) + "\n"
                                                          for r in rows))
    return d


def _good():
    return [
        {"video_id": "yct_0001", "outcome": ACC, "label_confidence": "A", "evidence_url": DIR + "acme",
         "evidence_quote": "we got in"},
        {"video_id": "yct_0002", "outcome": REJ, "label_confidence": "A", "evidence_url": "https://x.org/p",
         "directory_url": DIR + "?batch=S21", "evidence_quote": "our application video was not selected"},
    ]


def test_all_pass_and_counts_only(vl, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SHOW_LABELS", raising=False)
    man = _man(tmp_path, {"yct_0001": "W22", "yct_0002": "S21"})
    sealed = _sealed(tmp_path, _good())
    assert vl.main(["--manifest", str(man), "--sealed", str(sealed), "--owner-side"]) == 0
    out = capsys.readouterr()
    assert "conf-A rows checked = 2; PASS = 2; NEEDS_RECHECK = 0; FAIL = 0" in out.out
    assert ACC not in out.out + out.err and REJ not in out.out + out.err
    assert "yct_0001" not in out.out and out.err == ""


def test_refuses_without_owner_side(vl, tmp_path, capsys):
    man = _man(tmp_path, {"yct_0001": "W22"})
    assert vl.main(["--manifest", str(man), "--sealed", str(_sealed(tmp_path, _good()))]) == 3
    assert "OWNER-SIDE" in capsys.readouterr().err


def test_batch_from_manifest_bug022(vl):
    man = {"yct_0001": {"claimed_batch": "W22"}, "yct_0002": {"claimed_batch": "UNKNOWN"}}
    r1, r2 = _good()
    assert vl.check_row("yct_0001", r1, man) == ("PASS", [])                  # sealed row has no batch
    assert vl.check_row("yct_0002", r2, man) == ("NEEDS_RECHECK", ["batch_unknown"])
    assert vl.check_row("yct_0001", dict(r1, claimed_batch="S20"), man)[0] == "FAIL"
    assert "batch_mismatch" in vl.check_row("yct_0001", dict(r1, claimed_batch="S20"), man)[1]
    assert vl.check_row("yct_0009", r1, man) == ("FAIL", ["not_in_manifest"])


def test_missing_quote_is_needs_recheck_never_auto_a(vl):
    man = {"yct_0001": {"claimed_batch": "W22"}, "yct_0002": {"claimed_batch": "S21"}}
    r1, r2 = _good()
    for vid, r in (("yct_0001", r1), ("yct_0002", r2)):
        st, why = vl.check_row(vid, {k: v for k, v in r.items() if k != "evidence_quote"}, man)
        assert st == "NEEDS_RECHECK" and why == ["quote_missing"]
    assert vl.check_row("yct_0001", dict(r1, evidence_quote="", quote="alt column"), man) == ("PASS", [])


def test_directory_url_rule(vl):
    man = {"yct_0001": {"claimed_batch": "W22"}, "yct_0002": {"claimed_batch": "S21"}}
    r1, r2 = _good()
    st, why = vl.check_row("yct_0001", dict(r1, evidence_url="https://blog.example/post"), man)
    assert st == "FAIL" and why == ["a_rule_evidence"]                       # not a directory URL
    st, why = vl.check_row("yct_0001", dict(r1, evidence_url=""), man)
    assert st == "NEEDS_RECHECK" and why == ["a_rule_evidence"]
    assert vl.check_row("yct_0001", dict(r1, evidence_url="https://b.example", directory_url=DIR + "acme"),
                        man) == ("PASS", [])
    st, why = vl.check_row("yct_0002", {k: v for k, v in r2.items() if k != "directory_url"}, man)
    assert st == "NEEDS_RECHECK" and why == ["a_rule_evidence"]
    assert vl.check_row("yct_0002", dict(r2, outcome="maybe"), man)[0] == "FAIL"


def test_only_conf_a_rows_checked_and_tables_merged(vl, tmp_path):
    rows = _good() + [{"video_id": "yct_0003", "outcome": REJ, "label_confidence": "B"}]
    sealed = _sealed(tmp_path, rows)
    (sealed / "part2.json").write_text(json.dumps([{"video_id": "yct_0002", "outcome": REJ}]))
    res = vl.verify(vl.load_sealed(sealed), {"yct_0001": {"claimed_batch": "W22"},
                                             "yct_0002": {"claimed_batch": "S21"}})
    assert set(res) == {"yct_0001", "yct_0002"}
    (sealed / "part3.json").write_text(json.dumps([{"video_id": "yct_0002", "outcome": ACC}]))
    with pytest.raises(SystemExit, match="yct_0002"):
        vl.load_sealed(sealed)


def test_snapshot_verbatim_quote(vl, tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    body = b"<p>Today   we got in to the batch</p>"
    sha = hashlib.sha256(body).hexdigest()
    (snap / f"{sha}.html").write_bytes(body)
    man = {"yct_0001": {"claimed_batch": "W22"}}
    r1 = dict(_good()[0], evidence_sha256=sha)
    assert vl.check_row("yct_0001", r1, man, snap) == ("PASS", [])
    assert vl.check_row("yct_0001", dict(r1, evidence_quote="we never got in"), man, snap) == \
        ("FAIL", ["quote_not_verbatim"])
    assert vl.check_row("yct_0001", dict(r1, evidence_sha256="0" * 64), man, snap) == \
        ("FAIL", ["snapshot_missing"])
    (snap / f"{'1' * 64}.html").write_bytes(b"other")
    assert vl.check_row("yct_0001", dict(r1, evidence_sha256="1" * 64), man, snap) == \
        ("FAIL", ["snapshot_hash"])


def test_detail_only_to_file_or_stderr_after_banner(vl, tmp_path, capsys, monkeypatch):
    rows = _good()
    del rows[1]["evidence_quote"]
    man = _man(tmp_path, {"yct_0001": "W22", "yct_0002": "S21"})
    sealed = _sealed(tmp_path, rows)
    out_file = tmp_path / "detail.tsv"
    monkeypatch.delenv("SHOW_LABELS", raising=False)
    args = ["--manifest", str(man), "--sealed", str(sealed), "--out", str(out_file), "--owner-side"]
    assert vl.main(args) == 2
    cap = capsys.readouterr()
    assert "NEEDS_RECHECK = 1" in cap.out and "yct_0002" not in cap.out and cap.err == ""
    assert out_file.read_text().strip() == "yct_0002\tNEEDS_RECHECK\tquote_missing"
    monkeypatch.setenv("SHOW_LABELS", "1")
    assert vl.main(["--manifest", str(man), "--sealed", str(sealed), "--owner-side"]) == 2
    cap = capsys.readouterr()
    assert "yct_0002" not in cap.out
    assert cap.err.index("DO NOT PASTE") < cap.err.index("yct_0002")
