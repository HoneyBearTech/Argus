"""Check generated dashboard stability and output drift."""

from pathlib import Path

import generate_dashboards as generate


def test_generated_dashboard_is_current() -> None:
    assert generate.main(["--check"]) == 0
    panels = generate.dashboard()["panels"]
    assert len({panel["id"] for panel in panels}) == len(panels)
    assert all(panel["datasource"]["uid"] == "prometheus" for panel in panels)


def test_generate_and_check_drift(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "models.json"
    assert generate.main(["--check", "--output", str(output)]) == 1
    assert generate.main(["--output", str(output)]) == 0
    assert generate.main(["--check", "--output", str(output)]) == 0
    output.write_text("{}")
    assert generate.main(["--check", "--output", str(output)]) == 1
