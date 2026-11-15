from __future__ import annotations

import io
import json
import os
from typing import TYPE_CHECKING

import auto_deploy
import pytest
import setup
import status_page
import upgrade

if TYPE_CHECKING:
    from pathlib import Path


def example_root(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text(
        "CONFIG_ROOT=/old\nCOMPOSE_PROFILES=old\nGRAFANA_BIND=0.0.0.0:3000\nPROMETHEUS_BIND=0.0.0.0:9090\nLOKI_BIND=0.0.0.0:3101\n"
    )
    for name in ("targets", "secrets"):
        (tmp_path / f"{name}.example").mkdir()
        (tmp_path / f"{name}.example/a").write_text("example")
    (tmp_path / "secrets.example/grafana_admin_password").write_text("insecure")
    return tmp_path


def test_setup_preserves_existing_configuration(tmp_path: Path) -> None:
    root = example_root(tmp_path)
    setup.prepare(root, "/srv/argus", "loki")
    assert "CONFIG_ROOT=/srv/argus" in (root / ".env").read_text()
    assert "GRAFANA_BIND=127.0.0.1:3000" in (root / ".env").read_text()
    password = (root / "secrets/grafana_admin_password").read_text()
    assert len(password.strip()) >= 32
    assert password != (root / "secrets.example/grafana_admin_password").read_text()
    assert (root / "targets/a").read_text() == "[]\n"
    assert (root / "secrets").stat().st_mode & 0o777 == 0o700
    assert (root / ".env").stat().st_mode & 0o777 == 0o600
    (root / "targets/a").write_text("operator target")
    setup.prepare(root, "/different", "")
    assert (root / "targets/a").read_text() == "operator target"
    assert (root / "secrets/grafana_admin_password").read_text() == password
    assert "CONFIG_ROOT=/srv/argus" in (root / ".env").read_text()


@pytest.mark.parametrize(("directory", "profiles"), [("relative", ""), ("/srv/${SECRET}", ""), ("/srv/config", "wat")])
def test_setup_invalid_input_changes_nothing(tmp_path: Path, directory: str, profiles: str) -> None:
    with pytest.raises(ValueError, match=r"CONFIG_ROOT|unknown Compose profile"):
        setup.prepare(example_root(tmp_path), directory, profiles)
    assert not (tmp_path / ".env").exists()


def test_setup_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "ROOT", example_root(tmp_path))
    assert setup.main(["--defaults"]) == 0
    assert setup.main(["--defaults", "--config-root", "bad"]) == 1
    answers = iter(["/srv/custom", "snmp"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert setup.main([]) == 0


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[tuple[str, ...]]]:
    (tmp_path / ".env").write_text("# keep me\nARGUS_VERSION=0.9.0\nOTHER=value\n")
    (tmp_path / "secrets").mkdir()
    monkeypatch.setattr(upgrade, "ROOT", tmp_path)
    monkeypatch.setattr(upgrade, "select_release", lambda _v: "1.0.0")
    monkeypatch.setattr(auto_deploy, "healthy", lambda: True)
    for key in ("ARGUS_VERSION", "ARGUS_AGENT_IMAGE", "ARGUS_INTEL_GPU_EXPORTER_IMAGE"):
        monkeypatch.delenv(key, raising=False)
    calls = []

    def run(*cmd: str) -> str:
        calls.append(cmd)
        version = "1.0.0" if "--env-file" in cmd else "0.9.0"
        return json.dumps({"services": {"grafana": {"image": f"ghcr.io/honeybeartech/argus-grafana:{version}"}}})

    monkeypatch.setattr(auto_deploy, "run", run)
    return tmp_path, calls


def test_upgrade_success(installation: tuple[Path, list[tuple[str, ...]]]) -> None:
    root, calls = installation
    original = (root / ".env").read_text()
    assert upgrade.main(["latest"]) == 0
    assert (root / ".env").read_text() == original.replace("0.9.0", "1.0.0")
    assert (root / "secrets/argus-upgrade.env.backup").read_text() == original
    assert ("docker", "compose", "pull") in calls
    assert ("docker", "compose", "up", "-d", "--wait", "--wait-timeout", "300") in calls


def test_upgrade_rolls_back(installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch) -> None:
    root, calls = installation
    original = (root / ".env").read_text()
    health = iter([False, True])
    monkeypatch.setattr(auto_deploy, "healthy", lambda: next(health))
    assert upgrade.main(["latest"]) == 1
    assert (root / ".env").read_text() == original
    assert sum(cmd[2] == "up" for cmd in calls) == 2


def test_upgrade_pull_failure_restores_env(
    installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _calls = installation
    original = (root / ".env").read_text()
    run = auto_deploy.run

    def fail(*cmd: str) -> str:
        if cmd[2] == "pull":
            msg = "offline"
            raise auto_deploy.DeployError(msg)
        return run(*cmd)

    monkeypatch.setattr(auto_deploy, "run", fail)
    assert upgrade.main(["latest"]) == 1
    assert (root / ".env").read_text() == original


def test_upgrade_dry_run(installation: tuple[Path, list[tuple[str, ...]]]) -> None:
    root, calls = installation
    assert upgrade.main(["latest", "--dry-run"]) == 0
    assert "0.9.0" in (root / ".env").read_text()
    assert len(calls) == 2


def test_upgrade_rejects_source_mode(
    installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _calls = installation
    monkeypatch.setattr(auto_deploy, "run", lambda *_cmd: json.dumps({"services": {"grafana": {"build": "."}}}))
    assert upgrade.main(["latest"]) == 1
    assert "0.9.0" in (root / ".env").read_text()


def test_upgrade_rejects_shell_override(
    installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (installation[0] / ".env").exists()
    monkeypatch.setenv("ARGUS_VERSION", "99.0.0")
    assert upgrade.main(["latest"]) == 1


def test_upgrade_rejects_env_override(installation: tuple[Path, list[tuple[str, ...]]]) -> None:
    root, _calls = installation
    with (root / ".env").open("a") as env:
        env.write("ARGUS_AGENT_IMAGE=custom:9\n")
    assert upgrade.main(["latest"]) == 1


def test_upgrade_rejects_symlink(installation: tuple[Path, list[tuple[str, ...]]]) -> None:
    root, _calls = installation
    (root / ".env").rename(root / "actual")
    (root / ".env").symlink_to(root / "actual")
    assert upgrade.main(["latest"]) == 1


def test_version_env() -> None:
    assert upgrade.version_env("X=a\n", "1.2.3") == "X=a\nARGUS_VERSION=1.2.3\n"
    with pytest.raises(auto_deploy.DeployError):
        upgrade.version_env("", "v1.2")


@pytest.mark.parametrize("version", ["latest", "1.2.3", "v1.2.3"])
def test_select_release(version: str, monkeypatch: pytest.MonkeyPatch) -> None:
    urls = []

    def release(url: str) -> dict[str, object]:
        urls.append(url)
        return {"tag_name": "v1.2.3", "draft": False, "prerelease": False}

    monkeypatch.setattr(auto_deploy, "http_json", release)
    assert upgrade.select_release(version) == "1.2.3"
    assert urls[0].endswith("/latest" if version == "latest" else "/tags/v1.2.3")


@pytest.mark.parametrize(
    "release", [{"tag_name": "v1.0.0", "draft": True}, {"tag_name": "v1.0.0-rc1"}, {"tag_name": "v1.2.4"}]
)
def test_reject_bad_release(release: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_deploy, "http_json", lambda _url: release)
    with pytest.raises(auto_deploy.DeployError):
        upgrade.select_release("1.2.3")


def test_reject_invalid_release_version() -> None:
    with pytest.raises(auto_deploy.DeployError):
        upgrade.select_release("../evil")


def test_status_uses_dashboard_queries() -> None:
    queries = status_page.overview_queries(status_page.ROOT)
    assert len(queries) >= 15
    assert all("$group" not in expr and "$__range" not in expr for _name, expr in queries)
    assert any("probe_success" in expr for _name, expr in queries)


def test_status_escapes_untrusted_labels() -> None:
    document = status_page.render(
        [
            (
                "<script>title</script>",
                [{"metric": {"service": "<img src=x onerror=evil()>"}, "value": [1, "<script>evil()</script>"]}],
            ),
            ("Empty", []),
        ],
        "today",
    )
    assert "<script>" not in document
    assert "&lt;img" in document
    assert "No data" in document
    assert "Snapshot generated today" in document


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://user:secret@localhost", "http://localhost?x=1", "http:///bad"]
)
def test_status_rejects_bad_urls(url: str) -> None:
    with pytest.raises(ValueError, match="Prometheus URL"):
        status_page.query(url, "up")


def test_status_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    password = tmp_path / "password"
    password.write_text("secret\n")
    output = tmp_path / "status.html"
    seen = []

    def query(_url: str, expr: str, auth: str | None) -> list[dict[str, object]]:
        seen.append((expr, auth))
        return [{"metric": {}, "value": [1, "2"]}]

    monkeypatch.setattr(status_page, "query", query)
    assert status_page.main(["--output", str(output), "--password-file", str(password)]) == 0
    assert "<h1>Argus status</h1>" in output.read_text()
    assert "secret" not in output.read_text()
    assert seen[0][1] == "Basic YXJndXM6c2VjcmV0"

    def failing(*_args: object) -> list[dict[str, object]]:
        msg = "query failed"
        raise ValueError(msg)

    previous = output.read_text()
    monkeypatch.setattr(status_page, "query", failing)
    assert status_page.main(["--output", str(output)]) == 1
    assert output.read_text() == previous


@pytest.mark.parametrize("success", [True, False])
def test_status_query_http(monkeypatch: pytest.MonkeyPatch, *, success: bool) -> None:
    seen = []
    payload = {"status": "success" if success else "error", "data": {"resultType": "vector", "result": []}}

    def response(request: object, *, timeout: int) -> io.BytesIO:
        assert timeout == 15
        seen.append(request)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(status_page.urllib.request, "urlopen", response)
    if success:
        assert status_page.query("https://prometheus.example", "up", "Basic test") == []
        assert seen[0].get_header("Authorization") == "Basic test"
        assert seen[0].full_url == "https://prometheus.example/api/v1/query?query=up"
    else:
        with pytest.raises(ValueError, match="successful instant vector"):
            status_page.query("https://prometheus.example", "up")


def test_upgrade_unhealthy_rollback(
    installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _calls = installation
    monkeypatch.setattr(auto_deploy, "healthy", lambda: False)
    assert upgrade.main(["latest"]) == 1
    assert "0.9.0" in (root / ".env").read_text()


def test_upgrade_rejects_fixed_image_override(
    installation: tuple[Path, list[tuple[str, ...]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _calls = installation
    monkeypatch.setattr(auto_deploy, "run", lambda *_cmd: json.dumps({"services": {"grafana": {"image": "other:9"}}}))
    assert upgrade.main(["latest", "--dry-run"]) == 1
    assert "0.9.0" in (root / ".env").read_text()


def test_setup_password_readable_despite_restrictive_umask(tmp_path: Path) -> None:
    root = example_root(tmp_path)
    previous = os.umask(0o077)
    try:
        setup.prepare(root, "/srv/config", "loki")
    finally:
        os.umask(previous)
    assert (root / "secrets/grafana_admin_password").stat().st_mode & 0o777 == 0o644


def test_upgrade_backup_permissions(installation: tuple[Path, list[tuple[str, ...]]]) -> None:
    root, _calls = installation
    backup = root / "secrets/argus-upgrade.env.backup"
    backup.write_text("old backup")
    backup.chmod(0o644)
    assert upgrade.main(["latest"]) == 0
    assert backup.stat().st_mode & 0o777 == 0o600
