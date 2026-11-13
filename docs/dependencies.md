# Dependencies and vulnerability management

How Argus chooses, obtains, tracks and updates what it's built from, and what
happens when one of those
dependencies has a vulnerability.

Argus' dependencies are almost all **container images**: the upstream images its
own images are built
from, and the exporter images the compose files run. The rest are the GitHub
Actions in its workflows and
the Python tools its checks and tests use. Argus' own images contain no packages
beyond their upstream
base.

## Choosing a dependency

A new component must:

- be open source under an OSI-approved license compatible with redistributing it
  in an image (see
  "Licenses" below);
- be actively maintained (releases in the last year, security issues answered)
  and widely used, preferring
  the upstream project's official image (Grafana, Prometheus, Loki and
  blackbox_exporter come from their
  maintainers);
- publish versioned images for linux/amd64 and linux/arm64 (an amd64-only
  exporter, like the Plex one,
  runs only on hosts that need it);
- need no more access than read-only credentials for the service it watches;
- be worth it: no component is added for something a few lines of configuration
  can do.

## Obtaining dependencies

All dependencies are fetched by standard tooling from their official registries,
pinned so that a build
always gets the same bytes:

- **Dependency:** Upstream base images (Grafana, Prometheus, blackbox_exporter,
  Loki, Alloy)
  - **Declared in:** [`images/*/Dockerfile`](../images/),
    [`agent/Dockerfile`](../agent/Dockerfile)
  - **Pinned by:** version tag and multi-arch digest
  - **Fetched by:** Docker / BuildKit

- **Dependency:** Exporter images (pihole-exporter, unpoller, snmp-exporter,
  exportarr, qbittorrent-exporter, gitlab-ci-pipelines-exporter,
  prometheus-pve-exporter, tdarr-exporter, Varken, Plex exporter, NVIDIA GPU
  exporter)
  - **Declared in:** [`docker-compose.yml`](../docker-compose.yml),
    [`agent/compose.yml`](../agent/compose.yml)
  - **Pinned by:** version tag (the Plex exporter by digest)
  - **Fetched by:** Docker Compose

- **Dependency:** `prometheus-ipmi-exporter`, `freeipmi-tools` and `sudo` on
  monitored servers (not in Argus' images)
  - **Declared in:**
    [`deploy/ipmi/setup-ipmi-exporter.sh`](../deploy/ipmi/setup-ipmi-exporter.sh)
  - **Pinned by:** Debian stable's package; the script's sudo rules are checked
    against `1.10.0-2+b4` and it stops on another version
  - **Fetched by:** apt, from the Debian archive (security updates through the
    server's own updates)

- **Dependency:** `prometheus-node-exporter` on servers without the agent whose
  add-in GPU Argus reads (not in Argus' images)
  - **Declared in:**
    [`deploy/hwmon/setup-node-exporter.sh`](../deploy/hwmon/setup-node-exporter.sh)
  - **Pinned by:** Debian stable's package, without its recommended collectors
  - **Fetched by:** apt, from the Debian archive (security updates through the
    server's own updates)

- **Dependency:** Images used only by CI (promtool, linters, Trivy)
  - **Declared in:** [`.github/workflows/`](../.github/workflows/)
  - **Pinned by:** version tag, and digest for most
  - **Fetched by:** Docker

- **Dependency:** Images of the GitLab copy's pipeline (Python, Docker CLI, git,
  promtool, Alloy, blackbox_exporter, hadolint, actionlint)
  - **Declared in:** [`.gitlab-ci.yml`](../.gitlab-ci.yml)
  - **Pinned by:** version tag and digest
  - **Fetched by:** GitLab Runner (Docker executor)

- **Dependency:** GitHub Actions
  - **Declared in:** [`.github/workflows/`](../.github/workflows/)
  - **Pinned by:** full commit SHA (version in a comment)
  - **Fetched by:** GitHub Actions

- **Dependency:** Python check and test tools (pytest, coverage, ruff, yamllint,
  PyYAML)
  - **Declared in:** [`requirements-dev.in`](../requirements-dev.in) →
    [`requirements-dev.txt`](../requirements-dev.txt)
  - **Pinned by:** exact version and SHA-256 hashes
    (`pip-compile --generate-hashes`)
  - **Fetched by:** `pip install --require-hashes --no-deps`

Released Argus images carry an SBOM listing every package in them
([verifying-releases.md](verifying-releases.md)).

## Tracking dependencies

**Renovate** ([`renovate.json`](../renovate.json)) checks weekly in the
`America/Chicago` timezone and opens
labeled pull requests; automerge is disabled. The migration pull request body
contains the heading `Migrated from Dependabot`, the T1 coverage mapping, and
the post-merge note to verify that GitHub security alerts and security updates
remain enabled. That note applies to the migration pull request only. This
migration does not change repository security settings; Dependabot alerts are
retained.

- **Files and declarations:** `agent/Dockerfile`, `images/*/Dockerfile`
  - **Renovate manager:** Docker
  - **Notes:** Dockerfile base images; Dockerfile paths are explicitly included

- **Files and declarations:** `docker-compose*.yml`, `agent/compose.yml`,
  `logs/compose.yml`
  - **Renovate manager:** Docker Compose
  - **Notes:** Includes Compose image defaults and external exporter images

- **Files and declarations:** `.github/workflows/*.yml` action `uses:`
  references
  - **Renovate manager:** GitHub Actions
  - **Notes:** Minor and patch updates remain grouped

- **Files and declarations:** `requirements-dev.in`, `requirements-dev.txt`
  - **Renovate manager:** pip_requirements and pip-compile
  - **Notes:** Source declarations and hash-pinned compiled check and test
    dependencies

- **Files and declarations:** `.gitlab-ci.yml` `image:` and nested `image.name:`
  - **Renovate manager:** GitLab CI
  - **Notes:** Explicitly included; Renovate covers all top-level and nested
    declarations

- **Files and declarations:** Literal third-party image operands in `docker run`
  commands in `.github/workflows/ci.yml` and `scan.yml`
  - **Renovate manager:** Regex custom manager
  - **Notes:** Matches only the listed image operands, captures just the tag,
    and preserves any existing digest text on replacement

The Dependabot coverage migrated in T1 maps Docker `/agent`, `/images/grafana`,
`/images/prometheus`,
`/images/blackbox`, `/images/loki`, and `/images/intel-gpu-exporter` to Docker;
Compose `/`, `/agent`, and
`/logs` to Docker Compose; GitHub Actions `/` to GitHub Actions; and pip `/` to
pip. GitLab CI
images are now covered by the GitLab CI manager, and workflow shell-run images
by the custom manager.

CI workflow image tags with digests are intentionally matched by the shell
manager only at the tag token; the
digest remains verbatim. Existing Dockerfile and Compose digests are also
retained. `argus-*:source`,
`argus-*:ci`, and `argus-intel-gpu-exporter:ci` are local build outputs and are
excluded from registry updates.

The configurable Argus release defaults `${ARGUS_VERSION:-latest}`,
`${ARGUS_AGENT_IMAGE:-...}`, and
`${ARGUS_INTEL_GPU_EXPORTER_IMAGE:-...}` remain configurable. Argus maintainers
own these selections; update
them through the release workflow or local source build, with overrides in
`.env`. Compose interpolation
handles the defaults. There are no independent image-valued `.env` declarations
and no Ansible image fields
or roles in this repository. GitHub security alerts and security updates remain
enabled; repository security
settings are unchanged.

Pull requests are merged by hand after the upstream bump is loaded in a sandbox,
since changes can affect
provisioning or config behavior. Keep related image tags synchronized across
Dockerfiles, Compose, GitLab CI,
and workflow shell commands where comments identify a shared image. Update the
Grafana README badge with its
image bump.

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found by:

- the weekly **image scan**
  ([`.github/workflows/scan.yml`](../.github/workflows/scan.yml)): Trivy scans
  all six Argus images for HIGH and CRITICAL vulnerabilities that have a fix
  available, and reports each
  one as a
  [code scanning alert](https://github.com/HoneyBearTech/Argus/security/code-scanning);
- **GitHub security alerts** for the GitHub Actions and Python tools;
- upstream security advisories for Grafana, Prometheus, Loki and Alloy, which
  the maintainer follows.

Each finding is triaged within 14 days:

1. **If a fixed upstream release exists**, bump to it (a Renovate pull request
   usually already does),
   test it in the sandbox and merge. A fix for an exploitable critical or
   high-severity vulnerability goes
   out in a patch release within 30 days; others go out with the next release.
2. **If upstream hasn't released a fix**, assess whether the vulnerable code is
   reachable in Argus'
   deployment (which ports are published, who can send it input, which features
   Argus uses). If it is
   exploitable, mitigate it in Argus' configuration where possible (for example
   by not publishing a port
   or turning a feature off) and say so in the release notes; otherwise dismiss
   the alert with the reason.
   Either way, it's fixed by a bump when upstream ships one.
3. **If a component is abandoned** and keeps accumulating vulnerabilities,
   replace it or rebuild it from
   source with patched dependencies.

### Current findings

As of 14 October 2026 (main after 0.6.0, with Grafana 13.2.4): 28 open code
scanning alerts, which are five
vulnerabilities repeated across the images' Go programs. All five are denial of
service (CPU or memory
exhaustion, or a crash); none allows code execution or data access.

- **Go standard library, CVE-2026-78667** (`net/http`: many small ranges in a
  `Range` header make
  `FileServer`, `ServeContent` and `ServeFile` burn CPU), **CVE-2026-78669**
  (`net/http` and
  `golang.org/x/net/http2`: excessive HTTP/2 `SETTINGS` frames) and
  **CVE-2026-97031** (`crypto/tls`:
  repeated ECH outer extensions exhaust a TLS server's memory). Fixed in Go
  1.26.9 and 1.27.2 and
  `golang.org/x/net` 0.60.0. They're in Prometheus and promtool (v3.15.0), Loki
  (3.7.8), Alloy in the agent
  (v1.20.1), blackbox_exporter (v0.29.0) and the three datasource plugins
  Grafana keeps; each is that
  project's latest release, and none has been rebuilt with the fixed Go yet.
  Assessment: **CVE-2026-97031** needs a Go TLS server, and none of Argus' Go
  programs terminates TLS
  (Grafana sits behind the reverse proxy, which isn't Go). **CVE-2026-78669** on
  the server side needs
  HTTP/2, which Go only speaks over TLS unless a program turns on h2c, so the
  plain-HTTP listeners
  (Prometheus, Loki, blackbox_exporter, the exporters) aren't affected; as a
  client, Prometheus, Alloy and
  blackbox_exporter only talk to the targets and URLs the operator lists, so a
  hostile target could at worst
  slow the prober down. **CVE-2026-78667** affects Prometheus, whose web UI
  serves its static files with
  `ServeContent`: someone who can reach port 9090 could burn its CPU. Argus runs
  on a trusted network, and
  with a password set (`prometheus-web.yml`,
  [security.md](security.md#requiring-a-password-for-prometheus))
  Prometheus answers nothing without it. Loki serves no files; Alloy's own HTTP
  server listens on the host's
  loopback only; the Grafana plugins talk to Grafana over a local channel, not
  the network. Fixed by the
  Dependabot bumps once upstream ships builds with the fixed Go; the alerts stay
  open until then.
- **gRPC-Go, CVE-2026-84445**, in Grafana's bundled Prometheus datasource
  plugin: **fixed by Grafana
  13.2.4**, which also fixes four of Grafana's own vulnerabilities
  (CVE-2026-15577, CVE-2026-33374,
  CVE-2026-93294, CVE-2026-95502). Argus' image keeps removing the bundled
  plugins it doesn't use, which
  also leaves out the Tempo plugin and its two findings.
- **argus-agent**: Alloy's Go findings above; none in its Ubuntu base, whose
  security updates the image
  applies at build time.

## Licenses

Every dependency must be under an OSI-approved open source license that allows
redistribution in an
image (Apache-2.0, MIT, BSD, MPL-2.0 and similar). Grafana and Loki are
AGPL-3.0: Argus redistributes
their unmodified images (with configuration files added), which the AGPL allows;
their source is available
from their upstream projects. Argus' own files are MIT-licensed.

## Policy for findings from static analysis (SAST)

CodeQL analyses the Python code and the workflows on every pull request and
weekly, and ruff runs the
bandit security rules on the Python code in CI. A CodeQL finding of medium
severity or higher is fixed
before the next release, or, if it is a false positive, dismissed in code
scanning with a written reason.
A ruff finding fails CI; a deliberate exception is a per-line `noqa` with the
reason next to it.

## Published vulnerabilities

Vulnerabilities in Argus itself are published as GitHub security advisories, as
described in
[SECURITY.md](../SECURITY.md#published-vulnerabilities).
