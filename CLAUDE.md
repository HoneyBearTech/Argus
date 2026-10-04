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
- `docker-compose.yml` — Grafana (`grafana/grafana:13.2.2`) + Prometheus (`prom/prometheus:v3.14.0`), used unchanged for production and the local sandbox; per-host settings in a gitignored `.env` (template: `.env.example`). Bump image versions here and in `.github/workflows/ci.yml` together.
- `dashboards/<folder>/*.json` — provisioned with `foldersFromFilesStructure`, `allowUiUpdates: false`.
- `provisioning/datasources/argus.yaml` — the only place datasource uids are defined.
- `prometheus/prometheus.yml` — scrape jobs; each job reads `targets/<job>.json` (`file_sd`). `targets/` is gitignored; `targets.example/` holds placeholders that CI validates.

## Commands
```sh
python3 scripts/check_dashboards.py   # dashboard + public-repo checks (also run in CI)
                                      # internal names it rejects: gitignored .forbidden-patterns locally,
                                      # ARGUS_FORBIDDEN_PATTERNS repo secret in CI — keep the two in sync
docker compose up -d                  # start / apply compose changes
docker compose restart prometheus     # after editing prometheus/prometheus.yml
```
Adding a scrape job: add it to `prometheus/prometheus.yml` with a `file_sd_configs` entry, add a placeholder in `targets.example/`, and put the real target in `targets/` on each host.
