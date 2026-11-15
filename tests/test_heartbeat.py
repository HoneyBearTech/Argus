"""Heartbeat only signals success after local readiness, without leaking secrets."""

from __future__ import annotations

import io
import urllib.error
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import heartbeat as hb
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    path = tmp_path / "heartbeat_url"
    path.write_text("https://heartbeat.example/secret-token\n")
    return path


def test_success_checks_local_services_before_ping(secret: Path, monkeypatch: MonkeyPatch) -> None:
    password = secret.parent / "prometheus_password"
    password.write_text("private-password\n")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(hb, "request_ok", lambda url, password="": calls.append((url, password)) or True)
    checks = ["http://127.0.0.1:3000/api/health", "http://127.0.0.1:9090/-/ready"]
    assert hb.heartbeat(secret, checks, password)
    assert calls == [(checks[0], ""), (checks[1], "private-password"), (secret.read_text().strip(), "")]


def test_failure_does_not_ping(secret: Path, monkeypatch: MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(hb, "request_ok", lambda url, _password="": calls.append(url) and False)
    assert not hb.heartbeat(secret, ["http://localhost/-/ready"], secret.parent / "missing")
    assert calls == ["http://localhost/-/ready"]


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://example.test/secret",
        "file:///secret",
        "https:///missing",
        "https://user:secret@example.test/",
        "https://example.test/#secret",
    ],
)
def test_rejects_insecure_heartbeat_url(secret: Path, url: str) -> None:
    secret.write_text(url)
    with pytest.raises(ValueError, match="heartbeat URL"):
        hb.heartbeat(secret, [], secret.parent / "missing")


@pytest.mark.parametrize("check", ["file:///etc/passwd", "http:///missing", "https://user:secret@example.test/"])
def test_rejects_invalid_checks(secret: Path, check: str) -> None:
    with pytest.raises(ValueError, match="readiness checks"):
        hb.heartbeat(secret, [check], secret.parent / "missing")


@pytest.mark.parametrize("status", [200, 201, 302, 503])
def test_request_status(monkeypatch: MonkeyPatch, status: int) -> None:
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.status = status
    monkeypatch.setattr(hb.urllib.request, "build_opener", lambda *_args: opener)
    assert hb.request_ok("https://example.test/", "password") is (status == 200)
    request = opener.open.call_args.args[0]
    assert request.get_header("Authorization") == "Basic YXJndXM6cGFzc3dvcmQ="
    assert opener.open.call_args.kwargs["timeout"] == hb.TIMEOUT


@pytest.mark.parametrize("error", [OSError("secret"), urllib.error.URLError("secret"), ValueError("secret")])
def test_network_error_is_safe(monkeypatch: MonkeyPatch, error: Exception) -> None:
    opener = MagicMock()
    opener.open.side_effect = error
    monkeypatch.setattr(hb.urllib.request, "build_opener", lambda *_args: opener)
    assert not hb.request_ok("https://example.test/secret")


def test_redirects_are_refused() -> None:
    assert hb.NoRedirect().redirect_request(MagicMock(), None, 302, "redirect", {}, "https://elsewhere.test/") is None


def test_main_handles_invalid_configuration(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    assert hb.main(["--url-file", str(tmp_path / "missing")]) == 1
    assert "could not be read or is invalid" in capsys.readouterr().err


@pytest.mark.parametrize("success", [True, False])
def test_main_result(secret: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str], *, success: bool) -> None:
    call = MagicMock(return_value=success)
    monkeypatch.setattr(hb, "heartbeat", call)
    assert hb.main(["--url-file", str(secret)]) == (0 if success else 1)
    assert call.call_args.args[1] == ["http://127.0.0.1:3000/api/health", "http://127.0.0.1:9090/-/ready"]
    captured = capsys.readouterr()
    assert "secret-token" not in captured.out + captured.err


def test_main_custom_check(secret: Path, monkeypatch: MonkeyPatch) -> None:
    call = MagicMock(return_value=True)
    monkeypatch.setattr(hb, "heartbeat", call)
    assert hb.main(["--url-file", str(secret), "--check", "http://localhost:3001/api/health"]) == 0
    assert call.call_args.args[1] == ["http://localhost:3001/api/health"]


def test_http_error_closes_response(monkeypatch: MonkeyPatch) -> None:
    stream = io.BytesIO(b"not ready")
    error = urllib.error.HTTPError("https://example.test/", 503, "unavailable", None, stream)
    opener = MagicMock()
    opener.open.side_effect = error
    monkeypatch.setattr(hb.urllib.request, "build_opener", lambda *_args: opener)
    assert not hb.request_ok("https://example.test/")
    assert stream.closed
