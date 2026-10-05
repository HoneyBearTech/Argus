#!/usr/bin/env python3
"""Build promtool unit tests for the PromQL in Argus' alert rules and dashboards.

Each file in tests/promql/ is a promtool test file (https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
whose promql_expr_test entries name the query to test instead of repeating it, so a test always
runs the query that ships:

    - rule: argus-service-down    # an alert rule's query (refId A) with its threshold applied:
                                  # the result is exactly the series that would alert
      measurement: true           # optional: the raw query, without the threshold
    - dashboard: argus-hosts      # a dashboard panel's query
      panel: 9                    # the panel's id, or its title if that is unique
      ref_id: A                   # optional: which of the panel's queries (default: the first)
      vars: {host: ".*"}          # values for the dashboard and Grafana variables in the query

This writes the resolved files to an output directory; run them with
`promtool test rules <dir>/*.yml`.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "provisioning" / "alerting" / "rules.yaml"
DASHBOARDS = ROOT / "dashboards"
SPECS = ROOT / "tests" / "promql"

# Grafana threshold evaluators and the PromQL comparison each one means.
THRESHOLD_OPS = {"gt": ">", "lt": "<"}
# $name, ${name}, ${name:format} and [[name]]. Names start with a letter or underscore, so
# label_replace's "$1" is left alone.
VAR_RE = re.compile(r"\$\{([A-Za-z_]\w*)(?::\w+)?\}|\$([A-Za-z_]\w*)|\[\[([A-Za-z_]\w*)\]\]")
QUERY_KEYS = ("rule", "measurement", "dashboard", "panel", "ref_id", "vars")


class SpecError(Exception):
    """A test names a query that doesn't exist or can't be tested."""


def load_rules(path: Path = RULES) -> dict[str, dict[str, Any]]:
    """Return the provisioned alert rules by uid."""
    groups = yaml.safe_load(path.read_text())["groups"]
    return {rule["uid"]: rule for group in groups for rule in group["rules"]}


def load_dashboards(root: Path = DASHBOARDS) -> dict[str, dict[str, Any]]:
    """Return the dashboards by uid."""
    dashboards = (json.loads(path.read_text()) for path in sorted(root.rglob("*.json")))
    return {dash["uid"]: dash for dash in dashboards}


def rule_query(rules: dict[str, dict[str, Any]], uid: str, *, measurement: bool = False) -> str:
    """Return an alert rule's PromQL, with its threshold applied unless `measurement` is set."""
    rule = rules.get(uid)
    if rule is None:
        msg = f"no alert rule with uid {uid!r}"
        raise SpecError(msg)
    data = {item["refId"]: item for item in rule["data"]}
    query = data["A"]
    if query["datasourceUid"] != "prometheus":
        msg = f"alert rule {uid!r} queries {query['datasourceUid']!r}, not Prometheus"
        raise SpecError(msg)
    expr = query["model"]["expr"]
    if measurement:
        return expr
    condition = data[rule["condition"]]["model"]
    if condition.get("type") != "threshold" or condition.get("expression") != "A":
        msg = f"alert rule {uid!r}: only a threshold on A can be applied; test it with measurement: true"
        raise SpecError(msg)
    evaluator = condition["conditions"][0]["evaluator"]
    op = THRESHOLD_OPS.get(evaluator["type"])
    if op is None:
        msg = f"alert rule {uid!r}: unsupported threshold type {evaluator['type']!r}"
        raise SpecError(msg)
    return f"({expr}) {op} {evaluator['params'][0]}"


def walk_panels(panels: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield every panel, including those inside rows."""
    for panel in panels:
        yield panel
        yield from walk_panels(panel.get("panels", []))


def substitute(expr: str, variables: dict[str, Any]) -> str:
    """Replace Grafana variables in a query with the test's values."""

    def value(match: re.Match[str]) -> str:
        name = next(group for group in match.groups() if group)
        if name not in variables:
            msg = f"the query uses ${name}; give it a value under vars"
            raise SpecError(msg)
        return str(variables[name])

    return VAR_RE.sub(value, expr)


def panel_query(
    dashboards: dict[str, dict[str, Any]],
    uid: str,
    panel: int | str,
    ref_id: str | None = None,
    variables: dict[str, Any] | None = None,
) -> str:
    """Return a dashboard panel's PromQL with its variables filled in."""
    dash = dashboards.get(uid)
    if dash is None:
        msg = f"no dashboard with uid {uid!r}"
        raise SpecError(msg)
    found = [p for p in walk_panels(dash.get("panels", [])) if panel in (p.get("id"), p.get("title"))]
    if len(found) != 1:
        msg = f"dashboard {uid!r} has {len(found)} panels matching {panel!r}; use the panel id"
        raise SpecError(msg)
    targets = [t for t in found[0].get("targets", []) if "expr" in t and ref_id in (None, t.get("refId"))]
    if not targets:
        msg = f"dashboard {uid!r} panel {panel!r} has no query {ref_id or ''}".rstrip()
        raise SpecError(msg)
    return substitute(targets[0]["expr"], variables or {})


def resolve_entry(entry: dict[str, Any], rules: dict[str, Any], dashboards: dict[str, Any]) -> dict[str, Any]:
    """Return a promql_expr_test entry with its named query replaced by the query itself."""
    if "expr" in entry:
        msg = "write the query in the alert rule or dashboard, and name it here with rule: or dashboard:"
        raise SpecError(msg)
    resolved = {key: value for key, value in entry.items() if key not in QUERY_KEYS}
    if ("rule" in entry) == ("dashboard" in entry):
        msg = "each promql_expr_test needs exactly one of rule: or dashboard:"
        raise SpecError(msg)
    if "rule" in entry:
        expr = rule_query(rules, entry["rule"], measurement=entry.get("measurement", False))
    else:
        if "panel" not in entry:
            msg = f"dashboard {entry['dashboard']!r}: say which panel"
            raise SpecError(msg)
        expr = panel_query(dashboards, entry["dashboard"], entry["panel"], entry.get("ref_id"), entry.get("vars"))
    return {"expr": expr, **resolved}


def resolve(spec: dict[str, Any], rules: dict[str, Any], dashboards: dict[str, Any]) -> dict[str, Any]:
    """Return a promtool test file with every named query resolved."""
    resolved = copy.deepcopy(spec)
    resolved.setdefault("rule_files", [])
    for group in resolved.get("tests", []):
        group["promql_expr_test"] = [
            resolve_entry(entry, rules, dashboards) for entry in group.get("promql_expr_test", [])
        ]
    return resolved


def build(specs: list[Path], out: Path, rules: dict[str, Any], dashboards: dict[str, Any]) -> list[str]:
    """Write the resolved test files to `out` and return any errors."""
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    for path in specs:
        try:
            resolved = resolve(yaml.safe_load(path.read_text()), rules, dashboards)
        except SpecError as e:
            errors.append(f"{path.name}: {e}")
            continue
        (out / path.name).write_text(yaml.safe_dump(resolved, sort_keys=False, width=1000))
    return errors


def main(argv: list[str] | None = None) -> int:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the promtool test files")
    parser.add_argument("specs", type=Path, nargs="*", help=f"test files (default: {SPECS.relative_to(ROOT)}/*.yml)")
    args = parser.parse_args(argv)
    specs = args.specs or sorted(SPECS.glob("*.yml"))
    errors = build(specs, args.out, load_rules(), load_dashboards())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: {len(specs)} test file(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
