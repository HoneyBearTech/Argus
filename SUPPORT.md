# Support

Argus is maintained by one person in their own time (see [GOVERNANCE.md](GOVERNANCE.md)), so this is a
best-effort policy, not a contract.

## Getting help

- **Questions, bugs and ideas**: [GitHub Issues](https://github.com/HoneyBearTech/Argus/issues). Say which
  version you run, which dashboard or exporter is involved, and what you expected. Leave out your own
  addresses, hostnames and credentials.
- **Security vulnerabilities**: never in a public issue; see [SECURITY.md](SECURITY.md).
- **Documentation**: the [README](README.md) and [docs/](docs/README.md), starting with the
  [quick start](docs/quick-start.md).

## Which versions are supported, and for how long

| Version | Supported with | Until |
| --- | --- | --- |
| The latest release | bug fixes and security fixes | the next release is published |
| An older release | nothing | it stopped being supported when the next release came out |
| `main` | bug fixes and security fixes | always (it's where fixes land first) |

- A fix is released as a new version (a patch release such as 0.2.1 for fixes only), never applied to an
  older release.
- **A release stops receiving security updates the moment the next release is published.** Its notes and
  [CHANGELOG.md](CHANGELOG.md) say what changed and whether upgrading needs steps; upgrading is described
  in [docs/upgrading.md](docs/upgrading.md).
- Before 1.0, a minor release (0.3.0) may change behaviour or need upgrade steps; they're listed in the
  changelog under "Upgrading".
- Argus ships pinned upstream components (Grafana, Prometheus, Loki, blackbox_exporter, Grafana Alloy and
  the exporters). Fixes for those reach you as a new Argus release that bumps them; see
  [docs/dependencies.md](docs/dependencies.md).
- If a supported line will end differently (for example a 1.x line kept alive after 2.0), it will be
  announced in the release notes and in this table first.

Images stay available on GHCR and Docker Hub after their support ends, so existing installations keep
working, but they won't get fixes: run the latest release.
