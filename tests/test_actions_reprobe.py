"""Tests for the post-spawn re-probe loop.

The loop polls TCP+HTTP at increasing intervals (0.5s, 1s, 2s, 3.5s, 5s)
within a 5-second wall budget; first ``up`` wins.
"""

from __future__ import annotations

import http.server
import socket
import threading

import pytest

from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._detection import Detection


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _PypiServerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><a href='pkg/'>pkg</a></body></html>")

    def log_message(self, *a, **kw):  # silence
        pass


@pytest.fixture
def pypiserver_on_port():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PypiServerHandler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port
    srv.shutdown()
    srv.server_close()


def _detection(port: int, flavor: str = "pypiserver") -> Detection:
    return Detection(
        name=f"{flavor}:{port}",
        flavor=flavor,
        host="127.0.0.1",
        port=port,
        url=f"http://127.0.0.1:{port}/",
        status="down",
        source="declared",
    )


def test_reprobe_succeeds_immediately(pypiserver_on_port):
    result = probe(_detection(pypiserver_on_port), budget_seconds=5.0)
    assert result.status == "up"


def test_reprobe_never_succeeds_when_no_server():
    port = _free_port()
    result = probe(_detection(port), budget_seconds=1.0)
    assert result.status in ("absent", "down")


def test_reprobe_flavor_mismatch(pypiserver_on_port):
    det = _detection(pypiserver_on_port, flavor="devpi")
    result = probe(det, budget_seconds=2.0)
    assert result.status == "down"
    assert "flavor" in (result.detail or "")


def test_reprobe_zero_budget_returns_immediately():
    """budget_seconds < smallest offset (0.5) → loop never fires; never sleeps."""
    sleep_calls = []
    times = iter([0.0, 0.0, 0.0])  # consumed if probe ever calls _now
    detection = _detection(1)  # port 1, won't be probed
    result = probe(
        detection,
        budget_seconds=0.4,
        _sleep=lambda s: sleep_calls.append(s),
        _now=lambda: next(times, 0.0),
    )
    assert result.status == "absent"
    assert sleep_calls == []  # no sleeps occurred


def test_reprobe_early_exit_on_first_success(monkeypatch):
    """Once status='up', no further attempts run."""
    from auntiepypi._actions import _reprobe

    attempts = []

    def fake_attempt(d):
        attempts.append(d)
        # second attempt succeeds; we want to confirm a third never happens
        return _reprobe.ReprobeResult(status="up" if len(attempts) >= 2 else "down")

    monkeypatch.setattr(_reprobe, "_attempt", fake_attempt)
    sleep_calls = []
    # Use a controlled clock to walk through the offsets.
    elapsed = [0.0]

    def fake_now():
        return elapsed[0]

    def fake_sleep(s):
        sleep_calls.append(s)
        elapsed[0] += s

    result = probe(
        _detection(1),
        budget_seconds=5.0,
        _sleep=fake_sleep,
        _now=fake_now,
    )
    assert result.status == "up"
    assert len(attempts) == 2  # first attempt at offset 0.5, success at offset 1.0
    assert len(sleep_calls) == 2  # sleeps before each of the two attempts


def test_reprobe_desired_down_exits_on_absent(monkeypatch):
    """desired='down' wins as soon as we observe absent (no listener)."""
    from auntiepypi._actions import _reprobe

    attempts = []

    def fake_attempt(d):
        attempts.append(d)
        return _reprobe.ReprobeResult(status="absent")

    monkeypatch.setattr(_reprobe, "_attempt", fake_attempt)
    elapsed = [0.0]

    def fake_now():
        return elapsed[0]

    def fake_sleep(s):
        elapsed[0] += s

    result = probe(
        _detection(1),
        budget_seconds=5.0,
        desired="down",
        _sleep=fake_sleep,
        _now=fake_now,
    )
    assert result.status == "absent"
    assert len(attempts) == 1  # first attempt observed absent → exit


def test_reprobe_desired_down_keeps_polling_while_up(monkeypatch):
    """desired='down' continues across attempts while status remains 'up'."""
    from auntiepypi._actions import _reprobe

    attempts = []

    def fake_attempt(d):
        attempts.append(d)
        # Stay 'up' for first 3 attempts, then 'down'
        return _reprobe.ReprobeResult(status="up" if len(attempts) <= 3 else "down")

    monkeypatch.setattr(_reprobe, "_attempt", fake_attempt)
    elapsed = [0.0]

    def fake_now():
        return elapsed[0]

    def fake_sleep(s):
        elapsed[0] += s

    result = probe(
        _detection(1),
        budget_seconds=5.0,
        desired="down",
        _sleep=fake_sleep,
        _now=fake_now,
    )
    assert result.status == "down"
    assert len(attempts) == 4


def test_reprobe_desired_down_exhausts_when_still_up(monkeypatch):
    """desired='down' but server stays up for the full budget → returns final 'up'."""
    from auntiepypi._actions import _reprobe

    monkeypatch.setattr(
        _reprobe,
        "_attempt",
        lambda d: _reprobe.ReprobeResult(status="up"),
    )
    elapsed = [0.0]

    def fake_now():
        return elapsed[0]

    def fake_sleep(s):
        elapsed[0] += s

    result = probe(
        _detection(1),
        budget_seconds=5.0,
        desired="down",
        _sleep=fake_sleep,
        _now=fake_now,
    )
    assert result.status == "up"  # ran the whole budget, never matched desired
