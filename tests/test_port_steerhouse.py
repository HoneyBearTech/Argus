"""Tests for scripts/port_steerhouse.py, which copies Steerhouse's dashboards into Argus."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import port_steerhouse
import pytest
from check_dashboards import formatted

if TYPE_CHECKING:
    from pathlib import Path

PROM = {"type": "prometheus", "uid": "${prometheus}"}
PG = {"type": "grafana-postgresql-datasource", "uid": "${postgres}"}


def steerhouse_dashboard(uid: str = "steerhouse-overview", **extra: object) -> dict[str, Any]:
    """A small dashboard in the shape Steerhouse ships them."""
    return {
        "uid": uid,
        "title": "Steerhouse: overview & runs",
        "description": "Steerhouse's own description.",
        "tags": ["steerhouse"],
        "editable": True,
        "templating": {
            "list": [
                {"type": "datasource", "name": "prometheus", "query": "prometheus"},
                {"type": "datasource", "name": "postgres", "query": "grafana-postgresql-datasource"},
                {"type": "query", "name": "project", "datasource": PG, "query": "SELECT 1"},
                {"type": "textbox", "name": "steerhouse_url", "query": "", "current": {"text": "", "value": ""}},
            ]
        },
        "annotations": {"list": [{"name": "Failed runs", "datasource": PG, "target": {"rawSql": "SELECT 1"}}]},
        "links": [{"type": "dashboards", "tags": ["steerhouse"], "title": "Steerhouse"}],
        "panels": [
            {"id": 1, "type": "row", "title": "Now", "panels": [{"id": 9, "datasource": PROM, "targets": []}]},
            {"id": 2, "type": "stat", "datasource": PROM, "targets": [{"refId": "A", "datasource": PROM}]},
            {"id": 3, "type": "stat", "datasource": PROM, "interval": "1m", "targets": []},
            {
                "id": 4,
                "type": "table",
                "datasource": PG,
                "interval": None,
                "targets": [{"refId": "A", "datasource": PG}],
            },
        ],
        **extra,
    }


def test_port_pins_the_datasources_and_drops_their_variables() -> None:
    dash = port_steerhouse.port(steerhouse_dashboard(), "v1.2.3")
    assert [v["name"] for v in dash["templating"]["list"]] == ["project", "steerhouse_url"]
    assert dash["templating"]["list"][0]["datasource"] == port_steerhouse.DATASOURCES["${postgres}"]
    assert dash["annotations"]["list"][0]["datasource"]["uid"] == "steerhouse-db"
    panels = {p["id"]: p for p in port_steerhouse.walk_panels(dash["panels"])}
    assert panels[2]["datasource"] == {"type": "prometheus", "uid": "prometheus"}
    assert panels[2]["targets"][0]["datasource"] == {"type": "prometheus", "uid": "prometheus"}
    assert panels[4]["targets"][0]["datasource"]["uid"] == "steerhouse-db"
    assert "${" not in json.dumps(dash)


def test_port_applies_argus_conventions() -> None:
    dash = port_steerhouse.port(steerhouse_dashboard(), "v1.2.3")
    assert list(dash)[:5] == ["id", "uid", "title", "description", "tags"]
    assert dash["id"] is None
    assert dash["uid"] == "argus-steerhouse-overview"
    assert dash["tags"] == ["argus", "steerhouse"]
    assert dash["description"].startswith(port_steerhouse.QUESTIONS["steerhouse-overview"])
    assert "Steerhouse v1.2.3" in dash["description"]
    assert [link["title"] for link in dash["links"]] == ["Argus dashboards", "Steerhouse"]
    assert dash["editable"] is True


def test_port_gives_prometheus_panels_the_scrape_interval_as_minimum() -> None:
    """The steerhouse job scrapes every 30 s, so $__rate_interval must span at least that."""
    dash = port_steerhouse.port(steerhouse_dashboard(), "v1")
    panels = {p["id"]: p for p in port_steerhouse.walk_panels(dash["panels"])}
    assert panels[2]["interval"] == "30s"
    assert panels[9]["interval"] == "30s"  # inside a collapsed row
    assert panels[3]["interval"] == "1m"  # Steerhouse's own minimum stays
    assert panels[4]["interval"] is None  # not a Prometheus panel
    assert "interval" not in panels[1]


def test_port_is_repeatable() -> None:
    """Porting an already ported dashboard changes nothing (no second Argus link or tag)."""
    once = port_steerhouse.port(steerhouse_dashboard(), "v1")
    twice = port_steerhouse.port({**once, "uid": "steerhouse-overview"}, "v1")
    assert twice == once


def test_port_rejects_an_unknown_dashboard() -> None:
    with pytest.raises(port_steerhouse.PortError, match="QUESTIONS"):
        port_steerhouse.port(steerhouse_dashboard(uid="steerhouse-new"), "v1")


def test_port_rejects_a_url_box_with_a_value() -> None:
    """A real Steerhouse address must never land in the public repo."""
    dash = steerhouse_dashboard()
    dash["templating"]["list"][3]["query"] = "https://steerhouse.example.com"
    with pytest.raises(port_steerhouse.PortError, match="steerhouse_url"):
        port_steerhouse.port(dash, "v1")


def test_port_rejects_a_datasource_variable_it_cannot_pin() -> None:
    dash = steerhouse_dashboard()
    dash["panels"][1]["targets"][0]["datasource"] = {"type": "prometheus", "uid": "${prometheus}", "extra": 1}
    with pytest.raises(port_steerhouse.PortError, match="prometheus"):
        port_steerhouse.port(dash, "v1")


def test_pin_datasources_pins_plain_string_references() -> None:
    assert port_steerhouse.pin_datasources({"datasource": "${postgres}"}) == {
        "datasource": {"type": "grafana-postgresql-datasource", "uid": "steerhouse-db"}
    }


def steerhouse_checkout(tmp_path: Path, *dashboards: dict[str, Any]) -> Path:
    folder = tmp_path / "steerhouse" / "grafana" / "dashboards"
    folder.mkdir(parents=True)
    for dash in dashboards:
        (folder / f"{dash['uid']}.json").write_text(json.dumps(dash))
    return tmp_path / "steerhouse"


def test_main_writes_the_dashboards_and_check_then_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    checkout = steerhouse_checkout(tmp_path, steerhouse_dashboard())
    out = tmp_path / "out"
    out.mkdir()
    args = ["--steerhouse", str(checkout), "--version", "v1", "--out", str(out)]
    assert port_steerhouse.main(["--check", *args]) == 1
    assert "differs" in capsys.readouterr().err
    assert port_steerhouse.main(args) == 0
    written = (out / "steerhouse-overview.json").read_text()
    assert written == formatted(port_steerhouse.port(steerhouse_dashboard(), "v1"))
    assert "1 of 1 dashboard(s) updated" in capsys.readouterr().out
    assert port_steerhouse.main(["--check", *args]) == 0
    assert port_steerhouse.main(args) == 0
    assert "0 of 1 dashboard(s) updated" in capsys.readouterr().out


def test_main_reports_a_checkout_without_dashboards(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert port_steerhouse.main(["--steerhouse", str(tmp_path), "--version", "v1"]) == 1
    assert "no dashboards" in capsys.readouterr().err


def test_main_reports_a_dashboard_it_cannot_port(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    checkout = steerhouse_checkout(tmp_path, steerhouse_dashboard(uid="steerhouse-new"))
    assert port_steerhouse.main(["--steerhouse", str(checkout), "--version", "v1", "--out", str(tmp_path)]) == 1
    assert "steerhouse-new" in capsys.readouterr().err


def test_version_comes_from_the_checkouts_tag(tmp_path: Path) -> None:
    checkout = steerhouse_checkout(tmp_path, steerhouse_dashboard())
    git = ["git", "-C", str(checkout), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "--no-gpg-sign", "-m", "x"], check=True)
    subprocess.run([*git, "tag", "--no-sign", "v9.9.9"], check=True)
    assert port_steerhouse.checkout_version(checkout) == "v9.9.9"


def test_version_without_git_asks_for_it(tmp_path: Path) -> None:
    with pytest.raises(port_steerhouse.PortError, match="--version"):
        port_steerhouse.checkout_version(tmp_path / "missing")
