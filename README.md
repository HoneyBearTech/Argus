# Argus
Grafana dashboards as code for my homelab. Version-controlled JSON dashboards for Docker hosts, the Plex/arr media stack, reverse proxy traffic, and network health, edited in VS Code and provisioned automatically.

## How it works
Grafana, Prometheus, blackbox_exporter, pihole-exporter, unpoller and (optionally) snmp-exporter run from [`docker-compose.yml`](docker-compose.yml). Grafana loads every dashboard under [`dashboards/`](dashboards/) through file provisioning — each subfolder becomes a Grafana folder, and UI edits are blocked so this repo stays the source of truth. The same compose file runs production and a local sandbox; per-host settings come from a gitignored `.env`.

```
dashboards/          dashboard JSON, one folder per Grafana folder
provisioning/        Grafana datasources (pinned uids) and the dashboard provider
prometheus/          Prometheus config — scrape jobs, no addresses
blackbox/            blackbox_exporter probe modules (HTTP service check, DNS resolve)
agent/               the Argus agent image (Grafana Alloy + config) and its compose file, one per monitored host
logs/                Loki, the log store, for the host with the most disk
targets.example/     placeholder scrape/probe targets; real ones go in targets/ (gitignored)
secrets.example/     placeholder credentials Prometheus scrapes with; real ones go in secrets/ (gitignored)
scripts/             repo checks, run in CI
```

## Dashboards
| Dashboard | Folder | Answers | Data |
|---|---|---|---|
| Homelab Overview (home page) | overview | Is everything up right now, and if not, what? | [Uptime Kuma](https://github.com/louislam/uptime-kuma) `/metrics`, blackbox_exporter HTTP + DNS probes |
| DNS / Pi-hole | dns | Is DNS healthy and consistent, and what's being blocked? | [pihole-exporter](https://github.com/eko/pihole-exporter) (Pi-hole v6 API), blackbox DNS probes |
| Host Health | hosts | Is any machine running out of disk, memory or CPU? | Argus agent on each host (embedded node_exporter) |
| Docker Containers | hosts | Which containers are restarting, stopped, or eating resources? | Argus agent on each host (embedded cAdvisor) |
| Network / UniFi | network | How's the internet connection, and what's on the network? | [unpoller](https://github.com/unpoller/unpoller) with a read-only UniFi account |
| Media Stack | media | Who's watching what, is the download pipeline flowing, and is the library healthy? | [exportarr](https://github.com/onedr0p/exportarr) (*arr, SABnzbd), [qbittorrent-exporter](https://github.com/martabal/qbittorrent-exporter); Plex exporter beside Plex (`agent/compose.yml`, `plex` profile) |
| NAS / Storage | storage | Are the NAS units healthy, and how fast are they filling? | snmp-exporter (bundled `synology` + standard MIB modules), SNMPv3 |
| Smart Home | home | What's the house doing — temperatures, HVAC, energy? | Home Assistant's Prometheus integration (long-lived token) |
| Reverse Proxy Traffic | network | What's hitting the services behind the reverse proxy, and is anything erroring? | Nginx Proxy Manager access logs → Alloy → Loki |
| Logs | hosts | What did a host or container log around the time something broke? | Docker container logs → Alloy → Loki |
| UPS / Power | power | How long would the lab survive a power cut, and is the UPS healthy? | [PeaNUT](https://github.com/Brandawg93/PeaNUT) `/api/v1/metrics` |

## Alerts
Grafana-managed alert rules live in [`provisioning/alerting/rules.yaml`](provisioning/alerting/rules.yaml) (edit there — UI changes are blocked) and notify a Discord channel through the webhook in `DISCORD_WEBHOOK_URL` (production `.env` only; a sandbox gets a dummy URL so it can't post). Each rule is a raw PromQL measurement (`A`) plus a threshold (`C`), one alert per series:

| Group | Rules |
|---|---|
| Availability | host stopped reporting (its agent went silent), service down (only services that were up for at least an hour in the last 7 days), DNS server not answering, monitoring target down |
| Capacity | local disk > 90 % (network shares are covered by the NAS pool rule), NAS storage pool > 90 %, certificate < 14 days |
| Power and hardware | UPS on battery, UPS battery < 50 %, NAS disk unhealthy, NAS pool degraded, NAS disk > 55 °C, network device > 85 °C |
| Network | internet on backup WAN, internet dropped, Pi-hole blocklists out of sync |
| Containers | container restarted more than 3 times in an hour |
| Logs | a site returning > 20 server errors (5xx) in 10 minutes, log pipeline stalled (Loki receiving almost nothing for 15 minutes) |

Alerts are grouped per rule and repeat every 12 hours while firing.

## Running it
```sh
cp .env.example .env              # set GF_SECURITY_ADMIN_PASSWORD, ports, root URL
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp secrets.example/* secrets/
# then put real addresses in targets/ and real credentials in secrets/
docker compose up -d
```
Grafana is on `GRAFANA_BIND` (default `127.0.0.1:3000`). Edits to dashboard JSON are picked up within 30 seconds; edits to `targets/*.json` are picked up by Prometheus without a restart.

To deploy, `git pull` on the production host — provisioning reloads the dashboards on its own. Restart the stack only when `docker-compose.yml`, `provisioning/` or `prometheus/` change (`docker compose up -d`, plus `docker compose restart prometheus` for a config change).

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
  ghcr.io/honeybeartech/argus-agent:latest
```

Or copy `agent/compose.yml` and `agent/.env.example` (as `.env`) to the host and run `docker compose up -d`. The server's Prometheus must be reachable from the host (`PROMETHEUS_BIND=0.0.0.0:9090`) and is started with `--web.enable-remote-write-receiver`.

## Adding or changing a dashboard
1. Build or edit it in the sandbox Grafana, then **Export → Export as JSON** (leave "Export for sharing externally" off), or edit the JSON directly in VS Code.
2. Save it under `dashboards/<folder>/<name>.json` with a stable, hand-picked `uid`, `"id": null`, the `argus` tag, and a description saying what question it answers.
3. Reference datasources by uid (`prometheus`) — never by name or URL.
4. Run `python3 scripts/check_dashboards.py`. It also fails on private IP addresses and on internal names listed one regex per line in a gitignored `.forbidden-patterns` file (CI reads the same list from the `ARGUS_FORBIDDEN_PATTERNS` secret): **this repo is public**, so addresses stay in `targets/` and `.env`.

## Checks
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the dashboard checks, `promtool check config`, and `docker compose config` on every push and pull request.
