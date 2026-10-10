"""Tests for security-relevant settings in the shipped configuration (see docs/assurance-case.md)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text())


def test_http_probe_does_not_count_403_as_up() -> None:
    """Regression test for #3: a reverse proxy's access list answers 403 without reaching the service."""
    http = load("blackbox/blackbox.yml")["modules"]["http_service"]["http"]
    assert 403 not in http["valid_status_codes"]
    assert 200 in http["valid_status_codes"]


def test_probes_verify_tls_certificates() -> None:
    for name, module in load("blackbox/blackbox.yml")["modules"].items():
        tls = module.get(module["prober"], {}).get("tls_config", {})
        assert not tls.get("insecure_skip_verify"), f"{name} skips TLS verification"


def test_dashboards_cannot_be_changed_in_the_ui() -> None:
    for provider in load("provisioning/dashboards/argus.yaml")["providers"]:
        assert provider["allowUiUpdates"] is False
        assert provider["disableDeletion"] is True


def test_datasources_cannot_be_changed_in_the_ui() -> None:
    for datasource in load("provisioning/datasources/argus.yaml")["datasources"]:
        assert datasource["editable"] is False


def test_grafana_image_turns_off_sign_up_and_anonymous_access() -> None:
    dockerfile = (ROOT / "images" / "grafana" / "Dockerfile").read_text()
    assert re.search(r"\bGF_USERS_ALLOW_SIGN_UP=false\b", dockerfile)
    assert re.search(r"\bGF_AUTH_ANONYMOUS_ENABLED=false\b", dockerfile)


def test_credentials_come_from_files_or_environment() -> None:
    """Scrape credentials are read from secrets/, never written into the Prometheus config."""
    config = (ROOT / "prometheus" / "prometheus.yml").read_text()
    assert not re.search(r"^\s*(password|bearer_token|credentials):", config, re.MULTILINE)
    contact_points = (ROOT / "provisioning" / "alerting" / "contact-points.yaml").read_text()
    assert "url: ${DISCORD_WEBHOOK_URL}" in contact_points


def test_compose_files_publish_no_blackbox_or_exporter_ports() -> None:
    """Only Grafana, Prometheus and Loki listen on the host; exporters stay on the compose network."""
    services = load("docker-compose.yml")["services"]
    published = sorted(name for name, service in services.items() if service.get("ports"))
    assert published == ["grafana", "loki", "prometheus"]


def test_proxy_override_adds_only_grafana_to_the_proxy_network() -> None:
    """Grafana keeps the compose network (to reach Prometheus) and joins only an existing proxy network."""
    override = load("docker-compose.proxy.yml")
    assert list(override["services"]) == ["grafana"]
    networks = override["services"]["grafana"]["networks"]
    assert "default" in networks
    assert networks["proxy"]["aliases"] == ["argus-grafana"]
    assert override["networks"]["proxy"]["external"] is True
    assert "ports" not in override["services"]["grafana"]


def test_unifi_exporter_verifies_tls_by_default() -> None:
    environment = load("docker-compose.yml")["services"]["unpoller"]["environment"]
    assert environment["UP_UNIFI_DEFAULT_VERIFY_SSL"] == "${UNIFI_VERIFY_SSL:-true}"


def test_blackbox_image_does_not_run_as_root() -> None:
    dockerfile = (ROOT / "images" / "blackbox" / "Dockerfile").read_text()
    users = re.findall(r"^USER\s+(\S+)", dockerfile, re.MULTILINE)
    assert users
    assert users[-1].split(":")[0] not in {"0", "root"}


def test_grafana_runs_only_the_plugins_in_its_image() -> None:
    dockerfile = (ROOT / "images" / "grafana" / "Dockerfile").read_text()
    assert re.search(r"^\s*GF_PLUGINS_PREINSTALL_DISABLED=true\b", dockerfile, re.MULTILINE)
    # Not /var/lib/grafana/plugins, which is in the data volume and survives image upgrades.
    plugins = re.search(r"^\s*GF_PATHS_PLUGINS=(\S+)", dockerfile, re.MULTILINE)
    assert plugins
    assert not plugins.group(1).startswith("/var/lib/grafana")


def test_grafana_image_does_not_run_as_root() -> None:
    dockerfile = (ROOT / "images" / "grafana" / "Dockerfile").read_text()
    users = re.findall(r"^USER\s+(\S+)", dockerfile, re.MULTILINE)
    assert users
    assert users[-1].split(":")[0] not in {"0", "root"}


def test_agent_can_reach_containerd() -> None:
    # Regression test: with Docker's containerd image store (default since Docker 29), cAdvisor needs
    # containerd's socket, or the Docker Containers dashboard is empty for that host.
    agent = load("agent/compose.yml")["services"]["agent"]
    assert "/run/containerd:/run/containerd:ro" in agent["volumes"]


def alloy_block(config: str, header: str) -> str:
    """Return the Alloy block that starts with `header`, up to its matching closing brace."""
    start = config.index(header + " {")
    depth = 0
    for end in range(config.index("{", start), len(config)):
        depth += {"{": 1, "}": -1}.get(config[end], 0)
        if depth == 0:
            return config[start : end + 1]
    msg = f"unterminated block: {header}"
    raise ValueError(msg)


def test_agent_skips_gitlab_runner_job_containers() -> None:
    # CI job containers keep raw job output, without GitLab's secret masking: they must not be
    # tailed into Loki, and their one-job lifetimes would only churn container metrics.
    config = (ROOT / "agent/config.alloy").read_text()
    label = "com_gitlab_gitlab_runner_managed"
    log_targets = alloy_block(config, 'discovery.relabel "log_targets"')
    assert f"__meta_docker_container_label_{label}" in log_targets
    assert 'action        = "drop"' in log_targets
    source = alloy_block(config, 'loki.source.docker "containers"')
    assert "targets       = discovery.relabel.log_targets.output" in source
    metrics = alloy_block(config, 'prometheus.relabel "containers"')
    regex = re.search(r'source_labels = \["name"\]\s*regex\s*= "([^"]+)"\s*action\s*= "drop"', metrics)
    assert regex
    job = re.compile(regex.group(1))
    assert job.fullmatch("runner-t3abcdef-project-12-concurrent-0-0a1b2c3d4e5f6a7b-build")
    assert job.fullmatch("runner-t3abcdef-project-12-concurrent-0")
    # cache-init containers (seen on GitLab Runner 19.4 with the Docker executor)
    assert job.fullmatch(f"runner-{'a' * 32}-cache-{'b' * 32}-protected-set-permission-{'c' * 32}")
    assert not job.fullmatch("my-runner-app")


def test_prometheus_reads_its_web_config_from_secrets() -> None:
    """Whether Prometheus requires a password is decided by secrets/prometheus-web.yml."""
    command = load("docker-compose.yml")["services"]["prometheus"]["command"]
    assert "--web.config.file=/etc/prometheus/secrets/prometheus-web.yml" in command


def test_example_web_config_requires_no_password() -> None:
    """The shipped example lists no users, so no install ends up with a published password."""
    assert load("secrets.example/prometheus-web.yml") is None


def test_prometheus_password_is_read_from_a_file() -> None:
    """Grafana and Prometheus' own scrape read the password from secrets/, never from committed config."""
    datasource = next(d for d in load("provisioning/datasources/argus.yaml")["datasources"] if d["uid"] == "prometheus")
    assert datasource["basicAuth"] is True
    assert datasource["basicAuthUser"] == "argus"
    assert datasource["secureJsonData"]["basicAuthPassword"] == "$__file{/etc/grafana/secrets/prometheus_password}"
    job = next(j for j in load("prometheus/prometheus.yml")["scrape_configs"] if j["job_name"] == "prometheus")
    assert job["basic_auth"] == {"username": "argus", "password_file": "/etc/prometheus/secrets/prometheus_password"}


def test_grafana_gets_only_the_prometheus_password() -> None:
    """Grafana mounts one secret file, read-only, and compose refuses to start rather than create it."""
    volumes = load("docker-compose.yml")["services"]["grafana"]["volumes"]
    secrets = [v for v in volumes if isinstance(v, dict) and "secrets" in v["source"]]
    assert secrets == [
        {
            "type": "bind",
            "source": "./secrets/prometheus_password",
            "target": "/etc/grafana/secrets/prometheus_password",
            "read_only": True,
            "bind": {"create_host_path": False},
        }
    ]
    assert not [v for v in volumes if isinstance(v, str) and "secrets" in v]


def test_agent_sends_the_prometheus_password() -> None:
    config = (ROOT / "agent" / "config.alloy").read_text()
    remote_write = re.search(r'prometheus\.remote_write "argus" \{.*?\n\}', config, re.DOTALL)
    assert remote_write
    assert re.search(
        r'basic_auth \{\s*username = "argus"\s*password = sys\.env\("ARGUS_PROMETHEUS_PASSWORD"\)\s*\}',
        remote_write.group(),
    )
    environment = load("agent/compose.yml")["services"]["agent"]["environment"]
    assert environment["ARGUS_PROMETHEUS_PASSWORD"] == "${ARGUS_PROMETHEUS_PASSWORD:-}"  # noqa: S105 - compose reference
