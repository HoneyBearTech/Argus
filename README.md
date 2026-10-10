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
[![Grafana](https://img.shields.io/badge/grafana-13.2.3-F46800?logo=grafana&logoColor=white)](images/grafana/Dockerfile)
[![License](https://img.shields.io/github/license/HoneyBearTech/Argus)](LICENSE)

Grafana dashboards as code for a homelab: version-controlled JSON dashboards and alert rules for Docker hosts, the Plex/arr media stack, reverse proxy traffic, DNS, network, storage, power and the smart home — edited in VS Code, provisioned automatically, and shipped as Docker images with a one-container agent for each host.

## How it works
Grafana, Prometheus, blackbox_exporter, Loki and exporters for Pi-hole, UniFi, SNMP and the media apps run on one server from [`docker-compose.yml`](docker-compose.yml); an Argus agent on every monitored host pushes its metrics and logs there. Grafana loads every dashboard under [`dashboards/`](dashboards/) through file provisioning — each subfolder becomes a Grafana folder, and UI edits are blocked so this repo stays the source of truth. The same compose file runs production and a local sandbox; per-install settings come from a gitignored `.env`.

```
dashboards/          dashboard JSON, one folder per Grafana folder
provisioning/        Grafana datasources (pinned uids) and the dashboard provider
prometheus/          Prometheus config — scrape jobs, no addresses
blackbox/            blackbox_exporter probe modules (HTTP service check, DNS resolve)
agent/               the Argus agent image (Grafana Alloy + config) and its compose file, one per monitored host
logs/                Loki config, plus a compose file to run Loki on a separate host with more disk
images/              Dockerfiles for the published server images
targets.example/     placeholder scrape/probe targets; real ones go in targets/ (gitignored)
secrets.example/     placeholder credentials Prometheus scrapes with; real ones go in secrets/ (gitignored)
scripts/             repo checks and the PromQL test builder, run in CI
tests/               unit tests (pytest) and PromQL tests (tests/promql/, run with promtool)
docs/                user, security and project documentation
```

## Dashboards
| Dashboard | Folder | Answers | Data |
|---|---|---|---|
| Homelab Overview (home page) | overview | Is everything up right now, and if not, what? | [Uptime Kuma](https://github.com/louislam/uptime-kuma) `/metrics`, blackbox_exporter HTTP + DNS probes |
| DNS / Pi-hole | dns | Is DNS healthy and consistent, and what's being blocked? | [pihole-exporter](https://github.com/eko/pihole-exporter) (Pi-hole v6 API), blackbox DNS probes |
| Host Health | hosts | Is any machine running out of disk, memory or CPU? | Argus agent on each host (embedded node_exporter) |
| Docker Containers | hosts | Which containers are restarting, stopped, or eating resources? | Argus agent on each host (embedded cAdvisor) |
| Network / UniFi | network | How's the internet connection, and what's on the network? | [unpoller](https://github.com/unpoller/unpoller) with a read-only UniFi account |
| Internet / ISP | network | Is the ISP delivering the speed we pay for, and how often does the connection drop? | unpoller: the UniFi gateway's own speed tests and the plan speeds set in UniFi |
| Media Stack | media | Who's watching what, is the download pipeline flowing, and is the library healthy? | [exportarr](https://github.com/onedr0p/exportarr) (*arr, SABnzbd), [qbittorrent-exporter](https://github.com/martabal/qbittorrent-exporter); Plex exporter beside Plex (`agent/compose.yml`, `plex` profile) |
| NAS / Storage | storage | Are the NAS units healthy, and how fast are they filling? | snmp-exporter (bundled `synology` + standard MIB modules), SNMPv3 |
| Smart Home | home | What's the house doing — temperatures, HVAC, energy? | Home Assistant's Prometheus integration (long-lived token) |
| Reverse Proxy Traffic | network | What's hitting the services behind the reverse proxy, and is anything erroring? | Nginx Proxy Manager access logs → Alloy → Loki |
| Logs | hosts | What did a host or container log around the time something broke? | Docker container logs → Alloy → Loki |
| GitLab CI | ci | Are pipelines healthy, is the runner keeping up, and is GitLab itself healthy? | [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter) with a `read_api` token (`gitlab` profile); GitLab Runner's metrics endpoint; a subset of GitLab's bundled Prometheus (Omnibus), read through `/federate` |
| ESXi / vCenter | vsphere | Are the ESXi hosts overcommitted, and how are datastores filling? | [Telegraf](https://github.com/influxdata/telegraf)'s vSphere input with a read-only vCenter account (`vsphere` profile) |
| UPS / Power | power | How long would the lab survive a power cut, and is the UPS healthy? | [PeaNUT](https://github.com/Brandawg93/PeaNUT) `/api/v1/metrics` |

## Alerts
Grafana-managed alert rules live in [`provisioning/alerting/rules.yaml`](provisioning/alerting/rules.yaml) (edit there — UI changes are blocked) and notify a Discord channel through the webhook in `DISCORD_WEBHOOK_URL` (production `.env` only; a sandbox gets a dummy URL so it can't post). Each rule is a raw PromQL measurement (`A`) plus a threshold (`C`), one alert per series:

| Group | Rules |
|---|---|
| Availability | host stopped reporting (its agent went silent), service down (only services that were up for at least an hour in the last 7 days), DNS server not answering, monitoring target down |
| Capacity | local disk > 90 % (network shares are covered by the NAS pool rule), NAS storage pool > 90 %, certificate < 14 days |
| Power and hardware | UPS on battery, UPS battery < 50 %, NAS disk unhealthy, NAS pool degraded, NAS disk > 55 °C, network device > 85 °C |
| Network | internet on backup WAN, internet dropped, internet much slower than usual (latest speed test under half its 14-day median), no speed test in 8 days, Pi-hole blocklists out of sync |
| Containers | container restarted more than 3 times in an hour |
| Logs | a site returning > 20 server errors (5xx) in 10 minutes, log pipeline stalled (Loki receiving almost nothing for 15 minutes) |
| GitLab | a GitLab component (Puma, Sidekiq, Gitaly, PostgreSQL, …) down for 5 minutes, the latest pipeline on a watched branch failed |

Alerts are grouped per rule and repeat every 12 hours while firing.

## Running it
**Requirements:** Docker with Compose v2.24 or later, on amd64 or arm64. One host runs the server; every host you want to watch runs the agent.

Argus ships as images for amd64 and arm64 on GHCR (`ghcr.io/honeybeartech/argus-*`) and Docker Hub (`honeybeartech/argus-*`; set `ARGUS_REGISTRY=docker.io/honeybeartech` in `.env` to use it). The Grafana image has every dashboard, datasource and alert rule baked in; the Prometheus, blackbox and Loki images carry their configs. What stays on the host is what's specific to your network: scrape targets, credentials and `.env`.

**Server** (one host — Grafana, Prometheus, blackbox_exporter, Loki):
```sh
git clone --depth 1 https://github.com/HoneyBearTech/Argus.git && cd Argus
cp .env.example .env              # set GF_SECURITY_ADMIN_PASSWORD and GRAFANA_ROOT_URL
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp secrets.example/* secrets/
# put your real addresses in targets/ and credentials in secrets/ — delete what you don't use
docker compose up -d
```
Then run the agent on each host you want to watch (next section). Grafana is on port 3000; the home page is the Homelab Overview. Edits to `targets/*.json` are picked up by Prometheus without a restart.

Host Health, Docker Containers and Logs work with just the agents. Every other dashboard lights up as you connect the service it reads:

| To see | Add to `targets/` | Credentials in `secrets/` | Enable in `.env` |
|---|---|---|---|
| Service up/down, certificates (Overview) | `blackbox_http.json` (URLs), `blackbox_dns.json` (DNS servers) | — | — |
| Uptime Kuma monitors (Overview) | `uptime_kuma.json` | `uptime_kuma_api_key` | — |
| DNS / Pi-hole | `blackbox_dns.json` | `pihole-exporter.env` | — |
| Network / UniFi, Internet / ISP | — | `unpoller.env` (read-only local account) | — |
| NAS / Storage | `snmp.json` | `snmp-auth.yml` (SNMPv3) | `COMPOSE_PROFILES=snmp` |
| Smart Home | `homeassistant.json` | `home_assistant_token` | — |
| UPS / Power | `peanut.json` | `peanut_username`, `peanut_password` (PeaNUT 6's login; PeaNUT 5 ignores them) | — |
| Media Stack (*arr, SABnzbd, qBittorrent) | `media.json` (enabled exporters only) | `<app>.env` (URL, API key) | the app's profile, e.g. `radarr,sonarr` |
| Media Stack (Plex) | `plex.json` | `PLEX_TOKEN` in the Plex host's agent `.env` | `COMPOSE_PROFILES=plex` on that agent |
| Loki's own health | `loki.json` (`loki:3100` for the bundled one) | — | — |
| GitLab CI (pipelines) | `gitlab.json` | `gitlab.env` (`read_api` token), `gitlab.yml` (GitLab's URL) | `COMPOSE_PROFILES=gitlab` |
| GitLab CI (runner) | `gitlab_runner.json` (`<runner>:9252`); set `listen_address = ":9252"` in the runner's `config.toml` | — | — |
| GitLab CI (GitLab's health) | `gitlab_server.json` (`<gitlab>:9090`); set `prometheus['listen_address'] = '0.0.0.0:9090'` in `gitlab.rb` and run `gitlab-ctl reconfigure` (restarts Puma and Sidekiq: a minute or two of 502s) | — | — |
| ESXi / vCenter | `vsphere.json` (`telegraf-vsphere:9273` and `:9274`) | `vsphere.env` (vCenter URL + a read-only account), `vsphere-ca.pem` (vCenter's CA, from `https://<vcenter>/certs/download.zip`) | `COMPOSE_PROFILES=vsphere` |

To upgrade, pull new images (`docker compose pull && docker compose up -d`), or pin `ARGUS_VERSION` in `.env` to a release; see [docs/upgrading.md](docs/upgrading.md). New to Argus? The [quick start](docs/quick-start.md) runs it on one machine in about ten minutes.

**Security:** Prometheus (9090) and Loki (3101) accept pushes without authentication, so agents anywhere on the network can reach them; Prometheus can [require a password](docs/security.md#requiring-a-password-for-prometheus). Run Argus on a trusted network, and put Grafana behind a reverse proxy with TLS if it's reachable from outside (`docker-compose.proxy.yml` puts Grafana on the network of a proxy running in Docker on the same host, so its own port can listen on loopback only). What Argus does and doesn't protect against is in [docs/security.md](docs/security.md).

**Developing** — to edit dashboards, alert rules or configs live, run from the checkout instead of the published images by setting `COMPOSE_FILE=docker-compose.yml:docker-compose.source.yml` in `.env`. Grafana then reads `dashboards/` and `provisioning/` straight from the repo (dashboard edits show up within 30 seconds), and `docker compose up -d --build` rebuilds the images. In this mode, deploying is `git pull` on the server; restart the stack only when `docker-compose.yml`, `provisioning/` or a config changes. A systemd timer can do that for you once CI passes: see [docs/auto-deploy.md](docs/auto-deploy.md).

Releases are published by pushing a signed `v*.*.*` tag ([`.github/workflows/release.yml`](.github/workflows/release.yml)): the images are signed with cosign and carry an SBOM and provenance, and the GitHub Release gets its notes from [CHANGELOG.md](CHANGELOG.md) and a signed checksum file. [docs/verifying-releases.md](docs/verifying-releases.md) shows how to check them.

## Adding a host
Each monitored host runs one container, the **Argus agent** (`agent/`): Grafana Alloy with embedded node_exporter and cAdvisor that pushes host metrics, container metrics and container logs to the Argus server. Nothing on the server needs to change — the host appears in the dashboards as soon as the agent starts, and it only makes outbound connections (no firewall rules on the host).

```sh
docker run -d --name argus-agent --restart unless-stopped \
  --network host --pid host --privileged \
  -e ARGUS_HOST=my-host \
  -e ARGUS_PROMETHEUS_URL=http://argus-server:9090 \
  -e ARGUS_LOKI_URL=http://argus-server:3101 \
  -v /:/rootfs:ro,rslave -v /sys:/sys:ro -v /run/udev:/run/udev:ro -v /dev/disk:/dev/disk:ro \
  -v /var/lib/docker:/var/lib/docker:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /run/containerd:/run/containerd:ro \
  ghcr.io/honeybeartech/argus-agent:latest
```

Or copy `agent/compose.yml` and `agent/.env.example` (as `.env`) to the host and run `docker compose up -d`; pin `ARGUS_AGENT_IMAGE` to a release tag for predictable upgrades. The compose file also covers two extras:
- **Nginx Proxy Manager access logs** (Reverse Proxy Traffic dashboard): on the host running NPM, set `NPM_LOG_DIR` to its `data/logs` directory.
- **Plex** (Media Stack): on the Plex host (amd64), add the `plex` profile with `PLEX_SERVER` and `PLEX_TOKEN`, and list that host in the server's `targets/plex.json`.

The agent needs the server's Prometheus (9090) and Loki (3101) to be reachable from the host; those are the defaults. If Prometheus requires a password, add `-e ARGUS_PROMETHEUS_PASSWORD=...` (or set it in the agent's `.env`).

## Adding or changing a dashboard
1. Build or edit it in the sandbox Grafana, then **Export → Export as JSON** (leave "Export for sharing externally" off), or edit the JSON directly in VS Code.
2. Save it under `dashboards/<folder>/<name>.json` with a stable, hand-picked `uid`, `"id": null`, the `argus` tag, and a description saying what question it answers.
3. Reference datasources by uid (`prometheus`) — never by name or URL.
4. Run `python3 scripts/check_dashboards.py`. It also fails on private IP addresses and on internal names listed one regex per line in a gitignored `.forbidden-patterns` file (CI reads the same list from the `ARGUS_FORBIDDEN_PATTERNS` secret): **this repo is public**, so addresses stay in `targets/` and `.env`.

## Checks
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push and pull request: linters for Python, YAML, workflows, Dockerfiles and the agent config; unit tests with a coverage floor; the dashboard and public-repo checks; `promtool check config` and the [PromQL tests](tests/promql/), which run the shipped alert rule and dashboard queries against synthetic series; the blackbox, Loki and Alloy config checks; it builds every image, starts Grafana to check that every dashboard, alert rule and datasource loads, and validates the compose files.

Alongside it: [CodeQL](https://codeql.github.com/) analyses the Python checks and the workflows on every push and pull request and weekly, a weekly [Trivy](https://trivy.dev/) scan reports known vulnerabilities in the five images, [OpenSSF Scorecard](https://scorecard.dev/) scores the repo's supply-chain practices weekly (see the badge above), and Dependabot opens weekly PRs for the upstream images, GitHub Actions and the check tools. Image updates are merged by hand after a sandbox run. How dependencies are handled is in [docs/dependencies.md](docs/dependencies.md).

## Documentation
[docs/](docs/README.md) has the [quick start](docs/quick-start.md), [architecture](docs/architecture.md), [interfaces](docs/interfaces.md), [upgrading](docs/upgrading.md), [security requirements](docs/security.md) and [assurance case](docs/assurance-case.md), [dependency policy](docs/dependencies.md) and [roadmap](docs/roadmap.md). Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Contributing
Bug reports and ideas go in [GitHub Issues](https://github.com/HoneyBearTech/Argus/issues); see [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, coding standards, test policy and sign-off, [SECURITY.md](SECURITY.md) for reporting vulnerabilities privately, and [SUPPORT.md](SUPPORT.md) for which versions are supported. The project's [governance](GOVERNANCE.md) and [code of conduct](CODE_OF_CONDUCT.md) apply to everyone taking part.

## License
[MIT](LICENSE)
