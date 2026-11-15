#!/usr/bin/env python3
"""Generate a read-only HTML snapshot from the shipped Overview dashboard queries."""

from __future__ import annotations

import argparse
import base64
import html
import http.client
import json
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def overview_queries(root: Path) -> list[tuple[str, str]]:
    """Read instant status queries from Overview, using all groups and a 24h range."""
    dashboard = json.loads((root / "dashboards/overview/homelab-overview.json").read_text())
    return [
        (
            panel["title"].replace("$group", "all groups"),
            target["expr"].replace("$group", ".*").replace("$__range", "24h"),
        )
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if target.get("expr")
    ]


def query(base_url: str, expression: str, authorization: str | None = None) -> list[dict[str, Any]]:
    """Fetch an instant vector with optional Prometheus authentication."""
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        msg = "Prometheus URL must be an HTTP(S) base URL without credentials, query or fragment"
        raise ValueError(msg)
    url = base_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    headers = {"Authorization": authorization} if authorization else {}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - HTTP(S) validated above
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - HTTP(S) validated above
        payload = json.load(response)
    if payload.get("status") != "success" or payload.get("data", {}).get("resultType") != "vector":
        msg = "Prometheus did not return a successful instant vector"
        raise ValueError(msg)
    return payload["data"]["result"]


def render(results: list[tuple[str, list[dict[str, Any]]]], generated: str) -> str:
    """Render escaped metrics as static HTML, with no credentials or browser requests."""
    sections = []
    for title, series in results:
        rows = []
        for sample in series:
            labels = ", ".join(f"{key}={value}" for key, value in sorted(sample["metric"].items()) if key != "__name__")
            rows.append(
                f"<tr><td>{html.escape(labels or 'Total')}</td><td>{html.escape(str(sample['value'][1]))}</td></tr>"
            )
        body = "".join(rows) or '<tr><td colspan="2">No data</td></tr>'
        sections.append(f"<section><h2>{html.escape(title)}</h2><table><tbody>{body}</tbody></table></section>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>Argus status</title><style>body{font:16px system-ui;max-width:70rem;margin:2rem auto;padding:0 1rem;"
        "background:#101827;color:#eef2ff}section{margin:2rem 0}table{border-collapse:collapse;width:100%}"
        "td{padding:.6rem;border-bottom:1px solid #445}td:last-child{text-align:right}</style>"
        f"<h1>Argus status</h1><p>Snapshot generated {html.escape(generated)}. "
        "This page does not refresh automatically.</p>" + "".join(sections) + "</html>\n"
    )


def write_snapshot(path: Path, document: str) -> None:
    """Replace a snapshot atomically so failed writes preserve the previous page."""
    with tempfile.TemporaryDirectory(prefix=".argus-status-", dir=path.parent) as directory:
        staged = Path(directory) / "status.html"
        staged.write_text(document)
        staged.replace(path)


def main(argv: list[str] | None = None) -> int:
    """Generate a snapshot; a query failure leaves the previous output untouched."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument("--password-file", type=Path, help="Prometheus basic-auth password file; username argus")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        authorization = None
        if args.password_file:
            password = args.password_file.read_text().strip()
            authorization = "Basic " + base64.b64encode(f"argus:{password}".encode()).decode()
        results = [(title, query(args.prometheus_url, expr, authorization)) for title, expr in overview_queries(ROOT)]
        document = render(results, datetime.now(UTC).isoformat(timespec="seconds"))
        write_snapshot(args.output, document)
    except (OSError, ValueError, KeyError, http.client.HTTPException) as err:
        print(f"status-page: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
