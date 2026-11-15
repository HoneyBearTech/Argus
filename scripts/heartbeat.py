#!/usr/bin/env python3
"""Ping an external dead-man switch only after Argus' local readiness checks pass.

The heartbeat URL is a credential: read it from a file and never log it. Run
once per minute with the supplied systemd timer. Only Python's standard library
is needed; no external heartbeat is sent until explicitly configured.
"""

from __future__ import annotations

import argparse
import base64
import sys
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import override

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 10


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent a redirect from forwarding heartbeat secrets or local credentials."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """Refuse all redirects."""
        return


def request_ok(url: str, password: str = "") -> bool:
    """Return whether the endpoint answers 200 without following redirects."""
    headers = {"User-Agent": "argus-heartbeat"}
    if password:
        token = base64.b64encode(f"argus:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - caller validates URL
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT) as response:
            return response.status == HTTPStatus.OK
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except (OSError, urllib.error.URLError, ValueError):
        return False


def heartbeat(url_file: Path, checks: list[str], password_file: Path) -> bool:
    """Check readiness before sending one authenticated HTTPS heartbeat."""
    url = url_file.read_text().strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        msg = "heartbeat URL must be HTTPS with a host, no userinfo and no fragment"
        raise ValueError(msg)
    password = password_file.read_text().strip() if password_file.exists() else ""
    for check in checks:
        parsed_check = urllib.parse.urlsplit(check)
        if parsed_check.scheme not in {"http", "https"} or not parsed_check.hostname or parsed_check.username:
            msg = "readiness checks must be HTTP(S) URLs without userinfo"
            raise ValueError(msg)
        # Credentials are sent only to Prometheus' readiness path, never Grafana.
        credential = password if parsed_check.path == "/-/ready" else ""
        if not request_ok(check, credential):
            return False
    return request_ok(url)


def main(argv: list[str] | None = None) -> int:
    """Run one readiness check and heartbeat, returning a failure status if either fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url-file", type=Path, default=ROOT / "secrets" / "heartbeat_url")
    parser.add_argument("--prometheus-password-file", type=Path, default=ROOT / "secrets" / "prometheus_password")
    parser.add_argument("--check", action="append", help="readiness URL; repeat to replace the default checks")
    args = parser.parse_args(argv)
    checks = args.check or ["http://127.0.0.1:3000/api/health", "http://127.0.0.1:9090/-/ready"]
    try:
        succeeded = heartbeat(args.url_file, checks, args.prometheus_password_file)
    except (OSError, ValueError):
        print("Argus heartbeat configuration could not be read or is invalid", file=sys.stderr)
        return 1
    if not succeeded:
        print("Argus readiness check or external heartbeat failed", file=sys.stderr)
        return 1
    print("Argus readiness checks and external heartbeat succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
