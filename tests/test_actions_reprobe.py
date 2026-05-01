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


# --------- v0.7.0: local-source detections respect TLS + auth ---------


def test_reprobe_local_uses_https_when_tls_configured(monkeypatch, tmp_path):
    """When source='local' and tls is configured, _attempt must probe https,
    not http. Otherwise an HTTPS-only first-party server reprobes as down."""
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.auntiepypi.local]\ncert = "{cert}"\nkey = "{key}"\n'
    )
    monkeypatch.chdir(tmp_path)

    captured = {}

    def fake_probe(host, port, **kw):
        captured["scheme"] = kw.get("scheme")
        captured["ssl_context"] = kw.get("ssl_context")
        from auntiepypi._detect._http import ProbeOutcome

        return ProbeOutcome(
            url=f"https://{host}:{port}/",
            tcp_open=True,
            http_status=200,
            body=b"<html>",
            error=None,
        )

    from auntiepypi._actions import _reprobe

    monkeypatch.setattr(_reprobe, "probe_endpoint", fake_probe)
    detection = Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="https://127.0.0.1:3141/",
        status="absent",
        source="local",
    )
    result = _reprobe._attempt(detection)
    assert result.status == "up"
    assert captured["scheme"] == "https"
    assert captured["ssl_context"] is not None


def test_reprobe_local_treats_401_as_up_when_auth_configured(monkeypatch, tmp_path):
    """A 401 from the first-party server with auth on means the auth gate
    is working — must reprobe as up, otherwise `auntie up` falsely fails."""
    htp = tmp_path / "htp"
    (tmp_path / "pyproject.toml").write_text(f'[tool.auntiepypi.local]\nhtpasswd = "{htp}"\n')
    monkeypatch.chdir(tmp_path)

    def fake_probe(host, port, **kw):
        from auntiepypi._detect._http import ProbeOutcome

        return ProbeOutcome(
            url=f"http://{host}:{port}/",
            tcp_open=True,
            http_status=401,
            body=b"401\n",
            error=None,
        )

    from auntiepypi._actions import _reprobe

    monkeypatch.setattr(_reprobe, "probe_endpoint", fake_probe)
    detection = Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="absent",
        source="local",
    )
    result = _reprobe._attempt(detection)
    assert result.status == "up"


def test_reprobe_local_401_without_auth_is_down(monkeypatch, tmp_path):
    """Without auth configured, a 401 is anomalous and reports as down."""
    monkeypatch.chdir(tmp_path)

    def fake_probe(host, port, **kw):
        from auntiepypi._detect._http import ProbeOutcome

        return ProbeOutcome(
            url=f"http://{host}:{port}/",
            tcp_open=True,
            http_status=401,
            body=b"401\n",
            error=None,
        )

    from auntiepypi._actions import _reprobe

    monkeypatch.setattr(_reprobe, "probe_endpoint", fake_probe)
    detection = Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="absent",
        source="local",
    )
    result = _reprobe._attempt(detection)
    assert result.status == "down"


def test_reprobe_declared_source_unchanged(monkeypatch, tmp_path):
    """source='declared' must keep using plain HTTP regardless of pyproject."""
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.auntiepypi.local]\ncert = "{cert}"\nkey = "{key}"\n'
    )
    monkeypatch.chdir(tmp_path)

    captured = {}

    def fake_probe(host, port, **kw):
        captured["scheme"] = kw.get("scheme")
        captured["ssl_context"] = kw.get("ssl_context")
        from auntiepypi._detect._http import ProbeOutcome

        return ProbeOutcome(
            url=f"http://{host}:{port}/",
            tcp_open=True,
            http_status=200,
            body=b"<html>",
            error=None,
        )

    from auntiepypi._actions import _reprobe

    monkeypatch.setattr(_reprobe, "probe_endpoint", fake_probe)
    detection = Detection(
        name="my-pypi",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="absent",
        source="declared",
    )
    _reprobe._attempt(detection)
    # declared servers don't read the local config; plain HTTP.
    assert captured["scheme"] == "http"
    assert captured["ssl_context"] is None


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
    """desired='down' continues across attempts while status remains 'up'.

    desired='down' matches only 'absent' (port unbound) — 'down' (TCP open
    but HTTP error) is treated as "still up" for stop's purposes.
    """
    from auntiepypi._actions import _reprobe

    attempts = []

    def fake_attempt(d):
        attempts.append(d)
        # Stay 'up' for first 3 attempts, then 'absent'
        return _reprobe.ReprobeResult(status="up" if len(attempts) <= 3 else "absent")

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
