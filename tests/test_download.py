"""P2 downloader (src/yct/curate/download.py), with yt-dlp/ffprobe mocked: no network, no media."""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from yct.curate import download as d

PROBE = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
         "avg_frame_rate": "30000/1001",
         "side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 2},
    ],
    "format": {"duration": "61.5", "bit_rate": "2500000", "tags": {"title": "SECRET TITLE"}},
}


def _cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class FakeRunner:
    """yt-dlp: writes <id>.mp4 unless the url maps to an error; ffprobe: returns PROBE."""

    def __init__(self, errors: dict[str, list[str]] | None = None):
        self.errors = errors or {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "ffprobe":
            return _cp(out=json.dumps(PROBE))
        url = cmd[-1]
        tmpl = Path(cmd[cmd.index("-o") + 1])
        errs = self.errors.get(url)
        if errs:
            return _cp(1, err=errs.pop(0))
        Path(str(tmpl).replace("%(ext)s", "mp4")).write_bytes(b"media-" + url.encode())
        return _cp()


def _rows(*pairs):
    return [{"video_id": v, "url": u} for v, u in pairs]


def test_primary_rows_filters_in_primary(tmp_path):
    m = tmp_path / "m.csv"
    m.write_text("video_id,url,in_primary,qc_pass\na,u1,True,False\nb,u2,False,True\nc,sealed:x,True,True\n")
    assert [r["video_id"] for r in d.primary_rows(m)] == ["a", "c"]  # qc_pass False kept (sensitivity)


def test_cmd_is_polite_and_never_evades():
    cmd = d.ytdlp_cmd("https://x", "yct_1", Path("/o"))
    s = " ".join(cmd)
    assert "bv*+ba/b" in cmd and "--merge-output-format" in cmd
    assert "--sleep-requests 2" in s and "--sleep-interval 5" in s and "--retries 3" in s
    for bad in ("--cookies", "--proxy", "--impersonate", "--write-info-json", "--write-description"):
        assert bad not in cmd
    assert cmd[-1] == "https://x" and cmd[-2] == "--"


def test_download_probe_and_sealed_skip(tmp_path):
    run = FakeRunner()
    probes, logs, events = d.download_all(_rows(("v1", "https://a"), ("v2", "sealed:abc")), tmp_path, run,
                                          log=lambda _: None)
    assert events == []
    assert logs == [{"video_id": "v1", "status": "downloaded", "error_class": ""},
                    {"video_id": "v2", "status": "skipped", "error_class": "sealed_url_owner_action"}]
    p = probes[0]
    assert p["container"] == "mp4" and p["vcodec"] == "h264" and p["acodec"] == "aac"
    assert p["fps"] == 29.97 and p["bitrate_kbps"] == 2500.0 and p["rotation"] == -90
    assert p["audio_hz"] == "44100" and p["audio_channels"] == 2 and p["duration_s"] == 61.5
    assert len(p["sha256"]) == 64 and set(p) == set(d.PROBE_COLUMNS)
    assert not any(c[-1] == "sealed:abc" for c in run.calls)


def test_rate_limit_stops_run(tmp_path):
    run = FakeRunner({"https://b": ["ERROR: HTTP Error 429: Too Many Requests"]})
    rows = _rows(("v1", "https://a"), ("v2", "https://b"), ("v3", "https://c"), ("v4", "sealed:z"))
    probes, logs, events = d.download_all(rows, tmp_path, run, log=lambda _: None)
    assert events == ["rate_limited at v2"]
    assert [x["status"] for x in logs] == ["downloaded", "failed", "not_attempted", "skipped"]
    assert logs[2]["error_class"] == "stopped_rate_limited"
    assert sum(1 for c in run.calls if c[-1] == "https://b") == 1  # never retried
    assert not any(c[-1] == "https://c" for c in run.calls)


def test_bot_check_stops(tmp_path):
    run = FakeRunner({"https://a": ["ERROR: Sign in to confirm you're not a bot"]})
    _, logs, events = d.download_all(_rows(("v1", "https://a")), tmp_path, run, log=lambda _: None)
    assert events and logs[0]["error_class"] == "bot_check"


def test_transient_retried_permanent_not(tmp_path):
    run = FakeRunner({"https://a": ["ERROR: connection reset", "ERROR: timed out"],
                      "https://b": ["ERROR: [youtube] x: Private video"]})
    probes, logs, _ = d.download_all(_rows(("v1", "https://a"), ("v2", "https://b")), tmp_path, run,
                                     log=lambda _: None)
    assert logs[0]["status"] == "downloaded" and logs[1] == {"video_id": "v2", "status": "failed",
                                                             "error_class": "private"}
    assert sum(1 for c in run.calls if c[-1] == "https://b") == 1


def test_resume_skips_existing(tmp_path):
    (tmp_path / "v1.mp4").write_bytes(b"x")
    (tmp_path / "v2.f137.mp4").write_bytes(b"partial")
    run = FakeRunner()
    d.download_all(_rows(("v1", "https://a"), ("v2", "https://b")), tmp_path, run, log=lambda _: None)
    assert [c[-1] for c in run.calls if c[0] == "yt-dlp"] == ["https://b"]


def test_main_writes_csvs_without_titles(tmp_path, monkeypatch):
    m = tmp_path / "m.csv"
    m.write_text("video_id,url,in_primary\nv1,https://a,True\n")
    monkeypatch.setattr(d, "_run", FakeRunner())
    monkeypatch.setattr(d.download_all, "__defaults__", (FakeRunner(), print))
    out = tmp_path / "raw"
    assert d.main(["--manifest", str(m), "--out", str(out)]) == 0
    hdr = next(csv.reader(open(out / "raw_probe.csv")))
    assert hdr == d.PROBE_COLUMNS
    assert next(csv.reader(open(out / "download_log.csv"))) == d.LOG_COLUMNS
    text = (out / "raw_probe.csv").read_text() + (out / "download_log.csv").read_text()
    assert "SECRET TITLE" not in text and "title" not in text.lower()
