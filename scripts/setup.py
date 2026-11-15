#!/usr/bin/env python3
"""Prepare a safe local Argus configuration without replacing existing files."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_new(path: Path, text: str, mode: int = 0o644) -> bool:
    """Create a file exclusively so a repeated setup never replaces operator data."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(text)
    return True


def prepare(root: Path, config_root: str, profiles: str) -> None:
    """Copy examples, generate the initial admin password, and bind ports locally."""
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", config_root):
        msg = "CONFIG_ROOT must be an absolute path containing only letters, digits, _, -, . and /"
        raise ValueError(msg)
    allowed = {
        "loki",
        "snmp",
        "radarr",
        "radarr4k",
        "sonarr",
        "sonarr4k",
        "lidarr",
        "bazarr",
        "prowlarr",
        "sabnzbd",
        "qbittorrent",
        "gitlab",
        "proxmox",
        "tdarr",
        "varken",
    }
    if any(profile not in allowed for profile in profiles.split(",") if profile):
        msg = "unknown Compose profile; see .env.example"
        raise ValueError(msg)
    env = (root / ".env.example").read_text()
    for key, value in {
        "CONFIG_ROOT": config_root,
        "COMPOSE_PROFILES": profiles,
        "GRAFANA_BIND": "127.0.0.1:3000",
        "PROMETHEUS_BIND": "127.0.0.1:9090",
        "LOKI_BIND": "127.0.0.1:3101",
    }.items():
        env = re.sub(rf"(?m)^{key}=.*$", f"{key}={value}", env)
    write_new(root / ".env", env, 0o600)
    for directory in ("targets", "secrets"):
        destination = root / directory
        destination.mkdir(mode=0o700, exist_ok=True)
        for example in sorted((root / f"{directory}.example").iterdir()):
            if example.is_file() and example.name != "grafana_admin_password":
                # Target examples contain documentation addresses; new installations
                # start with no external scrape/probe targets.
                content = "[]\n" if directory == "targets" else example.read_text()
                write_new(destination / example.name, content)
    write_new(root / "secrets/grafana_admin_password", secrets.token_urlsafe(32) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Prompt for the initial configuration, or accept explicit unattended defaults."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--defaults", action="store_true", help="use loopback binds, /srv/config and the loki profile")
    parser.add_argument("--config-root", default="/srv/config")
    parser.add_argument("--profiles", default="loki", help="comma-separated Compose profiles")
    args = parser.parse_args(argv)
    try:
        config_root = args.config_root
        profiles = args.profiles
        if not args.defaults:
            config_root = input(f"Persistent data directory [{config_root}]: ").strip() or config_root
            profiles = input(f"Compose profiles [{profiles}] (use --profiles '' for none): ").strip() or profiles
        prepare(ROOT, config_root, profiles)
    except (OSError, ValueError, EOFError) as err:
        print(f"setup: {err}", file=sys.stderr)
        return 1
    print("Configuration prepared; existing files preserved. Ports listen on loopback.")
    print("Read secrets/grafana_admin_password for the login; review targets/ and secrets/ before starting.")
    print("Next: docker compose config --quiet && docker compose up -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
