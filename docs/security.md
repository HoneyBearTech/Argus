# Security requirements

What you can and can't expect from Argus in terms of security. The reasoning and evidence behind each
claim are in the [assurance case](assurance-case.md); how to report a problem is in
[SECURITY.md](../SECURITY.md).

## Intended deployment

Argus monitors a home lab or small network that its operator controls. The server and the agents run on
a **trusted network**: the machines on it, and the people who can reach it, are the operator's. Grafana
may be published beyond that network, but only behind a reverse proxy that terminates TLS. Prometheus and
Loki must not be reachable from outside it.

## What Argus is designed to guarantee

1. **The repository is the source of truth.** Dashboards, datasources, alert rules and the contact point
   are provisioned from files and can't be changed or deleted in Grafana's UI; changing them needs write
   access to the server or a new image.
2. **No credentials in the repository or the images.** Credentials for the watched services, the Grafana
   admin password and the Discord webhook come from the server's `secrets/` and `.env`, which are
   gitignored, mounted read-only and never baked into an image. Prometheus reads tokens from files. GitHub
   secret scanning with push protection guards the repository.
3. **No network details in the repository.** Addresses, host names and domains live only in the server's
   `targets/` and `.env`; CI rejects private IP addresses and a private list of internal names in every
   committed file.
4. **Grafana requires a login.** Sign-up and anonymous access are off, and the stack refuses to start
   without an admin password.
5. **Only three services listen on the network**: Grafana, Prometheus and Loki (plus the Plex exporter on
   a Plex host, if enabled). blackbox_exporter and the exporters are reachable only from the compose
   network, and the agent accepts no connections from other machines.
6. **TLS is verified by default** on every outgoing connection that uses it: web probes (an invalid or
   expired certificate fails the probe), the UniFi console (unless `UNIFI_VERIFY_SSL=false`), the Discord
   webhook, and HTTPS scrape targets.
7. **Least privilege for the server.** Grafana, Prometheus, Loki and blackbox_exporter run as non-root
   users in their containers. The integrations are designed for read-only accounts on the watched
   services (a read-only UniFi user, a non-admin Home Assistant user, Pi-hole app passwords, SNMPv3).
8. **Releases are verifiable.** Images are signed keylessly by the release workflow and carry an SBOM and
   provenance; release files are covered by a signed checksum file; version tags are signed
   ([verifying-releases.md](verifying-releases.md)). Base images are pinned by digest, and Grafana runs
   only the plugins in its image: it downloads none at start-up.
9. **Bounded storage.** Prometheus keeps 30 days or 8 GB, Loki 30 days with an ingestion rate limit, and
   noisy exporters are trimmed at scrape time, so a misbehaving source can't fill the disk unchecked.

## What Argus does not protect against

- **Anyone on the trusted network can push to and read from Prometheus and Loki.** They have no
  authentication: a machine on the network can read every metric and every collected log line, or push
  false metrics and logs (hiding a problem or raising false alerts). Keep them off untrusted networks;
  firewall them to the agents' addresses if your network isn't fully trusted.
- **Logs can contain secrets.** Whatever your containers print (tokens, personal data) is stored in Loki
  for 30 days and readable through Grafana by every Grafana user and through Loki by anyone who can reach
  it. CI job containers started by GitLab Runner (label `com.gitlab.gitlab-runner.managed`) are never read:
  Docker keeps their output without the secret masking GitLab applies to job logs.
- **The agent is root on its host.** It runs privileged, in the host's PID and network namespaces, with
  read access to the host's filesystem and the Docker and containerd sockets (which are equivalent to root). A compromised
  agent image or Argus release is a compromised host; that's why releases are signed.
- **Agent traffic is not encrypted by default.** Agents push over plain HTTP. Put Prometheus and Loki
  behind a TLS proxy and use `https://` URLs for the agents if traffic crosses a network you don't trust.
- **A compromised monitored host or service** can send whatever metrics and logs it likes about itself.
- **Grafana users can read everything.** Argus doesn't separate dashboards or data by user; give Grafana
  accounts only to people who may see all of it.
- **Vulnerabilities in the upstream components** (Grafana, Prometheus, Loki, Alloy, blackbox_exporter,
  the exporters). Argus pins and updates them and scans its images weekly
  ([dependencies.md](dependencies.md)), but a fix reaches you only when you upgrade.
- **Auto-deploy trusts `main`.** If you enable [auto-deploy](auto-deploy.md), anyone who can merge to
  `main` changes what runs on the server within minutes, once CI passes; protect the branch accordingly.
- **The host and its Docker daemon**: anyone with access to the server can read `secrets/` and change
  everything.
- **Alert delivery**: alerts go to one Discord webhook; if Discord, the webhook or the server is down,
  nothing is delivered, and nothing alerts that the server itself is down.

## Recommendations

- Keep the server and agents on a network you control; publish only Grafana, through a reverse proxy with
  TLS and a strong admin password.
- Give each integration its own read-only account or token, and rotate them if they leak.
- Pin `ARGUS_VERSION` and `ARGUS_AGENT_IMAGE` to a release, verify it, and upgrade when a release fixes a
  vulnerability.
- Keep `UNIFI_VERIFY_SSL=true` and give the UniFi console a trusted certificate if you can.
