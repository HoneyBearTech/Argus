# Add-in GPUs on servers (hwmon)

The **Server Hardware** dashboard's GPU panels and the **GPU hot** alert read add-in GPUs that the server's BMC
can't see, such as an Intel Arc card in a Dell server: the iDRAC reads Dell's own parts, not a third-party
card. The server's kernel driver does read the card's temperature, fan, energy use and power limit, and
publishes them as hardware monitoring (hwmon) sensors. Debian's `prometheus-node-exporter`, running with only its hwmon collector, serves
them to Prometheus.

Hosts that run the Argus agent report hwmon sensors already (the agent embeds node_exporter). This page is for
servers without the agent, such as Proxmox VE nodes.

## How it works

```
server ── GPU driver (i915) ── /sys/class/hwmon
  └ prometheus-node-exporter :9100 (hwmon only, basic auth) ◀── scrape, job "hwmon" ── Prometheus (Argus server)
```

- The exporter runs as the unprivileged `prometheus` user. Any user may read hwmon sensors, so it needs no sudo
  and no other privilege.
- It runs only the hwmon collector (`--collector.disable-defaults --collector.hwmon`, and
  `--web.disable-exporter-metrics` for its own Go and process metrics): the readings of every chip the kernel
  monitors, such as the CPU cores and the GPU, and nothing about processes, file systems or the network.
- It listens on the server's own address, port 9100, behind basic auth (user `argus`).
- node_exporter names each chip after its device's path rather than its `hwmonN` number, which can change
  between boots. So an add-in card's `chip` label ends in its PCI address (`…_0000:43:00_0` for a card at
  `0000:43:00.0`), and the panels and the alert name the card by that address.
- The GPU power panel is the rate of the card's energy counter (`node_hwmon_energy_joule_total`), with the
  driver's sustained power limit (`node_hwmon_power_max_watt`) as a dashed line. A card near its limit is busy;
  one that runs hot at low power is short of airflow.

**Which GPUs.** The panels and the alert pick chips whose driver is Intel's `i915` or `xe`. These drivers
register hwmon sensors for discrete cards only, so an integrated GPU doesn't show up. NVIDIA GPUs come from the
GPU exporter instead (the GPUs dashboard).

**Passthrough to a VM.** When the card is passed through to a VM (vfio), the server's driver lets go of it, and
its sensors disappear from the server. The VM's own driver reads them from then on. If the VM runs the Argus
agent, the agent reports the card under the VM's name. The panels and the alert don't filter by job, so they
follow the card.

## Setting up a server

Requirements: Debian 13 (or Proxmox VE 9) and the card's driver loaded (`ls /sys/bus/pci/devices/<address>/hwmon/`
lists a `hwmonN` directory), plus `apache2-utils` (`htpasswd`) on the Argus server.

1. On the Argus server, create the exporter's password once (all servers share it):

   ```sh
   openssl rand -base64 33 | tr -d '/+=\n' | head -c 32 > secrets/hwmon_password
   chmod 644 secrets/hwmon_password   # Prometheus' container reads it, like the other secrets
   ```

2. Copy [`deploy/hwmon/setup-node-exporter.sh`](../deploy/hwmon/setup-node-exporter.sh) to the server and run it
   as root with the password's bcrypt hash on stdin, so only the hash ever reaches the server:

   ```sh
   scp deploy/hwmon/setup-node-exporter.sh root@<server>:
   htpasswd -niB -C 12 argus < secrets/hwmon_password | head -1 | cut -d: -f2- \
     | ssh root@<server> ./setup-node-exporter.sh <server-address>
   ```

   The script:
   - installs `prometheus-node-exporter` without its recommended `prometheus-node-exporter-collectors` (timers
     that run as root), and without letting Debian start the service on its default configuration, which runs
     every default collector on every address without a password;
   - writes `/etc/prometheus/node_exporter_web.yml` (basic auth, user `argus`, the bcrypt hash) and the service's
     arguments in `/etc/default/prometheus-node-exporter` (keeping the package's original as `….dist`);
   - installs the systemd drop-in
     `/etc/systemd/system/prometheus-node-exporter.service.d/10-argus-wait-for-network.conf`, so the service
     starts after `network-online.target` and, should its address still be missing, retries every 5 s instead of
     giving up after systemd's default five fast failures (a Proxmox bridge can get its address after Debian's
     unit has started);
   - starts the service and checks that it listens on the given address only and refuses a scrape without the
     password;
   - lists the hwmon chips it will report, each with its device (a PCI card by its address).

   It can be run again at any time (after a reinstall, or to change the address).

3. On the Argus server, add the server to `targets/hwmon.json` with a `host` label (the name the dashboard and
   the alert show; use the same name as in `targets/ipmi.json`):

   ```json
   [
     {"targets": ["<server-address>:9100"], "labels": {"host": "<server name>"}}
   ]
   ```

   Prometheus picks the file up without a restart. Check it from the Argus server:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' http://<server-address>:9100/metrics   # 401
   printf 'user = "argus:%s"\n' "$(cat secrets/hwmon_password)" \
     | curl -s -K - http://<server-address>:9100/metrics | grep '^node_hwmon_chip_names'   # one line per chip
   ```

## What alerts, and what doesn't

**GPU hot** fires when a GPU stays above 85 °C for 10 minutes, Intel cards read through hwmon and NVIDIA GPUs
alike. GPUs like these slow themselves down in the high 80s to 90s °C. A server that doesn't raise its own fan
speed for a third-party card leaves the card to its own fan, so this is the alert that notices a blocked or
failed fan.

A server whose exporter is down raises the general **Monitoring target down**. A card whose sensors disappear
while the exporter runs raises nothing: the driver let go of it (a passthrough to a VM without the agent, or a
driver failure), and the GPU panels read "No GPU reporting".

## Security notes

- The exporter answers on the network with basic auth but without TLS, so the password crosses the LAN in the
  clear on every scrape. Add `tls_server_config` to `node_exporter_web.yml` and a `tls_config` to the `hwmon`
  job if that matters in your network.
- What it serves is hardware sensor readings only: temperatures, fan speeds, voltages and power figures, with
  the chips' names and device paths.
- The `prometheus` user gets no extra privilege for it.
