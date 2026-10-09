# Changelog

All notable changes to Argus are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Before 1.0.0, a minor version may include changes that need
steps when upgrading; those are listed under "Upgrading" and in [docs/upgrading.md](docs/upgrading.md).
Each release's notes on GitHub are its section here.

## [Unreleased]

### Fixed

- [docs/verifying-releases.md](docs/verifying-releases.md) asked for cosign 2.0 or later, but release
  images are signed with cosign 3, whose signatures cosign 2 can't find. It now says 3.0 or later.

## [0.4.0] - 2026-10-09

### Upgrading

- Agents: copy the new `agent/compose.yml` to each host (it mounts `/run/containerd`, see Fixed) and set
  `ARGUS_AGENT_IMAGE` to `0.4.0`, then `docker compose up -d`. On a host that runs GitLab Runner with the
  Docker executor, upgrade the agent before (or instead of) running 0.3.0 or earlier there: older agents
  ship CI job output to Loki.

### Added

- GitLab CI dashboard: the latest pipeline on each branch and tag, a status history, pipeline and job
  durations, how long jobs wait for a runner, and the latest run of every job with its failure reason. It
  reads GitLab's API through [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter),
  behind the new `gitlab` compose profile: put GitLab's URL in `secrets/gitlab.yml`, a `read_api` token in
  `secrets/gitlab.env` (templates in `secrets.example/`) and the exporter in `targets/gitlab.json`.

### Security

- The agent no longer reads the logs of GitLab Runner's CI job containers (Docker executor). Docker keeps
  their raw output, without the masking GitLab applies to secrets in job logs, so masked CI variables a job
  printed could reach Loki. Those containers are also left out of container metrics, where each job would
  have added a short-lived container. Takes effect when the agent runs the new image.

### Fixed

- The agent showed no container metrics on hosts whose Docker uses the containerd image store, the default
  for new installs since Docker 29: cAdvisor couldn't reach containerd. `agent/compose.yml` now mounts
  `/run/containerd` read-only; if you run the agent with `docker run`, add
  `-v /run/containerd:/run/containerd:ro`.
- Auto-deploy's health check crashed instead of reporting "not answering" when something other than an
  HTTP server answered on Grafana's or Prometheus' port.

## [0.3.0] - 2026-10-05

### Upgrading

- Grafana now runs only the plugins in the image: the Prometheus and Loki datasources and Grafana's
  built-in panels. It no longer downloads plugins from grafana.com at start-up, so the Explore
  "Drilldown" apps (metrics, logs, traces, profiles) and the Advisor app are gone. Plugins earlier
  versions downloaded into the `grafana_data` volume are ignored; to reclaim the space, run
  `docker compose exec grafana sh -c 'rm -rf /var/lib/grafana/plugins/*'`.

### Added

- Internet / ISP dashboard: the UniFi gateway's speed tests over time against the plan speeds set in UniFi,
  how long ago the last test ran, latency and connectivity drops. It needs nothing beyond unpoller. The
  gateway measures from the edge of the network, so the results aren't capped by a server's network card.
- Optional auto-deploy for servers that run from a checkout: a systemd timer ([deploy/systemd/](deploy/systemd/))
  runs `scripts/auto_deploy.py`, which fast-forwards to `main` once its CI check has passed, rebuilds, restarts
  what reads a changed config, and rolls back if Grafana or Prometheus don't come back. Deploys and
  rollbacks are posted to Discord. See [docs/auto-deploy.md](docs/auto-deploy.md).

### Changed

- `argus-grafana` keeps only the Prometheus and Loki datasource plugins (removing Grafana's other
  bundled ones), turns off Grafana's plugin preinstaller and reads plugins from a directory inside the
  image (`GF_PATHS_PLUGINS`), so what runs is what was signed and scanned. Adding a datasource of another
  type now means extending the image.
- Release images are built without a build cache. The cache was written per release tag, where no later
  release could read it, and filled 1.6 GB of the repository's Actions storage per release.

### Security

- `argus-agent` applies Ubuntu's security updates to its base image, fixing CVE-2026-84782 (OpenSSL,
  HIGH), which Grafana Alloy v1.20.1's image still contains. The agent runs as root on every host, so
  upgrade the agents.
- `argus-grafana` drops seven of Grafana's eight HIGH findings (gRPC and Tempo libraries in bundled plugins
  Argus doesn't use) by removing those plugins. Before 0.3.0, Grafana also downloaded 18 plugins from
  grafana.com at start-up into its data volume, where they took precedence over the image's own copies,
  so the datasource code that ran was neither signed by the release nor covered by the image scan. The remaining one, CVE-2026-84445 in the Prometheus
  plugin, is waiting on a Grafana release; see
  [docs/dependencies.md](docs/dependencies.md#current-findings).

## [0.2.0] - 2026-10-05

### Upgrading

- unpoller now verifies the UniFi console's TLS certificate. If your console still uses its factory
  self-signed certificate, set `UNIFI_VERIFY_SSL=false` in `.env` before upgrading, or the Network /
  UniFi dashboard goes empty.

### Added

- Releases are signed: every image is signed keylessly with cosign (Sigstore) and carries an SBOM and SLSA
  provenance, and each GitHub Release has a source archive, the image digests, a signed `SHA256SUMS` and
  SLSA build provenance. Version tags are signed with the maintainer's SSH key. How to check:
  [docs/verifying-releases.md](docs/verifying-releases.md).
- Release notes come from this changelog, with repository links pointing at the release's tag.
- CI now starts the Grafana image and checks that every dashboard, alert rule, datasource and the contact
  point loads, so an invalid alert rule fails the pull request instead of the server.
- PromQL tests: the shipped alert rule and dashboard queries run against synthetic series with
  `promtool test rules` ([tests/promql/](tests/promql/)), including regression tests for the false alerts
  fixed in 0.1.0.
- Unit tests for the repo checks, with a coverage floor, and linting for Python (ruff), YAML (yamllint),
  workflows (actionlint), Dockerfiles (hadolint) and the agent config (`alloy fmt`), all in CI.
- A weekly vulnerability scan of the five images (Trivy), reported to code scanning.
- Project documentation: [governance](GOVERNANCE.md), [support](SUPPORT.md), the
  [code of conduct](CODE_OF_CONDUCT.md), and in [docs/](docs/README.md) a quick start, architecture,
  interfaces, security requirements, assurance case, dependency policy, roadmap and upgrade guide.
- Contributions need a Developer Certificate of Origin sign-off, checked on every pull request.
- An MIT [license](LICENSE), a [security policy](SECURITY.md) for reporting vulnerabilities, and a
  [contributing guide](CONTRIBUTING.md).

### Changed

- Grafana 13.2.2 → 13.2.3 and Prometheus v3.14.0 → v3.15.0 in the `argus-grafana` and `argus-prometheus`
  images.
- Every upstream base image is pinned by digest as well as version tag, so a re-pushed upstream tag can't
  change what an Argus release builds from.
- `UNIFI_VERIFY_SSL` (default `true`) controls unpoller's certificate check, which used to be off.
- `check_dashboards.py` also checks that dashboards keep Grafana's 2-space JSON format (`--fix` rewrites
  them).
- The `argus-blackbox` image runs as an unprivileged user (65534) instead of root; Argus' HTTP and DNS
  probes don't need root.
- `agent/config.alloy` is formatted with `alloy fmt` (whitespace only).

### Security

- No vulnerabilities in Argus itself. The new weekly image scan reports upstream Go standard library,
  `golang.org/x/net`, `golang.org/x/crypto` and gRPC vulnerabilities in blackbox_exporter v0.28.0, the
  latest upstream release; the assessment and plan are in
  [docs/dependencies.md](docs/dependencies.md#current-findings). The blackbox image now runs unprivileged,
  and unpoller now verifies the UniFi console's certificate by default.

## [0.1.0] - 2026-10-04

First published release: Grafana dashboards, alert rules and a per-host agent for monitoring a homelab,
shipped as Docker images for amd64 and arm64 on GHCR and Docker Hub.

### Added

- Images `argus-grafana` (Grafana 13.2.2 with every dashboard, datasource and alert rule baked in),
  `argus-prometheus` (Prometheus v3.14.0 with the scrape config; accepts pushes from agents),
  `argus-blackbox` (blackbox_exporter v0.28.0 with the HTTP and DNS probe modules), `argus-loki` (Loki
  3.7.8, single process, 30-day retention) and `argus-agent` (Grafana Alloy with embedded node_exporter
  and cAdvisor; pushes host metrics, container metrics and container logs).
- 11 dashboards: Homelab Overview, DNS / Pi-hole, Host Health, Docker Containers, Logs, Network / UniFi,
  Reverse Proxy Traffic, NAS / Storage, Smart Home, Media Stack (including Plex), UPS / Power.
- 19 alert rules with a Discord contact point: availability, capacity, power and hardware, network,
  containers, logs.
- Push-model agent: one container per host, outbound connections only, no per-host server config.

### Fixed

- A 403 answer no longer counts as a service being up: a reverse proxy's access list answers 403 without
  reaching the service (#3).
- "Service down" fired on a single failed probe and for services that had never really been up; "Disk
  almost full" fired for network shares already covered by the NAS pool rule (#15).
- Host Health's "Load per core" failed while a host briefly had two load series (#17).

### Security

- No vulnerabilities fixed in this release. Prometheus and Loki accept pushes without authentication; run
  Argus on a trusted network.

[Unreleased]: https://github.com/HoneyBearTech/Argus/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/HoneyBearTech/Argus/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HoneyBearTech/Argus/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HoneyBearTech/Argus/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HoneyBearTech/Argus/releases/tag/v0.1.0
