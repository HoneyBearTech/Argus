# Argus

Grafana dashboards as code for the homelab — version-controlled JSON dashboards, edited in VS Code and provisioned into Grafana automatically.

## Before Making Structural Changes
Read the project's notes first. They live outside this repo, in the owner's Obsidian vault **Chronos** at `~/Chronos/Projects/Argus/` (every file is prefixed `argus-`):
- `argus-roadmap.md` — phases, open questions, what's in scope now vs. later
- `argus-Dashboard-Catalog.md` — which dashboards to build, the question each answers, and the data source/exporter each needs
- `argus-Inventory.md` — what's running on the network (hosts, VLANs, services, existing monitoring pieces)
- `argus-Architecture.md` — pipeline, hosting, repo layout, authoring and deploy conventions
- `argus-Security-Considerations.md` — public-repo rules, exporter credentials, exposure checklist
- `argus-Decisions-Log.md` — ADR-style log of why decisions were made (entries marked **Proposed** still need the owner's call)
- `argus-Pass-Map.md` — pass-by-pass delivery log; add a row when a pass ships

Update these files as the project evolves — they're the source of truth for project direction. New decisions get a dated entry in `argus-Decisions-Log.md`; roadmap checkboxes get ticked as dashboards land.

**The notes never go into this repo.** Chronos is versioned in its own private repo; only commit or push it when the owner asks.

## This repo is public
- No IP addresses, internal hostnames, internal domains or service maps in anything committed — dashboards, provisioning, docs or commit messages. That detail lives only in `argus-Inventory.md`.
- No secrets. Credentials come from environment variables or files outside the repo; `.gitignore` covers `.env`, `secrets/`, `*.key`, `*.pem` — extend it rather than working around it.
- Review exported dashboard JSON before committing: Grafana bakes current variable values and cached query text into exports.

## Conventions
- Every dashboard has a stable, hand-chosen `uid` and `"id": null`.
- Reference datasources by pinned UID (see `provisioning/datasources/`), never by name or a hard-coded URL.
- Tag every dashboard `argus`; put the one-line "question it answers" from the Dashboard Catalog in its description.

## Layout
- `docker-compose.yml` — Grafana (`grafana/grafana:13.2.2`) + Prometheus (`prom/prometheus:v3.14.0`) + blackbox_exporter (`prom/blackbox-exporter:v0.28.0`), used unchanged for production and the local sandbox; per-host settings in a gitignored `.env` (template: `.env.example`). Bump image versions here and in `.github/workflows/ci.yml` together.
- `dashboards/<folder>/*.json` — provisioned with `foldersFromFilesStructure`, `allowUiUpdates: false`.
- `provisioning/datasources/argus.yaml` — the only place datasource uids are defined.
- `prometheus/prometheus.yml` — scrape jobs; each job reads `targets/<job>.json` (`file_sd`). `targets/` is gitignored; `targets.example/` holds placeholders that CI validates.
- `blackbox/blackbox.yml` — probe modules only; which URLs/servers get probed lives in `targets/blackbox_*.json` (labels `service`, `group`).
- `agents/compose.yml` (+ `agents/alloy/`, `agents/.env.example`) — agents for a monitored Docker host: node_exporter (:9100, host network, read-only root mount) and cAdvisor (:9338, Docker containers only, heavy metric groups disabled); deployed by copying it to `~/argus-agent/` on each host and `docker compose up -d`. Targets in `targets/node.json` / `targets/cadvisor.json` with a `host` label. Pull images with a throwaway `DOCKER_CONFIG` — a host whose Docker credential store needs an interactive GPG unlock (`credsStore: pass`) can't pull non-interactively otherwise.
- `secrets/` (gitignored) — credentials: files Prometheus reads (`password_file` etc., mounted read-only) and env files for exporters (`pihole-exporter.env`, `unpoller.env`, loaded with `required: false` so the stack still starts without it); placeholders in `secrets.example/`.
- unpoller emits every UniFi device series once per UniFi device *tag*, so device queries must aggregate with `max by (name, ...)` or totals double-count. It refreshes every 30 s; UniFi panels set a 30 s minimum interval so `$__rate_interval` spans at least two updates.
- `snmp-exporter` is behind the `snmp` compose profile (`COMPOSE_PROFILES=snmp` in `.env`) because it needs `secrets/snmp-auth.yml`, which is mounted as a second `--config.file` next to the image's bundled `snmp.yml`. SNMP targets (`targets/snmp.json`) carry `module` and `auth` labels that become the scrape's URL params. Synology reports disk IDs hex-encoded; dashboards decode `Disk N` with `label_replace`.
- Alerting is provisioned from `provisioning/alerting/` (rules, Discord contact point, policy). Grafana refuses to start if a provisioned rule is invalid — always load changes in the sandbox first. A rule's `__dashboardUid__` annotation is only accepted together with `__panelId__`. Provisioning files expand environment variables (that's how `DISCORD_WEBHOOK_URL` gets in), so never name an env var like a template variable (`labels`, `values`).
- Home Assistant exports ~17k series; the `homeassistant` job keeps only the families in its `metric_relabel_configs` keep-list — add a family there before using it. HA exports Celsius; the Smart Home dashboard converts to Fahrenheit. Room/area names are personal, so queries select rooms by a generic rule (areas with a floor and exactly one sensor) and never name an area.
- Media exporters: one compose service per app (exportarr ×8 instances, qbittorrent-exporter), each behind a profile named after the app and reading `secrets/<profile>.env`; `targets/media.json` lists only enabled ones (with an `app` label) so missing apps never raise "target down". The `media` job drops `qbittorrent_torrent_*` (per-torrent, ~11k series). The Plex exporter image is amd64-only, so it runs beside Plex in `agents/compose.yml` (`plex` profile, `PLEX_SERVER`/`PLEX_TOKEN` in that host's `~/argus-agent/.env`); Prometheus scrapes it in its own 30 s `plex` job (`targets/plex.json`). A session is "live" while `rate(play_seconds_total[2m]) > 0`. On play metrics the exporter swaps labels: `title` is the show or movie, `child_title` the season, `grandchild_title` the episode, and the library name is in `library_type`. Test a Plex token from inside a container — Plex can exempt LAN clients from auth, which makes a bad token look good.
- Logs: Loki runs from `logs/compose.yml` on the host with the most disk (not necessarily the main stack's host), port 3101, 30-day retention. Alloy (`agents/alloy/config.alloy`, `logs` profile in `agents/compose.yml`) ships Docker container logs (labels `host`, `container`, `compose_project`, `job="docker"`) and, where `NPM_LOG_DIR` is set, Nginx Proxy Manager access logs (`job="npm"`, labels `site`, `status`, `method`; Argus' own Blackbox probes dropped). Alloy drops lines older than an hour so first-start backfill doesn't hit Loki's age limit. Grafana's Loki datasource (uid `loki`) takes its URL from `LOKI_URL`. Loki bar gauges need `reduceOptions.values: true` — Grafana's Loki plugin returns instant metric results as one table.
- Grafana's home page is `dashboards/overview/homelab-overview.json` (`GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`).

## Commands
```sh
python3 scripts/check_dashboards.py   # dashboard + public-repo checks (also run in CI)
                                      # internal names it rejects: gitignored .forbidden-patterns locally,
                                      # ARGUS_FORBIDDEN_PATTERNS repo secret in CI — keep the two in sync
docker compose up -d                  # start / apply compose changes
docker compose restart prometheus     # after editing prometheus/prometheus.yml
```
Adding a scrape job: add it to `prometheus/prometheus.yml` with a `file_sd_configs` entry, add a placeholder in `targets.example/`, and put the real target in `targets/` on each host.
