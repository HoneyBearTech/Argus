"""Security invariants and opt-in Docker integration for the TLS push proxy.

Run ARGUS_TEST_TLS=1 pytest tests/test_push_security.py to exercise a real nginx
TLS listener against fixture upstreams. The regular suite needs no Docker.
"""

from __future__ import annotations

import base64
import os
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "deploy" / "tls" / "nginx.conf"
OVERLAY = ROOT / "docker-compose.tls.yml"


def test_tls_overlay_replaces_all_plaintext_push_bindings() -> None:
    text = OVERLAY.read_text()
    assert text.count("ports: !override") == 2
    services = yaml.safe_load(text.replace("ports: !override", "ports:"))["services"]
    assert services["prometheus"]["ports"] == ["127.0.0.1:9090:9090"]
    assert services["loki"]["ports"] == ["127.0.0.1:3101:3100"]
    proxy = services["push-proxy"]
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    assert proxy["user"] == "101:101"
    assert "@sha256:" in proxy["image"]
    for volume in proxy["volumes"]:
        assert volume["read_only"] is True
        assert volume["bind"]["create_host_path"] is False


def test_both_agent_configs_authenticate_loki() -> None:
    for name in ("config.alloy", "kubernetes.alloy"):
        text = (ROOT / "agent" / name).read_text()
        block = text.split('loki.write "argus" {', 1)[1].split("external_labels", 1)[0]
        assert 'username = "argus"' in block
        assert 'password = sys.env("ARGUS_LOKI_PASSWORD")' in block
    assert "ARGUS_LOKI_PASSWORD: ${ARGUS_LOKI_PASSWORD:-}" in (ROOT / "agent" / "compose.yml").read_text()


def docker(*args: str) -> str:
    done = subprocess.run(["docker", *args], check=True, capture_output=True, text=True)
    return (done.stdout + done.stderr if args[0] == "logs" else done.stdout).strip()


@pytest.fixture
def tls_proxy(tmp_path: Path) -> Iterator[tuple[str, ssl.SSLContext]]:
    if os.environ.get("ARGUS_TEST_TLS") != "1":
        pytest.skip("set ARGUS_TEST_TLS=1 to run the Docker TLS integration")
    assert shutil.which("docker"), "Docker required when ARGUS_TEST_TLS=1"
    assert shutil.which("openssl"), "openssl required when ARGUS_TEST_TLS=1"
    docker("info", "--format", "{{.ServerVersion}}")
    cert = tmp_path / "fullchain.pem"
    key = tmp_path / "privkey.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    # Throwaway fixture material: nginx uid 101 must traverse the mounted
    # directory on Linux, where bind mounts preserve the host permissions.
    tmp_path.chmod(0o755)
    key.chmod(0o644)
    encoded = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input="test-password\n",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (tmp_path / "htpasswd").write_text(f"argus:{encoded}\n")
    token = base64.b64encode(b"argus:test-password").decode()
    # Same proxy server, with in-container fixture upstreams on the real ports.
    backends = f"""
    server {{
        listen 9090;
        location = /api/v1/write {{
            if ($http_authorization != "Basic {token}") {{ return 401; }}
            return 204;
        }}
    }}
    server {{
        listen 3100;
        location = /loki/api/v1/push {{
            if ($http_authorization != "") {{ return 403; }}
            return 204;
        }}
    }}
"""
    config = tmp_path / "nginx.conf"
    config.write_text(CONFIG.read_text().replace("http {", "http {" + backends, 1))
    overlay = yaml.safe_load(OVERLAY.read_text().replace("ports: !override", "ports:"))
    image = overlay["services"]["push-proxy"]["image"]
    network = docker("network", "create", "argus-tls-test-" + uuid.uuid4().hex)
    try:
        cid = docker(
            "run",
            "-d",
            "--user",
            "101:101",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--tmpfs",
            "/tmp:uid=101,gid=101,mode=0700",  # noqa: S108 - isolated container tmpfs
            "--network",
            network,
            "--network-alias",
            "prometheus",
            "--network-alias",
            "loki",
            "-p",
            "127.0.0.1::8443",
            "-v",
            f"{config}:/etc/nginx/nginx.conf:ro",
            "-v",
            f"{tmp_path}:/etc/nginx/push-tls:ro",
            "--entrypoint",
            "nginx",
            image,
            "-g",
            "daemon off;",
        )
    except subprocess.CalledProcessError:
        docker("network", "rm", network)
        raise

    try:
        assert docker("inspect", "--format", "{{.State.Running}}", cid) == "true", docker("logs", cid)
        host_port = docker("port", cid, "8443/tcp")
        assert host_port, docker("logs", cid)
        host = "https://" + host_port
        context = ssl.create_default_context(cafile=str(cert))
        for _ in range(100):
            try:
                proxy_request(host, "/", context)
                break
            except urllib.error.URLError:
                time.sleep(0.05)
        else:
            pytest.fail("TLS proxy did not become ready: " + docker("logs", cid))
        yield host, context
    finally:
        docker("rm", "-f", cid)
        docker("network", "rm", network)


def proxy_request(host: str, path: str, context: ssl.SSLContext, password: str = "", method: str = "POST") -> int:
    headers = {}
    if password:
        token = base64.b64encode(f"argus:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    request = urllib.request.Request(host + path, headers=headers, data=b"test", method=method)  # noqa: S310 - fixture HTTPS URL
    try:
        with urllib.request.urlopen(request, context=context, timeout=5) as response:  # noqa: S310 - fixture HTTPS URL
            return response.status
    except urllib.error.HTTPError as error:
        error.close()
        return error.code


def test_real_tls_authentication_and_push_only_routes(tls_proxy: tuple[str, ssl.SSLContext]) -> None:
    host, context = tls_proxy
    for path in ("/api/v1/write", "/loki/api/v1/push"):
        assert proxy_request(host, path, context) == 401
        assert proxy_request(host, path, context, "wrong-password") == 401
        assert proxy_request(host, path, context, "test-password") == 204
        assert proxy_request(host, path, context, "test-password", "GET") == 403
    for path in ("/", "/api/v1/query", "/loki/api/v1/query", "/ready", "/api/v1/write/extra"):
        assert proxy_request(host, path, context, "test-password") == 404
    with pytest.raises(urllib.error.URLError, match="CERTIFICATE_VERIFY_FAILED"):
        proxy_request(host, "/api/v1/write", ssl.create_default_context(), "test-password")
