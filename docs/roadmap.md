# Roadmap

What Argus intends to do over the next year (to October 2027), and what it deliberately won't do. Plans
change; this file is updated when they do, and larger items get a GitHub issue before work starts.
Suggestions are welcome in [Issues](https://github.com/HoneyBearTech/Argus/issues).

## Where it stands

Argus 0.1 (October 2026) covers a typical home lab end to end: 11 dashboards (overview, hosts,
containers, logs, DNS, network, reverse proxy, storage, smart home, media, power), 19 alert rules sent to
Discord, a one-container push agent per host, and images for amd64 and arm64 on GHCR and Docker Hub. The
project has CI with linting, unit and PromQL tests and a Grafana start-up check, signed releases, and the
OpenSSF Best Practices badge.

## Over the following year

**Security and operations**

- Optional authentication for the push endpoints: a documented reverse-proxy setup (or Prometheus' and
  Loki's own options) with TLS and credentials for agents, so Argus can run on networks that aren't fully
  trusted.
- Notification channels beyond Discord (e-mail, ntfy, Slack-compatible webhooks) as provisioned contact
  points selected in `.env`.
- A "watch the watcher": an external heartbeat so that the Argus server being down is noticed.
- Replacing or rebuilding components whose upstream images go stale on security fixes
  ([dependencies.md](dependencies.md)).

**Dashboards and integrations**

- VMware vSphere / ESXi hosts and VMs.
- GitLab (or other self-hosted CI) pipelines and runners.
- Local AI model servers (loaded models, memory), once they expose metrics.
- Internet speed history for ISP accountability.
- More PromQL tests, until every alert rule has one.

**Ease of use**

- An install script or guided `.env` setup, and a one-command upgrade.
- A read-only status page generated from the Overview data.
- Generating repetitive dashboards from code (Jsonnet/Grafonnet) if the JSON keeps growing.

**1.0**: a stable interface ([interfaces.md](interfaces.md)) with upgrades that need no manual steps
within a major version, once the items above that change configuration have landed.

## What Argus will not do

- **Be a hosted service or a multi-tenant platform.** Argus is for one operator's own network; it won't
  separate data between users or customers.
- **Be exposed directly to the internet.** Only Grafana, behind the operator's TLS proxy, is meant to be
  reachable from outside.
- **Support Kubernetes, Helm or non-Docker installs.** Docker Compose on Linux is the supported way to
  run it; other setups can reuse the images and configs at their own risk.
- **Write its own exporters or agent** when a maintained one exists; Argus configures and packages
  standard components.
- **Manage or change the systems it watches.** Integrations are read-only; Argus never restarts, updates
  or configures a monitored service.
- **Collect data about its users.** Argus itself sends nothing anywhere except the alerts you configure
  (Loki's usage reporting is off; Grafana's anonymous usage statistics can be turned off with
  `GF_ANALYTICS_REPORTING_ENABLED=false` in the compose environment).
