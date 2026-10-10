#!/usr/bin/env python3
"""Deploy the latest main to an Argus server that runs from a checkout (source mode).

Run by the systemd timer in deploy/systemd/ (see docs/auto-deploy.md). Each run:

1. fetches origin/main and stops if the checkout is already there, isn't on main, has local edits to
   tracked files, or has commits that aren't on origin/main;
2. waits until the "Dashboards + config" check from GitHub Actions has passed on the new commit, and
   never deploys one where it failed;
3. fast-forwards, runs `docker compose up -d --build` and restarts the services whose bind-mounted
   configuration changed (dashboards need nothing: Grafana rereads them every 30 seconds);
4. checks that Grafana and Prometheus answer. If they don't, it goes back to the previous commit,
   redeploys that, and remembers the bad commit so the next run doesn't try it again.

Deploys and rollbacks are posted to Discord when DISCORD_WEBHOOK_URL is set in .env. Only the standard
library is used, so the script runs with the server's own python3.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
CHECK_NAME = "Dashboards + config"
CHECK_APP = "github-actions"
# Commits that failed to deploy; the timer skips them until main moves on.
BAD_COMMITS = ROOT / ".git" / "argus-deploy-bad-commits"
# Bind-mounted paths (docker-compose.source.yml) and the service that reads them at start-up.
RESTART_ON = {
    "prometheus/": "prometheus",
    "blackbox/": "blackbox",
    "logs/loki.yaml": "loki",
    "provisioning/": "grafana",
}
# Service, container port, the path that answers 200 once it's ready, and whether it may need
# Prometheus' password (secrets/prometheus-web.yml).
HEALTH_CHECKS = (("grafana", 3000, "/api/health", False), ("prometheus", 9090, "/-/ready", True))
PROMETHEUS_PASSWORD = ROOT / "secrets" / "prometheus_password"
HEALTH_TIMEOUT = 300
USER_AGENT = "argus-deploy"


class DeployError(Exception):
    """A step failed; the message says which."""


def run(*cmd: str) -> str:
    """Run a command in the checkout and return its output."""
    try:
        done = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)  # noqa: S603 - fixed commands
    except subprocess.CalledProcessError as err:
        msg = f"{' '.join(cmd)} failed: {(err.stderr or err.stdout).strip()}"
        raise DeployError(msg) from err
    return done.stdout.strip()


def log(message: str) -> None:
    """Print a line for the journal."""
    print(message, flush=True)


def repo_slug(url: str) -> str:
    """Return owner/name from a GitHub remote URL (HTTPS or SSH)."""
    match = re.fullmatch(r"(?:https://github\.com/|(?:ssh://)?git@github\.com[:/])([^/]+/[^/]+?)(?:\.git)?/?", url)
    if not match:
        msg = f"origin is not a GitHub repository: {url}"
        raise DeployError(msg)
    return match.group(1)


def ci_result(check_runs: list[dict[str, Any]]) -> str:
    """Reduce a commit's check runs to "success", "pending" or "failure" for the required check."""
    runs = [r for r in check_runs if r.get("name") == CHECK_NAME and (r.get("app") or {}).get("slug") == CHECK_APP]
    if any(r.get("conclusion") == "success" for r in runs):
        return "success"
    if not runs or any(r.get("status") != "completed" for r in runs):
        return "pending"
    return "failure"


def http_json(url: str) -> Any:  # noqa: ANN401 - any JSON value
    """GET a JSON document."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})  # noqa: S310 - https URL built here
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def check_runs(slug: str, sha: str) -> list[dict[str, Any]]:
    """Fetch the commit's check runs from GitHub's public API."""
    query = urllib.parse.urlencode({"check_name": CHECK_NAME})
    return http_json(f"https://api.github.com/repos/{slug}/commits/{sha}/check-runs?{query}")["check_runs"]


def read_env(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from a compose .env file."""
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                env[key.strip()] = value.strip().strip("'\"")
    return env


def notify(webhook: str, message: str) -> None:
    """Post to Discord; a failure here is logged, never fatal."""
    if not webhook:
        return
    body = json.dumps({"content": message}).encode()
    request = urllib.request.Request(  # noqa: S310 - the operator's webhook URL
        webhook, data=body, headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=30).close()  # noqa: S310
    except (urllib.error.URLError, OSError) as err:
        log(f"Discord notification failed: {err}")


def changed_services(changed: list[str], running: set[str]) -> list[str]:
    """Return the running services that read one of the changed files at start-up."""
    wanted = {service for path in changed for prefix, service in RESTART_ON.items() if path.startswith(prefix)}
    return sorted(wanted & running)


def answers(url: str, authorization: str | None = None) -> bool:
    """Whether the URL answers 200, sending the Authorization header if there is one."""
    request = urllib.request.Request(url, headers={"Authorization": authorization} if authorization else {})  # noqa: S310 - local health endpoint
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - local health endpoint
            return response.status == 200  # noqa: PLR2004 - HTTP OK
    except urllib.error.HTTPError as err:
        err.close()
        return False
    except (urllib.error.URLError, OSError, http.client.HTTPException):  # nothing there, or not HTTP
        return False


def prometheus_authorization() -> str | None:
    """Return the basic auth header for Prometheus' `argus` user, if secrets/ has its password."""
    if not PROMETHEUS_PASSWORD.exists():
        return None
    password = PROMETHEUS_PASSWORD.read_text().strip()
    return "Basic " + base64.b64encode(f"argus:{password}".encode()).decode()


def health_urls() -> dict[str, str | None]:
    """Health URLs of the published Grafana and Prometheus ports, with the Authorization header for each."""
    urls = {}
    for service, port, path, needs_password in HEALTH_CHECKS:
        published = run("docker", "compose", "port", service, str(port))
        host, _, host_port = published.rpartition(":")
        host = "127.0.0.1" if host in {"0.0.0.0", "", "::", "[::]"} else host  # noqa: S104 - mapping, not binding
        urls[f"http://{host}:{host_port}{path}"] = prometheus_authorization() if needs_password else None
    return urls


def healthy(timeout: float = HEALTH_TIMEOUT) -> bool:
    """Wait until Grafana and Prometheus answer, up to the timeout."""
    deadline = time.monotonic() + timeout
    pending = health_urls()
    while pending and time.monotonic() < deadline:
        pending = {url: auth for url, auth in pending.items() if not answers(url, auth)}
        if pending:
            time.sleep(5)
    for url in pending:
        log(f"not answering: {url}")
    return not pending


def apply(changed: list[str]) -> list[str]:
    """Rebuild and start the stack, then restart the services that read a changed config."""
    run("docker", "compose", "up", "-d", "--build")
    running = set(run("docker", "compose", "ps", "--services", "--status", "running").splitlines())
    restart = changed_services(changed, running)
    if restart:
        run("docker", "compose", "restart", *restart)
    return restart


def rollback(old: str, changed: list[str]) -> str:
    """Return the checkout and the stack to `old`; describe how that went."""
    try:
        run("git", "reset", "--hard", "--quiet", old)
        apply(changed)
    except DeployError as err:
        return f"rolling back failed too ({err}); check the server"
    return "it is healthy again" if healthy() else "it is NOT healthy either; check the server"


def bad_commits() -> set[str]:
    """Return the commits a previous run rolled back."""
    return set(BAD_COMMITS.read_text().split()) if BAD_COMMITS.exists() else set()


def next_commit() -> tuple[str, str] | None:
    """Return (current, new) when origin/main has a commit to deploy; raise if the checkout can't follow it."""
    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        log(f"checkout is on {branch}, not {BRANCH}; auto-deploy only follows {BRANCH}")
        return None
    run("git", "fetch", "--quiet", "origin", BRANCH)
    old, new = run("git", "rev-parse", "HEAD"), run("git", "rev-parse", f"origin/{BRANCH}")
    if old == new or new in bad_commits():
        return None
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        msg = "tracked files have local changes; not deploying (commit or discard them)"
        raise DeployError(msg)
    try:
        run("git", "merge-base", "--is-ancestor", old, new)
    except DeployError:
        msg = f"HEAD {old[:7]} is not an ancestor of origin/{BRANCH}; not deploying"
        raise DeployError(msg) from None
    return old, new


def ship(old: str, new: str, subject: str) -> int:
    """Deploy `new`; roll back to `old` if it fails. Return the exit status."""
    webhook = read_env(ROOT / ".env").get("DISCORD_WEBHOOK_URL", "")
    changed = run("git", "diff", "--name-only", old, new).splitlines()
    log(f"deploying {old[:7]} -> {new[:7]}: {subject}")
    try:
        run("git", "merge", "--ff-only", "--quiet", new)
        restarted = apply(changed)
        log(f"at {new[:7]}; restarted: {', '.join(restarted) or 'nothing'}")
        if healthy():
            notify(webhook, f"Argus deployed `{new[:7]}`: {subject}")
            return 0
        failure = "Grafana or Prometheus did not come back"
    except DeployError as err:
        failure = str(err)
    log(f"deploy of {new[:7]} failed ({failure}); rolling back to {old[:7]}")
    with BAD_COMMITS.open("a") as bad:
        bad.write(new + "\n")
    state = rollback(old, changed)
    log(f"rolled back to {old[:7]}: {state}")
    notify(webhook, f"Argus deploy of `{new[:7]}` ({subject}) failed: {failure}. Rolled back to `{old[:7]}`; {state}.")
    return 1


def deploy(*, dry_run: bool = False) -> int:
    """Run once, as the timer does; return the exit status."""
    commits = next_commit()
    if commits is None:
        return 0
    old, new = commits
    result = ci_result(check_runs(repo_slug(run("git", "remote", "get-url", "origin")), new))
    if result != "success":
        log(f"{new[:7]}: {CHECK_NAME} is {result}; {'waiting' if result == 'pending' else 'not deploying it'}")
        return 0
    subject = run("git", "log", "-1", "--format=%s", new)
    if dry_run:
        log(f"would deploy {old[:7]} -> {new[:7]}: {subject}")
        return 0
    return ship(old, new, subject)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="say what would be deployed, change nothing")
    args = parser.parse_args(argv)
    try:
        return deploy(dry_run=args.dry_run)
    except (DeployError, urllib.error.URLError, OSError, KeyError, ValueError) as err:
        log(f"auto-deploy: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
