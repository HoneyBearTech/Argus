#!/usr/bin/env python3
"""Port Steerhouse's Grafana dashboards into Argus.

Steerhouse (an Ansible web UI) ships three dashboards in its repository's grafana/dashboards/.
They pick their data sources through two variables, ${prometheus} and ${postgres}; Argus pins
data source uids instead. This copies them into dashboards/ci/ with Argus' conventions:

- the data source variables are dropped and every reference points at the pinned uids
  (`prometheus`, and `steerhouse-db` for Steerhouse's database);
- uid `argus-<Steerhouse's uid>`, "id": null, the `argus` tag (Steerhouse's own tag stays, for its
  dashboard links), the question each dashboard answers as its description, and the Steerhouse
  version it was ported from;
- Prometheus panels get a 30 s minimum interval, the steerhouse job's scrape interval, so
  $__rate_interval spans at least two scrapes;
- the Argus dashboards menu is added to the links.

Run it again when Steerhouse changes its dashboards, from a checkout of the release:

    python3 scripts/port_steerhouse.py --steerhouse ~/GitHub/Steerhouse

--check only reports whether the committed dashboards match what the checkout would produce.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_dashboards import formatted

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboards" / "ci"

# The data source variables Steerhouse's dashboards use, and the Argus datasource each becomes.
DATASOURCES = {
    "${prometheus}": {"type": "prometheus", "uid": "prometheus"},
    "${postgres}": {"type": "grafana-postgresql-datasource", "uid": "steerhouse-db"},
}
DATASOURCE_VARIABLES = {"prometheus", "postgres"}
# The steerhouse job's scrape interval (prometheus/prometheus.yml).
MIN_INTERVAL = "30s"
# The question each dashboard answers, by Steerhouse's uid (the Dashboard Catalog's wording).
QUESTIONS = {
    "steerhouse-overview": "Is Steerhouse healthy right now, and how have its Ansible runs gone: "
    "which failed, and how long did they take?",
    "steerhouse-execution": "Is Steerhouse keeping up: are runs waiting for a worker, are notifications "
    "going out, and is its API healthy?",
    "steerhouse-security": "Is anyone trying to get into Steerhouse, and who changed users, access or keys?",
}
ARGUS_LINK = {
    "title": "Argus dashboards",
    "type": "dashboards",
    "tags": ["argus"],
    "asDropdown": True,
    "includeVars": False,
    "keepTime": True,
    "targetBlank": False,
    "icon": "external link",
}


class PortError(Exception):
    """A Steerhouse dashboard doesn't look the way this port expects."""


def pin_datasources(node: Any) -> Any:  # noqa: ANN401 - any JSON value
    """Return a copy of a JSON value with every ${prometheus}/${postgres} reference pinned."""
    if isinstance(node, dict):
        ds = node.get("uid")
        if isinstance(ds, str) and ds in DATASOURCES and set(node) <= {"type", "uid"}:
            return dict(DATASOURCES[ds])
        return {
            key: dict(DATASOURCES[value])
            if key == "datasource" and isinstance(value, str) and value in DATASOURCES
            else pin_datasources(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [pin_datasources(item) for item in node]
    return node


def walk_panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every panel, including those inside collapsed rows."""
    found = []
    for panel in panels:
        found.append(panel)
        found.extend(walk_panels(panel.get("panels", [])))
    return found


def port(dashboard: dict[str, Any], version: str) -> dict[str, Any]:
    """Return a Steerhouse dashboard converted to Argus' conventions."""
    source_uid = dashboard.get("uid")
    if source_uid not in QUESTIONS:
        msg = f"unknown Steerhouse dashboard {source_uid!r}: add the question it answers to QUESTIONS"
        raise PortError(msg)
    dash = copy.deepcopy(dashboard)
    variables = dash.get("templating", {}).get("list", [])
    dash["templating"]["list"] = [v for v in variables if v.get("name") not in DATASOURCE_VARIABLES]
    for variable in dash["templating"]["list"]:
        if variable.get("type") == "textbox" and variable.get("query"):
            msg = f"{source_uid}: textbox {variable['name']!r} has a default value; Argus keeps it empty"
            raise PortError(msg)
    dash = pin_datasources(dash)
    leftover = [var for var in DATASOURCES if var in json.dumps(dash)]
    if leftover:
        msg = f"{source_uid}: still refers to {', '.join(leftover)} after pinning the data sources"
        raise PortError(msg)
    for panel in walk_panels(dash.get("panels", [])):
        if panel.get("datasource", {}).get("uid") == "prometheus" and not panel.get("interval"):
            panel["interval"] = MIN_INTERVAL
    links = [link for link in dash.get("links", []) if link.get("tags") != ["argus"]]
    tags = dash.get("tags", [])
    return {
        "id": None,
        "uid": f"argus-{source_uid}",
        "title": dash["title"],
        "description": f"{QUESTIONS[source_uid]} (Ported from Steerhouse {version} by scripts/port_steerhouse.py.)",
        "tags": ["argus", *(tag for tag in tags if tag != "argus")],
        **{key: value for key, value in dash.items() if key not in {"id", "uid", "title", "description", "tags"}},
        "links": [ARGUS_LINK, *links],
    }


def checkout_version(steerhouse: Path) -> str:
    """Return the Steerhouse checkout's version, as `git describe` names it."""
    git = shutil.which("git") or "git"
    result = subprocess.run(  # noqa: S603 - fixed arguments, a local path
        [git, "-C", str(steerhouse), "describe", "--tags", "--always"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"can't tell the Steerhouse version of {steerhouse} (give --version): {result.stderr.strip()}"
        raise PortError(msg)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steerhouse", type=Path, required=True, help="a checkout of Steerhouse")
    parser.add_argument("--version", help="the Steerhouse version (default: git describe of the checkout)")
    parser.add_argument("--out", type=Path, default=OUT, help="where the Argus dashboards go")
    parser.add_argument("--check", action="store_true", help="only check that the committed dashboards are current")
    args = parser.parse_args(argv)
    sources = sorted((args.steerhouse / "grafana" / "dashboards").glob("*.json"))
    if not sources:
        print(f"no dashboards in {args.steerhouse / 'grafana' / 'dashboards'}", file=sys.stderr)
        return 1
    try:
        version = args.version or checkout_version(args.steerhouse)
        ported = {path.name: formatted(port(json.loads(path.read_text()), version)) for path in sources}
    except PortError as e:
        print(e, file=sys.stderr)
        return 1
    current = {path.name: path.read_text() for path in args.out.glob("*.json")}
    stale = [name for name, text in ported.items() if current.get(name) != text]
    if args.check:
        for name in stale:
            print(f"{args.out / name} differs from Steerhouse {version}'s", file=sys.stderr)
        return 1 if stale else 0
    for name in stale:
        (args.out / name).write_text(ported[name])
    print(f"Steerhouse {version}: {len(stale)} of {len(ported)} dashboard(s) updated in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
