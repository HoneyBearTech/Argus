"""Status snapshots remain readable when network or filesystem operations fail."""

from __future__ import annotations

import http.client
from pathlib import Path

import pytest
import status_page


def test_snapshot_replaces_previous_page_and_removes_staging(tmp_path: Path) -> None:
    output = tmp_path / "status.html"
    output.write_text("old snapshot")
    status_page.write_snapshot(output, "new snapshot")
    assert output.read_text() == "new snapshot"
    assert list(tmp_path.iterdir()) == [output]


def test_snapshot_preserves_previous_page_if_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "status.html"
    output.write_text("previous snapshot")

    def fail_replace(_self: Path, _target: Path) -> None:
        msg = "filesystem unavailable"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="filesystem unavailable"):
        status_page.write_snapshot(output, "new snapshot")
    assert output.read_text() == "previous snapshot"
    assert list(tmp_path.iterdir()) == [output]


def test_http_protocol_error_preserves_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "status.html"
    output.write_text("previous snapshot")

    def fail_query(_url: str, _expr: str, _auth: str | None) -> list[dict[str, object]]:
        msg = "invalid HTTP response"
        raise http.client.BadStatusLine(msg)

    monkeypatch.setattr(status_page, "query", fail_query)
    assert status_page.main(["--output", str(output)]) == 1
    assert output.read_text() == "previous snapshot"
