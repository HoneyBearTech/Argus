#!/usr/bin/env python3
"""Upgrade a published-image installation with config validation and health rollback."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import auto_deploy

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def select_release(version: str) -> str:
    """Resolve an explicit stable version or GitHub's latest published release."""
    if version != "latest" and not VERSION.fullmatch(version.removeprefix("v")):
        msg = "version must be a stable semantic version or latest"
        raise auto_deploy.DeployError(msg)
    tag = "latest" if version == "latest" else "tags/v" + version.removeprefix("v")
    release = auto_deploy.http_json(f"https://api.github.com/repos/HoneyBearTech/Argus/releases/{tag}")
    selected = str(release.get("tag_name", "")).removeprefix("v")
    if release.get("draft") or release.get("prerelease") or not VERSION.fullmatch(selected):
        msg = "only published stable semantic-version releases are supported"
        raise auto_deploy.DeployError(msg)
    if version != "latest" and selected != version.removeprefix("v"):
        msg = "release tag did not match the requested version"
        raise auto_deploy.DeployError(msg)
    return selected


def save_env(path: Path, content: str) -> None:
    """Atomically replace .env without exposing credentials in a temporary file."""
    with tempfile.TemporaryDirectory(prefix="argus-upgrade-", dir=path.parent) as directory:
        staged = Path(directory) / "env"
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)
        staged.replace(path)


def version_env(content: str, version: str) -> str:
    """Change just the shared image release selector, preserving other settings."""
    if not VERSION.fullmatch(version):
        msg = "invalid release version"
        raise auto_deploy.DeployError(msg)
    if re.search(r"(?m)^ARGUS_VERSION=", content):
        return re.sub(r"(?m)^ARGUS_VERSION=.*$", f"ARGUS_VERSION={version}", content)
    return content.rstrip("\n") + f"\nARGUS_VERSION={version}\n"


def target_config(content: str, selected: str) -> dict[str, object]:
    """Render the target release without changing the live installation's .env."""
    with tempfile.TemporaryDirectory(prefix="argus-upgrade-", dir=ROOT) as directory:
        candidate = Path(directory) / "candidate.env"
        save_env(candidate, version_env(content, selected))
        return json.loads(
            auto_deploy.run("docker", "compose", "--env-file", str(candidate), "config", "--format", "json")
        )


def validate_images(config: dict[str, object], registry: str, selected: str) -> None:
    """Reject Compose overrides that bypass the shared release selector."""
    services = config["services"]
    for name in ("grafana", "prometheus", "blackbox", "loki"):
        if name in services and services[name].get("image") != f"{registry}/argus-{name}:{selected}":
            msg = f"{name} image does not follow ARGUS_VERSION; remove its Compose image override"
            raise auto_deploy.DeployError(msg)


def require_healthy() -> None:
    """Require both application health endpoints to answer after an upgrade."""
    if not auto_deploy.healthy():
        msg = "Grafana or Prometheus did not become ready"
        raise auto_deploy.DeployError(msg)


def upgrade(version: str, *, dry_run: bool = False) -> int:
    """Select, validate, pull and start a release; restore the previous env on failure."""
    path = ROOT / ".env"
    if path.is_symlink():
        msg = ".env must be a regular file, not a symlink"
        raise auto_deploy.DeployError(msg)
    original = path.read_text()
    selected = select_release(version)
    config = json.loads(auto_deploy.run("docker", "compose", "config", "--format", "json"))
    services = config["services"]
    if any(service.get("build") for service in services.values()):
        msg = "this tool supports published images; source-mode installations use auto_deploy.py"
        raise auto_deploy.DeployError(msg)
    env = auto_deploy.read_env(path)
    if any(env.get(key) for key in ("ARGUS_AGENT_IMAGE", "ARGUS_INTEL_GPU_EXPORTER_IMAGE")):
        msg = "remove individual image overrides from .env before upgrading the shared release"
        raise auto_deploy.DeployError(msg)
    if any(os.environ.get(key) for key in ("ARGUS_VERSION", "ARGUS_AGENT_IMAGE", "ARGUS_INTEL_GPU_EXPORTER_IMAGE")):
        msg = "unset image version overrides in the shell before upgrading"
        raise auto_deploy.DeployError(msg)
    target = target_config(original, selected)
    registry = os.environ.get("ARGUS_REGISTRY", env.get("ARGUS_REGISTRY", "ghcr.io/honeybeartech"))
    validate_images(target, registry, selected)
    if dry_run:
        print(f"Would deploy Argus {selected}; target Compose configuration is valid.")
        return 0
    backup = ROOT / "secrets/argus-upgrade.env.backup"
    save_env(backup, original)
    save_env(path, version_env(original, selected))
    try:
        auto_deploy.run("docker", "compose", "config", "--quiet")
        auto_deploy.run("docker", "compose", "pull")
        auto_deploy.run("docker", "compose", "up", "-d", "--wait", "--wait-timeout", "300")
        require_healthy()
    except (auto_deploy.DeployError, OSError):
        save_env(path, original)
        auto_deploy.run("docker", "compose", "up", "-d", "--wait", "--wait-timeout", "300")
        if not auto_deploy.healthy():
            msg = "rollback restored .env but the previous release is unhealthy; inspect the server"
            raise auto_deploy.DeployError(msg) from None
        print("Upgrade failed; restored the previous release and verified its health.", file=sys.stderr)
        return 1
    print(f"Argus {selected} is healthy. Previous .env saved in secrets/argus-upgrade.env.backup.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run a single upgrade while holding an exclusive installation lock."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="stable version such as 0.9.0, or latest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        (ROOT / "secrets").mkdir(mode=0o700, exist_ok=True)
        with (ROOT / "secrets/.argus-upgrade.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return upgrade(args.version, dry_run=args.dry_run)
    except (auto_deploy.DeployError, OSError, ValueError, KeyError) as err:
        print(f"upgrade: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
