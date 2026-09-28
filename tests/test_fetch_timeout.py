"""Downloads must time out and retry.

What happened without this: a national run froze for 93 minutes in silence.
Eight worker processes sat at 0% CPU, each blocked in requests.get on a socket
that would never deliver — one ESTABLISHED with no data flowing, the rest in
CLOSE_WAIT where the server had hung up and the client never noticed. requests
waits forever by default. A hang is neither a failure nor a completion, so a
watcher looking for either sees a healthy job, and the log's last line was over
an hour old.
"""
import os

import pytest
import requests

from earthchange import gee_utils


class _Resp:
    def __init__(self, chunks=(b"data",)):
        self._chunks = chunks

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=8192):
        return iter(self._chunks)


def test_a_timeout_is_always_passed(monkeypatch, tmp_path):
    seen = {}

    def fake_get(url, stream=False, timeout=None):
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(requests, "get", fake_get)
    gee_utils._fetch("http://x/y", str(tmp_path / "a.tif"))
    assert seen["timeout"] is not None, "requests.get was called without a timeout"
    connect, read = seen["timeout"]
    assert 0 < connect <= 60
    assert read >= 120, "Earth Engine computes before it sends; allow for that"


def test_a_stalled_download_is_retried_then_raised(monkeypatch, tmp_path):
    calls = {"n": 0}

    def always_timeout(url, stream=False, timeout=None):
        calls["n"] += 1
        raise requests.exceptions.ReadTimeout("stalled")

    monkeypatch.setattr(requests, "get", always_timeout)
    monkeypatch.setattr(gee_utils.time, "sleep", lambda s: None)
    with pytest.raises(requests.exceptions.RequestException):
        gee_utils._fetch("http://x/y", str(tmp_path / "b.tif"), attempts=3)
    assert calls["n"] == 3, "a stalled fetch must be retried, not hung on"


def test_a_transient_stall_recovers(monkeypatch, tmp_path):
    calls = {"n": 0}

    def flaky(url, stream=False, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("reset")
        return _Resp((b"ok",))

    monkeypatch.setattr(requests, "get", flaky)
    monkeypatch.setattr(gee_utils.time, "sleep", lambda s: None)
    out = gee_utils._fetch("http://x/y", str(tmp_path / "c.tif"))
    assert open(out, "rb").read() == b"ok"
    assert calls["n"] == 2


def test_a_partial_file_is_removed_between_attempts(monkeypatch, tmp_path):
    """A resumed download must never append to a stump."""
    target = tmp_path / "d.tif"
    calls = {"n": 0}

    def write_then_fail(url, stream=False, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            target.write_bytes(b"XXXXXXXX")       # a partial body
            raise requests.exceptions.ReadTimeout("mid-body")
        return _Resp((b"good",))

    monkeypatch.setattr(requests, "get", write_then_fail)
    monkeypatch.setattr(gee_utils.time, "sleep", lambda s: None)
    gee_utils._fetch("http://x/y", str(target))
    assert target.read_bytes() == b"good", "the stump survived into the retry"


def test_the_defaults_are_finite():
    connect, read = gee_utils.FETCH_TIMEOUT
    assert connect and read
    assert read < 3600, "a read timeout this long is indistinguishable from none"
    assert gee_utils.FETCH_ATTEMPTS >= 2
