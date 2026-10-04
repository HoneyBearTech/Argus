# Argus
Grafana dashboards as code for my homelab. Version-controlled JSON dashboards for Docker hosts, the Plex/arr media stack, reverse proxy traffic, and network health, edited in VS Code and provisioned automatically.

## How it works
Grafana and Prometheus run from [`docker-compose.yml`](docker-compose.yml). Grafana loads every dashboard under [`dashboards/`](dashboards/) through file provisioning — each subfolder becomes a Grafana folder, and UI edits are blocked so this repo stays the source of truth. The same compose file runs production and a local sandbox; per-host settings come from a gitignored `.env`.

```
dashboards/          dashboard JSON, one folder per Grafana folder
provisioning/        Grafana datasources (pinned uids) and the dashboard provider
prometheus/          Prometheus config — scrape jobs, no addresses
targets.example/     placeholder scrape targets; real ones go in targets/ (gitignored)
scripts/             repo checks, run in CI
```

## Dashboards
| Dashboard | Folder | Answers | Data |
|---|---|---|---|
| UPS / Power | power | How long would the lab survive a power cut, and is the UPS healthy? | [PeaNUT](https://github.com/Brandawg93/PeaNUT) `/api/v1/metrics` |

## Running it
```sh
cp .env.example .env              # set GF_SECURITY_ADMIN_PASSWORD, ports, root URL
mkdir -p targets && cp targets.example/*.json targets/   # then put real addresses in targets/
docker compose up -d
```
Grafana is on `GRAFANA_BIND` (default `127.0.0.1:3000`). Edits to dashboard JSON are picked up within 30 seconds; edits to `targets/*.json` are picked up by Prometheus without a restart.

To deploy, `git pull` on the production host — provisioning reloads the dashboards on its own. Restart the stack only when `docker-compose.yml`, `provisioning/` or `prometheus/` change (`docker compose up -d`, plus `docker compose restart prometheus` for a config change).

## Adding or changing a dashboard
1. Build or edit it in the sandbox Grafana, then **Export → Export as JSON** (leave "Export for sharing externally" off), or edit the JSON directly in VS Code.
2. Save it under `dashboards/<folder>/<name>.json` with a stable, hand-picked `uid`, `"id": null`, the `argus` tag, and a description saying what question it answers.
3. Reference datasources by uid (`prometheus`) — never by name or URL.
4. Run `python3 scripts/check_dashboards.py`. It also fails on private IP addresses and on internal names listed one regex per line in a gitignored `.forbidden-patterns` file (CI reads the same list from the `ARGUS_FORBIDDEN_PATTERNS` secret): **this repo is public**, so addresses stay in `targets/` and `.env`.

## Checks
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the dashboard checks, `promtool check config`, and `docker compose config` on every push and pull request.
