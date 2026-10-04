# Argus
Grafana dashboards as code for my homelab. Version-controlled JSON dashboards for Docker hosts, the Plex/arr media stack, reverse proxy traffic, and network health, edited in VS Code and provisioned automatically.

## How it works
Grafana, Prometheus, blackbox_exporter, pihole-exporter, unpoller and (optionally) snmp-exporter run from [`docker-compose.yml`](docker-compose.yml). Grafana loads every dashboard under [`dashboards/`](dashboards/) through file provisioning — each subfolder becomes a Grafana folder, and UI edits are blocked so this repo stays the source of truth. The same compose file runs production and a local sandbox; per-host settings come from a gitignored `.env`.

```
dashboards/          dashboard JSON, one folder per Grafana folder
provisioning/        Grafana datasources (pinned uids) and the dashboard provider
prometheus/          Prometheus config — scrape jobs, no addresses
blackbox/            blackbox_exporter probe modules (HTTP service check, DNS resolve)
agents/              agents that run on the monitored hosts (node-exporter, cAdvisor, Alloy for logs, Plex exporter)
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
| Host Health | hosts | Is any machine running out of disk, memory or CPU? | node_exporter on each host (`agents/compose.yml`) |
| Docker Containers | hosts | Which containers are restarting, stopped, or eating resources? | cAdvisor on each Docker host (`agents/compose.yml`) |
| Network / UniFi | network | How's the internet connection, and what's on the network? | [unpoller](https://github.com/unpoller/unpoller) with a read-only UniFi account |
| Media Stack | media | Who's watching what, is the download pipeline flowing, and is the library healthy? | [exportarr](https://github.com/onedr0p/exportarr) (*arr, SABnzbd), [qbittorrent-exporter](https://github.com/martabal/qbittorrent-exporter); Plex exporter beside Plex (`agents/compose.yml`, `plex` profile) |
| NAS / Storage | storage | Are the NAS units healthy, and how fast are they filling? | snmp-exporter (bundled `synology` + standard MIB modules), SNMPv3 |
| Smart Home | home | What's the house doing — temperatures, HVAC, energy? | Home Assistant's Prometheus integration (long-lived token) |
| Reverse Proxy Traffic | network | What's hitting the services behind the reverse proxy, and is anything erroring? | Nginx Proxy Manager access logs → Alloy → Loki |
| Logs | hosts | What did a host or container log around the time something broke? | Docker container logs → Alloy → Loki |
| UPS / Power | power | How long would the lab survive a power cut, and is the UPS healthy? | [PeaNUT](https://github.com/Brandawg93/PeaNUT) `/api/v1/metrics` |

## Alerts
Grafana-managed alert rules live in [`provisioning/alerting/rules.yaml`](provisioning/alerting/rules.yaml) (edit there — UI changes are blocked) and notify a Discord channel through the webhook in `DISCORD_WEBHOOK_URL` (production `.env` only; a sandbox gets a dummy URL so it can't post). Each rule is a raw PromQL measurement (`A`) plus a threshold (`C`), one alert per series:

| Group | Rules |
|---|---|
| Availability | host agent down, service down (only services that were up at some point in the last 7 days), DNS server not answering, monitoring target down |
| Capacity | disk > 90 %, NAS storage pool > 90 %, certificate < 14 days |
| Power and hardware | UPS on battery, UPS battery < 50 %, NAS disk unhealthy, NAS pool degraded, NAS disk > 55 °C, network device > 85 °C |
| Network | internet on backup WAN, internet dropped, Pi-hole blocklists out of sync |
| Containers | container restarted more than 3 times in an hour |

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

## Adding a host to Host Health
On a Docker host: copy the `agents/` directory to the host (e.g. `~/argus-agent/`), create `.env` there from `agents/.env.example` (host name, Loki URL, profiles), and run `docker compose up -d`. It starts node-exporter (port 9100, host network — open it to the Prometheus host if the host runs a firewall, e.g. `sudo ufw allow from <prometheus-host> to any port 9100 proto tcp`) and cAdvisor (port 9338, published by Docker, so `ufw` doesn't block it). Then add the host to `targets/node.json` and `targets/cadvisor.json` with the same `host` label.

## Adding or changing a dashboard
1. Build or edit it in the sandbox Grafana, then **Export → Export as JSON** (leave "Export for sharing externally" off), or edit the JSON directly in VS Code.
2. Save it under `dashboards/<folder>/<name>.json` with a stable, hand-picked `uid`, `"id": null`, the `argus` tag, and a description saying what question it answers.
3. Reference datasources by uid (`prometheus`) — never by name or URL.
4. Run `python3 scripts/check_dashboards.py`. It also fails on private IP addresses and on internal names listed one regex per line in a gitignored `.forbidden-patterns` file (CI reads the same list from the `ARGUS_FORBIDDEN_PATTERNS` secret): **this repo is public**, so addresses stay in `targets/` and `.env`.

## Checks
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the dashboard checks, `promtool check config`, and `docker compose config` on every push and pull request.
