"""Tests for scripts/promql_tests.py, which turns tests/promql/ into promtool test files."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import promql_tests
import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def alert_rule(uid: str, expr: str, *, evaluator: str = "lt", threshold: float = 1, **query: object) -> dict[str, Any]:
    return {
        "uid": uid,
        "condition": "C",
        "data": [
            {"refId": "A", "datasourceUid": "prometheus", "model": {"refId": "A", "expr": expr}, **query},
            {
                "refId": "C",
                "datasourceUid": "__expr__",
                "model": {
                    "type": "threshold",
                    "expression": "A",
                    "conditions": [{"evaluator": {"type": evaluator, "params": [threshold]}}],
                },
            },
        ],
    }


RULES = {
    "up": alert_rule("up", "up"),
    "hot": alert_rule("hot", "temp", evaluator="gt", threshold=55),
    "range": alert_rule("range", "temp", evaluator="within_range"),
    "logs": {
        "uid": "logs",
        "condition": "C",
        "data": [{"refId": "A", "datasourceUid": "loki", "model": {"expr": "{job='x'}"}}],
    },
    "math": {
        "uid": "math",
        "condition": "B",
        "data": [
            {"refId": "A", "datasourceUid": "prometheus", "model": {"expr": "up"}},
            {"refId": "B", "datasourceUid": "__expr__", "model": {"type": "math", "expression": "$A * 2"}},
        ],
    },
}

DASHBOARDS = {
    "hosts": {
        "uid": "hosts",
        "panels": [
            {"id": 1, "title": "Load", "targets": [{"refId": "A", "expr": 'load{host=~"$host"}'}]},
            {
                "id": 2,
                "type": "row",
                "title": "Disks",
                "panels": [
                    {
                        "id": 3,
                        "title": "Disk",
                        "targets": [
                            {"refId": "A", "expr": "rate(io[$__rate_interval])"},
                            {"refId": "B", "expr": 'label_replace(disk, "d", "Disk $1", "id", "(.*)")'},
                        ],
                    }
                ],
            },
            {"id": 4, "title": "Twin", "targets": []},
            {"id": 5, "title": "Twin", "targets": []},
            {"id": 6, "title": "Text"},
        ],
    }
}


def test_rule_query_applies_the_threshold() -> None:
    assert promql_tests.rule_query(RULES, "up") == "(up) < 1"
    assert promql_tests.rule_query(RULES, "hot") == "(temp) > 55"


def test_rule_query_measurement_is_the_raw_query() -> None:
    assert promql_tests.rule_query(RULES, "math", measurement=True) == "up"


@pytest.mark.parametrize(
    ("uid", "problem"),
    [
        ("missing", "no alert rule with uid 'missing'"),
        ("logs", "queries 'loki', not Prometheus"),
        ("math", "only a threshold on A can be applied"),
        ("range", "unsupported threshold type 'within_range'"),
    ],
)
def test_rule_query_errors(uid: str, problem: str) -> None:
    with pytest.raises(promql_tests.SpecError, match=problem):
        promql_tests.rule_query(RULES, uid)


def test_panel_query_by_id_or_title_including_rows() -> None:
    assert promql_tests.panel_query(DASHBOARDS, "hosts", 1, variables={"host": "a|b"}) == 'load{host=~"a|b"}'
    assert promql_tests.panel_query(DASHBOARDS, "hosts", "Disk", variables={"__rate_interval": "2m"}) == (
        "rate(io[2m])"
    )


def test_panel_query_by_ref_id_leaves_regex_groups_alone() -> None:
    assert promql_tests.panel_query(DASHBOARDS, "hosts", 3, "B") == 'label_replace(disk, "d", "Disk $1", "id", "(.*)")'


@pytest.mark.parametrize(
    ("args", "problem"),
    [
        (("nope", 1), "no dashboard with uid 'nope'"),
        (("hosts", "Twin"), "has 2 panels matching 'Twin'"),
        (("hosts", 99), "has 0 panels matching 99"),
        (("hosts", 6), "panel 6 has no query$"),
        (("hosts", 3, "Z"), "panel 3 has no query Z"),
        (("hosts", 1), r"uses \$host; give it a value under vars"),
    ],
)
def test_panel_query_errors(args: tuple[Any, ...], problem: str) -> None:
    with pytest.raises(promql_tests.SpecError, match=problem):
        promql_tests.panel_query(DASHBOARDS, *args)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("$a + ${a} + ${a:regex} + [[a]]", "1 + 1 + 1 + 1"),
        ('x{y=~"foo$"}', 'x{y=~"foo$"}'),
    ],
)
def test_substitute(expr: str, expected: str) -> None:
    assert promql_tests.substitute(expr, {"a": 1}) == expected


def test_resolve_replaces_named_queries_and_keeps_the_rest() -> None:
    spec = {
        "tests": [
            {
                "interval": "1m",
                "promql_expr_test": [
                    {"rule": "up", "eval_time": "5m", "exp_samples": []},
                    {"rule": "up", "measurement": True, "eval_time": "5m"},
                    {"dashboard": "hosts", "panel": "Load", "vars": {"host": ".*"}, "eval_time": "1m"},
                ],
            },
            {"interval": "1m"},
        ]
    }
    resolved = promql_tests.resolve(spec, RULES, DASHBOARDS)
    assert resolved["rule_files"] == []
    assert resolved["tests"][0]["promql_expr_test"] == [
        {"expr": "(up) < 1", "eval_time": "5m", "exp_samples": []},
        {"expr": "up", "eval_time": "5m"},
        {"expr": 'load{host=~".*"}', "eval_time": "1m"},
    ]
    assert resolved["tests"][1]["promql_expr_test"] == []
    assert "rule" in spec["tests"][0]["promql_expr_test"][0]  # the spec itself is untouched


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({"expr": "up"}, "write the query in the alert rule or dashboard"),
        ({}, "exactly one of rule: or dashboard:"),
        ({"rule": "up", "dashboard": "hosts"}, "exactly one of rule: or dashboard:"),
        ({"dashboard": "hosts"}, "say which panel"),
    ],
)
def test_resolve_entry_errors(entry: dict[str, Any], problem: str) -> None:
    with pytest.raises(promql_tests.SpecError, match=problem):
        promql_tests.resolve_entry(entry, RULES, DASHBOARDS)


@pytest.fixture
def spec_file(tmp_path: Path) -> Callable[[str, Any], Path]:
    def write(name: str, spec: Any) -> Path:  # noqa: ANN401 - any YAML document
        path = tmp_path / "specs" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(yaml.safe_dump(spec))
        return path

    return write


def test_build_writes_resolved_files_and_collects_errors(tmp_path: Path, spec_file: Callable[..., Path]) -> None:
    good = spec_file("good.yml", {"tests": [{"promql_expr_test": [{"rule": "hot", "eval_time": "1m"}]}]})
    bad = spec_file("bad.yml", {"tests": [{"promql_expr_test": [{"rule": "missing"}]}]})
    out = tmp_path / "out"
    errors = promql_tests.build([good, bad], out, RULES, DASHBOARDS)
    assert errors == ["bad.yml: no alert rule with uid 'missing'"]
    assert yaml.safe_load((out / "good.yml").read_text()) == {
        "tests": [{"promql_expr_test": [{"expr": "(temp) > 55", "eval_time": "1m"}]}],
        "rule_files": [],
    }
    assert not (out / "bad.yml").exists()


def test_load_rules_and_dashboards(tmp_path: Path) -> None:
    rules = tmp_path / "rules.yaml"
    rules.write_text(yaml.safe_dump({"groups": [{"rules": [RULES["up"]]}, {"rules": [RULES["hot"]]}]}))
    assert list(promql_tests.load_rules(rules)) == ["up", "hot"]
    (tmp_path / "dash" / "hosts").mkdir(parents=True)
    (tmp_path / "dash" / "hosts" / "h.json").write_text(json.dumps(DASHBOARDS["hosts"]))
    assert list(promql_tests.load_dashboards(tmp_path / "dash")) == ["hosts"]


def test_main(tmp_path: Path, spec_file: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    good = spec_file("good.yml", {"tests": [{"promql_expr_test": [{"rule": "argus-host-down"}]}]})
    bad = spec_file("bad.yml", {"tests": [{"promql_expr_test": [{"rule": "missing"}]}]})
    out = tmp_path / "out"
    assert promql_tests.main(["--out", str(out), str(good)]) == 0
    assert capsys.readouterr().out == f"OK: 1 test file(s) written to {out}\n"
    assert promql_tests.main(["--out", str(out), str(bad)]) == 1
    assert capsys.readouterr().err == "bad.yml: no alert rule with uid 'missing'\n"


def test_every_shipped_spec_resolves(tmp_path: Path) -> None:
    """The real tests/promql/ files name queries that exist (promtool runs them in CI)."""
    assert promql_tests.main(["--out", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(p.name for p in promql_tests.SPECS.glob("*.yml"))
