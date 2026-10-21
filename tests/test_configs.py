"""Tests for security-relevant settings in the shipped configuration (see docs/assurance-case.md)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
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
    assert "url: $__file{/run/secrets/discord_webhook_url}" in contact_points


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


def test_grafana_reads_its_admin_password_and_webhook_from_files() -> None:
    """Neither shows in `docker inspect`: compose secrets, read through __FILE and $__file{}."""
    grafana = load("docker-compose.yml")["services"]["grafana"]
    environment = grafana["environment"]
    assert environment["GF_SECURITY_ADMIN_PASSWORD__FILE"] == "/run/secrets/grafana_admin_password"  # noqa: S105 - a path
    assert "GF_SECURITY_ADMIN_PASSWORD" not in environment
    assert "DISCORD_WEBHOOK_URL" not in environment
    assert grafana["secrets"] == ["grafana_admin_password", "discord_webhook_url"]
    receivers = [r for p in load("provisioning/alerting/contact-points.yaml")["contactPoints"] for r in p["receivers"]]
    assert [r["settings"]["url"] for r in receivers] == ["$__file{/run/secrets/discord_webhook_url}"]


def test_secret_templates_cant_post_alerts_or_set_a_known_password() -> None:
    """A copy of secrets.example/ must neither reach a real channel nor start Grafana with a published password."""
    webhook = (ROOT / "secrets.example" / "discord_webhook_url").read_text().strip()
    assert re.fullmatch(r"https://[^/]+\.invalid/\S*", webhook)
    assert not (ROOT / "secrets.example" / "grafana_admin_password").read_text().strip()


def test_grafana_image_starts_through_the_password_check() -> None:
    dockerfile = (ROOT / "images" / "grafana" / "Dockerfile").read_text()
    assert re.search(r'^ENTRYPOINT \["/argus-start.sh"\]$', dockerfile, re.MULTILINE)
    assert "images/grafana/start.sh /argus-start.sh" in dockerfile
    assert (ROOT / "images" / "grafana" / "start.sh").read_text().rstrip().endswith('exec /run.sh "$@"')


@pytest.mark.parametrize(
    ("password_file", "env_password", "refused"),
    [
        ("", None, True),  # the template: empty
        (" \n\t\n", None, True),
        (None, None, True),  # file missing (or unreadable)
        ("s3cret\n", None, False),
        (None, "from-env", False),  # GF_SECURITY_ADMIN_PASSWORD still works without __FILE (CI's boot test)
        (None, "", True),
    ],
)
def test_grafana_refuses_to_start_without_an_admin_password(
    tmp_path: Path, password_file: str | None, env_password: str | None, *, refused: bool
) -> None:
    """Grafana would fall back to admin/admin; the entrypoint stops first. Otherwise it execs /run.sh (absent here)."""
    environment = {"PATH": "/usr/bin:/bin"}
    if env_password is None:
        environment["GF_SECURITY_ADMIN_PASSWORD__FILE"] = str(tmp_path / "password")
        if password_file is not None:
            (tmp_path / "password").write_text(password_file)
    else:
        environment["GF_SECURITY_ADMIN_PASSWORD"] = env_password
    done = subprocess.run(
        ["/bin/bash", str(ROOT / "images" / "grafana" / "start.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if refused:
        assert done.returncode == 1
        assert "no Grafana admin password" in done.stderr
    else:
        assert "/run.sh" in done.stderr  # reached `exec /run.sh`, which only the image has
        assert "no Grafana admin password" not in done.stderr


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


def redaction_patterns() -> list[str]:
    """The agent's stage.replace expressions, unescaped from Alloy strings."""
    config = (ROOT / "agent" / "config.alloy").read_text()
    return [json.loads(m) for m in re.findall(r'stage\.replace \{\s*expression = ("(?:[^"\\]|\\.)*")', config)]


def test_agent_redacts_credentials_in_urls_of_every_log_pipeline() -> None:
    """Every log pipeline (containers, NPM, deploys) carries the same redaction (secrets reached Loki, 2026-10-11)."""
    patterns = redaction_patterns()
    assert len(patterns) == 3
    assert len(set(patterns)) == 1


@pytest.mark.parametrize(
    ("line", "redacted"),
    [
        (
            'GET "/api/v3/queue?page=1&apikey=0123abcd&sortKey=time" [Client',
            'GET "/api/v3/queue?page=1&apikey=REDACTED&sortKey=time" [Client',
        ),
        (
            '"/signalr/messages/negotiate?access_token=f2d9&negotiateVersion=1"',
            '"/signalr/messages/negotiate?access_token=REDACTED&negotiateVersion=1"',
        ),
        (
            "/library/sections?X-Plex-Token=AbCd&X-Plex-Product=Plexamp",
            "/library/sections?X-Plex-Token=REDACTED&X-Plex-Product=Plexamp",
        ),
        (
            "http://sab:8080/api?mode=queue&api_key=dead output",
            "http://sab:8080/api?mode=queue&api_key=REDACTED output",
        ),
        ("/s3/obj?X-Amz-Date=1&Signature=abc%2Fdef", "/s3/obj?X-Amz-Date=1&Signature=REDACTED"),
        ("/login?token=t1;password=p2", "/login?token=REDACTED;password=REDACTED"),
        ('/search?q=hello&page=2 "curl"', '/search?q=hello&page=2 "curl"'),  # nothing secret: unchanged
        ("/keys?monkey=1&keyboard=2", "/keys?monkey=1&keyboard=2"),  # only whole parameter names
    ],
)
def test_redaction_replaces_only_the_secret_values(line: str, redacted: str) -> None:
    pattern = re.compile(redaction_patterns()[0])

    def replace(match: re.Match[str]) -> str:
        start, end = match.span(1)
        return match.group(0)[: start - match.start()] + "REDACTED" + match.group(0)[end - match.start() :]

    assert pattern.sub(replace, line) == redacted


EXPORTARR_APPS = ["radarr", "radarr4k", "sonarr", "sonarr4k", "lidarr", "bazarr", "prowlarr", "sabnzbd"]


def test_exporter_credentials_are_mounted_files_not_environment() -> None:
    """Credentials reach exporters as files under /run/secrets, so `docker inspect` doesn't show them."""
    compose = load("docker-compose.yml")
    services = compose["services"]
    for app in EXPORTARR_APPS:
        assert services[f"exportarr-{app}"]["secrets"] == [{"source": f"{app}_api_key", "target": "api_key"}]
        assert services[f"exportarr-{app}"]["environment"]["API_KEY_FILE"] == "/run/secrets/api_key"
    assert services["unpoller"]["secrets"] == ["unifi_password"]
    assert services["unpoller"]["environment"]["UP_UNIFI_DEFAULT_PASS"] == "file:///run/secrets/unifi_password"  # noqa: S105 - a path
    assert services["qbittorrent-exporter"]["secrets"] == ["qbittorrent_password"]
    qbittorrent = services["qbittorrent-exporter"]["environment"]
    assert qbittorrent["QBITTORRENT_PASSWORD_FILE"] == "/run/secrets/qbittorrent_password"  # noqa: S105 - a path
    assert "env_file" not in services["gitlab-ci-pipelines-exporter"]  # its token is in the mounted config file
    assert services["pve-exporter"]["secrets"] == ["pve.yml"]
    assert services["pve-exporter"]["command"] == ["--config.file=/run/secrets/pve.yml"]
    assert "environment" not in services["pve-exporter"]
    assert "env_file" not in services["pve-exporter"]


def deploy_line_pattern() -> re.Pattern[str]:
    """The deploys.log pipeline's stage.regex expression, unescaped from its Alloy string."""
    config = (ROOT / "agent" / "config.alloy").read_text()
    block = config[config.index('loki.process "homelab_pull"') :]
    expression = re.search(r'stage\.regex \{\s*expression = ("(?:[^"\\]|\\.)*")', block)
    assert expression
    return re.compile(json.loads(expression[1]))


def test_agent_reads_homelab_pull_state_read_only() -> None:
    """deploys.log and the metrics (textfile collector) come from read-only mounts of its state directory; the
    metrics directory has its own, so it exists (empty) without homelab-pull: a missing one errors every scrape."""
    config = (ROOT / "agent" / "config.alloy").read_text()
    volumes = service("agent/compose.yml", "agent")["volumes"]
    assert "${HOMELAB_PULL_DIR:-./no-homelab-pull}:/var/lib/homelab-pull:ro" in volumes
    assert "${HOMELAB_PULL_DIR:-./no-homelab-pull}/metrics:/var/lib/homelab-pull-metrics:ro" in volumes
    assert 'directory = "/var/lib/homelab-pull-metrics"' in config
    assert '"__path__" = "/var/lib/homelab-pull/*/deploys.log"' in config


@pytest.mark.parametrize(
    ("line", "labels"),
    [
        ("2026-10-14T13:56:52-0500 media ok 0123456789ab -> 89abcdef0123 Bump x (#2)", ("media", "ok")),
        (
            "2026-10-14T18:56:52+0000 home-2 failed:recreate 0123456789ab -> 89abcdef0123 Kometa [recreated: k]",
            ("home-2", "failed:recreate"),
        ),
        ("2026-10-14T13:56:52-0500 media maybe 0123 -> 89ab x", None),  # an unknown result gets no labels
    ],
)
def test_deploy_lines_get_stack_and_result_labels(line: str, labels: tuple[str, str] | None) -> None:
    match = deploy_line_pattern().match(line)
    assert (match["stack"], match["result"]) == labels if labels else match is None


def test_gpu_job_keeps_every_metric_the_dashboard_and_alerts_use() -> None:
    """The gpu job keeps ~10 of the exporter's ~150 series per GPU; a query on a dropped one would read nothing."""
    job = next(j for j in load("prometheus/prometheus.yml")["scrape_configs"] if j["job_name"] == "gpu")
    keep = re.compile(job["metric_relabel_configs"][0]["regex"])
    used = set()
    for path in ["dashboards/hosts/gpus.json", "provisioning/alerting/rules.yaml"]:
        used |= set(re.findall(r"nvidia_smi_[a-z_]+", (ROOT / path).read_text()))
    assert used
    assert not [name for name in sorted(used) if not keep.fullmatch(name)]


def autoheal_poll_pattern() -> re.Pattern[str]:
    """The container pipeline's stage.drop expression for autoheal's polling, unescaped from its Alloy string."""
    config = (ROOT / "agent" / "config.alloy").read_text()
    drop = re.search(r'expression\s*= ("(?:[^"\\]|\\.)*")\s*drop_counter_reason = "autoheal_poll"', config)
    assert drop
    return re.compile(json.loads(drop[1]))


PROXY = (
    "::ffff:192.0.2.3:49160 [14/Oct/2026:20:23:01.425] proxy docker/socket 0/0/0/2/2 {status} 190 - - ---- "
    "1/1/0/0/0 0/0 "
)
AUTOHEAL_POLL = (
    '"GET /containers/json?filters={#22health#22:[#22unhealthy#22],#22label#22:[#22autoheal=true#22]} HTTP/1.1"'
)


@pytest.mark.parametrize(
    ("request_line", "status", "dropped"),
    [
        (AUTOHEAL_POLL, 200, True),
        ('"GET /_ping HTTP/1.1"', 200, True),
        (AUTOHEAL_POLL, 403, False),  # refused: kept
        ('"POST /containers/abc/restart HTTP/1.1"', 204, False),  # autoheal restarting something: kept
        ('"GET /containers/abc/json HTTP/1.1"', 200, False),
    ],
)
def test_agent_drops_only_autoheals_answered_polls(request_line: str, status: int, *, dropped: bool) -> None:
    """Real socket-proxy (HAProxy) lines: ~8.5k a day per host were autoheal's health checks."""
    line = PROXY.format(status=status) + request_line
    assert bool(autoheal_poll_pattern().search(line)) == dropped


def test_snmp_exporter_loads_the_ssd_cache_module() -> None:
    """The module file is mounted and passed as a --config.file; its walk covers every metric it defines."""
    exporter = load("docker-compose.yml")["services"]["snmp-exporter"]
    target = "/etc/snmp_exporter/synology-flashcache.yml"
    assert f"./snmp/synology-flashcache.yml:{target}:ro" in exporter["volumes"]
    assert f"--config.file={target}" in exporter["command"]
    module = load("snmp/synology-flashcache.yml")["modules"]["synology_flashcache"]
    assert module["walk"] == ["1.3.6.1.4.1.6574.103.1.1"]
    assert all(m["oid"].startswith(module["walk"][0] + ".") for m in module["metrics"])
    modules = [t["labels"]["module"].split(",") for t in json.loads((ROOT / "targets.example/snmp.json").read_text())]
    assert all("synology_flashcache" in m for m in modules if "synology" in m)


def test_tdarr_exporter_reads_its_settings_only_from_its_env_file() -> None:
    """Its image reads the API key only from the environment, so the key stays in secrets/tdarr.env."""
    tdarr = load("docker-compose.yml")["services"]["tdarr-exporter"]
    assert tdarr["env_file"] == [{"path": "./secrets/tdarr.env", "required": False}]
    assert tdarr["environment"] == {"INSTANCE_NAME": "tdarr"}
    assert "secrets" not in tdarr


def test_varken_reads_keys_from_secret_files_and_runs_tautulli_sonarr_and_radarr() -> None:
    varken = load("docker-compose.yml")["services"]["varken"]
    env = varken["environment"]
    assert varken["secrets"] == [
        "tautulli_api_key",
        "sonarr_api_key",
        "sonarr4k_api_key",
        "radarr_api_key",
        "radarr4k_api_key",
        "lidarr_api_key",
        "seerr_api_key",
        "maxmind_license_key",
    ]
    assert env["VRKN_TAUTULLI_1_APIKEY_FILE"] == "/run/secrets/tautulli_api_key"
    # Server 1 is the app, 2 its 4K instance; the keys are exportarr's secrets.
    for app in ("sonarr", "radarr"):
        assert env[f"VRKN_GLOBAL_{app.upper()}_SERVER_IDS"] == "1,2"
        assert env[f"VRKN_{app.upper()}_1_APIKEY_FILE"] == f"/run/secrets/{app}_api_key"
        assert env[f"VRKN_{app.upper()}_2_APIKEY_FILE"] == f"/run/secrets/{app}4k_api_key"
    assert varken["env_file"] == [{"path": "./secrets/varken.env", "required": False}]
    # GeoIP: the MaxMind license key is a secret file too; the account ID is in secrets/varken.env.
    assert env["VRKN_GLOBAL_MAXMIND_LICENSE_KEY_FILE"] == "/run/secrets/maxmind_license_key"
    # The URL comes from secrets/varken.env; no key or password in the compose file or the template.
    assert not any(name.endswith(("_APIKEY", "_PASSWORD", "_LICENSE_KEY")) for name in env)
    assert env["VRKN_GLOBAL_TAUTULLI_SERVER_IDS"] == "1"
    assert env["VRKN_GLOBAL_SEERR_SERVER_IDS"] == "1"
    assert env["VRKN_SEERR_1_APIKEY_FILE"] == "/run/secrets/seerr_api_key"
    assert env["VRKN_GLOBAL_LIDARR_SERVER_IDS"] == "1"
    assert env["VRKN_LIDARR_1_APIKEY_FILE"] == "/run/secrets/lidarr_api_key"
    others = ("OMBI", "SICKCHILL", "UNIFI")
    assert all(env[f"VRKN_GLOBAL_{app}_SERVER_IDS"] == "false" for app in others)
    assert env["LOG_TO_FILE"] == "false"
    # The homelab standard: data in CONFIG_ROOT/<service>/config, never a named volume.
    assert varken["volumes"] == ["${CONFIG_ROOT:?set CONFIG_ROOT in .env}/varken/config:/config"]


def test_every_secret_is_a_file_in_secrets_with_a_template() -> None:
    for name, secret in load("docker-compose.yml")["secrets"].items():
        assert secret == {"file": f"./secrets/{name}"}
        assert (ROOT / "secrets.example" / name).is_file(), f"secrets.example/{name} is missing"


def test_example_env_files_hold_no_credentials() -> None:
    """Passwords, API keys and tokens moved to their own files; the env files keep URLs and user names."""
    for env in sorted((ROOT / "secrets.example").glob("*.env")):
        if env.name == "pihole-exporter.env":  # pihole-exporter reads its passwords only from the environment
            continue
        keys = re.findall(r"^([A-Z0-9_]+)=", env.read_text(), re.MULTILINE)
        assert not [k for k in keys if re.search(r"PASS|API_KEY|TOKEN|SECRET", k)], env.name


def test_pve_exporter_verifies_tls_against_the_cluster_ca() -> None:
    """The template points verify_ssl at the mounted CA certificate instead of turning verification off."""
    module = load("secrets.example/pve.yml")["default"]
    assert module["verify_ssl"] == "/etc/pve-exporter/pve-ca.pem"
    volumes = load("docker-compose.yml")["services"]["pve-exporter"]["volumes"]
    assert {"source": "./secrets/pve-ca.pem", "target": "/etc/pve-exporter/pve-ca.pem"}.items() <= volumes[0].items()


def test_pve_job_asks_the_exporter_about_each_target() -> None:
    """Multi-target exporter: the node's address goes in ?target=, the scrape goes to pve-exporter."""
    job = next(j for j in load("prometheus/prometheus.yml")["scrape_configs"] if j["job_name"] == "pve")
    assert job["metrics_path"] == "/pve"
    assert job["params"] == {"module": ["default"], "cluster": ["1"], "node": ["1"]}
    rules = job["relabel_configs"]
    assert {"source_labels": ["__address__"], "target_label": "__param_target"} in rules
    assert {"target_label": "__address__", "replacement": "pve-exporter:9221"} in rules
    # A target labelled cluster: "0" skips the cluster-wide collectors (one node per cluster reports guests).
    assert {"source_labels": ["cluster"], "regex": "(.+)", "target_label": "__param_cluster"} in rules


def test_pve_quorum_job_asks_every_node_for_its_own_view() -> None:
    """The quorum alerts can't depend on the one node the pve job reads the cluster from."""
    jobs = {j["job_name"]: j for j in load("prometheus/prometheus.yml")["scrape_configs"]}
    job = jobs["pve_quorum"]
    assert job["file_sd_configs"] == jobs["pve"]["file_sd_configs"]
    assert job["params"] == {"module": ["default"], "cluster": ["1"], "node": ["0"]}
    # Every target asks for the cluster view: the targets' cluster label is dropped, not passed on.
    assert not [r for r in job["relabel_configs"] if r.get("target_label") == "__param_cluster"]
    assert {"regex": "cluster", "action": "labeldrop"} in job["relabel_configs"]
    assert job["metric_relabel_configs"] == [
        {"source_labels": ["__name__", "id"], "regex": "pve_up;cluster/.+|pve_qdevice_up;.*", "action": "keep"}
    ]
    # Regression test: the pve job kept its own copy of the cluster's pve_up, and the dashboard's joins
    # on (instance, id) failed with "found duplicate series for the match group".
    drop = {"source_labels": ["__name__", "id"], "regex": "pve_up;cluster/.+|pve_qdevice_.+;.*", "action": "drop"}
    assert drop in jobs["pve"]["metric_relabel_configs"]


def test_ipmi_job_scrapes_with_basic_auth_from_a_secret_file() -> None:
    """The IPMI exporter runs on each server and asks for basic auth; the password is a file in secrets/."""
    job = next(j for j in load("prometheus/prometheus.yml")["scrape_configs"] if j["job_name"] == "ipmi")
    assert job["basic_auth"] == {"username": "argus", "password_file": "/etc/prometheus/secrets/ipmi_password"}
    assert (ROOT / "secrets.example" / "ipmi_password").is_file()
    assert job["file_sd_configs"] == [{"files": ["/etc/prometheus/targets/ipmi.json"]}]
    targets = json.loads((ROOT / "targets.example" / "ipmi.json").read_text())
    assert targets
    assert all(t["labels"]["host"] for t in targets), "the dashboard and alerts name servers by their host label"
    # The BMC's own address (bmc_url on ipmi_bmc_info) never reaches Prometheus.
    assert {"regex": "bmc_url", "action": "labeldrop"} in job["metric_relabel_configs"]


def test_ipmi_dashboard_lists_the_sensors_the_alerts_watch() -> None:
    """Empty slots (Entity Presence) and Supermicro's PatternN LED sensors sit at state 2 without being faults.

    The alerts leave them out; the dashboard's counts and table use the same selector, so what it shows as not
    OK is exactly what alerts.
    """
    rules = {r["uid"]: r for g in load("provisioning/alerting/rules.yaml")["groups"] for r in g["rules"]}
    selector_re = re.compile(r'\{__name__=~"ipmi_\(sensor[^}]*\}')
    critical = selector_re.findall(rules["argus-ipmi-sensor-critical"]["data"][0]["model"]["expr"])
    warning = selector_re.findall(rules["argus-ipmi-sensor-warning"]["data"][0]["model"]["expr"])
    assert len(critical) == 1
    assert 'type!="Entity Presence"' in critical[0]
    assert 'name!~"Pattern[0-9]+"' in critical[0]
    assert warning == critical
    # The dashboard adds only its host filter.
    exprs = [
        t["expr"]
        for p in json.loads((ROOT / "dashboards/proxmox/hardware.json").read_text())["panels"]
        for t in p.get("targets", [])
    ]
    used = {s.replace('host=~"$host", ', "") for e in exprs for s in selector_re.findall(e)}
    assert used == set(critical)


def test_hwmon_job_scrapes_with_basic_auth_from_a_secret_file() -> None:
    """node_exporter on servers without the agent asks for basic auth; the password is a file in secrets/."""
    job = next(j for j in load("prometheus/prometheus.yml")["scrape_configs"] if j["job_name"] == "hwmon")
    assert job["basic_auth"] == {"username": "argus", "password_file": "/etc/prometheus/secrets/hwmon_password"}
    assert (ROOT / "secrets.example" / "hwmon_password").is_file()
    assert job["file_sd_configs"] == [{"files": ["/etc/prometheus/targets/hwmon.json"]}]
    targets = json.loads((ROOT / "targets.example" / "hwmon.json").read_text())
    assert targets
    assert all(t["labels"]["host"] for t in targets), "the dashboard and the alert name servers by their host label"


def test_hwmon_setup_runs_only_the_hwmon_collector_on_one_address_behind_auth() -> None:
    """The exporter runs on a hypervisor: nothing but hardware sensors, on the address given, with a password."""
    script = (ROOT / "deploy" / "hwmon" / "setup-node-exporter.sh").read_text()
    args = " ".join(re.findall(r'^ARGS="(?:\$ARGS )?([^"]*)"$', script, re.MULTILINE)).split()
    collectors = [a for a in args if a.startswith("--collector.")]
    assert collectors == ["--collector.disable-defaults", "--collector.hwmon"]
    assert "--web.listen-address=${LISTEN_IP}:9100" in args
    assert "--web.config.file=/etc/prometheus/node_exporter_web.yml" in args
    # Debian's Recommends (prometheus-node-exporter-collectors) runs timers as root.
    assert "--no-install-recommends prometheus-node-exporter" in script


def test_gpu_panels_and_the_gpu_hot_alert_pick_the_same_hwmon_chips() -> None:
    """Server Hardware's GPU panels show exactly the cards the GPU hot alert watches: Intel's i915 and xe drivers."""
    rules = {r["uid"]: r for g in load("provisioning/alerting/rules.yaml")["groups"] for r in g["rules"]}
    chips_re = re.compile(r"node_hwmon_chip_names\{([^}]*)\}")
    alert = chips_re.findall(rules["argus-gpu-hot"]["data"][0]["model"]["expr"])
    assert alert == ['chip_name=~"i915|xe"']
    panels = json.loads((ROOT / "dashboards/proxmox/hardware.json").read_text())["panels"]
    gpu_panels = [p for p in panels if "GPU" in p["title"]]
    assert [p["title"] for p in gpu_panels] == ["Hottest GPU", "GPU temperature", "GPU fan speed"]
    for panel in gpu_panels:
        used = chips_re.findall(panel["targets"][0]["expr"])
        assert [s.replace(', host=~"$host"', "") for s in used] == alert, panel["title"]


def test_secrets_mounts_never_create_the_host_path() -> None:
    """Regression test: a missing secrets/ file must stop the service, not become an empty root-owned directory.

    With the short syntax, Docker creates a bind mount's missing source as a directory; that happened to
    secrets/pve-ca.pem on a server, and the exporter ran without its CA certificate.
    """
    services = load("docker-compose.yml")["services"]
    mounts = 0
    for name, service in services.items():
        for volume in service.get("volumes", []):
            if isinstance(volume, str):
                assert not volume.startswith("./secrets"), f"{name}: use the long syntax for {volume}"
            elif volume["source"].startswith("./secrets"):
                mounts += 1
                assert volume["type"] == "bind"
                assert volume["read_only"] is True, f"{name}: {volume['source']} must be read-only"
                assert volume["bind"] == {"create_host_path": False}, f"{name}: {volume['source']}"
    assert mounts == 5  # Prometheus' directory, Grafana's password, 3 exporter files


# Every compose file a user runs; each of their services gets the hardening in docs/security.md#hardening.
COMPOSE_FILES = ["docker-compose.yml", "logs/compose.yml", "agent/compose.yml"]
# Docker's default capability set: a service may add back one of these, never one beyond it.
DOCKER_DEFAULT_CAPABILITIES = {
    "AUDIT_WRITE",
    "CHOWN",
    "DAC_OVERRIDE",
    "FOWNER",
    "FSETID",
    "KILL",
    "MKNOD",
    "NET_BIND_SERVICE",
    "NET_RAW",
    "SETFCAP",
    "SETGID",
    "SETPCAP",
    "SETUID",
    "SYS_CHROOT",
}
SERVICES = [(path, name) for path in COMPOSE_FILES for name in load(path)["services"]]


def service(path: str, name: str) -> dict:
    return load(path)["services"][name]


@pytest.mark.parametrize(("path", "name"), SERVICES)
def test_every_service_drops_all_capabilities_and_cannot_gain_privileges(path: str, name: str) -> None:
    config = service(path, name)
    assert "no-new-privileges:true" in config.get("security_opt", []), f"{path}: {name}"
    assert config.get("cap_drop") == ["ALL"], f"{path}: {name}"
    assert not config.get("privileged"), f"{path}: {name}"
    added = {c.upper().removeprefix("CAP_") for c in config.get("cap_add", [])}
    assert added <= DOCKER_DEFAULT_CAPABILITIES, f"{path}: {name} adds {sorted(added - DOCKER_DEFAULT_CAPABILITIES)}"


@pytest.mark.parametrize(("path", "name"), SERVICES)
def test_every_service_has_a_read_only_root_filesystem(path: str, name: str) -> None:
    """They write only to their volumes and tmpfs mounts."""
    assert service(path, name).get("read_only") is True, f"{path}: {name}"


def test_only_the_agent_gets_a_capability_back() -> None:
    """Adding one is a decision: document it in docs/security.md#hardening and list it here."""
    configs = {(path, name): service(path, name) for path, name in SERVICES}
    added = {key: config["cap_add"] for key, config in configs.items() if "cap_add" in config}
    assert added == {("agent/compose.yml", "agent"): ["DAC_OVERRIDE"]}


def test_only_the_agent_shares_the_hosts_namespaces_or_docker() -> None:
    """The agent's exceptions (docs/security.md#hardening); no other service gets any of them."""
    for path, name in SERVICES:
        config = service(path, name)
        mounts = [v for v in config.get("volumes", []) if isinstance(v, str)]
        host_access = {
            "network": config.get("network_mode") == "host",
            "pid": config.get("pid") == "host",
            "docker": any(m.startswith("/var/run/docker.sock:") for m in mounts),
        }
        if (path, name) == ("agent/compose.yml", "agent"):
            assert host_access == {"network": True, "pid": True, "docker": True}
            host_mounts = [m for m in mounts if m.startswith("/")]
            assert all(m.split(":")[2].startswith("ro") for m in host_mounts), "the agent mounts the host read-only"
        else:
            assert not any(host_access.values()), f"{path}: {name}: {host_access}"


def test_images_that_default_to_root_run_as_nobody() -> None:
    """They only read their settings and secrets, so they don't need root (or any capability)."""
    services = load("docker-compose.yml")["services"]
    for name in ["pihole-exporter", "unpoller", "snmp-exporter", "qbittorrent-exporter"]:
        assert services[name]["user"] == "65534:65534", name
    assert service("agent/compose.yml", "plex-exporter")["user"] == "65534:65534"
