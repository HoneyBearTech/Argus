# Argus

[![CI](https://github.com/HoneyBearTech/Argus/actions/workflows/ci.yml/badge.svg)](https://github.com/HoneyBearTech/Argus/actions/workflows/ci.yml)
[![Release images](https://github.com/HoneyBearTech/Argus/actions/workflows/release.yml/badge.svg)](https://github.com/HoneyBearTech/Argus/actions/workflows/release.yml)
[![CodeQL](https://github.com/HoneyBearTech/Argus/actions/workflows/codeql.yml/badge.svg)](https://github.com/HoneyBearTech/Argus/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/HoneyBearTech/Argus/badge)](https://scorecard.dev/viewer/?uri=github.com/HoneyBearTech/Argus)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15224/badge)](https://www.bestpractices.dev/projects/15224)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15224/baseline)](https://www.bestpractices.dev/projects/15224)
[![Docker Pulls](https://img.shields.io/docker/pulls/honeybeartech/argus-grafana?logo=docker&logoColor=white)](https://hub.docker.com/r/honeybeartech/argus-grafana)
[![Version](https://img.shields.io/github/v/tag/HoneyBearTech/Argus?sort=semver&logo=docker&logoColor=white&label=version)](https://hub.docker.com/r/honeybeartech/argus-grafana/tags)
[![Agent image size](https://img.shields.io/docker/image-size/honeybeartech/argus-agent/latest?logo=docker&logoColor=white&label=agent%20image)](https://hub.docker.com/r/honeybeartech/argus-agent)
[![Grafana](https://img.shields.io/badge/grafana-13.2.4-F46800?logo=grafana&logoColor=white)](images/grafana/Dockerfile)
[![License](https://img.shields.io/github/license/HoneyBearTech/Argus)](LICENSE)

Grafana dashboards as code for a homelab: version-controlled JSON dashboards and
alert rules for Docker hosts and their logs, the Plex/arr media stack, reverse
proxy traffic, DNS, the network and internet connection, NAS storage, UPS power,
the smart home, GitLab CI, Steerhouse (an Ansible web UI), Tdarr, Plex's current
streams (through Tautulli) and the Proxmox VE cluster — edited in VS Code,
provisioned automatically, and shipped as Docker images with a one-container
agent for each host.

## How it works

Grafana, Prometheus, blackbox_exporter, Loki and exporters for Pi-hole, UniFi,
SNMP, the media apps, Tdarr, Tautulli (through Varken), GitLab CI and Proxmox
run on one server from [`docker-compose.yml`](docker-compose.yml) (the optional
ones behind Compose profiles, and Loki on another host if you prefer); an Argus
agent on every monitored host pushes its metrics and logs there. Grafana loads
every dashboard under [`dashboards/`](dashboards/) through file provisioning —
each subfolder becomes a Grafana folder, and UI edits are blocked so this repo
stays the source of truth. The same compose file runs production and a local
sandbox; per-install settings come from a gitignored `.env`.

```text
dashboards/          dashboard JSON, one folder per Grafana folder
provisioning/        Grafana datasources (pinned uids) and the dashboard
                     provider
prometheus/          Prometheus config — scrape jobs, no addresses
blackbox/            blackbox_exporter probe modules (HTTP service check, DNS
                     resolve)
agent/               the Argus agent image (Grafana Alloy + config) and its
                     compose file, one per monitored host
logs/                Loki config, plus a compose file to run Loki on a separate
                     host with more disk
images/              Dockerfiles for the published server images
targets.example/     placeholder scrape/probe targets; real ones go in targets/
                     (gitignored)
secrets.example/     placeholder credentials Prometheus scrapes with; real ones
                     go in secrets/ (gitignored)
scripts/             repo checks and the PromQL test builder, run in CI; the
                     Steerhouse dashboard port
tests/               unit tests (pytest) and PromQL tests (tests/promql/, run
                     with promtool)
docs/                user, security and project documentation
```

## Dashboards

- **Dashboard:** Homelab Overview (home page)
  - **Folder:** overview
  - **Answers:** Is everything up right now, and if not, what?
  - **Data:** [Uptime Kuma](https://github.com/louislam/uptime-kuma) `/metrics`,
    blackbox_exporter HTTP + DNS probes

- **Dashboard:** DNS / Pi-hole
  - **Folder:** dns
  - **Answers:** Is DNS healthy and consistent, and what's being blocked?
  - **Data:** [pihole-exporter](https://github.com/eko/pihole-exporter) (Pi-hole
    v6 API), blackbox DNS probes

- **Dashboard:** Host Health
  - **Folder:** hosts
  - **Answers:** Is any machine running out of disk, memory or CPU?
  - **Data:** Argus agent on each host (embedded node_exporter)

- **Dashboard:** GPUs
  - **Folder:** hosts
  - **Answers:** Are the GPUs doing the transcoding, and are they healthy?
  - **Data:**
    [nvidia_gpu_exporter](https://github.com/utkuozdemir/nvidia_gpu_exporter)
    (nvidia-smi) beside the agent on a GPU host (`agent/compose.yml`, `gpu`
    profile); Intel GPUs from Argus' Intel GPU exporter (`intel_gpu_top`, see
    [docs/intel-gpu.md](docs/intel-gpu.md)) with temperature and power from
    hwmon

- **Dashboard:** Databases
  - **Folder:** hosts
  - **Answers:** Are the shared database servers up, and is any app close to
    running out of connections, cache or room?
  - **Data:**
    [postgres_exporter](https://github.com/prometheus-community/postgres_exporter)
    and [mysqld_exporter](https://github.com/prometheus/mysqld_exporter),
    running beside PostgreSQL and MariaDB

- **Dashboard:** Docker Containers
  - **Folder:** hosts
  - **Answers:** Which containers are restarting, stopped, or eating resources?
  - **Data:** Argus agent on each host (embedded cAdvisor)

- **Dashboard:** Network / UniFi
  - **Folder:** network
  - **Answers:** How's the internet connection, and what's on the network?
  - **Data:** [unpoller](https://github.com/unpoller/unpoller) with a read-only
    UniFi account

- **Dashboard:** Internet / ISP
  - **Folder:** network
  - **Answers:** Is the ISP delivering the speed we pay for, and how often does
    the connection drop?
  - **Data:** unpoller: the UniFi gateway's own speed tests and the plan speeds
    set in UniFi

- **Dashboard:** Media Stack
  - **Folder:** media
  - **Answers:** Who's watching what, is the download pipeline flowing, and is
    the library healthy?
  - **Data:** [exportarr](https://github.com/onedr0p/exportarr) (*arr, SABnzbd),
    [qbittorrent-exporter](https://github.com/martabal/qbittorrent-exporter);
    Plex exporter beside Plex (`agent/compose.yml`, `plex` profile)

- **Dashboard:** Tautulli
  - **Folder:** media
  - **Answers:** What's playing on Plex right now, and how is it being
    delivered?
  - **Data:** [Varken](https://github.com/HoneyBearTech/Varken)'s Prometheus
    output, reading Tautulli's API (`varken` profile): streams, transcode
    decisions, bandwidth, sessions by quality and platform, library sizes

- **Dashboard:** Varken
  - **Folder:** media
  - **Answers:** What's on Plex, who's watching from where, and what are Sonarr,
    Radarr and Seerr waiting on?
  - **Data:** The original
    [Varken dashboard](https://github.com/HoneyBearTech/Varken/tree/main/dashboard),
    ported to Prometheus, with Seerr in place of Ombi and without SickChill:
    Varken 3.0's metrics with `stream_details` on (viewer names, titles and
    cities) and GeoIP on (a MaxMind account: `maxmind_license_key` secret,
    account ID in `varken.env`) for the map; Sonarr and Radarr (and their 4K
    instances, with an HD/4K column) and Seerr's requests and issues through
    Varken too

- **Dashboard:** Varken [Classic]
  - **Folder:** media
  - **Answers:** The same, in the original Varken dashboard's look
  - **Data:** The Varken dashboard's queries, restyled like the original "Varken
    [Official]" (coloured tiles and rows, heat strip, US map)

- **Dashboard:** Tdarr
  - **Folder:** media
  - **Answers:** Is Tdarr keeping up, and how much space has it saved?
  - **Data:** [tdarr-exporter](https://github.com/homeylab/tdarr-exporter)
    through Tdarr's API (`tdarr` profile); the Tdarr container's CPU, memory and
    logs from the Argus agent

- **Dashboard:** NAS / Storage
  - **Folder:** storage
  - **Answers:** Are the NAS units healthy, and how fast are they filling?
  - **Data:** snmp-exporter (bundled `synology` + standard MIB modules, and
    Argus' [`synology_flashcache`](snmp/synology-flashcache.yml) for SSD
    caches), SNMPv3

- **Dashboard:** Smart Home
  - **Folder:** home
  - **Answers:** What's the house doing — temperatures, HVAC, energy?
  - **Data:** Home Assistant's Prometheus integration (long-lived token)

- **Dashboard:** Reverse Proxy Traffic
  - **Folder:** network
  - **Answers:** What's hitting the services behind the reverse proxy, and is
    anything erroring?
  - **Data:** Nginx Proxy Manager access logs → Alloy → Loki

- **Dashboard:** Logs
  - **Folder:** hosts
  - **Answers:** What did a host or container log around the time something
    broke?
  - **Data:** Docker container logs → Alloy → Loki

- **Dashboard:** Deploys
  - **Folder:** ci
  - **Answers:** Did every merge reach its host, and is every host's deploy
    agent alive?
  - **Data:** [homelab-pull](docs/interfaces.md#data-contracts)'s metrics and
    deploy log (a pull-based deploy agent: one stack per host, deployed from its
    git branch), read by the Argus agent (`HOMELAB_PULL_DIR`); deploy markers on
    Host Health and Docker Containers

- **Dashboard:** GitLab CI
  - **Folder:** ci
  - **Answers:** Are pipelines healthy, are the runners keeping up, and is
    GitLab itself healthy?
  - **Data:**
    [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter)
    with a `read_api` token (`gitlab` profile); GitLab Runner's metrics
    endpoint; a subset of GitLab's bundled Prometheus (Omnibus), read through
    `/federate`

- **Dashboard:** Steerhouse: overview & runs
  - **Folder:** ci
  - **Answers:** Is Steerhouse healthy right now, and how have its Ansible runs
    gone: which failed, and how long did they take?
  - **Data:** [Steerhouse](https://github.com/HoneyBearTech/Steerhouse)'s
    token-protected `/metrics` (port 8002) and its database's read-only
    `analytics` views, as the `grafana_ro` role over TLS; the three Steerhouse
    dashboards are Steerhouse's own, ported by
    [`scripts/port_steerhouse.py`](scripts/port_steerhouse.py)

- **Dashboard:** Steerhouse: execution, queue & workers
  - **Folder:** ci
  - **Answers:** Is Steerhouse keeping up: are runs waiting for a worker, are
    notifications going out, and is its API healthy?
  - **Data:** The same

- **Dashboard:** Steerhouse: security & access
  - **Folder:** ci
  - **Answers:** Is anyone trying to get into Steerhouse, and who changed users,
    access or keys?
  - **Data:** The same

- **Dashboard:** Proxmox VE
  - **Folder:** proxmox
  - **Answers:** Are the Proxmox nodes overcommitted, are the guests that should
    run running, and how is storage filling?
  - **Data:**
    [prometheus-pve-exporter](https://github.com/prometheus-pve/prometheus-pve-exporter)
    with a read-only API token (`proxmox` profile)

- **Dashboard:** Server Hardware
  - **Folder:** proxmox
  - **Answers:** Is the server hardware healthy: temperatures, fans, power
    supplies, batteries, power draw, room in the BMCs' event logs, and add-in
    GPUs, including how busy an Intel GPU is?
  - **Data:**
    [prometheus-ipmi-exporter](https://github.com/prometheus-community/ipmi_exporter)
    on each server (Debian package), reading its own BMC through `/dev/ipmi0` —
    see [docs/ipmi.md](docs/ipmi.md); add-in GPUs, which the BMC can't see, from
    [node_exporter](https://github.com/prometheus/node_exporter)'s hwmon
    collector (Debian package, hwmon only) — see [docs/hwmon.md](docs/hwmon.md);
    Intel GPU load from Argus' own exporter around `intel_gpu_top` — see
    [docs/intel-gpu.md](docs/intel-gpu.md)

- **Dashboard:** UPS / Power
  - **Folder:** power
  - **Answers:** How long would the lab survive a power cut, and is the UPS
    healthy?
  - **Data:** [PeaNUT](https://github.com/Brandawg93/PeaNUT) `/api/v1/metrics`

## Alerts

Grafana-managed alert rules live in
[`provisioning/alerting/rules.yaml`](provisioning/alerting/rules.yaml) (edit
there — UI changes are blocked) and notify a Discord channel through the webhook
in `secrets/discord_webhook_url` (its template points nowhere, so a sandbox
can't post). Each rule is a raw PromQL measurement (`A`) plus a threshold (`C`),
one alert per series:

- **Group:** Availability
  - **Rules:** host stopped reporting (its agent went silent), service down
    (only services that were up for at least an hour in the last 7 days), DNS
    server not answering, monitoring target down (not a host's NVIDIA or Intel
    GPU exporter while that host says it's on another GPU), Proxmox node without
    cluster quorum, Proxmox QDevice disconnected for 5 minutes, GPU exporter
    reporting no GPU (driver not loaded), an Intel GPU on its server's driver
    that intel_gpu_top can't read for 10 minutes

- **Group:** Capacity
  - **Rules:** local disk > 90 % (network shares are covered by the NAS pool
    rule), NAS storage pool > 90 %, certificate < 14 days, Proxmox node memory >
    90 % used, Proxmox node memory overcommitted (running guests allocated > 100
    %)

- **Group:** Power and hardware
  - **Rules:** UPS on battery, UPS battery < 50 %, NAS disk unhealthy, NAS pool
    degraded, NAS disk > 55 °C, network device > 85 °C, GPU > 85 °C (NVIDIA, and
    Intel cards read by the server's driver), a BMC sensor critical for 5
    minutes (a failed battery, power supply or fan, or a reading past its
    critical limit; empty slots and Supermicro's LED pattern sensors don't
    count), a BMC sensor in warning for 15 minutes, a BMC that can't be read for
    10 minutes, a BMC event log with < 1 KiB left

- **Group:** Network
  - **Rules:** internet on backup WAN, internet dropped, internet much slower
    than usual (latest speed test under half its 14-day median), no speed test
    in 8 days, Pi-hole blocklists out of sync

- **Group:** Containers
  - **Rules:** container restarted more than 3 times in an hour

- **Group:** Logs
  - **Rules:** a site returning > 20 server errors (5xx) in 10 minutes, log
    pipeline stalled (Loki receiving almost nothing for 15 minutes)

- **Group:** Tautulli
  - **Rules:** Varken can't read Tautulli for 10 minutes (down, wrong API key or
    an unreadable reply), Tautulli data stale for 10 minutes while Varken still
    reports it up (a hanging request)

- **Group:** Tdarr
  - **Rules:** new transcode or health-check errors in the last hour, files
    queued but no transcode or health check finished in a day

- **Group:** Deploys
  - **Rules:** a deploy agent that hasn't finished a run for 50 minutes, a
    deploy failing for 15 minutes, every run of an agent failing for 15 minutes
    (fetch or settings), deploys paused for 2 hours (the checkout isn't on its
    branch)

- **Group:** GitLab
  - **Rules:** a GitLab component (Puma, Sidekiq, Gitaly, PostgreSQL, …) down
    for 5 minutes, the latest pipeline on a watched branch failed

- **Group:** Steerhouse
  - **Rules:** more than 30 % of the runs that ended in the last hour failed or
    timed out (for 15 minutes), over 30 failed sign-ins in 15 minutes, a
    notification waiting over 15 minutes to be sent, Steerhouse's API unable to
    read its database for 5 minutes. Single events (a failed run, a worker
    offline, a lockout) are Steerhouse's own notifications; its metrics not
    arriving is "monitoring target down"

Alerts are grouped per rule and repeat every 12 hours while firing.

## Running it

**Requirements:** Docker with Compose v2.24 or later, on amd64 or arm64. One
host runs the server; every host you want to watch runs the agent.

Argus ships as images for amd64 and arm64 on GHCR
(`ghcr.io/honeybeartech/argus-*`) and Docker Hub (`honeybeartech/argus-*`; set
`ARGUS_REGISTRY=docker.io/honeybeartech` in `.env` to use it). The Grafana image
has every dashboard, datasource and alert rule baked in; the Prometheus,
blackbox and Loki images carry their configs. What stays on the host is what's
specific to your network: scrape targets, credentials and `.env`.

**Server** (one host — Grafana, Prometheus, blackbox_exporter, Loki):

```sh
git clone --depth 1 https://github.com/HoneyBearTech/Argus.git && cd Argus
cp .env.example .env              # set GRAFANA_ROOT_URL
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp \
  secrets.example/* secrets/
# Grafana's admin password (user admin)
openssl rand -base64 24 > secrets/grafana_admin_password
# put your real addresses in targets/ and credentials in secrets/ — delete what
# you don't use
docker compose up -d
```

Then run the agent on each host you want to watch (next section). Grafana is on
port 3000; the home page is the Homelab Overview. Edits to `targets/*.json` are
picked up by Prometheus without a restart.

Host Health, Docker Containers and Logs work with just the agents. Every other
dashboard lights up as you connect the service it reads. `COMPOSE_PROFILES`
starts as `loki`: add profiles to that list (`loki,snmp`) rather than replacing
it, or Loki stops (unless it runs on another host, with `LOKI_URL` set):

- **To see:** Service up/down, certificates (Overview)
  - **Add to `targets/`:** `blackbox_http.json` (URLs), `blackbox_dns.json` (DNS
    servers)
  - **Credentials in `secrets/`:** —
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Uptime Kuma monitors (Overview)
  - **Add to `targets/`:** `uptime_kuma.json`
  - **Credentials in `secrets/`:** `uptime_kuma_api_key`
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** DNS / Pi-hole
  - **Add to `targets/`:** `blackbox_dns.json`
  - **Credentials in `secrets/`:** `pihole-exporter.env`
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Network / UniFi, Internet / ISP
  - **Add to `targets/`:** —
  - **Credentials in `secrets/`:** `unpoller.env` (console URL + read-only local
    account), `unifi_password`
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** NAS / Storage
  - **Add to `targets/`:** `snmp.json` (add `synology_flashcache` to a
    Synology's `module` list for its SSD cache)
  - **Credentials in `secrets/`:** `snmp-auth.yml` (SNMPv3)
  - **Add to `COMPOSE_PROFILES` in `.env`:** `snmp`

- **To see:** Smart Home
  - **Add to `targets/`:** `homeassistant.json`
  - **Credentials in `secrets/`:** `home_assistant_token`
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** UPS / Power
  - **Add to `targets/`:** `peanut.json`
  - **Credentials in `secrets/`:** `peanut_username`, `peanut_password` (PeaNUT
    6's login; PeaNUT 5 ignores them)
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Media Stack (*arr, SABnzbd, qBittorrent)
  - **Add to `targets/`:** `media.json` (enabled exporters only)
  - **Credentials in `secrets/`:** `<app>.env` (URL), `<app>_api_key`
    (qBittorrent: `qbittorrent.env` with URL + user, `qbittorrent_password`)
  - **Add to `COMPOSE_PROFILES` in `.env`:** the app's profile, e.g.
    `radarr,sonarr`

- **To see:** Tautulli
  - **Add to `targets/`:** `varken.json` (`varken:9180`)
  - **Credentials in `secrets/`:** `varken.env` (Tautulli's, Sonarr's, Radarr's,
    Lidarr's and Seerr's addresses, SSL settings), `tautulli_api_key` and the
    Sonarr/Radarr (and 4K) and Lidarr API keys exportarr uses, `seerr_api_key`;
    and `CONFIG_ROOT/varken/config` owned by uid 1000
  - **Add to `COMPOSE_PROFILES` in `.env`:** `varken`

- **To see:** Tdarr
  - **Add to `targets/`:** `tdarr.json` (`tdarr-exporter:9090`)
  - **Credentials in `secrets/`:** `tdarr.env` (Tdarr's URL; and `TDARR_API_KEY`
    once Tdarr's own login is on, which the exporter reads only from its
    environment)
  - **Add to `COMPOSE_PROFILES` in `.env`:** `tdarr`

- **To see:** Server Hardware
  - **Add to `targets/`:** `ipmi.json` (`<server>:9290`, with a `host` label)
  - **Credentials in `secrets/`:** `ipmi_password` (the exporters' basic auth;
    set up each server with [`deploy/ipmi/`](deploy/ipmi/), see
    [docs/ipmi.md](docs/ipmi.md))
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Server Hardware (add-in GPUs)
  - **Add to `targets/`:** `hwmon.json` (`<server>:9100`, with the same `host`
    label)
  - **Credentials in `secrets/`:** `hwmon_password` (node_exporter's basic auth;
    set up each server with [`deploy/hwmon/`](deploy/hwmon/), see
    [docs/hwmon.md](docs/hwmon.md))
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Server Hardware (Intel GPU load)
  - **Add to `targets/`:** `intel_gpu.json` (`<server or host>:9836`, with a
    `host` label)
  - **Credentials in `secrets/`:** `intel_gpu_password` (the Intel GPU
    exporters' basic auth; set up a server with
    [`deploy/intelgpu/`](deploy/intelgpu/), see
    [docs/intel-gpu.md](docs/intel-gpu.md))
  - **Add to `COMPOSE_PROFILES` in `.env`:** `intel-gpu`, on a host or VM with
    the agent, with `ARGUS_INTEL_GPU_PASSWORD_HASH`

- **To see:** GPUs
  - **Add to `targets/`:** `gpu.json` (`<gpu host>:9835`, with a `host` label)
  - **Credentials in `secrets/`:** —
  - **Add to `COMPOSE_PROFILES` in `.env`:** `gpu`, in that host's agent `.env`
    (needs the NVIDIA Container Toolkit)

- **To see:** Media Stack (Plex)
  - **Add to `targets/`:** `plex.json`
  - **Credentials in `secrets/`:** `PLEX_TOKEN` in the Plex host's agent `.env`
  - **Add to `COMPOSE_PROFILES` in `.env`:** `plex`, in that host's agent `.env`

- **To see:** Loki's own health
  - **Add to `targets/`:** `loki.json` (`loki:3100` for the bundled one)
  - **Credentials in `secrets/`:** —
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** GitLab CI (pipelines)
  - **Add to `targets/`:** `gitlab.json`
  - **Credentials in `secrets/`:** `gitlab.yml` (GitLab's URL and a `read_api`
    token)
  - **Add to `COMPOSE_PROFILES` in `.env`:** `gitlab`

- **To see:** GitLab CI (runners)
  - **Add to `targets/`:** `gitlab_runner.json` (`<runner>:9252`, one target per
    runner); set `listen_address = ":9252"` in each runner's `config.toml`
  - **Credentials in `secrets/`:** —
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** GitLab CI (GitLab's health)
  - **Add to `targets/`:** `gitlab_server.json` (`<gitlab>:9090`); set
    `prometheus['listen_address'] = '0.0.0.0:9090'` in `gitlab.rb` and run
    `gitlab-ctl reconfigure` (restarts Puma and Sidekiq: a minute or two of
    502s)
  - **Credentials in `secrets/`:** —
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Steerhouse
  - **Add to `targets/`:** `steerhouse.json` (`<steerhouse host>:8002`, the
    backend's metrics port, which Steerhouse serves once `METRICS_TOKEN` and
    `METRICS_HOST` are set); and `STEERHOUSE_DB_ADDRESS` in `.env` (its
    PostgreSQL, `host:port`)
  - **Credentials in `secrets/`:** `steerhouse_metrics_token` (Steerhouse's
    `METRICS_TOKEN`), `steerhouse_db_password` (the `grafana_ro` role's
    password: see [docs/steerhouse.md](docs/steerhouse.md)), `steerhouse_db_ca`
    (the CA certificate that signed the database's TLS certificate, which must
    name the address)
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Databases
  - **Add to `targets/`:** `postgres.json` (`<db server>:9187`) and `mysql.json`
    (`<db server>:9104`), each target with a `host` label
  - **Credentials in `secrets/`:** — (the exporters keep their own database
    logins)
  - **Add to `COMPOSE_PROFILES` in `.env`:** —

- **To see:** Proxmox VE
  - **Add to `targets/`:** `pve.json`: each node's API address (port 8006 by
    default), which the node's certificate must name; in a cluster, label every
    node but one `"cluster": "0"`
  - **Credentials in `secrets/`:** `pve.yml` (an API token with the `PVEAuditor`
    role; the commands are in the template), `pve-ca.pem` (the cluster's CA,
    `/etc/pve/pve-root-ca.pem` on any node)
  - **Add to `COMPOSE_PROFILES` in `.env`:** `proxmox`

To upgrade, pull new images (`docker compose pull && docker compose up -d`), or
pin `ARGUS_VERSION` in `.env` to a release; see
[docs/upgrading.md](docs/upgrading.md). New to Argus? The
[quick start](docs/quick-start.md) runs it on one machine in about ten minutes.

**Security:** Prometheus (9090) and Loki (3101) accept pushes without
authentication, so agents anywhere on the network can reach them; Prometheus can
[require a password](docs/security.md#requiring-a-password-for-prometheus). Run
Argus on a trusted network, and put Grafana behind a reverse proxy with TLS if
it's reachable from outside (`docker-compose.proxy.yml` puts Grafana on the
network of a proxy running in Docker on the same host, so its own port can
listen on loopback only). What Argus does and doesn't protect against is in
[docs/security.md](docs/security.md).

**Developing** — to edit dashboards, alert rules or configs live, run from the
checkout instead of the published images by setting
`COMPOSE_FILE=docker-compose.yml:docker-compose.source.yml` in `.env`. Grafana
then reads `dashboards/` and `provisioning/` straight from the repo (dashboard
edits show up within 30 seconds), and `docker compose up -d --build` rebuilds
the images. In this mode, deploying is `git pull` on the server; restart the
stack only when `docker-compose.yml`, `provisioning/` or a config changes. A
systemd timer can do that for you once CI passes: see
[docs/auto-deploy.md](docs/auto-deploy.md).

Releases are published by pushing a signed `v*.*.*` tag
([`.github/workflows/release.yml`](.github/workflows/release.yml)): the images
are signed with cosign and carry an SBOM and provenance, and the GitHub Release
gets its notes from [CHANGELOG.md](CHANGELOG.md) and a signed checksum file.
[docs/verifying-releases.md](docs/verifying-releases.md) shows how to check
them.

## Adding a host

Each monitored host runs one container, the **Argus agent** (`agent/`): Grafana
Alloy with embedded node_exporter and cAdvisor that pushes host metrics,
container metrics and container logs to the Argus server. Nothing on the server
needs to change — the host appears in the dashboards as soon as the agent
starts, and it only makes outbound connections (no firewall rules on the host).

```sh
docker run -d --name argus-agent --restart unless-stopped \
  --network host --pid host --read-only \
  --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges:true \
  -e ARGUS_HOST=my-host \
  -e ARGUS_PROMETHEUS_URL=http://argus-server:9090 \
  -e ARGUS_LOKI_URL=http://argus-server:3101 \
  -v /:/rootfs:ro,rslave -v /sys:/sys:ro -v /run/udev:/run/udev:ro -v \
    /dev/disk:/dev/disk:ro \
  -v /var/lib/docker:/var/lib/docker:ro -v \
    /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /run/containerd:/run/containerd:ro -v \
    argus-agent-data:/var/lib/alloy/data \
  ghcr.io/honeybeartech/argus-agent:latest
```

It runs as root in the host's network and PID namespaces with the host mounted
read-only, but not privileged: its only capability is `DAC_OVERRIDE` (to read
files that belong to other users), and its own filesystem is read-only, so it
writes only its data volume. Why it needs each of these is in
[docs/security.md](docs/security.md#hardening).

Or copy `agent/compose.yml` and `agent/.env.example` (as `.env`) to the host and
run `docker compose up -d`; pin `ARGUS_AGENT_IMAGE` to a release tag for
predictable upgrades. The compose file also covers five extras:

- **Nginx Proxy Manager access logs** (Reverse Proxy Traffic dashboard): on the
  host running NPM, set `NPM_LOG_DIR` to its `data/logs` directory.
- **homelab-pull deploys** (Deploys dashboard): on a host whose Docker Compose
  stack homelab-pull (0.4.0 or later) deploys, set `HOMELAB_PULL_DIR` to its
  state directory (`~/.local/state/homelab-pull` of the user it runs as). The
  agent reads its metrics files (`metrics/*.prom`, node_exporter's textfile
  collector) and each stack's `deploys.log`.
- **NVIDIA GPUs** (GPUs dashboard): on a host with an NVIDIA GPU, the NVIDIA
  Container Toolkit 1.18 or later and **Docker Engine 29.2 or later**, add the
  `gpu` profile, and list that host in the server's `targets/gpu.json`. From
  29.2, Docker serves the exporter's `driver: nvidia` reservation through CDI
  (the toolkit's `nvidia-cdi-hook`, with `nvidia-cdi-refresh` keeping the CDI
  spec current). An older Engine uses NVIDIA's runtime hook, and the container
  loses the GPU at every `systemctl daemon-reload` (apt and unattended-upgrades
  run one): `nvidia-smi` fails with "Failed to initialize NVML: Unknown Error"
  ([NVIDIA container-toolkit issue #48](https://github.com/NVIDIA/nvidia-container-toolkit/issues/48))
  and the "GPU not reporting" alert fires. To check a host:
  `sudo systemctl daemon-reload`, then
  `docker exec argus-gpu-exporter nvidia-smi -L` still lists the GPU. A host
  whose GPU can change (a VM that fails over to a machine with an Intel GPU and
  stops its exporter there) can say which GPU it booted with,
  `homelab_gpu_selected{vendor="intel"} 1`, so its stopped exporter doesn't
  raise "Monitoring target down"
  ([docs/interfaces.md](docs/interfaces.md#data-contracts)).
- **Intel GPUs** (Server Hardware dashboard): on a host or VM whose own i915
  driver has an Intel GPU (amd64), add the `intel-gpu` profile with
  `ARGUS_INTEL_GPU_PASSWORD_HASH`, and list that host in the server's
  `targets/intel_gpu.json`. The exporter's only privilege is `PERFMON`
  ([docs/intel-gpu.md](docs/intel-gpu.md)). A host whose GPU can change switches
  it on only while it has the Intel GPU; with `homelab_gpu_selected` it doesn't
  alert while it's off.
- **Plex** (Media Stack): on the Plex host (amd64), add the `plex` profile with
  `PLEX_SERVER` and `PLEX_TOKEN`, and list that host in the server's
  `targets/plex.json`.

**Kubernetes nodes** run the same image as a DaemonSet with its second
configuration, `kubernetes.alloy`: node metrics, container metrics from each
node's kubelet and pod logs, under the same labels, with no container runtime
socket ([docs/kubernetes.md](docs/kubernetes.md)).

The agent needs the server's Prometheus (9090) and Loki (3101) to be reachable
from the host; those are the defaults. If Prometheus requires a password, add
`-e ARGUS_PROMETHEUS_PASSWORD=...` (or set it in the agent's `.env`).

## Adding or changing a dashboard

1. Build or edit it in the sandbox Grafana, then **Export → Export as JSON**
   (leave "Export for sharing externally" off), or edit the JSON directly in VS
   Code.
2. Save it under `dashboards/<folder>/<name>.json` with a stable, hand-picked
   `uid`, `"id": null`, the `argus` tag, and a description saying what question
   it answers.
3. Reference datasources by uid (`prometheus`) — never by name or URL.
4. Run `python3 scripts/check_dashboards.py`. It also fails on private IP
   addresses and on internal names listed one regex per line in a gitignored
   `.forbidden-patterns` file (CI reads the same list from the
   `ARGUS_FORBIDDEN_PATTERNS` secret): **this repo is public**, so addresses
   stay in `targets/` and `.env`.

## Checks

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push
and pull request: linters for Python, YAML, workflows, Dockerfiles and the agent
config; unit tests with a coverage floor; the dashboard and public-repo checks;
`promtool check config` and the [PromQL tests](tests/promql/), which run the
shipped alert rule and dashboard queries against synthetic series; the blackbox,
Loki and Alloy config checks; it builds every image, starts Grafana to check
that every dashboard, alert rule and datasource loads, and validates the compose
files.

Alongside it: [CodeQL](https://codeql.github.com/) analyses the Python checks
and the workflows on every push and pull request and weekly, a weekly
[Trivy](https://trivy.dev/) scan reports known vulnerabilities in the six
images, [OpenSSF Scorecard](https://scorecard.dev/) scores the repo's
supply-chain practices weekly (see the badge above), and Dependabot opens weekly
PRs for the upstream images, GitHub Actions and the check tools. Image updates
are merged by hand after a sandbox run. How dependencies are handled is in
[docs/dependencies.md](docs/dependencies.md).

## Documentation

[docs/](docs/README.md) has the [quick start](docs/quick-start.md),
[architecture](docs/architecture.md), [interfaces](docs/interfaces.md),
[upgrading](docs/upgrading.md), [security requirements](docs/security.md) and
[assurance case](docs/assurance-case.md),
[dependency policy](docs/dependencies.md) and [roadmap](docs/roadmap.md).
Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Bug reports and ideas go in
[GitHub Issues](https://github.com/HoneyBearTech/Argus/issues); see
[CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, coding standards,
test policy and sign-off, [SECURITY.md](SECURITY.md) for reporting
vulnerabilities privately, and [SUPPORT.md](SUPPORT.md) for which versions are
supported. The project's [governance](GOVERNANCE.md) and
[code of conduct](CODE_OF_CONDUCT.md) apply to everyone taking part.

## License

[MIT](LICENSE)
