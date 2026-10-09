# Architecture

Argus is monitoring for a home lab, built from standard open-source components (Grafana, Prometheus,
Loki, blackbox_exporter, Grafana Alloy and a set of exporters) and the configuration that ties them
together: dashboards, alert rules, scrape jobs, probe modules and the agent pipeline. Argus writes no
server code of its own; what it ships is that configuration, baked into images, plus the checks and tests
that keep it correct.

## Components

```
 monitored host (one per host)                    Argus server (one host)
┌───────────────────────────────┐   push   ┌────────────────────────────────────────────────┐
│ argus-agent (Grafana Alloy)   │─────────▶│ Prometheus :9090  ◀── scrapes ── exporters     │
│  ├ node_exporter (host)       │ metrics  │   │  remote-write        (Pi-hole, UniFi, SNMP, │
│  ├ cAdvisor (containers)      │          │   │  receiver             media apps, …)       │
│  └ Docker / NPM log tailing   │─────────▶│ Loki :3101 (or on another host)                 │
└───────────────────────────────┘   logs   │   │        blackbox_exporter ── probes ──▶ URLs, │
                                           │   ▼                                    DNS      │
                                           │ Grafana :3000 ── dashboards, alert rules        │
                                           └──────────────────────┬─────────────────────────┘
                                                                  ▼ alerts
                                                           Discord webhook
```

| Component | Image | Role |
| --- | --- | --- |
| **Argus agent** | `argus-agent` (Grafana Alloy + [`agent/config.alloy`](../agent/config.alloy)) | One container per monitored host. Embedded node_exporter and cAdvisor collect host and container metrics, which it **pushes** to Prometheus (remote write); it tails Docker container logs and, where configured, Nginx Proxy Manager access logs and pushes them to Loki. It only makes outbound connections. |
| **Prometheus** | `argus-prometheus` ([`prometheus/prometheus.yml`](../prometheus/prometheus.yml)) | Stores metrics for 30 days or 8 GB. Accepts agent pushes, and **scrapes** the exporters and the probe results; which targets is read from `targets/*.json` on the server (file service discovery), so no addresses live in the repo. |
| **blackbox_exporter** | `argus-blackbox` ([`blackbox/blackbox.yml`](../blackbox/blackbox.yml)) | Probes web services (HTTP status, TLS certificate) and DNS servers on Prometheus' behalf. Not published on the host. |
| **Exporters** | upstream images, pinned in [`docker-compose.yml`](../docker-compose.yml) | Translate a service's API into metrics: pihole-exporter, unpoller (UniFi), snmp-exporter (NAS), exportarr and qbittorrent-exporter (media apps), gitlab-ci-pipelines-exporter (GitLab CI, through GitLab's API), the Plex exporter (beside Plex, from `agent/compose.yml`). Home Assistant, PeaNUT and Uptime Kuma expose metrics themselves. Each reads its credentials from `secrets/`. |
| **Loki** | `argus-loki` ([`logs/loki.yaml`](../logs/loki.yaml)) | Stores logs for 30 days. Runs in the main stack (`loki` profile) or on a host with more disk ([`logs/compose.yml`](../logs/compose.yml)). |
| **Grafana** | `argus-grafana` (dashboards, datasources and alerting baked in) | Dashboards, the alert rules and the Discord contact point, all provisioned from files; editing them in the UI is blocked, so the repository stays the source of truth. |

## How data flows

1. **Metrics.** Agents push host (`job="node"`) and container (`job="cadvisor"`) series every 15–30 s,
   labelled with the host's name (`host`). Prometheus scrapes everything else on its own schedule
   (15 s by default, 30–60 s for slower exporters), with targets and their labels from `targets/`.
2. **Probes.** For each URL in `targets/blackbox_http.json` (and DNS server in `blackbox_dns.json`),
   Prometheus asks blackbox_exporter to probe it and stores `probe_success`, timings and certificate
   expiry.
3. **Logs.** The agent reads container logs through the Docker socket, labels them (`host`, `container`,
   `compose_project`), drops lines older than an hour (first-start backfill) and pushes them to Loki.
   GitLab Runner's CI job containers are skipped, for both logs and container metrics. NPM
   access logs are parsed into `site`, `status` and `method`, and Argus' own probes are dropped.
4. **Dashboards.** Grafana queries Prometheus (PromQL) and Loki (LogQL) through datasources with fixed
   uids (`prometheus`, `loki`), so dashboards keep working on any installation.
5. **Alerts.** Grafana evaluates the [alert rules](../provisioning/alerting/rules.yaml) every 1–5 minutes:
   each rule is a query (`A`) and a threshold (`C`), one alert per series. Firing and resolved alerts go
   to Discord, grouped per rule and repeated every 12 hours.

A silent agent is detected as "series that existed in the last day but not now", since pushed metrics
have no scrape `up` to go to 0.

## From repository to running system

- **Images.** Each server image is a pinned upstream image (by version and digest) with Argus' files
  copied in ([`images/`](../images/), [`agent/Dockerfile`](../agent/Dockerfile)). A version tag makes the
  release workflow build all five for amd64 and arm64, sign them and publish them to GHCR and Docker Hub
  ([verifying-releases.md](verifying-releases.md)).
- **Installation.** `docker-compose.yml` runs the published images; what is specific to one network stays
  on the server: `.env` (settings), `targets/` (what to watch) and `secrets/` (credentials), all
  gitignored. Upgrading is changing `ARGUS_VERSION` ([upgrading.md](upgrading.md)).
- **Development.** `docker-compose.source.yml` builds the images from the checkout and bind-mounts
  `dashboards/`, `provisioning/` and the configs, so edits show up without a rebuild.

## Key properties

- **Configuration as code.** Every dashboard, alert rule, datasource, scrape job and probe module is a
  file in this repository, reviewed in a pull request, checked and tested in CI
  ([CONTRIBUTING.md](../CONTRIBUTING.md#when-and-how-tests-run)) and provisioned read-only.
- **Nothing private in the repository.** Addresses, host names and credentials live only on the server;
  CI rejects private IP addresses and a private list of internal names in any committed file.
- **Push from hosts, pull from services.** A new host needs only the agent, no server change or firewall
  rule; services that can't run an agent are scraped.
- **Bounded resources.** Retention limits on Prometheus (time and size) and Loki (time, ingestion rate),
  keep-lists and drop rules for exporters that emit too many series (Home Assistant, qBittorrent), and
  cAdvisor's expensive metric groups turned off.

## Technology

| Area | Choice |
| --- | --- |
| Dashboards and alerting | Grafana 13 (provisioned dashboards, Grafana-managed alert rules) |
| Metrics | Prometheus 3 (remote-write receiver, file service discovery), PromQL |
| Logs | Loki 3 (single process, filesystem storage, TSDB index), LogQL |
| Agent | Grafana Alloy 1.x with embedded node_exporter and cAdvisor |
| Probes | blackbox_exporter |
| Packaging | Docker images (amd64, arm64), Docker Compose |
| Checks and tests | Python 3 (pytest, ruff, yamllint), promtool, actionlint, hadolint, GitHub Actions |
