"""Exercise the real Grafana provisioning parser in an isolated container."""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    os.environ.get("ARGUS_TEST_GRAFANA") != "1", reason="needs built argus-grafana:ci image"
)


@pytest.mark.parametrize("channel", ["email", "slack", "ntfy"])
def test_notification_loads(channel: str, tmp_path: Path) -> None:
    password = tmp_path / "admin_password"
    password.write_text("argus-ci")
    password.chmod(0o644)
    command = [
        "docker",
        "run",
        "-d",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp",  # noqa: S108 - container tmpfs, not a host path
        "--tmpfs",
        "/var/lib/grafana",
        "-p",
        "127.0.0.1::3000",
        "-e",
        "GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_admin_password",
        "-e",
        "ARGUS_EMAIL_ADDRESSES=operator@example.invalid",
        "-e",
        "LOKI_URL=http://loki:3100",
        "-e",
        "STEERHOUSE_DB_ADDRESS=database.example.invalid:5432",
    ]
    mounts = {
        password: "/run/secrets/grafana_admin_password",
        ROOT / "secrets.example/prometheus_password": "/etc/grafana/secrets/prometheus_password",
        ROOT / "secrets.example/notification_endpoint": "/run/secrets/notification_endpoint",
        ROOT / "secrets.example/steerhouse_db_password": "/run/secrets/steerhouse_db_password",
        ROOT / "secrets.example/steerhouse_db_ca": "/run/secrets/steerhouse_db_ca",
        ROOT / "deploy/notifications" / f"{channel}.yaml": "/etc/grafana/provisioning/alerting/contact-points.yaml",
        ROOT / "deploy/notifications/policies.yaml": "/etc/grafana/provisioning/alerting/policies.yaml",
    }
    for source, destination in mounts.items():
        command.extend(["-v", f"{source}:{destination}:ro"])
    container = subprocess.check_output([*command, "argus-grafana:ci"], text=True).strip()
    try:
        port = subprocess.check_output(["docker", "port", container, "3000"], text=True).strip()
        request = urllib.request.Request(f"http://{port}/api/v1/provisioning/contact-points")
        # Fixed credentials exist only inside this disposable CI container.
        request.add_header("Authorization", "Basic YWRtaW46YXJndXMtY2k=")
        deadline = time.monotonic() + 90
        points = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - loopback Docker port
                    points = json.load(response)
                break
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, ConnectionResetError):
                time.sleep(1)
        logs = subprocess.check_output(["docker", "logs", container], text=True, stderr=subprocess.STDOUT)
        assert points is not None, logs
        assert [(point["name"], point["type"]) for point in points] == [
            ("Notifications", {"email": "email", "slack": "slack", "ntfy": "webhook"}[channel])
        ], logs
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=True, capture_output=True)
