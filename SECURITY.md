# Security Policy

## Reporting a vulnerability

Please report vulnerabilities in Argus through GitHub's private vulnerability reporting form:

https://github.com/HoneyBearTech/Argus/security/advisories/new

Do not report vulnerabilities through public issues. Include what you found, how to reproduce it, which
version or commit you tested, and what an attacker gains. Please avoid accessing or changing data that is
not yours while investigating. If you'd like to be credited under a particular name, or not at all, say
so.

## How reports are handled

This is a personal project maintained by one person (see [GOVERNANCE.md](GOVERNANCE.md)), so these are
targets rather than a contractual SLA:

1. **Acknowledge** the report within 7 days.
2. **Triage** it: reproduce the problem, decide whether it is a vulnerability in Argus (see "Scope"
   below) and agree its severity with you. If it isn't a vulnerability, you'll get an explanation, and the
   report may move to a public issue with your agreement.
3. **Fix** it privately in a [GitHub security advisory](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/about-repository-security-advisories),
   with a regression test where the problem can be tested, and invite you to review the fix if you want
   to.
4. **Release** the fix, then publish the advisory (requesting a CVE where it applies) with the affected
   and fixed versions and any workaround. The aim is to release fixes for critical and high-severity
   issues within 30 days of the report and others within 90 days, and to keep you updated at least every
   14 days until then.
5. **Credit** the reporter in the advisory and the release notes, unless you ask to stay anonymous.

## Coordinated disclosure

Please keep the details private until the advisory is published, or for 90 days after your report if no
fix has been released by then, whichever comes first. If you need a different timeline, say so in the
report.

## Supported versions

The latest release and `main` receive security fixes; a release stops receiving them when the next one is
published. Details are in [SUPPORT.md](SUPPORT.md).

## Published vulnerabilities

Vulnerabilities fixed in Argus are published as
[GitHub security advisories](https://github.com/HoneyBearTech/Argus/security/advisories) (with a CVE
where one applies), naming the affected and fixed versions, how to tell whether you're affected and how
to fix or work around it, and they're listed in the release notes and [CHANGELOG.md](CHANGELOG.md). None
have been reported so far.

Known vulnerabilities in the upstream components Argus ships (Grafana, Prometheus, Loki, blackbox_exporter,
Grafana Alloy and the exporters) are found by a weekly image scan and handled as described in
[docs/dependencies.md](docs/dependencies.md).

## Scope

Argus is monitoring for a home lab or small network. It is designed to run on a **trusted network**:
Prometheus and Loki accept pushes from the agents without authentication, and the agent runs privileged on
every monitored host. Treat the server as a sensitive system: it holds read-only credentials for the
services it watches and sees the logs of every container.

What Argus does and doesn't protect against is described in [docs/security.md](docs/security.md) (its
security requirements), and the reasoning behind it in [docs/assurance-case.md](docs/assurance-case.md)
(threat model, trust boundaries and the defences against common weaknesses). Read them before you deploy
or report.

In scope: anything that breaks the guarantees in those documents, for example a way to change dashboards
or alert rules without access to the server, an Argus default that exposes credentials, a release
artifact that doesn't match its signature, or a published file that leaks a secret. Expected behaviour,
not vulnerabilities: anyone on the trusted network pushing metrics or logs to the unauthenticated
endpoints, and anything that requires control of a monitored host or the server. Vulnerabilities in
Grafana, Prometheus, Loki, Alloy or an exporter themselves belong with that project, but please tell us
too if Argus' configuration makes one worse.
