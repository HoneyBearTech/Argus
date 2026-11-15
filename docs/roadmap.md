# Roadmap

What Argus intends to do through October 2027, and what it deliberately won't
do. Plans change; this file is updated when they do, and larger items get a
GitHub issue before work starts. Suggestions are welcome in
[Issues](https://github.com/HoneyBearTech/Argus/issues).

## Where it stands

As of November 2026, the latest release is **0.9.0** (29 October). The current
checkout contains 26 dashboards and 47 provisioned alert rules, with alerts
sent to Discord by default. It covers hosts, containers, logs, databases, network and ISP
health, storage, smart home, media, power, server hardware, GPUs, deployments,
GitLab, Steerhouse and vLLM. See the [README](../README.md) for the full inventory
and [changelog](../CHANGELOG.md) for release and unreleased changes.

The server runs with Docker Compose on Linux. A one-container push agent runs
on Docker hosts; since 0.9.0, the same image also runs as a Kubernetes DaemonSet
for node metrics, container metrics and pod logs
([kubernetes.md](kubernetes.md)). Most images support amd64 and arm64; the
Intel GPU exporter image is amd64 only.

Already delivered from the original roadmap:

- GitLab runner metrics and GitLab server health, alongside pipelines and jobs,
  on the GitLab CI dashboard.
- Internet speed history and connection-drop monitoring on the Internet / ISP
  dashboard, using the UniFi gateway's speed tests.
- Optional [Prometheus password
  protection](security.md#requiring-a-password-for-prometheus),
  including agents that push with credentials. Agent traffic crossing an
  untrusted network uses the optional authenticated
  TLS push proxy; Loki itself has no built-in authentication.
- Documented [upgrade and rollback procedures](upgrading.md), plus optional
  [automatic source deployments](auto-deploy.md) after the required check
  passes, with health checks and rollback.

The project checks lint, unit tests, PromQL and configuration, builds images,
and starts Grafana to validate provisioning. Releases include signed images,
SBOMs and provenance ([verifying-releases.md](verifying-releases.md)).

## Implemented in the current checkout

The following items are implemented as unreleased changes. They become
available to published-image users when the corresponding images are released.

### Security and operations

- [Authenticated TLS push endpoints](push-security.md) for Prometheus and
  Loki, with agent credentials, loopback native listeners and an integration
  test that exercises TLS verification, authentication and path restrictions.
- [Notification channels](notifications.md): e-mail, Slack-compatible incoming
  webhooks and ntfy, provisioned through an optional Compose overlay selected
  in `.env`. Grafana provisioning tests load each channel.
- [External heartbeat](heartbeat.md): a systemd user timer sends an HTTPS ping
  only after Grafana and Prometheus are ready. Operators supply their external
  dead-man-switch service and notification policy.
- [Dependency automation](dependencies.md): Renovate tracks container images,
  workflow actions, pre-commit hooks, release defaults and hash-compiled Python
  tooling. Its configuration passes the official strict validator; pip-compile
  owns the requirements source/output pair.

### Dashboards and integrations

- [Local model servers](local-models.md): native vLLM metrics for exported
  model inventory, requests, KV cache occupancy and token throughput. Other
  servers need a compatible metrics endpoint before an integration can be
  provided; total GPU memory remains on the GPUs dashboard.
- All **47 alert queries** have executable fixtures: 46 PromQL rules run in
  Prometheus and the proxy error LogQL rule runs in Loki. The coverage guard
  requires firing and absent-series cases for each Prometheus alert. These
  query tests do not replace Grafana's provisioning and alert timing checks.

### Ease of use

- [Guided setup](operator-tools.md#guided-setup), preserving existing operator
  files and generating a private initial configuration and random password.
- [Published-image upgrades](operator-tools.md#upgrade-published-images) with
  stable release selection, target configuration checks, health checks and
  rollback of the image selector. Data migration rollback still requires an
  operator backup; the command does not update the checkout or remote agents.
- A [read-only status snapshot](operator-tools.md#read-only-status-page)
  generated from the shipped Overview expressions, with no browser access to
  Prometheus or embedded credentials.
- [Dashboard generation from code](local-models.md#generating-dashboards),
  starting with the repetitive model-server panels. Generated output is checked
  for drift in CI; a separate Jsonnet/Grafonnet dependency is unnecessary for
  this implementation.

## Continuing maintenance and the 1.0 release gate

Dependency security upkeep is ongoing: review vulnerability findings, rebuild
or replace abandoned components, and run the sandbox checks for upstream bumps
as described in [dependencies.md](dependencies.md). It cannot be permanently
completed by a single change.

**1.0** remains a release milestone, not a claim that this unreleased checkout
has been deployed. Before tagging it, merge and validate these configuration
changes, exercise an upgrade and restore against a real installation with
backups, and confirm the stable [interface contract](interfaces.md). Within a
major version, releases must preserve that contract and avoid manual migration
steps. Version 0.x upgrades can still require the documented configuration
changes.

## What Argus will not do

- **Be a hosted service or a multi-tenant platform.** Argus is for one
  operator's own network; it won't separate data between users or customers.
- **Be exposed directly to the internet.** Grafana needs the operator's TLS
  proxy for outside access. The optional
  authenticated push proxy exposes only two HTTPS ingestion paths; query APIs
  remain on the trusted network.
- **Run the server on Kubernetes, through Helm or without Docker.** Docker
  Compose on Linux remains the supported server installation. Monitoring
  Kubernetes nodes with the agent is supported as described above.
- **Replace maintained exporters or agents without a need.** Argus configures
  and packages standard components where they meet its requirements. Its Intel
  GPU exporter wraps `intel_gpu_top` to supply the metrics its dashboards need.
- **Manage or change the systems it watches.** Integrations are read-only;
  Argus never restarts, updates or configures a monitored service.
- **Collect data about its users.** Argus itself sends nothing anywhere except
  the alerts you configure (Loki's usage reporting is off; Grafana's anonymous
  usage statistics can be turned off with
  `GF_ANALYTICS_REPORTING_ENABLED=false` in the compose environment).
