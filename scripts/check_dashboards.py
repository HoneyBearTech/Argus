#!/usr/bin/env python3
"""Repo checks for Argus, run in CI and before committing.

- Every dashboard is valid JSON with a stable, unique uid, "id": null, the
  "argus" tag and a description (the question it answers).
- Every datasource reference uses a uid provisioned in provisioning/datasources/.
- No committed file contains a private IP address or any of the forbidden
  patterns (internal domains, hostnames) — the repo is public. The patterns
  themselves can't live here either, so they come from a gitignored
  .forbidden-patterns file and/or the ARGUS_FORBIDDEN_PATTERNS environment
  variable (a CI secret): one case-insensitive regex per line.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = ROOT / "dashboards"
DATASOURCES = ROOT / "provisioning" / "datasources"

UID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# Grafana's built-in pseudo datasources, allowed alongside the provisioned ones.
BUILTIN_DS_UIDS = {"grafana", "-- Grafana --", "-- Mixed --", "-- Dashboard --", "__expr__"}
PRIVATE_IP_RE = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
)
FORBIDDEN_FILE = ROOT / ".forbidden-patterns"


def provisioned_uids():
    uids = set()
    for path in DATASOURCES.glob("*.y*ml"):
        uids.update(re.findall(r"^\s*uid:\s*['\"]?([^'\"\s#]+)", path.read_text(), re.MULTILINE))
    return uids


def datasource_uids(node):
    """Yield every datasource uid referenced anywhere in a dashboard."""
    if isinstance(node, dict):
        ds = node.get("datasource")
        if isinstance(ds, dict) and "uid" in ds:
            yield ds["uid"]
        elif isinstance(ds, str):
            yield ds
        for value in node.values():
            yield from datasource_uids(value)
    elif isinstance(node, list):
        for item in node:
            yield from datasource_uids(item)


def check_dashboards(errors):
    allowed = provisioned_uids() | BUILTIN_DS_UIDS
    seen = {}
    for path in sorted(DASHBOARDS.rglob("*.json")):
        rel = path.relative_to(ROOT)
        try:
            dash = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        uid = dash.get("uid")
        if not isinstance(uid, str) or not UID_RE.match(uid):
            errors.append(f"{rel}: uid {uid!r} must be lowercase letters, digits and dashes, max 40 chars")
        elif uid in seen:
            errors.append(f"{rel}: uid {uid!r} already used by {seen[uid]}")
        else:
            seen[uid] = rel
        if dash.get("id") is not None:
            errors.append(f"{rel}: \"id\" must be null (Grafana assigns it)")
        if "argus" not in dash.get("tags", []):
            errors.append(f"{rel}: missing the \"argus\" tag")
        if not dash.get("description", "").strip():
            errors.append(f"{rel}: missing a description (the question the dashboard answers)")
        for ds_uid in sorted(set(datasource_uids(dash))):
            if ds_uid not in allowed:
                errors.append(f"{rel}: datasource uid {ds_uid!r} is not provisioned (allowed: {sorted(allowed)})")
    return len(seen)


def forbidden_patterns():
    lines = os.environ.get("ARGUS_FORBIDDEN_PATTERNS", "").splitlines()
    if FORBIDDEN_FILE.is_file():
        lines += FORBIDDEN_FILE.read_text().splitlines()
    patterns = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def check_no_network_details(errors):
    rules = [(PRIVATE_IP_RE, "private IP address")]
    forbidden = forbidden_patterns()
    rules += [(regex, "forbidden pattern") for regex in forbidden]
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for regex, what in rules:
                match = regex.search(line)
                if match:
                    errors.append(f"{name}:{lineno}: {what} {match.group(0)!r} — keep network details out of this public repo")
    return len(forbidden)


def main():
    errors = []
    count = check_dashboards(errors)
    pattern_count = check_no_network_details(errors)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"\n{len(errors)} problem(s) found.", file=sys.stderr)
        return 1
    print(f"OK: {count} dashboard(s) checked, no private IPs or forbidden patterns ({pattern_count} loaded).")
    if pattern_count == 0:
        print("warning: no forbidden patterns loaded — create .forbidden-patterns or set ARGUS_FORBIDDEN_PATTERNS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
