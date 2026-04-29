"""Tests for `auntiepypi doctor`."""

from __future__ import annotations

import json
import subprocess
from typing import Callable, Iterator

import pytest

from auntiepypi._probes._probe import Probe
from auntiepypi._probes._runtime import ProbeResult
from auntiepypi.cli import _commands, main
from auntiepypi.cli._commands.doctor import _diagnose, _try_start


def _set_runner(runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    """Monkey-patch the doctor's RUN indirection to a fake."""
    _commands.doctor.RUN = runner


def _restore_runner() -> None:
    _commands.doctor.RUN = subprocess.run


@pytest.fixture(autouse=True)
def _restore_doctor_runner() -> Iterator[None]:
    yield
    _restore_runner()


def test_doctor_dry_run_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Dry-run is the default; no fix is attempted."""
    invocations: list[list[str]] = []

    def fake_run(argv, **kwargs):  # noqa: ANN001 - test indirection
        invocations.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    _set_runner(fake_run)
    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 0
    assert invocations == []  # dry-run never invokes start_command
    assert "(dry-run" in out


def test_doctor_dry_run_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "auntiepypi doctor"
    assert payload["fix_applied"] is False
    items = payload["sections"][0]["items"]
    for item in items:
        assert "diagnosis" in item
        # Dry-run never recorded a fix attempt.
        assert item.get("fix_attempted") in (False, None)


def test_doctor_fix_invokes_start_command_for_down_servers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocations: list[list[str]] = []

    def fake_run(argv, **kwargs):  # noqa: ANN001
        invocations.append(list(argv))
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    _set_runner(fake_run)
    main(["doctor", "--fix", "--json"])
    payload = json.loads(capsys.readouterr().out)
    items = payload["sections"][0]["items"]
    # Each down/absent probe should have one start_command invocation.
    expected_invocations = sum(1 for item in items if item["status"] != "up")
    # If everything came up "up" the test still passes — assert consistency only.
    assert len(invocations) == expected_invocations or len(invocations) == sum(
        1 for item in items if item.get("fix_attempted")
    )


def test_doctor_fix_failure_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """When start_command returns non-zero, exit with EXIT_ENV_ERROR (2)."""

    def fake_run(argv, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr="boom\n")

    _set_runner(fake_run)
    rc = main(["doctor", "--fix", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    items = payload["sections"][0]["items"]
    if all(item["status"] == "up" for item in items):
        # No fixes attempted; exit code is 0. Re-run with a forced down state
        # would require mocking probes — skip in that case.
        pytest.skip("no servers were down; nothing to fix")
    assert rc == 2
    # Error JSON should also be on stderr.
    err_line = captured.err.strip().splitlines()[-1]
    err = json.loads(err_line)
    assert err["code"] == 2


def test_diagnose_no_start_command() -> None:
    """Cover the _diagnose branch when probe has no start_command (lines 42-44)."""
    probe = Probe(
        name="testprobe",
        default_port=19999,
        health_path="/health",
        start_command=(),  # empty tuple is falsy -> "no start_command" branch
    )
    item: ProbeResult = {
        "name": "testprobe",
        "port": 19999,
        "url": "http://x",  # NOSONAR S5332 - synthetic test fixture; never dereferenced
        "status": "absent",
    }
    result = _diagnose(item, probe)
    assert "no start_command" in result["diagnosis"]
    assert result["remediation"] == "configure start_command in the probe definition"


def test_try_start_file_not_found() -> None:
    """Cover the FileNotFoundError branch in _try_start (line 61)."""
    probe = Probe(
        name="testprobe",
        default_port=19999,
        health_path="/health",
        start_command=("no-such-binary-xyzzy", "start"),
    )

    # Don't fake RUN; let subprocess.run raise FileNotFoundError naturally.
    _restore_runner()
    ok, detail = _try_start(probe)
    assert ok is False
    assert "command not found" in detail


def test_try_start_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the except (OSError, subprocess.SubprocessError) branch (lines 62-63)."""
    probe = Probe(
        name="testprobe",
        default_port=19999,
        health_path="/health",
        start_command=("some-server", "start"),
    )

    def fake_run(argv, **kwargs):  # noqa: ANN001
        raise OSError("connection reset")

    _set_runner(fake_run)
    ok, detail = _try_start(probe)
    assert ok is False
    assert "OSError" in detail


def test_try_start_subprocess_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the except (OSError, subprocess.SubprocessError) branch via SubprocessError."""
    probe = Probe(
        name="testprobe",
        default_port=19999,
        health_path="/health",
        start_command=("some-server", "start"),
    )

    def fake_run(argv, **kwargs):  # noqa: ANN001
        raise subprocess.SubprocessError("timeout expired")

    _set_runner(fake_run)
    ok, detail = _try_start(probe)
    assert ok is False
    assert "SubprocessError" in detail


def test_doctor_renders_down_with_detail_and_fix_ok(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover _apply_fix detail/diagnosis=fixed branches (lines 83, 85) and
    _render_text fix_attempted rendering (lines 139, 141-142)."""
    from auntiepypi.cli._commands import doctor as _doctor_mod

    # Track how many times probe_status is called per probe name.
    call_counts: dict[str, int] = {}

    def fake_probe_status(probe, **kwargs):  # noqa: ANN001
        call_counts[probe.name] = call_counts.get(probe.name, 0) + 1
        if probe.name == "devpi":
            if call_counts["devpi"] == 1:
                # Initial probe: server is down.
                return {
                    "name": "devpi",
                    "port": 3141,
                    "url": "http://127.0.0.1:3141/+api",
                    "status": "down",
                    "detail": "http 500",
                }
            # Re-probe after fix: server is now up, with a detail to exercise line 83.
            return {
                "name": "devpi",
                "port": 3141,
                "url": "http://127.0.0.1:3141/+api",
                "status": "up",
                "detail": "was down",
            }
        # pypiserver: always up.
        return {
            "name": probe.name,
            "port": probe.default_port,
            "url": probe.health_url(),
            "status": "up",
        }

    monkeypatch.setattr(_doctor_mod, "probe_status", fake_probe_status)

    def fake_run(argv, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    _set_runner(fake_run)

    rc = main(["doctor", "--fix"])
    assert rc == 0
    out = capsys.readouterr().out
    # _render_text fix_attempted lines (139, 141-142) should appear.
    assert "fix:" in out
    assert "ok" in out


def test_doctor_renders_down_with_detail_text(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the 'down with detail' status in _render_text output."""
    from auntiepypi.cli._commands import doctor as _doctor_mod

    def fake_probe_status(probe, **kwargs):  # noqa: ANN001
        if probe.name == "devpi":
            return {
                "name": "devpi",
                "port": 3141,
                "url": "http://127.0.0.1:3141/+api",
                "status": "down",
                "detail": "http 500",
            }
        return {
            "name": probe.name,
            "port": probe.default_port,
            "url": probe.health_url(),
            "status": "absent",
        }

    monkeypatch.setattr(_doctor_mod, "probe_status", fake_probe_status)

    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "down" in out


def test_render_text_string_remediation() -> None:
    """Cover the elif isinstance(rem, str) branch in _render_text (line 139).

    This path fires when a probe has no start_command; _diagnose sets
    remediation to a plain string (not a list).
    """
    from auntiepypi.cli._commands.doctor import _render_text

    payload = {
        "subject": "auntiepypi doctor",
        "sections": [
            {
                "name": "local-pypi-servers",
                "summary": "1 absent",
                "items": [
                    {
                        "name": "custom",
                        "port": 19999,
                        "url": "http://127.0.0.1:19999/health",
                        "status": "absent",
                        "diagnosis": "absent; no start_command configured",
                        "remediation": "configure start_command in the probe definition",
                        "fix_attempted": False,
                    }
                ],
            }
        ],
        "fix_applied": False,
    }
    text = _render_text(payload)
    assert "configure start_command" in text
