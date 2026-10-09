# Dependencies and vulnerability management

How Argus chooses, obtains, tracks and updates what it's built from, and what happens when one of those
dependencies has a vulnerability.

Argus' dependencies are almost all **container images**: the upstream images its own images are built
from, and the exporter images the compose files run. The rest are the GitHub Actions in its workflows and
the Python tools its checks and tests use. Argus' own images contain no packages beyond their upstream
base.

## Choosing a dependency

A new component must:

- be open source under an OSI-approved license compatible with redistributing it in an image (see
  "Licenses" below);
- be actively maintained (releases in the last year, security issues answered) and widely used, preferring
  the upstream project's official image (Grafana, Prometheus, Loki and blackbox_exporter come from their
  maintainers);
- publish versioned images for linux/amd64 and linux/arm64 (an amd64-only exporter, like the Plex one,
  runs only on hosts that need it);
- need no more access than read-only credentials for the service it watches;
- be worth it: no component is added for something a few lines of configuration can do.

## Obtaining dependencies

All dependencies are fetched by standard tooling from their official registries, pinned so that a build
always gets the same bytes:

| Dependency | Declared in | Pinned by | Fetched by |
| --- | --- | --- | --- |
| Upstream base images (Grafana, Prometheus, blackbox_exporter, Loki, Alloy) | [`images/*/Dockerfile`](../images/), [`agent/Dockerfile`](../agent/Dockerfile) | version tag and multi-arch digest | Docker / BuildKit |
| Exporter images (pihole-exporter, unpoller, snmp-exporter, exportarr, qbittorrent-exporter, gitlab-ci-pipelines-exporter, Plex exporter) | [`docker-compose.yml`](../docker-compose.yml), [`agent/compose.yml`](../agent/compose.yml) | version tag (the Plex exporter by digest) | Docker Compose |
| Images used only by CI (promtool, linters, Trivy) | [`.github/workflows/`](../.github/workflows/) | version tag, and digest for most | Docker |
| GitHub Actions | [`.github/workflows/`](../.github/workflows/) | full commit SHA (version in a comment) | GitHub Actions |
| Python check and test tools (pytest, coverage, ruff, yamllint, PyYAML) | [`requirements-dev.in`](../requirements-dev.in) → [`requirements-dev.txt`](../requirements-dev.txt) | exact version and SHA-256 hashes (`pip-compile --generate-hashes`) | `pip install --require-hashes --no-deps` |

Released Argus images carry an SBOM listing every package in them ([verifying-releases.md](verifying-releases.md)).

## Tracking dependencies

- **Dependabot** ([`.github/dependabot.yml`](../.github/dependabot.yml)) checks weekly for new versions of
  the base images, the exporter images in all three compose files, the GitHub Actions and the Python
  tools, and opens a pull request for each. Dependabot alerts and security updates are on.
- Pull requests are **merged by hand**, not automatically: an upstream bump can change how provisioning or
  a config behaves, so it's loaded in a sandbox first, and the matching version in `ci.yml` (and for
  Grafana, the README badge) moves with it.
- CI images in workflow `run:` steps aren't seen by Dependabot; they're bumped together with the image
  they check (for example promtool with the Prometheus base image).

## Policy for vulnerabilities in dependencies

Known vulnerabilities are found by:

- the weekly **image scan** ([`.github/workflows/scan.yml`](../.github/workflows/scan.yml)): Trivy scans
  all five Argus images for HIGH and CRITICAL vulnerabilities that have a fix available, and reports each
  one as a [code scanning alert](https://github.com/HoneyBearTech/Argus/security/code-scanning);
- **Dependabot alerts** for the GitHub Actions and Python tools;
- upstream security advisories for Grafana, Prometheus, Loki and Alloy, which the maintainer follows.

Each finding is triaged within 14 days:

1. **If a fixed upstream release exists**, bump to it (a Dependabot pull request usually already does),
   test it in the sandbox and merge. A fix for an exploitable critical or high-severity vulnerability goes
   out in a patch release within 30 days; others go out with the next release.
2. **If upstream hasn't released a fix**, assess whether the vulnerable code is reachable in Argus'
   deployment (which ports are published, who can send it input, which features Argus uses). If it is
   exploitable, mitigate it in Argus' configuration where possible (for example by not publishing a port
   or turning a feature off) and say so in the release notes; otherwise dismiss the alert with the reason.
   Either way, it's fixed by a bump when upstream ships one.
3. **If a component is abandoned** and keeps accumulating vulnerabilities, replace it or rebuild it from
   source with patched dependencies.

### Current findings

As of 5 October 2026 (0.3.0):

- **blackbox_exporter v0.28.0**, the latest upstream release (built with Go 1.25.5): Go standard library,
  `golang.org/x/net`, `golang.org/x/crypto` and gRPC vulnerabilities. Assessment: blackbox_exporter isn't
  published on the host, so only Prometheus can call it, and it only connects to the URLs and DNS servers
  the operator lists; the reachable code is its HTTP and DNS clients talking to the operator's own
  services, so the realistic impact is a probed service crashing or stalling the prober (a false "down"
  alert), not a compromise. Argus' image runs it as an unprivileged user. It will be bumped as soon as
  upstream releases a build with current Go; if that hasn't happened by the end of 2026, Argus will build
  blackbox_exporter from source with patched dependencies instead.
- **Grafana 13.2.3**, the latest release: CVE-2026-84445 (gRPC-Go denial of service) in the bundled
  Prometheus datasource plugin. Assessment: the plugin's gRPC is the local channel between Grafana and
  its plugin process, not a network listener; the queries it sends go to Argus' own Prometheus. Fixed when
  Grafana ships a release with gRPC 1.83.2 or later. Argus' image removes the bundled datasource plugins it
  doesn't use, which took the Grafana image from eight HIGH findings to this one.
- **argus-agent**: none. Its image applies Ubuntu's security updates at build time (0.3.0 fixed
  CVE-2026-84782 in OpenSSL, which Alloy v1.20.1's base image still shipped).

Prometheus and Loki have no fixable HIGH or CRITICAL findings.

## Licenses

Every dependency must be under an OSI-approved open source license that allows redistribution in an
image (Apache-2.0, MIT, BSD, MPL-2.0 and similar). Grafana and Loki are AGPL-3.0: Argus redistributes
their unmodified images (with configuration files added), which the AGPL allows; their source is available
from their upstream projects. Argus' own files are MIT-licensed.

## Policy for findings from static analysis (SAST)

CodeQL analyses the Python code and the workflows on every pull request and weekly, and ruff runs the
bandit security rules on the Python code in CI. A CodeQL finding of medium severity or higher is fixed
before the next release, or, if it is a false positive, dismissed in code scanning with a written reason.
A ruff finding fails CI; a deliberate exception is a per-line `noqa` with the reason next to it.

## Published vulnerabilities

Vulnerabilities in Argus itself are published as GitHub security advisories, as described in
[SECURITY.md](../SECURITY.md#published-vulnerabilities).
