# Quick start

Run the Argus server and one agent on a single machine, and see host, container and service dashboards in
about ten minutes. You need Docker with Compose v2.24 or later on Linux (amd64 or arm64); on macOS or
Windows the server works, but the agent sees Docker Desktop's VM rather than your machine.

## 1. Start the server

```sh
git clone --depth 1 https://github.com/HoneyBearTech/Argus.git && cd Argus
cp .env.example .env
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp secrets.example/* secrets/
```

Edit `.env`:

- set `GF_SECURITY_ADMIN_PASSWORD` to a password of your choice;
- for a trial on your own machine, change the three `*_BIND` lines to listen on loopback only:
  `GRAFANA_BIND=127.0.0.1:3000`, `PROMETHEUS_BIND=127.0.0.1:9090`, `LOKI_BIND=127.0.0.1:3101`.

`COMPOSE_PROFILES=loki` is already set, so Loki (the log store) starts too. Then:

```sh
docker compose up -d
```

Open <http://localhost:3000> and sign in as `admin`. The home page is the Homelab Overview; it's empty
until there's something to watch.

## 2. Watch some services

Edit `targets/blackbox_http.json` and list a few web services you run (or any public sites), each with
the name and group the dashboards show:

```json
[
  { "targets": ["https://example.com"], "labels": { "service": "example", "group": "trial" } },
  { "targets": ["https://grafana.com"], "labels": { "service": "grafana.com", "group": "trial" } }
]
```

Prometheus picks the change up within a minute; the Overview shows each service as up or down, with its
response time and certificate expiry. Delete the other files in `targets/` that you don't use; they only
contain placeholders.

## 3. Add the agent

On the same machine:

```sh
docker run -d --name argus-agent --restart unless-stopped \
  --network host --pid host --privileged \
  -e ARGUS_HOST=$(hostname) \
  -e ARGUS_PROMETHEUS_URL=http://127.0.0.1:9090 \
  -e ARGUS_LOKI_URL=http://127.0.0.1:3101 \
  -v /:/rootfs:ro,rslave -v /sys:/sys:ro -v /run/udev:/run/udev:ro -v /dev/disk:/dev/disk:ro \
  -v /var/lib/docker:/var/lib/docker:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
  ghcr.io/honeybeartech/argus-agent:latest
```

Within a minute, **Host Health** shows the machine's CPU, memory, disks and network, **Docker
Containers** shows every container (including Argus itself), and **Logs** lets you search their output.

## What next

- Add more hosts: run the same agent on each, pointing at the server's address instead of `127.0.0.1`
  (and set the server's `*_BIND` back to `0.0.0.0` so the agents can reach it). See
  [Adding a host](../README.md#adding-a-host).
- Light up the other dashboards (Pi-hole, UniFi, NAS, Home Assistant, media apps, UPS) by adding their
  targets and credentials; the README's [table](../README.md#running-it) lists what each needs.
- Send alerts to Discord by setting `DISCORD_WEBHOOK_URL` in `.env` and running `docker compose up -d`.
- Read [security.md](security.md) before running Argus anywhere but your own trusted network.
- Pin `ARGUS_VERSION` in `.env` to a release and [verify it](verifying-releases.md).

To remove everything: `docker rm -f argus-agent && docker compose down -v` (the `-v` deletes the stored
metrics, logs and Grafana settings).
