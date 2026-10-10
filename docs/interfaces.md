# Interfaces

Every interface the released Argus images and compose files expose or depend on: what listens where,
what it accepts, and how it's configured. The trust placed in each is described in
[assurance-case.md](assurance-case.md#2-trust-boundaries).

## Network endpoints

| Endpoint | Where | Protocol and authentication | Used by |
| --- | --- | --- | --- |
| Grafana | server, `GRAFANA_BIND` (default `0.0.0.0:3000`); with `docker-compose.proxy.yml` also `argus-grafana:3000` on the proxy's Docker network (`ARGUS_PROXY_NETWORK`) | HTTP; Grafana login (sign-up and anonymous access off). Put a reverse proxy with TLS in front if it's reachable beyond your own network; with the proxy on the same host, `docker-compose.proxy.yml` and `GRAFANA_BIND=127.0.0.1:3000` leave the proxy as the only way in. | people (UI), Grafana's HTTP API |
| Prometheus | server, `PROMETHEUS_BIND` (default `0.0.0.0:9090`) | HTTP: the remote-write receiver (`/api/v1/write`) and the query API. **No authentication** until `secrets/prometheus-web.yml` lists a user; then basic auth as `argus` with `secrets/prometheus_password` on every path ([security.md](security.md#requiring-a-password-for-prometheus)) | agents (push), Grafana, you |
| Loki | server (`loki` profile, `LOKI_BIND`, default `0.0.0.0:3101`) or `logs/compose.yml` (`:3101`) | HTTP, **no authentication**: push (`/loki/api/v1/push`) and query APIs | agents (push), Grafana |
| blackbox_exporter, the exporters | server, compose network only (not published) | HTTP `/metrics` or `/probe` | Prometheus |
| Plex exporter | the Plex host, `:9594` (`plex` profile of `agent/compose.yml`) | HTTP `/metrics`, no authentication | Prometheus (`targets/plex.json`) |
| Agent | each host; Alloy's own UI on `127.0.0.1:12345` only | — (the agent accepts no connections from other machines) | — |

Outbound connections:

| From | To | What |
| --- | --- | --- |
| Agent | `ARGUS_PROMETHEUS_URL`, `ARGUS_LOKI_URL` | metrics (Prometheus remote write) and logs (Loki push) |
| Prometheus | everything in `targets/*.json` | scrapes (HTTP, or HTTPS where a target uses it) |
| blackbox_exporter | URLs in `targets/blackbox_http.json`, DNS servers in `targets/blackbox_dns.json` | HTTP(S) probes with certificate verification; DNS queries (UDP) |
| Exporters | the service each one watches (from `secrets/<name>.env`) | the service's API (Pi-hole, UniFi, SNMPv3, *arr, qBittorrent, Plex) |
| Grafana | Prometheus, Loki (`LOKI_URL`), `DISCORD_WEBHOOK_URL` | queries; alert notifications (HTTPS). It downloads no plugins: `GF_PLUGINS_PREINSTALL_DISABLED=true` |
| Auto-deploy (optional, [auto-deploy.md](auto-deploy.md)) | GitHub (`git fetch`, the public API), `DISCORD_WEBHOOK_URL` | the new commit and its check result (HTTPS, no token); deploy and rollback notices |

## Configuration

**Server `.env`** (template: [`.env.example`](../.env.example)): `GF_SECURITY_ADMIN_USER`,
`GF_SECURITY_ADMIN_PASSWORD` (required), `GRAFANA_ROOT_URL`, `ARGUS_VERSION`, `ARGUS_REGISTRY`,
`COMPOSE_FILE` (source mode, proxy network), `ARGUS_PROXY_NETWORK`, `GRAFANA_BIND`, `PROMETHEUS_BIND`, `LOKI_BIND`,
`PROMETHEUS_RETENTION_TIME`, `PROMETHEUS_RETENTION_SIZE`, `COMPOSE_PROFILES` (`loki`, `snmp`, one per
media app), `DISCORD_WEBHOOK_URL`, `UNIFI_VERIFY_SSL`, `LOKI_URL`.

**Agent** (environment, or `agent/.env` from [`agent/.env.example`](../agent/.env.example)):
`ARGUS_HOST` (the `host` label), `ARGUS_PROMETHEUS_URL`, `ARGUS_LOKI_URL` (all required);
`ARGUS_PROMETHEUS_PASSWORD` (Prometheus' password, if it requires one); `NPM_LOG_DIR`; `COMPOSE_PROFILES=plex` with `PLEX_SERVER` and `PLEX_TOKEN`; `ARGUS_AGENT_IMAGE`. Host
mounts (all read-only): `/` as `/rootfs`, `/sys`, `/run/udev`, `/dev/disk`, `/var/lib/docker`, the Docker
socket, and `NPM_LOG_DIR`. It needs the host's PID and network namespaces and `--privileged`.

**Targets** (`targets/<job>.json`, Prometheus
[file service discovery](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#file_sd_config)
format; placeholders in [`targets.example/`](../targets.example/)): a list of
`{"targets": [...], "labels": {...}}`. Labels the dashboards use: `service` and `group` (blackbox),
`host`, `module` and `auth` (SNMP), `app` (media). Prometheus reloads these files without a restart.

**Credentials** (`secrets/`, placeholders in [`secrets.example/`](../secrets.example/)), mounted
read-only: env files for the exporters (`pihole-exporter.env`, `unpoller.env`, `<app>.env`, `vsphere.env`), vCenter's CA
certificate for Telegraf (`vsphere-ca.pem`), files
Prometheus reads (`home_assistant_token`, `uptime_kuma_api_key`, `peanut_username` and `peanut_password`), and
`snmp-auth.yml`.

## Data contracts

- **Datasource uids** `prometheus` and `loki` ([`provisioning/datasources/argus.yaml`](../provisioning/datasources/argus.yaml))
  and **dashboard uids** (`argus-*`) are stable: links and bookmarks to them survive upgrades.
- **Labels**: host series carry `host` (= `ARGUS_HOST`) and `instance`; container series `host`, `name`;
  logs `host`, `container`, `compose_project`, `job` (`docker` or `npm`), and for NPM `site`, `status`,
  `method`.
- **Alert notifications** are Grafana's Discord message format; each rule has a stable `uid`
  (`argus-*`), a `severity` label and a one-line summary.

## Release artifacts

| Artifact | Where | Notes |
| --- | --- | --- |
| Images `argus-grafana`, `argus-prometheus`, `argus-blackbox`, `argus-loki`, `argus-agent` | `ghcr.io/honeybeartech/…`, `docker.io/honeybeartech/…` | linux/amd64 and linux/arm64; tags `X.Y.Z`, `X.Y`, `latest`; cosign signature, SBOM and SLSA provenance on each |
| Source archive, `images.txt` (digests), `SHA256SUMS` (signed), build provenance | the [GitHub Release](https://github.com/HoneyBearTech/Argus/releases) | see [verifying-releases.md](verifying-releases.md) |

Paths inside the images: Grafana provisioning in `/etc/grafana/provisioning`, dashboards in
`/etc/argus/dashboards`; `/etc/prometheus/prometheus.yml`; `/etc/blackbox/blackbox.yml`;
`/etc/loki/loki.yaml`; `/etc/alloy/config.alloy`. Data volumes: `grafana_data`, `prometheus_data`,
`loki_data`, `agent_data`.

A change to any interface above is listed in [CHANGELOG.md](../CHANGELOG.md), under "Upgrading" when you
need to act.
