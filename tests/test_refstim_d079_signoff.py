"""D-079 final sign-off (wf_7797c743-b64): referee B1 (a byte-stage sha1 mismatch is a download defect:
delete, re-download once, then STOP naming the title; only a metadata-stage mismatch is the identity_changed
reject) and referee B2 / QA B1 (identity_changed rows log identity_stage and data_sha1; finalise writes the
identity_changed disclosure list, or "none")."""
import hashlib
from pathlib import Path

import pytest

from yct.curate import refstim_auto as ra

GOOD, BAD = b"good-bytes", b"stale-bytes"
SHA_GOOD = hashlib.sha1(GOOD).hexdigest()
RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "refstim_auto_run.py"


def downloader(payloads):
    calls = []

    def dl(url, dest):
        calls.append(url)
        dest.write_bytes(payloads[min(len(calls), len(payloads)) - 1])
        return dest
    return dl, calls


def test_bytes_match_first_download(tmp_path):
    dl, calls = downloader([GOOD])
    src = tmp_path / "a.jpg"
    assert ra.fetch_verified(src, "u", SHA_GOOD, "File:a.jpg", dl) == SHA_GOOD
    assert calls == ["u"] and src.read_bytes() == GOOD


def test_bad_bytes_are_deleted_and_redownloaded_once(tmp_path):
    dl, calls = downloader([BAD, GOOD])
    src = tmp_path / "a.jpg"
    assert ra.fetch_verified(src, "u", SHA_GOOD, "File:a.jpg", dl) == SHA_GOOD
    assert calls == ["u", "u"] and src.read_bytes() == GOOD


def test_bad_bytes_twice_is_a_stop_naming_the_title(tmp_path):
    dl, calls = downloader([BAD, BAD, BAD])
    src = tmp_path / "a.jpg"
    with pytest.raises(ra.StopError, match="File:a.jpg"):
        ra.fetch_verified(src, "u", SHA_GOOD, "File:a.jpg", dl)
    assert calls == ["u", "u"] and not src.exists()


def test_stale_cached_file_is_redownloaded(tmp_path):
    src = tmp_path / "a.jpg"
    src.write_bytes(BAD)
    dl, calls = downloader([GOOD])
    assert ra.fetch_verified(src, "u", SHA_GOOD, "File:a.jpg", dl) == SHA_GOOD
    assert calls == ["u"]


def test_byte_stage_is_never_an_identity_reject_in_runner():
    src = RUNNER.read_text()
    assert "ra.fetch_verified(" in src
    assert 'raise ra.RejectError("D1", ra.IDENTITY_REASON)' not in src


def test_identity_reject_row_logs_stage_and_data_sha1():
    c = ra.Candidate("File:x.jpg", "k", {}, {}, None, None, True, lambda: None)
    row = ra.identity_reject_row("face", c)
    assert row["identity_stage"] == "metadata" and row["data_sha1"] is None
    assert (row["rule"], row["reason"]) == ("D1", "identity_changed")


def test_identity_disclosure_lists_rows_or_none():
    rows = [{"title": "File:a.jpg", "decision": "pass", "reason": None},
            {"title": "File:b.jpg", "decision": "reject", "reason": "identity_changed", "sha1": "s1",
             "commons_sha1": "c1", "identity_stage": "metadata", "data_sha1": None}]
    assert ra.identity_disclosure(rows) == [{"title": "File:b.jpg", "sha1": "s1", "commons_sha1": "c1",
                                             "identity_stage": "metadata", "data_sha1": None}]
    assert ra.identity_disclosure(rows[:1]) == "none"


def test_identity_disclosure_refuses_a_row_without_stage():
    with pytest.raises(ra.StopError, match="File:b.jpg"):
        ra.identity_disclosure([{"title": "File:b.jpg", "decision": "reject", "reason": "identity_changed",
                                 "sha1": "s1", "commons_sha1": "c1"}])


def test_finalise_writes_identity_disclosure():
    src = RUNNER.read_text()
    assert "ra.identity_disclosure(" in src and "image_identity_changed_v2.json" in src
