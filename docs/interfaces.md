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
| GPU exporter | a host with an NVIDIA GPU, `:9835` (`gpu` profile of `agent/compose.yml`) | HTTP `/metrics`, no authentication | Prometheus (`targets/gpu.json`) |
| IPMI exporter | each server whose hardware Argus reads, `<server address>:9290` (Debian's `prometheus-ipmi-exporter`, [`deploy/ipmi/`](../deploy/ipmi/)) | HTTP `/metrics`, basic auth (user `argus`, `secrets/ipmi_password`) | Prometheus (`targets/ipmi.json`) |
| node_exporter (hwmon only) | a server without the agent whose add-in GPU Argus reads, `<server address>:9100` (Debian's `prometheus-node-exporter`, [`deploy/hwmon/`](../deploy/hwmon/)) | HTTP `/metrics`, basic auth (user `argus`, `secrets/hwmon_password`) | Prometheus (`targets/hwmon.json`) |
| Intel GPU exporter | a server whose i915 driver has an Intel GPU, `<server address>:9836` ([`deploy/intelgpu/`](../deploy/intelgpu/)), or a host with the agent's `intel-gpu` profile, `:9836` | HTTP `/metrics`, basic auth (user `argus`, `secrets/intel_gpu_password`; the server or agent keeps only its bcrypt hash) | Prometheus (`targets/intel_gpu.json`) |
| Agent | each host; Alloy's own UI on `127.0.0.1:12345` only | — (the agent accepts no connections from other machines) | — |

Outbound connections:

| From | To | What |
| --- | --- | --- |
| Agent | `ARGUS_PROMETHEUS_URL`, `ARGUS_LOKI_URL` | metrics (Prometheus remote write) and logs (Loki push) |
| Prometheus | everything in `targets/*.json` | scrapes (HTTP, or HTTPS where a target uses it) |
| blackbox_exporter | URLs in `targets/blackbox_http.json`, DNS servers in `targets/blackbox_dns.json` | HTTP(S) probes with certificate verification; DNS queries (UDP) |
| Exporters | the service each one watches (from `secrets/<name>.env` and the credential files) | the service's API (Pi-hole, UniFi, SNMPv3, *arr, qBittorrent, Tdarr, Tautulli, Plex) |
| Grafana | Prometheus, Loki (`LOKI_URL`), Steerhouse's PostgreSQL (`STEERHOUSE_DB_ADDRESS`), the Discord webhook (`secrets/discord_webhook_url`) | queries (PostgreSQL over TLS, the server verified against `secrets/steerhouse_db_ca`); alert notifications (HTTPS). It downloads no plugins: `GF_PLUGINS_PREINSTALL_DISABLED=true` |
| Auto-deploy (optional, [auto-deploy.md](auto-deploy.md)) | GitHub (`git fetch`, the public API), the Discord webhook (`secrets/discord_webhook_url`, else `DISCORD_WEBHOOK_URL` in `.env`) | the new commit and its check result (HTTPS, no token); deploy and rollback notices |

## Configuration

**Server `.env`** (template: [`.env.example`](../.env.example)): `GF_SECURITY_ADMIN_USER`,
`GRAFANA_ROOT_URL`, `ARGUS_VERSION`, `ARGUS_REGISTRY`,
`COMPOSE_FILE` (source mode, proxy network), `ARGUS_PROXY_NETWORK`, `GRAFANA_BIND`, `PROMETHEUS_BIND`, `LOKI_BIND`,
`PROMETHEUS_RETENTION_TIME`, `PROMETHEUS_RETENTION_SIZE`, `COMPOSE_PROFILES` (`loki`, `snmp`, one per
media app), `UNIFI_VERIFY_SSL`, `LOKI_URL`, `STEERHOUSE_DB_ADDRESS` (Steerhouse's PostgreSQL, `host:port`).
Grafana's admin password and the Discord webhook are files in
`secrets/` (below); `GF_SECURITY_ADMIN_PASSWORD` and `DISCORD_WEBHOOK_URL` in `.env` are no longer passed to
Grafana (auto-deploy still falls back to `DISCORD_WEBHOOK_URL`).

**Agent** (environment, or `agent/.env` from [`agent/.env.example`](../agent/.env.example)):
`ARGUS_HOST` (the `host` label), `ARGUS_PROMETHEUS_URL`, `ARGUS_LOKI_URL` (all required);
`ARGUS_PROMETHEUS_PASSWORD` (Prometheus' password, if it requires one); `NPM_LOG_DIR`; `HOMELAB_PULL_DIR`; `COMPOSE_PROFILES=plex` with `PLEX_SERVER` and `PLEX_TOKEN`, and/or `gpu`, and/or `intel-gpu` with `ARGUS_INTEL_GPU_PASSWORD_HASH` (and optionally `ARGUS_INTEL_GPU_EXPORTER_IMAGE`); `ARGUS_AGENT_IMAGE`. Host
mounts (all read-only): `/` as `/rootfs`, `/sys`, `/run/udev`, `/dev/disk`, `/var/lib/docker`, the Docker
socket, the containerd socket, `NPM_LOG_DIR` and `HOMELAB_PULL_DIR`; its own data is in a volume at `/var/lib/alloy/data`. It needs
the host's PID and network namespaces and the `DAC_OVERRIDE` capability, not `--privileged`
([security.md](security.md#hardening)).

**Targets** (`targets/<job>.json`, Prometheus
[file service discovery](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#file_sd_config)
format; placeholders in [`targets.example/`](../targets.example/)): a list of
`{"targets": [...], "labels": {...}}`. Labels the dashboards use: `service` and `group` (blackbox),
`host`, `module` and `auth` (SNMP), `app` (media), `host` (GPUs, IPMI). Prometheus reloads these files without a restart.

**Credentials** (`secrets/`, placeholders in [`secrets.example/`](../secrets.example/)), mounted
read-only, so the containers' users must be able to read them (mode 644; the env files, which only the compose
command reads, can stay 600): Grafana's admin password (`grafana_admin_password`, required) and the Discord
webhook (`discord_webhook_url`), both mounted under `/run/secrets/`, like the password of Steerhouse's
`grafana_ro` database role (`steerhouse_db_password`) and the CA certificate its PostgreSQL's TLS certificate is
checked against (`steerhouse_db_ca`), which Grafana needs to start (the templates will do where Steerhouse isn't
watched); env files with the exporters' URLs and user names (`pihole-exporter.env`, which also holds
the Pi-hole passwords, `unpoller.env`, `<app>.env`, `qbittorrent.env`, `tdarr.env`, which also holds Tdarr's API key once Tdarr's
own login is on, and `varken.env`, Tautulli's address); the exporters' passwords and API
keys as files mounted under `/run/secrets/` (`unifi_password`, `<app>_api_key`, `qbittorrent_password`,
`tautulli_api_key`);
`gitlab.yml` (GitLab, its token and what to watch); `pve.yml` (the Proxmox VE API token, mounted under
`/run/secrets/`); the CA certificate of Proxmox VE (`pve-ca.pem`); files Prometheus reads
(`home_assistant_token`, `uptime_kuma_api_key`, `peanut_username` and `peanut_password`,
`ipmi_password` (the IPMI exporters' basic auth; see [IPMI](ipmi.md)), `hwmon_password` (node_exporter's
basic auth on servers; see [hwmon](hwmon.md)), `intel_gpu_password` (the Intel GPU exporters' basic auth; see
[Intel GPU](intel-gpu.md)), `steerhouse_metrics_token` (Steerhouse's `METRICS_TOKEN`; see
[Steerhouse](steerhouse.md)), `prometheus-web.yml`, `prometheus_password`); and `snmp-auth.yml`.

## Data contracts

- **Datasource uids** `prometheus`, `loki` and `steerhouse-db` ([`provisioning/datasources/argus.yaml`](../provisioning/datasources/argus.yaml))
  and **dashboard uids** (`argus-*`) are stable: links and bookmarks to them survive upgrades.
- **Labels**: host series carry `host` (= `ARGUS_HOST`) and `instance`; container series `host`, `name`;
  logs `host`, `container`, `compose_project`, `job` (`docker`, `kubernetes`, `npm` or `homelab-pull`; Kubernetes
  pods also `namespace`, `pod`), for NPM `site`,
  `status`, `method`, and for deploys `stack`, `result`.
- **Deploys** (what the Deploys dashboard reads from `HOMELAB_PULL_DIR`; homelab-pull 0.4.0 writes it, and any
  deploy tool can): `metrics/<stack>.prom`, Prometheus text format, rewritten after every run, with the
  gauges `homelab_pull_info{stack, version}`, `homelab_pull_last_run_timestamp_seconds`,
  `homelab_pull_last_run_success` (1/0), `homelab_pull_paused` (1/0), `homelab_pull_deploy_failing` (1/0),
  `homelab_pull_deploy_failure_info{commit, kind}` (only while failing), `homelab_pull_deployed_info{commit}`,
  `homelab_pull_up_to_date` (1/0), `homelab_pull_last_deploy_timestamp_seconds` and
  `homelab_pull_last_deploy_duration_seconds`, each labelled `stack`; and `<stack>/deploys.log`, one line per
  attempt: `<time, 2006-01-02T15:04:05-0700> <stack> <ok|failed:<kind>> <old> -> <new> <subject>`.
- **Selected GPU** (optional; read by the "Monitoring target down" alert): a host whose GPU can change, such as
  a VM that fails over to a machine with another GPU, writes one series `homelab_gpu_selected{vendor} 1`, `vendor`
  being `nvidia`, `intel` or `none`, to a `.prom` file in `HOMELAB_PULL_DIR`'s `metrics/` directory (the agent
  adds `host`). While it isn't `nvidia`, a stopped NVIDIA GPU exporter on that host (its `gpu` target)
  doesn't alert, and while it isn't `intel`, a stopped Intel GPU exporter (its `intel_gpu` target); without the
  series, they do.
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
