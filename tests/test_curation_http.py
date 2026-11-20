"""Owner decision 2026-11-20: Commons/upload.wikimedia.org requests carry the approved User-Agent from config,
honour Retry-After, back off exponentially, keep >= 1 s between requests per host, never fall back to another
client or UA, and STOP when a host keeps answering 429 for longer than the configured limit."""
import io
import urllib.error

import pytest

from yct.config import load_config
from yct.curate import refstim as rs

APPROVED = "yct-research/0.1 (https://github.com/ArioMoniri/yct)"


@pytest.fixture(autouse=True)
def _fresh_hosts():
    rs._LAST_REQUEST.clear()
    yield
    rs._LAST_REQUEST.clear()


def cfg():
    return load_config()["controls"]["curation_http"]


def test_user_agent_is_the_owner_approved_value_and_has_no_email():
    c = cfg()
    assert c["user_agent"] == APPROVED
    assert "@" not in c["user_agent"]
    assert rs.user_agent() == APPROVED
    assert c["min_interval_s"] >= 1.0 and c["max_429_wait_s"] == 1800


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def time(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _http_error(code, retry_after=None):
    hdrs = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("u", code, "x", hdrs, io.BytesIO(b""))


class Opener:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return io.BytesIO(nxt)


def test_every_request_sends_the_config_user_agent():
    op, clk = Opener([b"ok"]), Clock()
    assert rs.http_get("https://upload.wikimedia.org/a.jpg", opener=op, clock=clk) == b"ok"
    assert op.calls[0].get_header("User-agent") == APPROVED


def test_retry_after_is_honoured_then_succeeds():
    op, clk = Opener([_http_error(429, retry_after=42), b"ok"]), Clock()
    assert rs.http_get("https://upload.wikimedia.org/b.jpg", opener=op, clock=clk) == b"ok"
    assert 42 in clk.sleeps
    assert all(r.get_header("User-agent") == APPROVED for r in op.calls)


def test_backoff_is_exponential_without_retry_after():
    op, clk = Opener([_http_error(429), _http_error(429), b"ok"]), Clock()
    rs.http_get("https://upload.wikimedia.org/c.jpg", opener=op, clock=clk)
    waits = [s for s in clk.sleeps if s > cfg()["min_interval_s"]]
    assert len(waits) == 2 and waits[1] >= 2 * waits[0]


def test_min_interval_between_requests_to_the_same_host():
    op, clk = Opener([b"1", b"2"]), Clock()
    rs.http_get("https://upload.wikimedia.org/d.jpg", opener=op, clock=clk)
    t1 = clk.t
    rs.http_get("https://upload.wikimedia.org/e.jpg", opener=op, clock=clk)
    assert clk.t - t1 >= cfg()["min_interval_s"]


def test_persistent_429_beyond_the_limit_stops():
    op, clk = Opener([_http_error(429, retry_after=600)] * 10), Clock()
    with pytest.raises(rs.CurationError, match="429"):
        rs.http_get("https://upload.wikimedia.org/f.jpg", opener=op, clock=clk)
    c = cfg()
    assert c["max_429_wait_s"] < clk.t <= c["max_429_wait_s"] + 600 + 2 * c["min_interval_s"]
    assert len(op.calls) < 10


def test_non_retryable_error_raises_without_switching_client():
    op, clk = Opener([_http_error(404)]), Clock()
    with pytest.raises(rs.CurationError, match="404"):
        rs.http_get("https://upload.wikimedia.org/g.jpg", opener=op, clock=clk)
    assert len(op.calls) == 1
