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

- **Anyone on the trusted network can push to and read from Loki, and from Prometheus unless you
  [give it a password](#requiring-a-password-for-prometheus).** Without one, a machine on the network can
  read every metric and every collected log line, or push false metrics and logs (hiding a problem or
  raising false alerts). Loki has no authentication of its own: keep it off untrusted networks and
  firewall it to the agents' addresses if your network isn't fully trusted.
- **Logs can contain secrets.** Whatever your containers print (tokens, personal data) is stored in Loki
  for 30 days and readable through Grafana by every Grafana user and through Loki by anyone who can reach
  it. CI job containers started by GitLab Runner (the label it marks them with as managed) are never read:
  Docker keeps their output without the secret masking GitLab applies to job logs.
- **The agent is root on its host.** It runs privileged, in the host's PID and network namespaces, with
  read access to the host's filesystem and the Docker and containerd sockets (which are equivalent to root). A compromised
  agent image or Argus release is a compromised host; that's why releases are signed.
- **Agent traffic is not encrypted by default.** Agents push over plain HTTP, Prometheus' password
  included. Put Prometheus and Loki behind a TLS proxy and use `https://` URLs for the agents if traffic
  crosses a network you don't trust.
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
  TLS and a strong admin password. If the proxy runs in Docker on the same host, add
  `docker-compose.proxy.yml` to `COMPOSE_FILE` with `ARGUS_PROXY_NETWORK` set to the proxy's network, point
  the proxy at `argus-grafana:3000` and set `GRAFANA_BIND=127.0.0.1:3000`, so the plain-HTTP port isn't
  open to the network.
- [Require a password for Prometheus](#requiring-a-password-for-prometheus).
- Give each integration its own read-only account or token, and rotate them if they leak.
- Pin `ARGUS_VERSION` and `ARGUS_AGENT_IMAGE` to a release, verify it, and upgrade when a release fixes a
  vulnerability.
- Keep `UNIFI_VERIFY_SSL=true` and give the UniFi console a trusted certificate if you can.
- If you open GitLab's bundled Prometheus (`prometheus['listen_address']`) or GitLab Runner's metrics port
  for Argus, they answer anyone who can reach them, without authentication; allow only the Argus server
  with a host firewall (for example `ufw allow from <argus-server> to any port 9090`).

## Requiring a password for Prometheus

Prometheus' web configuration, `secrets/prometheus-web.yml`, lists who may push to and query it. The
example lists no one, so Prometheus answers anyone. The password of its user `argus` is in
`secrets/prometheus_password`; Grafana's datasource, Prometheus' scrape of itself and
[auto-deploy](auto-deploy.md)'s health check always send it, so they keep working once it's required.

1. Put a random password in `secrets/prometheus_password` (readable by the containers, like the other
   secrets):

   ```sh
   openssl rand -base64 24 | tr -d '/+=' > secrets/prometheus_password
   chmod 644 secrets/prometheus_password
   docker compose up -d   # Grafana reads the password at start-up
   ```

2. On every agent host, set `ARGUS_PROMETHEUS_PASSWORD` in the agent's `.env` to that password (agent
   0.6.0 or later; older agents send no password) and run `docker compose up -d`. A Prometheus that
   requires no password ignores it, so this can happen before the next step.
3. Add the password's bcrypt hash to `secrets/prometheus-web.yml` and restart Prometheus:

   ```sh
   hash=$(docker run --rm httpd:2.4-alpine htpasswd -nbB argus "$(cat secrets/prometheus_password)" | cut -d: -f2)
   printf 'basic_auth_users:\n  argus: %s\n' "$hash" > secrets/prometheus-web.yml
   docker compose restart prometheus
   ```

4. Check that every host still reports (the "Host stopped reporting" alert stays quiet); an agent without
   the password logs `401 Unauthorized`.

Every request then needs the password, including `/metrics` and the health endpoints. To turn it off
again, empty the user list (copy `secrets.example/prometheus-web.yml`) and restart Prometheus.
