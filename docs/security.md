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
   admin password and the Discord webhook come from the server's `secrets/`, which is gitignored,
   mounted read-only and never baked into an image. Prometheus, Grafana and the exporters read
   passwords, API keys, tokens and the webhook from files, so they don't show in `docker inspect` or
   Portainer's container view; the exceptions are the Pi-hole exporter, the Plex exporter and
   tdarr-exporter (only once Tdarr's own login is on), which take their passwords, token and API key only
   from the environment. GitHub secret scanning with push protection
   guards the repository.
3. **No network details in the repository.** Addresses, host names and domains live only in the server's
   `targets/` and `.env`; CI rejects private IP addresses and a private list of internal names in every
   committed file.
4. **Grafana requires a login.** Sign-up and anonymous access are off, and Grafana refuses to start
   without an admin password (`secrets/grafana_admin_password` missing, empty or unreadable).
5. **Only three services listen on the network**: Grafana, Prometheus and Loki (plus, where enabled, the
   Plex exporter on a Plex host and the GPU exporter on a GPU host; both serve metrics only, without a
   login; and the IPMI exporter on a server whose hardware Argus reads, and the Intel GPU exporter, both
   behind basic auth). blackbox_exporter and the exporters are reachable only from the compose
   network, and the agent accepts no connections from other machines.
6. **TLS is verified by default** on every outgoing connection that uses it: web probes (an invalid or
   expired certificate fails the probe), the UniFi console (unless `UNIFI_VERIFY_SSL=false`), the Discord
   webhook, HTTPS scrape targets, and Steerhouse's database (`verify-full`: the certificate must come from
   the CA in `secrets/steerhouse_db_ca` and name the address).
7. **Least privilege for the server.** Every server container runs as a non-root user, with no Linux
   capabilities, can't gain privileges (`no-new-privileges`), and has a read-only root filesystem: it
   writes only its own volume and, where needed, `/tmp` in memory ([hardening](#hardening)). The
   integrations are designed for read-only accounts on the watched services (a read-only UniFi user, a
   non-admin Home Assistant user, Pi-hole app passwords, SNMPv3).
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
  it. The agent blanks the values of credential-looking URL parameters (`apikey`, `api_key`, `access_token`,
  `token`, `X-Plex-Token`, `key`, `signature`, `password`, `passwd`, `secret`) in container and Nginx Proxy
  Manager logs before shipping them, but secrets printed any other way are stored as they are. CI job
  containers started by GitLab Runner (the label it marks them with as managed) are never read: Docker
  keeps their output without the secret masking GitLab applies to job logs.
- **Varken holds Seerr's admin key.** Seerr has no read-only API key, so `secrets/seerr_api_key` can change
  anything in Seerr; Varken only reads with it. Keep the file at mode 600, like the other secrets.
- **Prometheus holds viewing activity.** Varken runs with `stream_details` on, so Prometheus keeps who watched
  what, on which player and from which city (GeoIP is on), with the city's coordinates, for its retention
  time. Anyone who can query Prometheus or open the Varken dashboard can see it. Viewer IP addresses are
  never exported. For GeoIP, Varken downloads MaxMind's GeoLite2 database about monthly (HTTPS, Basic auth
  with the account ID and the `maxmind_license_key` secret).
- **The agent is root on its host.** It no longer runs privileged, but it runs as root in the host's PID
  and network namespaces, can read every file on the host, and holds the Docker and containerd sockets,
  which are equivalent to root even when mounted read-only ([its exceptions](#the-agents-exceptions)). A
  compromised agent image or Argus release is a compromised host; that's why releases are signed.
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
- The IPMI exporter ([IPMI](ipmi.md)) reads the BMC as root through sudo rules that allow only its four
  read-only command lines; keep those rules exact rather than allowing the binaries with any arguments
  (`ipmi-sel` can clear the event log, `ipmi-dcmi` set power limits, `ipmi-chassis` power the server off).
  It uses basic auth without TLS by default; add TLS to its web config if the password shouldn't cross
  your network in the clear.
- Steerhouse ([Steerhouse](steerhouse.md)): Grafana reads its database as `grafana_ro`, a role that can read
  only Steerhouse's `analytics` views, with a connection limit (Grafana opens at most 5), over TLS only.
  Publish the database's port to the Argus server only, and let only TLS connections from it in
  (`hostssl` in `pg_hba.conf`). Steerhouse's metrics port answers only requests with its token, which
  crosses the network in the clear (plain HTTP); firewall the port to the Argus server.
- node_exporter on a server without the agent ([hwmon](hwmon.md)) runs only its hwmon collector, as an
  unprivileged user without sudo, so it serves hardware sensor readings and nothing about processes, file
  systems or the network. It uses basic auth without TLS too.
- The Intel GPU exporter ([Intel GPU](intel-gpu.md)) runs on a server as a transient unprivileged user whose
  only capability is `CAP_PERFMON`, which lets it read performance counters and change nothing; the server's
  `perf_event_paranoid` stays as it is. It serves GPU load, clocks and PCI addresses, with basic auth without
  TLS; the server keeps only the password's bcrypt hash.

## Hardening

What each container runs with. Every service in `docker-compose.yml`, `logs/compose.yml` and
`agent/compose.yml` drops all Linux capabilities (`cap_drop: [ALL]`), can't gain privileges through setuid
binaries or file capabilities (`no-new-privileges:true`), and has a read-only root filesystem; it writes only
to its volume and, where it needs one, a `/tmp` in memory. A capability may be added back only from Docker's
default set, with the reason next to it in the compose file; the one exception is the Intel GPU exporter's
`PERFMON` (below). `tests/test_configs.py` fails if a service breaks
any of this, and CI's boot test starts Grafana and Prometheus with these settings.

| Service | Runs as | Capabilities added back | Read-only root | Writes | Why |
| --- | --- | --- | --- | --- | --- |
| grafana | uid 472 (image) | none | yes | its volume; `/tmp` in memory | Its datasource plugins run as separate processes and talk to Grafana over sockets in `/tmp` |
| prometheus | `nobody` (image) | none | yes | its volume | |
| loki (both compose files) | uid 10001 (image) | none | yes | its volume | |
| blackbox | uid 65534 (Argus image) | none | yes | nothing | HTTP and DNS probes need no privileges (ICMP probes would need root and `NET_RAW`) |
| pihole-exporter | uid 65534 (compose; the image defaults to root) | none | yes | nothing | Needs no file |
| unpoller | uid 65534 (compose; the image sets root) | none | yes | nothing | Only reads its password file |
| snmp-exporter | uid 65534 (compose; the image defaults to root) | none | yes | nothing | Only reads its configuration |
| exportarr (each app) | uid 65532 (image) | none | yes | nothing | |
| qbittorrent-exporter | uid 65534 (compose; the image defaults to root) | none | yes | nothing | Only reads its password file |
| gitlab-ci-pipelines-exporter | uid 65534 (image) | none | yes | nothing | |
| pve-exporter | uid 101 (image) | none | yes | `/tmp` in memory | Python won't start without a writable temporary directory |
| tdarr-exporter | uid 65532 (image) | none | yes | nothing | Needs no file |
| varken | uid 1000 (image) | none | yes | `CONFIG_ROOT/varken/config` (`/config`) | Writes the `varken.ini` it creates on first start; needs no `/tmp` |
| agent | root | `DAC_OVERRIDE` | yes | its data volume | [The agent's exceptions](#the-agents-exceptions) |
| plex-exporter (agent's `plex` profile) | uid 65534 (compose; the image defaults to root) | none | yes | nothing | Needs no file |
| gpu-exporter (agent's `gpu` profile) | uid 65534 (image) | none | yes | nothing | Runs `nvidia-smi`, which the NVIDIA runtime mounts in; the GPU's device files are open to every user |
| intel-gpu-exporter (agent's `intel-gpu` profile) | root | `PERFMON` | yes | nothing | Runs `intel_gpu_top`, which reads the GPU's busy and idle counters (the i915 PMU) through `perf_event_open()`; [see below](#the-intel-gpu-exporters-perfmon) |

Since no server container holds a capability, none can read another user's private file: everything in
`secrets/` that a container mounts must be readable by its user, which means mode 644 (as the templates and
`docs/interfaces.md` say). A file with mode 600 makes that service fail to read it; Grafana then refuses to
start, unpoller logs `Reading UniFi Password File: … permission denied`. The env files in `secrets/` are read by
the compose command, not by the containers, and can stay 600.

### The Intel GPU exporter's PERFMON

`intel_gpu_top` reads an Intel GPU's engine busy time, clocks and idle residency from the i915 driver's
performance counters, which the kernel serves only through `perf_event_open()`. For counters that cover the
whole system, as a GPU's do, the kernel requires `CAP_PERFMON` (or `CAP_SYS_ADMIN`), and Docker's seccomp
profile allows the call only with one of them. `PERFMON` is the narrower one: it lets the process read
performance counters and nothing else. It isn't in Docker's default set, so it's the one capability Argus adds
beyond it, for this one optional container. Docker gives an added capability to root only, so the container
runs as root with `PERFMON` as its only capability, `no-new-privileges` and a read-only filesystem. It opens no
device file (the GPU is found through sysfs) and gets no `/dev/dri`. Lowering the host's
`kernel.perf_event_paranoid` instead would open performance counters to every process on the host.

On a server without the agent, the exporter runs as a systemd service ([docs/intel-gpu.md](intel-gpu.md)) with
the same single capability, under a transient unprivileged user.

### The agent's exceptions

The agent has to see the host it reports on, so it keeps more than the server's services. Each of these was
checked by running the agent without it and comparing what reached Prometheus and Loki:

- **Host network** (`network_mode: host`): node_exporter reads the network interfaces from `/proc/net`,
  which shows only the network namespace the agent runs in. Without it the Host Health network panels show the
  container's own `eth0` instead of the host's interfaces.
- **Host PID** (`pid: host`): node_exporter finds the filesystems to report through PID 1's mount table, and
  cAdvisor reads each container's network counters through the container's processes. Without it the disk
  panels list the agent container's own mounts and container network traffic is incomplete.
- **The Docker and containerd sockets, mounted read-only**: cAdvisor and the log collection find containers,
  their names and labels through them, and read their logs through Docker's API. A read-only mount protects
  the socket file, not the API: whoever controls the agent controls Docker, which is root on the host.
- **The host's filesystem, read-only**: `/` as `/rootfs`, `/sys`, `/run/udev`, `/dev/disk`, `/var/lib/docker`,
  and Nginx Proxy Manager's logs where configured.
- **Root with `DAC_OVERRIDE`**: without capabilities, root can only open files it owns. The agent's data
  directory belongs to the image's `alloy` user (uid 473) and Alloy exits without access to it, and the host
  files it reads (logs, mount points below private directories) can belong to anyone. Every host mount is
  read-only, so this lets it read, not change, them.

It no longer runs `--privileged`: it has no other capability, no access to the host's devices, and Docker's
default seccomp and AppArmor profiles apply. The one thing that costs is cAdvisor's `machine_*` metrics
(the host's CPU count and memory size as cAdvisor sees them), which need `SYS_PTRACE`; Argus doesn't use them,
and node_exporter reports the same facts.

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
