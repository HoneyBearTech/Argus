"""Tests for scripts/check_dashboards.py, run against a throwaway repository."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import check_dashboards
import pytest

if TYPE_CHECKING:
    from pathlib import Path

DATASOURCES = """\
datasources:
  - name: Prometheus
    uid: prometheus
  - name: Loki
    uid: 'loki'  # quoted, with a comment
"""


def ip(*octets: int) -> str:
    """Build an address at run time: this file is checked for private addresses too."""
    return ".".join(map(str, octets))


def dashboard(**overrides: object) -> dict[str, Any]:
    dash = {
        "id": None,
        "uid": "argus-test",
        "title": "Test",
        "tags": ["argus"],
        "description": "Is the test passing?",
        "panels": [{"datasource": {"type": "prometheus", "uid": "prometheus"}, "targets": []}],
    }
    dash.update(overrides)
    return dash


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git repository laid out like Argus, which the checks are pointed at."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "provisioning" / "datasources").mkdir(parents=True)
    (tmp_path / "provisioning" / "datasources" / "argus.yaml").write_text(DATASOURCES)
    (tmp_path / "dashboards").mkdir()
    monkeypatch.setattr(check_dashboards, "ROOT", tmp_path)
    monkeypatch.setattr(check_dashboards, "DASHBOARDS", tmp_path / "dashboards")
    monkeypatch.setattr(check_dashboards, "DATASOURCES", tmp_path / "provisioning" / "datasources")
    monkeypatch.setattr(check_dashboards, "FORBIDDEN_FILE", tmp_path / ".forbidden-patterns")
    monkeypatch.delenv("ARGUS_FORBIDDEN_PATTERNS", raising=False)
    return tmp_path


def write(repo: Path, name: str, dash: dict[str, Any] | str) -> Path:
    path = repo / "dashboards" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dash if isinstance(dash, str) else check_dashboards.formatted(dash))
    return path


def dashboard_errors() -> list[str]:
    errors: list[str] = []
    check_dashboards.check_dashboards(errors)
    return errors


@pytest.mark.usefixtures("repo")
def test_provisioned_uids() -> None:
    assert check_dashboards.provisioned_uids() == {"prometheus", "loki"}


def test_datasource_uids_finds_every_reference() -> None:
    dash = {
        "datasource": "loki",
        "panels": [{"datasource": {"uid": "prometheus"}}, {"targets": [{"datasource": {"type": "x"}}]}],
    }
    assert sorted(check_dashboards.datasource_uids(dash)) == ["loki", "prometheus"]


def test_good_dashboard_passes(repo: Path) -> None:
    write(repo, "test/good.json", dashboard())
    errors: list[str] = []
    assert check_dashboards.check_dashboards(errors) == 1
    assert errors == []


def test_invalid_json(repo: Path) -> None:
    write(repo, "broken.json", "{")
    assert dashboard_errors() == [
        (
            "dashboards/broken.json: invalid JSON: Expecting property name enclosed in double quotes: "
            "line 1 column 2 (char 1)"
        )
    ]


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"uid": "Not-Lowercase"}, "uid 'Not-Lowercase' must be lowercase letters, digits and dashes"),
        ({"uid": "x" * 41}, "must be lowercase letters, digits and dashes, max 40 chars"),
        ({"uid": None}, "uid None must be"),
        ({"id": 7}, '"id" must be null'),
        ({"tags": ["other"]}, 'missing the "argus" tag'),
        ({"description": "  "}, "missing a description"),
        ({"panels": [{"datasource": {"uid": "influx"}}]}, "datasource uid 'influx' is not provisioned"),
    ],
)
def test_dashboard_problems(repo: Path, overrides: dict[str, Any], problem: str) -> None:
    write(repo, "bad.json", dashboard(**overrides))
    errors = dashboard_errors()
    assert len(errors) == 1
    assert problem in errors[0]


def test_builtin_datasources_are_allowed(repo: Path) -> None:
    panels = [{"datasource": {"uid": "-- Grafana --"}}, {"datasource": "__expr__"}]
    write(repo, "builtin.json", dashboard(panels=panels))
    assert dashboard_errors() == []


def test_duplicate_uid(repo: Path) -> None:
    write(repo, "a.json", dashboard())
    write(repo, "b.json", dashboard())
    assert dashboard_errors() == ["dashboards/b.json: uid 'argus-test' already used by dashboards/a.json"]


def test_unformatted_dashboard_is_reported_and_fixed(repo: Path) -> None:
    path = write(repo, "compact.json", json.dumps(dashboard()))
    assert dashboard_errors() == ["dashboards/compact.json: not formatted with a 2-space indent; run with --fix"]

    errors: list[str] = []
    check_dashboards.check_dashboards(errors, fix=True)
    assert errors == []
    assert path.read_text() == check_dashboards.formatted(dashboard())


def test_forbidden_patterns_from_env_and_file(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_FORBIDDEN_PATTERNS", "lab\\.example\n\n# a comment\n")
    (repo / ".forbidden-patterns").write_text("secret-host\n")
    patterns = check_dashboards.forbidden_patterns()
    assert [p.pattern for p in patterns] == ["lab\\.example", "secret-host"]
    assert patterns[0].search("GRAFANA.LAB.EXAMPLE")  # case-insensitive


@pytest.mark.parametrize("address", [ip(10, 1, 2, 3), ip(192, 168, 40, 1), ip(172, 16, 0, 1), ip(172, 31, 255, 255)])
def test_private_ips_are_rejected(repo: Path, address: str) -> None:
    (repo / "notes.txt").write_text(f"first line\nserver at {address}\n")
    errors: list[str] = []
    check_dashboards.check_no_network_details(errors)
    assert errors == [f"notes.txt:2: private IP address {address!r} — keep network details out of this public repo"]


@pytest.mark.parametrize("address", ["8.8.8.8", "172.32.0.1", "127.0.0.1", "v10.1.2"])
def test_public_and_loopback_addresses_pass(repo: Path, address: str) -> None:
    (repo / "notes.txt").write_text(address)
    errors: list[str] = []
    check_dashboards.check_no_network_details(errors)
    assert errors == []


def test_forbidden_pattern_and_ignored_files(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_FORBIDDEN_PATTERNS", "secret-host")
    (repo / ".gitignore").write_text("targets/\n")
    (repo / "targets").mkdir()
    (repo / "targets" / "real.json").write_text(f"secret-host {ip(10, 0, 0, 1)}")  # gitignored: never committed
    (repo / "image.bin").write_bytes(b"\xff\xfe secret-host")  # not text
    (repo / "README.md").write_text("see secret-host.local")
    errors: list[str] = []
    assert check_dashboards.check_no_network_details(errors) == 1
    assert errors == ["README.md:1: forbidden pattern 'secret-host' — keep network details out of this public repo"]


def test_deleted_tracked_file_is_skipped(repo: Path) -> None:
    (repo / "gone.txt").write_text(ip(10, 0, 0, 1))
    subprocess.run(["git", "add", "gone.txt"], cwd=repo, check=True)
    (repo / "gone.txt").unlink()
    errors: list[str] = []
    check_dashboards.check_no_network_details(errors)
    assert errors == []


def test_main_ok(repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_FORBIDDEN_PATTERNS", "secret-host")
    write(repo, "good.json", dashboard())
    assert check_dashboards.main([]) == 0
    out, err = capsys.readouterr()
    assert out == "OK: 1 dashboard(s) checked, no private IPs or forbidden patterns (1 loaded).\n"
    assert err == ""


@pytest.mark.usefixtures("repo")
def test_main_warns_without_patterns(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_dashboards.main([]) == 0
    assert "warning: no forbidden patterns loaded" in capsys.readouterr().err


def test_main_reports_problems(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(repo, "bad.json", dashboard(id=1, tags=[]))
    assert check_dashboards.main([]) == 1
    err = capsys.readouterr().err
    assert '"id" must be null' in err
    assert "2 problem(s) found." in err


def test_main_fix(repo: Path) -> None:
    path = write(repo, "compact.json", json.dumps(dashboard()))
    assert check_dashboards.main(["--fix"]) == 0
    assert path.read_text() == check_dashboards.formatted(dashboard())
