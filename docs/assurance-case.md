# Assurance case

This document argues that Argus meets its [security requirements](security.md). It describes the threat
model, identifies the trust boundaries, shows how secure design principles were applied, and lists how
common weaknesses are countered, with pointers to the files and tests that back each claim. The component
overview is in [architecture.md](architecture.md).

The top-level claim is:

> **Deployed as documented, Argus shows and alerts on the state of the operator's network without
> publishing their credentials or network details, without letting dashboards and alerts be changed
> outside the repository, and with releases whose origin can be verified, within the limits stated in
> [security.md](security.md).**

It rests on four arguments: the threat model is understood (1), every trust boundary is mediated or
explicitly accepted (2), the design follows secure design principles (3), and the implementation counters
common weaknesses and is continuously verified (4, 5).

Argus contains no server code of its own; its "implementation" is configuration for upstream components
(Grafana, Prometheus, Loki, Alloy, blackbox_exporter, exporters), the image build and release workflows,
and the Python checks in `scripts/`. The argument is therefore mostly about how those components are
configured, packaged and delivered.

## 1. Threat model

**Assets**, most valuable first: the monitored hosts (the agent runs privileged on each); the
credentials in the server's `secrets/` and `.env` (API keys and tokens for Pi-hole, UniFi, Home
Assistant, the media apps and SNMP, the Grafana admin password, the Discord webhook); the collected logs
and metrics (which describe the network and may contain sensitive data); the integrity of alerting (no
false silence, no false alarms); the integrity of the published images and release files; and the
privacy of the maintainer's network, which must not leak through the public repository.

**Actors and what they may try:**

| Actor | Trusted with | Threats considered |
| --- | --- | --- |
| Internet client | Nothing | Reach Grafana (if published) and guess the password; reach Prometheus or Loki. |
| Machine on the trusted network | Pushing and reading metrics and logs (accepted, see [security.md](security.md#what-argus-does-not-protect-against)) | Change dashboards or alert rules; read credentials; reach the exporters. |
| Grafana user | Viewing all dashboards and logs | Change provisioned dashboards, alert rules or datasources; create accounts. |
| Watched service or probed URL | Answering probes and API calls | A hostile or impersonated service: forged TLS certificate, oversized or malformed responses, a 403 from a proxy hiding an outage. |
| Contributor | Proposing changes | A pull request that adds a credential or network detail, a malicious workflow change, a change that silently breaks an alert. |
| Supply chain | Nothing beyond what's pinned | A tampered upstream image, GitHub Action or Python tool; a tampered Argus image between registry and user. |
| Network attacker | Nothing | Intercept or tamper with traffic between components, or with downloads. |

**Out of scope** (see [security.md](security.md#what-argus-does-not-protect-against)): anyone with
control of the server, its Docker daemon or a monitored host; abuse of the unauthenticated Prometheus and
Loki endpoints from inside the trusted network; vulnerabilities in the upstream components themselves
(handled by updating them, [dependencies.md](dependencies.md)).

## 2. Trust boundaries

| # | Boundary | What crosses it | How it is mediated |
| --- | --- | --- | --- |
| B1 | Browser → Grafana | HTTP requests, logins | Grafana authentication on every request; sign-up and anonymous access off ([`images/grafana/Dockerfile`](../images/grafana/Dockerfile)); the admin password is required (`docker-compose.yml` refuses to start without it); TLS from the operator's reverse proxy. Provisioned dashboards, datasources and alerting are read-only ([`provisioning/`](../provisioning/); tested in [`tests/test_configs.py`](../tests/test_configs.py)). |
| B2 | Agent → Prometheus / Loki | Metrics and logs | Accepted without authentication on the trusted network (documented). The agent drops log lines older than an hour; Loki rejects samples older than a week and limits ingestion rate ([`logs/loki.yaml`](../logs/loki.yaml)); Prometheus retention is bounded by time and size. |
| B3 | Prometheus → exporters, blackbox → probed URLs, exporters → watched services | Scrapes, probes, API calls with credentials | Exporters sit on the compose network with no published port; credentials come from read-only mounted files in `secrets/`; TLS certificates are verified (probes: no `insecure_skip_verify`, tested; UniFi: `UNIFI_VERIFY_SSL` defaults to `true`, tested); a probe counts only explicit success codes, not 403 (tested, #3); scrape timeouts and per-job drop rules bound what a target can send. |
| B4 | Agent → host | Host metrics, container metrics, container logs | The agent is privileged by necessity; it mounts the host read-only and only connects out. Its image is signed and pinned per host by the operator. Alloy's UI listens on loopback only. |
| B5 | Grafana → Discord | Alert notifications | HTTPS with certificate verification; the webhook comes from the environment and a sandbox defaults to an invalid URL, so a test install can't post to a real channel. |
| B6 | Contributor → repository | Pull requests | `main` accepts changes only through pull requests that pass the required CI check, enforced for administrators; CI rejects private addresses and internal names (`scripts/check_dashboards.py`); secret scanning with push protection; DCO sign-off; workflows from forks get read-only tokens and no secrets; CodeQL analyses the workflows. |
| B7 | Upstream → build → registries → user | Base images, Actions, tools, published images | Base images pinned by version and digest, Actions by commit SHA, Python tools by hash; the release workflow signs each image keylessly (identity: the workflow on the tag), attaches SBOM and provenance, and signs the release checksums; users verify with cosign ([verifying-releases.md](verifying-releases.md)). |

### Attack surface

- **Grafana** (HTTP, authenticated): the main surface if published; hardened by Grafana's defaults plus
  the settings above, and meant to sit behind a TLS proxy.
- **Prometheus and Loki** (HTTP, unauthenticated): read and write APIs, on the trusted network only.
- **Plex exporter** (HTTP, unauthenticated, read-only metrics) on a Plex host, if enabled.
- **Responses from watched services**, parsed by the exporters and blackbox_exporter.
- **Logs from containers and NPM**, parsed by Alloy with fixed regular expressions; a line that doesn't
  match is stored unparsed, never executed.

The full list of ports, files and variables is in [interfaces.md](interfaces.md).

## 3. Secure design principles

| Principle | How Argus applies it |
| --- | --- |
| Economy of mechanism | No server code: standard components with small, readable configuration files. One agent container per host instead of several. |
| Fail-safe defaults | TLS verification on; sign-up and anonymous access off; the stack won't start without an admin password; a sandbox's Discord URL is invalid by default; a probe is up only on an explicit success code; exporters without credentials start but scrape nothing. |
| Complete mediation | Every Grafana request is authenticated; provisioned resources are read-only on every path (UI and API). |
| Open design | Everything is public and documented; security rests on the operator's credentials and network, not on secrecy of the configuration. |
| Separation of privilege | Publishing a release needs both a tag pushed by the maintainer and the release workflow's identity; changes to `main` need a pull request and a passing check. |
| Least privilege | Read-only accounts for integrations; read-only mounts for `secrets/`, `targets/` and the host filesystem; non-root server containers; workflows default to read-only tokens and each job asks only for what it needs. |
| Least common mechanism | Each exporter runs in its own container with only its own credentials; Loki can run on a separate host. |
| Psychological acceptability | One `.env`, one `targets/` folder and one `secrets/` folder, with placeholders for each; the secure defaults need no configuration. |

## 4. Countering common weaknesses

| Weakness | Countermeasure | Evidence |
| --- | --- | --- |
| Hard-coded or committed credentials (CWE-798, CWE-312) | Credentials only in gitignored `secrets/` and `.env`; Prometheus reads token files; push protection | `.gitignore`; [`tests/test_configs.py`](../tests/test_configs.py) (no credentials in the Prometheus config, webhook from the environment) |
| Exposure of sensitive information (CWE-200) | No addresses or internal names in committed files; exporters not published | [`scripts/check_dashboards.py`](../scripts/check_dashboards.py) in CI (tested in [`tests/test_check_dashboards.py`](../tests/test_check_dashboards.py)); `test_compose_files_publish_no_blackbox_or_exporter_ports` |
| Improper certificate validation (CWE-295) | Verification on by default everywhere | `test_probes_verify_tls_certificates`, `test_unifi_exporter_verifies_tls_by_default` |
| Execution with unnecessary privileges (CWE-250) | Non-root server images, including blackbox_exporter (upstream runs as root) | `test_blackbox_image_does_not_run_as_root`; [`images/`](../images/) |
| Missing authentication / improper access control (CWE-306, CWE-284) | Grafana login, no sign-up or anonymous access, read-only provisioning; the unauthenticated endpoints are documented and kept to the trusted network | `test_grafana_image_turns_off_sign_up_and_anonymous_access`, `test_dashboards_cannot_be_changed_in_the_ui`, `test_datasources_cannot_be_changed_in_the_ui`; [security.md](security.md) |
| Inclusion of functionality from an untrusted source (CWE-829, CWE-494) | Digest-pinned images, SHA-pinned Actions, hash-pinned Python tools; signed releases | the Dockerfiles, workflows and `requirements-dev.txt`; OpenSSF Scorecard (Pinned-Dependencies) |
| Injection into CI scripts (CWE-78, CWE-94) | Untrusted values reach `run:` scripts only through `env:`; no `pull_request_target` | actionlint and shellcheck in CI; CodeQL for Actions |
| Uncontrolled resource consumption (CWE-400) | Retention limits, Loki ingestion limits, keep-lists and drop rules for noisy exporters, scrape timeouts | [`prometheus/prometheus.yml`](../prometheus/prometheus.yml), [`logs/loki.yaml`](../logs/loki.yaml), [`docker-compose.yml`](../docker-compose.yml) |
| Incorrect alert logic hiding or inventing outages | Alert and dashboard queries are tested against synthetic series, including regressions for past false alerts; Grafana is started in CI to prove every rule loads | [`tests/promql/`](../tests/promql/); the "Grafana starts with everything provisioned" CI step |
| Use of components with known vulnerabilities (CWE-1395) | Dependabot for images, Actions and tools; weekly Trivy scan of all images | [dependencies.md](dependencies.md) |

The repository's own Python code (`scripts/`) only reads repository files and runs `git ls-files` with a
fixed argument list; it parses YAML with `yaml.safe_load` and JSON with the standard library.

## 5. Verification evidence

On every push and pull request, CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs:
ruff (including the bandit security rules), yamllint, actionlint with shellcheck, hadolint, `alloy fmt`;
the unit tests with a 90 % coverage floor; the dashboard and public-repo checks; `promtool check config`
and the PromQL tests; config checks for blackbox, Loki and Alloy; builds every image; starts Grafana to
check that everything provisions; and validates the compose files. CodeQL analyses the Python code and the
workflows on every change and weekly; a DCO check runs on every pull request; Trivy scans the images
weekly; OpenSSF Scorecard scores the repository weekly. Releases are signed and carry SBOM and provenance.

This document is reviewed when the threat model changes: a new listening service, a new kind of
credential, a new integration that writes rather than reads, or a change to how releases are built.
