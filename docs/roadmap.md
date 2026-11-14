# Roadmap

What Argus intends to do through October 2027, and what it deliberately won't
do. Plans change; this file is updated when they do, and larger items get a
GitHub issue before work starts. Suggestions are welcome in
[Issues](https://github.com/HoneyBearTech/Argus/issues).

## Where it stands

As of November 2026, the latest release is **0.9.0** (29 October). The current
checkout contains 25 dashboards and 47 provisioned alert rules, with alerts
sent to Discord. It covers hosts, containers, logs, databases, network and ISP
health, storage, smart home, media, power, server hardware, GPUs, deployments,
GitLab and Steerhouse. See the [README](../README.md) for the full inventory
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
- Optional [Prometheus password protection](security.md#requiring-a-password-for-prometheus),
  including agents that push with credentials. Agent traffic still needs a TLS
  proxy when crossing an untrusted network; Loki has no built-in authentication.
- Documented [upgrade and rollback procedures](upgrading.md), plus optional
  [automatic source deployments](auto-deploy.md) after the required check
  passes, with health checks and rollback.

The project checks lint, unit tests, PromQL and configuration, builds images,
and starts Grafana to validate provisioning. Releases include signed images,
SBOMs and provenance ([verifying-releases.md](verifying-releases.md)).

## Remaining work through October 2027

### Security and operations

- A complete, documented TLS reverse-proxy setup for both push endpoints,
  including Loki authentication and the corresponding agent credentials, so
  operators have a tested recipe for networks that aren't fully trusted.
- Notification channels beyond Discord (e-mail, ntfy, Slack-compatible webhooks)
  as provisioned contact points selected in `.env`.
- A "watch the watcher": an external heartbeat so that the Argus server being
  down is noticed.
- Replacing or rebuilding components whose upstream images go stale on
  security fixes ([dependencies.md](dependencies.md)); this is ongoing upkeep.

### Dashboards and integrations

- Local model servers (loaded models, memory), once they expose metrics.
- More PromQL tests, until every alert rule has one. The current query fixtures
  cover 36 of 47 provisioned rules; expand them to the remaining rules and
  continue adding cases for new behavior.

### Ease of use

- An install script or guided `.env` setup.
- A one-command upgrade for published-image installations, including the
  release selection and configuration checks that are currently manual.
- A read-only status page generated from the Overview data.
- Generating repetitive dashboards from code (Jsonnet/Grafonnet) if the JSON
  keeps growing.

**1.0**: a stable interface ([interfaces.md](interfaces.md)) with upgrades that
need no manual steps within a major version, once the items above that change
configuration have landed.

## What Argus will not do

- **Be a hosted service or a multi-tenant platform.** Argus is for one
  operator's own network; it won't separate data between users or customers.
- **Be exposed directly to the internet.** Only Grafana, behind the operator's
  TLS proxy, is meant to be reachable from outside.
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
